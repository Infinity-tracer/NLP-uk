"""
Pipeline Stages

Individual processing stages for the clinical document pipeline.
Each stage is modular, independently testable, and produces confidence scores.
"""

from .s01_ocr import OCRStage
from .s02_ocr_cleanup import OCRCleanupStage
from .s03_section_detection import SectionDetectionStage
from .s04_abbreviation_expansion import AbbreviationExpansionStage
from .s05_negation_detection import NegationDetectionStage
from .s06_ner import NERStage
from .s07_medication_parser import MedicationParserStage
from .s08_investigation_parser import InvestigationParserStage
from .s09_temporal_reasoning import TemporalReasoningStage
from .s10_snomed_retrieval import SNOMEDRetrievalStage
from .s11_llm_validation import LLMValidationStage
from .s12_clinical_validation import ClinicalValidationStage
from .s13_summary_generation import SummaryGenerationStage
from .s14_confidence_scoring import ConfidenceScoringStage
from .s15_structured_output import StructuredOutputStage

__all__ = [
    "OCRStage",
    "OCRCleanupStage",
    "SectionDetectionStage",
    "AbbreviationExpansionStage",
    "NegationDetectionStage",
    "NERStage",
    "MedicationParserStage",
    "InvestigationParserStage",
    "TemporalReasoningStage",
    "SNOMEDRetrievalStage",
    "LLMValidationStage",
    "ClinicalValidationStage",
    "SummaryGenerationStage",
    "ConfidenceScoringStage",
    "StructuredOutputStage",
]

# Ordered list of all stages for pipeline execution
PIPELINE_STAGES = [
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
]
