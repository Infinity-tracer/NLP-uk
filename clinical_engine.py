"""
Clinical Intelligence Engine for NHS Document Processing

This module provides context-aware clinical entity extraction, classification,
and validation. It replaces keyword-based matching with clinically-informed
understanding of document structure, entity types, and temporal states.

Pipeline:
    Document → Section Detection → Entity Extraction → Classification →
    SNOMED/ICD Mapping → Clinical Validation → Confidence Scoring

Key features:
- Document structure detection (sections, headers, tables)
- Context-aware entity classification
- Negation and temporal state detection
- Ontology-aware code mapping
- Clinical validation layer
- Component-level confidence scoring
- Full explainability/traceability
"""

from __future__ import annotations
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal
from enum import Enum


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1: ENUMS AND DATA CLASSES
# ══════════════════════════════════════════════════════════════════════════════

class EntityCategory(Enum):
    """Clinical entity categories for proper code mapping."""
    DIAGNOSIS = "diagnosis"
    PROCEDURE = "procedure"
    MEDICATION = "medication"
    INVESTIGATION = "investigation"
    FOLLOW_UP = "follow_up"
    ALLERGY = "allergy"
    OBSERVATION = "observation"
    ADMINISTRATIVE = "administrative"
    ANATOMICAL = "anatomical"
    LABORATORY = "laboratory"
    SYMPTOM = "symptom"
    UNKNOWN = "unknown"


class TemporalState(Enum):
    """Temporal state of clinical entities."""
    CURRENT = "current"
    HISTORICAL = "historical"
    PLANNED = "planned"
    RESOLVED = "resolved"
    PENDING = "pending"
    FAMILY_HISTORY = "family_history"
    DIFFERENTIAL = "differential"


class NegationStatus(Enum):
    """Negation status of clinical entities."""
    AFFIRMED = "affirmed"
    NEGATED = "negated"
    UNCERTAIN = "uncertain"
    RULED_OUT = "ruled_out"


class SectionType(Enum):
    """Standard clinical document sections."""
    DIAGNOSIS = "diagnosis"
    PROCEDURE = "procedure"
    MEDICATION = "medication"
    ALLERGY = "allergy"
    INVESTIGATION = "investigation"
    FOLLOW_UP = "follow_up"
    GP_ACTIONS = "gp_actions"
    PLAN = "plan"
    ASSESSMENT = "assessment"
    HISTORY = "history"
    IMPRESSION = "impression"
    EXAMINATION = "examination"
    SOCIAL_HISTORY = "social_history"
    FAMILY_HISTORY = "family_history"
    HEADER = "header"
    UNKNOWN = "unknown"


@dataclass
class DocumentSection:
    """A detected section within a clinical document."""
    section_type: SectionType
    title: str
    content: str
    start_pos: int
    end_pos: int
    confidence: float = 1.0


@dataclass
class ClinicalEntity:
    """A clinical entity extracted from the document with full context."""
    entity_id: str
    text: str
    category: EntityCategory
    temporal_state: TemporalState
    negation_status: NegationStatus
    section: SectionType

    # Position and evidence
    start_pos: int = 0
    end_pos: int = 0
    page_number: int = 1
    original_text: str = ""
    context_window: str = ""

    # Clinical coding
    snomed_code: str = ""
    snomed_description: str = ""
    icd_code: str = ""
    icd_description: str = ""

    # Confidence breakdown
    extraction_confidence: float = 0.0
    classification_confidence: float = 0.0
    coding_confidence: float = 0.0
    validation_confidence: float = 0.0
    overall_confidence: float = 0.0

    # Additional metadata
    priority: str = ""  # Urgent, Routine, etc.
    result: str = ""    # For investigations: Pending, Normal, etc.
    responsible_party: str = ""  # For follow-ups
    due_date: str = ""  # For follow-ups

    # Validation
    is_valid: bool = True
    validation_notes: list = field(default_factory=list)
    evidence: list = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "entity_id": self.entity_id,
            "text": self.text,
            "category": self.category.value,
            "temporal_state": self.temporal_state.value,
            "negation_status": self.negation_status.value,
            "section": self.section.value,
            "start_pos": self.start_pos,
            "end_pos": self.end_pos,
            "page_number": self.page_number,
            "original_text": self.original_text,
            "context_window": self.context_window,
            "snomed_code": self.snomed_code,
            "snomed_description": self.snomed_description,
            "icd_code": self.icd_code,
            "icd_description": self.icd_description,
            "extraction_confidence": self.extraction_confidence,
            "classification_confidence": self.classification_confidence,
            "coding_confidence": self.coding_confidence,
            "validation_confidence": self.validation_confidence,
            "overall_confidence": self.overall_confidence,
            "priority": self.priority,
            "result": self.result,
            "responsible_party": self.responsible_party,
            "due_date": self.due_date,
            "is_valid": self.is_valid,
            "validation_notes": self.validation_notes,
            "evidence": self.evidence,
        }


@dataclass
class ConfidenceScore:
    """Component-level confidence scoring."""
    ocr_quality: float = 0.0
    layout_detection: float = 0.0
    entity_extraction: float = 0.0
    entity_classification: float = 0.0
    clinical_coding: float = 0.0
    validation: float = 0.0
    overall: float = 0.0

    def compute_overall(self, weights: dict = None) -> float:
        """Compute weighted overall confidence."""
        if weights is None:
            weights = {
                "ocr_quality": 0.15,
                "layout_detection": 0.10,
                "entity_extraction": 0.20,
                "entity_classification": 0.15,
                "clinical_coding": 0.25,
                "validation": 0.15,
            }
        self.overall = (
            weights["ocr_quality"] * self.ocr_quality +
            weights["layout_detection"] * self.layout_detection +
            weights["entity_extraction"] * self.entity_extraction +
            weights["entity_classification"] * self.entity_classification +
            weights["clinical_coding"] * self.clinical_coding +
            weights["validation"] * self.validation
        )
        return self.overall

    def to_dict(self) -> dict:
        return {
            "ocr_quality": round(self.ocr_quality, 3),
            "layout_detection": round(self.layout_detection, 3),
            "entity_extraction": round(self.entity_extraction, 3),
            "entity_classification": round(self.entity_classification, 3),
            "clinical_coding": round(self.clinical_coding, 3),
            "validation": round(self.validation, 3),
            "overall": round(self.overall, 3),
        }


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2: DOCUMENT STRUCTURE DETECTION
# ══════════════════════════════════════════════════════════════════════════════

# Section header patterns for NHS clinical documents
SECTION_PATTERNS = {
    SectionType.DIAGNOSIS: [
        r'(?i)^(?:post[- ]?op\s+)?diagnosis(?:es)?[:\s]*$',
        r'(?i)^primary\s+diagnosis[:\s]*$',
        r'(?i)^secondary\s+diagnos(?:is|es)[:\s]*$',
        r'(?i)^working\s+diagnosis[:\s]*$',
        r'(?i)^final\s+diagnosis[:\s]*$',
        r'(?i)^presenting\s+complaint[:\s]*$',
    ],
    SectionType.PROCEDURE: [
        r'(?i)^procedure(?:s)?(?:\s+information)?[:\s]*$',
        r'(?i)^operation(?:s)?(?:\s+performed)?[:\s]*$',
        r'(?i)^surgical\s+procedure[:\s]*$',
        r'(?i)^interventions?[:\s]*$',
    ],
    SectionType.MEDICATION: [
        r'(?i)^(?:your\s+)?medication(?:s)?(?:\s+list)?[:\s]*$',
        r'(?i)^(?:current\s+)?medications?(?:\s+on\s+discharge)?[:\s]*$',
        r'(?i)^(?:continue\s+)?taking\s+(?:this\s+)?medication[:\s]*$',
        r'(?i)^drugs?\s+on\s+discharge[:\s]*$',
        r'(?i)^prescription[:\s]*$',
        r'(?i)^tto[:\s]*$',  # To Take Out
        r'(?i)^tta[:\s]*$',  # To Take Away
    ],
    SectionType.ALLERGY: [
        r'(?i)^allergies?(?:\s+as\s+of)?[:\s]*',
        r'(?i)^known\s+allergies?[:\s]*$',
        r'(?i)^drug\s+allergies?[:\s]*$',
        r'(?i)^adverse\s+reactions?[:\s]*$',
    ],
    SectionType.INVESTIGATION: [
        r'(?i)^investigations?(?:\s+pending)?[:\s]*$',
        r'(?i)^(?:laboratory\s+)?results?[:\s]*$',
        r'(?i)^(?:blood\s+)?tests?[:\s]*$',
        r'(?i)^imaging[:\s]*$',
        r'(?i)^specimens?[:\s]*$',
        r'(?i)^histology[:\s]*$',
        r'(?i)^pathology[:\s]*$',
        r'(?i)^radiology[:\s]*$',
        r'(?i)^unresulted\s+labs?[:\s]*$',
    ],
    SectionType.FOLLOW_UP: [
        r'(?i)^follow[- ]?up[:\s]*$',
        r'(?i)^outpatient\s+follow[- ]?up[:\s]*$',
        r'(?i)^review[:\s]*$',
        r'(?i)^next\s+appointment[:\s]*$',
    ],
    SectionType.GP_ACTIONS: [
        r'(?i)^(?:actions?\s+)?required\s+(?:of\s+)?(?:general\s+practice|gp)(?:\s*\([^)]*\))?[:\s]*$',
        r'(?i)^gp\s+actions?[:\s]*$',
        r'(?i)^gp\s+surgery\s+actions?[:\s]*$',
        r'(?i)^for\s+(?:the\s+)?gp[:\s]*$',
        r'(?i)^gp\s+to\s+(?:do|action)[:\s]*$',
    ],
    SectionType.PLAN: [
        r'(?i)^plan(?:\s+and\s+requested\s+actions)?[:\s]*$',
        r'(?i)^management\s+plan[:\s]*$',
        r'(?i)^discharge\s+plan[:\s]*$',
        r'(?i)^treatment\s+plan[:\s]*$',
        r'(?i)^post[- ]?op\s+instructions?[:\s]*$',
    ],
    SectionType.ASSESSMENT: [
        r'(?i)^assessment[:\s]*$',
        r'(?i)^clinical\s+assessment[:\s]*$',
        r'(?i)^findings?[:\s]*$',
    ],
    SectionType.HISTORY: [
        r'(?i)^(?:past\s+)?medical\s+history[:\s]*$',
        r'(?i)^(?:relevant\s+)?history[:\s]*$',
        r'(?i)^pmh[:\s]*$',
        r'(?i)^hpc[:\s]*$',  # History of Presenting Complaint
        r'(?i)^history\s+of\s+presenting\s+complaint[:\s]*$',
    ],
    SectionType.IMPRESSION: [
        r'(?i)^impression[:\s]*$',
        r'(?i)^summary[:\s]*$',
        r'(?i)^clinical\s+summary[:\s]*$',
        r'(?i)^discharge\s+summary[:\s]*$',
        r'(?i)^conclusion[:\s]*$',
    ],
    SectionType.EXAMINATION: [
        r'(?i)^examination[:\s]*$',
        r'(?i)^(?:physical\s+)?exam(?:ination)?[:\s]*$',
        r'(?i)^on\s+examination[:\s]*$',
        r'(?i)^o/?e[:\s]*$',
    ],
    SectionType.SOCIAL_HISTORY: [
        r'(?i)^social\s+history[:\s]*$',
        r'(?i)^shx[:\s]*$',
    ],
    SectionType.FAMILY_HISTORY: [
        r'(?i)^family\s+history[:\s]*$',
        r'(?i)^fhx[:\s]*$',
    ],
}


def detect_document_sections(text: str) -> list[DocumentSection]:
    """
    Detect clinical document sections from text.

    Returns list of DocumentSection objects with section type, content, and positions.
    """
    sections = []
    lines = text.split('\n')
    current_section = None
    current_content_lines = []
    current_start = 0

    pos = 0
    for i, line in enumerate(lines):
        line_stripped = line.strip()
        line_length = len(line) + 1  # +1 for newline

        # Try to match section headers
        matched_section = None
        for section_type, patterns in SECTION_PATTERNS.items():
            for pattern in patterns:
                if re.match(pattern, line_stripped):
                    matched_section = section_type
                    break
            if matched_section:
                break

        if matched_section:
            # Save previous section if exists
            if current_section is not None:
                content = '\n'.join(current_content_lines).strip()
                if content:
                    sections.append(DocumentSection(
                        section_type=current_section,
                        title=current_title,
                        content=content,
                        start_pos=current_start,
                        end_pos=pos,
                    ))

            # Start new section
            current_section = matched_section
            current_title = line_stripped
            current_content_lines = []
            current_start = pos
        elif current_section is not None:
            current_content_lines.append(line)

        pos += line_length

    # Save final section
    if current_section is not None and current_content_lines:
        content = '\n'.join(current_content_lines).strip()
        if content:
            sections.append(DocumentSection(
                section_type=current_section,
                title=current_title,
                content=content,
                start_pos=current_start,
                end_pos=pos,
            ))

    return sections


def get_section_at_position(sections: list[DocumentSection], pos: int) -> SectionType:
    """Get the section type at a given character position."""
    for section in sections:
        if section.start_pos <= pos <= section.end_pos:
            return section.section_type
    return SectionType.UNKNOWN


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3: NEGATION AND TEMPORAL STATE DETECTION
# ══════════════════════════════════════════════════════════════════════════════

# Negation patterns
NEGATION_PATTERNS = [
    # Pre-entity negations
    r'\b(?:no|not|without|denies?|denied|negative\s+for|ruled?\s+out|excludes?|'
    r'absence\s+of|never|none|nil|neither|nor|does\s+not\s+have|'
    r'unlikely|improbable|no\s+evidence\s+of|not\s+consistent\s+with)\b',
    # Post-entity negations
    r'\b(?:negative|absent|not\s+(?:present|found|detected|seen|identified))\b',
]

# Ruled out / differential patterns
RULED_OUT_PATTERNS = [
    r'\brule[ds]?\s+out\b',
    r'\bexclude[ds]?\b',
    r'\bdifferential\s+(?:diagnosis|includes?)\b',
    r'\b(?:to\s+)?exclude\b',
    r'\bunlikely\b',
]

# Historical patterns
HISTORICAL_PATTERNS = [
    r'\b(?:history\s+of|h/?o|past|previous(?:ly)?|prior|former|'
    r'in\s+(?:19|20)\d{2}|years?\s+ago|\d+\s+years?\s+ago|'
    r'childhood|long[- ]?standing|chronic|known|established)\b',
    r'\bpast\s+medical\s+history\b',
    r'\bpmh\b',
]

# Planned/future patterns
PLANNED_PATTERNS = [
    r'\b(?:planned|will\s+(?:be|have|undergo)|scheduled|for|awaiting|'
    r'to\s+(?:be\s+)?(?:done|performed|arranged|booked)|pending|upcoming|'
    r'arrange|refer(?:ral)?|consider(?:ing)?|recommend(?:ed)?)\b',
]

# Family history patterns
FAMILY_HISTORY_PATTERNS = [
    r'\b(?:family\s+history|fhx?|mother|father|sibling|brother|sister|'
    r'parent|grandparent|relative|familial)\b',
]

# Resolved patterns
RESOLVED_PATTERNS = [
    r'\b(?:resolved|cured|recovered|healed|improved|better|'
    r'no\s+longer|discontinued|stopped|cleared|remission)\b',
]


def detect_negation_status(text: str, entity_pos: int, context_window: int = 100) -> NegationStatus:
    """
    Detect negation status of an entity based on surrounding context.

    Args:
        text: Full document text
        entity_pos: Character position of the entity
        context_window: Characters before/after entity to check

    Returns:
        NegationStatus enum value
    """
    # Get context window
    start = max(0, entity_pos - context_window)
    end = min(len(text), entity_pos + context_window)
    context = text[start:end].lower()

    # Check for ruled out
    for pattern in RULED_OUT_PATTERNS:
        if re.search(pattern, context, re.IGNORECASE):
            return NegationStatus.RULED_OUT

    # Check for negation
    for pattern in NEGATION_PATTERNS:
        if re.search(pattern, context, re.IGNORECASE):
            return NegationStatus.NEGATED

    # Check for uncertainty
    if re.search(r'\b(?:possible|probable|likely|suspect(?:ed)?|query|?\?)\b', context):
        return NegationStatus.UNCERTAIN

    return NegationStatus.AFFIRMED


def detect_temporal_state(
    text: str,
    entity_pos: int,
    section: SectionType,
    context_window: int = 100
) -> TemporalState:
    """
    Detect temporal state of an entity based on context and section.

    Args:
        text: Full document text
        entity_pos: Character position of the entity
        section: Section where entity was found
        context_window: Characters before/after entity to check

    Returns:
        TemporalState enum value
    """
    # Section-based defaults
    if section == SectionType.HISTORY:
        return TemporalState.HISTORICAL
    if section == SectionType.FAMILY_HISTORY:
        return TemporalState.FAMILY_HISTORY

    # Get context window
    start = max(0, entity_pos - context_window)
    end = min(len(text), entity_pos + context_window)
    context = text[start:end].lower()

    # Check patterns
    for pattern in FAMILY_HISTORY_PATTERNS:
        if re.search(pattern, context, re.IGNORECASE):
            return TemporalState.FAMILY_HISTORY

    for pattern in RESOLVED_PATTERNS:
        if re.search(pattern, context, re.IGNORECASE):
            return TemporalState.RESOLVED

    for pattern in HISTORICAL_PATTERNS:
        if re.search(pattern, context, re.IGNORECASE):
            return TemporalState.HISTORICAL

    for pattern in PLANNED_PATTERNS:
        if re.search(pattern, context, re.IGNORECASE):
            return TemporalState.PLANNED

    # Check for pending (investigations)
    if re.search(r'\b(?:pending|awaiting|outstanding|to\s+follow)\b', context):
        return TemporalState.PENDING

    # Check for differential
    if re.search(r'\b(?:differential|possible|query|?)\b', context):
        return TemporalState.DIFFERENTIAL

    return TemporalState.CURRENT


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 4: ENTITY CLASSIFICATION
# ══════════════════════════════════════════════════════════════════════════════

# Category-specific patterns for classification
CATEGORY_PATTERNS = {
    EntityCategory.MEDICATION: [
        # Common drug name patterns
        r'\b\d+\s*(?:mg|mcg|ml|g|iu|units?)\b',
        r'\b(?:tablet|capsule|injection|inhaler|cream|gel|ointment|patch|drop|syrup|solution)\b',
        r'\b(?:once|twice|three\s+times?|four\s+times?|daily|weekly|bd|tds|qds|od|prn)\b',
    ],
    EntityCategory.INVESTIGATION: [
        r'\b(?:ct|mri|x[- ]?ray|ultrasound|scan|ecg|ekg|echo|angio|pet|'
        r'colonoscopy|endoscopy|gastroscopy|sigmoidoscopy|cystoscopy|bronchoscopy|'
        r'biopsy|histology|cytology|pathology|blood\s+test|urine\s+test|'
        r'fbc|lfts?|u&e|creatinine|egfr|hba1c|lipid|thyroid|glucose|'
        r'culture|swab|pcr|antigen)\b',
    ],
    EntityCategory.PROCEDURE: [
        r'\b(?:surgery|operation|procedure|excision|removal|repair|'
        r'injection|infusion|transfusion|transplant|implant|'
        r'resection|ablation|bypass|graft|reconstruction|'
        r'aspiration|drainage|debridement|amputation)\b',
    ],
    EntityCategory.ALLERGY: [
        r'\b(?:allergy|allergic|anaphylaxis|reaction\s+to|intolerance|'
        r'hypersensitivity|contraindicated)\b',
    ],
    EntityCategory.ANATOMICAL: [
        r'\b(?:structure|body\s+part|anatomy|region|area|site|location)\b',
    ],
}

# SNOMED semantic tags that indicate entity category
SNOMED_CATEGORY_MAPPING = {
    "(disorder)": EntityCategory.DIAGNOSIS,
    "(finding)": EntityCategory.OBSERVATION,
    "(procedure)": EntityCategory.PROCEDURE,
    "(substance)": EntityCategory.MEDICATION,
    "(product)": EntityCategory.MEDICATION,
    "(body structure)": EntityCategory.ANATOMICAL,
    "(morphologic abnormality)": EntityCategory.DIAGNOSIS,
    "(observable entity)": EntityCategory.OBSERVATION,
    "(situation)": EntityCategory.OBSERVATION,
    "(event)": EntityCategory.PROCEDURE,
    "(regime/therapy)": EntityCategory.PROCEDURE,
}


def classify_entity_category(
    text: str,
    snomed_description: str = "",
    comprehend_category: str = "",
    section: SectionType = SectionType.UNKNOWN
) -> tuple[EntityCategory, float]:
    """
    Classify an entity into a clinical category.

    Uses multiple signals:
    1. SNOMED semantic tag from description
    2. AWS Comprehend Medical category
    3. Document section context
    4. Pattern matching

    Returns:
        Tuple of (EntityCategory, confidence)
    """
    confidence = 0.5
    text_lower = text.lower()
    desc_lower = snomed_description.lower() if snomed_description else ""

    # 1. Check SNOMED semantic tag (highest priority)
    for tag, category in SNOMED_CATEGORY_MAPPING.items():
        if tag in desc_lower:
            return (category, 0.95)

    # 2. Check Comprehend Medical category
    cat_upper = comprehend_category.upper() if comprehend_category else ""
    if cat_upper:
        if cat_upper in ("MEDICATION", "GENERIC_NAME", "BRAND_NAME"):
            return (EntityCategory.MEDICATION, 0.90)
        if cat_upper == "TEST_NAME":
            return (EntityCategory.INVESTIGATION, 0.90)
        if cat_upper == "PROCEDURE_NAME":
            return (EntityCategory.PROCEDURE, 0.90)
        if cat_upper == "TREATMENT_NAME":
            return (EntityCategory.PROCEDURE, 0.85)
        if cat_upper == "ANATOMY":
            return (EntityCategory.ANATOMICAL, 0.90)
        if cat_upper in ("MEDICAL_CONDITION", "DX_NAME"):
            return (EntityCategory.DIAGNOSIS, 0.85)

    # 3. Section-based classification
    section_category_map = {
        SectionType.MEDICATION: EntityCategory.MEDICATION,
        SectionType.ALLERGY: EntityCategory.ALLERGY,
        SectionType.INVESTIGATION: EntityCategory.INVESTIGATION,
        SectionType.PROCEDURE: EntityCategory.PROCEDURE,
        SectionType.DIAGNOSIS: EntityCategory.DIAGNOSIS,
    }
    if section in section_category_map:
        return (section_category_map[section], 0.80)

    # 4. Pattern-based classification
    for category, patterns in CATEGORY_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text_lower, re.IGNORECASE):
                return (category, 0.75)

    # Default based on description keywords
    if any(x in desc_lower for x in ["therapy", "treatment", "procedure"]):
        return (EntityCategory.PROCEDURE, 0.70)
    if any(x in desc_lower for x in ["drug", "medication", "medicinal"]):
        return (EntityCategory.MEDICATION, 0.70)
    if any(x in desc_lower for x in ["test", "examination", "assessment", "measurement"]):
        return (EntityCategory.INVESTIGATION, 0.70)

    return (EntityCategory.DIAGNOSIS, 0.50)  # Default


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 5: CLINICAL VALIDATION ENGINE
# ══════════════════════════════════════════════════════════════════════════════

class ClinicalValidationEngine:
    """
    Validates extracted clinical entities for accuracy and consistency.

    Catches:
    - Anatomy misclassified as diagnosis
    - Procedures misclassified as diagnosis
    - Diagnoses misclassified as procedures
    - Hallucinated entities
    - Contextually invalid concepts
    - Low-confidence entities
    - Duplicate entities
    """

    # Terms that should NEVER be coded as diagnoses
    ANATOMY_BLOCKLIST = {
        "disc", "disk", "rectum", "colon", "anus", "anal", "sigmoid",
        "descending", "mucosa", "tissue", "skin", "tag", "tags",
        "stomach", "intestine", "bowel", "liver", "kidney", "lung",
        "heart", "brain", "bone", "muscle", "nerve", "vessel", "artery",
        "vein", "lymph", "node", "gland", "organ", "structure",
    }

    # SNOMED codes that are anatomical structures (not conditions)
    ANATOMY_SNOMED_CODES = {
        "34402009",   # Rectum
        "71854001",   # Colon
        "53505006",   # Anus
        "60184004",   # Sigmoid colon
        "32713005",   # Descending colon
        "414781009",  # Mucosa
        "39937001",   # Skin
        "123037004",  # Body structure
        "91723000",   # Anatomical structure
    }

    # Procedure-only SNOMED codes (should not be in diagnoses)
    PROCEDURE_SNOMED_CODES = {
        "73761001",   # Colonoscopy
        "44441009",   # Flexible sigmoidoscopy
        "386053000",  # Evaluation procedure
        "11429006",   # Consultation
    }

    # Minimum confidence thresholds by category
    MIN_CONFIDENCE = {
        EntityCategory.DIAGNOSIS: 0.45,
        EntityCategory.PROCEDURE: 0.50,
        EntityCategory.MEDICATION: 0.60,
        EntityCategory.INVESTIGATION: 0.50,
        EntityCategory.ALLERGY: 0.70,
        EntityCategory.OBSERVATION: 0.40,
    }

    def __init__(self):
        self.validation_errors = []
        self.validation_warnings = []

    def validate_entity(self, entity: ClinicalEntity) -> tuple[bool, list[str]]:
        """
        Validate a single clinical entity.

        Returns:
            Tuple of (is_valid, list of validation notes)
        """
        notes = []
        is_valid = True
        text_lower = entity.text.lower().strip()

        # 1. Check for anatomy misclassified as diagnosis
        if entity.category == EntityCategory.DIAGNOSIS:
            if text_lower in self.ANATOMY_BLOCKLIST:
                notes.append(f"Rejected: '{entity.text}' is anatomical term, not diagnosis")
                is_valid = False

            if entity.snomed_code in self.ANATOMY_SNOMED_CODES:
                notes.append(f"Rejected: SNOMED {entity.snomed_code} is anatomical structure")
                is_valid = False

            if entity.snomed_code in self.PROCEDURE_SNOMED_CODES:
                notes.append(f"Rejected: SNOMED {entity.snomed_code} is procedure, not diagnosis")
                is_valid = False

            if entity.snomed_description:
                desc_lower = entity.snomed_description.lower()
                if "(body structure)" in desc_lower:
                    notes.append(f"Rejected: SNOMED description indicates anatomical structure")
                    is_valid = False

        # 2. Check negation status - don't code negated entities
        if entity.negation_status in (NegationStatus.NEGATED, NegationStatus.RULED_OUT):
            notes.append(f"Excluded: Entity is {entity.negation_status.value}")
            is_valid = False

        # 3. Check temporal state - different handling for historical
        if entity.temporal_state == TemporalState.FAMILY_HISTORY:
            notes.append("Flagged: Family history - should not be coded as patient condition")
            is_valid = False

        # 4. Check confidence threshold
        min_conf = self.MIN_CONFIDENCE.get(entity.category, 0.40)
        if entity.overall_confidence < min_conf:
            notes.append(f"Low confidence ({entity.overall_confidence:.2f} < {min_conf})")
            is_valid = False

        # 5. Check for very short/generic terms
        if len(text_lower) < 3:
            notes.append(f"Rejected: Term too short ({len(text_lower)} chars)")
            is_valid = False

        # 6. Check for administrative/non-clinical terms
        admin_terms = {
            "treatment", "advice", "consultation", "review", "assessment",
            "follow-up", "referral", "patient", "doctor", "nurse",
        }
        if text_lower in admin_terms:
            notes.append(f"Rejected: '{entity.text}' is administrative term")
            is_valid = False

        entity.is_valid = is_valid
        entity.validation_notes = notes

        return is_valid, notes

    def validate_entities(self, entities: list[ClinicalEntity]) -> list[ClinicalEntity]:
        """
        Validate all entities and remove invalid ones.

        Returns:
            List of valid entities only
        """
        valid_entities = []
        seen_codes = set()
        seen_texts = set()

        for entity in entities:
            is_valid, notes = self.validate_entity(entity)

            # Check for duplicates
            key = (entity.text.lower(), entity.snomed_code)
            if key in seen_codes or entity.text.lower() in seen_texts:
                entity.is_valid = False
                entity.validation_notes.append("Duplicate entity removed")
                continue

            if is_valid:
                valid_entities.append(entity)
                if entity.snomed_code:
                    seen_codes.add(key)
                seen_texts.add(entity.text.lower())

        return valid_entities

    def validate_consistency(
        self,
        entities: list[ClinicalEntity],
        sections: list[DocumentSection]
    ) -> list[str]:
        """
        Cross-validate entities against document sections.

        Catches:
        - Procedures in text but not in procedure output
        - Medications in medication section but not extracted
        - Missing follow-up actions
        """
        warnings = []

        # Get entities by category
        diagnoses = [e for e in entities if e.category == EntityCategory.DIAGNOSIS]
        procedures = [e for e in entities if e.category == EntityCategory.PROCEDURE]
        medications = [e for e in entities if e.category == EntityCategory.MEDICATION]
        investigations = [e for e in entities if e.category == EntityCategory.INVESTIGATION]

        # Check procedure section has corresponding entities
        procedure_sections = [s for s in sections if s.section_type == SectionType.PROCEDURE]
        for section in procedure_sections:
            if section.content.strip() and not procedures:
                warnings.append(
                    f"Procedure section detected but no procedures extracted. "
                    f"Section content: {section.content[:100]}..."
                )

        # Check medication section
        med_sections = [s for s in sections if s.section_type == SectionType.MEDICATION]
        for section in med_sections:
            if section.content.strip() and not medications:
                warnings.append(
                    f"Medication section detected but no medications extracted. "
                    f"Section content: {section.content[:100]}..."
                )

        # Check investigation section
        inv_sections = [s for s in sections if s.section_type == SectionType.INVESTIGATION]
        for section in inv_sections:
            if section.content.strip() and not investigations:
                warnings.append(
                    f"Investigation section detected but no investigations extracted. "
                    f"Section content: {section.content[:100]}..."
                )

        self.validation_warnings = warnings
        return warnings


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 6: SNOMED/ICD MAPPING IMPROVEMENTS
# ══════════════════════════════════════════════════════════════════════════════

def rank_snomed_concepts(
    concepts: list[dict],
    entity_category: EntityCategory,
    section: SectionType,
    text: str
) -> list[dict]:
    """
    Rank SNOMED concepts considering clinical context.

    Ranking factors:
    1. AWS Comprehend score
    2. Category alignment (diagnosis concepts for diagnoses, etc.)
    3. Specificity (more specific codes preferred)
    4. Semantic tag match
    """
    if not concepts:
        return []

    scored_concepts = []
    text_lower = text.lower()

    for concept in concepts:
        score = concept.get("Score", 0.5)
        desc = concept.get("Description", "").lower()
        code = concept.get("Code", "")

        # Boost/penalty based on category alignment
        category_boost = 0.0

        if entity_category == EntityCategory.DIAGNOSIS:
            if "(disorder)" in desc or "(disease)" in desc:
                category_boost = 0.15
            elif "(body structure)" in desc:
                category_boost = -0.5  # Strong penalty for anatomy
            elif "(procedure)" in desc:
                category_boost = -0.3  # Penalty for procedures

        elif entity_category == EntityCategory.PROCEDURE:
            if "(procedure)" in desc:
                category_boost = 0.15
            elif "(disorder)" in desc:
                category_boost = -0.3

        elif entity_category == EntityCategory.MEDICATION:
            if "(substance)" in desc or "(product)" in desc:
                category_boost = 0.15

        elif entity_category == EntityCategory.INVESTIGATION:
            if "(procedure)" in desc and any(x in desc for x in ["test", "examination", "measurement"]):
                category_boost = 0.10

        # Specificity bonus - longer descriptions tend to be more specific
        specificity_bonus = min(0.05, len(desc) / 1000)

        # Text match bonus
        text_match_bonus = 0.05 if text_lower in desc else 0.0

        final_score = score + category_boost + specificity_bonus + text_match_bonus
        final_score = max(0.0, min(1.0, final_score))  # Clamp to 0-1

        scored_concepts.append({
            **concept,
            "adjusted_score": final_score,
            "original_score": score,
            "category_boost": category_boost,
        })

    # Sort by adjusted score
    scored_concepts.sort(key=lambda x: x["adjusted_score"], reverse=True)
    return scored_concepts


def validate_snomed_mapping(
    code: str,
    description: str,
    entity_category: EntityCategory
) -> tuple[bool, str]:
    """
    Validate that a SNOMED code is appropriate for the entity category.

    Returns:
        Tuple of (is_valid, rejection_reason)
    """
    desc_lower = description.lower() if description else ""

    # Diagnosis-specific validation
    if entity_category == EntityCategory.DIAGNOSIS:
        if "(body structure)" in desc_lower:
            return False, "Anatomical structure cannot be diagnosis"
        if code in ClinicalValidationEngine.ANATOMY_SNOMED_CODES:
            return False, "Code is anatomical structure"
        if code in ClinicalValidationEngine.PROCEDURE_SNOMED_CODES:
            return False, "Code is procedure, not diagnosis"

    # Procedure-specific validation
    if entity_category == EntityCategory.PROCEDURE:
        if "(disorder)" in desc_lower:
            return False, "Disorder code used for procedure"

    # Medication-specific validation
    if entity_category == EntityCategory.MEDICATION:
        if "(procedure)" in desc_lower or "(disorder)" in desc_lower:
            return False, "Non-medication code used for medication"

    return True, ""


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 7: MAIN PROCESSING FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════

def process_clinical_entities(
    text: str,
    raw_entities: list[dict],
    ocr_confidence: float = 0.8
) -> tuple[list[ClinicalEntity], ConfidenceScore, list[str]]:
    """
    Main entry point for clinical entity processing.

    Takes raw entities from AWS Comprehend Medical and transforms them into
    validated, classified clinical entities with full context.

    Args:
        text: Full document text
        raw_entities: Entities from Comprehend Medical
        ocr_confidence: OCR/Textract confidence score

    Returns:
        Tuple of (validated_entities, confidence_score, validation_warnings)
    """
    # Step 1: Detect document structure
    sections = detect_document_sections(text)
    layout_confidence = 0.8 if sections else 0.5

    # Step 2: Process each entity with context
    entities = []
    extraction_confidences = []
    classification_confidences = []
    coding_confidences = []

    for raw in raw_entities:
        entity_text = raw.get("Text", "").strip()
        if not entity_text or len(entity_text) < 2:
            continue

        # Find entity position (approximate)
        pos = text.find(entity_text)
        if pos == -1:
            pos = 0

        # Get section context
        section = get_section_at_position(sections, pos)

        # Detect negation and temporal state
        negation = detect_negation_status(text, pos)
        temporal = detect_temporal_state(text, pos, section)

        # Get SNOMED concepts
        concepts = raw.get("SNOMEDCTConcepts", [])

        # Classify entity
        category, class_conf = classify_entity_category(
            entity_text,
            snomed_description=concepts[0].get("Description", "") if concepts else "",
            comprehend_category=raw.get("Category", ""),
            section=section
        )

        # Rank and select best SNOMED concept
        ranked_concepts = rank_snomed_concepts(concepts, category, section, entity_text)
        best_concept = ranked_concepts[0] if ranked_concepts else {}

        # Validate SNOMED mapping
        snomed_valid = True
        if best_concept:
            snomed_valid, _ = validate_snomed_mapping(
                best_concept.get("Code", ""),
                best_concept.get("Description", ""),
                category
            )

        # Calculate confidences
        raw_score = raw.get("Score", 0.5)
        extraction_conf = raw_score
        coding_conf = best_concept.get("adjusted_score", 0.0) if snomed_valid else 0.0

        # Create entity
        entity = ClinicalEntity(
            entity_id=str(uuid.uuid4())[:8],
            text=entity_text,
            category=category,
            temporal_state=temporal,
            negation_status=negation,
            section=section,
            start_pos=pos,
            end_pos=pos + len(entity_text),
            original_text=entity_text,
            context_window=text[max(0, pos-50):min(len(text), pos+50)],
            snomed_code=best_concept.get("Code", "") if snomed_valid else "",
            snomed_description=best_concept.get("Description", "") if snomed_valid else "",
            extraction_confidence=extraction_conf,
            classification_confidence=class_conf,
            coding_confidence=coding_conf,
            overall_confidence=(extraction_conf + class_conf + coding_conf) / 3,
        )

        entities.append(entity)
        extraction_confidences.append(extraction_conf)
        classification_confidences.append(class_conf)
        coding_confidences.append(coding_conf)

    # Step 3: Validate entities
    validator = ClinicalValidationEngine()
    validated_entities = validator.validate_entities(entities)

    # Step 4: Cross-validate with document structure
    warnings = validator.validate_consistency(validated_entities, sections)

    # Step 5: Calculate confidence scores
    confidence = ConfidenceScore(
        ocr_quality=ocr_confidence,
        layout_detection=layout_confidence,
        entity_extraction=sum(extraction_confidences) / len(extraction_confidences) if extraction_confidences else 0.5,
        entity_classification=sum(classification_confidences) / len(classification_confidences) if classification_confidences else 0.5,
        clinical_coding=sum(coding_confidences) / len(coding_confidences) if coding_confidences else 0.5,
        validation=len(validated_entities) / len(entities) if entities else 0.5,
    )
    confidence.compute_overall()

    return validated_entities, confidence, warnings


def categorize_entities_for_output(
    entities: list[ClinicalEntity]
) -> dict[str, list[dict]]:
    """
    Organize validated entities into output categories.

    Returns dict with:
    - diagnoses: Confirmed diagnoses
    - problems: Symptoms and findings
    - procedures: Therapeutic procedures
    - investigations: Diagnostic tests
    - medications: Drugs
    - follow_up: Follow-up actions
    - allergies: Known allergies
    """
    output = {
        "diagnoses": [],
        "problems": [],
        "procedures": [],
        "investigations": [],
        "medications": [],
        "follow_up": [],
        "allergies": [],
    }

    for entity in entities:
        if not entity.is_valid:
            continue

        entity_dict = entity.to_dict()

        if entity.category == EntityCategory.DIAGNOSIS:
            output["diagnoses"].append(entity_dict)
        elif entity.category in (EntityCategory.SYMPTOM, EntityCategory.OBSERVATION):
            output["problems"].append(entity_dict)
        elif entity.category == EntityCategory.PROCEDURE:
            # Distinguish therapeutic vs diagnostic procedures
            if entity.temporal_state == TemporalState.PENDING:
                output["investigations"].append(entity_dict)
            else:
                output["procedures"].append(entity_dict)
        elif entity.category == EntityCategory.INVESTIGATION:
            output["investigations"].append(entity_dict)
        elif entity.category == EntityCategory.MEDICATION:
            output["medications"].append(entity_dict)
        elif entity.category == EntityCategory.FOLLOW_UP:
            output["follow_up"].append(entity_dict)
        elif entity.category == EntityCategory.ALLERGY:
            output["allergies"].append(entity_dict)

    return output


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 8: INTEGRATION HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def convert_comprehend_to_clinical_entities(
    snomed_response: dict,
    text: str,
    ocr_confidence: float = 0.8
) -> dict:
    """
    Convert Comprehend Medical SNOMED response to validated clinical entities.

    This is the main integration point with the existing pipeline.

    Args:
        snomed_response: Response from run_comprehend_medical()
        text: Full document text
        ocr_confidence: Textract confidence

    Returns:
        Dict with categorized entities and confidence scores
    """
    # Get raw entities
    raw_entities = snomed_response.get("entities", [])

    # Process through clinical engine
    validated_entities, confidence, warnings = process_clinical_entities(
        text, raw_entities, ocr_confidence
    )

    # Categorize for output
    categorized = categorize_entities_for_output(validated_entities)

    # Build response
    return {
        "diagnoses": categorized["diagnoses"],
        "problems": categorized["problems"],
        "procedures": categorized["procedures"],
        "treatments": categorized["procedures"],  # Alias for compatibility
        "investigations": categorized["investigations"],
        "medications": categorized["medications"],
        "follow_up": categorized["follow_up"],
        "allergies": categorized["allergies"],
        "all_entities": [e.to_dict() for e in validated_entities],
        "confidence": confidence.to_dict(),
        "validation_warnings": warnings,
        "snomed_confidence": confidence.clinical_coding,
    }
