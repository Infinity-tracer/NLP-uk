"""
Pipeline Base Classes and Interfaces

Provides the foundation for the modular pipeline architecture.
Each stage inherits from PipelineStage and produces a StageResult.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Type
from datetime import datetime
import traceback
import sys


class StageStatus(Enum):
    """Status of a pipeline stage execution."""
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    PARTIAL = "partial"
    SKIPPED = "skipped"
    ERROR = "error"


@dataclass
class StageResult:
    """
    Result from a single pipeline stage.

    Every stage produces this standardized output for debugging and testing.
    """
    stage_name: str
    status: StageStatus
    confidence: float  # 0.0-1.0 stage confidence

    # Primary output data
    data: Any = None

    # Intermediate outputs for debugging
    debug_data: Dict[str, Any] = field(default_factory=dict)

    # Timing
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    duration_ms: float = 0.0

    # Error handling
    error: Optional[str] = None
    error_traceback: Optional[str] = None

    # Metrics
    items_processed: int = 0
    items_filtered: int = 0

    # Notes for debugging
    notes: List[str] = field(default_factory=list)

    def add_note(self, note: str):
        """Add a debug note."""
        self.notes.append(note)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "stage_name": self.stage_name,
            "status": self.status.value,
            "confidence": round(self.confidence, 4),
            "duration_ms": round(self.duration_ms, 2),
            "items_processed": self.items_processed,
            "items_filtered": self.items_filtered,
            "error": self.error,
            "notes": self.notes,
            "debug_data": self.debug_data if self.debug_data else None,
        }


@dataclass
class PipelineContext:
    """
    Shared context passed through all pipeline stages.

    Contains the document data and accumulated results from each stage.
    """
    # Document identification
    doc_id: str
    filename: str

    # Raw input
    input_path: str
    input_bytes: Optional[bytes] = None

    # Text content (populated by OCR stage)
    raw_ocr_text: str = ""
    normalized_text: str = ""

    # Page information
    pages_processed: int = 0
    page_images: List[str] = field(default_factory=list)
    page_texts: List[str] = field(default_factory=list)

    # Detected document structure (populated by Section Detection)
    sections: List[Dict[str, Any]] = field(default_factory=list)
    document_type: str = "unknown"
    document_type_confidence: float = 0.0

    # Patient information
    patient_info: Dict[str, Any] = field(default_factory=dict)

    # Extracted entities (populated by NER and parsers)
    entities: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)

    # SNOMED mappings
    snomed_mappings: List[Dict[str, Any]] = field(default_factory=list)

    # Validated entities
    validated_entities: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    rejected_entities: List[Dict[str, Any]] = field(default_factory=list)

    # Summaries
    summaries: Dict[str, Any] = field(default_factory=dict)

    # Stage results for debugging
    stage_results: Dict[str, StageResult] = field(default_factory=dict)

    # Configuration
    config: "PipelineConfig" = None

    # Timestamps
    created_at: datetime = field(default_factory=datetime.now)

    def get_stage_result(self, stage_name: str) -> Optional[StageResult]:
        """Get result from a specific stage."""
        return self.stage_results.get(stage_name)

    def get_text(self) -> str:
        """Get best available text (normalized if available, else raw)."""
        return self.normalized_text or self.raw_ocr_text

    def add_entities(self, category: str, entities: List[Dict[str, Any]]):
        """Add entities to a category."""
        if category not in self.entities:
            self.entities[category] = []
        self.entities[category].extend(entities)

    def get_all_entities(self) -> List[Dict[str, Any]]:
        """Get all entities across all categories."""
        all_entities = []
        for category, entities in self.entities.items():
            for e in entities:
                e_copy = e.copy()
                e_copy["_category"] = category
                all_entities.append(e_copy)
        return all_entities


@dataclass
class PipelineConfig:
    """
    Configuration for the pipeline.

    Controls which stages run and their parameters.
    """
    # Stage enable/disable
    enable_ocr_cleanup: bool = True
    enable_section_detection: bool = True
    enable_abbreviation_expansion: bool = True
    enable_negation_detection: bool = True
    enable_ner: bool = True
    enable_medication_parser: bool = True
    enable_investigation_parser: bool = True
    enable_temporal_reasoning: bool = True
    enable_snomed_retrieval: bool = True
    enable_llm_validation: bool = True
    enable_clinical_validation: bool = True
    enable_summary_generation: bool = True

    # Confidence thresholds
    entity_confidence_threshold: float = 0.40
    snomed_confidence_threshold: float = 0.50

    # OCR settings
    ocr_provider: str = "textract"  # textract, tesseract
    ocr_confidence_threshold: float = 0.90  # Below this, flag for review

    # NER settings
    ner_model: str = "rule_based"  # rule_based, transformers

    # SNOMED settings
    snomed_max_candidates: int = 5
    snomed_chunk_size: int = 4500  # AWS Comprehend limit

    # LLM settings
    llm_model: str = "us.anthropic.claude-sonnet-4-20250514-v1:0"
    llm_temperature: float = 0.1

    # Summary settings
    summary_max_words: int = 120

    # Debug settings
    debug_mode: bool = False
    save_intermediate: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            k: v for k, v in self.__dict__.items()
        }


class PipelineStage(ABC):
    """
    Abstract base class for all pipeline stages.

    Each stage must implement:
    - name: Stage identifier
    - process(): Main processing logic

    Optional overrides:
    - validate_input(): Check prerequisites
    - get_dependencies(): List of required prior stages
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique stage identifier."""
        pass

    @property
    def description(self) -> str:
        """Human-readable description."""
        return f"{self.name} stage"

    def get_dependencies(self) -> List[str]:
        """
        List of stage names that must complete before this stage.
        Default: no dependencies.
        """
        return []

    def validate_input(self, context: PipelineContext) -> bool:
        """
        Validate that prerequisites are met.
        Override to add validation logic.
        Returns True if valid, False otherwise.
        """
        return True

    @abstractmethod
    def process(self, context: PipelineContext) -> StageResult:
        """
        Execute the stage processing.

        Args:
            context: Pipeline context with document data and prior results

        Returns:
            StageResult with output data and confidence score
        """
        pass

    def run(self, context: PipelineContext) -> StageResult:
        """
        Execute the stage with timing and error handling.

        This is the main entry point called by the orchestrator.
        """
        start_time = datetime.now()

        try:
            # Validate input
            if not self.validate_input(context):
                return StageResult(
                    stage_name=self.name,
                    status=StageStatus.SKIPPED,
                    confidence=0.0,
                    error="Input validation failed",
                    start_time=start_time,
                    end_time=datetime.now(),
                )

            # Run processing
            result = self.process(context)

            # Set timing
            end_time = datetime.now()
            result.start_time = start_time
            result.end_time = end_time
            result.duration_ms = (end_time - start_time).total_seconds() * 1000

            # Store in context
            context.stage_results[self.name] = result

            return result

        except Exception as e:
            end_time = datetime.now()
            error_tb = traceback.format_exc()

            print(f"[ERROR] Stage {self.name} failed: {e}", file=sys.stderr)
            print(error_tb, file=sys.stderr)

            result = StageResult(
                stage_name=self.name,
                status=StageStatus.ERROR,
                confidence=0.0,
                error=str(e),
                error_traceback=error_tb,
                start_time=start_time,
                end_time=end_time,
                duration_ms=(end_time - start_time).total_seconds() * 1000,
            )

            context.stage_results[self.name] = result
            return result


class StageRegistry:
    """
    Registry of all available pipeline stages.

    Allows dynamic stage discovery and instantiation.
    """
    _stages: Dict[str, Type[PipelineStage]] = {}

    @classmethod
    def register(cls, stage_class: Type[PipelineStage]):
        """Register a stage class."""
        instance = stage_class()
        cls._stages[instance.name] = stage_class
        return stage_class

    @classmethod
    def get(cls, name: str) -> Optional[Type[PipelineStage]]:
        """Get a stage class by name."""
        return cls._stages.get(name)

    @classmethod
    def list_all(cls) -> List[str]:
        """List all registered stage names."""
        return list(cls._stages.keys())

    @classmethod
    def create(cls, name: str) -> Optional[PipelineStage]:
        """Create an instance of a stage."""
        stage_class = cls.get(name)
        if stage_class:
            return stage_class()
        return None
