"""Pytest fixtures for API tests."""
import os
import sys
import pytest
from fastapi.testclient import TestClient

# Add parent directories to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from api.main import app


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


@pytest.fixture
def sample_image_path():
    """Path to a sample test image."""
    # Create a simple test image if it doesn't exist
    test_dir = os.path.dirname(os.path.abspath(__file__))
    test_image = os.path.join(test_dir, "test_image.jpg")

    if not os.path.exists(test_image):
        # Create a minimal JPEG for testing
        from PIL import Image
        img = Image.new('RGB', (100, 100), color='white')
        img.save(test_image, 'JPEG')

    return test_image


@pytest.fixture
def sample_pdf_path():
    """Path to sample clinical document PDF."""
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    pdf_path = os.path.join(project_root, "sample_clinical_doc.pdf")

    if os.path.exists(pdf_path):
        return pdf_path
    return None
