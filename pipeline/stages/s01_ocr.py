"""
Stage 1: OCR - Text Extraction

Extracts text from document images using AWS Textract.
Produces per-page text and confidence scores.
"""

import os
import sys
from pathlib import Path
from typing import List, Tuple

from ..base import PipelineStage, StageResult, PipelineContext, StageStatus, StageRegistry


@StageRegistry.register
class OCRStage(PipelineStage):
    """
    OCR Stage - Extract text from document images.

    Supports:
    - AWS Textract (default)
    - Fallback to basic extraction

    Outputs:
    - raw_ocr_text: Full document text
    - page_texts: Per-page text
    - Per-page confidence scores
    """

    @property
    def name(self) -> str:
        return "ocr"

    @property
    def description(self) -> str:
        return "Extract text from document images using OCR"

    def process(self, context: PipelineContext) -> StageResult:
        """Run OCR on document pages."""
        result = StageResult(
            stage_name=self.name,
            status=StageStatus.RUNNING,
            confidence=0.0,
        )

        try:
            # Get page images from context
            page_images = context.page_images
            if not page_images:
                result.status = StageStatus.ERROR
                result.error = "No page images to process"
                return result

            # Run OCR on each page
            all_texts = []
            all_confidences = []
            page_results = []

            for i, img_path in enumerate(page_images):
                page_text, page_conf = self._run_textract(img_path)

                all_texts.append(page_text)
                all_confidences.append(page_conf)

                page_results.append({
                    "page": i + 1,
                    "text_length": len(page_text),
                    "confidence": page_conf,
                    "image_path": img_path,
                })

                result.add_note(f"Page {i+1}: {len(page_text)} chars, conf={page_conf:.3f}")

            # Combine results
            full_text = "\n\n".join(all_texts)
            avg_confidence = sum(all_confidences) / len(all_confidences) if all_confidences else 0.0

            # Update context
            context.raw_ocr_text = full_text
            context.page_texts = all_texts
            context.pages_processed = len(page_images)

            # Build result
            result.status = StageStatus.DONE
            result.confidence = avg_confidence
            result.items_processed = len(page_images)
            result.data = {
                "full_text": full_text,
                "page_texts": all_texts,
                "page_confidences": all_confidences,
                "total_chars": len(full_text),
            }
            result.debug_data = {
                "page_results": page_results,
                "provider": context.config.ocr_provider if context.config else "textract",
            }

            # Flag for review if confidence below threshold
            threshold = context.config.ocr_confidence_threshold if context.config else 0.90
            if avg_confidence < threshold:
                result.add_note(f"Low confidence ({avg_confidence:.3f}) - flagged for review")

            return result

        except Exception as e:
            result.status = StageStatus.ERROR
            result.error = str(e)
            return result

    def _run_textract(self, image_path: str) -> Tuple[str, float]:
        """
        Run AWS Textract on a single image.

        Returns (text, confidence).
        """
        import boto3

        try:
            # Read image bytes
            with open(image_path, "rb") as f:
                image_bytes = f.read()

            # Call Textract
            client = boto3.client(
                "textract",
                region_name=os.getenv("AWS_REGION", "us-east-1"),
            )

            response = client.detect_document_text(
                Document={"Bytes": image_bytes}
            )

            # Extract text and confidence
            lines = []
            confidences = []

            for block in response.get("Blocks", []):
                if block["BlockType"] == "LINE":
                    lines.append(block.get("Text", ""))
                    confidences.append(block.get("Confidence", 0) / 100.0)

            text = "\n".join(lines)
            avg_conf = sum(confidences) / len(confidences) if confidences else 0.5

            return text, avg_conf

        except Exception as e:
            print(f"[WARN] Textract failed: {e}, using fallback", file=sys.stderr)
            return self._run_fallback(image_path)

    def _run_fallback(self, image_path: str) -> Tuple[str, float]:
        """Fallback OCR using PyMuPDF or basic extraction."""
        try:
            import fitz

            # Try to extract text if it's a PDF
            ext = Path(image_path).suffix.lower()
            if ext == ".pdf":
                doc = fitz.open(image_path)
                text = ""
                for page in doc:
                    text += page.get_text()
                doc.close()
                return text, 0.7  # Lower confidence for fallback

        except ImportError:
            pass

        return "", 0.0
