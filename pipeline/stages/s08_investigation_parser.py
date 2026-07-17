"""
Stage 8: Investigation Parser - Lab and Imaging Result Extraction

Extracts structured investigation data with results and status.
"""

import re
from typing import Dict, List, Optional, Tuple

from ..base import PipelineStage, StageResult, PipelineContext, StageStatus, StageRegistry


@StageRegistry.register
class InvestigationParserStage(PipelineStage):
    """
    Investigation Parser Stage - Extract structured investigation data.

    Extracts:
    - Investigation name and abbreviation
    - Result values
    - Result status (normal/abnormal)
    - Category (blood_test, imaging, etc.)

    Outputs:
    - investigations: List of structured investigation objects
    """

    # Investigation categories
    INVESTIGATION_CATEGORIES = {
        "blood_test": [
            "FBC", "U&E", "UE", "LFT", "TFT", "CRP", "ESR", "HbA1c", "INR",
            "ABG", "VBG", "BNP", "troponin", "d-dimer", "lactate", "glucose",
            "creatinine", "urea", "sodium", "potassium", "calcium", "magnesium",
            "haemoglobin", "Hb", "WBC", "WCC", "platelets", "neutrophils",
            "lymphocytes", "CK", "amylase", "lipase", "albumin", "bilirubin",
            "ALT", "AST", "ALP", "GGT", "ferritin", "B12", "folate", "TSH",
            "T4", "T3", "PSA", "CA125", "CEA", "AFP",
        ],
        "imaging": [
            "CXR", "chest x-ray", "AXR", "abdominal x-ray", "CT", "MRI",
            "ultrasound", "USS", "X-ray", "XR", "angiogram", "angiography",
            "CTPA", "CT head", "CT chest", "CT abdomen", "MRI brain",
            "MRI spine", "echo", "echocardiogram", "doppler",
        ],
        "cardiology": [
            "ECG", "EKG", "holter", "cardiac monitor", "angiogram",
            "coronary angiography", "stress test", "ETT", "exercise test",
            "TOE", "TTE", "echocardiogram",
        ],
        "microbiology": [
            "blood culture", "urine culture", "wound culture", "sputum culture",
            "MSU", "CSF", "stool culture", "swab", "sensitivity",
        ],
        "endoscopy": [
            "OGD", "gastroscopy", "colonoscopy", "sigmoidoscopy", "ERCP",
            "bronchoscopy", "cystoscopy", "EUS",
        ],
        "pulmonary": [
            "spirometry", "PFT", "lung function", "peak flow", "ABG",
        ],
        "urine": [
            "urinalysis", "urine dipstick", "MSU", "urine MC&S", "urine PCR",
            "urine albumin", "24h urine",
        ],
    }

    # Normal value ranges (simplified)
    NORMAL_RANGES = {
        "haemoglobin": (120, 165),
        "hb": (120, 165),
        "wbc": (4.0, 11.0),
        "wcc": (4.0, 11.0),
        "platelets": (150, 400),
        "sodium": (135, 145),
        "potassium": (3.5, 5.0),
        "creatinine": (60, 110),
        "urea": (2.5, 7.8),
        "egfr": (60, 999),
        "crp": (0, 5),
        "inr": (0.8, 1.2),
        "glucose": (4.0, 7.0),
        "hba1c": (20, 42),
    }

    # Pattern for investigation with result
    INV_RESULT_PATTERN = re.compile(
        r'\b('
        r'FBC|U&E|UE|LFT|TFT|CRP|ESR|HbA1c|INR|ABG|VBG|'
        r'troponin|d-dimer|lactate|creatinine|urea|sodium|potassium|'
        r'haemoglobin|Hb|WBC|WCC|platelets|glucose|BNP|'
        r'ECG|CXR|CT|MRI|USS|X-ray|ultrasound'
        r')\s*'
        r'(?:[:=\-]?\s*)'
        r'([\d\.]+(?:\s*[-/]\s*[\d\.]+)?)?'  # Numeric value(s)
        r'\s*'
        r'(mmol/L|g/L|g/dL|%|mg/L|U/L|mL/min|×10\^9/L|×10\^12/L)?',  # Unit
        re.IGNORECASE
    )

    @property
    def name(self) -> str:
        return "investigation_parser"

    @property
    def description(self) -> str:
        return "Extract structured investigation data"

    def get_dependencies(self) -> List[str]:
        return ["ner"]

    def validate_input(self, context: PipelineContext) -> bool:
        return bool(context.get_text())

    def process(self, context: PipelineContext) -> StageResult:
        """Parse investigations from text."""
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

            # Get investigation entities from NER
            ner_result = context.get_stage_result("ner")
            ner_investigations = []
            if ner_result and ner_result.data:
                ner_investigations = ner_result.data.get("entities", {}).get("investigation", [])

            # Parse investigations from full text
            parsed_invs = self._parse_investigations(text)

            # Merge with NER results
            all_invs = self._merge_investigations(parsed_invs, ner_investigations)

            # Enrich with structured data
            enriched_invs = [self._enrich_investigation(inv, text) for inv in all_invs]

            # Add to context
            context.add_entities("investigation_structured", enriched_invs)

            # Calculate confidence
            confidence = min(0.9, 0.6 + (len(enriched_invs) * 0.05))

            # Count by category
            category_counts = {}
            for inv in enriched_invs:
                cat = inv.get("category", "other")
                category_counts[cat] = category_counts.get(cat, 0) + 1

            # Build result
            result.status = StageStatus.DONE
            result.confidence = confidence
            result.items_processed = len(enriched_invs)
            result.data = {
                "investigations": enriched_invs,
                "count": len(enriched_invs),
                "category_counts": category_counts,
            }
            result.debug_data = {
                "from_pattern": len(parsed_invs),
                "from_ner": len(ner_investigations),
            }

            result.add_note(f"Parsed {len(enriched_invs)} investigations")
            for cat, count in category_counts.items():
                if count > 0:
                    result.add_note(f"  {cat}: {count}")

            return result

        except Exception as e:
            result.status = StageStatus.ERROR
            result.error = str(e)
            return result

    def _parse_investigations(self, text: str) -> List[Dict]:
        """Parse investigations using patterns."""
        investigations = []

        for match in self.INV_RESULT_PATTERN.finditer(text):
            inv_name = match.group(1)
            result_value = match.group(2) if match.lastindex >= 2 else None
            unit = match.group(3) if match.lastindex >= 3 else None

            inv = {
                "text": match.group().strip(),
                "investigation": inv_name,
                "investigation_abbrev": self._get_abbreviation(inv_name),
                "result": result_value,
                "unit": unit,
                "category": self._get_category(inv_name),
                "start_pos": match.start(),
                "end_pos": match.end(),
                "line_number": text[:match.start()].count('\n') + 1,
                "confidence": 0.85,
            }

            investigations.append(inv)

        return investigations

    def _get_abbreviation(self, inv_name: str) -> Optional[str]:
        """Get standard abbreviation for investigation."""
        inv_upper = inv_name.upper()
        if inv_upper in ["FBC", "U&E", "UE", "LFT", "TFT", "CRP", "ESR", "ECG", "CXR"]:
            return inv_upper
        return None

    def _get_category(self, inv_name: str) -> str:
        """Get category for investigation."""
        inv_lower = inv_name.lower()

        for category, investigations in self.INVESTIGATION_CATEGORIES.items():
            if any(inv_lower == i.lower() or inv_lower in i.lower() for i in investigations):
                return category

        return "other"

    def _merge_investigations(
        self,
        parsed: List[Dict],
        ner_invs: List[Dict]
    ) -> List[Dict]:
        """Merge parsed and NER investigations."""
        all_invs = []
        seen_spans = set()

        # Add parsed first
        for inv in parsed:
            span = (inv["start_pos"], inv["end_pos"])
            if span not in seen_spans:
                seen_spans.add(span)
                all_invs.append(inv)

        # Add NER if not overlapping
        for ner_inv in ner_invs:
            span = (ner_inv.get("start_pos", 0), ner_inv.get("end_pos", 0))
            overlaps = any(
                self._spans_overlap(span, s) for s in seen_spans
            )
            if not overlaps:
                inv = {
                    "text": ner_inv.get("text", ""),
                    "investigation": ner_inv.get("text", ""),
                    "investigation_abbrev": None,
                    "result": None,
                    "unit": None,
                    "category": self._get_category(ner_inv.get("text", "")),
                    "start_pos": ner_inv.get("start_pos", 0),
                    "end_pos": ner_inv.get("end_pos", 0),
                    "line_number": ner_inv.get("line_number", 1),
                    "evidence": ner_inv.get("evidence"),
                    "confidence": ner_inv.get("confidence", 0.7),
                }
                all_invs.append(inv)
                seen_spans.add(span)

        return all_invs

    def _spans_overlap(self, span1: Tuple[int, int], span2: Tuple[int, int]) -> bool:
        """Check if two spans overlap."""
        return not (span1[1] <= span2[0] or span2[1] <= span1[0])

    def _enrich_investigation(self, inv: Dict, text: str) -> Dict:
        """Enrich investigation with context."""
        # Get sentence context if not present
        if not inv.get("evidence"):
            start = inv.get("start_pos", 0)
            end = inv.get("end_pos", 0)
            sent_start = max(0, text.rfind('.', 0, start) + 1)
            sent_end = text.find('.', end)
            if sent_end == -1:
                sent_end = min(len(text), end + 100)
            inv["evidence"] = text[sent_start:sent_end].strip()[:200]

        # Determine result status
        inv["result_status"] = self._determine_result_status(inv)

        # Extract result from context if not found
        if not inv.get("result"):
            evidence = inv.get("evidence", "")
            result_match = re.search(r'[\d\.]+(?:\s*[-/]\s*[\d\.]+)?', evidence)
            if result_match:
                inv["result"] = result_match.group()

        # Determine priority from context
        evidence_lower = inv.get("evidence", "").lower()
        if any(w in evidence_lower for w in ["urgent", "stat", "emergency"]):
            inv["priority"] = "urgent"
        elif any(w in evidence_lower for w in ["routine"]):
            inv["priority"] = "routine"
        else:
            inv["priority"] = None

        return inv

    def _determine_result_status(self, inv: Dict) -> str:
        """Determine if result is normal/abnormal."""
        evidence = inv.get("evidence", "").lower()
        result = inv.get("result")
        inv_name = inv.get("investigation", "").lower()

        # Check for explicit status in text
        if any(w in evidence for w in ["abnormal", "raised", "elevated", "high", "low", "positive"]):
            return "abnormal"
        if any(w in evidence for w in ["normal", "unremarkable", "negative", "wnl", "within normal"]):
            return "normal"
        if any(w in evidence for w in ["pending", "awaited", "awaiting"]):
            return "pending"

        # Check against normal ranges if result is numeric
        if result:
            try:
                # Extract numeric value
                num_match = re.match(r'([\d\.]+)', str(result))
                if num_match:
                    value = float(num_match.group(1))
                    if inv_name in self.NORMAL_RANGES:
                        low, high = self.NORMAL_RANGES[inv_name]
                        if value < low or value > high:
                            return "abnormal"
                        return "normal"
            except (ValueError, TypeError):
                pass

        return "unknown"
