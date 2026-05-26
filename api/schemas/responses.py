"""Response schemas for API endpoints."""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum
from datetime import datetime


class ProcessingStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    REVIEW_REQUIRED = "review_required"


class TierStatus(BaseModel):
    """Status of a single tier processing."""
    tier: str
    status: ProcessingStatus
    duration_ms: Optional[int] = None
    confidence: Optional[float] = None
    error: Optional[str] = None
    output_path: Optional[str] = None


class HealthResponse(BaseModel):
    """Health check response."""
    status: str = "healthy"
    version: str
    timestamp: str
    dependencies: Dict[str, str] = Field(default_factory=dict)


class Tier0Response(BaseModel):
    """Response from Tier 0 preprocessing."""
    status: str
    total_pages: int
    preprocessed_images: List[str]
    failed_pages: List[Dict[str, Any]] = Field(default_factory=list)
    processing_time_ms: int


class Tier1Response(BaseModel):
    """Response from Tier 1 Textract extraction."""
    status: str
    pages_processed: int
    output_files: List[str]
    average_confidence: Optional[float] = None
    processing_time_ms: int


class Tier2Response(BaseModel):
    """Response from Tier 2 LayoutLMv3 refinement."""
    status: str
    refined_elements: List[Dict[str, Any]]
    escalation_queue: List[Dict[str, Any]] = Field(default_factory=list)
    quality_score: float
    processing_time_ms: int


class Tier3Response(BaseModel):
    """Response from Tier 3 Vision-LLM correction."""
    status: str
    corrected_regions: List[Dict[str, Any]]
    audit_log: List[Dict[str, Any]]
    processing_time_ms: int


class TrackAResponse(BaseModel):
    """Response from Track A SNOMED mapping."""
    status: str
    entities: List[Dict[str, Any]]
    snomed_codes: List[Dict[str, Any]]
    processing_time_ms: int


class TrackBResponse(BaseModel):
    """Response from Track B summarization."""
    status: str
    summary: str
    key_findings: List[str] = Field(default_factory=list)
    action_plans: Dict[str, List[str]] = Field(default_factory=dict)
    processing_time_ms: int


class PipelineJobResponse(BaseModel):
    """Response when starting a pipeline job."""
    job_id: str
    status: ProcessingStatus = ProcessingStatus.QUEUED
    message: str = "Document queued for processing"


class PipelineStatusResponse(BaseModel):
    """Response for pipeline status check."""
    job_id: str
    status: ProcessingStatus
    current_tier: Optional[str] = None
    progress_percent: int = 0
    tiers: List[TierStatus] = Field(default_factory=list)
    error: Optional[str] = None


class PipelineResultResponse(BaseModel):
    """Full pipeline result."""
    job_id: str
    status: ProcessingStatus
    document_name: str
    total_processing_time_ms: int
    tier0: Optional[Tier0Response] = None
    tier1: Optional[Tier1Response] = None
    tier2: Optional[Tier2Response] = None
    tier3: Optional[Tier3Response] = None
    track_a: Optional[TrackAResponse] = None
    track_b: Optional[TrackBResponse] = None
    audit_trail: List[Dict[str, Any]] = Field(default_factory=list)
