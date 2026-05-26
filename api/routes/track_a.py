"""Track A - SNOMED CT Mapping API endpoints."""
import os
import time
import json
import boto3
from fastapi import APIRouter, HTTPException, UploadFile, File
from typing import Optional

from api.config import settings
from api.schemas.requests import TrackARequest
from api.schemas.responses import TrackAResponse

router = APIRouter()


def extract_text_from_textract(textract_data: dict) -> str:
    """Extract raw text from Textract JSON response."""
    text_lines = []
    for block in textract_data.get('Blocks', []):
        if block.get('BlockType') == 'LINE':
            text_lines.append(block.get('Text', ''))
    return " ".join(text_lines)


@router.post("/snomed-map", response_model=TrackAResponse)
async def map_to_snomed(request: TrackARequest):
    """
    Track A: Medical Entity & SNOMED CT Mapping

    Uses AWS Comprehend Medical to extract medical entities and map them
    to SNOMED CT codes.

    Accepts either:
    - textract_json_path: Path to Textract output file
    - text: Raw text to analyze
    """
    start_time = time.time()

    # Get text to analyze
    text_to_analyze = None

    if request.text:
        text_to_analyze = request.text
    elif request.textract_json_path:
        if not os.path.exists(request.textract_json_path):
            raise HTTPException(
                status_code=404,
                detail=f"Textract file not found: {request.textract_json_path}"
            )
        with open(request.textract_json_path, 'r') as f:
            textract_data = json.load(f)
        text_to_analyze = extract_text_from_textract(textract_data)
    else:
        raise HTTPException(
            status_code=400,
            detail="Either 'text' or 'textract_json_path' must be provided"
        )

    if not text_to_analyze or not text_to_analyze.strip():
        raise HTTPException(
            status_code=400,
            detail="No text to analyze"
        )

    # Truncate to AWS limit
    text_to_analyze = text_to_analyze[:9500]

    try:
        comprehend_medical = boto3.client(
            'comprehendmedical',
            region_name=settings.AWS_REGION
        )

        # Call SNOMED CT inference
        response = comprehend_medical.infer_snomedct(Text=text_to_analyze)

        # Extract entities and SNOMED codes
        entities = []
        snomed_codes = []

        for entity in response.get('Entities', []):
            entity_data = {
                "text": entity.get('Text', ''),
                "category": entity.get('Category', ''),
                "type": entity.get('Type', ''),
                "score": entity.get('Score', 0),
                "begin_offset": entity.get('BeginOffset', 0),
                "end_offset": entity.get('EndOffset', 0),
            }
            entities.append(entity_data)

            # Extract SNOMED codes from this entity
            for snomed_concept in entity.get('SNOMEDCTConcepts', []):
                snomed_codes.append({
                    "code": snomed_concept.get('Code', ''),
                    "description": snomed_concept.get('Description', ''),
                    "score": snomed_concept.get('Score', 0),
                    "source_text": entity.get('Text', ''),
                })

        processing_time = int((time.time() - start_time) * 1000)

        return TrackAResponse(
            status="success",
            entities=entities,
            snomed_codes=snomed_codes,
            processing_time_ms=processing_time,
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"SNOMED mapping error: {str(e)}"
        )


@router.post("/snomed-map-file", response_model=TrackAResponse)
async def map_file_to_snomed(file: UploadFile = File(...)):
    """
    Track A: Map uploaded Textract JSON file to SNOMED codes.
    """
    start_time = time.time()

    try:
        content = await file.read()
        textract_data = json.loads(content.decode('utf-8'))

        text_to_analyze = extract_text_from_textract(textract_data)

        if not text_to_analyze or not text_to_analyze.strip():
            raise HTTPException(
                status_code=400,
                detail="No text found in Textract file"
            )

        # Truncate to AWS limit
        text_to_analyze = text_to_analyze[:9500]

        comprehend_medical = boto3.client(
            'comprehendmedical',
            region_name=settings.AWS_REGION
        )

        response = comprehend_medical.infer_snomedct(Text=text_to_analyze)

        entities = []
        snomed_codes = []

        for entity in response.get('Entities', []):
            entities.append({
                "text": entity.get('Text', ''),
                "category": entity.get('Category', ''),
                "type": entity.get('Type', ''),
                "score": entity.get('Score', 0),
            })

            for snomed_concept in entity.get('SNOMEDCTConcepts', []):
                snomed_codes.append({
                    "code": snomed_concept.get('Code', ''),
                    "description": snomed_concept.get('Description', ''),
                    "score": snomed_concept.get('Score', 0),
                    "source_text": entity.get('Text', ''),
                })

        processing_time = int((time.time() - start_time) * 1000)

        return TrackAResponse(
            status="success",
            entities=entities,
            snomed_codes=snomed_codes,
            processing_time_ms=processing_time,
        )

    except json.JSONDecodeError:
        raise HTTPException(
            status_code=400,
            detail="Invalid JSON file"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"SNOMED mapping error: {str(e)}"
        )
