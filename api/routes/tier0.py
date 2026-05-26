"""Tier 0 - Image Preprocessing API endpoints."""
import os
import time
import shutil
import tempfile
from typing import List
from fastapi import APIRouter, UploadFile, File, HTTPException

from api.config import settings
from api.schemas.responses import Tier0Response

# Import existing modules with error handling
try:
    from document_handler import prepare_document
    from preprocessing import preprocess_batch
    TIER0_AVAILABLE = True
except ImportError as e:
    TIER0_AVAILABLE = False
    TIER0_ERROR = str(e)

router = APIRouter()


@router.post("/preprocess", response_model=Tier0Response)
async def preprocess_document(
    file: UploadFile = File(..., description="PDF or image file to preprocess")
):
    """
    Tier 0: Image Preprocessing

    Accepts a PDF or image file and runs:
    1. Document preparation (PDF page extraction)
    2. Image preprocessing (adaptive thresholding, morphological ops, deskewing)

    Returns list of preprocessed image paths.
    """
    if not TIER0_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail=f"Tier 0 dependencies not available: {TIER0_ERROR}. Install project requirements."
        )

    start_time = time.time()

    # Validate file type
    content_type = file.content_type or ""
    if content_type not in settings.ALLOWED_FILE_TYPES:
        # Also check by extension
        ext = os.path.splitext(file.filename or "")[1].lower()
        if ext not in {".pdf", ".jpg", ".jpeg", ".png", ".tiff", ".tif"}:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {content_type}. Allowed: PDF, JPEG, PNG, TIFF"
            )

    # Save uploaded file temporarily
    temp_dir = tempfile.mkdtemp()
    temp_path = os.path.join(temp_dir, file.filename or "upload")

    try:
        with open(temp_path, "wb") as f:
            content = await file.read()
            f.write(content)

        # Ensure output directory exists
        output_dir = settings.TEMP_PAGES_DIR
        os.makedirs(output_dir, exist_ok=True)

        # Step 1: Document preparation
        image_paths, failed_pages = prepare_document(temp_path, output_dir)

        if not image_paths:
            raise HTTPException(
                status_code=400,
                detail="No pages could be extracted from the document"
            )

        # Step 2: Preprocessing
        success, failed = preprocess_batch(image_paths)

        preprocessed_images = [item["cleaned"] for item in success]
        all_failed = failed_pages + [
            {"page": i + 1, "error": f["error"]}
            for i, f in enumerate(failed)
        ]

        processing_time = int((time.time() - start_time) * 1000)

        return Tier0Response(
            status="success",
            total_pages=len(image_paths),
            preprocessed_images=preprocessed_images,
            failed_pages=all_failed,
            processing_time_ms=processing_time,
        )

    finally:
        # Cleanup temp file
        shutil.rmtree(temp_dir, ignore_errors=True)


@router.post("/preprocess-batch", response_model=Tier0Response)
async def preprocess_batch_documents(
    files: List[UploadFile] = File(..., description="Multiple PDF or image files")
):
    """
    Tier 0: Batch Image Preprocessing

    Accepts multiple files and preprocesses them all.
    """
    if not TIER0_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail=f"Tier 0 dependencies not available: {TIER0_ERROR}"
        )

    start_time = time.time()
    all_preprocessed = []
    all_failed = []
    total_pages = 0

    temp_dir = tempfile.mkdtemp()

    try:
        for file in files:
            temp_path = os.path.join(temp_dir, file.filename or f"upload_{len(all_preprocessed)}")

            with open(temp_path, "wb") as f:
                content = await file.read()
                f.write(content)

            output_dir = settings.TEMP_PAGES_DIR
            os.makedirs(output_dir, exist_ok=True)

            image_paths, failed_pages = prepare_document(temp_path, output_dir)
            total_pages += len(image_paths)

            if image_paths:
                success, failed = preprocess_batch(image_paths)
                all_preprocessed.extend([item["cleaned"] for item in success])
                all_failed.extend(failed_pages)
                all_failed.extend([
                    {"page": f"batch_{file.filename}", "error": f["error"]}
                    for f in failed
                ])
            else:
                all_failed.extend(failed_pages)

        processing_time = int((time.time() - start_time) * 1000)

        return Tier0Response(
            status="success" if all_preprocessed else "failed",
            total_pages=total_pages,
            preprocessed_images=all_preprocessed,
            failed_pages=all_failed,
            processing_time_ms=processing_time,
        )

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
