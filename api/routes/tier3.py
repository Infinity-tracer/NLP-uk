"""Tier 3 - Vision-LLM Correction API endpoints."""
import os
import time
from fastapi import APIRouter, HTTPException
from PIL import Image

from api.config import settings
from api.schemas.requests import Tier3Request
from api.schemas.responses import Tier3Response

# Import existing module with error handling
try:
    from tier3_ocr_correction.tier3_processor import process_low_confidence_regions
    TIER3_AVAILABLE = True
except ImportError as e:
    TIER3_AVAILABLE = False
    TIER3_ERROR = str(e)

router = APIRouter()


@router.post("/correct", response_model=Tier3Response)
async def correct_ocr(request: Tier3Request):
    """
    Tier 3: Vision-LLM OCR Correction

    Takes low-confidence regions from Tier 2 and uses Claude Sonnet
    via AWS Bedrock for vision-based correction.

    Features:
    - Hallucination detection (>30% deviation = review required)
    - LLM confidence gating
    - Audit logging for compliance
    """
    start_time = time.time()

    # Validate image exists
    if not TIER3_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail=f"Tier 3 dependencies not available: {TIER3_ERROR}"
        )

    if not os.path.exists(request.image_path):
        raise HTTPException(
            status_code=404,
            detail=f"Image not found: {request.image_path}"
        )

    if not request.low_confidence_regions:
        return Tier3Response(
            status="success",
            corrected_regions=[],
            audit_log=[],
            processing_time_ms=0,
        )

    try:
        # Load image
        page_image = Image.open(request.image_path)

        # Process low-confidence regions
        result = process_low_confidence_regions(
            low_confidence_regions=request.low_confidence_regions,
            page_image=page_image,
            surrounding_context_text=request.surrounding_text,
            confidence_threshold=request.confidence_threshold,
        )

        processing_time = int((time.time() - start_time) * 1000)

        return Tier3Response(
            status=result.get("status", "success"),
            corrected_regions=result.get("corrected_regions", []),
            audit_log=result.get("audit_log", []),
            processing_time_ms=processing_time,
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Tier 3 processing error: {str(e)}"
        )


@router.post("/correct-from-tier2")
async def correct_from_tier2_output(tier2_output_path: str, image_path: str):
    """
    Tier 3: Correct regions from Tier 2 escalation queue.

    Takes a Tier 2 output file and processes its escalation queue.
    """
    import json

    start_time = time.time()

    if not os.path.exists(tier2_output_path):
        raise HTTPException(
            status_code=404,
            detail=f"Tier 2 output not found: {tier2_output_path}"
        )

    if not os.path.exists(image_path):
        raise HTTPException(
            status_code=404,
            detail=f"Image not found: {image_path}"
        )

    try:
        # Load Tier 2 output
        with open(tier2_output_path, 'r') as f:
            tier2_data = json.load(f)

        escalation_queue = tier2_data.get("escalation_queue", [])

        if not escalation_queue:
            return Tier3Response(
                status="success",
                corrected_regions=[],
                audit_log=[{"message": "No regions to process in escalation queue"}],
                processing_time_ms=0,
            )

        # Convert escalation queue to low-confidence regions format
        low_confidence_regions = [
            {
                "text": item.get("text", ""),
                "bbox": item.get("bbox", [0, 0, 0, 0]),
                "confidence": item.get("confidence", 0),
                "page_number": item.get("page_number", 1),
            }
            for item in escalation_queue
        ]

        # Load image
        page_image = Image.open(image_path)

        # Get surrounding text for context
        refined_elements = tier2_data.get("refined_elements", [])
        surrounding_text = " ".join([elem.get("text", "") for elem in refined_elements[:10]])

        # Process
        result = process_low_confidence_regions(
            low_confidence_regions=low_confidence_regions,
            page_image=page_image,
            surrounding_context_text=surrounding_text,
            confidence_threshold=settings.TIER3_CONFIDENCE_THRESHOLD,
        )

        processing_time = int((time.time() - start_time) * 1000)

        return Tier3Response(
            status=result.get("status", "success"),
            corrected_regions=result.get("corrected_regions", []),
            audit_log=result.get("audit_log", []),
            processing_time_ms=processing_time,
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Tier 3 processing error: {str(e)}"
        )
