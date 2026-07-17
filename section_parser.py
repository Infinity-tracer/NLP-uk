"""
Section-Aware Document Parser

Recognizes NHS clinical document headings and assigns context to entities.

Supported sections:
- Presenting Complaint / Chief Complaint
- History of Presenting Complaint (HPC)
- Past Medical History (PMH)
- Medication / Drug History
- Social History
- Family History
- Examination / On Examination
- Investigations / Results
- Diagnosis / Impression
- Treatment / Management / Plan
- Discharge / Discharge Summary
- Advice / Patient Advice
- GP Actions / Actions for GP
- Follow-up / Review

Entities inherit context from their section:
- "Asthma" under PMH → Historical Disease (not Current Diagnosis)
- "Chest pain" under HPC → Current Symptom
- "Diabetes" under FHx → Family History
"""

import re
from dataclasses import dataclass, asdict, field
from typing import List, Dict, Optional, Tuple, Set
from enum import Enum


class SectionType(Enum):
    """Clinical document section types"""
    PRESENTING_COMPLAINT = "presenting_complaint"
    HISTORY_PRESENTING_COMPLAINT = "history_presenting_complaint"
    PAST_MEDICAL_HISTORY = "past_medical_history"
    SURGICAL_HISTORY = "surgical_history"
    MEDICATION = "medication"
    ALLERGIES = "allergies"
    SOCIAL_HISTORY = "social_history"
    FAMILY_HISTORY = "family_history"
    EXAMINATION = "examination"
    INVESTIGATIONS = "investigations"
    DIAGNOSIS = "diagnosis"
    DIFFERENTIAL_DIAGNOSIS = "differential_diagnosis"
    TREATMENT = "treatment"
    DISCHARGE = "discharge"
    ADVICE = "advice"
    GP_ACTIONS = "gp_actions"
    FOLLOW_UP = "follow_up"
    REFERRAL = "referral"
    PROGNOSIS = "prognosis"
    UNKNOWN = "unknown"
    HEADER = "header"  # Document header (patient info, dates)


class EntityContext(Enum):
    """Context for entities based on section"""
    CURRENT_SYMPTOM = "current_symptom"
    CURRENT_DIAGNOSIS = "current_diagnosis"
    HISTORICAL_DISEASE = "historical_disease"
    PAST_SURGERY = "past_surgery"
    CURRENT_MEDICATION = "current_medication"
    HISTORICAL_MEDICATION = "historical_medication"
    ALLERGY = "allergy"
    SOCIAL_FACTOR = "social_factor"
    FAMILY_HISTORY = "family_history"
    EXAMINATION_FINDING = "examination_finding"
    INVESTIGATION_RESULT = "investigation_result"
    TREATMENT_PLAN = "treatment_plan"
    DISCHARGE_MEDICATION = "discharge_medication"
    PATIENT_ADVICE = "patient_advice"
    GP_ACTION = "gp_action"
    FOLLOW_UP_PLAN = "follow_up_plan"
    SUSPECTED_DIAGNOSIS = "suspected_diagnosis"
    UNKNOWN = "unknown"


@dataclass
class Section:
    """A section of a clinical document"""
    section_type: str
    heading: str              # Original heading text
    start_line: int           # Line number where section starts
    end_line: int             # Line number where section ends
    content: str              # Section content (excluding heading)
    confidence: float         # Confidence in section detection


@dataclass
class SectionEntity:
    """An entity with section context"""
    text: str
    section_type: str
    entity_context: str       # Derived context based on section
    temporal_state: str       # current/historical/resolved/etc.
    assertion: str            # present/absent/possible/etc.
    line_number: int
    section_heading: str
    raw_line: str
    confidence: float


@dataclass
class ParsedDocument:
    """A fully parsed clinical document"""
    sections: List[Section]
    entities: List[SectionEntity]
    section_order: List[str]  # Order of sections found
    document_type: Optional[str]  # Letter type if detected
    stats: Dict[str, int]     # Section and entity counts


# Section heading patterns with variations
SECTION_PATTERNS = {
    SectionType.PRESENTING_COMPLAINT: [
        r"presenting\s*complaint[s]?",
        r"chief\s*complaint[s]?",
        r"reason\s*for\s*(?:attendance|admission|referral|visit)",
        r"pc[:\s]",
        r"c/o[:\s]",
        r"complaining\s*of",
        r"presented\s*with",
        r"referred\s*(?:with|for)",
    ],
    SectionType.HISTORY_PRESENTING_COMPLAINT: [
        r"history\s*of\s*presenting\s*complaint",
        r"hpc[:\s]",
        r"h[/.]?p[/.]?c[:\s]",
        r"history\s*of\s*present\s*illness",
        r"hpi[:\s]",
        r"clinical\s*history",
        r"history[:\s]$",
        r"presenting\s*history",
    ],
    SectionType.PAST_MEDICAL_HISTORY: [
        r"past\s*medical\s*history",
        r"pmh[:\s]",
        r"p[/.]?m[/.]?h[:\s]",
        r"pmhx[:\s]",
        r"medical\s*history",
        r"background\s*(?:history|medical)",
        r"co-?morbidities",
        r"comorbidities",
        r"known\s*(?:to\s*have|conditions?)",
        r"previous\s*(?:medical\s*)?history",
    ],
    SectionType.SURGICAL_HISTORY: [
        r"past\s*surgical\s*history",
        r"psh[:\s]",
        r"surgical\s*history",
        r"previous\s*(?:surgery|surgeries|operations?)",
        r"operations?[:\s]",
    ],
    SectionType.MEDICATION: [
        r"medications?[:\s]",
        r"current\s*medications?",
        r"drug\s*history",
        r"dh[:\s]",
        r"d[/.]?h[:\s]",
        r"regular\s*medications?",
        r"medicines?[:\s]",
        r"prescription[s]?[:\s]",
        r"on\s*admission\s*medications?",
        r"pre[- ]?admission\s*medications?",
        r"home\s*medications?",
        r"discharge\s*medications?",
        r"ttah?\s*medications?",  # To take away/home
        r"medications?\s*on\s*discharge",
    ],
    SectionType.ALLERGIES: [
        r"allergies[:\s]",
        r"allergy[:\s]",
        r"drug\s*allergies",
        r"adverse\s*(?:drug\s*)?reactions?",
        r"nkda",  # No known drug allergies
        r"sensitivities",
    ],
    SectionType.SOCIAL_HISTORY: [
        r"social\s*history",
        r"sh[:\s]",
        r"s[/.]?h[:\s]",
        r"shx[:\s]",
        r"social\s*circumstances",
        r"occupational\s*history",
        r"smoking[:\s]",
        r"alcohol[:\s]",
        r"living\s*(?:situation|circumstances|arrangements?)",
        r"functional\s*(?:status|history)",
        r"mobility[:\s]",
        r"baseline\s*function",
    ],
    SectionType.FAMILY_HISTORY: [
        r"family\s*history",
        r"fh[:\s]",
        r"f[/.]?h[:\s]",
        r"fhx[:\s]",
        r"family\s*medical\s*history",
    ],
    SectionType.EXAMINATION: [
        r"examination[:\s]",
        r"on\s*examination",
        r"o/?e[:\s]",
        r"physical\s*exam(?:ination)?",
        r"clinical\s*exam(?:ination)?",
        r"findings?[:\s]$",
        r"exam[:\s]$",
        r"systems?\s*review",
        r"review\s*of\s*systems",
        r"observations?[:\s]",
        r"vital\s*signs?[:\s]",
    ],
    SectionType.INVESTIGATIONS: [
        r"investigations?[:\s]",
        r"results?[:\s]",
        r"test\s*results?",
        r"laboratory\s*(?:results?|findings?)",
        r"lab\s*(?:results?|findings?)",
        r"bloods?[:\s]",
        r"imaging[:\s]",
        r"radiology[:\s]",
        r"ecg[:\s]",
        r"x[- ]?ray[:\s]",
    ],
    SectionType.DIAGNOSIS: [
        r"diagnosis[:\s]",
        r"diagnoses[:\s]",
        r"dx[:\s]",
        r"impression[:\s]",
        r"assessment[:\s]",
        r"conclusion[s]?[:\s]",
        r"working\s*diagnosis",
        r"final\s*diagnosis",
        r"primary\s*diagnosis",
        r"secondary\s*diagnos[ie]s",
    ],
    SectionType.DIFFERENTIAL_DIAGNOSIS: [
        r"differential\s*diagnos[ie]s",
        r"ddx[:\s]",
        r"differentials?[:\s]",
        r"possible\s*diagnos[ie]s",
    ],
    SectionType.TREATMENT: [
        r"treatment[:\s]",
        r"management[:\s]",
        r"plan[:\s]",
        r"rx[:\s]",
        r"therapy[:\s]",
        r"intervention[s]?[:\s]",
        r"procedure[s]?[:\s]$",
        r"course\s*(?:of\s*)?treatment",
        r"inpatient\s*(?:course|stay|management)",
        r"clinical\s*course",
        r"hospital\s*course",
    ],
    SectionType.DISCHARGE: [
        r"discharge[:\s]",
        r"discharge\s*summary",
        r"discharge\s*plan",
        r"discharge\s*(?:diagnosis|diagnoses)",
        r"discharge\s*destination",
        r"disposition[:\s]",
        r"outcome[:\s]",
    ],
    SectionType.ADVICE: [
        r"advice[:\s]",
        r"patient\s*advice",
        r"advice\s*(?:given|to\s*patient)",
        r"patient\s*information",
        r"patient\s*education",
        r"safety\s*net(?:ting)?",
        r"red\s*flag[s]?",
        r"warning\s*signs?",
        r"worsening\s*advice",
        r"when\s*to\s*(?:seek\s*help|return|re-?attend)",
    ],
    SectionType.GP_ACTIONS: [
        r"gp\s*actions?",
        r"actions?\s*for\s*gp",
        r"gp\s*(?:to\s*)?(?:please|kindly)?",
        r"primary\s*care\s*actions?",
        r"for\s*(?:the\s*)?gp",
        r"request(?:ed)?\s*(?:of|from)\s*gp",
        r"gp\s*follow[- ]?up",
        r"(?:please|kindly)\s*(?:arrange|book|refer)",
    ],
    SectionType.FOLLOW_UP: [
        r"follow[- ]?up[:\s]",
        r"f/?u[:\s]",
        r"review[:\s]",
        r"outpatient\s*(?:follow[- ]?up|appointment|review)",
        r"clinic\s*(?:follow[- ]?up|appointment|review)",
        r"next\s*(?:appointment|review)",
        r"return\s*(?:visit|appointment)",
        r"scheduled\s*(?:follow[- ]?up|review)",
    ],
    SectionType.REFERRAL: [
        r"referral[s]?[:\s]",
        r"referred\s*to",
        r"onward\s*referral",
        r"specialist\s*referral",
    ],
    SectionType.PROGNOSIS: [
        r"prognosis[:\s]",
        r"expected\s*outcome",
        r"outlook[:\s]",
    ],
}

# Map section types to entity contexts
SECTION_TO_CONTEXT = {
    SectionType.PRESENTING_COMPLAINT: EntityContext.CURRENT_SYMPTOM,
    SectionType.HISTORY_PRESENTING_COMPLAINT: EntityContext.CURRENT_SYMPTOM,
    SectionType.PAST_MEDICAL_HISTORY: EntityContext.HISTORICAL_DISEASE,
    SectionType.SURGICAL_HISTORY: EntityContext.PAST_SURGERY,
    SectionType.MEDICATION: EntityContext.CURRENT_MEDICATION,
    SectionType.ALLERGIES: EntityContext.ALLERGY,
    SectionType.SOCIAL_HISTORY: EntityContext.SOCIAL_FACTOR,
    SectionType.FAMILY_HISTORY: EntityContext.FAMILY_HISTORY,
    SectionType.EXAMINATION: EntityContext.EXAMINATION_FINDING,
    SectionType.INVESTIGATIONS: EntityContext.INVESTIGATION_RESULT,
    SectionType.DIAGNOSIS: EntityContext.CURRENT_DIAGNOSIS,
    SectionType.DIFFERENTIAL_DIAGNOSIS: EntityContext.SUSPECTED_DIAGNOSIS,
    SectionType.TREATMENT: EntityContext.TREATMENT_PLAN,
    SectionType.DISCHARGE: EntityContext.DISCHARGE_MEDICATION,
    SectionType.ADVICE: EntityContext.PATIENT_ADVICE,
    SectionType.GP_ACTIONS: EntityContext.GP_ACTION,
    SectionType.FOLLOW_UP: EntityContext.FOLLOW_UP_PLAN,
    SectionType.REFERRAL: EntityContext.FOLLOW_UP_PLAN,
    SectionType.PROGNOSIS: EntityContext.CURRENT_DIAGNOSIS,
    SectionType.UNKNOWN: EntityContext.UNKNOWN,
    SectionType.HEADER: EntityContext.UNKNOWN,
}

# Map section types to temporal states
SECTION_TO_TEMPORAL = {
    SectionType.PRESENTING_COMPLAINT: "current",
    SectionType.HISTORY_PRESENTING_COMPLAINT: "current",
    SectionType.PAST_MEDICAL_HISTORY: "historical",
    SectionType.SURGICAL_HISTORY: "historical",
    SectionType.MEDICATION: "current",
    SectionType.ALLERGIES: "current",
    SectionType.SOCIAL_HISTORY: "current",
    SectionType.FAMILY_HISTORY: "historical",
    SectionType.EXAMINATION: "current",
    SectionType.INVESTIGATIONS: "current",
    SectionType.DIAGNOSIS: "current",
    SectionType.DIFFERENTIAL_DIAGNOSIS: "suspected",
    SectionType.TREATMENT: "current",
    SectionType.DISCHARGE: "current",
    SectionType.ADVICE: "current",
    SectionType.GP_ACTIONS: "current",
    SectionType.FOLLOW_UP: "current",
    SectionType.REFERRAL: "current",
    SectionType.PROGNOSIS: "current",
    SectionType.UNKNOWN: "unknown",
    SectionType.HEADER: "unknown",
}

# Map section types to assertion status
SECTION_TO_ASSERTION = {
    SectionType.PRESENTING_COMPLAINT: "present",
    SectionType.HISTORY_PRESENTING_COMPLAINT: "present",
    SectionType.PAST_MEDICAL_HISTORY: "historical",
    SectionType.SURGICAL_HISTORY: "historical",
    SectionType.MEDICATION: "present",
    SectionType.ALLERGIES: "present",
    SectionType.SOCIAL_HISTORY: "present",
    SectionType.FAMILY_HISTORY: "family_history",
    SectionType.EXAMINATION: "present",
    SectionType.INVESTIGATIONS: "present",
    SectionType.DIAGNOSIS: "present",
    SectionType.DIFFERENTIAL_DIAGNOSIS: "possible",
    SectionType.TREATMENT: "present",
    SectionType.DISCHARGE: "present",
    SectionType.ADVICE: "present",
    SectionType.GP_ACTIONS: "present",
    SectionType.FOLLOW_UP: "present",
    SectionType.REFERRAL: "present",
    SectionType.PROGNOSIS: "present",
    SectionType.UNKNOWN: "present",
    SectionType.HEADER: "present",
}


class SectionParser:
    """
    Section-aware clinical document parser.

    Recognizes NHS document headings and assigns context to entities
    based on which section they appear in.
    """

    def __init__(self):
        self.section_patterns = SECTION_PATTERNS
        self.section_to_context = SECTION_TO_CONTEXT
        self.section_to_temporal = SECTION_TO_TEMPORAL
        self.section_to_assertion = SECTION_TO_ASSERTION

        self._compile_patterns()

    def _compile_patterns(self):
        """Compile regex patterns for section detection"""

        self.compiled_patterns: Dict[SectionType, List[re.Pattern]] = {}

        for section_type, patterns in self.section_patterns.items():
            self.compiled_patterns[section_type] = [
                re.compile(r'^\s*[-•*]?\s*' + pattern, re.IGNORECASE | re.MULTILINE)
                for pattern in patterns
            ]

        # Pattern for detecting any heading-like line
        self.heading_pattern = re.compile(
            r'^[\s\-•*]*([A-Z][A-Za-z\s/]+)[:\s]*$|'  # "Heading:" or "Heading"
            r'^[\s\-•*]*([A-Z]{2,})[:\s]*$',          # "PMH:" (abbreviations)
            re.MULTILINE
        )

    def parse(self, text: str) -> ParsedDocument:
        """
        Parse a clinical document into sections.

        Args:
            text: Full clinical document text

        Returns:
            ParsedDocument with sections and context-aware entities
        """
        lines = text.split('\n')
        sections = []
        current_section = None
        current_start = 0
        current_content_lines = []
        section_order = []

        for i, line in enumerate(lines):
            # Check if this line is a section heading
            section_type, confidence = self._detect_section(line)

            if section_type and section_type != SectionType.UNKNOWN:
                # Save previous section
                if current_section:
                    sections.append(Section(
                        section_type=current_section.value,
                        heading=lines[current_start].strip(),
                        start_line=current_start,
                        end_line=i - 1,
                        content='\n'.join(current_content_lines),
                        confidence=0.85
                    ))
                    section_order.append(current_section.value)

                # Start new section
                current_section = section_type
                current_start = i
                current_content_lines = []
            else:
                # Add line to current section content
                if line.strip():
                    current_content_lines.append(line)

        # Save final section
        if current_section:
            sections.append(Section(
                section_type=current_section.value,
                heading=lines[current_start].strip() if current_start < len(lines) else "",
                start_line=current_start,
                end_line=len(lines) - 1,
                content='\n'.join(current_content_lines),
                confidence=0.85
            ))
            section_order.append(current_section.value)

        # If no sections found, treat entire document as unknown
        if not sections:
            sections.append(Section(
                section_type=SectionType.UNKNOWN.value,
                heading="",
                start_line=0,
                end_line=len(lines) - 1,
                content=text,
                confidence=0.5
            ))

        # Build stats
        stats = {
            "total_sections": len(sections),
            "total_lines": len(lines),
        }
        for section in sections:
            key = f"section_{section.section_type}"
            stats[key] = stats.get(key, 0) + 1

        return ParsedDocument(
            sections=sections,
            entities=[],  # Entities added separately
            section_order=section_order,
            document_type=self._detect_document_type(text, sections),
            stats=stats
        )

    def _detect_section(self, line: str) -> Tuple[Optional[SectionType], float]:
        """Detect if a line is a section heading"""

        line = line.strip()
        if not line:
            return None, 0.0

        # Skip very long lines (unlikely to be headings)
        if len(line) > 100:
            return None, 0.0

        # Skip lines that look like data rather than headings
        # e.g., "ECG: ST elevation V2-V4" has data after the colon
        if ':' in line:
            parts = line.split(':', 1)
            heading_part = parts[0].strip()
            data_part = parts[1].strip() if len(parts) > 1 else ""

            # If there's substantial data after colon, it's probably not a section heading
            # Section headings are like "Past Medical History:" with nothing after
            # Data lines are like "ECG: ST elevation V2-V4"
            if data_part and len(data_part) > 5:
                # Check if heading part is a known short abbreviation that IS a section
                known_section_abbrevs = {'pmh', 'hpc', 'fh', 'sh', 'dh', 'pc', 'o/e', 'rx'}
                if heading_part.lower() not in known_section_abbrevs:
                    return None, 0.0

        # Check against compiled patterns
        best_match = None
        best_confidence = 0.0

        for section_type, patterns in self.compiled_patterns.items():
            for pattern in patterns:
                if pattern.match(line):
                    # Longer pattern matches are more confident
                    confidence = min(0.95, 0.7 + len(pattern.pattern) / 100)
                    if confidence > best_confidence:
                        best_match = section_type
                        best_confidence = confidence
                    break

        return best_match, best_confidence

    def _detect_document_type(self, text: str, sections: List[Section]) -> Optional[str]:
        """Detect the type of clinical document"""

        text_lower = text.lower()

        # Check for discharge summary indicators
        if any(s.section_type == SectionType.DISCHARGE.value for s in sections):
            return "discharge_summary"
        if "discharge summary" in text_lower:
            return "discharge_summary"

        # Check for clinic letter indicators
        if "clinic" in text_lower and "letter" in text_lower:
            return "clinic_letter"
        if "outpatient" in text_lower:
            return "clinic_letter"

        # Check for ED/A&E
        if "emergency department" in text_lower or "a&e" in text_lower:
            return "ed_report"

        # Check for referral
        if "referral" in text_lower:
            return "referral_letter"

        # Check for GP letter
        if "dear doctor" in text_lower or "gp surgery" in text_lower:
            return "gp_letter"

        return None

    def get_entity_context(self, entity_text: str, line_number: int,
                          parsed_doc: ParsedDocument) -> SectionEntity:
        """
        Get context for an entity based on which section it appears in.

        Args:
            entity_text: The entity text
            line_number: Line number where entity was found
            parsed_doc: The parsed document

        Returns:
            SectionEntity with context information
        """
        # Find which section contains this line
        section = self._find_section_for_line(line_number, parsed_doc.sections)

        if section:
            section_type = SectionType(section.section_type)
            entity_context = self.section_to_context.get(
                section_type, EntityContext.UNKNOWN
            )
            temporal_state = self.section_to_temporal.get(section_type, "unknown")
            assertion = self.section_to_assertion.get(section_type, "present")

            return SectionEntity(
                text=entity_text,
                section_type=section.section_type,
                entity_context=entity_context.value,
                temporal_state=temporal_state,
                assertion=assertion,
                line_number=line_number,
                section_heading=section.heading,
                raw_line="",
                confidence=section.confidence
            )

        return SectionEntity(
            text=entity_text,
            section_type=SectionType.UNKNOWN.value,
            entity_context=EntityContext.UNKNOWN.value,
            temporal_state="unknown",
            assertion="present",
            line_number=line_number,
            section_heading="",
            raw_line="",
            confidence=0.5
        )

    def _find_section_for_line(self, line_number: int,
                               sections: List[Section]) -> Optional[Section]:
        """Find which section contains a given line"""

        for section in sections:
            if section.start_line <= line_number <= section.end_line:
                return section

        return None

    def classify_entity(self, entity_text: str, section_type: str) -> Dict:
        """
        Classify an entity based on section context.

        Args:
            entity_text: The entity text
            section_type: The section type string

        Returns:
            Dictionary with classification info
        """
        try:
            section_enum = SectionType(section_type)
        except ValueError:
            section_enum = SectionType.UNKNOWN

        entity_context = self.section_to_context.get(section_enum, EntityContext.UNKNOWN)
        temporal_state = self.section_to_temporal.get(section_enum, "unknown")
        assertion = self.section_to_assertion.get(section_enum, "present")

        return {
            "entity": entity_text,
            "section_type": section_type,
            "entity_context": entity_context.value,
            "temporal_state": temporal_state,
            "assertion": assertion,
            "is_current": temporal_state == "current",
            "is_historical": temporal_state == "historical",
            "is_family_history": section_enum == SectionType.FAMILY_HISTORY,
        }

    def get_section_summary(self, parsed_doc: ParsedDocument) -> Dict:
        """Get a summary of sections in the document"""

        summary = {
            "document_type": parsed_doc.document_type,
            "section_count": len(parsed_doc.sections),
            "section_order": parsed_doc.section_order,
            "sections": {}
        }

        for section in parsed_doc.sections:
            summary["sections"][section.section_type] = {
                "heading": section.heading,
                "line_count": section.end_line - section.start_line + 1,
                "char_count": len(section.content),
                "confidence": section.confidence,
            }

        return summary


def parse_document(text: str) -> Dict:
    """
    Convenience function to parse a clinical document.

    Args:
        text: Clinical document text

    Returns:
        Dictionary with parsed sections and metadata
    """
    parser = SectionParser()
    parsed = parser.parse(text)

    return {
        "sections": [asdict(s) for s in parsed.sections],
        "section_order": parsed.section_order,
        "document_type": parsed.document_type,
        "stats": parsed.stats
    }


def get_entity_context(entity_text: str, section_type: str) -> Dict:
    """
    Get context classification for an entity based on section.

    Args:
        entity_text: The entity text (e.g., "Asthma")
        section_type: The section type (e.g., "past_medical_history")

    Returns:
        Dictionary with context classification
    """
    parser = SectionParser()
    return parser.classify_entity(entity_text, section_type)


if __name__ == "__main__":
    # Test the parser
    test_document = """
    DISCHARGE SUMMARY

    Patient: John Smith
    DOB: 15/03/1965
    NHS Number: 123 456 7890
    Admission Date: 10/07/2024
    Discharge Date: 14/07/2024

    Presenting Complaint:
    Chest pain and shortness of breath for 2 days

    History of Presenting Complaint:
    Mr Smith presented with central crushing chest pain radiating to left arm.
    Associated with sweating and nausea. Pain score 8/10 on arrival.
    Symptoms started at rest while watching television.

    Past Medical History:
    - Hypertension (diagnosed 2015)
    - Type 2 Diabetes Mellitus
    - Asthma - childhood, resolved
    - Appendicectomy 1990

    Medications on Admission:
    - Amlodipine 10mg OD
    - Metformin 500mg BD
    - Ramipril 5mg OD

    Allergies:
    NKDA

    Social History:
    Ex-smoker (quit 2010), 20 pack-years
    Alcohol: occasional
    Lives with wife, independent

    Family History:
    Father: MI aged 55
    Mother: Type 2 DM

    On Examination:
    Alert and oriented
    HR 98 bpm, BP 145/92, RR 18, SpO2 97% on air
    Heart sounds normal, no murmurs
    Chest clear

    Investigations:
    ECG: ST elevation V2-V4
    Troponin: 850 (elevated)
    FBC: Normal
    U&E: Cr 95, eGFR 65
    CXR: Clear lung fields

    Diagnosis:
    1. STEMI (anterior)
    2. Type 2 Diabetes Mellitus
    3. Hypertension

    Treatment:
    - Emergency PCI to LAD - successful
    - Dual antiplatelet therapy initiated
    - Cardiac rehabilitation referral

    Discharge Medications:
    - Aspirin 75mg OD (NEW)
    - Clopidogrel 75mg OD (NEW)
    - Atorvastatin 80mg ON (NEW)
    - Bisoprolol 2.5mg OD (NEW)
    - Ramipril 5mg OD (CONTINUE)
    - Metformin 500mg BD (CONTINUE)
    - Amlodipine 10mg OD (CONTINUE)
    - GTN spray PRN (NEW)

    Advice:
    - Avoid driving for 4 weeks
    - Attend cardiac rehabilitation
    - Return if chest pain recurs
    - Red flags: severe chest pain, breathlessness, collapse

    GP Actions:
    1. Please check BP in 2 weeks
    2. Monitor HbA1c in 3 months
    3. Refer to diabetic eye screening if not already enrolled

    Follow-up:
    - Cardiology clinic in 6 weeks
    - Cardiac rehabilitation starting 15/07/2024
    """

    parser = SectionParser()
    parsed = parser.parse(test_document)

    print("=" * 80)
    print("SECTION PARSER TEST")
    print("=" * 80)

    print(f"\nDocument Type: {parsed.document_type}")
    print(f"Total Sections: {len(parsed.sections)}")
    print(f"\nSection Order: {' -> '.join(parsed.section_order)}")

    print("\n" + "-" * 80)
    print("DETECTED SECTIONS:")
    print("-" * 80)

    for section in parsed.sections:
        content_preview = section.content[:100].replace('\n', ' ')
        if len(section.content) > 100:
            content_preview += "..."
        print(f"\n[{section.section_type.upper()}] (lines {section.start_line}-{section.end_line})")
        print(f"  Heading: {section.heading}")
        print(f"  Content: {content_preview}")

    print("\n" + "-" * 80)
    print("ENTITY CONTEXT TEST:")
    print("-" * 80)

    test_entities = [
        ("Asthma", "past_medical_history"),
        ("Chest pain", "presenting_complaint"),
        ("Diabetes", "family_history"),
        ("Hypertension", "diagnosis"),
        ("Amlodipine 10mg", "medication"),
        ("ST elevation", "investigations"),
        ("PCI to LAD", "treatment"),
        ("Appendicectomy", "surgical_history"),
    ]

    for entity, section in test_entities:
        context = parser.classify_entity(entity, section)
        temporal = "CURRENT" if context["is_current"] else \
                   "HISTORICAL" if context["is_historical"] else \
                   "FAMILY" if context["is_family_history"] else "OTHER"
        print(f"\n  '{entity}' under {section.upper()}")
        print(f"    -> Context: {context['entity_context']}")
        print(f"    -> Temporal: {temporal}")
        print(f"    -> Assertion: {context['assertion']}")
