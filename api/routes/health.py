"""Health check endpoint."""
from datetime import datetime
from fastapi import APIRouter

from api.config import settings
from api.schemas.responses import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Check API health and dependency status."""
    dependencies = {}

    # Check AWS connectivity (basic check)
    try:
        import boto3
        boto3.client('sts', region_name=settings.AWS_REGION).get_caller_identity()
        dependencies["aws"] = "healthy"
    except Exception as e:
        dependencies["aws"] = f"unhealthy: {str(e)[:50]}"

    return HealthResponse(
        status="healthy",
        version=settings.API_VERSION,
        timestamp=datetime.utcnow().isoformat(),
        dependencies=dependencies,
    )
