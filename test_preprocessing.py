import os
import tempfile
import unittest
from unittest.mock import patch

import cv2
import numpy as np

import preprocessing


class TestPreprocessing(unittest.TestCase):
    def test_preprocess_image_success(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = os.path.join(temp_dir, "sample_original.jpg")
            output_path = os.path.join(temp_dir, "sample_CLEANED.jpg")

            sample = np.full((120, 120), 255, dtype=np.uint8)
            cv2.putText(sample, "A", (35, 70), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0,), 2)
            cv2.imwrite(image_path, sample)

            result = preprocessing.preprocess_image(image_path, output_path)

            self.assertEqual(result, output_path)
            self.assertTrue(os.path.exists(output_path))
            saved = cv2.imread(output_path, cv2.IMREAD_GRAYSCALE)
            self.assertIsNotNone(saved)
            self.assertEqual(saved.shape, sample.shape)

    def test_preprocess_image_raises_for_invalid_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = os.path.join(temp_dir, "out.jpg")
            with self.assertRaises(ValueError):
                preprocessing.preprocess_image("does_not_exist.jpg", output_path)

    def test_deskew_blank_image_returns_original(self):
        blank = np.zeros((100, 100), dtype=np.uint8)
        result = preprocessing._deskew(blank)
        self.assertTrue(np.array_equal(result, blank))

    @patch("preprocessing.preprocess_image")
    def test_preprocess_batch_collects_success_and_failures(self, mock_preprocess):
        mock_preprocess.side_effect = [None, Exception("bad image")]
        image_paths = [
            "temp_pages/doc_page1_original.jpg",
            "temp_pages/doc_page2_original.jpg",
        ]

        success, failed = preprocessing.preprocess_batch(image_paths)

        self.assertEqual(len(success), 1)
        self.assertEqual(len(failed), 1)
        self.assertEqual(success[0]["cleaned"], "temp_pages/doc_page1_CLEANED.jpg")
        self.assertIn("bad image", failed[0]["error"])

    def test_get_tier1_payload_parses_page_and_doc_name(self):
        payload = preprocessing.get_tier1_payload(
            [
                {"cleaned": "temp_pages/discharge_summary1page2_CLEANED.jpg"},
                {"cleaned": "temp_pages/unexpected-name.jpg"},
            ]
        )
        self.assertEqual(payload[0]["doc_name"], "discharge_summary1")
        self.assertEqual(payload[0]["page"], 2)
        self.assertEqual(payload[1]["page"], 0)


if __name__ == "__main__":
    unittest.main()
