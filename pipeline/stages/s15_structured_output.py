"""
Stage 15: Structured Output - Final JSON Assembly

Assembles the final structured JSON output with all entities and metadata.
"""

from datetime import datetime
from typing import Dict, List, Optional, Any

from ..base import PipelineStage, StageResult, PipelineContext, StageStatus, StageRegistry


@StageRegistry.register
class StructuredOutputStage(PipelineStage):
    """
    Structured Output Stage - Assemble final JSON.

    Produces the standardized output schema with:
    - metadata
    - summary
    - diagnoses, symptoms, medications, investigations, vitals
    - procedures, referrals, gp_actions, hospital_actions, follow_up
    - coding
    - confidence

    All entities include evidence spans (page, line, sentence).
    """

    @property
    def name(self) -> str:
        return "structured_output"

    @property
    def description(self) -> str:
        return "Assemble final structured JSON output"

    def get_dependencies(self) -> List[str]:
        return ["confidence_scoring"]

    def validate_input(self, context: PipelineContext) -> bool:
        return True  # Always runs

    def process(self, context: PipelineContext) -> StageResult:
        """Assemble final output."""
        result = StageResult(
            stage_name=self.name,
            status=StageStatus.RUNNING,
            confidence=0.0,
        )

        try:
            # Get confidence scores
            conf_result = context.get_stage_result("confidence_scoring")
            confidence_scores = {}
            if conf_result and conf_result.data:
                confidence_scores = conf_result.data.get("confidence_scores", {})

            # Build metadata
            metadata = {
                "doc_id": context.doc_id,
                "filename": context.filename,
                "processed_at": datetime.now().isoformat(),
                "status": "processed" if confidence_scores.get("overall", 0) >= confidence_scores.get("threshold", 0.4) else "review_required",
                "pages_processed": context.pages_processed,
                "document_type": context.document_type,
                "document_type_confidence": context.document_type_confidence,
                "pipeline_stages": {
                    name: res.to_dict()
                    for name, res in context.stage_results.items()
                },
            }

            # Transform entities to standardized format
            diagnoses = self._transform_entities(
                context.entities.get("diagnosis", []) +
                context.validated_entities.get("clinical", []),
                "diagnosis"
            )

            symptoms = self._transform_entities(
                context.entities.get("symptom", []) +
                context.entities.get("sign", []),
                "symptom"
            )

            medications = self._transform_entities(
                context.entities.get("medication_structured", []) +
                context.entities.get("medication", []),
                "medication"
            )

            investigations = self._transform_entities(
                context.entities.get("investigation_structured", []) +
                context.entities.get("investigation", []),
                "investigation"
            )

            vitals = self._transform_entities(
                context.entities.get("vital_sign", []),
                "vital"
            )

            procedures = self._transform_entities(
                context.entities.get("procedure", []),
                "procedure"
            )

            referrals = self._transform_entities(
                context.entities.get("referral", []),
                "referral"
            )

            gp_actions = self._transform_entities(
                context.entities.get("gp_action", []),
                "action"
            )

            hospital_actions = self._transform_entities(
                context.entities.get("hospital_action", []),
                "action"
            )

            follow_up = self._transform_entities(
                context.entities.get("follow_up", []),
                "follow_up"
            )

            # Build coding output
            coding = {
                "snomed_codes": [
                    self._transform_to_clinical_entity(e)
                    for e in context.snomed_mappings
                    if e.get("clinical_validated", True)
                ],
                "icd10_codes": [],
                "total_codes": len(context.snomed_mappings),
                "mapping_confidence": confidence_scores.get("snomed", 0.5),
                "validation_rejected": [
                    self._transform_to_clinical_entity(e)
                    for e in context.rejected_entities
                ],
            }

            # Build final output
            output = {
                # New standardized schema
                "metadata": metadata,
                "summary": context.summaries,
                "diagnoses": diagnoses,
                "symptoms": symptoms,
                "medications": medications,
                "investigations": investigations,
                "vitals": vitals,
                "procedures": procedures,
                "referrals": referrals,
                "gp_actions": gp_actions,
                "hospital_actions": hospital_actions,
                "follow_up": follow_up,
                "coding": coding,
                "confidence": confidence_scores,
                "patient_info": context.patient_info,
                "extracted_text": context.normalized_text[:8000] or context.raw_ocr_text[:8000],
                "raw_ocr_text": context.raw_ocr_text[:8000],

                # Legacy compatibility fields
                "doc_id": context.doc_id,
                "filename": context.filename,
                "processed_at": metadata["processed_at"],
                "status": metadata["status"],
                "pages_processed": context.pages_processed,
                "pipeline_stages": metadata["pipeline_stages"],
                "unified_confidence": confidence_scores.get("overall", 0.5),
                "confidence_threshold": confidence_scores.get("threshold", 0.4),
                "requires_review": metadata["status"] == "review_required",
                "confidence_scores": confidence_scores,
                "letter_type": context.document_type,
                "summaries": context.summaries,
                "snomed": {
                    "diagnoses": [e for e in coding["snomed_codes"] if e.get("clinical_category") == "diagnoses"],
                    "problems": [e for e in coding["snomed_codes"] if e.get("clinical_category") == "problems"],
                    "medications": [e for e in coding["snomed_codes"] if e.get("clinical_category") == "medications"],
                    "treatments": [e for e in coding["snomed_codes"] if e.get("clinical_category") == "treatments"],
                    "investigations": [e for e in coding["snomed_codes"] if e.get("clinical_category") == "investigations"],
                    "snomed_confidence": confidence_scores.get("snomed", 0.5),
                    "validation_rejected": coding["validation_rejected"],
                },
            }

            # Build result
            result.status = StageStatus.DONE
            result.confidence = confidence_scores.get("overall", 0.5)
            result.data = output

            entity_counts = {
                "diagnoses": len(diagnoses),
                "symptoms": len(symptoms),
                "medications": len(medications),
                "investigations": len(investigations),
                "vitals": len(vitals),
            }
            total_entities = sum(entity_counts.values())

            result.add_note(f"Assembled output with {total_entities} entities")
            for cat, count in entity_counts.items():
                if count > 0:
                    result.add_note(f"  {cat}: {count}")

            return result

        except Exception as e:
            result.status = StageStatus.ERROR
            result.error = str(e)
            return result

    def _transform_entities(self, entities: List[Dict], category: str) -> List[Dict]:
        """Transform entities to standardized format with evidence."""
        transformed = []
        seen = set()

        for entity in entities:
            # Deduplicate
            key = (entity.get("text", ""), entity.get("start_pos", 0))
            if key in seen:
                continue
            seen.add(key)

            transformed_entity = self._transform_to_clinical_entity(entity)
            if transformed_entity:
                transformed.append(transformed_entity)

        return transformed

    def _transform_to_clinical_entity(self, entity: Dict) -> Optional[Dict]:
        """Transform a single entity to standardized ClinicalEntity format."""
        text = entity.get("text", "").strip()
        if not text:
            return None

        # Build evidence span
        evidence = {
            "text": text,
            "page": 1,  # Default to page 1
            "line": entity.get("line_number", 1),
            "sentence": entity.get("evidence", text)[:200],
            "char_start": entity.get("start_pos", 0),
            "char_end": entity.get("end_pos", len(text)),
        }

        # Determine ontology
        snomed_code = entity.get("snomed_code")
        ontology_system = "SNOMED-CT" if snomed_code else "NONE"

        return {
            # Core identification
            "text": text,
            "normalized_text": entity.get("snomed_description") or text,

            # Evidence (REQUIRED)
            "evidence": evidence,

            # Ontology
            "ontology_code": snomed_code,
            "ontology_system": ontology_system,
            "ontology_description": entity.get("snomed_description"),
            "ontology_source_text": text if snomed_code else None,

            # Confidence
            "confidence": entity.get("confidence", 0.5),
            "mapping_confidence": entity.get("llm_confidence", entity.get("confidence", 0.5)),
            "validated": entity.get("clinical_validated", True),
            "validation_note": entity.get("validation_rejection"),

            # Clinical context
            "assertion_status": entity.get("assertion", "present"),
            "temporal_status": entity.get("temporal_state", "current"),
            "section": entity.get("section", "unknown"),

            # Category
            "clinical_category": entity.get("clinical_category"),

            # Deduplication
            "canonical_form": entity.get("canonical_form"),
            "aliases": entity.get("aliases"),
        }
