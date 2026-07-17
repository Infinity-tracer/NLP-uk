"""
Stage 5: Negation Detection - Assertion Status Determination

Detects negation, uncertainty, and historical context in clinical text.
Assigns assertion status to entities.
"""

import re
from typing import Dict, List, Tuple, Optional

from ..base import PipelineStage, StageResult, PipelineContext, StageStatus, StageRegistry


@StageRegistry.register
class NegationDetectionStage(PipelineStage):
    """
    Negation Detection Stage - Determine assertion status.

    Detects:
    - Negation (no, denies, without)
    - Historical context (history of, previous)
    - Uncertainty (possible, query, suspected)
    - Family history (mother had, family history of)
    - Ruled out (excluded, ruled out)

    Outputs:
    - assertion_patterns: Detected assertion contexts
    - negation_spans: Text spans with negation scope
    """

    # Negation trigger patterns
    NEGATION_TRIGGERS = [
        r'\bno\b',
        r'\bnot\b',
        r'\bnone\b',
        r'\bdenies?\b',
        r'\bdenied\b',
        r'\bwithout\b',
        r'\babsent\b',
        r'\bnegative\b',
        r'\bnil\b',
        r'\bfree\s+(?:of|from)\b',
        r'\brules?\s+out\b',
        r'\bruled\s+out\b',
        r'\bexcludes?\b',
        r'\bexcluded\b',
        r'\bunremarkable\b',
        r'\bnormal\b',  # Can negate findings
    ]

    # Historical triggers
    HISTORICAL_TRIGGERS = [
        r'\bhistory\s+of\b',
        r'\bh/o\b',
        r'\bpast\s+(?:medical\s+)?history\b',
        r'\bpmh\b',
        r'\bprevious(?:ly)?\b',
        r'\bformer(?:ly)?\b',
        r'\bknown\b',
        r'\bbackground\b',
        r'\blong[\s-]?standing\b',
        r'\b\d+\s*(?:years?|months?)\s+ago\b',
        r'\bin\s+(?:19|20)\d{2}\b',
        r'\bresolved\b',
    ]

    # Uncertainty triggers
    UNCERTAINTY_TRIGGERS = [
        r'\bpossible\b',
        r'\bpossibly\b',
        r'\bprobable\b',
        r'\bprobably\b',
        r'\bsuspected?\b',
        r'\bquery\b',
        r'\b\?\b',
        r'\blikely\b',
        r'\bmay\s+(?:be|have)\b',
        r'\bmight\b',
        r'\bcould\b',
        r'\bquestionable\b',
        r'\bdifferential\b',
        r'\bworking\s+diagnosis\b',
        r'\bconsider\b',
    ]

    # Family history triggers
    FAMILY_TRIGGERS = [
        r'\bfamily\s+history\b',
        r'\bfh\b',
        r'\bfhx\b',
        r'\bmother\s+(?:had|has|with)\b',
        r'\bfather\s+(?:had|has|with)\b',
        r'\bsibling\s+(?:had|has|with)\b',
        r'\bbrother\s+(?:had|has|with)\b',
        r'\bsister\s+(?:had|has|with)\b',
        r'\bfamilial\b',
        r'\bhereditary\b',
    ]

    # Scope termination patterns
    SCOPE_TERMINATORS = [
        r'\bbut\b',
        r'\bhowever\b',
        r'\balthough\b',
        r'\bexcept\b',
        r'\bapart\s+from\b',
        r'\.\s',
        r',\s+(?:and|with|but)\b',
    ]

    @property
    def name(self) -> str:
        return "negation_detection"

    @property
    def description(self) -> str:
        return "Detect negation and assertion status in clinical text"

    def get_dependencies(self) -> List[str]:
        return ["section_detection"]

    def validate_input(self, context: PipelineContext) -> bool:
        return bool(context.get_text())

    def process(self, context: PipelineContext) -> StageResult:
        """Detect negation and assertion patterns."""
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

            # Process text by sentences
            sentences = self._split_sentences(text)

            # Detect patterns in each sentence
            assertion_patterns = []
            stats = {
                "negated": 0,
                "historical": 0,
                "uncertain": 0,
                "family_history": 0,
                "present": 0,
            }

            for sent_idx, sentence in enumerate(sentences):
                # Find negation triggers
                negations = self._find_triggers(sentence, self.NEGATION_TRIGGERS, "absent")
                for n in negations:
                    n["sentence_idx"] = sent_idx
                    n["sentence"] = sentence
                assertion_patterns.extend(negations)
                stats["negated"] += len(negations)

                # Find historical triggers
                historical = self._find_triggers(sentence, self.HISTORICAL_TRIGGERS, "historical")
                for h in historical:
                    h["sentence_idx"] = sent_idx
                    h["sentence"] = sentence
                assertion_patterns.extend(historical)
                stats["historical"] += len(historical)

                # Find uncertainty triggers
                uncertain = self._find_triggers(sentence, self.UNCERTAINTY_TRIGGERS, "possible")
                for u in uncertain:
                    u["sentence_idx"] = sent_idx
                    u["sentence"] = sentence
                assertion_patterns.extend(uncertain)
                stats["uncertain"] += len(uncertain)

                # Find family history triggers
                family = self._find_triggers(sentence, self.FAMILY_TRIGGERS, "family_history")
                for f in family:
                    f["sentence_idx"] = sent_idx
                    f["sentence"] = sentence
                assertion_patterns.extend(family)
                stats["family_history"] += len(family)

            # Calculate scope for each trigger
            for pattern in assertion_patterns:
                pattern["scope"] = self._calculate_scope(
                    pattern["sentence"],
                    pattern["trigger_end"]
                )

            # Calculate confidence
            total_patterns = sum(stats.values())
            confidence = min(0.95, 0.7 + (total_patterns * 0.02))

            # Build result
            result.status = StageStatus.DONE
            result.confidence = confidence
            result.items_processed = len(assertion_patterns)
            result.data = {
                "assertion_patterns": assertion_patterns,
                "stats": stats,
                "sentence_count": len(sentences),
            }
            result.debug_data = {
                "sample_patterns": assertion_patterns[:20],
            }

            result.add_note(f"Found {len(assertion_patterns)} assertion patterns")
            for status, count in stats.items():
                if count > 0:
                    result.add_note(f"  {status}: {count}")

            return result

        except Exception as e:
            result.status = StageStatus.ERROR
            result.error = str(e)
            return result

    def _split_sentences(self, text: str) -> List[str]:
        """Split text into sentences."""
        # Simple sentence splitting
        sentences = re.split(r'(?<=[.!?])\s+', text)
        return [s.strip() for s in sentences if s.strip()]

    def _find_triggers(
        self,
        text: str,
        patterns: List[str],
        assertion_type: str
    ) -> List[Dict]:
        """Find trigger patterns in text."""
        results = []

        for pattern in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                results.append({
                    "trigger": match.group(),
                    "trigger_start": match.start(),
                    "trigger_end": match.end(),
                    "assertion_type": assertion_type,
                    "confidence": 0.85,
                })

        return results

    def _calculate_scope(self, sentence: str, trigger_end: int) -> Dict:
        """Calculate the scope of a negation/assertion trigger."""
        # Default scope: rest of sentence after trigger
        scope_text = sentence[trigger_end:].strip()

        # Find scope terminator
        scope_end = len(scope_text)
        for pattern in self.SCOPE_TERMINATORS:
            match = re.search(pattern, scope_text, re.IGNORECASE)
            if match:
                scope_end = min(scope_end, match.start())

        scope_text = scope_text[:scope_end].strip()

        # Also look backward for pre-trigger scope (e.g., "chest pain - no")
        pre_scope = sentence[:trigger_end].strip()
        # Take last phrase before trigger
        pre_match = re.search(r'([^,;.]+)$', pre_scope)
        if pre_match:
            pre_scope = pre_match.group(1).strip()
        else:
            pre_scope = ""

        return {
            "forward": scope_text[:100],  # Limit scope length
            "backward": pre_scope[-50:] if pre_scope else "",
        }

    def get_assertion_for_span(
        self,
        text: str,
        start: int,
        end: int,
        patterns: List[Dict]
    ) -> Tuple[str, float, Optional[str]]:
        """
        Get assertion status for a text span based on nearby patterns.

        Returns (assertion_type, confidence, trigger)
        """
        span_text = text[start:end]

        # Check each pattern to see if span falls within scope
        for pattern in patterns:
            sent = pattern.get("sentence", "")
            scope = pattern.get("scope", {})

            # Check if span text appears in scope
            forward_scope = scope.get("forward", "")
            backward_scope = scope.get("backward", "")

            if span_text.lower() in forward_scope.lower():
                return (
                    pattern["assertion_type"],
                    pattern["confidence"],
                    pattern["trigger"]
                )

            if span_text.lower() in backward_scope.lower():
                return (
                    pattern["assertion_type"],
                    pattern["confidence"] * 0.8,  # Lower confidence for backward scope
                    pattern["trigger"]
                )

        # Default: present
        return ("present", 0.7, None)
