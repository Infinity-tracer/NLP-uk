"""Admin API endpoints."""
import os
import json
import glob
from datetime import datetime
from fastapi import APIRouter, HTTPException

from api.config import settings

router = APIRouter()


@router.get("/jobs")
async def list_all_jobs():
    """List all pipeline jobs (delegates to pipeline router)."""
    from api.routes.pipeline import _jobs

    return {
        "total": len(_jobs),
        "jobs": [
            {
                "job_id": j["job_id"],
                "status": str(j["status"]),
                "document_name": j.get("document_name"),
                "created_at": j.get("created_at"),
                "updated_at": j.get("updated_at"),
                "current_tier": j.get("current_tier"),
                "progress": j.get("progress", 0),
                "error": j.get("error"),
            }
            for j in _jobs.values()
        ]
    }


@router.get("/outputs")
async def list_all_outputs():
    """List all output files from all tiers."""
    outputs = {
        "tier0": [],
        "tier1": [],
        "tier2": [],
        "track_a": [],
        "track_b": [],
    }

    # Tier 0 outputs (preprocessed images)
    if os.path.exists(settings.TEMP_PAGES_DIR):
        outputs["tier0"] = glob.glob(os.path.join(settings.TEMP_PAGES_DIR, "*_CLEANED.*"))

    # Tier 1 outputs (Textract JSON)
    if os.path.exists(settings.TEXTRACT_OUTPUTS_DIR):
        outputs["tier1"] = glob.glob(os.path.join(settings.TEXTRACT_OUTPUTS_DIR, "*_textract.json"))

    # Tier 2 outputs
    if os.path.exists(settings.TIER2_OUTPUTS_DIR):
        outputs["tier2"] = glob.glob(os.path.join(settings.TIER2_OUTPUTS_DIR, "*.json"))

    # Track A outputs
    if os.path.exists(settings.TRACK_A_OUTPUTS_DIR):
        outputs["track_a"] = glob.glob(os.path.join(settings.TRACK_A_OUTPUTS_DIR, "*_snomed.json"))

    # Track B outputs
    if os.path.exists(settings.TRACK_B_OUTPUTS_DIR):
        outputs["track_b"] = glob.glob(os.path.join(settings.TRACK_B_OUTPUTS_DIR, "*.txt"))

    return outputs


@router.get("/output/{tier}/{filename}")
async def get_output_file(tier: str, filename: str):
    """Get contents of a specific output file."""
    tier_dirs = {
        "tier0": settings.TEMP_PAGES_DIR,
        "tier1": settings.TEXTRACT_OUTPUTS_DIR,
        "tier2": settings.TIER2_OUTPUTS_DIR,
        "track_a": settings.TRACK_A_OUTPUTS_DIR,
        "track_b": settings.TRACK_B_OUTPUTS_DIR,
    }

    if tier not in tier_dirs:
        raise HTTPException(status_code=400, detail=f"Invalid tier: {tier}")

    filepath = os.path.join(tier_dirs[tier], filename)

    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="File not found")

    # Return JSON for JSON files, base64 for images
    if filepath.endswith('.json'):
        with open(filepath, 'r') as f:
            return json.load(f)
    elif filepath.endswith('.txt'):
        with open(filepath, 'r') as f:
            return {"content": f.read()}
    else:
        # For images, return file info
        return {
            "path": filepath,
            "size_bytes": os.path.getsize(filepath),
            "message": "Use /api/v1/admin/download/{tier}/{filename} for binary files"
        }


@router.delete("/outputs/{tier}")
async def clear_tier_outputs(tier: str):
    """Clear all outputs for a specific tier."""
    import shutil

    tier_dirs = {
        "tier0": settings.TEMP_PAGES_DIR,
        "tier1": settings.TEXTRACT_OUTPUTS_DIR,
        "tier2": settings.TIER2_OUTPUTS_DIR,
        "track_a": settings.TRACK_A_OUTPUTS_DIR,
        "track_b": settings.TRACK_B_OUTPUTS_DIR,
    }

    if tier not in tier_dirs:
        raise HTTPException(status_code=400, detail=f"Invalid tier: {tier}")

    dir_path = tier_dirs[tier]
    if os.path.exists(dir_path):
        shutil.rmtree(dir_path)
        os.makedirs(dir_path)

    return {"message": f"Cleared {tier} outputs"}


@router.delete("/outputs")
async def clear_all_outputs():
    """Clear all output directories."""
    import shutil

    dirs = [
        settings.TEMP_PAGES_DIR,
        settings.TEXTRACT_OUTPUTS_DIR,
        settings.TIER2_OUTPUTS_DIR,
        settings.TRACK_A_OUTPUTS_DIR,
        settings.TRACK_B_OUTPUTS_DIR,
    ]

    for dir_path in dirs:
        if os.path.exists(dir_path):
            shutil.rmtree(dir_path)
            os.makedirs(dir_path)

    return {"message": "All outputs cleared"}


@router.get("/stats")
async def get_stats():
    """Get processing statistics."""
    from api.routes.pipeline import _jobs

    total_jobs = len(_jobs)
    completed = sum(1 for j in _jobs.values() if str(j["status"]) == "completed")
    failed = sum(1 for j in _jobs.values() if str(j["status"]) == "failed")
    processing = sum(1 for j in _jobs.values() if str(j["status"]) == "processing")

    # Count output files
    outputs = {
        "tier0": len(glob.glob(os.path.join(settings.TEMP_PAGES_DIR, "*_CLEANED.*"))) if os.path.exists(settings.TEMP_PAGES_DIR) else 0,
        "tier1": len(glob.glob(os.path.join(settings.TEXTRACT_OUTPUTS_DIR, "*_textract.json"))) if os.path.exists(settings.TEXTRACT_OUTPUTS_DIR) else 0,
        "tier2": len(glob.glob(os.path.join(settings.TIER2_OUTPUTS_DIR, "*.json"))) if os.path.exists(settings.TIER2_OUTPUTS_DIR) else 0,
        "track_a": len(glob.glob(os.path.join(settings.TRACK_A_OUTPUTS_DIR, "*_snomed.json"))) if os.path.exists(settings.TRACK_A_OUTPUTS_DIR) else 0,
    }

    return {
        "jobs": {
            "total": total_jobs,
            "completed": completed,
            "failed": failed,
            "processing": processing,
        },
        "outputs": outputs,
        "timestamp": datetime.utcnow().isoformat(),
    }
