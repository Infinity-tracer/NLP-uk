import json
import os
import tempfile
import unittest

from bedrock_prompt_management import BedrockPromptManager


class TestBedrockPromptManagement(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.registry_path = os.path.join(self.temp_dir.name, "prompt_registry.json")
        self.change_log_path = os.path.join(self.temp_dir.name, "prompt_change_log.json")
        self.manager = BedrockPromptManager(
            registry_path=self.registry_path,
            change_log_path=self.change_log_path,
            sync_enabled=False,
            auto_snapshot=False,
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_compose_prompt_tracks_template_versions(self):
        prompt, tracking = self.manager.compose_track_b_prompt(
            document_id="doc_001",
            role_key="clinician",
            role_guidance="Focus on diagnosis and treatment details.",
            document_type="discharge_summary",
            clinical_document="Patient diagnosed with hypertension and diabetes.",
            retrieved_context=["Relevant cardiology history", "Medication trend"],
            output_schema={"type": "object", "properties": {"summary": {"type": "string"}}},
        )
        self.assertIn("Action generation policy for clinician", prompt)
        self.assertIn("Strict reliability rules", prompt)
        self.assertIn("selected_versions", tracking)
        self.assertEqual(set(tracking["selected_versions"].keys()), {
            "medical_summarization",
            "role_based_actions",
            "error_correction",
        })
        for details in tracking["components"].values():
            self.assertEqual(details["bedrock_sync_status"], "skipped")

    def test_ab_test_assignment_is_deterministic(self):
        self.manager.configure_ab_test(
            template_name="medical_summarization",
            enabled=True,
            weights={"v1": 0.3, "v2": 0.7},
            salt="fixed-salt",
            rationale="test deterministic split",
        )

        _, first_tracking = self.manager.compose_track_b_prompt(
            document_id="doc_ab_001",
            role_key="clinician",
            role_guidance="test",
            document_type="clinical_note",
            clinical_document="text",
            retrieved_context=[],
            output_schema={"type": "object"},
        )
        _, second_tracking = self.manager.compose_track_b_prompt(
            document_id="doc_ab_001",
            role_key="clinician",
            role_guidance="test",
            document_type="clinical_note",
            clinical_document="text",
            retrieved_context=[],
            output_schema={"type": "object"},
        )

        self.assertEqual(
            first_tracking["selected_versions"]["medical_summarization"],
            second_tracking["selected_versions"]["medical_summarization"],
        )
        self.assertEqual(
            first_tracking["selection_modes"]["medical_summarization"],
            "ab_test",
        )

    def test_rollback_updates_active_version(self):
        self.manager.set_active_version(
            template_name="medical_summarization",
            version="v2",
            rationale="adopt v2",
        )
        self.assertEqual(
            self.manager.registry["templates"]["medical_summarization"]["active_version"],
            "v2",
        )

        self.manager.rollback_to_version(
            template_name="medical_summarization",
            version="v1",
            rationale="rollback for stability",
        )
        self.assertEqual(
            self.manager.registry["templates"]["medical_summarization"]["active_version"],
            "v1",
        )

        with open(self.change_log_path, "r", encoding="utf-8") as handle:
            history = json.load(handle)
        self.assertTrue(any(entry["change_type"] == "ROLLBACK" for entry in history))

    def test_sync_skipped_when_disabled(self):
        result = self.manager.sync_template_to_bedrock("medical_summarization", "v1")
        self.assertEqual(result["status"], "skipped")


if __name__ == "__main__":
    unittest.main()
