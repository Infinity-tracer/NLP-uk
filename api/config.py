"""API Configuration settings."""
import os
from typing import Optional


class Settings:
    """Application settings loaded from environment variables."""

    # API Settings
    API_TITLE: str = "NLP-uk Clinical Pipeline API"
    API_VERSION: str = "1.0.0"
    API_PREFIX: str = "/api/v1"
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

    # AWS Settings
    AWS_REGION: str = os.getenv("AWS_REGION", "us-east-1")

    # Processing Settings (0-100 scale for API, converted to 0-1 internally)
    DEFAULT_CONFIDENCE_THRESHOLD: float = 90.0
    TIER2_CONFIDENCE_THRESHOLD: float = 90.0
    TIER3_CONFIDENCE_THRESHOLD: float = 0.85  # 0-1 scale (Tier 3 module expects 0-1)

    # File Upload Settings
    MAX_FILE_SIZE_MB: int = 50
    ALLOWED_FILE_TYPES: set = {"application/pdf", "image/jpeg", "image/png", "image/tiff"}

    # Directory Settings
    TEMP_PAGES_DIR: str = "temp_pages"
    TEXTRACT_OUTPUTS_DIR: str = "textract_outputs"
    TIER2_OUTPUTS_DIR: str = "tier2_outputs"
    TRACK_A_OUTPUTS_DIR: str = "track_a_outputs"
    TRACK_B_OUTPUTS_DIR: str = "track_b_outputs"

    # CORS Settings
    CORS_ORIGINS: list = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173").split(",")


settings = Settings()
