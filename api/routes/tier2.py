"""Tier 2 - LayoutLMv3 Refinement API endpoints."""
import os
import time
import json
import uuid
from fastapi import APIRouter, HTTPException
from PIL import Image

from api.config import settings
from api.schemas.requests import Tier2Request
from api.schemas.responses import Tier2Response

# Import existing module with error handling
try:
    from tier2_layoutlmv3_refinement import LayoutLMv3Refiner, refine_textract_batch
    TIER2_AVAILABLE = True
except ImportError as e:
    TIER2_AVAILABLE = False
    TIER2_ERROR = str(e)
    LayoutLMv3Refiner = None

router = APIRouter()

# Lazy-loaded refiner instance
_refiner = None


def get_refiner():
    """Get or create the LayoutLMv3 refiner instance."""
    global _refiner
    if _refiner is None:
        _refiner = LayoutLMv3Refiner()
    return _refiner


@router.post("/refine", response_model=Tier2Response)
async def refine_document(request: Tier2Request):
    """
    Tier 2: LayoutLMv3 Structure Refinement

    Takes Textract output and corresponding image, applies multimodal
    LayoutLMv3 processing to refine structure understanding.

    Triggered when Textract confidence < 90%.
    """
    if not TIER2_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail=f"Tier 2 dependencies not available: {TIER2_ERROR}"
        )

    start_time = time.time()

    # Validate input files exist
    if not os.path.exists(request.textract_json_path):
        raise HTTPException(
            status_code=404,
            detail=f"Textract JSON not found: {request.textract_json_path}"
        )

    if not os.path.exists(request.image_path):
        raise HTTPException(
            status_code=404,
            detail=f"Image not found: {request.image_path}"
        )

    try:
        # Load Textract data
        with open(request.textract_json_path, 'r') as f:
            textract_data = json.load(f)

        # Load image as PIL Image
        page_image = Image.open(request.image_path)

        # Generate document_id from filename and extract page number
        base_name = os.path.basename(request.textract_json_path)
        document_id = base_name.replace('_textract.json', '').replace('_CLEANED', '')

        # Try to extract page number from filename (e.g., "doc_page1_CLEANED")
        page_number = 1
        if 'page' in document_id.lower():
            try:
                import re
                match = re.search(r'page(\d+)', document_id, re.IGNORECASE)
                if match:
                    page_number = int(match.group(1))
            except:
                pass

        # Get refiner and process
        refiner = get_refiner()
        result = refiner.refine_document(
            textract_output=textract_data,
            page_image=page_image,
            document_id=document_id,
            page_number=page_number,
        )

        processing_time = int((time.time() - start_time) * 1000)

        # Convert result to response format
        refined_elements = [
            {
                "text": elem.text,
                "element_type": elem.element_type,
                "confidence": elem.confidence,
                "bbox": elem.bbox,
                "page_number": elem.page_number,
            }
            for elem in result.refined_elements
        ]

        escalation_queue = [
            {
                "text": elem.text,
                "element_type": elem.element_type,
                "confidence": elem.confidence,
                "bbox": elem.bbox,
                "reason": "Low confidence - requires Tier 3 review",
            }
            for elem in result.escalation_queue
        ]

        return Tier2Response(
            status="success",
            refined_elements=refined_elements,
            escalation_queue=escalation_queue,
            quality_score=result.quality_score,
            processing_time_ms=processing_time,
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Tier 2 processing error: {str(e)}"
        )


@router.post("/refine-batch")
async def refine_batch(textract_dir: str = None, image_dir: str = None):
    """
    Tier 2: Batch LayoutLMv3 Refinement

    Process all Textract outputs in a directory.
    """
    if not TIER2_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail=f"Tier 2 dependencies not available: {TIER2_ERROR}"
        )

    start_time = time.time()

    textract_dir = textract_dir or settings.TEXTRACT_OUTPUTS_DIR
    image_dir = image_dir or settings.TEMP_PAGES_DIR
    output_dir = settings.TIER2_OUTPUTS_DIR

    os.makedirs(output_dir, exist_ok=True)

    try:
        results = refine_textract_batch(
            textract_dir=textract_dir,
            image_dir=image_dir,
            output_dir=output_dir,
        )

        processing_time = int((time.time() - start_time) * 1000)

        return {
            "status": "success",
            "documents_processed": len(results),
            "output_dir": output_dir,
            "processing_time_ms": processing_time,
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Batch refinement error: {str(e)}"
        )
