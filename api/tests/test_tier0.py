"""Tests for Tier 0 preprocessing endpoint."""
import os
import pytest


def test_tier0_preprocess_success(client, sample_image_path):
    """Test successful image preprocessing."""
    if not sample_image_path:
        pytest.skip("No test image available")

    with open(sample_image_path, "rb") as f:
        response = client.post(
            "/api/v1/tier0/preprocess",
            files={"file": ("test.jpg", f, "image/jpeg")}
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "preprocessed_images" in data
    assert "processing_time_ms" in data


def test_tier0_preprocess_invalid_file_type(client):
    """Test preprocessing with invalid file type."""
    response = client.post(
        "/api/v1/tier0/preprocess",
        files={"file": ("test.txt", b"hello world", "text/plain")}
    )

    assert response.status_code == 400
    assert "Unsupported file type" in response.json()["detail"]


def test_tier0_preprocess_with_pdf(client, sample_pdf_path):
    """Test preprocessing with PDF file."""
    if not sample_pdf_path or not os.path.exists(sample_pdf_path):
        pytest.skip("No sample PDF available")

    with open(sample_pdf_path, "rb") as f:
        response = client.post(
            "/api/v1/tier0/preprocess",
            files={"file": ("sample.pdf", f, "application/pdf")}
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["total_pages"] > 0
