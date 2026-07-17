"""
Stage 13: Summary Generation - Multi-audience Clinical Summaries

Generates summaries for clinicians, patients, and pharmacists.
"""

import json
import os
import sys
from typing import Dict, List, Optional

from ..base import PipelineStage, StageResult, PipelineContext, StageStatus, StageRegistry


@StageRegistry.register
class SummaryGenerationStage(PipelineStage):
    """
    Summary Generation Stage - Generate clinical summaries.

    Generates:
    - Clinician summary (technical, structured)
    - Patient summary (plain language)
    - Pharmacist summary (medication-focused)
    - Follow-up actions

    Outputs:
    - summaries: Dict with all summary types
    """

    CLINICIAN_PROMPT = '''Generate a clinical summary for this NHS document.

Document text:
{text}

Extracted entities:
{entities_json}

Requirements:
- Prioritize: PC → O/E → Ix → Dx → Rx → Advice → F/U
- Maximum 120 words
- Preserve chronology
- No hallucination - only include information from the document
- Exclude historical PMH unless clinically relevant to current presentation

Return JSON:
{{
  "summary": "Clinical summary text...",
  "confidence": 0.85
}}'''

    PATIENT_PROMPT = '''Generate a patient-friendly summary of this clinical letter.

Document text:
{text}

Requirements:
- Plain English, avoid medical jargon
- Explain what was found and what happens next
- Maximum 100 words
- Be reassuring but accurate

Return JSON:
{{
  "summary": "Patient summary text...",
  "confidence": 0.85
}}'''

    PHARMACIST_PROMPT = '''Generate a pharmacist summary focusing on medications.

Document text:
{text}

Medications extracted:
{medications_json}

Requirements:
- List all medications with doses and frequencies
- Note any changes, new medications, or stopped medications
- Flag any potential interactions or concerns
- Maximum 80 words

Return JSON:
{{
  "summary": "Pharmacist summary text...",
  "confidence": 0.85
}}'''

    ACTIONS_PROMPT = '''Extract follow-up actions from this clinical document.

Document text:
{text}

Requirements:
- Identify actions for GP surgery (doctor, pharmacist, reception)
- Identify actions for the sender/hospital
- Identify patient actions and booking requirements
- Be specific and actionable

Return JSON:
{{
  "gp_surgery_actions": {{
    "doctor": ["action1", "action2"],
    "pharmacist": ["action1"],
    "reception": ["action1"]
  }},
  "sender_actions": {{
    "doctor": ["action1"],
    "pharmacist": [],
    "reception": []
  }},
  "patient_actions": ["action1", "action2"],
  "patient_booking": ["action1"],
  "follow_up_text": "Summary of follow-up requirements..."
}}'''

    @property
    def name(self) -> str:
        return "summary_generation"

    @property
    def description(self) -> str:
        return "Generate multi-audience clinical summaries"

    def get_dependencies(self) -> List[str]:
        return ["clinical_validation"]

    def validate_input(self, context: PipelineContext) -> bool:
        return bool(context.get_text())

    def process(self, context: PipelineContext) -> StageResult:
        """Generate clinical summaries."""
        result = StageResult(
            stage_name=self.name,
            status=StageStatus.RUNNING,
            confidence=0.0,
        )

        try:
            text = context.get_text()
            config = context.config

            if not text:
                result.status = StageStatus.SKIPPED
                return result

            # Get validated entities
            validated = context.validated_entities.get("clinical", [])

            # Generate summaries
            clinician = self._generate_summary(text, validated, "clinician", config)
            patient = self._generate_summary(text, validated, "patient", config)
            pharmacist = self._generate_summary(text, validated, "pharmacist", config)
            actions = self._generate_actions(text, config)

            summaries = {
                "clinician": clinician,
                "patient": patient,
                "pharmacist": pharmacist,
                "actions_structured": actions.get("structured", {}),
                "follow_up_actions": actions.get("follow_up_text", ""),
                "llm_confidence": (
                    clinician.get("confidence", 0.5) +
                    patient.get("confidence", 0.5) +
                    pharmacist.get("confidence", 0.5)
                ) / 3,
            }

            # Update context
            context.summaries = summaries

            # Calculate confidence
            confidence = summaries["llm_confidence"]

            # Build result
            result.status = StageStatus.DONE
            result.confidence = confidence
            result.items_processed = 4  # 3 summaries + actions
            result.data = {
                "summaries": summaries,
            }
            result.debug_data = {
                "clinician_length": len(clinician.get("summary", "")),
                "patient_length": len(patient.get("summary", "")),
                "pharmacist_length": len(pharmacist.get("summary", "")),
            }

            result.add_note(f"Generated 3 summaries + actions")
            result.add_note(f"Clinician: {len(clinician.get('summary', ''))} chars")
            result.add_note(f"Patient: {len(patient.get('summary', ''))} chars")

            return result

        except Exception as e:
            result.status = StageStatus.ERROR
            result.error = str(e)
            return result

    def _generate_summary(
        self,
        text: str,
        entities: List[Dict],
        summary_type: str,
        config
    ) -> Dict:
        """Generate a single summary type."""
        import boto3

        try:
            # Select prompt
            if summary_type == "clinician":
                prompt = self.CLINICIAN_PROMPT.format(
                    text=text[:6000],
                    entities_json=json.dumps(entities[:30], indent=2)
                )
            elif summary_type == "patient":
                prompt = self.PATIENT_PROMPT.format(text=text[:5000])
            else:  # pharmacist
                medications = [e for e in entities if e.get("clinical_category") == "medications"]
                prompt = self.PHARMACIST_PROMPT.format(
                    text=text[:4000],
                    medications_json=json.dumps(medications[:20], indent=2)
                )

            # Call Bedrock
            client = boto3.client(
                "bedrock-runtime",
                region_name=os.getenv("AWS_REGION", "us-east-1"),
            )

            model_id = config.llm_model if config else "us.anthropic.claude-sonnet-4-20250514-v1:0"

            response = client.invoke_model(
                modelId=model_id,
                body=json.dumps({
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 1000,
                    "temperature": 0.2,
                    "thinking": {"type": "disabled"},
                    "messages": [
                        {"role": "user", "content": prompt}
                    ]
                })
            )

            response_body = json.loads(response["body"].read())
            content = response_body.get("content", [])

            # Extract text response
            text_response = ""
            for block in content:
                if block.get("type") == "text":
                    text_response = block.get("text", "")
                    break

            # Parse JSON response
            result = json.loads(text_response)
            return result

        except Exception as e:
            print(f"[WARN] Summary generation failed for {summary_type}: {e}", file=sys.stderr)
            return {"summary": "", "confidence": 0.3}

    def _generate_actions(self, text: str, config) -> Dict:
        """Generate follow-up actions."""
        import boto3

        try:
            prompt = self.ACTIONS_PROMPT.format(text=text[:5000])

            client = boto3.client(
                "bedrock-runtime",
                region_name=os.getenv("AWS_REGION", "us-east-1"),
            )

            model_id = config.llm_model if config else "us.anthropic.claude-sonnet-4-20250514-v1:0"

            response = client.invoke_model(
                modelId=model_id,
                body=json.dumps({
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 1000,
                    "temperature": 0.2,
                    "thinking": {"type": "disabled"},
                    "messages": [
                        {"role": "user", "content": prompt}
                    ]
                })
            )

            response_body = json.loads(response["body"].read())
            content = response_body.get("content", [])

            text_response = ""
            for block in content:
                if block.get("type") == "text":
                    text_response = block.get("text", "")
                    break

            result = json.loads(text_response)
            return {
                "structured": {
                    "gp_surgery_actions": result.get("gp_surgery_actions", {}),
                    "sender_actions": result.get("sender_actions", {}),
                    "patient_actions": result.get("patient_actions", []),
                    "patient_booking": result.get("patient_booking", []),
                },
                "follow_up_text": result.get("follow_up_text", ""),
            }

        except Exception as e:
            print(f"[WARN] Actions generation failed: {e}", file=sys.stderr)
            return {
                "structured": {
                    "gp_surgery_actions": {"doctor": [], "pharmacist": [], "reception": []},
                    "sender_actions": {"doctor": [], "pharmacist": [], "reception": []},
                },
                "follow_up_text": "",
            }
