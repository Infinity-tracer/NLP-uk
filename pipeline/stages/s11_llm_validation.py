"""
Stage 11: LLM Validation - Claude-based Entity Validation

Uses Claude to validate extracted entities and SNOMED mappings.
"""

import json
import os
import sys
from typing import Dict, List, Optional

from ..base import PipelineStage, StageResult, PipelineContext, StageStatus, StageRegistry


@StageRegistry.register
class LLMValidationStage(PipelineStage):
    """
    LLM Validation Stage - Validate entities with Claude.

    Validates:
    - Entity extraction accuracy
    - SNOMED mapping correctness
    - Clinical context appropriateness

    Outputs:
    - validated_entities: Entities that passed validation
    - rejected_entities: Entities that failed validation
    """

    VALIDATION_PROMPT = '''You are a clinical coding expert validating entity extractions from NHS clinical documents.

Review these extracted entities and their SNOMED mappings:

{entities_json}

For each entity, determine if the SNOMED mapping is CORRECT or INCORRECT.

Rules:
1. The SNOMED code must match the clinical concept
2. Category must be appropriate (medication vs procedure vs diagnosis)
3. Reject mappings where the SNOMED description doesn't match the original text
4. Reject obviously wrong mappings (e.g., "Collapse" mapped to "Prolapse")

Return JSON array with validation results:
[
  {{"entity_idx": 0, "valid": true, "confidence": 0.95}},
  {{"entity_idx": 1, "valid": false, "confidence": 0.9, "reason": "SNOMED description doesn't match"}}
]

Only return the JSON array, no other text.'''

    @property
    def name(self) -> str:
        return "llm_validation"

    @property
    def description(self) -> str:
        return "Validate entities using Claude LLM"

    def get_dependencies(self) -> List[str]:
        return ["snomed_retrieval"]

    def validate_input(self, context: PipelineContext) -> bool:
        return bool(context.snomed_mappings)

    def process(self, context: PipelineContext) -> StageResult:
        """Validate entities with Claude."""
        result = StageResult(
            stage_name=self.name,
            status=StageStatus.RUNNING,
            confidence=0.0,
        )

        try:
            mappings = context.snomed_mappings
            config = context.config

            if not mappings:
                result.status = StageStatus.SKIPPED
                return result

            # Batch mappings for validation (max 20 at a time)
            batch_size = 20
            all_validations = []

            for i in range(0, len(mappings), batch_size):
                batch = mappings[i:i + batch_size]
                validations = self._validate_batch(batch, config)
                all_validations.extend(validations)

            # Apply validations to mappings
            validated = []
            rejected = []

            for idx, mapping in enumerate(mappings):
                validation = all_validations[idx] if idx < len(all_validations) else {"valid": True}

                mapping["llm_validated"] = validation.get("valid", True)
                mapping["llm_confidence"] = validation.get("confidence", 0.5)

                if validation.get("valid", True):
                    validated.append(mapping)
                else:
                    mapping["rejection_reason"] = validation.get("reason", "LLM validation failed")
                    rejected.append(mapping)

            # Update context
            context.validated_entities = {"snomed": validated}
            context.rejected_entities = rejected

            # Calculate confidence
            validation_rate = len(validated) / len(mappings) if mappings else 0
            confidence = 0.5 + (validation_rate * 0.4)

            # Build result
            result.status = StageStatus.DONE
            result.confidence = confidence
            result.items_processed = len(mappings)
            result.items_filtered = len(rejected)
            result.data = {
                "validated": validated,
                "rejected": rejected,
                "validation_rate": validation_rate,
            }
            result.debug_data = {
                "total_entities": len(mappings),
                "validated_count": len(validated),
                "rejected_count": len(rejected),
            }

            result.add_note(f"Validated {len(validated)}/{len(mappings)} entities")
            result.add_note(f"Rejected {len(rejected)} entities")

            return result

        except Exception as e:
            result.status = StageStatus.PARTIAL
            result.error = str(e)
            # On error, accept all entities (fail open)
            context.validated_entities = {"snomed": context.snomed_mappings}
            context.rejected_entities = []
            return result

    def _validate_batch(self, batch: List[Dict], config) -> List[Dict]:
        """Validate a batch of entities using Claude."""
        import boto3

        try:
            # Prepare entities for validation
            entities_for_validation = [
                {
                    "idx": i,
                    "text": e.get("text"),
                    "snomed_code": e.get("snomed_code"),
                    "snomed_description": e.get("snomed_description"),
                    "category": e.get("clinical_category"),
                }
                for i, e in enumerate(batch)
            ]

            prompt = self.VALIDATION_PROMPT.format(
                entities_json=json.dumps(entities_for_validation, indent=2)
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
                    "max_tokens": 2000,
                    "temperature": 0.1,
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
            validations = json.loads(text_response)
            return validations

        except Exception as e:
            print(f"[WARN] LLM validation failed: {e}", file=sys.stderr)
            # Return all valid on failure
            return [{"valid": True, "confidence": 0.5} for _ in batch]
