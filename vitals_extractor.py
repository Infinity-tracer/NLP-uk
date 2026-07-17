"""
Vital Signs Extractor

Extracts vital sign measurements from clinical text.

Extracts:
- Temperature
- Pulse / Heart Rate
- Respiratory Rate
- Blood Pressure (systolic/diastolic)
- SpO2 (Oxygen Saturation)
- GCS (Glasgow Coma Scale)
- Pain Score

Stores:
- value
- unit
- timestamp (if present)

Example:
    HR = 98 bpm
    BP = 108/64 mmHg
    SpO2 = 98%
"""

import re
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional, Tuple
from enum import Enum
from datetime import datetime


class VitalType(Enum):
    """Type of vital sign"""
    TEMPERATURE = "temperature"
    PULSE = "pulse"
    HEART_RATE = "heart_rate"
    RESPIRATORY_RATE = "respiratory_rate"
    BLOOD_PRESSURE = "blood_pressure"
    SYSTOLIC_BP = "systolic_bp"
    DIASTOLIC_BP = "diastolic_bp"
    SPO2 = "spo2"
    GCS = "gcs"
    GCS_EYE = "gcs_eye"
    GCS_VERBAL = "gcs_verbal"
    GCS_MOTOR = "gcs_motor"
    PAIN_SCORE = "pain_score"
    AVPU = "avpu"
    WEIGHT = "weight"
    HEIGHT = "height"
    BMI = "bmi"
    BSA = "bsa"
    BLOOD_GLUCOSE = "blood_glucose"


class VitalStatus(Enum):
    """Status/interpretation of vital sign"""
    NORMAL = "normal"
    LOW = "low"
    HIGH = "high"
    CRITICAL_LOW = "critical_low"
    CRITICAL_HIGH = "critical_high"
    UNKNOWN = "unknown"


@dataclass
class VitalSign:
    """Extracted vital sign with value, unit, and timestamp"""
    vital_type: str              # Type of vital sign
    value: str                   # The measured value
    numeric_value: Optional[float]  # Numeric value if parseable
    unit: str                    # Unit of measurement
    timestamp: Optional[str]     # Timestamp if present
    status: str                  # normal/low/high/critical
    raw_text: str                # Original text
    confidence: float            # Extraction confidence

    # For blood pressure, store both values
    systolic: Optional[float] = None
    diastolic: Optional[float] = None

    # For GCS, store components
    gcs_eye: Optional[int] = None
    gcs_verbal: Optional[int] = None
    gcs_motor: Optional[int] = None

    def to_dict(self) -> Dict:
        return asdict(self)


# Normal ranges for vital signs (adult)
NORMAL_RANGES = {
    VitalType.TEMPERATURE: (36.1, 37.2),      # Celsius
    VitalType.PULSE: (60, 100),                # bpm
    VitalType.HEART_RATE: (60, 100),           # bpm
    VitalType.RESPIRATORY_RATE: (12, 20),      # breaths/min
    VitalType.SYSTOLIC_BP: (90, 140),          # mmHg
    VitalType.DIASTOLIC_BP: (60, 90),          # mmHg
    VitalType.SPO2: (95, 100),                 # %
    VitalType.GCS: (15, 15),                   # 15 is normal
    VitalType.PAIN_SCORE: (0, 3),              # 0-3 mild
    VitalType.BLOOD_GLUCOSE: (4.0, 7.8),       # mmol/L fasting
}

# Critical ranges
CRITICAL_RANGES = {
    VitalType.TEMPERATURE: (35.0, 38.5),      # Hypothermia / Hyperpyrexia
    VitalType.PULSE: (40, 150),                # Bradycardia / Tachycardia
    VitalType.HEART_RATE: (40, 150),
    VitalType.RESPIRATORY_RATE: (8, 30),
    VitalType.SYSTOLIC_BP: (70, 180),          # Hypotension / Hypertensive crisis
    VitalType.DIASTOLIC_BP: (40, 120),
    VitalType.SPO2: (88, 100),                 # Hypoxia
    VitalType.GCS: (8, 15),                    # Severe brain injury < 8
    VitalType.BLOOD_GLUCOSE: (2.8, 11.1),      # Hypoglycemia / Hyperglycemia
}

# Vital sign name variations
VITAL_PATTERNS = {
    VitalType.TEMPERATURE: [
        "temperature", "temp", "t°", "t °", "tº", "t:", "temp:", "temperature:",
        "core temp", "core temperature", "tympanic", "axillary", "oral temp",
        "rectal temp",
    ],
    VitalType.PULSE: [
        "pulse", "p:", "pulse:", "pulse rate", "pr", "pr:",
    ],
    VitalType.HEART_RATE: [
        "heart rate", "hr", "hr:", "h/r", "h.r.", "heartrate", "heart rate:",
        "ventricular rate",  # Removed generic "rate" - too many false positives
    ],
    VitalType.RESPIRATORY_RATE: [
        "respiratory rate", "rr", "rr:", "resp rate", "resp:", "respirations",
        "breathing rate", "resp. rate", "resps", "r/r",
    ],
    VitalType.BLOOD_PRESSURE: [
        "blood pressure", "bp", "bp:", "b/p", "b.p.", "nibp", "abp",
        "arterial pressure", "systolic/diastolic",
    ],
    VitalType.SPO2: [
        "spo2", "sp02", "sao2", "sa02", "o2 sat", "o2sat", "oxygen saturation",
        "oxygen sats", "o2 sats", "sats", "saturation", "sat:", "sats:",
        "pulse ox", "pulse oximetry", "spo2:",
    ],
    VitalType.GCS: [
        "gcs", "g.c.s.", "glasgow coma scale", "glasgow coma score",
        "gcs:", "glasgow:", "coma scale",
    ],
    VitalType.PAIN_SCORE: [
        "pain score", "pain:", "pain level", "vas", "nrs", "numeric pain",
        "pain rating", "pain scale", "pain /10", "pain/10",
    ],
    VitalType.AVPU: [
        "avpu", "a.v.p.u.", "avpu:", "conscious level", "consciousness",
        "level of consciousness", "loc:",
    ],
    VitalType.WEIGHT: [
        "weight", "wt", "wt:", "weight:", "body weight",
    ],
    VitalType.HEIGHT: [
        "height", "ht", "ht:", "height:", "stature",
    ],
    VitalType.BMI: [
        "bmi", "b.m.i.", "body mass index", "bmi:",
    ],
    VitalType.BSA: [
        "bsa", "b.s.a.", "body surface area", "bsa:",
    ],
    VitalType.BLOOD_GLUCOSE: [
        "blood glucose", "bg", "bg:", "cbg", "capillary glucose", "glucose",
        "blood sugar", "bm", "bm:", "glucometer", "fingerprick",
    ],
}

# Unit patterns
UNIT_PATTERNS = {
    VitalType.TEMPERATURE: [
        r"°?[cC]", r"celsius", r"°?[fF]", r"fahrenheit", r"degrees",
    ],
    VitalType.PULSE: [
        r"bpm", r"beats?\s*/?min", r"beats?\s*per\s*min", r"/min",
    ],
    VitalType.HEART_RATE: [
        r"bpm", r"beats?\s*/?min", r"beats?\s*per\s*min", r"/min",
    ],
    VitalType.RESPIRATORY_RATE: [
        r"breaths?\s*/?min", r"/min", r"rpm", r"resp/min",
    ],
    VitalType.BLOOD_PRESSURE: [
        r"mmHg", r"mm\s*Hg", r"mm\s*hg",
    ],
    VitalType.SPO2: [
        r"%", r"percent",
    ],
    VitalType.GCS: [
        r"/15", r"out\s*of\s*15",
    ],
    VitalType.PAIN_SCORE: [
        r"/10", r"out\s*of\s*10", r"/5", r"out\s*of\s*5",
    ],
    VitalType.WEIGHT: [
        r"kg", r"kilogram", r"kilograms", r"lbs?", r"pounds?", r"stone",
    ],
    VitalType.HEIGHT: [
        r"cm", r"centimeter", r"centimeters", r"m", r"meters?", r"ft", r"feet",
        r"inches?", r"in",
    ],
    VitalType.BMI: [
        r"kg/m2", r"kg/m²",
    ],
    VitalType.BSA: [
        r"m2", r"m²",
    ],
    VitalType.BLOOD_GLUCOSE: [
        r"mmol/[lL]", r"mmol", r"mg/d[lL]",
    ],
}

# AVPU values
AVPU_VALUES = {
    "a": "Alert",
    "alert": "Alert",
    "v": "Voice",
    "voice": "Voice",
    "responds to voice": "Voice",
    "p": "Pain",
    "pain": "Pain",
    "responds to pain": "Pain",
    "u": "Unresponsive",
    "unresponsive": "Unresponsive",
}


class VitalsExtractor:
    """
    Vital Signs Extractor

    Extracts vital sign measurements from clinical text with:
    - Value extraction
    - Unit normalization
    - Timestamp detection
    - Normal/abnormal status classification
    """

    def __init__(self):
        self.vital_patterns = VITAL_PATTERNS
        self.unit_patterns = UNIT_PATTERNS
        self.normal_ranges = NORMAL_RANGES
        self.critical_ranges = CRITICAL_RANGES

        self._compile_patterns()

    def _compile_patterns(self):
        """Compile regex patterns for extraction"""

        # Blood pressure pattern: 120/80 or 120 / 80
        self.bp_pattern = re.compile(
            r'(\d{2,3})\s*/\s*(\d{2,3})\s*(?:mmHg|mm\s*Hg)?',
            re.IGNORECASE
        )

        # GCS pattern with components: E4V5M6 or GCS 15 (E4V5M6)
        self.gcs_component_pattern = re.compile(
            r'[Ee]\s*(\d)\s*[Vv]\s*(\d)\s*[Mm]\s*(\d)',
            re.IGNORECASE
        )

        # GCS total pattern: GCS 15 or GCS: 15 or GCS = 15
        self.gcs_total_pattern = re.compile(
            r'(?:gcs|glasgow)[:\s=]*(\d{1,2})(?:\s*/\s*15)?',
            re.IGNORECASE
        )

        # General numeric value pattern
        self.numeric_pattern = re.compile(
            r'[:\s=]*\s*(\d+(?:\.\d+)?)\s*'
        )

        # Temperature with unit
        self.temp_pattern = re.compile(
            r'(\d{2}(?:\.\d)?)\s*°?\s*([CcFf])?',
            re.IGNORECASE
        )

        # SpO2 pattern: 98% or 98 %
        self.spo2_pattern = re.compile(
            r'(\d{2,3})\s*%',
            re.IGNORECASE
        )

        # Time patterns
        self.time_pattern = re.compile(
            r'(?:at\s+)?(\d{1,2}[:.]\d{2}(?:\s*[ap]m)?|\d{4}(?:hrs?)?)',
            re.IGNORECASE
        )

        # Date patterns
        self.date_pattern = re.compile(
            r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
            re.IGNORECASE
        )

    def extract(self, text: str) -> List[VitalSign]:
        """
        Extract all vital signs from text.

        Args:
            text: Clinical text containing vital signs

        Returns:
            List of VitalSign objects
        """
        vitals = []

        # Split into lines
        lines = text.split('\n')

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Extract vitals from line
            line_vitals = self._extract_from_line(line)
            vitals.extend(line_vitals)

        # Deduplicate by type (keep highest confidence)
        vitals = self._deduplicate(vitals)

        return vitals

    def extract_single(self, text: str, vital_type: Optional[VitalType] = None) -> Optional[VitalSign]:
        """
        Extract a single vital sign from text.

        Args:
            text: Text containing a vital sign
            vital_type: Optional type to look for specifically

        Returns:
            VitalSign object or None
        """
        vitals = self._extract_from_line(text, vital_type)
        return vitals[0] if vitals else None

    def _extract_from_line(self, line: str, target_type: Optional[VitalType] = None) -> List[VitalSign]:
        """Extract vital signs from a single line"""

        vitals = []
        line_lower = line.lower()

        # Priority order: longer/more specific patterns first
        # BMI before blood glucose (both have short patterns)
        # Height before weight (both have "ht"/"wt")
        priority_order = [
            VitalType.RESPIRATORY_RATE,  # Check "respiratory rate" before generic "rate"
            VitalType.HEART_RATE,
            VitalType.PULSE,
            VitalType.BLOOD_PRESSURE,
            VitalType.SPO2,
            VitalType.TEMPERATURE,
            VitalType.GCS,
            VitalType.PAIN_SCORE,
            VitalType.AVPU,
            VitalType.BMI,            # BMI before blood glucose
            VitalType.BSA,            # BSA before generic matches
            VitalType.HEIGHT,         # Height before weight
            VitalType.WEIGHT,
            VitalType.BLOOD_GLUCOSE,  # Last - most generic patterns
        ]

        matched_types = set()

        for vital_type in priority_order:
            if target_type and vital_type != target_type:
                continue

            # Skip if a more specific type already matched for this line
            if vital_type == VitalType.HEART_RATE and VitalType.RESPIRATORY_RATE in matched_types:
                if "respiratory" in line_lower:
                    continue

            # Skip blood glucose if BMI already matched
            if vital_type == VitalType.BLOOD_GLUCOSE and VitalType.BMI in matched_types:
                continue

            # Skip weight if height matched on same line (e.g., "Height: 175cm")
            if vital_type == VitalType.WEIGHT and VitalType.HEIGHT in matched_types:
                if "height" in line_lower and "weight" not in line_lower:
                    continue

            patterns = self.vital_patterns.get(vital_type, [])
            for pattern in patterns:
                # Use word boundary check for short patterns (2-3 chars)
                if len(pattern) <= 3:
                    pattern_re = re.compile(r'\b' + re.escape(pattern) + r'\b', re.IGNORECASE)
                    if pattern_re.search(line_lower):
                        vital = self._extract_vital(line, vital_type, pattern)
                        if vital:
                            vitals.append(vital)
                            matched_types.add(vital_type)
                        break
                elif pattern in line_lower:
                    vital = self._extract_vital(line, vital_type, pattern)
                    if vital:
                        vitals.append(vital)
                        matched_types.add(vital_type)
                    break

        return vitals

    def _extract_vital(self, line: str, vital_type: VitalType, matched_pattern: str) -> Optional[VitalSign]:
        """Extract a specific vital sign from line"""

        line_lower = line.lower()

        # Find position of the pattern
        pos = line_lower.find(matched_pattern)
        if pos == -1:
            return None

        # Get text after the pattern
        after_pattern = line[pos + len(matched_pattern):]

        # Special handling for different vital types
        if vital_type == VitalType.BLOOD_PRESSURE:
            return self._extract_blood_pressure(line, after_pattern)

        elif vital_type == VitalType.GCS:
            return self._extract_gcs(line, after_pattern)

        elif vital_type == VitalType.AVPU:
            return self._extract_avpu(line, after_pattern)

        elif vital_type == VitalType.TEMPERATURE:
            return self._extract_temperature(line, after_pattern, vital_type)

        elif vital_type == VitalType.SPO2:
            return self._extract_spo2(line, after_pattern, vital_type)

        else:
            return self._extract_numeric_vital(line, after_pattern, vital_type)

    def _extract_blood_pressure(self, line: str, after_pattern: str) -> Optional[VitalSign]:
        """Extract blood pressure (systolic/diastolic)"""

        match = self.bp_pattern.search(line)
        if not match:
            return None

        systolic = float(match.group(1))
        diastolic = float(match.group(2))

        # Determine status
        status = self._determine_bp_status(systolic, diastolic)

        # Extract timestamp
        timestamp = self._extract_timestamp(line)

        return VitalSign(
            vital_type=VitalType.BLOOD_PRESSURE.value,
            value=f"{int(systolic)}/{int(diastolic)}",
            numeric_value=systolic,  # Store systolic as primary
            unit="mmHg",
            timestamp=timestamp,
            status=status,
            raw_text=line,
            confidence=0.95,
            systolic=systolic,
            diastolic=diastolic,
        )

    def _extract_gcs(self, line: str, after_pattern: str) -> Optional[VitalSign]:
        """Extract Glasgow Coma Scale (total and components)"""

        gcs_eye = None
        gcs_verbal = None
        gcs_motor = None
        total = None

        # Try to find components first
        comp_match = self.gcs_component_pattern.search(line)
        if comp_match:
            gcs_eye = int(comp_match.group(1))
            gcs_verbal = int(comp_match.group(2))
            gcs_motor = int(comp_match.group(3))
            total = gcs_eye + gcs_verbal + gcs_motor

        # Try to find total
        if not total:
            total_match = self.gcs_total_pattern.search(line)
            if total_match:
                total = int(total_match.group(1))

        if not total:
            # Try simple numeric extraction
            match = self.numeric_pattern.search(after_pattern)
            if match:
                val = float(match.group(1))
                if 3 <= val <= 15:
                    total = int(val)

        if not total:
            return None

        # Determine status
        status = self._determine_status(VitalType.GCS, total)

        # Extract timestamp
        timestamp = self._extract_timestamp(line)

        return VitalSign(
            vital_type=VitalType.GCS.value,
            value=str(total),
            numeric_value=float(total),
            unit="/15",
            timestamp=timestamp,
            status=status,
            raw_text=line,
            confidence=0.95 if gcs_eye else 0.85,
            gcs_eye=gcs_eye,
            gcs_verbal=gcs_verbal,
            gcs_motor=gcs_motor,
        )

    def _extract_avpu(self, line: str, after_pattern: str) -> Optional[VitalSign]:
        """Extract AVPU score"""

        line_lower = line.lower()

        for key, value in AVPU_VALUES.items():
            if key in line_lower:
                timestamp = self._extract_timestamp(line)

                return VitalSign(
                    vital_type=VitalType.AVPU.value,
                    value=value,
                    numeric_value=None,
                    unit="",
                    timestamp=timestamp,
                    status="normal" if value == "Alert" else "abnormal",
                    raw_text=line,
                    confidence=0.90,
                )

        return None

    def _extract_temperature(self, line: str, after_pattern: str, vital_type: VitalType) -> Optional[VitalSign]:
        """Extract temperature with unit handling"""

        match = self.temp_pattern.search(after_pattern)
        if not match:
            match = self.numeric_pattern.search(after_pattern)

        if not match:
            return None

        value = float(match.group(1))
        unit_char = match.group(2) if len(match.groups()) > 1 and match.group(2) else None

        # Determine unit and convert if necessary
        unit = "°C"
        if unit_char and unit_char.upper() == 'F':
            unit = "°F"
            # Convert to Celsius for status check
            value_c = (value - 32) * 5 / 9
        else:
            value_c = value

        # Check if value is plausible
        if not (30 <= value_c <= 45):
            return None

        # Determine status using Celsius value
        status = self._determine_status(VitalType.TEMPERATURE, value_c)

        timestamp = self._extract_timestamp(line)

        return VitalSign(
            vital_type=vital_type.value,
            value=f"{value:.1f}",
            numeric_value=value,
            unit=unit,
            timestamp=timestamp,
            status=status,
            raw_text=line,
            confidence=0.90,
        )

    def _extract_spo2(self, line: str, after_pattern: str, vital_type: VitalType) -> Optional[VitalSign]:
        """Extract oxygen saturation"""

        match = self.spo2_pattern.search(line)
        if not match:
            match = self.numeric_pattern.search(after_pattern)

        if not match:
            return None

        value = float(match.group(1))

        # Check if value is plausible (50-100%)
        if not (50 <= value <= 100):
            return None

        status = self._determine_status(VitalType.SPO2, value)
        timestamp = self._extract_timestamp(line)

        return VitalSign(
            vital_type=vital_type.value,
            value=f"{int(value)}",
            numeric_value=value,
            unit="%",
            timestamp=timestamp,
            status=status,
            raw_text=line,
            confidence=0.95,
        )

    def _extract_numeric_vital(self, line: str, after_pattern: str, vital_type: VitalType) -> Optional[VitalSign]:
        """Extract a generic numeric vital sign"""

        match = self.numeric_pattern.search(after_pattern)
        if not match:
            return None

        value = float(match.group(1))

        # Validate value range based on type
        if not self._is_plausible_value(vital_type, value):
            return None

        # Determine unit
        unit = self._determine_unit(vital_type, after_pattern)

        # Determine status
        status = self._determine_status(vital_type, value)

        timestamp = self._extract_timestamp(line)

        return VitalSign(
            vital_type=vital_type.value,
            value=f"{value:.1f}" if value != int(value) else str(int(value)),
            numeric_value=value,
            unit=unit,
            timestamp=timestamp,
            status=status,
            raw_text=line,
            confidence=0.85,
        )

    def _determine_unit(self, vital_type: VitalType, text: str) -> str:
        """Determine the unit for a vital type"""

        if vital_type not in self.unit_patterns:
            return ""

        text_lower = text.lower()
        for pattern in self.unit_patterns[vital_type]:
            if re.search(pattern, text_lower):
                # Return standardized unit
                match = re.search(pattern, text_lower)
                return match.group(0)

        # Default units
        default_units = {
            VitalType.PULSE: "bpm",
            VitalType.HEART_RATE: "bpm",
            VitalType.RESPIRATORY_RATE: "/min",
            VitalType.BLOOD_PRESSURE: "mmHg",
            VitalType.SPO2: "%",
            VitalType.TEMPERATURE: "°C",
            VitalType.PAIN_SCORE: "/10",
            VitalType.WEIGHT: "kg",
            VitalType.HEIGHT: "cm",
            VitalType.BMI: "kg/m²",
            VitalType.BSA: "m²",
            VitalType.BLOOD_GLUCOSE: "mmol/L",
        }

        return default_units.get(vital_type, "")

    def _determine_status(self, vital_type: VitalType, value: float) -> str:
        """Determine if vital sign is normal, low, high, or critical"""

        if vital_type not in self.normal_ranges:
            return VitalStatus.UNKNOWN.value

        normal_low, normal_high = self.normal_ranges[vital_type]
        critical_low, critical_high = self.critical_ranges.get(vital_type, (None, None))

        # Check critical first
        if critical_low and value < critical_low:
            return VitalStatus.CRITICAL_LOW.value
        if critical_high and value > critical_high:
            return VitalStatus.CRITICAL_HIGH.value

        # Check normal
        if normal_low <= value <= normal_high:
            return VitalStatus.NORMAL.value
        elif value < normal_low:
            return VitalStatus.LOW.value
        else:
            return VitalStatus.HIGH.value

    def _determine_bp_status(self, systolic: float, diastolic: float) -> str:
        """Determine blood pressure status"""

        # Check critical
        if systolic < 70 or diastolic < 40:
            return VitalStatus.CRITICAL_LOW.value
        if systolic > 180 or diastolic > 120:
            return VitalStatus.CRITICAL_HIGH.value

        # Check normal
        sys_normal = 90 <= systolic <= 140
        dia_normal = 60 <= diastolic <= 90

        if sys_normal and dia_normal:
            return VitalStatus.NORMAL.value
        elif systolic < 90 or diastolic < 60:
            return VitalStatus.LOW.value
        else:
            return VitalStatus.HIGH.value

    def _is_plausible_value(self, vital_type: VitalType, value: float) -> bool:
        """Check if value is plausible for the vital type"""

        plausible_ranges = {
            VitalType.PULSE: (20, 250),
            VitalType.HEART_RATE: (20, 250),
            VitalType.RESPIRATORY_RATE: (4, 60),
            VitalType.SPO2: (50, 100),
            VitalType.GCS: (3, 15),
            VitalType.PAIN_SCORE: (0, 10),
            VitalType.TEMPERATURE: (30, 45),
            VitalType.WEIGHT: (1, 500),
            VitalType.HEIGHT: (30, 250),
            VitalType.BMI: (10, 80),
            VitalType.BSA: (0.1, 3.5),
            VitalType.BLOOD_GLUCOSE: (1, 50),
        }

        if vital_type not in plausible_ranges:
            return True

        low, high = plausible_ranges[vital_type]
        return low <= value <= high

    def _extract_timestamp(self, line: str) -> Optional[str]:
        """Extract timestamp from line if present"""

        # Try time pattern
        time_match = self.time_pattern.search(line)
        date_match = self.date_pattern.search(line)

        if time_match and date_match:
            return f"{date_match.group(1)} {time_match.group(1)}"
        elif time_match:
            return time_match.group(1)
        elif date_match:
            return date_match.group(1)

        return None

    def _deduplicate(self, vitals: List[VitalSign]) -> List[VitalSign]:
        """Remove duplicates, keeping highest confidence"""

        seen = {}
        for vital in vitals:
            key = vital.vital_type
            if key not in seen or vital.confidence > seen[key].confidence:
                seen[key] = vital

        return list(seen.values())

    def format_vitals(self, vitals: List[VitalSign]) -> str:
        """Format vitals as a readable summary"""

        lines = []
        for v in vitals:
            status_marker = ""
            if v.status == "critical_low" or v.status == "critical_high":
                status_marker = " [CRITICAL]"
            elif v.status == "low":
                status_marker = " [LOW]"
            elif v.status == "high":
                status_marker = " [HIGH]"

            line = f"{v.vital_type}: {v.value} {v.unit}{status_marker}"
            if v.timestamp:
                line += f" @ {v.timestamp}"
            lines.append(line)

        return "\n".join(lines)


def extract_vitals(text: str) -> List[Dict]:
    """
    Convenience function to extract vital signs from text.

    Args:
        text: Clinical text containing vital signs

    Returns:
        List of vital sign dictionaries
    """
    extractor = VitalsExtractor()
    vitals = extractor.extract(text)
    return [v.to_dict() for v in vitals]


if __name__ == "__main__":
    # Test the extractor
    test_cases = [
        "HR = 98 bpm",
        "BP = 108/64 mmHg",
        "SpO2 = 98%",
        "Temperature: 37.2°C",
        "Temp 38.5 C",
        "RR: 18/min",
        "Respiratory rate 22",
        "Pulse: 72 bpm",
        "GCS 15 (E4V5M6)",
        "GCS: 12",
        "Pain score: 6/10",
        "O2 sats: 94% on room air",
        "AVPU: Alert",
        "Blood glucose: 6.2 mmol/L",
        "Weight: 75kg",
        "Height: 175cm",
        "BMI: 24.5",
        "BP 180/110 at 14:30",
        "HR 45 bpm - bradycardia",
        "Temp 35.0°C - hypothermic",
    ]

    extractor = VitalsExtractor()

    print("=" * 80)
    print("VITAL SIGNS EXTRACTION TEST")
    print("=" * 80)

    for test in test_cases:
        print(f"\nInput: {test}")
        vitals = extractor.extract(test)
        if vitals:
            for v in vitals:
                print(f"  Type:      {v.vital_type}")
                print(f"  Value:     {v.value} {v.unit}")
                if v.systolic:
                    print(f"  Systolic:  {v.systolic}")
                    print(f"  Diastolic: {v.diastolic}")
                if v.gcs_eye:
                    print(f"  GCS (E/V/M): {v.gcs_eye}/{v.gcs_verbal}/{v.gcs_motor}")
                print(f"  Status:    {v.status}")
                if v.timestamp:
                    print(f"  Timestamp: {v.timestamp}")
                print(f"  Confidence: {v.confidence:.2f}")
        else:
            print("  [No vital signs extracted]")

    print("\n" + "=" * 80)
    print("CLINICAL OBSERVATIONS BLOCK TEST")
    print("=" * 80)

    obs_text = """
    Observations on arrival (14:30):
    HR: 98 bpm
    BP: 142/88 mmHg
    RR: 20/min
    SpO2: 97% on room air
    Temp: 37.8°C
    GCS: 15 (E4V5M6)
    Pain: 4/10
    AVPU: Alert
    Blood glucose: 5.8 mmol/L

    Vitals at 16:00:
    HR: 82 bpm
    BP: 128/76 mmHg
    Temp: 37.2°C
    SpO2: 99%
    """

    vitals = extractor.extract(obs_text)
    print(f"\nExtracted {len(vitals)} vital signs:")
    print(extractor.format_vitals(vitals))
