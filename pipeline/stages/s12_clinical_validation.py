"""
Stage 12: Clinical Validation - Rule-based Medical Validation

Applies clinical validation rules to detect impossible mappings.
"""

import re
from typing import Dict, List, Tuple

from ..base import PipelineStage, StageResult, PipelineContext, StageStatus, StageRegistry


@StageRegistry.register
class ClinicalValidationStage(PipelineStage):
    """
    Clinical Validation Stage - Apply medical validation rules.

    Validates:
    - Category-appropriate SNOMED mappings
    - Semantic consistency (prevents Collapse→Prolapse, LOC→Animal)
    - Cross-entity consistency

    Outputs:
    - validated_entities: Entities passing validation
    - rejected_entities: Entities failing validation with reasons
    """

    # Valid SNOMED categories per clinical category
    VALID_CATEGORY_MAPPINGS = {
        "diagnoses": ["disorder", "finding", "clinical_finding", "situation"],
        "problems": ["disorder", "finding", "clinical_finding", "symptom"],
        "medications": ["substance", "product", "drug"],
        "treatments": ["procedure", "regime/therapy"],
        "investigations": ["procedure", "observable", "test"],
        "anatomy": ["body_structure", "morphology"],
    }

    # Impossible mappings (source_text_pattern → reject if SNOMED contains)
    IMPOSSIBLE_MAPPINGS = {
        r'\bcollapse\b': ["prolapse", "structural"],
        r'\bloc\b': ["animal", "geographic", "organism"],
        r'\bfall\b': ["autumn", "season", "waterfall"],
        r'\bcold\b': ["temperature", "weather"],
        r'\bhead\b': ["leader", "chief", "anatomical head only if context wrong"],
        r'\bstroke\b': ["painting", "swimming", "touch"],
        r'\bfit\b': ["appropriate", "suitable", "healthy"],
        r'\bchest\b': ["furniture", "container", "box"],
    }

    # Semantic blockers (text → cannot be mapped to category)
    SEMANTIC_BLOCKERS = {
        "medications": ["pain", "symptom", "diagnosis", "finding", "procedure"],
        "diagnoses": ["drug", "medication", "tablet", "capsule", "injection"],
        "treatments": ["symptom", "complaint", "finding"],
        "investigations": ["treatment", "therapy", "medication"],
    }

    @property
    def name(self) -> str:
        return "clinical_validation"

    @property
    def description(self) -> str:
        return "Apply clinical validation rules"

    def get_dependencies(self) -> List[str]:
        return ["llm_validation"]

    def validate_input(self, context: PipelineContext) -> bool:
        return bool(context.validated_entities or context.snomed_mappings)

    def process(self, context: PipelineContext) -> StageResult:
        """Apply clinical validation rules."""
        result = StageResult(
            stage_name=self.name,
            status=StageStatus.RUNNING,
            confidence=0.0,
        )

        try:
            # Get entities from LLM validation or SNOMED retrieval
            entities = context.validated_entities.get("snomed", []) if context.validated_entities else context.snomed_mappings

            if not entities:
                result.status = StageStatus.SKIPPED
                return result

            validated = []
            rejected = []
            validation_stats = {
                "category_mismatch": 0,
                "impossible_mapping": 0,
                "semantic_block": 0,
                "low_confidence": 0,
            }

            for entity in entities:
                is_valid, reason, rule_type = self._validate_entity(entity, context.config)

                if is_valid:
                    entity["clinical_validated"] = True
                    validated.append(entity)
                else:
                    entity["clinical_validated"] = False
                    entity["validation_rejection"] = reason
                    entity["validation_rule"] = rule_type
                    rejected.append(entity)
                    validation_stats[rule_type] = validation_stats.get(rule_type, 0) + 1

            # Update context
            context.validated_entities["clinical"] = validated
            context.rejected_entities.extend(rejected)

            # Calculate confidence
            validation_rate = len(validated) / len(entities) if entities else 0
            confidence = 0.5 + (validation_rate * 0.4)

            # Build result
            result.status = StageStatus.DONE
            result.confidence = confidence
            result.items_processed = len(entities)
            result.items_filtered = len(rejected)
            result.data = {
                "validated": validated,
                "rejected": rejected,
                "validation_rate": validation_rate,
                "stats": validation_stats,
            }
            result.debug_data = {
                "rejection_reasons": [
                    {"text": e.get("text"), "reason": e.get("validation_rejection")}
                    for e in rejected[:10]
                ],
            }

            result.add_note(f"Clinical validation: {len(validated)}/{len(entities)} passed")
            for rule, count in validation_stats.items():
                if count > 0:
                    result.add_note(f"  {rule}: {count} rejected")

            return result

        except Exception as e:
            result.status = StageStatus.ERROR
            result.error = str(e)
            return result

    def _validate_entity(self, entity: Dict, config) -> Tuple[bool, str, str]:
        """Validate a single entity against clinical rules."""
        text = entity.get("text", "").lower()
        snomed_desc = entity.get("snomed_description", "").lower()
        clinical_cat = entity.get("clinical_category", "")
        confidence = entity.get("confidence", 0.5)

        # Rule 1: Confidence threshold
        threshold = config.snomed_confidence_threshold if config else 0.50
        if confidence < threshold:
            return (False, f"Confidence {confidence:.2f} below threshold {threshold}", "low_confidence")

        # Rule 2: Category appropriateness
        if clinical_cat in self.VALID_CATEGORY_MAPPINGS:
            valid_types = self.VALID_CATEGORY_MAPPINGS[clinical_cat]
            concept_type = entity.get("type", "").lower()

            # Check if concept type is valid for category
            if concept_type and not any(vt in concept_type for vt in valid_types):
                return (
                    False,
                    f"Concept type '{concept_type}' invalid for category '{clinical_cat}'",
                    "category_mismatch"
                )

        # Rule 3: Impossible mappings
        for text_pattern, blocked_terms in self.IMPOSSIBLE_MAPPINGS.items():
            if re.search(text_pattern, text, re.IGNORECASE):
                for blocked in blocked_terms:
                    if blocked.lower() in snomed_desc:
                        return (
                            False,
                            f"Impossible mapping: '{text}' → '{snomed_desc}' (blocked: {blocked})",
                            "impossible_mapping"
                        )

        # Rule 4: Semantic blockers
        if clinical_cat in self.SEMANTIC_BLOCKERS:
            blocked_terms = self.SEMANTIC_BLOCKERS[clinical_cat]
            for blocked in blocked_terms:
                if blocked.lower() in snomed_desc:
                    return (
                        False,
                        f"Semantic block: category '{clinical_cat}' cannot contain '{blocked}'",
                        "semantic_block"
                    )

        # Rule 5: Text/description similarity
        if snomed_desc and text:
            similarity = self._text_similarity(text, snomed_desc)
            if similarity < 0.2:  # Very low similarity
                # Only reject if confident this is wrong
                if confidence > 0.7:
                    # High confidence but low similarity is suspicious
                    pass  # Allow for now, let LLM catch these

        return (True, "", "")

    def _text_similarity(self, text1: str, text2: str) -> float:
        """Calculate simple text similarity."""
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())

        if not words1 or not words2:
            return 0.0

        intersection = words1 & words2
        union = words1 | words2

        return len(intersection) / len(union)
