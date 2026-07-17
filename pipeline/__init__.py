"""
NHS Clinical Document Processing Pipeline

A modular, hybrid pipeline for clinical document processing.
Each stage is independently testable with confidence scores and intermediate outputs.

Pipeline stages:
1. OCR - Text extraction from images/PDFs
2. OCR Cleanup - Medical text normalization
3. Section Detection - Document structure parsing
4. Abbreviation Expansion - Clinical abbreviation resolution
5. Negation Detection - Assertion status determination
6. NER - Named Entity Recognition (17 categories)
7. Medication Parser - Structured medication extraction
8. Investigation Parser - Lab/imaging result parsing
9. Temporal Reasoning - Temporal state classification
10. SNOMED Retrieval - Ontology candidate retrieval
11. LLM Validation - Claude-based validation
12. Clinical Validation - Rule-based validation
13. Summary Generation - Multi-audience summaries
14. Confidence Scoring - Per-component confidence
15. Structured Output - Final JSON assembly
"""

from .base import (
    PipelineStage,
    StageResult,
    PipelineContext,
    PipelineConfig,
    StageStatus,
)
from .orchestrator import ClinicalPipeline

__all__ = [
    "PipelineStage",
    "StageResult",
    "PipelineContext",
    "PipelineConfig",
    "StageStatus",
    "ClinicalPipeline",
]
