"""Tier 1 - AWS Textract Extraction API endpoints."""
import os
import time
import json
import glob
import boto3
from typing import List, Optional
from fastapi import APIRouter, HTTPException

from api.config import settings
from api.schemas.requests import Tier1Request
from api.schemas.responses import Tier1Response

router = APIRouter()


def calculate_average_confidence(textract_response: dict) -> float:
    """Calculate average confidence from Textract blocks."""
    confidences = []
    for block in textract_response.get("Blocks", []):
        if "Confidence" in block:
            confidences.append(block["Confidence"])
    return sum(confidences) / len(confidences) if confidences else 0.0


@router.post("/extract", response_model=Tier1Response)
async def extract_text(request: Tier1Request = None):
    """
    Tier 1: AWS Textract Extraction

    Sends cleaned images to AWS Textract for OCR extraction with medical queries.

    If no image_paths provided, processes all *_CLEANED.* images in temp_pages.
    """
    start_time = time.time()

    # Find images to process
    if request and request.image_paths:
        cleaned_images = request.image_paths
    else:
        cleaned_images = glob.glob(os.path.join(settings.TEMP_PAGES_DIR, "*_CLEANED.*"))

    if not cleaned_images:
        raise HTTPException(
            status_code=400,
            detail=f"No cleaned images found. Run Tier 0 preprocessing first."
        )

    # Initialize Textract client
    textract_client = boto3.client('textract', region_name=settings.AWS_REGION)

    # Medical queries for SNOMED mapping
    queries = [
        {"Text": "What are the patient's primary diagnoses?", "Alias": "DIAGNOSIS"},
        {"Text": "What medications is the patient currently taking?", "Alias": "MEDICATIONS"},
        {"Text": "What are the key clinical findings or symptoms?", "Alias": "FINDINGS"}
    ]

    output_dir = settings.TEXTRACT_OUTPUTS_DIR
    os.makedirs(output_dir, exist_ok=True)

    output_files = []
    total_confidence = 0.0

    for img_path in cleaned_images:
        if not os.path.exists(img_path):
            continue

        with open(img_path, 'rb') as document:
            image_bytes = document.read()

        try:
            response = textract_client.analyze_document(
                Document={'Bytes': image_bytes},
                FeatureTypes=["QUERIES", "TABLES", "FORMS"],
                QueriesConfig={'Queries': queries}
            )

            base_name = os.path.basename(img_path).split('.')[0]
            output_file = os.path.join(output_dir, f"{base_name}_textract.json")

            with open(output_file, 'w') as f:
                json.dump(response, f, indent=4)

            output_files.append(output_file)
            total_confidence += calculate_average_confidence(response)

        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Textract error processing {img_path}: {str(e)}"
            )

    processing_time = int((time.time() - start_time) * 1000)
    avg_confidence = total_confidence / len(output_files) if output_files else 0.0

    return Tier1Response(
        status="success",
        pages_processed=len(output_files),
        output_files=output_files,
        average_confidence=round(avg_confidence, 2),
        processing_time_ms=processing_time,
    )


@router.get("/results")
async def get_textract_results():
    """Get all Textract output files."""
    output_dir = settings.TEXTRACT_OUTPUTS_DIR
    if not os.path.exists(output_dir):
        return {"files": []}

    files = glob.glob(os.path.join(output_dir, "*_textract.json"))
    return {"files": files}


@router.get("/results/{filename}")
async def get_textract_result(filename: str):
    """Get a specific Textract result file."""
    filepath = os.path.join(settings.TEXTRACT_OUTPUTS_DIR, filename)

    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="File not found")

    with open(filepath, 'r') as f:
        return json.load(f)
