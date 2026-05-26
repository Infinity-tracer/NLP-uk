"""Request schemas for API endpoints."""
from typing import Optional, List
from pydantic import BaseModel, Field


class Tier0Request(BaseModel):
    """Request for Tier 0 preprocessing."""
    pass  # File upload handled separately


class Tier1Request(BaseModel):
    """Request for Tier 1 Textract extraction."""
    image_paths: Optional[List[str]] = Field(
        None,
        description="List of cleaned image paths. If not provided, uses default temp_pages directory."
    )


class Tier2Request(BaseModel):
    """Request for Tier 2 LayoutLMv3 refinement."""
    textract_json_path: str = Field(..., description="Path to Textract JSON output")
    image_path: str = Field(..., description="Path to the corresponding image")


class Tier3Request(BaseModel):
    """Request for Tier 3 Vision-LLM correction."""
    low_confidence_regions: List[dict] = Field(..., description="Regions below confidence threshold")
    image_path: str = Field(..., description="Path to page image for vision context")
    surrounding_text: str = Field("", description="Surrounding text for context")
    confidence_threshold: float = Field(85.0, ge=0, le=100)


class TrackARequest(BaseModel):
    """Request for Track A SNOMED mapping."""
    textract_json_path: Optional[str] = Field(None, description="Path to Textract JSON file")
    text: Optional[str] = Field(None, description="Raw text to analyze (alternative to file path)")


class TrackBRequest(BaseModel):
    """Request for Track B summarization."""
    textract_json_path: Optional[str] = Field(None, description="Path to Textract JSON file")
    text: Optional[str] = Field(None, description="Raw text to summarize")


class PipelineRequest(BaseModel):
    """Request for full pipeline processing."""
    confidence_threshold: float = Field(90.0, ge=0, le=100, description="Tier 1 confidence threshold for routing")
    priority: str = Field("standard", pattern="^(low|standard|high)$")
