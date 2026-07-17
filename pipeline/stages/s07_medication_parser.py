"""
Stage 7: Medication Parser - Structured Medication Extraction

Extracts structured medication data including dose, frequency, route.
"""

import re
from typing import Dict, List, Optional, Tuple

from ..base import PipelineStage, StageResult, PipelineContext, StageStatus, StageRegistry


@StageRegistry.register
class MedicationParserStage(PipelineStage):
    """
    Medication Parser Stage - Extract structured medication data.

    Extracts:
    - Drug name
    - Dose/strength
    - Frequency
    - Route
    - Duration
    - Status (current, new, stopped)

    Outputs:
    - medications: List of structured medication objects
    """

    # Frequency codes mapping
    FREQUENCY_MAP = {
        "od": ("Once Daily", "OD"),
        "o.d.": ("Once Daily", "OD"),
        "once daily": ("Once Daily", "OD"),
        "bd": ("Twice Daily", "BD"),
        "b.d.": ("Twice Daily", "BD"),
        "twice daily": ("Twice Daily", "BD"),
        "tds": ("Three Times Daily", "TDS"),
        "t.d.s.": ("Three Times Daily", "TDS"),
        "three times daily": ("Three Times Daily", "TDS"),
        "qds": ("Four Times Daily", "QDS"),
        "q.d.s.": ("Four Times Daily", "QDS"),
        "four times daily": ("Four Times Daily", "QDS"),
        "prn": ("As Required", "PRN"),
        "p.r.n.": ("As Required", "PRN"),
        "as required": ("As Required", "PRN"),
        "when required": ("As Required", "PRN"),
        "stat": ("Immediately", "STAT"),
        "nocte": ("At Night", "NOCTE"),
        "at night": ("At Night", "NOCTE"),
        "mane": ("In the Morning", "MANE"),
        "in the morning": ("In the Morning", "MANE"),
    }

    # Route mapping
    ROUTE_MAP = {
        "po": "oral",
        "oral": "oral",
        "orally": "oral",
        "iv": "intravenous",
        "intravenous": "intravenous",
        "im": "intramuscular",
        "intramuscular": "intramuscular",
        "sc": "subcutaneous",
        "subcut": "subcutaneous",
        "subcutaneous": "subcutaneous",
        "pr": "rectal",
        "per rectum": "rectal",
        "sl": "sublingual",
        "sublingual": "sublingual",
        "top": "topical",
        "topical": "topical",
        "inh": "inhaled",
        "inhaled": "inhaled",
        "neb": "nebulised",
        "nebulised": "nebulised",
        "ng": "nasogastric",
        "peg": "peg",
    }

    # Form patterns
    FORMS = [
        "tablet", "tablets", "tab", "tabs",
        "capsule", "capsules", "cap", "caps",
        "solution", "suspension", "syrup",
        "injection", "infusion",
        "cream", "ointment", "gel",
        "patch", "patches",
        "inhaler", "spray",
        "drops", "eye drops",
    ]

    # Medication pattern
    MED_PATTERN = re.compile(
        r'\b([A-Z][a-z]+(?:\s+[A-Z]?[a-z]+)*)\s*'  # Drug name
        r'(\d+(?:\.\d+)?)\s*'                       # Dose number
        r'(mg|mcg|g|ml|units?|IU|%)\s*'            # Unit
        r'(?:'
        r'(?:(' + '|'.join(FORMS) + r')\s*)?'       # Form (optional)
        r'(?:(' + '|'.join(FREQUENCY_MAP.keys()) + r')\s*)?'  # Frequency
        r'(?:(' + '|'.join(ROUTE_MAP.keys()) + r')\s*)?'      # Route
        r')?',
        re.IGNORECASE
    )

    @property
    def name(self) -> str:
        return "medication_parser"

    @property
    def description(self) -> str:
        return "Extract structured medication data"

    def get_dependencies(self) -> List[str]:
        return ["ner"]

    def validate_input(self, context: PipelineContext) -> bool:
        return bool(context.get_text())

    def process(self, context: PipelineContext) -> StageResult:
        """Parse medications from text."""
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

            # Get medication entities from NER
            ner_result = context.get_stage_result("ner")
            ner_medications = []
            if ner_result and ner_result.data:
                ner_medications = ner_result.data.get("entities", {}).get("medication", [])

            # Parse medications from full text
            parsed_meds = self._parse_medications(text)

            # Merge with NER results
            all_meds = self._merge_medications(parsed_meds, ner_medications)

            # Enrich with structured data
            enriched_meds = [self._enrich_medication(m, text) for m in all_meds]

            # Add to context
            context.add_entities("medication_structured", enriched_meds)

            # Calculate confidence
            confidence = min(0.9, 0.6 + (len(enriched_meds) * 0.05))

            # Build result
            result.status = StageStatus.DONE
            result.confidence = confidence
            result.items_processed = len(enriched_meds)
            result.data = {
                "medications": enriched_meds,
                "count": len(enriched_meds),
            }
            result.debug_data = {
                "from_pattern": len(parsed_meds),
                "from_ner": len(ner_medications),
            }

            result.add_note(f"Parsed {len(enriched_meds)} medications")

            return result

        except Exception as e:
            result.status = StageStatus.ERROR
            result.error = str(e)
            return result

    def _parse_medications(self, text: str) -> List[Dict]:
        """Parse medications using patterns."""
        medications = []

        for match in self.MED_PATTERN.finditer(text):
            drug_name = match.group(1)
            dose_num = match.group(2)
            dose_unit = match.group(3)
            form = match.group(4) if match.lastindex >= 4 else None
            freq = match.group(5) if match.lastindex >= 5 else None
            route = match.group(6) if match.lastindex >= 6 else None

            # Skip very short drug names (likely false positives)
            if len(drug_name) < 3:
                continue

            # Build medication object
            med = {
                "text": match.group().strip(),
                "drug_name": drug_name,
                "strength": f"{dose_num}{dose_unit}",
                "dose": None,
                "form": form,
                "route": self._normalize_route(route),
                "frequency": None,
                "frequency_code": None,
                "start_pos": match.start(),
                "end_pos": match.end(),
                "line_number": text[:match.start()].count('\n') + 1,
                "confidence": 0.85,
            }

            # Normalize frequency
            if freq:
                freq_lower = freq.lower()
                if freq_lower in self.FREQUENCY_MAP:
                    med["frequency"], med["frequency_code"] = self.FREQUENCY_MAP[freq_lower]

            medications.append(med)

        return medications

    def _normalize_route(self, route: Optional[str]) -> Optional[str]:
        """Normalize route to standard form."""
        if not route:
            return None
        route_lower = route.lower()
        return self.ROUTE_MAP.get(route_lower, route)

    def _merge_medications(
        self,
        parsed: List[Dict],
        ner_meds: List[Dict]
    ) -> List[Dict]:
        """Merge parsed and NER medications, deduplicating."""
        all_meds = []
        seen_spans = set()

        # Add parsed medications first (higher confidence)
        for med in parsed:
            span = (med["start_pos"], med["end_pos"])
            if span not in seen_spans:
                seen_spans.add(span)
                all_meds.append(med)

        # Add NER medications if not overlapping
        for ner_med in ner_meds:
            span = (ner_med.get("start_pos", 0), ner_med.get("end_pos", 0))
            overlaps = any(
                self._spans_overlap(span, s) for s in seen_spans
            )
            if not overlaps:
                # Convert NER entity to medication format
                med = {
                    "text": ner_med.get("text", ""),
                    "drug_name": ner_med.get("text", ""),
                    "strength": None,
                    "dose": None,
                    "form": None,
                    "route": None,
                    "frequency": None,
                    "frequency_code": None,
                    "start_pos": ner_med.get("start_pos", 0),
                    "end_pos": ner_med.get("end_pos", 0),
                    "line_number": ner_med.get("line_number", 1),
                    "evidence": ner_med.get("evidence"),
                    "confidence": ner_med.get("confidence", 0.7),
                }
                all_meds.append(med)
                seen_spans.add(span)

        return all_meds

    def _spans_overlap(self, span1: Tuple[int, int], span2: Tuple[int, int]) -> bool:
        """Check if two spans overlap."""
        return not (span1[1] <= span2[0] or span2[1] <= span1[0])

    def _enrich_medication(self, med: Dict, text: str) -> Dict:
        """Enrich medication with context."""
        # Get sentence context if not present
        if not med.get("evidence"):
            start = med.get("start_pos", 0)
            end = med.get("end_pos", 0)
            sent_start = max(0, text.rfind('.', 0, start) + 1)
            sent_end = text.find('.', end)
            if sent_end == -1:
                sent_end = min(len(text), end + 100)
            med["evidence"] = text[sent_start:sent_end].strip()[:200]

        # Determine status from context
        evidence = med.get("evidence", "").lower()
        if any(w in evidence for w in ["stopped", "discontinued", "stop", "d/c"]):
            med["status"] = "discontinued"
        elif any(w in evidence for w in ["started", "new", "commence", "initiate"]):
            med["status"] = "new"
        elif any(w in evidence for w in ["changed", "increased", "decreased", "adjusted"]):
            med["status"] = "changed"
        elif any(w in evidence for w in ["continue", "regular", "current"]):
            med["status"] = "current"
        else:
            med["status"] = "unknown"

        # Extract duration if present
        duration_match = re.search(
            r'for\s+(\d+)\s*(days?|weeks?|months?)',
            evidence,
            re.IGNORECASE
        )
        if duration_match:
            med["duration"] = f"{duration_match.group(1)} {duration_match.group(2)}"

        return med
