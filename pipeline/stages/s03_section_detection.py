"""
Stage 3: Section Detection - Document Structure Parsing

Detects clinical document sections (History, Examination, Diagnosis, etc.)
and determines document type.
"""

import re
from typing import Dict, List, Optional, Tuple

from ..base import PipelineStage, StageResult, PipelineContext, StageStatus, StageRegistry


@StageRegistry.register
class SectionDetectionStage(PipelineStage):
    """
    Section Detection Stage - Parse document structure.

    Detects:
    - Document sections (PC, HPC, PMH, Examination, etc.)
    - Document type (ED Discharge, Clinic Letter, etc.)
    - Section boundaries and content

    Outputs:
    - sections: List of detected sections with content
    - document_type: Detected document type
    """

    # Section header patterns (case-insensitive)
    SECTION_PATTERNS = {
        "presenting_complaint": [
            r"presenting\s*complaint",
            r"reason\s*for\s*(?:attendance|visit|referral)",
            r"chief\s*complaint",
            r"pc[:\s]",
            r"main\s*problem",
        ],
        "history_presenting_complaint": [
            r"history\s*of\s*(?:the\s*)?presenting\s*(?:complaint|illness)",
            r"hpc[:\s]",
            r"hopi[:\s]",
            r"clinical\s*history",
        ],
        "past_medical_history": [
            r"past\s*(?:medical\s*)?history",
            r"pmh[:\s]",
            r"medical\s*history",
            r"previous\s*history",
            r"background",
        ],
        "surgical_history": [
            r"(?:past\s*)?surgical\s*history",
            r"psh[:\s]",
            r"previous\s*(?:surgery|operations)",
        ],
        "medication": [
            r"(?:current\s*)?medications?",
            r"drug\s*(?:history|list)",
            r"regular\s*medications?",
            r"meds[:\s]",
            r"prescription",
        ],
        "allergies": [
            r"allerg(?:y|ies)",
            r"adverse\s*(?:drug\s*)?reactions?",
            r"known\s*allergies",
            r"nkda",  # No Known Drug Allergies
        ],
        "social_history": [
            r"social\s*history",
            r"sh[:\s]",
            r"social\s*background",
            r"smoking|alcohol|occupation",
        ],
        "family_history": [
            r"family\s*history",
            r"fh[:\s]",
            r"fhx[:\s]",
        ],
        "examination": [
            r"(?:physical\s*)?examination",
            r"o/?e[:\s]",
            r"on\s*examination",
            r"clinical\s*findings?",
            r"findings",
        ],
        "investigations": [
            r"investigations?",
            r"results?",
            r"(?:blood\s*)?tests?",
            r"labs?(?:oratory)?",
            r"imaging",
            r"ix[:\s]",
        ],
        "diagnosis": [
            r"diagnos(?:is|es)",
            r"dx[:\s]",
            r"impression",
            r"assessment",
            r"working\s*diagnosis",
            r"final\s*diagnosis",
        ],
        "treatment": [
            r"treatment",
            r"management",
            r"plan",
            r"rx[:\s]",
            r"therapy",
        ],
        "discharge": [
            r"discharge",
            r"outcome",
            r"disposition",
        ],
        "advice": [
            r"advice",
            r"recommendations?",
            r"patient\s*information",
            r"safety\s*net",
        ],
        "gp_actions": [
            r"gp\s*(?:actions?|to\s*(?:do|action))",
            r"primary\s*care\s*actions?",
            r"for\s*(?:the\s*)?gp",
            r"practice\s*actions?",
        ],
        "follow_up": [
            r"follow[\s\-]*up",
            r"f/?u[:\s]",
            r"review",
            r"next\s*steps?",
            r"outpatient",
        ],
        "referral": [
            r"referral",
            r"refer(?:red)?\s*to",
            r"specialist\s*review",
        ],
    }

    # Document type detection signals
    DOCUMENT_TYPE_SIGNALS = {
        "ed_discharge": {
            "primary": ["emergency department", "a&e", "accident and emergency", "triage"],
            "secondary": ["arrival", "departure", "attendance", "disposition"],
            "exclude": ["clinic", "ward", "admission"],
        },
        "clinic_letter": {
            "primary": ["outpatient", "clinic", "seen in clinic", "thank you for referring"],
            "secondary": ["consultant", "follow-up appointment"],
            "exclude": ["emergency", "discharge summary"],
        },
        "discharge_summary": {
            "primary": ["discharge summary", "inpatient", "admitted", "length of stay"],
            "secondary": ["ward", "course", "discharge diagnosis"],
            "exclude": ["a&e", "emergency department"],
        },
        "radiology": {
            "primary": ["radiology", "x-ray", "ct scan", "mri", "ultrasound"],
            "secondary": ["findings", "impression", "technique"],
            "exclude": [],
        },
        "histopathology": {
            "primary": ["pathology", "histopathology", "specimen", "microscopy"],
            "secondary": ["macroscopy", "grade", "stage", "margins"],
            "exclude": [],
        },
        "operative_notes": {
            "primary": ["operative", "operation", "procedure note", "surgical"],
            "secondary": ["surgeon", "anaesthetist", "blood loss"],
            "exclude": [],
        },
        "mental_health": {
            "primary": ["psychiatric", "mental health", "mental state"],
            "secondary": ["risk assessment", "capacity", "section 2", "section 3"],
            "exclude": [],
        },
    }

    @property
    def name(self) -> str:
        return "section_detection"

    @property
    def description(self) -> str:
        return "Detect document sections and document type"

    def get_dependencies(self) -> List[str]:
        return ["ocr_cleanup"]

    def validate_input(self, context: PipelineContext) -> bool:
        return bool(context.get_text())

    def process(self, context: PipelineContext) -> StageResult:
        """Detect sections and document type."""
        result = StageResult(
            stage_name=self.name,
            status=StageStatus.RUNNING,
            confidence=0.0,
        )

        try:
            text = context.get_text()
            if not text:
                result.status = StageStatus.SKIPPED
                result.error = "No text to process"
                return result

            # Detect document type
            doc_type, doc_type_conf, type_signals = self._detect_document_type(text)

            # Detect sections
            sections = self._detect_sections(text)

            # Calculate confidence
            section_confidence = min(1.0, len(sections) * 0.15 + 0.4)
            overall_confidence = (section_confidence + doc_type_conf) / 2

            # Update context
            context.sections = sections
            context.document_type = doc_type
            context.document_type_confidence = doc_type_conf

            # Build result
            result.status = StageStatus.DONE
            result.confidence = overall_confidence
            result.items_processed = len(sections)
            result.data = {
                "document_type": doc_type,
                "document_type_confidence": doc_type_conf,
                "sections": sections,
                "section_count": len(sections),
            }
            result.debug_data = {
                "type_signals_matched": type_signals,
                "section_types": [s["type"] for s in sections],
            }

            result.add_note(f"Document type: {doc_type} (conf={doc_type_conf:.2f})")
            result.add_note(f"Detected {len(sections)} sections")

            return result

        except Exception as e:
            result.status = StageStatus.ERROR
            result.error = str(e)
            return result

    def _detect_document_type(self, text: str) -> Tuple[str, float, List[str]]:
        """Detect document type from content signals."""
        text_lower = text.lower()[:3000]  # Check first 3000 chars
        scores = {}
        matched_signals = {}

        for doc_type, signals in self.DOCUMENT_TYPE_SIGNALS.items():
            score = 0
            matches = []

            # Check primary signals (high weight)
            for signal in signals["primary"]:
                if signal in text_lower:
                    score += 3
                    matches.append(f"+{signal}")

            # Check secondary signals (medium weight)
            for signal in signals["secondary"]:
                if signal in text_lower:
                    score += 1
                    matches.append(f"+{signal}")

            # Check exclusion signals (negative weight)
            for signal in signals.get("exclude", []):
                if signal in text_lower:
                    score -= 2
                    matches.append(f"-{signal}")

            if score > 0:
                scores[doc_type] = score
                matched_signals[doc_type] = matches

        if not scores:
            return "unknown", 0.3, []

        # Get best match
        best_type = max(scores, key=scores.get)
        best_score = scores[best_type]

        # Calculate confidence based on score
        confidence = min(0.95, 0.5 + (best_score * 0.1))

        return best_type, confidence, matched_signals.get(best_type, [])

    def _detect_sections(self, text: str) -> List[Dict]:
        """Detect sections in the document."""
        sections = []
        lines = text.split('\n')

        current_section = None
        current_content = []
        current_start = 0

        for i, line in enumerate(lines):
            # Check if line is a section header
            section_type = self._identify_section_header(line)

            if section_type:
                # Save previous section
                if current_section:
                    sections.append({
                        "type": current_section,
                        "heading": lines[current_start].strip() if current_start < len(lines) else "",
                        "content": '\n'.join(current_content).strip(),
                        "start_line": current_start + 1,
                        "end_line": i,
                        "confidence": 0.8,
                    })

                # Start new section
                current_section = section_type
                current_content = []
                current_start = i
            elif current_section:
                current_content.append(line)

        # Save last section
        if current_section:
            sections.append({
                "type": current_section,
                "heading": lines[current_start].strip() if current_start < len(lines) else "",
                "content": '\n'.join(current_content).strip(),
                "start_line": current_start + 1,
                "end_line": len(lines),
                "confidence": 0.8,
            })

        return sections

    def _identify_section_header(self, line: str) -> Optional[str]:
        """Identify if a line is a section header."""
        line_stripped = line.strip()

        # Skip empty lines or very long lines (not headers)
        if not line_stripped or len(line_stripped) > 100:
            return None

        # Check against patterns
        for section_type, patterns in self.SECTION_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, line_stripped, re.IGNORECASE):
                    return section_type

        return None
