import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import lambda_confidence_aggregator as agg


class TestLambdaConfidenceAggregator(unittest.TestCase):
    def test_to_unit_interval_and_extractors(self):
        self.assertEqual(agg._to_unit_interval(50), 0.5)
        self.assertEqual(agg._to_unit_interval("bad", default=0.3), 0.3)
        with tempfile.TemporaryDirectory() as temp_dir:
            textract = os.path.join(temp_dir, "t.json")
            with open(textract, "w", encoding="utf-8") as f:
                json.dump({"Blocks": [{"BlockType": "LINE", "Confidence": 90.0}]}, f)
            self.assertAlmostEqual(agg._extract_textract_confidence_from_file(textract), 0.9, places=3)

            track_a = os.path.join(temp_dir, "a.json")
            with open(track_a, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "categorized_entities": {
                            "Diagnosis": [{"confidence": 0.8, "source": "comprehend_medical"}],
                            "Medication": [{"confidence": 0.7, "source": "semantic_fallback"}],
                        },
                        "unified_confidence_score": 0.6,
                    },
                    f,
                )
            c, faiss = agg._extract_track_a_scores(track_a)
            self.assertGreater(c, 0)
            self.assertGreater(faiss, 0)

            track_b = os.path.join(temp_dir, "b.json")
            with open(track_b, "w", encoding="utf-8") as f:
                json.dump({"confidence_score": 0.77}, f)
            self.assertAlmostEqual(agg._extract_track_b_llm_confidence(track_b), 0.77, places=3)

    def test_calculate_weighted_score_default_weights(self):
        components = {
            "textract": 0.9,
            "comprehend": 0.8,
            "faiss": 0.7,
            "llm_logprobs": 0.6,
        }
        score, latency_ms = agg.calculate_weighted_score(components, agg.DEFAULT_WEIGHTS)
        self.assertAlmostEqual(score, 0.75, places=6)
        self.assertLess(latency_ms, 100.0)

    def test_resolve_weights_normalizes_custom_values(self):
        weights = agg.resolve_weights({"weights": {"textract": 0.5, "comprehend": 0.2, "faiss": 0.2, "llm_logprobs": 0.1}})
        self.assertAlmostEqual(sum(weights.values()), 1.0, places=6)
        self.assertAlmostEqual(weights["textract"], 0.5, places=6)

    def test_collect_component_scores_accepts_percentage_inputs(self):
        scores = agg.collect_component_scores(
            {
                "textract_confidence": 93.0,
                "comprehend_confidence": 82.0,
                "faiss_similarity": 70.0,
                "llm_logprobs_confidence": 88.0,
            }
        )
        self.assertAlmostEqual(scores["textract"], 0.93, places=6)
        self.assertAlmostEqual(scores["llm_logprobs"], 0.88, places=6)

    def test_collect_component_scores_from_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            textract = os.path.join(temp_dir, "textract.json")
            track_a = os.path.join(temp_dir, "track_a.json")
            track_b = os.path.join(temp_dir, "track_b.json")
            with open(textract, "w", encoding="utf-8") as f:
                json.dump({"Blocks": [{"BlockType": "WORD", "Confidence": 95.0}]}, f)
            with open(track_a, "w", encoding="utf-8") as f:
                json.dump({"categorized_entities": {}, "unified_confidence_score": 0.4}, f)
            with open(track_b, "w", encoding="utf-8") as f:
                json.dump({"confidence_score": 0.5}, f)
            out = agg.collect_component_scores(
                {
                    "textract_json_path": textract,
                    "track_a_output_path": track_a,
                    "track_b_output_path": track_b,
                }
            )
            self.assertGreater(out["textract"], 0)

    def test_resolve_weights_fallback_to_default_when_zero(self):
        w = agg.resolve_weights({"weights": {"textract": 0, "comprehend": 0, "faiss": 0, "llm_logprobs": 0}})
        self.assertEqual(w, agg.DEFAULT_WEIGHTS)

    @patch("lambda_confidence_aggregator.create_secure_client")
    def test_route_document_creates_queue_if_missing(self, mock_client):
        fake = MagicMock()
        fake.get_queue_url.side_effect = RuntimeError("missing")
        fake.create_queue.return_value = {"QueueUrl": "https://q/new"}
        mock_client.return_value = fake
        out = agg.route_document("d1", 0.9, 0.85, {"textract": 1, "comprehend": 1, "faiss": 1, "llm_logprobs": 1}, agg.DEFAULT_WEIGHTS, 1.0)
        self.assertEqual(out["route"], "bypass_database")

    @patch("lambda_confidence_aggregator.get_audit_logger")
    def test_log_routing_audit(self, mock_get_logger):
        logger = MagicMock()
        mock_get_logger.return_value = logger
        agg.log_routing_audit(
            "doc1",
            {
                "queue_name": "q",
                "routing_payload": {
                    "route": "human_review",
                    "final_confidence_score": 0.4,
                    "threshold": 0.85,
                    "component_scores": {},
                    "weights": {},
                    "calculation_latency_ms": 1.0,
                    "calculation_latency_sla_met": True,
                },
            },
        )
        logger.log_change.assert_called_once()

    @patch("lambda_confidence_aggregator.log_routing_audit")
    @patch("lambda_confidence_aggregator.route_document")
    def test_lambda_handler_routes_high_confidence(self, mock_route, mock_audit):
        mock_route.return_value = {
            "route": "bypass_database",
            "queue_name": "Confidence_High_Bypass_Queue",
            "queue_url": "https://example/high",
            "routing_payload": {
                "final_confidence_score": 0.9,
                "threshold": 0.85,
                "component_scores": {"textract": 0.9, "comprehend": 0.9, "faiss": 0.9, "llm_logprobs": 0.9},
                "weights": agg.DEFAULT_WEIGHTS,
                "calculation_latency_ms": 0.05,
                "calculation_latency_sla_met": True,
                "route": "bypass_database",
            },
        }
        response = agg.lambda_handler(
            {
                "document_id": "doc_high",
                "textract_confidence": 0.9,
                "comprehend_confidence": 0.9,
                "faiss_similarity": 0.9,
                "llm_logprobs_confidence": 0.9,
            },
            None,
        )
        self.assertEqual(response["statusCode"], 200)
        body = json.loads(response["body"])
        self.assertEqual(body["route"], "bypass_database")
        mock_route.assert_called_once()
        mock_audit.assert_called_once()

    @patch("lambda_confidence_aggregator.log_routing_audit")
    @patch("lambda_confidence_aggregator.route_document")
    def test_lambda_handler_routes_low_confidence(self, mock_route, mock_audit):
        mock_route.return_value = {
            "route": "human_review",
            "queue_name": "Confidence_Low_Review_Queue",
            "queue_url": "https://example/low",
            "routing_payload": {
                "final_confidence_score": 0.61,
                "threshold": 0.85,
                "component_scores": {"textract": 0.6, "comprehend": 0.6, "faiss": 0.6, "llm_logprobs": 0.65},
                "weights": agg.DEFAULT_WEIGHTS,
                "calculation_latency_ms": 0.03,
                "calculation_latency_sla_met": True,
                "route": "human_review",
            },
        }
        response = agg.lambda_handler(
            {
                "document_id": "doc_low",
                "textract_confidence": 0.6,
                "comprehend_confidence": 0.6,
                "faiss_similarity": 0.6,
                "llm_logprobs_confidence": 0.65,
            },
            None,
        )
        self.assertEqual(response["statusCode"], 200)
        body = json.loads(response["body"])
        self.assertEqual(body["route"], "human_review")
        mock_route.assert_called_once()
        mock_audit.assert_called_once()

    @patch("lambda_confidence_aggregator.collect_component_scores", side_effect=RuntimeError("oops"))
    @patch("lambda_confidence_aggregator._get_monitor")
    def test_lambda_handler_error_path(self, mock_get_monitor, _collect):
        monitor = MagicMock()
        mock_get_monitor.return_value = monitor
        response = agg.lambda_handler({"document_id": "doc_err"}, None)
        self.assertEqual(response["statusCode"], 500)


if __name__ == "__main__":
    unittest.main()
