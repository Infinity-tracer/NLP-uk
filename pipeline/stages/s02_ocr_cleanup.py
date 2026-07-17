"""
Stage 2: OCR Cleanup - Medical Text Normalization

Cleans and normalizes OCR output for better NLP processing.
Fixes common OCR errors, removes artifacts, normalizes whitespace.
"""

import re
import sys
from typing import Dict, List, Tuple

from ..base import PipelineStage, StageResult, PipelineContext, StageStatus, StageRegistry


@StageRegistry.register
class OCRCleanupStage(PipelineStage):
    """
    OCR Cleanup Stage - Normalize medical text.

    Performs:
    - OCR error correction (l/1, O/0 confusion)
    - Artifact removal (page numbers, headers)
    - Whitespace normalization
    - Line break handling
    - Unicode normalization

    Outputs:
    - normalized_text: Cleaned document text
    - corrections_count: Number of corrections made
    """

    # Common OCR error patterns
    OCR_CORRECTIONS = {
        # Letter/number confusion
        r'\bl\b(?=\s*mg\b)': '1',  # "l mg" -> "1 mg"
        r'\bO\b(?=\s*mg\b)': '0',  # "O mg" -> "0 mg"
        r'(?<=\d)l(?=\d)': '1',    # "1l0" -> "110"
        r'(?<=\d)O(?=\d)': '0',    # "1O0" -> "100"

        # Common medical term OCR errors
        r'\brnl\b': 'ml',
        r'\brng\b': 'mg',
        r'\bmcq\b': 'mcg',
        r'\brnm\b': 'mm',
        r'\bhrn\b': 'hm',

        # Punctuation errors
        r'(?<=\d)\s*,\s*(?=\d{3}\b)': '',  # Remove thousands separator confusion
    }

    # Patterns to remove (artifacts)
    ARTIFACT_PATTERNS = [
        r'^Page\s+\d+\s+of\s+\d+\s*$',      # Page numbers
        r'^\d+\s*$',                         # Lone page numbers
        r'^-{3,}$',                          # Separator lines
        r'^_{3,}$',
        r'^\*{3,}$',
        r'^Confidential\s*$',                # Headers
        r'^DRAFT\s*$',
        r'^COPY\s*$',
    ]

    # Medical abbreviation expansions for normalization
    NORMALIZATIONS = {
        r'\bBP\b': 'blood pressure',
        r'\bHR\b': 'heart rate',
        r'\bRR\b': 'respiratory rate',
        r'\bSPO2\b': 'oxygen saturation',
        r'\bSp02\b': 'oxygen saturation',
        r'\bSpO2\b': 'oxygen saturation',
        r'\bT\s*:\s*(\d+\.?\d*)': r'temperature \1',
    }

    @property
    def name(self) -> str:
        return "ocr_cleanup"

    @property
    def description(self) -> str:
        return "Clean and normalize OCR text for NLP processing"

    def get_dependencies(self) -> List[str]:
        return ["ocr"]

    def validate_input(self, context: PipelineContext) -> bool:
        return bool(context.raw_ocr_text)

    def process(self, context: PipelineContext) -> StageResult:
        """Clean and normalize OCR text."""
        result = StageResult(
            stage_name=self.name,
            status=StageStatus.RUNNING,
            confidence=0.0,
        )

        try:
            raw_text = context.raw_ocr_text
            if not raw_text:
                result.status = StageStatus.SKIPPED
                result.error = "No text to process"
                return result

            # Track corrections
            corrections = []
            original_length = len(raw_text)

            # Step 1: Unicode normalization
            text = self._normalize_unicode(raw_text)

            # Step 2: Remove artifacts
            text, artifacts_removed = self._remove_artifacts(text)
            if artifacts_removed:
                corrections.append(f"Removed {artifacts_removed} artifacts")

            # Step 3: Fix OCR errors
            text, ocr_fixes = self._fix_ocr_errors(text)
            corrections.extend(ocr_fixes)

            # Step 4: Normalize whitespace
            text = self._normalize_whitespace(text)

            # Step 5: Fix line breaks
            text = self._fix_line_breaks(text)

            # Calculate confidence based on correction rate
            correction_rate = len(corrections) / max(1, original_length / 100)
            confidence = max(0.5, 1.0 - (correction_rate * 0.1))

            # Update context
            context.normalized_text = text

            # Build result
            result.status = StageStatus.DONE
            result.confidence = confidence
            result.items_processed = 1
            result.data = {
                "normalized_text": text,
                "original_length": original_length,
                "normalized_length": len(text),
                "corrections_count": len(corrections),
            }
            result.debug_data = {
                "corrections": corrections[:50],  # Limit for debug output
                "length_change_percent": round(
                    (len(text) - original_length) / max(1, original_length) * 100, 2
                ),
            }

            result.add_note(f"Made {len(corrections)} corrections")
            result.add_note(f"Length: {original_length} → {len(text)}")

            return result

        except Exception as e:
            result.status = StageStatus.ERROR
            result.error = str(e)
            return result

    def _normalize_unicode(self, text: str) -> str:
        """Normalize Unicode characters."""
        import unicodedata

        # Normalize to NFC form
        text = unicodedata.normalize("NFC", text)

        # Replace common problematic characters
        replacements = {
            '‘': "'",  # Left single quote
            '’': "'",  # Right single quote
            '“': '"',  # Left double quote
            '”': '"',  # Right double quote
            '–': '-',  # En dash
            '—': '-',  # Em dash
            '…': '...',  # Ellipsis
            ' ': ' ',  # Non-breaking space
            '﻿': '',   # BOM
        }

        for old, new in replacements.items():
            text = text.replace(old, new)

        return text

    def _remove_artifacts(self, text: str) -> Tuple[str, int]:
        """Remove OCR artifacts like page numbers and headers."""
        lines = text.split('\n')
        cleaned_lines = []
        removed_count = 0

        for line in lines:
            is_artifact = False
            for pattern in self.ARTIFACT_PATTERNS:
                if re.match(pattern, line.strip(), re.IGNORECASE):
                    is_artifact = True
                    removed_count += 1
                    break

            if not is_artifact:
                cleaned_lines.append(line)

        return '\n'.join(cleaned_lines), removed_count

    def _fix_ocr_errors(self, text: str) -> Tuple[str, List[str]]:
        """Fix common OCR errors."""
        corrections = []

        for pattern, replacement in self.OCR_CORRECTIONS.items():
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
                corrections.append(f"Fixed '{pattern}' → '{replacement}' ({len(matches)}x)")

        return text, corrections

    def _normalize_whitespace(self, text: str) -> str:
        """Normalize whitespace characters."""
        # Replace multiple spaces with single space
        text = re.sub(r'[ \t]+', ' ', text)

        # Replace multiple newlines with double newline
        text = re.sub(r'\n{3,}', '\n\n', text)

        # Strip trailing whitespace from lines
        lines = [line.rstrip() for line in text.split('\n')]
        text = '\n'.join(lines)

        return text.strip()

    def _fix_line_breaks(self, text: str) -> str:
        """Fix inappropriate line breaks (mid-sentence splits)."""
        # Join lines that were split mid-sentence
        # Look for lowercase letter at end of line followed by lowercase at start
        text = re.sub(r'([a-z,])\n([a-z])', r'\1 \2', text)

        # Join hyphenated words split across lines
        text = re.sub(r'(\w)-\n(\w)', r'\1\2', text)

        return text
