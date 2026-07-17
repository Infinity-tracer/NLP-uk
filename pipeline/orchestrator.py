"""
Pipeline Orchestrator

Coordinates execution of all pipeline stages in sequence.
Handles dependencies, error recovery, and result collection.
"""

import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Type

from .base import (
    PipelineStage,
    PipelineContext,
    PipelineConfig,
    StageResult,
    StageStatus,
)


class ClinicalPipeline:
    """
    Clinical Document Processing Pipeline Orchestrator.

    Executes 15 stages in sequence:
    1. OCR → 2. OCR Cleanup → 3. Section Detection → 4. Abbreviation Expansion
    5. Negation Detection → 6. NER → 7. Medication Parser → 8. Investigation Parser
    9. Temporal Reasoning → 10. SNOMED Retrieval → 11. LLM Validation
    12. Clinical Validation → 13. Summary Generation → 14. Confidence Scoring
    15. Structured Output

    Each stage is modular and independently testable.
    """

    def __init__(self, config: Optional[PipelineConfig] = None):
        """Initialize pipeline with optional configuration."""
        self.config = config or PipelineConfig()
        self._stages: List[PipelineStage] = []
        self._initialized = False

    def initialize(self):
        """Initialize all pipeline stages."""
        from .stages import (
            OCRStage,
            OCRCleanupStage,
            SectionDetectionStage,
            AbbreviationExpansionStage,
            NegationDetectionStage,
            NERStage,
            MedicationParserStage,
            InvestigationParserStage,
            TemporalReasoningStage,
            SNOMEDRetrievalStage,
            LLMValidationStage,
            ClinicalValidationStage,
            SummaryGenerationStage,
            ConfidenceScoringStage,
            StructuredOutputStage,
        )

        # Build stage list based on config
        self._stages = []

        # Stage 1: OCR (always required)
        self._stages.append(OCRStage())

        # Stage 2: OCR Cleanup
        if self.config.enable_ocr_cleanup:
            self._stages.append(OCRCleanupStage())

        # Stage 3: Section Detection
        if self.config.enable_section_detection:
            self._stages.append(SectionDetectionStage())

        # Stage 4: Abbreviation Expansion
        if self.config.enable_abbreviation_expansion:
            self._stages.append(AbbreviationExpansionStage())

        # Stage 5: Negation Detection
        if self.config.enable_negation_detection:
            self._stages.append(NegationDetectionStage())

        # Stage 6: NER
        if self.config.enable_ner:
            self._stages.append(NERStage())

        # Stage 7: Medication Parser
        if self.config.enable_medication_parser:
            self._stages.append(MedicationParserStage())

        # Stage 8: Investigation Parser
        if self.config.enable_investigation_parser:
            self._stages.append(InvestigationParserStage())

        # Stage 9: Temporal Reasoning
        if self.config.enable_temporal_reasoning:
            self._stages.append(TemporalReasoningStage())

        # Stage 10: SNOMED Retrieval
        if self.config.enable_snomed_retrieval:
            self._stages.append(SNOMEDRetrievalStage())

        # Stage 11: LLM Validation
        if self.config.enable_llm_validation:
            self._stages.append(LLMValidationStage())

        # Stage 12: Clinical Validation
        if self.config.enable_clinical_validation:
            self._stages.append(ClinicalValidationStage())

        # Stage 13: Summary Generation
        if self.config.enable_summary_generation:
            self._stages.append(SummaryGenerationStage())

        # Stage 14: Confidence Scoring (always required)
        self._stages.append(ConfidenceScoringStage())

        # Stage 15: Structured Output (always required)
        self._stages.append(StructuredOutputStage())

        self._initialized = True
        print(f"[INFO] Pipeline initialized with {len(self._stages)} stages", file=sys.stderr)

    def process(
        self,
        doc_id: str,
        input_path: str,
        page_images: List[str],
    ) -> Dict:
        """
        Process a document through the full pipeline.

        Args:
            doc_id: Unique document identifier
            input_path: Path to source document
            page_images: List of page image paths

        Returns:
            Final structured output dictionary
        """
        if not self._initialized:
            self.initialize()

        # Create context
        context = PipelineContext(
            doc_id=doc_id,
            filename=Path(input_path).name,
            input_path=input_path,
            page_images=page_images,
            config=self.config,
        )

        # Track overall timing
        start_time = datetime.now()
        stage_times = []

        # Execute each stage
        for i, stage in enumerate(self._stages):
            stage_start = datetime.now()

            print(f"[INFO] Stage {i+1}/{len(self._stages)}: {stage.name}", file=sys.stderr)

            # Check dependencies
            deps = stage.get_dependencies()
            deps_met = all(
                context.get_stage_result(dep) is not None
                for dep in deps
            )

            if not deps_met:
                print(f"[WARN] Skipping {stage.name}: dependencies not met", file=sys.stderr)
                result = StageResult(
                    stage_name=stage.name,
                    status=StageStatus.SKIPPED,
                    confidence=0.0,
                    error="Dependencies not met",
                )
                context.stage_results[stage.name] = result
                continue

            # Run stage
            try:
                result = stage.run(context)
                stage_times.append({
                    "stage": stage.name,
                    "duration_ms": result.duration_ms,
                    "status": result.status.value,
                })

                if result.status == StageStatus.ERROR:
                    print(f"[ERROR] Stage {stage.name} failed: {result.error}", file=sys.stderr)
                else:
                    print(
                        f"[INFO]   → {result.status.value} "
                        f"(conf={result.confidence:.3f}, "
                        f"items={result.items_processed}, "
                        f"{result.duration_ms:.0f}ms)",
                        file=sys.stderr
                    )

            except Exception as e:
                print(f"[ERROR] Stage {stage.name} exception: {e}", file=sys.stderr)
                result = StageResult(
                    stage_name=stage.name,
                    status=StageStatus.ERROR,
                    confidence=0.0,
                    error=str(e),
                )
                context.stage_results[stage.name] = result

        # Get final output
        output_result = context.get_stage_result("structured_output")
        if output_result and output_result.data:
            final_output = output_result.data
        else:
            # Fallback output
            final_output = {
                "doc_id": doc_id,
                "filename": context.filename,
                "status": "error",
                "error": "Pipeline failed to produce output",
                "pipeline_stages": {
                    name: res.to_dict()
                    for name, res in context.stage_results.items()
                },
            }

        # Add pipeline metadata
        end_time = datetime.now()
        final_output["_pipeline"] = {
            "total_duration_ms": (end_time - start_time).total_seconds() * 1000,
            "stages_executed": len(self._stages),
            "stage_times": stage_times,
        }

        return final_output

    def process_text(
        self,
        doc_id: str,
        text: str,
        filename: str = "text_input.txt",
    ) -> Dict:
        """
        Process raw text through the pipeline (skips OCR).

        Useful for testing or when text is already extracted.
        """
        if not self._initialized:
            self.initialize()

        # Create context with pre-populated text
        context = PipelineContext(
            doc_id=doc_id,
            filename=filename,
            input_path="",
            config=self.config,
        )
        context.raw_ocr_text = text
        context.normalized_text = text
        context.pages_processed = 1

        # Create fake OCR result
        context.stage_results["ocr"] = StageResult(
            stage_name="ocr",
            status=StageStatus.DONE,
            confidence=1.0,
            data={"full_text": text},
        )

        # Execute remaining stages (skip OCR)
        start_time = datetime.now()

        for i, stage in enumerate(self._stages):
            if stage.name == "ocr":
                continue  # Skip OCR, already have text

            print(f"[INFO] Stage: {stage.name}", file=sys.stderr)

            # Check dependencies
            deps = stage.get_dependencies()
            deps_met = all(
                context.get_stage_result(dep) is not None
                for dep in deps
            )

            if not deps_met:
                print(f"[WARN] Skipping {stage.name}: dependencies not met", file=sys.stderr)
                continue

            try:
                result = stage.run(context)
                print(
                    f"[INFO]   → {result.status.value} "
                    f"(conf={result.confidence:.3f})",
                    file=sys.stderr
                )
            except Exception as e:
                print(f"[ERROR] Stage {stage.name} failed: {e}", file=sys.stderr)

        # Get final output
        output_result = context.get_stage_result("structured_output")
        if output_result and output_result.data:
            return output_result.data

        return {
            "doc_id": doc_id,
            "status": "error",
            "error": "Pipeline failed",
        }

    def get_stage(self, name: str) -> Optional[PipelineStage]:
        """Get a specific stage by name."""
        for stage in self._stages:
            if stage.name == name:
                return stage
        return None

    def list_stages(self) -> List[str]:
        """List all stage names in order."""
        return [s.name for s in self._stages]


def create_pipeline(config: Optional[PipelineConfig] = None) -> ClinicalPipeline:
    """Factory function to create and initialize a pipeline."""
    pipeline = ClinicalPipeline(config)
    pipeline.initialize()
    return pipeline
