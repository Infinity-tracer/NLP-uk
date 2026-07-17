"""
Stage 9: Temporal Reasoning - Temporal State Classification

Classifies entities by temporal state (current, historical, chronic, etc.)
"""

import re
from typing import Dict, List, Optional, Tuple
from datetime import datetime

from ..base import PipelineStage, StageResult, PipelineContext, StageStatus, StageRegistry


@StageRegistry.register
class TemporalReasoningStage(PipelineStage):
    """
    Temporal Reasoning Stage - Classify temporal states.

    Classifies entities as:
    - current: Active/ongoing
    - historical: Past/resolved
    - chronic: Long-standing
    - acute: Recent onset
    - resolved: No longer active
    - suspected: Under investigation

    Outputs:
    - temporal_classifications: Entity classifications
    - temporal_stats: Distribution of temporal states
    """

    # Temporal triggers by category
    TEMPORAL_TRIGGERS = {
        "current": [
            r'\bcurrent(?:ly)?\b',
            r'\bpresent(?:ing)?\b',
            r'\bongoing\b',
            r'\bactive\b',
            r'\btoday\b',
            r'\bnow\b',
            r'\bat\s+present\b',
            r'\brecent(?:ly)?\b',
            r'\bthis\s+(?:morning|afternoon|evening)\b',
        ],
        "historical": [
            r'\bhistory\s+of\b',
            r'\bh/o\b',
            r'\bpast\b',
            r'\bprevious(?:ly)?\b',
            r'\bformer(?:ly)?\b',
            r'\bknown\b',
            r'\bdiagnosed\s+(?:with\s+)?(?:in\s+)?\d{4}\b',
            r'\b\d+\s+(?:years?|months?)\s+ago\b',
            r'\bin\s+(?:19|20)\d{2}\b',
            r'\blong[\s-]?standing\b',
            r'\bestablished\b',
        ],
        "chronic": [
            r'\bchronic\b',
            r'\blong[\s-]?term\b',
            r'\bpersistent\b',
            r'\brecurrent\b',
            r'\bintermittent\b',
            r'\brelapsing\b',
            r'\bon(?:going)?\s+(?:for\s+)?\d+\s+(?:years?|months?)\b',
        ],
        "acute": [
            r'\bacute\b',
            r'\bsudden\b',
            r'\bnew\s+onset\b',
            r'\brecent\s+onset\b',
            r'\bstarted\s+(?:\d+\s+)?(?:hours?|days?|weeks?)\s+ago\b',
            r'\bwoke\s+up\s+with\b',
            r'\bthis\s+(?:morning|week)\b',
            r'\byesterday\b',
        ],
        "resolved": [
            r'\bresolved\b',
            r'\brecovered\b',
            r'\bcleared\b',
            r'\bimproved\b',
            r'\bno\s+longer\b',
            r'\bsettled\b',
            r'\bremission\b',
            r'\bcured\b',
        ],
        "suspected": [
            r'\bsuspected\b',
            r'\bpossible\b',
            r'\bquery\b',
            r'\blikely\b',
            r'\bprobable\b',
            r'\b\?\b',
            r'\bworking\s+diagnosis\b',
            r'\bdifferential\b',
            r'\bawait(?:ing)?\s+(?:confirmation|results?)\b',
        ],
    }

    # Section-based temporal defaults
    SECTION_DEFAULTS = {
        "past_medical_history": "historical",
        "pmh": "historical",
        "surgical_history": "historical",
        "family_history": "historical",
        "presenting_complaint": "current",
        "examination": "current",
        "diagnosis": "current",
        "treatment": "current",
        "follow_up": "current",
    }

    @property
    def name(self) -> str:
        return "temporal_reasoning"

    @property
    def description(self) -> str:
        return "Classify entities by temporal state"

    def get_dependencies(self) -> List[str]:
        return ["ner", "section_detection"]

    def validate_input(self, context: PipelineContext) -> bool:
        return bool(context.entities)

    def process(self, context: PipelineContext) -> StageResult:
        """Classify temporal states for entities."""
        result = StageResult(
            stage_name=self.name,
            status=StageStatus.RUNNING,
            confidence=0.0,
        )

        try:
            text = context.get_text()
            entities = context.entities

            if not entities:
                result.status = StageStatus.SKIPPED
                return result

            # Get sections for context
            sections = context.sections

            # Process each entity
            temporal_stats = {
                "current": 0,
                "historical": 0,
                "chronic": 0,
                "acute": 0,
                "resolved": 0,
                "suspected": 0,
            }

            classifications = []
            processed_count = 0

            for category, entity_list in entities.items():
                for entity in entity_list:
                    # Classify temporal state
                    temporal_state, confidence, trigger = self._classify_temporal(
                        entity, text, sections
                    )

                    # Update entity
                    entity["temporal_state"] = temporal_state
                    entity["temporal_confidence"] = confidence
                    entity["temporal_trigger"] = trigger

                    # Track stats
                    temporal_stats[temporal_state] = temporal_stats.get(temporal_state, 0) + 1
                    processed_count += 1

                    classifications.append({
                        "text": entity.get("text"),
                        "category": category,
                        "temporal_state": temporal_state,
                        "confidence": confidence,
                        "trigger": trigger,
                    })

            # Calculate overall confidence
            confidence = min(0.9, 0.7 + (processed_count * 0.005))

            # Build result
            result.status = StageStatus.DONE
            result.confidence = confidence
            result.items_processed = processed_count
            result.data = {
                "classifications": classifications,
                "stats": temporal_stats,
            }
            result.debug_data = {
                "sample_classifications": classifications[:20],
            }

            result.add_note(f"Classified {processed_count} entities")
            for state, count in temporal_stats.items():
                if count > 0:
                    result.add_note(f"  {state}: {count}")

            return result

        except Exception as e:
            result.status = StageStatus.ERROR
            result.error = str(e)
            return result

    def _classify_temporal(
        self,
        entity: Dict,
        text: str,
        sections: List[Dict]
    ) -> Tuple[str, float, Optional[str]]:
        """Classify temporal state for an entity."""
        # Get entity context
        evidence = entity.get("evidence", "")
        start_pos = entity.get("start_pos", 0)
        entity_text = entity.get("text", "").lower()

        # Method 1: Check for explicit temporal triggers in context
        for state, patterns in self.TEMPORAL_TRIGGERS.items():
            for pattern in patterns:
                match = re.search(pattern, evidence, re.IGNORECASE)
                if match:
                    return (state, 0.9, match.group())

        # Method 2: Check section context
        section_type = self._get_section_for_position(start_pos, sections)
        if section_type:
            section_lower = section_type.lower()
            if section_lower in self.SECTION_DEFAULTS:
                return (self.SECTION_DEFAULTS[section_lower], 0.75, f"section:{section_type}")

        # Method 3: Check for time expressions in entity text
        time_match = re.search(r'\b(\d+)\s*(years?|months?|weeks?|days?)\s*ago\b', evidence, re.IGNORECASE)
        if time_match:
            num = int(time_match.group(1))
            unit = time_match.group(2).lower()
            if unit.startswith("year") and num > 1:
                return ("historical", 0.85, time_match.group())
            elif unit.startswith("month") and num > 6:
                return ("historical", 0.8, time_match.group())
            elif unit.startswith("day") or (unit.startswith("week") and num <= 2):
                return ("current", 0.8, time_match.group())

        # Method 4: Check for year references
        year_match = re.search(r'\b(19|20)\d{2}\b', evidence)
        if year_match:
            year = int(year_match.group())
            current_year = datetime.now().year
            if current_year - year > 2:
                return ("historical", 0.75, year_match.group())

        # Default: current (most clinical entities are current unless indicated)
        return ("current", 0.6, None)

    def _get_section_for_position(
        self,
        position: int,
        sections: List[Dict]
    ) -> Optional[str]:
        """Get section type for a given position."""
        for section in sections:
            start_line = section.get("start_line", 0)
            end_line = section.get("end_line", 0)
            # This is approximate - would need char positions for accuracy
            if start_line <= position / 80 <= end_line:  # Rough estimate
                return section.get("type")
        return None
