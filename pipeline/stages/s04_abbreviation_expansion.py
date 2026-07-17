"""
Stage 4: Abbreviation Expansion - Clinical Abbreviation Resolution

Expands clinical abbreviations to their full forms.
Preserves original text and maps positions.
"""

import re
from typing import Dict, List, Tuple

from ..base import PipelineStage, StageResult, PipelineContext, StageStatus, StageRegistry


@StageRegistry.register
class AbbreviationExpansionStage(PipelineStage):
    """
    Abbreviation Expansion Stage - Resolve clinical abbreviations.

    Expands common NHS clinical abbreviations while preserving original text.
    Provides mappings for downstream entity extraction.

    Outputs:
    - expanded_text: Text with abbreviations expanded
    - abbreviations: List of resolved abbreviations with positions
    """

    # Clinical abbreviation dictionary (abbreviation -> expansion)
    ABBREVIATIONS = {
        # Diagnoses/Conditions
        "MI": "Myocardial Infarction",
        "CVA": "Cerebrovascular Accident",
        "TIA": "Transient Ischaemic Attack",
        "COPD": "Chronic Obstructive Pulmonary Disease",
        "DM": "Diabetes Mellitus",
        "DM2": "Type 2 Diabetes Mellitus",
        "T2DM": "Type 2 Diabetes Mellitus",
        "HTN": "Hypertension",
        "AF": "Atrial Fibrillation",
        "CCF": "Congestive Cardiac Failure",
        "CHF": "Congestive Heart Failure",
        "CKD": "Chronic Kidney Disease",
        "AKI": "Acute Kidney Injury",
        "UTI": "Urinary Tract Infection",
        "LRTI": "Lower Respiratory Tract Infection",
        "URTI": "Upper Respiratory Tract Infection",
        "PE": "Pulmonary Embolism",
        "DVT": "Deep Vein Thrombosis",
        "SOB": "Shortness of Breath",
        "DOE": "Dyspnoea on Exertion",
        "LOC": "Loss of Consciousness",
        "NOF": "Neck of Femur",

        # Investigations
        "FBC": "Full Blood Count",
        "U&E": "Urea and Electrolytes",
        "UE": "Urea and Electrolytes",
        "LFT": "Liver Function Tests",
        "TFT": "Thyroid Function Tests",
        "CRP": "C-Reactive Protein",
        "ESR": "Erythrocyte Sedimentation Rate",
        "HbA1c": "Glycated Haemoglobin",
        "INR": "International Normalised Ratio",
        "ABG": "Arterial Blood Gas",
        "VBG": "Venous Blood Gas",
        "ECG": "Electrocardiogram",
        "CXR": "Chest X-Ray",
        "AXR": "Abdominal X-Ray",
        "CT": "Computed Tomography",
        "MRI": "Magnetic Resonance Imaging",
        "USS": "Ultrasound Scan",
        "ECHO": "Echocardiogram",
        "LP": "Lumbar Puncture",
        "CTPA": "CT Pulmonary Angiogram",

        # Vitals
        "BP": "Blood Pressure",
        "HR": "Heart Rate",
        "RR": "Respiratory Rate",
        "SpO2": "Oxygen Saturation",
        "SPO2": "Oxygen Saturation",
        "GCS": "Glasgow Coma Scale",
        "AVPU": "Alert Voice Pain Unresponsive",
        "T": "Temperature",
        "BM": "Blood Glucose",
        "NEWS": "National Early Warning Score",
        "NEWS2": "National Early Warning Score 2",

        # Medications
        "PRN": "As Required",
        "OD": "Once Daily",
        "BD": "Twice Daily",
        "TDS": "Three Times Daily",
        "QDS": "Four Times Daily",
        "STAT": "Immediately",
        "PO": "By Mouth",
        "IV": "Intravenous",
        "IM": "Intramuscular",
        "SC": "Subcutaneous",
        "PR": "Per Rectum",
        "SL": "Sublingual",
        "GTN": "Glyceryl Trinitrate",
        "ACEi": "ACE Inhibitor",
        "ARB": "Angiotensin Receptor Blocker",
        "NSAID": "Non-Steroidal Anti-Inflammatory Drug",
        "PPI": "Proton Pump Inhibitor",
        "LMWH": "Low Molecular Weight Heparin",
        "TTO": "To Take Out",
        "TTOs": "To Take Out",
        "TTA": "To Take Away",

        # Sections/Notes
        "PC": "Presenting Complaint",
        "HPC": "History of Presenting Complaint",
        "PMH": "Past Medical History",
        "PSH": "Past Surgical History",
        "DH": "Drug History",
        "SH": "Social History",
        "FH": "Family History",
        "O/E": "On Examination",
        "OE": "On Examination",
        "Ix": "Investigations",
        "Dx": "Diagnosis",
        "Rx": "Treatment",
        "Cx": "Complications",

        # Clinical
        "NAD": "No Abnormality Detected",
        "NKDA": "No Known Drug Allergies",
        "NKA": "No Known Allergies",
        "ROS": "Review of Systems",
        "WNL": "Within Normal Limits",
        "DNR": "Do Not Resuscitate",
        "DNAR": "Do Not Attempt Resuscitation",
        "NBM": "Nil By Mouth",
        "OPD": "Outpatient Department",
        "A&E": "Accident and Emergency",
        "ED": "Emergency Department",
        "ICU": "Intensive Care Unit",
        "ITU": "Intensive Therapy Unit",
        "HDU": "High Dependency Unit",
        "GP": "General Practitioner",
        "F/U": "Follow Up",
        "FU": "Follow Up",
    }

    @property
    def name(self) -> str:
        return "abbreviation_expansion"

    @property
    def description(self) -> str:
        return "Expand clinical abbreviations to full forms"

    def get_dependencies(self) -> List[str]:
        return ["ocr_cleanup"]

    def validate_input(self, context: PipelineContext) -> bool:
        return bool(context.get_text())

    def process(self, context: PipelineContext) -> StageResult:
        """Expand clinical abbreviations."""
        result = StageResult(
            stage_name=self.name,
            status=StageStatus.RUNNING,
            confidence=0.0,
        )

        try:
            text = context.get_text()
            if not text:
                result.status = StageStatus.SKIPPED
                return result

            # Find and expand abbreviations
            resolved = []
            expanded_text = text

            for abbrev, expansion in self.ABBREVIATIONS.items():
                # Build pattern with word boundaries
                pattern = r'\b' + re.escape(abbrev) + r'\b'
                matches = list(re.finditer(pattern, text, re.IGNORECASE))

                for match in matches:
                    resolved.append({
                        "abbreviation": match.group(),
                        "expansion": expansion,
                        "start_pos": match.start(),
                        "end_pos": match.end(),
                        "confidence": 0.95,
                    })

            # Sort by position
            resolved.sort(key=lambda x: x["start_pos"])

            # Calculate stats by category
            stats = self._calculate_stats(resolved)

            # Calculate confidence
            confidence = 0.9 if resolved else 0.7

            # Build result
            result.status = StageStatus.DONE
            result.confidence = confidence
            result.items_processed = len(resolved)
            result.data = {
                "abbreviations": resolved,
                "total_found": len(resolved),
                "stats": stats,
            }
            result.debug_data = {
                "unique_abbreviations": list(set(r["abbreviation"].upper() for r in resolved)),
            }

            result.add_note(f"Found {len(resolved)} abbreviations")
            for cat, count in stats.items():
                if count > 0:
                    result.add_note(f"  {cat}: {count}")

            return result

        except Exception as e:
            result.status = StageStatus.ERROR
            result.error = str(e)
            return result

    def _calculate_stats(self, resolved: List[Dict]) -> Dict[str, int]:
        """Calculate statistics by abbreviation category."""
        # Categorize abbreviations
        categories = {
            "diagnoses": ["MI", "CVA", "TIA", "COPD", "DM", "HTN", "AF", "CCF", "CKD", "UTI", "PE", "DVT"],
            "investigations": ["FBC", "U&E", "LFT", "TFT", "CRP", "ECG", "CXR", "CT", "MRI", "USS"],
            "vitals": ["BP", "HR", "RR", "SpO2", "GCS", "T", "BM", "NEWS"],
            "medications": ["PRN", "OD", "BD", "TDS", "QDS", "PO", "IV", "IM", "SC", "GTN"],
            "sections": ["PC", "HPC", "PMH", "PSH", "DH", "SH", "FH", "O/E", "Ix", "Dx", "Rx"],
        }

        stats = {cat: 0 for cat in categories}
        stats["other"] = 0

        for r in resolved:
            abbrev_upper = r["abbreviation"].upper()
            found = False
            for cat, abbrevs in categories.items():
                if abbrev_upper in [a.upper() for a in abbrevs]:
                    stats[cat] += 1
                    found = True
                    break
            if not found:
                stats["other"] += 1

        return stats
