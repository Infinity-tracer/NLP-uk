import json
import os
import tempfile
import unittest
from unittest.mock import patch

import tier2_router


class FakeSQS:
    def __init__(self):
        self.queue_urls = {
            "TrackA_Medical_Queue": "https://q/track-a",
            "TrackB_Summary_Queue": "https://q/track-b",
            "Tier2_LayoutLM_Queue": "https://q/tier2",
        }
        self.sent_messages = []

    def create_queue(self, QueueName):
        return {"QueueUrl": self.queue_urls[QueueName]}

    def send_message(self, QueueUrl, MessageBody):
        self.sent_messages.append((QueueUrl, json.loads(MessageBody)))
        return {"MessageId": "mid"}


class TestTier2Router(unittest.TestCase):
    def test_calculate_document_confidence(self):
        data = {
            "Blocks": [
                {"BlockType": "LINE", "Confidence": 95.0},
                {"BlockType": "WORD", "Confidence": 85.0},
                {"BlockType": "TABLE", "Confidence": 70.0},
            ]
        }
        confidence = tier2_router.calculate_document_confidence(data)
        self.assertAlmostEqual(confidence, 90.0, places=3)

    def test_find_image_for_textract(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            textract_path = os.path.join(temp_dir, "doc_1_textract.json")
            image_path = os.path.join(temp_dir, "doc_1.jpg")
            with open(textract_path, "w", encoding="utf-8") as f:
                f.write("{}")
            with open(image_path, "wb") as f:
                f.write(b"img")
            found = tier2_router.find_image_for_textract(textract_path, image_dir=temp_dir)
            self.assertEqual(found, image_path)

    @patch("tier2_router.create_secure_client")
    def test_setup_queues_and_route_data(self, mock_client):
        fake_sqs = FakeSQS()
        mock_client.return_value = fake_sqs

        with tempfile.TemporaryDirectory() as temp_dir:
            json_dir = os.path.join(temp_dir, "textract_outputs")
            img_dir = os.path.join(temp_dir, "temp_pages")
            os.makedirs(json_dir, exist_ok=True)
            os.makedirs(img_dir, exist_ok=True)

            high_path = os.path.join(json_dir, "high_textract.json")
            low_path = os.path.join(json_dir, "low_textract.json")
            with open(high_path, "w", encoding="utf-8") as f:
                json.dump({"Blocks": [{"BlockType": "LINE", "Confidence": 99.0}]}, f)
            with open(low_path, "w", encoding="utf-8") as f:
                json.dump({"Blocks": [{"BlockType": "LINE", "Confidence": 40.0}]}, f)

            with open(os.path.join(img_dir, "low.jpg"), "wb") as f:
                f.write(b"img")

            # The helper looks for temp_pages in cwd unless image_dir passed;
            # keep routing assertion focused on destination queues.
            tier2_router.setup_queues_and_route_data(input_dir=json_dir, confidence_threshold=90.0)

            destinations = [url for url, _ in fake_sqs.sent_messages]
            self.assertIn("https://q/track-a", destinations)
            self.assertIn("https://q/track-b", destinations)
            self.assertIn("https://q/tier2", destinations)


if __name__ == "__main__":
    unittest.main()
