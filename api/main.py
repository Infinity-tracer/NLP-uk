"""FastAPI application entry point for NLP-uk Clinical Pipeline."""
import sys
from pathlib import Path

# Add parent directory to path for importing existing modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.config import settings
from api.routes import health, tier0, tier1, tier2, tier3, track_a, track_b, pipeline, admin

app = FastAPI(
    title=settings.API_TITLE,
    version=settings.API_VERSION,
    description="REST API for the NLP-uk Clinical Document Processing Pipeline",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router, prefix=settings.API_PREFIX, tags=["Health"])
app.include_router(tier0.router, prefix=f"{settings.API_PREFIX}/tier0", tags=["Tier 0 - Preprocessing"])
app.include_router(tier1.router, prefix=f"{settings.API_PREFIX}/tier1", tags=["Tier 1 - Textract"])
app.include_router(tier2.router, prefix=f"{settings.API_PREFIX}/tier2", tags=["Tier 2 - LayoutLMv3"])
app.include_router(tier3.router, prefix=f"{settings.API_PREFIX}/tier3", tags=["Tier 3 - Vision-LLM"])
app.include_router(track_a.router, prefix=f"{settings.API_PREFIX}/track-a", tags=["Track A - SNOMED"])
app.include_router(track_b.router, prefix=f"{settings.API_PREFIX}/track-b", tags=["Track B - Summarization"])
app.include_router(pipeline.router, prefix=f"{settings.API_PREFIX}/pipeline", tags=["Full Pipeline"])
app.include_router(admin.router, prefix=f"{settings.API_PREFIX}/admin", tags=["Admin"])


@app.get("/")
async def root():
    """Root endpoint with API info."""
    return {
        "name": settings.API_TITLE,
        "version": settings.API_VERSION,
        "docs": "/docs",
        "health": f"{settings.API_PREFIX}/health",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)
