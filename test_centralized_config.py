import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import centralized_config as cc


class TestCentralizedConfig(unittest.TestCase):
    def test_load_runtime_config_by_environment(self):
        cfg = cc.load_runtime_config(environment="dev", config_dir=os.path.join("config", "runtime"))
        self.assertEqual(cfg.environment, "dev")
        self.assertIn("documents_base_url", cfg.api_endpoints)
        self.assertTrue(cc.is_feature_enabled(cfg, "enable_tier3"))

    def test_schema_validation_failure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            bad_path = os.path.join(temp_dir, "dev.json")
            with open(bad_path, "w", encoding="utf-8") as handle:
                json.dump({"environment": "dev"}, handle)
            with self.assertRaises(ValueError):
                cc.load_runtime_config(environment="dev", config_dir=temp_dir)

    def test_secrets_manager_merge(self):
        fake_client = MagicMock()
        fake_client.get_secret_value.return_value = {
            "SecretString": json.dumps(
                {
                    "api_endpoints": {"documents_base_url": "https://secret-endpoint.example.com"},
                    "runtime_token": "abc123"
                }
            )
        }
        cfg = cc.load_runtime_config(
            environment="dev",
            config_dir=os.path.join("config", "runtime"),
            load_secrets=True,
            secrets_client=fake_client,
        )
        self.assertEqual(
            cfg.api_endpoints["documents_base_url"],
            "https://secret-endpoint.example.com",
        )
        redacted = cc.redact_effective_config(cfg)
        self.assertEqual(redacted.get("runtime_token"), "<redacted>")

    def test_env_override_for_threshold(self):
        with patch.dict(os.environ, {"FINAL_CONFIDENCE_THRESHOLD": "0.9"}, clear=False):
            cfg = cc.load_runtime_config(environment="dev", config_dir=os.path.join("config", "runtime"))
            self.assertAlmostEqual(cc.get_model_parameter(cfg, "confidence_threshold"), 0.9, places=4)

    def test_api_endpoint_lookup_and_missing_key(self):
        cfg = cc.load_runtime_config(environment="staging", config_dir=os.path.join("config", "runtime"))
        self.assertTrue(cc.get_api_endpoint(cfg, "documents_base_url").startswith("https://"))
        with self.assertRaises(KeyError):
            _ = cc.get_api_endpoint(cfg, "unknown")

    def test_resolve_environment(self):
        with patch.dict(os.environ, {"APP_ENV": "prod"}, clear=False):
            self.assertEqual(cc.resolve_environment(), "prod")
        self.assertEqual(cc.resolve_environment("staging"), "staging")


if __name__ == "__main__":
    unittest.main()
