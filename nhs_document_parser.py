"""
NHS Clinical Document Parser
============================
Specialized parser for NHS clinical document types with document-specific extraction rules.

Supported document types:
- ED Discharge
- Clinic Letter
- Radiology Report
- Histopathology Report
- Operative Notes
- Referral Letters
- GP Letters
- Mental Health Reports
- Discharge Summary
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class NHSDocumentType(Enum):
    """NHS clinical document types."""
    ED_DISCHARGE = "ed_discharge"
    CLINIC_LETTER = "clinic_letter"
    RADIOLOGY = "radiology"
    HISTOPATHOLOGY = "histopathology"
    OPERATIVE_NOTES = "operative_notes"
    REFERRAL_LETTER = "referral_letter"
    GP_LETTER = "gp_letter"
    MENTAL_HEALTH = "mental_health"
    DISCHARGE_SUMMARY = "discharge_summary"
    UNKNOWN = "unknown"


@dataclass
class DocumentTypeSignature:
    """Signature patterns for document type detection."""
    doc_type: NHSDocumentType
    primary_signals: list[str]  # Must match at least one
    secondary_signals: list[str]  # Additional confirmation signals
    header_signals: list[str]  # Signals expected in first 500 chars
    exclusion_signals: list[str]  # If present, NOT this type
    confidence_boost: float = 0.0  # Confidence adjustment
    priority: int = 0  # Higher = check first


# Document type signatures with NHS-specific patterns
DOCUMENT_SIGNATURES: list[DocumentTypeSignature] = [
    # ED Discharge - Emergency Department
    DocumentTypeSignature(
        doc_type=NHSDocumentType.ED_DISCHARGE,
        primary_signals=[
            "emergency department", "a&e discharge", "ed discharge",
            "accident and emergency", "emergency medicine",
            "attendance reason", "arrival method", "triage category",
            "presenting complaint", "mode of arrival", "source of referral",
        ],
        secondary_signals=[
            "time of arrival", "time of departure", "seen by",
            "investigations in ed", "disposition", "follow up",
            "safety netting", "red flags discussed",
        ],
        header_signals=["emergency", "ed ", "a&e", "accident"],
        exclusion_signals=["discharge summary", "inpatient"],
        priority=10,
    ),

    # Radiology Report
    DocumentTypeSignature(
        doc_type=NHSDocumentType.RADIOLOGY,
        primary_signals=[
            "radiology report", "imaging report", "radiologist",
            "x-ray report", "ct report", "mri report", "ultrasound report",
            "examination:", "clinical details:", "findings:",
            "impression:", "recommendation:",
        ],
        secondary_signals=[
            "kvp", "mas", "contrast", "sequences", "views",
            "no acute abnormality", "unremarkable", "normal appearances",
            "compared to previous", "correlation recommended",
        ],
        header_signals=["radiology", "imaging", "x-ray", "ct ", "mri ", "ultrasound"],
        exclusion_signals=["discharge summary", "clinic letter", "operative"],
        priority=15,
    ),

    # Histopathology Report
    DocumentTypeSignature(
        doc_type=NHSDocumentType.HISTOPATHOLOGY,
        primary_signals=[
            "histopathology", "pathology report", "histology report",
            "specimen:", "macroscopy:", "microscopy:", "diagnosis:",
            "cellular pathology", "biopsy report",
        ],
        secondary_signals=[
            "formalin", "cassettes", "sections", "h&e", "immunohistochemistry",
            "ihc", "malignant", "benign", "dysplasia", "carcinoma",
            "adenoma", "margins", "grade", "stage",
        ],
        header_signals=["pathology", "histology", "histopathology", "specimen"],
        exclusion_signals=["radiology", "operative"],
        priority=15,
    ),

    # Operative Notes
    DocumentTypeSignature(
        doc_type=NHSDocumentType.OPERATIVE_NOTES,
        primary_signals=[
            "operative note", "operation note", "procedure note",
            "surgical report", "theatre report",
            "operation:", "procedure:", "surgeon:", "anaesthetist:",
            "indication:", "findings:", "closure:",
        ],
        secondary_signals=[
            "incision", "dissection", "haemostasis", "sutures",
            "blood loss", "drains", "tourniquet", "diathermy",
            "general anaesthesia", "regional anaesthesia", "spinal",
            "post-operative instructions", "vte prophylaxis",
        ],
        header_signals=["operative", "operation", "surgical", "theatre"],
        exclusion_signals=["clinic letter", "radiology"],
        priority=12,
    ),

    # Mental Health Report
    DocumentTypeSignature(
        doc_type=NHSDocumentType.MENTAL_HEALTH,
        primary_signals=[
            "mental health", "psychiatric", "psychiatry",
            "mental state examination", "mse:", "risk assessment",
            "section 2", "section 3", "mental health act",
            "crhtt", "cmht", "crisis team", "home treatment",
        ],
        secondary_signals=[
            "mood", "affect", "thought content", "delusions", "hallucinations",
            "insight", "suicidal ideation", "self-harm", "psychosis",
            "antipsychotic", "antidepressant", "anxiolytic",
            "safeguarding", "capacity", "mca",
        ],
        header_signals=["mental health", "psychiatric", "psychiatry", "cmht", "crhtt"],
        exclusion_signals=["radiology", "histopathology", "operative"],
        priority=11,
    ),

    # Referral Letter
    DocumentTypeSignature(
        doc_type=NHSDocumentType.REFERRAL_LETTER,
        primary_signals=[
            "referral", "refer to", "referring to", "please see",
            "i would be grateful", "please could you",
            "request for opinion", "request for review",
            "2 week wait", "2ww", "urgent referral", "routine referral",
        ],
        secondary_signals=[
            "reason for referral", "background", "current medications",
            "allergies", "please advise", "awaiting your review",
            "happy to discuss", "please contact", "accept this referral",
        ],
        header_signals=["referral", "refer"],
        exclusion_signals=["discharge summary", "operative note", "radiology report"],
        priority=8,
    ),

    # GP Letter
    DocumentTypeSignature(
        doc_type=NHSDocumentType.GP_LETTER,
        primary_signals=[
            "gp letter", "dear doctor", "dear colleague",
            "to the gp", "for gp", "gp surgery",
            "primary care", "general practice",
        ],
        secondary_signals=[
            "please arrange", "please prescribe", "please monitor",
            "blood test", "review in", "follow up with gp",
            "repeat prescription", "medication review",
        ],
        header_signals=["gp ", "general practice", "surgery"],
        exclusion_signals=["discharge summary", "operative", "radiology"],
        priority=5,
    ),

    # Clinic Letter
    DocumentTypeSignature(
        doc_type=NHSDocumentType.CLINIC_LETTER,
        primary_signals=[
            "clinic letter", "outpatient letter", "outpatient appointment",
            "thank you for referring", "i reviewed", "i saw",
            "seen in clinic", "attended clinic", "follow-up clinic",
        ],
        secondary_signals=[
            "on examination", "impression", "plan", "diagnosis",
            "investigations", "medications", "next appointment",
            "will review", "discharged from clinic",
        ],
        header_signals=["clinic", "outpatient"],
        exclusion_signals=["emergency", "operative", "radiology", "histopathology"],
        priority=6,
    ),

    # Discharge Summary (generic inpatient)
    DocumentTypeSignature(
        doc_type=NHSDocumentType.DISCHARGE_SUMMARY,
        primary_signals=[
            "discharge summary", "inpatient discharge", "discharge letter",
            "admission date", "discharge date", "length of stay",
            "discharging consultant", "ward:",
        ],
        secondary_signals=[
            "reason for admission", "diagnosis on admission",
            "investigations during admission", "procedures",
            "discharge medications", "follow up",
            "gp actions required", "safety netting",
        ],
        header_signals=["discharge", "inpatient"],
        exclusion_signals=["emergency department", "ed discharge", "a&e"],
        priority=7,
    ),
]


@dataclass
class ExtractedSection:
    """Extracted document section."""
    name: str
    content: str
    start_pos: int
    end_pos: int
    confidence: float = 0.8


@dataclass
class DocumentSpecificData:
    """Document type-specific extracted data."""
    # Common fields
    document_type: NHSDocumentType
    document_type_confidence: float
    date: Optional[str] = None
    author: Optional[str] = None
    recipient: Optional[str] = None

    # ED Discharge specific
    triage_category: Optional[str] = None
    arrival_time: Optional[str] = None
    departure_time: Optional[str] = None
    presenting_complaint: Optional[str] = None
    ed_diagnosis: Optional[str] = None
    disposition: Optional[str] = None

    # Radiology specific
    examination_type: Optional[str] = None
    clinical_indication: Optional[str] = None
    technique: Optional[str] = None
    findings: Optional[str] = None
    impression: Optional[str] = None
    comparison: Optional[str] = None

    # Histopathology specific
    specimen_type: Optional[str] = None
    specimen_site: Optional[str] = None
    macroscopy: Optional[str] = None
    microscopy: Optional[str] = None
    histology_diagnosis: Optional[str] = None
    grade: Optional[str] = None
    stage: Optional[str] = None
    margins: Optional[str] = None

    # Operative Notes specific
    operation_name: Optional[str] = None
    surgeon: Optional[str] = None
    anaesthetist: Optional[str] = None
    anaesthesia_type: Optional[str] = None
    indication: Optional[str] = None
    operative_findings: Optional[str] = None
    procedure_details: Optional[str] = None
    blood_loss: Optional[str] = None
    complications: Optional[str] = None
    post_op_instructions: Optional[str] = None

    # Mental Health specific
    mental_state: Optional[str] = None
    risk_assessment: Optional[str] = None
    mha_status: Optional[str] = None
    capacity_assessment: Optional[str] = None
    care_plan: Optional[str] = None

    # Discharge Summary specific
    admission_date: Optional[str] = None
    discharge_date: Optional[str] = None
    admission_reason: Optional[str] = None
    inpatient_course: Optional[str] = None
    discharge_diagnosis: Optional[str] = None
    discharge_medications: list[str] = field(default_factory=list)
    follow_up_plan: Optional[str] = None
    gp_actions: list[str] = field(default_factory=list)

    # Extracted sections
    sections: list[ExtractedSection] = field(default_factory=list)

    # Raw signals matched
    signals_matched: list[str] = field(default_factory=list)


class NHSDocumentParser:
    """Parser for NHS clinical documents with type-specific extraction."""

    def __init__(self):
        self.signatures = sorted(DOCUMENT_SIGNATURES, key=lambda s: -s.priority)

        # Section patterns for each document type
        self.section_patterns = {
            NHSDocumentType.ED_DISCHARGE: [
                (r"(?:presenting\s+complaint|chief\s+complaint|reason\s+for\s+attendance)[:\s]*(.+?)(?=\n[A-Z]|\n\n|$)", "presenting_complaint"),
                (r"(?:triage\s+category|triage)[:\s]*(\d+|[a-z]+)", "triage_category"),
                (r"(?:arrival|arrived|time\s+of\s+arrival)[:\s]*(\d{1,2}[:.]\d{2})", "arrival_time"),
                (r"(?:departure|discharged|left|time\s+of\s+departure)[:\s]*(\d{1,2}[:.]\d{2})", "departure_time"),
                (r"(?:diagnosis|impression|ed\s+diagnosis)[:\s]*(.+?)(?=\n[A-Z]|\n\n|$)", "ed_diagnosis"),
                (r"(?:disposition|outcome|discharge\s+destination)[:\s]*(.+?)(?=\n|$)", "disposition"),
            ],
            NHSDocumentType.RADIOLOGY: [
                (r"(?:examination|study|procedure)[:\s]*(.+?)(?=\n|$)", "examination_type"),
                (r"(?:clinical\s+(?:details|indication|information)|indication)[:\s]*(.+?)(?=\n[A-Z]|\n\n|$)", "clinical_indication"),
                (r"(?:technique|protocol)[:\s]*(.+?)(?=\n[A-Z]|\n\n|$)", "technique"),
                (r"(?:findings|report)[:\s]*(.+?)(?=impression|conclusion|\n\n|$)", "findings"),
                (r"(?:impression|conclusion|summary)[:\s]*(.+?)(?=\n\n|recommendation|$)", "impression"),
                (r"(?:comparison|compared\s+(?:to|with))[:\s]*(.+?)(?=\n|$)", "comparison"),
            ],
            NHSDocumentType.HISTOPATHOLOGY: [
                (r"(?:specimen|sample)[:\s]*(.+?)(?=\n|$)", "specimen_type"),
                (r"(?:site|location)[:\s]*(.+?)(?=\n|$)", "specimen_site"),
                (r"(?:macroscopy|macroscopic|gross)[:\s]*(.+?)(?=microscop|\n\n|$)", "macroscopy"),
                (r"(?:microscopy|microscopic|histology)[:\s]*(.+?)(?=diagnosis|conclusion|\n\n|$)", "microscopy"),
                (r"(?:diagnosis|conclusion)[:\s]*(.+?)(?=\n\n|$)", "histology_diagnosis"),
                (r"(?:grade|grading)[:\s]*(.+?)(?=\n|$)", "grade"),
                (r"(?:stage|staging|tnm)[:\s]*(.+?)(?=\n|$)", "stage"),
                (r"(?:margin|margins)[:\s]*(.+?)(?=\n|$)", "margins"),
            ],
            NHSDocumentType.OPERATIVE_NOTES: [
                (r"(?:operation|procedure)[:\s]*(.+?)(?=\n|$)", "operation_name"),
                (r"(?:surgeon|operator|performed\s+by)[:\s]*(.+?)(?=\n|$)", "surgeon"),
                (r"(?:anaesthetist|anesthetist)[:\s]*(.+?)(?=\n|$)", "anaesthetist"),
                (r"(?:anaesthesia|anesthesia)[:\s]*(.+?)(?=\n|$)", "anaesthesia_type"),
                (r"(?:indication|reason)[:\s]*(.+?)(?=\n|$)", "indication"),
                (r"(?:findings|operative\s+findings)[:\s]*(.+?)(?=procedure|closure|\n\n|$)", "operative_findings"),
                (r"(?:procedure|technique|details)[:\s]*(.+?)(?=closure|complications|\n\n|$)", "procedure_details"),
                (r"(?:blood\s+loss|ebl)[:\s]*(.+?)(?=\n|$)", "blood_loss"),
                (r"(?:complications)[:\s]*(.+?)(?=\n|$)", "complications"),
                (r"(?:post[- ]?op(?:erative)?\s+(?:instructions|plan))[:\s]*(.+?)(?=\n\n|$)", "post_op_instructions"),
            ],
            NHSDocumentType.MENTAL_HEALTH: [
                (r"(?:mental\s+state\s+examination|mse)[:\s]*(.+?)(?=risk|\n\n|$)", "mental_state"),
                (r"(?:risk\s+assessment|risk)[:\s]*(.+?)(?=plan|formulation|\n\n|$)", "risk_assessment"),
                (r"(?:mha|mental\s+health\s+act|section)[:\s]*(.+?)(?=\n|$)", "mha_status"),
                (r"(?:capacity|mca)[:\s]*(.+?)(?=\n|$)", "capacity_assessment"),
                (r"(?:care\s+plan|plan|management)[:\s]*(.+?)(?=\n\n|$)", "care_plan"),
            ],
            NHSDocumentType.DISCHARGE_SUMMARY: [
                (r"(?:admission\s+date|admitted)[:\s]*(.+?)(?=\n|$)", "admission_date"),
                (r"(?:discharge\s+date|discharged)[:\s]*(.+?)(?=\n|$)", "discharge_date"),
                (r"(?:reason\s+for\s+admission|presenting\s+complaint)[:\s]*(.+?)(?=\n\n|$)", "admission_reason"),
                (r"(?:inpatient\s+course|summary\s+of\s+admission|course)[:\s]*(.+?)(?=discharge|\n\n|$)", "inpatient_course"),
                (r"(?:discharge\s+diagnosis|diagnosis\s+(?:at|on)\s+discharge)[:\s]*(.+?)(?=\n\n|medication|$)", "discharge_diagnosis"),
                (r"(?:follow[- ]?up|follow\s+up\s+plan)[:\s]*(.+?)(?=\n\n|gp|$)", "follow_up_plan"),
            ],
        }

    def detect_document_type(self, text: str) -> tuple[NHSDocumentType, float, list[str]]:
        """Detect document type from text content.

        Returns:
            (document_type, confidence, signals_matched)
        """
        text_lower = text.lower()
        header = text_lower[:800]  # First 800 chars for header signals

        best_type = NHSDocumentType.UNKNOWN
        best_score = 0.0
        best_signals = []

        for sig in self.signatures:
            score = 0.0
            signals_matched = []

            # Check primary signals (required)
            primary_matches = [s for s in sig.primary_signals if s in text_lower]
            if not primary_matches:
                continue

            score += len(primary_matches) * 0.15
            signals_matched.extend(primary_matches)

            # Check header signals (bonus)
            header_matches = [s for s in sig.header_signals if s in header]
            score += len(header_matches) * 0.1
            signals_matched.extend(header_matches)

            # Check secondary signals (bonus)
            secondary_matches = [s for s in sig.secondary_signals if s in text_lower]
            score += len(secondary_matches) * 0.05
            signals_matched.extend(secondary_matches[:5])  # Limit to top 5

            # Check exclusion signals (penalty)
            exclusion_matches = [s for s in sig.exclusion_signals if s in text_lower]
            if exclusion_matches:
                score -= len(exclusion_matches) * 0.2

            # Apply confidence boost
            score += sig.confidence_boost

            # Cap at 1.0
            score = min(score, 1.0)

            if score > best_score:
                best_score = score
                best_type = sig.doc_type
                best_signals = list(set(signals_matched))

        # Ensure minimum confidence
        if best_score < 0.3:
            return NHSDocumentType.UNKNOWN, best_score, best_signals

        return best_type, best_score, best_signals

    def extract_document_specific_data(
        self,
        text: str,
        doc_type: Optional[NHSDocumentType] = None
    ) -> DocumentSpecificData:
        """Extract document-specific data based on document type.

        Args:
            text: Document text
            doc_type: Document type (if None, will be detected)

        Returns:
            DocumentSpecificData with extracted fields
        """
        # Detect document type if not provided
        if doc_type is None:
            doc_type, confidence, signals = self.detect_document_type(text)
        else:
            confidence = 0.9
            signals = []

        result = DocumentSpecificData(
            document_type=doc_type,
            document_type_confidence=confidence,
            signals_matched=signals,
        )

        # Extract common fields
        result.date = self._extract_date(text)
        result.author = self._extract_author(text)
        result.recipient = self._extract_recipient(text)

        # Extract document-specific sections
        if doc_type in self.section_patterns:
            for pattern, field_name in self.section_patterns[doc_type]:
                match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
                if match:
                    value = match.group(1).strip()
                    if value:
                        setattr(result, field_name, value[:500])  # Limit length
                        result.sections.append(ExtractedSection(
                            name=field_name,
                            content=value[:500],
                            start_pos=match.start(),
                            end_pos=match.end(),
                        ))

        # Type-specific post-processing
        if doc_type == NHSDocumentType.DISCHARGE_SUMMARY:
            result.discharge_medications = self._extract_medications(text)
            result.gp_actions = self._extract_gp_actions(text)

        return result

    def _extract_date(self, text: str) -> Optional[str]:
        """Extract document date."""
        patterns = [
            r"(?:date|dated)[:\s]*(\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4})",
            r"(\d{1,2}(?:st|nd|rd|th)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{2,4})",
            r"(\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4})",
        ]
        for pattern in patterns:
            match = re.search(pattern, text[:1000], re.IGNORECASE)
            if match:
                return match.group(1)
        return None

    def _extract_author(self, text: str) -> Optional[str]:
        """Extract document author/clinician."""
        patterns = [
            r"(?:signed|written|authored|prepared)\s+by[:\s]*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)",
            r"(?:consultant|doctor|dr|mr|ms|miss|mrs)[:\s]*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)",
            r"(?:yours\s+sincerely|kind\s+regards)[,\s]*\n+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return None

    def _extract_recipient(self, text: str) -> Optional[str]:
        """Extract document recipient."""
        patterns = [
            r"(?:dear|to)[:\s]*(?:dr|doctor|mr|ms|miss|mrs)?\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)",
            r"(?:gp|general\s+practitioner)[:\s]*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text[:500], re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return None

    def _extract_medications(self, text: str) -> list[str]:
        """Extract medication list from discharge summary."""
        meds = []
        # Look for medication sections
        med_section = re.search(
            r"(?:discharge\s+medications?|medications?\s+(?:on|at)\s+discharge|ttc|to\s+take\s+away)[:\s]*(.+?)(?=\n\n|follow|gp\s+actions|$)",
            text, re.IGNORECASE | re.DOTALL
        )
        if med_section:
            med_text = med_section.group(1)
            # Split by newlines or bullets
            lines = re.split(r'\n|•|[-–](?=\s)', med_text)
            for line in lines:
                line = line.strip()
                if line and len(line) > 3:
                    meds.append(line[:200])
        return meds[:20]  # Limit to 20 medications

    def _extract_gp_actions(self, text: str) -> list[str]:
        """Extract GP actions from discharge summary."""
        actions = []
        # Look for GP action sections
        action_section = re.search(
            r"(?:gp\s+actions?|actions?\s+for\s+gp|gp\s+to|please)[:\s]*(.+?)(?=\n\n|follow|patient\s+advice|$)",
            text, re.IGNORECASE | re.DOTALL
        )
        if action_section:
            action_text = action_section.group(1)
            # Split by newlines or bullets
            lines = re.split(r'\n|•|[-–](?=\s)|\d+[.)]\s*', action_text)
            for line in lines:
                line = line.strip()
                if line and len(line) > 5:
                    actions.append(line[:200])
        return actions[:10]  # Limit to 10 actions

    def parse(self, text: str) -> dict:
        """Parse document and return structured data.

        Returns dict suitable for JSON serialization.
        """
        data = self.extract_document_specific_data(text)

        result = {
            "document_type": data.document_type.value,
            "document_type_name": data.document_type.name.replace("_", " ").title(),
            "document_type_confidence": data.document_type_confidence,
            "date": data.date,
            "author": data.author,
            "recipient": data.recipient,
            "signals_matched": data.signals_matched,
            "sections": [
                {
                    "name": s.name,
                    "content": s.content,
                    "confidence": s.confidence,
                }
                for s in data.sections
            ],
        }

        # Add type-specific fields based on document type
        if data.document_type == NHSDocumentType.ED_DISCHARGE:
            result["ed_specific"] = {
                "triage_category": data.triage_category,
                "arrival_time": data.arrival_time,
                "departure_time": data.departure_time,
                "presenting_complaint": data.presenting_complaint,
                "ed_diagnosis": data.ed_diagnosis,
                "disposition": data.disposition,
            }

        elif data.document_type == NHSDocumentType.RADIOLOGY:
            result["radiology_specific"] = {
                "examination_type": data.examination_type,
                "clinical_indication": data.clinical_indication,
                "technique": data.technique,
                "findings": data.findings,
                "impression": data.impression,
                "comparison": data.comparison,
            }

        elif data.document_type == NHSDocumentType.HISTOPATHOLOGY:
            result["histopathology_specific"] = {
                "specimen_type": data.specimen_type,
                "specimen_site": data.specimen_site,
                "macroscopy": data.macroscopy,
                "microscopy": data.microscopy,
                "diagnosis": data.histology_diagnosis,
                "grade": data.grade,
                "stage": data.stage,
                "margins": data.margins,
            }

        elif data.document_type == NHSDocumentType.OPERATIVE_NOTES:
            result["operative_specific"] = {
                "operation_name": data.operation_name,
                "surgeon": data.surgeon,
                "anaesthetist": data.anaesthetist,
                "anaesthesia_type": data.anaesthesia_type,
                "indication": data.indication,
                "operative_findings": data.operative_findings,
                "procedure_details": data.procedure_details,
                "blood_loss": data.blood_loss,
                "complications": data.complications,
                "post_op_instructions": data.post_op_instructions,
            }

        elif data.document_type == NHSDocumentType.MENTAL_HEALTH:
            result["mental_health_specific"] = {
                "mental_state": data.mental_state,
                "risk_assessment": data.risk_assessment,
                "mha_status": data.mha_status,
                "capacity_assessment": data.capacity_assessment,
                "care_plan": data.care_plan,
            }

        elif data.document_type == NHSDocumentType.DISCHARGE_SUMMARY:
            result["discharge_specific"] = {
                "admission_date": data.admission_date,
                "discharge_date": data.discharge_date,
                "admission_reason": data.admission_reason,
                "inpatient_course": data.inpatient_course,
                "discharge_diagnosis": data.discharge_diagnosis,
                "discharge_medications": data.discharge_medications,
                "follow_up_plan": data.follow_up_plan,
                "gp_actions": data.gp_actions,
            }

        return result


# Convenience function
def parse_nhs_document(text: str) -> dict:
    """Parse an NHS clinical document and extract type-specific data."""
    parser = NHSDocumentParser()
    return parser.parse(text)
