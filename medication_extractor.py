"""
Structured Medication Extraction Engine

Extracts medication information with structured fields:
- Drug Name
- Strength
- Dose
- Route
- Frequency
- Duration
- Status

Supports UK prescribing abbreviations:
- OD (once daily)
- BD (twice daily)
- TDS (three times daily)
- QDS (four times daily)
- PRN (as needed)
- STAT (immediately)
"""

import re
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Tuple
from enum import Enum


class MedicationStatus(Enum):
    """Status of medication"""
    CURRENT = "current"
    DISCONTINUED = "discontinued"
    NEW = "new"
    CHANGED = "changed"
    ON_HOLD = "on_hold"
    PRN = "prn"
    UNKNOWN = "unknown"


class RouteOfAdministration(Enum):
    """Route of drug administration"""
    ORAL = "oral"
    SUBLINGUAL = "sublingual"
    BUCCAL = "buccal"
    TOPICAL = "topical"
    TRANSDERMAL = "transdermal"
    INHALATION = "inhalation"
    NEBULISED = "nebulised"
    NASAL = "nasal"
    OPHTHALMIC = "ophthalmic"
    OTIC = "otic"
    RECTAL = "rectal"
    VAGINAL = "vaginal"
    INTRAVENOUS = "intravenous"
    INTRAMUSCULAR = "intramuscular"
    SUBCUTANEOUS = "subcutaneous"
    INTRADERMAL = "intradermal"
    INTRATHECAL = "intrathecal"
    EPIDURAL = "epidural"
    PEG = "peg"
    NG = "ng"
    UNKNOWN = "unknown"


@dataclass
class StructuredMedication:
    """Structured medication object"""
    drug_name: str
    strength: Optional[str] = None
    dose: Optional[str] = None
    route: Optional[str] = None
    frequency: Optional[str] = None
    frequency_code: Optional[str] = None  # Original abbreviation (OD, BD, etc.)
    duration: Optional[str] = None
    status: str = "current"
    form: Optional[str] = None  # tablet, capsule, injection, etc.
    instructions: Optional[str] = None  # Additional instructions
    indication: Optional[str] = None  # What it's prescribed for
    raw_text: str = ""  # Original text
    confidence: float = 0.0

    def to_dict(self) -> Dict:
        return asdict(self)


# UK Frequency Abbreviations
UK_FREQUENCY_ABBREVIATIONS = {
    # Latin abbreviations
    "od": ("once daily", "OD"),
    "o.d.": ("once daily", "OD"),
    "o/d": ("once daily", "OD"),
    "om": ("every morning", "OM"),
    "o.m.": ("every morning", "OM"),
    "mane": ("every morning", "OM"),
    "on": ("every night", "ON"),
    "o.n.": ("every night", "ON"),
    "nocte": ("at night", "ON"),
    "bd": ("twice daily", "BD"),
    "b.d.": ("twice daily", "BD"),
    "b/d": ("twice daily", "BD"),
    "bid": ("twice daily", "BD"),
    "tds": ("three times daily", "TDS"),
    "t.d.s.": ("three times daily", "TDS"),
    "t/d/s": ("three times daily", "TDS"),
    "tid": ("three times daily", "TDS"),
    "qds": ("four times daily", "QDS"),
    "q.d.s.": ("four times daily", "QDS"),
    "qid": ("four times daily", "QDS"),
    "prn": ("as required", "PRN"),
    "p.r.n.": ("as required", "PRN"),
    "sos": ("if needed", "PRN"),
    "stat": ("immediately", "STAT"),
    "s.t.a.t.": ("immediately", "STAT"),

    # Hourly
    "q2h": ("every 2 hours", "Q2H"),
    "q4h": ("every 4 hours", "Q4H"),
    "q6h": ("every 6 hours", "Q6H"),
    "q8h": ("every 8 hours", "Q8H"),
    "q12h": ("every 12 hours", "Q12H"),
    "2hrly": ("every 2 hours", "Q2H"),
    "4hrly": ("every 4 hours", "Q4H"),
    "6hrly": ("every 6 hours", "Q6H"),
    "8hrly": ("every 8 hours", "Q8H"),
    "4 hourly": ("every 4 hours", "Q4H"),
    "6 hourly": ("every 6 hours", "Q6H"),

    # Weekly
    "weekly": ("once weekly", "WEEKLY"),
    "wkly": ("once weekly", "WEEKLY"),
    "once weekly": ("once weekly", "WEEKLY"),
    "twice weekly": ("twice weekly", "2X WEEKLY"),
    "biw": ("twice weekly", "2X WEEKLY"),
    "tiw": ("three times weekly", "3X WEEKLY"),

    # With meals
    "ac": ("before meals", "AC"),
    "a.c.": ("before meals", "AC"),
    "pc": ("after meals", "PC"),
    "p.c.": ("after meals", "PC"),
    "cc": ("with food", "CC"),
    "c.c.": ("with food", "CC"),
    "with food": ("with food", "CC"),

    # Other
    "alternate days": ("every other day", "ALT"),
    "alt days": ("every other day", "ALT"),
    "eod": ("every other day", "ALT"),
    "continuous": ("continuous", "CONT"),
}

# Route abbreviations
ROUTE_ABBREVIATIONS = {
    # Oral
    "po": RouteOfAdministration.ORAL,
    "p.o.": RouteOfAdministration.ORAL,
    "oral": RouteOfAdministration.ORAL,
    "orally": RouteOfAdministration.ORAL,
    "by mouth": RouteOfAdministration.ORAL,

    # Sublingual
    "sl": RouteOfAdministration.SUBLINGUAL,
    "s.l.": RouteOfAdministration.SUBLINGUAL,
    "sublingual": RouteOfAdministration.SUBLINGUAL,
    "under tongue": RouteOfAdministration.SUBLINGUAL,

    # Topical
    "top": RouteOfAdministration.TOPICAL,
    "topical": RouteOfAdministration.TOPICAL,
    "topically": RouteOfAdministration.TOPICAL,
    "apply": RouteOfAdministration.TOPICAL,

    # Inhalation
    "inh": RouteOfAdministration.INHALATION,
    "inhaled": RouteOfAdministration.INHALATION,
    "inhalation": RouteOfAdministration.INHALATION,
    "via inhaler": RouteOfAdministration.INHALATION,
    "puff": RouteOfAdministration.INHALATION,
    "puffs": RouteOfAdministration.INHALATION,

    # Nebulised
    "neb": RouteOfAdministration.NEBULISED,
    "nebs": RouteOfAdministration.NEBULISED,
    "nebulised": RouteOfAdministration.NEBULISED,
    "nebulized": RouteOfAdministration.NEBULISED,
    "via nebuliser": RouteOfAdministration.NEBULISED,

    # Nasal
    "nasal": RouteOfAdministration.NASAL,
    "intranasal": RouteOfAdministration.NASAL,
    "in": RouteOfAdministration.NASAL,
    "i.n.": RouteOfAdministration.NASAL,

    # Ophthalmic
    "od": RouteOfAdministration.OPHTHALMIC,  # right eye (context-dependent)
    "os": RouteOfAdministration.OPHTHALMIC,  # left eye
    "ou": RouteOfAdministration.OPHTHALMIC,  # both eyes
    "eye": RouteOfAdministration.OPHTHALMIC,
    "eyes": RouteOfAdministration.OPHTHALMIC,
    "ophthalmic": RouteOfAdministration.OPHTHALMIC,
    "eye drops": RouteOfAdministration.OPHTHALMIC,
    "drops": RouteOfAdministration.OPHTHALMIC,

    # Otic
    "ear": RouteOfAdministration.OTIC,
    "ears": RouteOfAdministration.OTIC,
    "otic": RouteOfAdministration.OTIC,
    "ear drops": RouteOfAdministration.OTIC,

    # Rectal
    "pr": RouteOfAdministration.RECTAL,
    "p.r.": RouteOfAdministration.RECTAL,
    "rectal": RouteOfAdministration.RECTAL,
    "rectally": RouteOfAdministration.RECTAL,
    "per rectum": RouteOfAdministration.RECTAL,

    # Vaginal
    "pv": RouteOfAdministration.VAGINAL,
    "p.v.": RouteOfAdministration.VAGINAL,
    "vaginal": RouteOfAdministration.VAGINAL,
    "vaginally": RouteOfAdministration.VAGINAL,
    "per vagina": RouteOfAdministration.VAGINAL,

    # Intravenous
    "iv": RouteOfAdministration.INTRAVENOUS,
    "i.v.": RouteOfAdministration.INTRAVENOUS,
    "intravenous": RouteOfAdministration.INTRAVENOUS,
    "intravenously": RouteOfAdministration.INTRAVENOUS,

    # Intramuscular
    "im": RouteOfAdministration.INTRAMUSCULAR,
    "i.m.": RouteOfAdministration.INTRAMUSCULAR,
    "intramuscular": RouteOfAdministration.INTRAMUSCULAR,
    "intramuscularly": RouteOfAdministration.INTRAMUSCULAR,

    # Subcutaneous
    "sc": RouteOfAdministration.SUBCUTANEOUS,
    "s.c.": RouteOfAdministration.SUBCUTANEOUS,
    "subcut": RouteOfAdministration.SUBCUTANEOUS,
    "subcutaneous": RouteOfAdministration.SUBCUTANEOUS,
    "subcutaneously": RouteOfAdministration.SUBCUTANEOUS,

    # Transdermal
    "td": RouteOfAdministration.TRANSDERMAL,
    "transdermal": RouteOfAdministration.TRANSDERMAL,
    "patch": RouteOfAdministration.TRANSDERMAL,

    # Feeding tubes
    "ng": RouteOfAdministration.NG,
    "n.g.": RouteOfAdministration.NG,
    "nasogastric": RouteOfAdministration.NG,
    "via ng": RouteOfAdministration.NG,
    "peg": RouteOfAdministration.PEG,
    "via peg": RouteOfAdministration.PEG,
    "gastrostomy": RouteOfAdministration.PEG,
}

# Drug forms
DRUG_FORMS = {
    "tablet": "tablet",
    "tablets": "tablet",
    "tab": "tablet",
    "tabs": "tablet",
    "capsule": "capsule",
    "capsules": "capsule",
    "cap": "capsule",
    "caps": "capsule",
    "injection": "injection",
    "inj": "injection",
    "solution": "solution",
    "soln": "solution",
    "suspension": "suspension",
    "susp": "suspension",
    "syrup": "syrup",
    "cream": "cream",
    "ointment": "ointment",
    "oint": "ointment",
    "gel": "gel",
    "lotion": "lotion",
    "spray": "spray",
    "inhaler": "inhaler",
    "nebules": "nebules",
    "drops": "drops",
    "patch": "patch",
    "patches": "patch",
    "suppository": "suppository",
    "pessary": "pessary",
    "enema": "enema",
    "sachet": "sachet",
    "sachets": "sachet",
    "powder": "powder",
    "granules": "granules",
    "lozenge": "lozenge",
    "lozenges": "lozenge",
    "mouthwash": "mouthwash",
    "liquid": "liquid",
    "elixir": "elixir",
    "modified release": "modified release",
    "m/r": "modified release",
    "mr": "modified release",
    "extended release": "extended release",
    "er": "extended release",
    "xl": "extended release",
    "sr": "sustained release",
    "la": "long acting",
}

# Status indicators
STATUS_INDICATORS = {
    "current": ["current", "continue", "continued", "ongoing", "regular", "usual"],
    "new": ["new", "started", "start", "commence", "initiated", "initiate", "begin"],
    "discontinued": ["stop", "stopped", "discontinue", "discontinued", "d/c", "dc", "cease", "ceased", "omit", "omitted"],
    "changed": ["changed", "change", "increased", "decreased", "reduced", "amended", "altered", "adjusted"],
    "on_hold": ["hold", "held", "withheld", "withhold", "suspend", "suspended", "pause", "paused"],
    "prn": ["prn", "as required", "as needed", "when required", "when needed"],
}

# Common drug name corrections (OCR errors)
DRUG_NAME_CORRECTIONS = {
    "atorvastain": "atorvastatin",
    "simvastain": "simvastatin",
    "metforrnin": "metformin",
    "metforrmin": "metformin",
    "amoxicilln": "amoxicillin",
    "amoxycillin": "amoxicillin",
    "amlodipne": "amlodipine",
    "omeprazol": "omeprazole",
    "lansoprazol": "lansoprazole",
    "ramipri1": "ramipril",
    "lisinopri1": "lisinopril",
    "paracetamo1": "paracetamol",
    "ibuprofem": "ibuprofen",
    "codiene": "codeine",
    "codene": "codeine",
    "morphime": "morphine",
    "tramado1": "tramadol",
    "gabapentim": "gabapentin",
    "pregabalin": "pregabalin",
    "sertralin": "sertraline",
    "citalopram": "citalopram",
    "fluoxetin": "fluoxetine",
    "mirtazapin": "mirtazapine",
    "warfarn": "warfarin",
    "apixabam": "apixaban",
    "rivaroxabam": "rivaroxaban",
    "clopidogre1": "clopidogrel",
    "bisoprolo1": "bisoprolol",
    "atenolo1": "atenolol",
    "levothyroxin": "levothyroxine",
    "thyroxin": "thyroxine",
    "prednisolon": "prednisolone",
    "hydrocortison": "hydrocortisone",
    "salbutamo1": "salbutamol",
    "ventolin": "salbutamol",
    "serevent": "salmeterol",
    "symbicort": "budesonide/formoterol",
    "seretide": "fluticasone/salmeterol",
    "fostair": "beclometasone/formoterol",
}


class MedicationExtractor:
    """
    Structured medication extraction engine.

    Parses medication strings and extracts:
    - Drug name
    - Strength
    - Dose
    - Route
    - Frequency
    - Duration
    - Status
    """

    def __init__(self):
        self.frequency_map = UK_FREQUENCY_ABBREVIATIONS
        self.route_map = ROUTE_ABBREVIATIONS
        self.form_map = DRUG_FORMS
        self.status_map = STATUS_INDICATORS
        self.drug_corrections = DRUG_NAME_CORRECTIONS

        # Compile regex patterns
        self._compile_patterns()

    def _compile_patterns(self):
        """Compile regex patterns for extraction"""

        # Strength pattern: number + unit (mg, mcg, g, ml, etc.)
        self.strength_pattern = re.compile(
            r'\b(\d+(?:\.\d+)?)\s*'
            r'(mg|mcg|microgram|micrograms|g|gram|grams|ml|millilitre|millilitres|'
            r'unit|units|iu|mmol|%|percent)\b',
            re.IGNORECASE
        )

        # Dose pattern: number + form (tablets, capsules, puffs, etc.)
        self.dose_pattern = re.compile(
            r'\b(\d+(?:\.\d+)?)\s*'
            r'(tablet|tablets|tab|tabs|capsule|capsules|cap|caps|'
            r'puff|puffs|drop|drops|spray|sprays|sachet|sachets|'
            r'patch|patches|dose|doses|unit|units|ml|spoon|spoonful)\b',
            re.IGNORECASE
        )

        # Duration pattern
        self.duration_pattern = re.compile(
            r'\b(?:for\s+)?(\d+)\s*'
            r'(day|days|week|weeks|month|months|year|years|'
            r'd|wk|wks|mo|mth|yr|yrs)\b',
            re.IGNORECASE
        )

        # Frequency pattern (handles "1 tablet twice daily" etc.)
        self.frequency_text_pattern = re.compile(
            r'\b(once|twice|three times|four times|'
            r'one|two|three|four|1|2|3|4)\s*'
            r'(daily|a day|per day|times daily|times a day|'
            r'weekly|a week|per week|times weekly)\b',
            re.IGNORECASE
        )

        # Combined strength+dose pattern: "40mg OD" or "Atorvastatin 40mg"
        self.med_line_pattern = re.compile(
            r'^(?P<name>[A-Za-z][A-Za-z\-/\s]+?)\s+'
            r'(?P<strength>\d+(?:\.\d+)?\s*(?:mg|mcg|g|ml|unit|units|iu|mmol|%))?'
            r'(?:\s+(?P<form>tablet|tablets|tab|capsule|capsules|cap|'
            r'injection|solution|suspension|cream|ointment|gel|spray|inhaler|drops|patch))?'
            r'(?:\s+(?P<route>oral|po|iv|im|sc|topical|inhaled|pr|pv|sl|'
            r'nasal|ophthalmic|otic|transdermal|nebulised))?'
            r'(?:\s+(?P<dose>\d+(?:\.\d+)?))?'
            r'(?:\s+(?P<frequency>od|bd|tds|qds|prn|stat|nocte|mane|'
            r'once daily|twice daily|three times daily|four times daily|'
            r'as required|when required))?',
            re.IGNORECASE
        )

    def extract(self, text: str) -> List[StructuredMedication]:
        """
        Extract structured medications from text.

        Args:
            text: Clinical text containing medication information

        Returns:
            List of StructuredMedication objects
        """
        medications = []

        # Split into lines and process each
        lines = text.split('\n')

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Try to extract medication from line
            med = self._extract_from_line(line)
            if med and med.drug_name:
                medications.append(med)

        # If no line-by-line extraction worked, try full text parsing
        if not medications:
            medications = self._extract_from_text(text)

        return medications

    def extract_single(self, med_string: str) -> StructuredMedication:
        """
        Extract a single medication from a medication string.

        Args:
            med_string: Single medication string (e.g., "Atorvastatin 40mg OD")

        Returns:
            StructuredMedication object
        """
        return self._extract_from_line(med_string)

    def _extract_from_line(self, line: str) -> Optional[StructuredMedication]:
        """Extract medication from a single line"""

        original_line = line
        line_lower = line.lower().strip()

        # Skip non-medication lines (headers, section titles, etc.)
        skip_patterns = [
            r'^(no|nil|none|not|denies)\b',
            r'^(allergies|allergy)\b',
            r'^\d+\.$',  # Numbered list item without content
            r'^[-•]$',  # Just a bullet
            r'^(current|prn|discontinued|changed|new|regular|usual)\s*(medications?|meds?)?[:\s]*$',  # Section headers
            r'^medications?\s*(list|on discharge|at discharge|to continue)?[:\s]*$',
            r'^(continue|stop|hold|start)\s*(taking)?[:\s]*$',
            r'^(your|patient\'?s?)\s*medications?[:\s]*$',
        ]
        for pattern in skip_patterns:
            if re.match(pattern, line_lower):
                return None

        # Initialize medication
        med = StructuredMedication(drug_name="", raw_text=original_line)

        # Extract components
        drug_name = self._extract_drug_name(line)
        if not drug_name:
            return None

        med.drug_name = drug_name
        med.strength = self._extract_strength(line)
        med.dose = self._extract_dose(line)
        med.route = self._extract_route(line)
        freq, freq_code = self._extract_frequency(line)
        med.frequency = freq
        med.frequency_code = freq_code
        med.duration = self._extract_duration(line)
        med.status = self._extract_status(line)
        med.form = self._extract_form(line)
        med.instructions = self._extract_instructions(line)
        med.confidence = self._calculate_confidence(med)

        return med

    def _extract_drug_name(self, text: str) -> Optional[str]:
        """Extract drug name from text"""

        # Common medication name pattern
        # Starts with capital letter, may contain hyphens/spaces
        name_pattern = re.compile(
            r'^[\s\-•\d.]*'  # Skip bullets, numbers
            r'([A-Z][a-zA-Z]+(?:[\-/][A-Za-z]+)*'  # Drug name
            r'(?:\s+[A-Z][a-zA-Z]+)?)'  # Optional second word (e.g., "Vitamin D")
        )

        match = name_pattern.match(text)
        if match:
            name = match.group(1).strip()

            # Clean up name
            name = re.sub(r'\s+', ' ', name)

            # Correct common OCR errors
            name_lower = name.lower()
            if name_lower in self.drug_corrections:
                name = self.drug_corrections[name_lower].title()

            # Validate it looks like a drug name (not just a word)
            if len(name) >= 3:
                return name

        return None

    def _extract_strength(self, text: str) -> Optional[str]:
        """Extract strength from text"""

        match = self.strength_pattern.search(text)
        if match:
            value = match.group(1)
            unit = match.group(2).lower()

            # Normalize units
            unit_map = {
                'microgram': 'mcg',
                'micrograms': 'mcg',
                'gram': 'g',
                'grams': 'g',
                'millilitre': 'ml',
                'millilitres': 'ml',
                'percent': '%',
            }
            unit = unit_map.get(unit, unit)

            return f"{value}{unit}"

        return None

    def _extract_dose(self, text: str) -> Optional[str]:
        """Extract dose from text"""

        match = self.dose_pattern.search(text)
        if match:
            value = match.group(1)
            unit = match.group(2).lower()

            # Normalize units
            unit_map = {
                'tablets': 'tablet',
                'tab': 'tablet',
                'tabs': 'tablet',
                'capsules': 'capsule',
                'cap': 'capsule',
                'caps': 'capsule',
                'puffs': 'puff',
                'drops': 'drop',
                'sprays': 'spray',
                'sachets': 'sachet',
                'patches': 'patch',
                'doses': 'dose',
                'units': 'unit',
                'spoonful': 'spoon',
            }
            unit = unit_map.get(unit, unit)

            return f"{value} {unit}"

        return None

    def _extract_route(self, text: str) -> Optional[str]:
        """Extract route of administration"""

        text_lower = text.lower()

        # Check for route abbreviations
        for abbrev, route in self.route_map.items():
            # Use word boundary to avoid partial matches
            pattern = r'\b' + re.escape(abbrev) + r'\b'
            if re.search(pattern, text_lower):
                # Handle ambiguous "od" (could be once daily or right eye)
                if abbrev == "od":
                    # If context suggests eye drops, it's ophthalmic
                    if any(word in text_lower for word in ['drop', 'eye', 'ophthalmic']):
                        return route.value
                    # Otherwise skip (probably frequency)
                    continue
                return route.value

        return None

    def _extract_frequency(self, text: str) -> Tuple[Optional[str], Optional[str]]:
        """Extract frequency and original code"""

        text_lower = text.lower()

        # Check for UK abbreviations
        for abbrev, (expansion, code) in self.frequency_map.items():
            pattern = r'\b' + re.escape(abbrev) + r'\b'
            if re.search(pattern, text_lower):
                return expansion, code

        # Check for text frequencies
        match = self.frequency_text_pattern.search(text)
        if match:
            quantity = match.group(1).lower()
            period = match.group(2).lower()

            # Normalize
            quantity_map = {'one': '1', 'two': '2', 'three': '3', 'four': '4',
                           'once': '1', 'twice': '2', 'three times': '3', 'four times': '4'}
            quantity = quantity_map.get(quantity, quantity)

            if 'daily' in period or 'day' in period:
                code_map = {'1': 'OD', '2': 'BD', '3': 'TDS', '4': 'QDS'}
                code = code_map.get(quantity, f"{quantity}X DAILY")
                return f"{quantity} times daily" if quantity not in ['1', '2'] else ('once daily' if quantity == '1' else 'twice daily'), code
            elif 'weekly' in period or 'week' in period:
                return f"{quantity} times weekly", f"{quantity}X WEEKLY"

        return None, None

    def _extract_duration(self, text: str) -> Optional[str]:
        """Extract duration"""

        match = self.duration_pattern.search(text)
        if match:
            value = match.group(1)
            unit = match.group(2).lower()

            # Normalize units
            unit_map = {
                'd': 'day',
                'days': 'day',
                'wk': 'week',
                'wks': 'week',
                'weeks': 'week',
                'mo': 'month',
                'mth': 'month',
                'months': 'month',
                'yr': 'year',
                'yrs': 'year',
                'years': 'year',
            }
            unit = unit_map.get(unit, unit)

            # Pluralize if needed
            if int(value) > 1 and not unit.endswith('s'):
                unit += 's'

            return f"{value} {unit}"

        return None

    def _extract_status(self, text: str) -> str:
        """Extract medication status"""

        text_lower = text.lower()

        for status, indicators in self.status_map.items():
            for indicator in indicators:
                if indicator in text_lower:
                    return status

        return "current"  # Default

    def _extract_form(self, text: str) -> Optional[str]:
        """Extract drug form"""

        text_lower = text.lower()

        for form_text, form_normalized in self.form_map.items():
            pattern = r'\b' + re.escape(form_text) + r'\b'
            if re.search(pattern, text_lower):
                return form_normalized

        return None

    def _extract_instructions(self, text: str) -> Optional[str]:
        """Extract additional instructions"""

        # Common instruction patterns
        instruction_patterns = [
            r'(?:take\s+)?with food',
            r'(?:take\s+)?after food',
            r'(?:take\s+)?before food',
            r'(?:take\s+)?on empty stomach',
            r'(?:take\s+)?at bedtime',
            r'(?:take\s+)?in the morning',
            r'(?:take\s+)?at night',
            r'do not crush',
            r'do not chew',
            r'swallow whole',
            r'dissolve in water',
            r'shake well',
            r'refrigerate',
            r'avoid alcohol',
            r'avoid grapefruit',
        ]

        text_lower = text.lower()
        found_instructions = []

        for pattern in instruction_patterns:
            if re.search(pattern, text_lower):
                match = re.search(pattern, text_lower)
                found_instructions.append(match.group())

        if found_instructions:
            return "; ".join(found_instructions)

        return None

    def _extract_from_text(self, text: str) -> List[StructuredMedication]:
        """Extract medications from unstructured text"""

        medications = []

        # Look for medication patterns in continuous text
        # Pattern: Drug name followed by optional strength/frequency
        med_pattern = re.compile(
            r'\b([A-Z][a-z]+(?:[\-/][A-Za-z]+)?)\s+'
            r'(\d+(?:\.\d+)?\s*(?:mg|mcg|g|ml|unit))?'
            r'(?:\s+(od|bd|tds|qds|prn|stat|nocte|mane))?',
            re.IGNORECASE
        )

        for match in med_pattern.finditer(text):
            drug_name = match.group(1)
            strength = match.group(2)
            frequency = match.group(3)

            # Validate drug name
            if len(drug_name) < 3:
                continue

            med = StructuredMedication(
                drug_name=drug_name,
                strength=strength.strip() if strength else None,
                raw_text=match.group(0)
            )

            if frequency:
                freq_lower = frequency.lower()
                if freq_lower in self.frequency_map:
                    med.frequency, med.frequency_code = self.frequency_map[freq_lower]

            med.confidence = self._calculate_confidence(med)
            medications.append(med)

        return medications

    def _calculate_confidence(self, med: StructuredMedication) -> float:
        """Calculate confidence score for extraction"""

        score = 0.0

        # Drug name present and valid
        if med.drug_name and len(med.drug_name) >= 3:
            score += 0.4

        # Strength extracted
        if med.strength:
            score += 0.2

        # Frequency extracted
        if med.frequency:
            score += 0.2

        # Route extracted
        if med.route:
            score += 0.1

        # Form extracted
        if med.form:
            score += 0.1

        return min(score, 1.0)

    def format_medication(self, med: StructuredMedication) -> str:
        """Format medication as readable string"""

        parts = [med.drug_name]

        if med.strength:
            parts.append(med.strength)

        if med.form:
            parts.append(med.form)

        if med.dose:
            parts.append(med.dose)

        if med.route:
            parts.append(med.route)

        if med.frequency:
            parts.append(med.frequency)
            if med.frequency_code and med.frequency_code not in med.frequency.upper():
                parts.append(f"({med.frequency_code})")

        if med.duration:
            parts.append(f"for {med.duration}")

        if med.status and med.status != "current":
            parts.append(f"[{med.status.upper()}]")

        return " ".join(parts)


def extract_medications(text: str) -> List[Dict]:
    """
    Convenience function to extract medications from text.

    Args:
        text: Clinical text containing medication information

    Returns:
        List of medication dictionaries
    """
    extractor = MedicationExtractor()
    medications = extractor.extract(text)
    return [med.to_dict() for med in medications]


if __name__ == "__main__":
    # Test the extractor
    test_cases = [
        "Atorvastatin 40mg OD",
        "Metformin 500mg BD",
        "Ramipril 2.5mg OM",
        "Salbutamol 100mcg inhaler 2 puffs PRN",
        "Omeprazole 20mg oral once daily",
        "Morphine Sulphate 10mg IV q4h",
        "Prednisolone 40mg OD for 5 days",
        "Amoxicillin 500mg TDS for 7 days",
        "Warfarin 3mg ON - INR dependent",
        "Insulin Lantus 20 units SC nocte",
        "GTN spray 1-2 puffs SL PRN for chest pain",
        "Lactulose 15ml BD",
        "Paracetamol 1g QDS PRN",
        "Bisoprolol 2.5mg OD [NEW]",
        "Amlodipine 10mg OD - STOP",
        "Vitamin D 800 units OD",
        "Co-codamol 30/500 2 tablets QDS",
    ]

    extractor = MedicationExtractor()

    print("=" * 80)
    print("MEDICATION EXTRACTION TEST")
    print("=" * 80)

    for test in test_cases:
        print(f"\nInput: {test}")
        med = extractor.extract_single(test)
        if med:
            print(f"  Drug Name:  {med.drug_name}")
            print(f"  Strength:   {med.strength}")
            print(f"  Dose:       {med.dose}")
            print(f"  Route:      {med.route}")
            print(f"  Frequency:  {med.frequency} ({med.frequency_code})")
            print(f"  Duration:   {med.duration}")
            print(f"  Status:     {med.status}")
            print(f"  Form:       {med.form}")
            print(f"  Confidence: {med.confidence:.2f}")
            print(f"  Formatted:  {extractor.format_medication(med)}")
        else:
            print("  [No medication extracted]")

    print("\n" + "=" * 80)
    print("MULTI-LINE EXTRACTION TEST")
    print("=" * 80)

    medication_list = """
    Current Medications:
    1. Atorvastatin 40mg OD
    2. Metformin 500mg BD
    3. Ramipril 5mg OM
    4. Aspirin 75mg OD
    5. Omeprazole 20mg OD

    PRN Medications:
    - Paracetamol 1g QDS PRN
    - GTN spray PRN

    Discontinued:
    - Amlodipine 5mg - STOP (ankle swelling)
    """

    meds = extractor.extract(medication_list)
    print(f"\nExtracted {len(meds)} medications:")
    for i, med in enumerate(meds, 1):
        print(f"  {i}. {extractor.format_medication(med)} (conf: {med.confidence:.2f})")
