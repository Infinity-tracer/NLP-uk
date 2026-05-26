"""Full Pipeline API endpoints."""
import os
import time
import json
import uuid
import asyncio
import tempfile
import shutil
from datetime import datetime
from typing import Dict, Any, Optional
from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks

from api.config import settings
from api.schemas.requests import PipelineRequest
from api.schemas.responses import (
    PipelineJobResponse,
    PipelineStatusResponse,
    PipelineResultResponse,
    ProcessingStatus,
    TierStatus,
)

router = APIRouter()

# In-memory job storage (replace with DynamoDB in production)
_jobs: Dict[str, Dict[str, Any]] = {}


def update_job_status(
    job_id: str,
    status: ProcessingStatus,
    current_tier: str = None,
    progress: int = 0,
    error: str = None,
    tier_result: Dict[str, Any] = None,
):
    """Update job status in storage."""
    if job_id not in _jobs:
        return

    _jobs[job_id]["status"] = status
    _jobs[job_id]["updated_at"] = datetime.utcnow().isoformat()

    if current_tier:
        _jobs[job_id]["current_tier"] = current_tier
    if progress:
        _jobs[job_id]["progress"] = progress
    if error:
        _jobs[job_id]["error"] = error
    if tier_result:
        tier_name = tier_result.get("tier", "unknown")
        _jobs[job_id]["results"][tier_name] = tier_result


async def process_pipeline_async(job_id: str, file_path: str, confidence_threshold: float):
    """
    Async pipeline processing task.

    Runs through all tiers sequentially:
    Tier 0 → Tier 1 → (Tier 2 if low confidence) → (Tier 3 if escalated) → Track A + Track B
    """
    try:
        from document_handler import prepare_document
        from preprocessing import preprocess_batch
    except ImportError as e:
        update_job_status(job_id, ProcessingStatus.FAILED, error=f"Missing dependencies: {e}")
        return

    try:
        # === TIER 0: Preprocessing ===
        update_job_status(job_id, ProcessingStatus.PROCESSING, "tier0", 10)

        start_tier0 = time.time()
        image_paths, failed_pages = prepare_document(file_path, settings.TEMP_PAGES_DIR)

        if not image_paths:
            update_job_status(job_id, ProcessingStatus.FAILED, error="No pages extracted")
            return

        success, failed = preprocess_batch(image_paths)
        preprocessed_images = [item["cleaned"] for item in success]

        tier0_result = {
            "tier": "tier0",
            "status": "success",
            "total_pages": len(image_paths),
            "preprocessed_images": preprocessed_images,
            "duration_ms": int((time.time() - start_tier0) * 1000),
        }
        update_job_status(job_id, ProcessingStatus.PROCESSING, "tier0", 20, tier_result=tier0_result)

        # === TIER 1: Textract ===
        update_job_status(job_id, ProcessingStatus.PROCESSING, "tier1", 30)

        import boto3
        import glob

        start_tier1 = time.time()
        textract_client = boto3.client('textract', region_name=settings.AWS_REGION)

        queries = [
            {"Text": "What are the patient's primary diagnoses?", "Alias": "DIAGNOSIS"},
            {"Text": "What medications is the patient currently taking?", "Alias": "MEDICATIONS"},
            {"Text": "What are the key clinical findings or symptoms?", "Alias": "FINDINGS"}
        ]

        os.makedirs(settings.TEXTRACT_OUTPUTS_DIR, exist_ok=True)
        textract_files = []
        total_confidence = 0.0

        for img_path in preprocessed_images:
            with open(img_path, 'rb') as f:
                image_bytes = f.read()

            response = textract_client.analyze_document(
                Document={'Bytes': image_bytes},
                FeatureTypes=["QUERIES", "TABLES", "FORMS"],
                QueriesConfig={'Queries': queries}
            )

            base_name = os.path.basename(img_path).split('.')[0]
            output_file = os.path.join(settings.TEXTRACT_OUTPUTS_DIR, f"{base_name}_textract.json")

            with open(output_file, 'w') as f:
                json.dump(response, f, indent=4)

            textract_files.append(output_file)

            # Calculate confidence
            confidences = [b["Confidence"] for b in response.get("Blocks", []) if "Confidence" in b]
            if confidences:
                total_confidence += sum(confidences) / len(confidences)

        avg_confidence = total_confidence / len(textract_files) if textract_files else 0

        tier1_result = {
            "tier": "tier1",
            "status": "success",
            "pages_processed": len(textract_files),
            "output_files": textract_files,
            "average_confidence": round(avg_confidence, 2),
            "duration_ms": int((time.time() - start_tier1) * 1000),
        }
        update_job_status(job_id, ProcessingStatus.PROCESSING, "tier1", 50, tier_result=tier1_result)

        # === TIER 2: LayoutLMv3 (if confidence < threshold) ===
        tier2_result = None
        escalation_queue = []

        if avg_confidence < confidence_threshold:
            update_job_status(job_id, ProcessingStatus.PROCESSING, "tier2", 60)

            from tier2_layoutlmv3_refinement import LayoutLMv3Refiner

            start_tier2 = time.time()
            refiner = LayoutLMv3Refiner()
            os.makedirs(settings.TIER2_OUTPUTS_DIR, exist_ok=True)

            for i, textract_file in enumerate(textract_files):
                with open(textract_file, 'r') as f:
                    textract_data = json.load(f)

                # Find corresponding image
                img_path = preprocessed_images[i] if i < len(preprocessed_images) else None
                if img_path:
                    from PIL import Image
                    page_image = Image.open(img_path)

                    # Extract document_id from filename
                    base_name = os.path.basename(textract_file)
                    document_id = base_name.replace('_textract.json', '').replace('_CLEANED', '')
                    page_number = i + 1

                    result = refiner.refine_document(
                        textract_output=textract_data,
                        page_image=page_image,
                        document_id=document_id,
                        page_number=page_number,
                    )
                    escalation_queue.extend(result.escalation_queue)

            tier2_result = {
                "tier": "tier2",
                "status": "success",
                "escalation_count": len(escalation_queue),
                "duration_ms": int((time.time() - start_tier2) * 1000),
            }
            update_job_status(job_id, ProcessingStatus.PROCESSING, "tier2", 70, tier_result=tier2_result)

        # === TIER 3: Vision-LLM (if escalations exist) ===
        tier3_result = None

        if escalation_queue:
            update_job_status(job_id, ProcessingStatus.PROCESSING, "tier3", 75)
            start_tier3 = time.time()

            try:
                from PIL import Image
                from tier3_ocr_correction.tier3_processor import process_low_confidence_regions
                import logging
                logging.basicConfig(level=logging.INFO)
                logger = logging.getLogger(__name__)

                # Process first image for now (simplified)
                if preprocessed_images:
                    page_image = Image.open(preprocessed_images[0])
                    logger.info(f"Tier 3: Processing image {preprocessed_images[0]}, size={page_image.size}")

                    low_conf_regions = [
                        {
                            "text": elem.text,
                            "bbox": elem.bbox,
                            "confidence": elem.confidence,
                            "page_number": elem.page_number,
                        }
                        for elem in escalation_queue[:10]  # Limit for demo
                    ]
                    logger.info(f"Tier 3: Processing {len(low_conf_regions)} low-confidence regions")

                    result = process_low_confidence_regions(
                        low_confidence_regions=low_conf_regions,
                        page_image=page_image,
                        surrounding_context_text="",
                        confidence_threshold=settings.TIER3_CONFIDENCE_THRESHOLD,
                    )

                    tier3_result = {
                        "tier": "tier3",
                        "status": "success" if result.get("status") == "SUCCESS" else "review_required",
                        "corrections_applied": len([r for r in result.get("corrected_regions", []) if r.get("correction_applied")]),
                        "regions_processed": len(result.get("corrected_regions", [])),
                        "audit_entries": len(result.get("audit_log", [])),
                        "duration_ms": int((time.time() - start_tier3) * 1000),
                    }
                    logger.info(f"Tier 3: Completed - {tier3_result}")
                else:
                    tier3_result = {
                        "tier": "tier3",
                        "status": "skipped",
                        "error": "No preprocessed images available",
                        "duration_ms": int((time.time() - start_tier3) * 1000),
                    }
            except Exception as e:
                import traceback
                error_details = traceback.format_exc()
                print(f"Tier 3 Error: {error_details}")
                tier3_result = {
                    "tier": "tier3",
                    "status": "failed",
                    "error": str(e),
                    "error_details": error_details,
                    "duration_ms": int((time.time() - start_tier3) * 1000),
                }

            update_job_status(job_id, ProcessingStatus.PROCESSING, "tier3", 80, tier_result=tier3_result)

        # === TRACK A: SNOMED Mapping ===
        update_job_status(job_id, ProcessingStatus.PROCESSING, "track_a", 85)
        start_track_a = time.time()

        all_entities = []
        all_snomed = []

        try:
            comprehend_medical = boto3.client('comprehendmedical', region_name=settings.AWS_REGION)
            seen_snomed_codes = set()  # Deduplicate SNOMED codes

            for textract_file in textract_files:
                with open(textract_file, 'r') as f:
                    textract_data = json.load(f)

                text_lines = [b["Text"] for b in textract_data.get("Blocks", []) if b.get("BlockType") == "LINE"]
                full_text = " ".join(text_lines)[:9500]

                if full_text.strip():
                    response = comprehend_medical.infer_snomedct(Text=full_text)

                    for entity in response.get('Entities', []):
                        entity_score = entity.get('Score', 0)
                        # Only include entities with reasonable confidence
                        if entity_score >= 0.5:
                            all_entities.append({
                                "text": entity.get('Text', '').strip(),
                                "category": entity.get('Category', ''),
                                "type": entity.get('Type', ''),
                                "score": entity_score,
                            })

                        for snomed in entity.get('SNOMEDCTConcepts', []):
                            snomed_code = snomed.get('Code', '')
                            snomed_score = snomed.get('Score', 0)
                            # Only include SNOMED codes with score >= 0.3 and deduplicate
                            if snomed_score >= 0.3 and snomed_code not in seen_snomed_codes:
                                seen_snomed_codes.add(snomed_code)
                                all_snomed.append({
                                    "code": snomed_code,
                                    "description": snomed.get('Description', ''),
                                    "score": snomed_score,
                                    "source_text": entity.get('Text', '').strip(),
                                })

            track_a_result = {
                "tier": "track_a",
                "status": "success",
                "entities_found": len(all_entities),
                "snomed_codes": len(all_snomed),
                "duration_ms": int((time.time() - start_track_a) * 1000),
                "entities": all_entities,
                "snomed": all_snomed,
            }
        except Exception as e:
            track_a_result = {
                "tier": "track_a",
                "status": "failed",
                "error": str(e),
                "duration_ms": int((time.time() - start_track_a) * 1000),
                "entities": all_entities,
                "snomed": all_snomed,
            }

        update_job_status(job_id, ProcessingStatus.PROCESSING, "track_a", 95, tier_result=track_a_result)

        # === TRACK B: Summarization ===
        update_job_status(job_id, ProcessingStatus.PROCESSING, "track_b", 98)

        bedrock = boto3.client('bedrock-runtime', region_name=settings.AWS_REGION)
        start_track_b = time.time()

        # Combine all text for summary
        all_text = []
        for textract_file in textract_files:
            with open(textract_file, 'r') as f:
                textract_data = json.load(f)
            text_lines = [b["Text"] for b in textract_data.get("Blocks", []) if b.get("BlockType") == "LINE"]
            all_text.extend(text_lines)

        combined_text = " ".join(all_text)[:8000]

        prompt = f"""Summarize this clinical document in 2-3 paragraphs. Include key findings and diagnoses.

{combined_text}

Provide a JSON response with: summary, key_findings (array), action_plans (object with clinician, patient, pharmacist arrays)."""

        try:
            response = bedrock.invoke_model(
                modelId="us.anthropic.claude-sonnet-4-20250514-v1:0",
                contentType="application/json",
                accept="application/json",
                body=json.dumps({
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 1500,
                    "messages": [{"role": "user", "content": prompt}]
                })
            )

            response_body = json.loads(response['body'].read())
            summary_text = response_body['content'][0]['text']

            # Parse JSON from response (handle markdown code blocks)
            parsed_summary = {}
            try:
                text_to_parse = summary_text
                if "```json" in text_to_parse:
                    json_start = text_to_parse.find("```json") + 7
                    json_end = text_to_parse.find("```", json_start)
                    text_to_parse = text_to_parse[json_start:json_end]
                elif "```" in text_to_parse:
                    json_start = text_to_parse.find("```") + 3
                    json_end = text_to_parse.find("```", json_start)
                    text_to_parse = text_to_parse[json_start:json_end]
                parsed_summary = json.loads(text_to_parse.strip())
            except json.JSONDecodeError:
                parsed_summary = {"summary": summary_text, "key_findings": [], "action_plans": {}}

            track_b_result = {
                "tier": "track_b",
                "status": "success",
                "summary": parsed_summary.get("summary", summary_text),
                "key_findings": parsed_summary.get("key_findings", []),
                "action_plans": parsed_summary.get("action_plans", {}),
                "duration_ms": int((time.time() - start_track_b) * 1000),
            }
        except Exception as e:
            track_b_result = {
                "tier": "track_b",
                "status": "failed",
                "error": str(e),
                "duration_ms": int((time.time() - start_track_b) * 1000),
            }

        update_job_status(job_id, ProcessingStatus.PROCESSING, "track_b", 100, tier_result=track_b_result)

        # === COMPLETE ===
        update_job_status(job_id, ProcessingStatus.COMPLETED, progress=100)

    except Exception as e:
        update_job_status(job_id, ProcessingStatus.FAILED, error=str(e))


@router.post("/process-document", response_model=PipelineJobResponse)
async def process_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="PDF or image file to process"),
    confidence_threshold: float = 90.0,
):
    """
    Full Pipeline: Process a clinical document through all tiers.

    Returns a job_id immediately. Poll /status/{job_id} for progress.

    Pipeline: Tier 0 → Tier 1 → Tier 2 (if needed) → Tier 3 (if needed) → Track A + Track B
    """
    # Validate file type
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in {".pdf", ".jpg", ".jpeg", ".png", ".tiff", ".tif"}:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Allowed: PDF, JPEG, PNG, TIFF"
        )

    # Create job
    job_id = str(uuid.uuid4())

    # Save file temporarily
    temp_dir = os.path.join(tempfile.gettempdir(), f"nlpuk_{job_id}")
    os.makedirs(temp_dir, exist_ok=True)
    file_path = os.path.join(temp_dir, file.filename or "upload")

    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    # Initialize job record
    _jobs[job_id] = {
        "job_id": job_id,
        "status": ProcessingStatus.QUEUED,
        "document_name": file.filename,
        "confidence_threshold": confidence_threshold,
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
        "current_tier": None,
        "progress": 0,
        "error": None,
        "results": {},
        "temp_dir": temp_dir,
        "file_path": file_path,
    }

    # Start async processing
    background_tasks.add_task(process_pipeline_async, job_id, file_path, confidence_threshold)

    return PipelineJobResponse(
        job_id=job_id,
        status=ProcessingStatus.QUEUED,
        message="Document queued for processing. Poll /status/{job_id} for updates.",
    )


@router.get("/status/{job_id}", response_model=PipelineStatusResponse)
async def get_job_status(job_id: str):
    """Get the current status of a pipeline job."""
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = _jobs[job_id]

    # Build tier statuses
    tiers = []
    for tier_name in ["tier0", "tier1", "tier2", "tier3", "track_a", "track_b"]:
        if tier_name in job.get("results", {}):
            result = job["results"][tier_name]
            tiers.append(TierStatus(
                tier=tier_name,
                status=ProcessingStatus.COMPLETED if result.get("status") == "success" else ProcessingStatus.FAILED,
                duration_ms=result.get("duration_ms"),
                confidence=result.get("average_confidence"),
                error=result.get("error"),
            ))

    return PipelineStatusResponse(
        job_id=job_id,
        status=job["status"],
        current_tier=job.get("current_tier"),
        progress_percent=job.get("progress", 0),
        tiers=tiers,
        error=job.get("error"),
    )


@router.get("/result/{job_id}")
async def get_job_result(job_id: str):
    """Get the full result of a completed pipeline job."""
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = _jobs[job_id]

    if job["status"] not in [ProcessingStatus.COMPLETED, ProcessingStatus.FAILED]:
        raise HTTPException(
            status_code=400,
            detail=f"Job not complete. Current status: {job['status']}"
        )

    # Calculate total processing time
    results = job.get("results", {})
    total_time = sum(r.get("duration_ms", 0) for r in results.values())

    # Transform track_a result to expected format
    track_a_raw = results.get("track_a", {})
    track_a = {
        "status": track_a_raw.get("status", "unknown"),
        "entities": track_a_raw.get("entities", []),
        "snomed_codes": track_a_raw.get("snomed", []),
        "processing_time_ms": track_a_raw.get("duration_ms", 0),
    } if track_a_raw else None

    # Transform track_b result to expected format
    track_b_raw = results.get("track_b", {})
    track_b = {
        "status": track_b_raw.get("status", "unknown"),
        "summary": track_b_raw.get("summary", ""),
        "key_findings": track_b_raw.get("key_findings", []),
        "action_plans": track_b_raw.get("action_plans", {}),
        "processing_time_ms": track_b_raw.get("duration_ms", 0),
        "error": track_b_raw.get("error"),
    } if track_b_raw else None

    return {
        "job_id": job_id,
        "status": job["status"],
        "document_name": job.get("document_name", "unknown"),
        "total_processing_time_ms": total_time,
        "tier0": results.get("tier0"),
        "tier1": results.get("tier1"),
        "tier2": results.get("tier2"),
        "tier3": results.get("tier3"),
        "track_a": track_a,
        "track_b": track_b,
        "audit_trail": [],
    }


@router.get("/jobs")
async def list_jobs():
    """List all jobs."""
    return {
        "jobs": [
            {
                "job_id": j["job_id"],
                "status": j["status"],
                "document_name": j.get("document_name"),
                "created_at": j.get("created_at"),
                "progress": j.get("progress", 0),
            }
            for j in _jobs.values()
        ]
    }


@router.delete("/jobs/{job_id}")
async def delete_job(job_id: str):
    """Delete a job and its temporary files."""
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = _jobs[job_id]

    # Cleanup temp directory
    temp_dir = job.get("temp_dir")
    if temp_dir and os.path.exists(temp_dir):
        shutil.rmtree(temp_dir, ignore_errors=True)

    del _jobs[job_id]

    return {"message": "Job deleted"}
