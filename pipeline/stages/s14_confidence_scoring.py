"""
Stage 14: Confidence Scoring - Per-component Confidence Calculation

Calculates weighted confidence scores for all pipeline components.
"""

from typing import Dict, List, Optional

from ..base import PipelineStage, StageResult, PipelineContext, StageStatus, StageRegistry


@StageRegistry.register
class ConfidenceScoringStage(PipelineStage):
    """
    Confidence Scoring Stage - Calculate per-component confidence.

    Computes confidence for:
    - OCR quality
    - NER extraction
    - SNOMED mapping
    - Medication parsing
    - Investigation parsing
    - Summary generation
    - Document classification

    Outputs:
    - confidence_scores: Per-component breakdown
    - overall_confidence: Weighted aggregate
    """

    # Default weights for each component
    DEFAULT_WEIGHTS = {
        "ocr": 0.20,
        "ner": 0.15,
        "snomed": 0.20,
        "medication": 0.10,
        "investigation": 0.10,
        "summary": 0.15,
        "classification": 0.10,
    }

    @property
    def name(self) -> str:
        return "confidence_scoring"

    @property
    def description(self) -> str:
        return "Calculate per-component confidence scores"

    def get_dependencies(self) -> List[str]:
        return ["summary_generation"]

    def validate_input(self, context: PipelineContext) -> bool:
        return bool(context.stage_results)

    def process(self, context: PipelineContext) -> StageResult:
        """Calculate confidence scores."""
        result = StageResult(
            stage_name=self.name,
            status=StageStatus.RUNNING,
            confidence=0.0,
        )

        try:
            # Get confidence from each stage
            scores = {}

            # OCR confidence
            ocr_result = context.get_stage_result("ocr")
            scores["ocr"] = ocr_result.confidence if ocr_result else 0.5

            # NER confidence
            ner_result = context.get_stage_result("ner")
            scores["ner"] = ner_result.confidence if ner_result else 0.5

            # SNOMED confidence
            snomed_result = context.get_stage_result("snomed_retrieval")
            clinical_result = context.get_stage_result("clinical_validation")
            if clinical_result:
                scores["snomed"] = clinical_result.confidence
            elif snomed_result:
                scores["snomed"] = snomed_result.confidence
            else:
                scores["snomed"] = 0.5

            # Medication confidence
            med_result = context.get_stage_result("medication_parser")
            scores["medication"] = med_result.confidence if med_result else 0.5

            # Investigation confidence
            inv_result = context.get_stage_result("investigation_parser")
            scores["investigation"] = inv_result.confidence if inv_result else 0.5

            # Summary confidence
            summary_result = context.get_stage_result("summary_generation")
            if summary_result and summary_result.data:
                summaries = summary_result.data.get("summaries", {})
                scores["summary"] = summaries.get("llm_confidence", 0.5)
            else:
                scores["summary"] = 0.5

            # Classification confidence
            section_result = context.get_stage_result("section_detection")
            if section_result and section_result.data:
                scores["classification"] = section_result.data.get("document_type_confidence", 0.5)
            else:
                scores["classification"] = 0.5

            # Calculate weighted overall
            weights = self.DEFAULT_WEIGHTS.copy()
            overall = sum(scores.get(k, 0.5) * w for k, w in weights.items())

            # Determine threshold
            config = context.config
            threshold = config.entity_confidence_threshold if config else 0.40

            # Build confidence output
            confidence_output = {
                "ocr": round(scores.get("ocr", 0.5), 4),
                "ner": round(scores.get("ner", 0.5), 4),
                "snomed": round(scores.get("snomed", 0.5), 4),
                "medication": round(scores.get("medication", 0.5), 4),
                "investigation": round(scores.get("investigation", 0.5), 4),
                "summary": round(scores.get("summary", 0.5), 4),
                "classification": round(scores.get("classification", 0.5), 4),
                "overall": round(overall, 4),
                "threshold": threshold,
                "weights": weights,
            }

            # Build result
            result.status = StageStatus.DONE
            result.confidence = overall
            result.items_processed = len(scores)
            result.data = {
                "confidence_scores": confidence_output,
                "requires_review": overall < threshold,
            }
            result.debug_data = {
                "raw_scores": scores,
            }

            result.add_note(f"Overall confidence: {overall:.3f}")
            for component, score in scores.items():
                result.add_note(f"  {component}: {score:.3f}")

            return result

        except Exception as e:
            result.status = StageStatus.ERROR
            result.error = str(e)
            return result
