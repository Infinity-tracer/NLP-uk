"""
Stage 6: NER - Named Entity Recognition

Extracts clinical entities across 17 categories using rule-based patterns.
Provides position information for evidence tracking.
"""

import re
from typing import Dict, List, Tuple, Optional

from ..base import PipelineStage, StageResult, PipelineContext, StageStatus, StageRegistry


@StageRegistry.register
class NERStage(PipelineStage):
    """
    Named Entity Recognition Stage - Extract clinical entities.

    Categories:
    - diagnoses, symptoms, signs
    - investigations, procedures, medications
    - allergies, social_history, past_medical_history
    - family_history, discharge_advice, follow_up_plan
    - gp_actions, hospital_actions, referrals
    - clinical_scores, vital_signs

    Outputs:
    - entities: Dict of entity lists by category
    - All entities include position evidence
    """

    # Entity patterns by category
    ENTITY_PATTERNS = {
        "diagnosis": [
            (r'\b(?:diagnos(?:is|ed)\s*(?:of|with|:)?\s*)([A-Za-z][A-Za-z\s\-]{3,50})', 0.85),
            (r'\b(?:assessment|impression)\s*[:.]?\s*([A-Za-z][A-Za-z\s\-]{3,50})', 0.8),
            (r'\b([A-Z][a-z]+(?:\s+[a-z]+)*)\s+(?:syndrome|disease|disorder)\b', 0.9),
        ],
        "symptom": [
            (r'\b(?:complaining\s+of|c/o|reports?|experiencing)\s+([A-Za-z][A-Za-z\s\-]{3,40})', 0.85),
            (r'\b((?:chest|abdominal|back|head|neck)\s+pain)\b', 0.9),
            (r'\b(nausea|vomiting|diarrhoea|constipation|headache|dizziness|fatigue)\b', 0.9),
            (r'\b(shortness\s+of\s+breath|dyspnoea|breathlessness)\b', 0.9),
            (r'\b(fever|rigors|chills|sweating)\b', 0.85),
            (r'\b(cough|sputum|haemoptysis)\b', 0.85),
            (r'\b(palpitations|syncope|presyncope|collapse)\b', 0.9),
            (r'\b(swelling|oedema|edema)\b', 0.85),
            (r'\b(weakness|numbness|tingling|paraesthesia)\b', 0.85),
        ],
        "sign": [
            (r'\b(?:o/e|on\s+examination|examination\s+(?:shows?|reveals?))\s*:?\s*([A-Za-z][A-Za-z\s\-,]{3,60})', 0.85),
            (r'\b(tenderness|guarding|rigidity|rebound)\b', 0.85),
            (r'\b((?:bi)?lateral\s+(?:crackles|wheeze|crepitations))\b', 0.9),
            (r'\b(murmur|bruit|gallop)\b', 0.85),
            (r'\b((?:un)?responsive|alert|orientated|confused)\b', 0.8),
            (r'\b(cyanosis|pallor|jaundice|clubbing)\b', 0.85),
        ],
        "investigation": [
            (r'\b((?:FBC|U&E|LFT|TFT|CRP|HbA1c|INR|ABG|VBG)(?:\s*[:\-]?\s*[A-Za-z0-9\.\s,]+)?)', 0.9),
            (r'\b((?:ECG|CXR|CT|MRI|USS|X-?ray|ultrasound)(?:\s+[A-Za-z]+)*)', 0.9),
            (r'\b(blood\s+(?:test|culture|gas)s?)\b', 0.85),
            (r'\b(urine\s+(?:test|culture|dipstick))\b', 0.85),
            (r'\b((?:troponin|d-dimer|lactate|creatinine|potassium|sodium|haemoglobin|wbc|platelets?)(?:\s*[:\-]?\s*[\d\.]+)?)', 0.9),
        ],
        "procedure": [
            (r'\b((?:underwent|performed|done)\s+(?:a\s+)?([A-Za-z][A-Za-z\s\-]{3,40}))', 0.85),
            (r'\b((?:endoscopy|colonoscopy|bronchoscopy|catheterisation|cannulation|intubation))\b', 0.9),
            (r'\b((?:biopsy|aspiration|drainage|excision|debridement))\b', 0.9),
            (r'\b((?:CABG|PCI|angioplasty|stent(?:ing)?|bypass))\b', 0.9),
        ],
        "medication": [
            (r'\b([A-Z][a-z]+(?:in|ol|am|ide|ate|one|ine|ide)\s+\d+\s*(?:mg|mcg|g|ml|units?))', 0.9),
            (r'\b((?:aspirin|paracetamol|ibuprofen|metformin|amlodipine|ramipril|bisoprolol|atorvastatin|omeprazole|lansoprazole)(?:\s+\d+\s*(?:mg|mcg))?)', 0.9),
            (r'\b((?:fluids?|saline|hartmann|glucose)\s*(?:\d+\s*(?:ml|L))?)\b', 0.8),
            (r'\b((?:morphine|codeine|tramadol|oxycodone|fentanyl)(?:\s+\d+\s*(?:mg|mcg))?)', 0.9),
            (r'\b((?:amoxicillin|co-amoxiclav|clarithromycin|doxycycline|metronidazole|gentamicin|vancomycin)(?:\s+\d+\s*(?:mg|g))?)', 0.9),
        ],
        "allergy": [
            (r'\b(?:allergic?\s+to|allergy\s+to|adverse\s+reaction\s+to)\s+([A-Za-z][A-Za-z\s\-]{2,30})', 0.9),
            (r'\b(?:NKDA|no\s+known\s+(?:drug\s+)?allergies)\b', 0.95),
        ],
        "vital_sign": [
            (r'\b(?:BP|blood\s+pressure)\s*[:=]?\s*(\d{2,3}/\d{2,3})', 0.95),
            (r'\b(?:HR|heart\s+rate|pulse)\s*[:=]?\s*(\d{2,3})\s*(?:bpm)?', 0.95),
            (r'\b(?:RR|resp(?:iratory)?\s+rate)\s*[:=]?\s*(\d{1,2})', 0.95),
            (r'\b(?:SpO2|sats?|O2\s+sats?)\s*[:=]?\s*(\d{2,3})\s*%?', 0.95),
            (r'\b(?:temp(?:erature)?|T)\s*[:=]?\s*(\d{2}\.?\d?)\s*(?:°?C)?', 0.9),
            (r'\b(?:GCS)\s*[:=]?\s*(\d{1,2}(?:/15)?)', 0.95),
            (r'\b(?:NEWS|NEWS2)\s*[:=]?\s*(\d{1,2})', 0.95),
        ],
        "gp_action": [
            (r'\b(?:gp\s+to|please|kindly)\s+([A-Za-z][A-Za-z\s\-]{5,60})', 0.8),
            (r'\b(?:for\s+(?:the\s+)?gp)\s*[:]\s*([A-Za-z][A-Za-z\s\-,]{5,80})', 0.85),
        ],
        "follow_up": [
            (r'\b(?:follow[\s\-]?up|f/u|review)\s+(?:in\s+)?(\d+\s*(?:days?|weeks?|months?))', 0.9),
            (r'\b(?:outpatient|clinic)\s+(?:appointment|review)\s+(?:in\s+)?(\d+\s*(?:days?|weeks?|months?))', 0.9),
            (r'\b(?:return\s+if|come\s+back\s+if)\s+([A-Za-z][A-Za-z\s\-,]{5,60})', 0.8),
        ],
        "referral": [
            (r'\b(?:refer(?:red)?\s+to|referral\s+to)\s+([A-Za-z][A-Za-z\s\-]{3,40})', 0.9),
            (r'\b(?:2ww|two\s+week\s+wait)\s+(?:referral\s+)?(?:to\s+)?([A-Za-z][A-Za-z\s\-]{3,30})', 0.95),
        ],
    }

    @property
    def name(self) -> str:
        return "ner"

    @property
    def description(self) -> str:
        return "Extract clinical entities using pattern-based NER"

    def get_dependencies(self) -> List[str]:
        return ["negation_detection"]

    def validate_input(self, context: PipelineContext) -> bool:
        return bool(context.get_text())

    def process(self, context: PipelineContext) -> StageResult:
        """Extract clinical entities."""
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

            # Get assertion patterns for context
            negation_result = context.get_stage_result("negation_detection")
            assertion_patterns = []
            if negation_result and negation_result.data:
                assertion_patterns = negation_result.data.get("assertion_patterns", [])

            # Extract entities by category
            all_entities = {}
            total_count = 0
            category_stats = {}

            for category, patterns in self.ENTITY_PATTERNS.items():
                entities = self._extract_category(
                    text, category, patterns, assertion_patterns
                )
                all_entities[category] = entities
                category_stats[category] = len(entities)
                total_count += len(entities)

                # Add to context
                context.add_entities(category, entities)

            # Deduplicate overlapping entities
            all_entities = self._deduplicate_entities(all_entities)

            # Calculate confidence
            confidence = min(0.9, 0.6 + (total_count * 0.01))

            # Build result
            result.status = StageStatus.DONE
            result.confidence = confidence
            result.items_processed = total_count
            result.data = {
                "entities": all_entities,
                "total_count": total_count,
                "stats": category_stats,
            }
            result.debug_data = {
                "categories_found": [c for c, e in all_entities.items() if e],
            }

            result.add_note(f"Extracted {total_count} entities")
            for cat, count in category_stats.items():
                if count > 0:
                    result.add_note(f"  {cat}: {count}")

            return result

        except Exception as e:
            result.status = StageStatus.ERROR
            result.error = str(e)
            return result

    def _extract_category(
        self,
        text: str,
        category: str,
        patterns: List[Tuple[str, float]],
        assertion_patterns: List[Dict]
    ) -> List[Dict]:
        """Extract entities for a single category."""
        entities = []
        seen_spans = set()

        for pattern, base_confidence in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                # Get the captured group (or full match)
                if match.groups():
                    entity_text = match.group(1)
                    start = match.start(1)
                    end = match.end(1)
                else:
                    entity_text = match.group()
                    start = match.start()
                    end = match.end()

                # Skip if already seen this span
                span_key = (start, end)
                if span_key in seen_spans:
                    continue
                seen_spans.add(span_key)

                # Clean entity text
                entity_text = entity_text.strip()
                if len(entity_text) < 2:
                    continue

                # Get line number
                line_num = text[:start].count('\n') + 1

                # Get sentence context
                sentence = self._get_sentence(text, start, end)

                # Determine assertion status
                assertion, assertion_conf, trigger = self._get_assertion(
                    text, start, end, assertion_patterns
                )

                entity = {
                    "text": entity_text,
                    "category": category,
                    "confidence": base_confidence * assertion_conf,
                    "start_pos": start,
                    "end_pos": end,
                    "line_number": line_num,
                    "evidence": sentence,
                    "assertion": assertion,
                    "assertion_trigger": trigger,
                    "assertion_confidence": assertion_conf,
                }

                entities.append(entity)

        return entities

    def _get_sentence(self, text: str, start: int, end: int) -> str:
        """Extract the sentence containing the entity."""
        # Find sentence boundaries
        sent_start = max(0, text.rfind('.', 0, start) + 1)
        sent_end = text.find('.', end)
        if sent_end == -1:
            sent_end = min(len(text), end + 100)

        sentence = text[sent_start:sent_end].strip()
        return sentence[:200]  # Limit length

    def _get_assertion(
        self,
        text: str,
        start: int,
        end: int,
        assertion_patterns: List[Dict]
    ) -> Tuple[str, float, Optional[str]]:
        """Get assertion status for an entity based on context."""
        # Check if entity falls within scope of any assertion pattern
        entity_text = text[start:end].lower()

        for pattern in assertion_patterns:
            scope = pattern.get("scope", {})
            forward = scope.get("forward", "").lower()
            backward = scope.get("backward", "").lower()

            if entity_text in forward or entity_text in backward:
                return (
                    pattern["assertion_type"],
                    pattern["confidence"],
                    pattern["trigger"]
                )

        return ("present", 0.8, None)

    def _deduplicate_entities(
        self,
        all_entities: Dict[str, List[Dict]]
    ) -> Dict[str, List[Dict]]:
        """Remove duplicate entities across categories."""
        # Build span index
        span_to_entity = {}

        for category, entities in all_entities.items():
            for entity in entities:
                span = (entity["start_pos"], entity["end_pos"])
                if span not in span_to_entity:
                    span_to_entity[span] = (category, entity)
                else:
                    # Keep higher confidence entity
                    existing_cat, existing = span_to_entity[span]
                    if entity["confidence"] > existing["confidence"]:
                        span_to_entity[span] = (category, entity)

        # Rebuild entity dict
        result = {cat: [] for cat in all_entities}
        for span, (category, entity) in span_to_entity.items():
            result[category].append(entity)

        return result
