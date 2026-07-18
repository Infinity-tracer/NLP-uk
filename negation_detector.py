"""
Clinical Negation Detection Engine

Detects assertion status for medical entities:
- Present: Currently active finding
- Absent: Explicitly negated (No fever, Denies pain)
- Historical: Past finding (History of MI)
- FamilyHistory: Family member has condition
- Possible: Uncertain (Query TIA, ?PE)
- RuledOut: Explicitly excluded

Uses NegEx-style algorithm with NHS/UK clinical language patterns.
"""

import re
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Set


class AssertionStatus(Enum):
    """Assertion status for clinical entities"""
    PRESENT = "present"
    ABSENT = "absent"
    HISTORICAL = "historical"
    FAMILY_HISTORY = "family_history"
    POSSIBLE = "possible"
    RULED_OUT = "ruled_out"


@dataclass
class NegationResult:
    """Result of negation detection for an entity"""
    entity_text: str
    assertion: AssertionStatus
    trigger_text: Optional[str] = None
    trigger_type: Optional[str] = None
    start_pos: int = 0
    end_pos: int = 0
    confidence: float = 1.0
    scope_text: Optional[str] = None


@dataclass
class DetectionStats:
    """Statistics from negation detection"""
    total_entities: int = 0
    present: int = 0
    absent: int = 0
    historical: int = 0
    family_history: int = 0
    possible: int = 0
    ruled_out: int = 0


# =============================================================================
# NEGATION TRIGGERS - Pre-negation (appear BEFORE the entity)
# =============================================================================

PRE_NEGATION_TRIGGERS = [
    # Simple negation
    r"\bno\b",
    r"\bnil\b",
    r"\bnot\b",
    r"\bnever\b",
    r"\bnone\b",
    r"\bwithout\b",
    r"\babsent\b",
    r"\blacks?\b",
    r"\blacking\b",

    # Clinical negation
    r"\bdenies\b",
    r"\bdeny\b",
    r"\bdenied\b",
    r"\bdenying\b",
    r"\bnegative\s+for\b",
    r"\bneg\s+for\b",
    r"\bneg\.?\s+for\b",
    r"\bfree\s+from\b",
    r"\bfree\s+of\b",
    r"\bno\s+evidence\s+of\b",
    r"\bno\s+signs?\s+of\b",
    r"\bno\s+symptoms?\s+of\b",
    r"\bno\s+history\s+of\b",
    r"\bno\s+hx\s+of\b",
    r"\bno\s+h/o\b",
    r"\bno\s+significant\b",
    r"\bwithout\s+evidence\s+of\b",
    r"\bwithout\s+signs?\s+of\b",
    r"\bfailed\s+to\s+reveal\b",
    r"\bunable\s+to\s+detect\b",
    r"\bdoes\s+not\s+have\b",
    r"\bdoesn'?t\s+have\b",
    r"\bhas\s+no\b",
    r"\bhad\s+no\b",
    r"\bno\s+acute\b",
    r"\bno\s+obvious\b",
    r"\bno\s+definite\b",
    r"\bno\s+overt\b",
    r"\bno\s+clinical\b",
    r"\bno\s+radiological\b",
    r"\bnot\s+suggestive\s+of\b",
    r"\bnot\s+consistent\s+with\b",
    r"\bnot\s+indicative\s+of\b",
    r"\bexcludes?\b",
    r"\bexcluded\b",
    r"\bexcluding\b",
    r"\brules?\s+out\b",
    r"\bruled\s+out\b",
    r"\bruling\s+out\b",
    r"\bunremarkable\s+for\b",
    r"\bnormal\b",

    # NHS/UK specific
    r"\bNAD\b",  # No Abnormality Detected
    r"\bNIL\b",
    r"\bNKDA\b",  # No Known Drug Allergies (context: allergies)
    r"\bNKA\b",   # No Known Allergies
    r"\bnil\s+recent\b",  # "Nil recent trauma"
    r"\bnil\s+urinary\b",  # "Nil urinary symptoms"
    r"\bnil\s+new\b",  # "Nil new symptoms"
    r"\bnil\s+focal\b",  # "Nil focal neurology"
    r"\bno\s+recent\b",  # "No recent history"
    r"\bno\s+urinary\b",  # "No urinary incontinence"
    r"\bno\s+faecal\b",  # "No faecal incontinence"
    r"\bno\s+bowel\b",  # "No bowel symptoms"
    r"\bno\s+new\b",  # "No new symptoms"
    r"\bno\s+focal\b",  # "No focal neurology"
    r"\bno\s+concerns?\b",  # "No concerns"
    r"\bnot\s+complaining\s+of\b",  # "Not complaining of"
]

# =============================================================================
# POST-NEGATION TRIGGERS - Appear AFTER the entity
# =============================================================================

POST_NEGATION_TRIGGERS = [
    r"\babsent\b",
    r"\bnegative\b",
    r"\bneg\b",
    r"\bnot\s+present\b",
    r"\bnot\s+seen\b",
    r"\bnot\s+detected\b",
    r"\bnot\s+identified\b",
    r"\bnot\s+found\b",
    r"\bnot\s+observed\b",
    r"\bwas\s+negative\b",
    r"\bwere\s+negative\b",
    r"\bis\s+negative\b",
    r"\bare\s+negative\b",
    r"\bruled\s+out\b",
    r"\bexcluded\b",
    r"\bhas\s+been\s+excluded\b",
    r"\bunlikely\b",
    r"\bnot\s+demonstrated\b",
    r"\bdenied\b",
]

# =============================================================================
# PSEUDO-NEGATION - Look like negation but aren't
# =============================================================================

PSEUDO_NEGATION = [
    r"\bnot\s+only\b",
    r"\bnot\s+necessarily\b",
    r"\bno\s+change\b",
    r"\bno\s+increase\b",
    r"\bno\s+decrease\b",
    r"\bno\s+improvement\b",
    r"\bno\s+significant\s+change\b",
    r"\bwithout\s+difficulty\b",
    r"\bwithout\s+incident\b",
    r"\bwithout\s+complication\b",
    r"\bgram\s+negative\b",
    r"\brh\s+negative\b",
    r"\brhesus\s+negative\b",
    r"\bhiv\s+negative\b",
    r"\bhep\s+b\s+negative\b",
    r"\bhep\s+c\s+negative\b",
    r"\bnot\s+drain\b",
    r"\bnot\s+certain\b",
    r"\bno\s+longer\b",
    r"\bno\s+further\b",
    r"\bno\s+additional\b",
]

# =============================================================================
# HISTORICAL TRIGGERS - Past findings
# =============================================================================

HISTORICAL_TRIGGERS = [
    r"\bhistory\s+of\b",
    r"\bh/o\b",
    r"\bhx\s+of\b",
    r"\bhx:\b",
    r"\bpmh\b",
    r"\bpast\s+medical\s+history\b",
    r"\bbackground\s+of\b",
    r"\bbackground:\b",
    r"\bprevious\b",
    r"\bpreviously\b",
    r"\bprior\b",
    r"\bpast\b",
    r"\bformer\b",
    r"\bformerly\b",
    r"\bchronic\b",
    r"\blong-?standing\b",
    r"\bknown\b",
    r"\bestablished\b",
    r"\bdiagnosed\s+with\b",
    r"\bdiagnosed\s+in\b",
    r"\bsuffered\s+from\b",
    r"\bhad\b",
    r"\b\d+\s*(?:year|yr|month|week)s?\s+ago\b",
    r"\bin\s+(?:19|20)\d{2}\b",
    r"\bchildhood\b",
    r"\badolescent\b",
    r"\byouth\b",
    r"\bas\s+a\s+child\b",
    r"\bremote\s+history\b",
    r"\bdistant\s+history\b",
    r"\bwhen\s+younger\b",
    r"\bback\s+in\b",
]

# =============================================================================
# FAMILY HISTORY TRIGGERS
# =============================================================================

FAMILY_HISTORY_TRIGGERS = [
    r"\bfamily\s+history\s+of\b",
    r"\bfhx\b",
    r"\bfh:\b",
    r"\bfh\s+of\b",
    r"\bfamilial\b",
    r"\bmother\s+(?:has|had|with|diagnosed)\b",
    r"\bfather\s+(?:has|had|with|diagnosed)\b",
    r"\bparent\s+(?:has|had|with|diagnosed)\b",
    r"\bparents?\s+(?:have|had|with)\b",
    r"\bbrother\s+(?:has|had|with|diagnosed)\b",
    r"\bsister\s+(?:has|had|with|diagnosed)\b",
    r"\bsibling\s+(?:has|had|with|diagnosed)\b",
    r"\bgrandmother\s+(?:has|had|with|diagnosed)\b",
    r"\bgrandfather\s+(?:has|had|with|diagnosed)\b",
    r"\bgrandparent\s+(?:has|had|with)\b",
    r"\baunt\s+(?:has|had|with|diagnosed)\b",
    r"\buncle\s+(?:has|had|with|diagnosed)\b",
    r"\brelative\s+(?:has|had|with|diagnosed)\b",
    r"\bruns\s+in\s+(?:the\s+)?family\b",
    r"\bheritable\b",
    r"\bhereditary\b",
    r"\binherited\b",
    r"\bgenetic\s+predisposition\b",
    r"\bmaternal\s+history\b",
    r"\bpaternal\s+history\b",
    r"\b(?:1st|first)\s+degree\s+relative\b",
    r"\b(?:2nd|second)\s+degree\s+relative\b",
]

# =============================================================================
# UNCERTAINTY TRIGGERS - Possible/Suspected
# =============================================================================

UNCERTAINTY_TRIGGERS = [
    r"\bpossible\b",
    r"\bpossibly\b",
    r"\bprobable\b",
    r"\bprobably\b",
    r"\blikely\b",
    r"\bsuspected\b",
    r"\bsuspect\b",
    r"\bsuspicion\s+of\b",
    r"\bsuspicious\s+for\b",
    r"\bquery\b",
    r"\bqueried\b",
    r"\b\?\s*",  # Question mark before entity
    r"\buncertain\b",
    r"\bequivocal\b",
    r"\bindeterminate\b",
    r"\bquestionable\b",
    r"\bcannot\s+exclude\b",
    r"\bcannot\s+rule\s+out\b",
    r"\bcan'?t\s+exclude\b",
    r"\bcan'?t\s+rule\s+out\b",
    r"\bmay\s+have\b",
    r"\bmight\s+have\b",
    r"\bcould\s+be\b",
    r"\bmay\s+be\b",
    r"\bmight\s+be\b",
    r"\bappears\s+to\s+be\b",
    r"\bseems\s+to\s+be\b",
    r"\bsuggests?\b",
    r"\bsuggestive\s+of\b",
    r"\bconsistent\s+with\b",
    r"\bin\s+keeping\s+with\b",
    r"\braise[sd]?\s+(?:the\s+)?possibility\b",
    r"\bdifferential\s+includes?\b",
    r"\bddx\b",
    r"\bworking\s+diagnosis\b",
    r"\bprovisional\b",
    r"\bpresumptive\b",
    r"\bpresumably\b",
    r"\bpresumed\b",
    r"\bto\s+be\s+confirmed\b",
    r"\btbc\b",
    r"\bawait(?:ing|s)?\s+confirmation\b",
    r"\bpending\s+confirmation\b",
    r"\b\?\b",  # Standalone question mark
]

# =============================================================================
# RULED OUT TRIGGERS - Explicitly excluded diagnoses
# =============================================================================

RULED_OUT_TRIGGERS = [
    r"\bruled\s+out\b",
    r"\brule\s+out\b",
    r"\br/o\b",
    r"\bexcluded\b",
    r"\bexclude[sd]?\b",
    r"\bunlikely\b",
    r"\bhighly\s+unlikely\b",
    r"\bdoes\s+not\s+support\b",
    r"\bdoesn'?t\s+support\b",
    r"\bagainst\s+(?:a\s+)?diagnosis\b",
    r"\bno\s+evidence\s+to\s+support\b",
    r"\bnot\s+(?:in\s+)?favour\b",
    r"\bnot\s+(?:in\s+)?favor\b",
    r"\bdisproved\b",
    r"\bdisproven\b",
    r"\brefuted\b",
    r"\brejected\b",
    r"\bdismissed\b",
    r"\bdiscounted\b",
    r"\bhas\s+been\s+ruled\s+out\b",
    r"\bwas\s+ruled\s+out\b",
    r"\beffectively\s+ruled\s+out\b",
    r"\bconfidently\s+excluded\b",
]

# =============================================================================
# SCOPE TERMINATORS - End of negation scope
# =============================================================================

SCOPE_TERMINATORS = [
    # Conjunctions that typically end negation scope
    r"\bbut\b",
    r"\bhowever\b",
    r"\balthough\b",
    r"\bthough\b",
    r"\byet\b",
    r"\bnevertheless\b",
    r"\bnonetheless\b",
    r"\bexcept\b",
    r"\bapart\s+from\b",
    r"\bother\s+than\b",
    r"\basides?\s+from\b",
    r"\bstill\b",
    r"\bwhich\s+is\b",
    r"\bwho\s+is\b",
    r"\bthat\s+is\b",
    r"\bwhereas\b",
    r"\bwhile\b",
    r"\bwhilst\b",

    # New section indicators
    r"\b(?:assessment|plan|impression|diagnosis|treatment):\s*",
    r"\b(?:examination|investigations?|results?):\s*",
]

# Punctuation that ends scope
SCOPE_PUNCTUATION = {'.', ';', ':', '\n', '\r'}


class ClinicalNegationDetector:
    """
    Clinical negation detection using NegEx-style algorithm.

    Detects assertion status for medical entities:
    - Present: Active finding
    - Absent: Negated
    - Historical: Past event
    - FamilyHistory: Family member
    - Possible: Uncertain
    - RuledOut: Explicitly excluded
    """

    def __init__(self, window_size: int = 6):
        """
        Initialize negation detector.

        Args:
            window_size: Number of words to check for triggers before/after entity
        """
        self.window_size = window_size

        # Compile all patterns for efficiency
        self._pre_negation = self._compile_patterns(PRE_NEGATION_TRIGGERS)
        self._post_negation = self._compile_patterns(POST_NEGATION_TRIGGERS)
        self._pseudo_negation = self._compile_patterns(PSEUDO_NEGATION)
        self._historical = self._compile_patterns(HISTORICAL_TRIGGERS)
        self._family_history = self._compile_patterns(FAMILY_HISTORY_TRIGGERS)
        self._uncertainty = self._compile_patterns(UNCERTAINTY_TRIGGERS)
        self._ruled_out = self._compile_patterns(RULED_OUT_TRIGGERS)
        self._terminators = self._compile_patterns(SCOPE_TERMINATORS)

    def _compile_patterns(self, patterns: List[str]) -> List[re.Pattern]:
        """Compile regex patterns with case insensitivity"""
        compiled = []
        for pattern in patterns:
            try:
                compiled.append(re.compile(pattern, re.IGNORECASE))
            except re.error:
                pass  # Skip invalid patterns
        return compiled

    def _find_trigger(
        self,
        text: str,
        patterns: List[re.Pattern]
    ) -> Optional[Tuple[str, int, int]]:
        """Find first matching trigger pattern in text"""
        for pattern in patterns:
            match = pattern.search(text)
            if match:
                return (match.group(), match.start(), match.end())
        return None

    def _contains_trigger(self, text: str, patterns: List[re.Pattern]) -> bool:
        """Check if text contains any trigger pattern"""
        for pattern in patterns:
            if pattern.search(text):
                return True
        return False

    def _is_pseudo_negation(self, text: str) -> bool:
        """Check if text contains pseudo-negation (looks like negation but isn't)"""
        return self._contains_trigger(text, self._pseudo_negation)

    def _get_scope_before(self, text: str, entity_start: int) -> str:
        """Get text before entity within negation scope"""
        # Find scope start (beginning of text or after terminator/punctuation)
        scope_start = 0

        # Check for terminators
        for pattern in self._terminators:
            for match in pattern.finditer(text[:entity_start]):
                if match.end() > scope_start:
                    scope_start = match.end()

        # Check for scope-ending punctuation
        for i, char in enumerate(text[:entity_start]):
            if char in SCOPE_PUNCTUATION:
                if i + 1 > scope_start:
                    scope_start = i + 1

        return text[scope_start:entity_start].strip()

    def _get_scope_after(self, text: str, entity_end: int) -> str:
        """Get text after entity within negation scope"""
        # Find scope end (end of text or before terminator/punctuation)
        scope_end = len(text)

        remaining = text[entity_end:]

        # Check for terminators
        for pattern in self._terminators:
            match = pattern.search(remaining)
            if match:
                potential_end = entity_end + match.start()
                if potential_end < scope_end:
                    scope_end = potential_end

        # Check for scope-ending punctuation
        for i, char in enumerate(remaining):
            if char in SCOPE_PUNCTUATION:
                potential_end = entity_end + i
                if potential_end < scope_end:
                    scope_end = potential_end
                break

        return text[entity_end:scope_end].strip()

    def _word_distance(self, text: str) -> int:
        """Count words in text"""
        words = text.split()
        return len(words)

    def detect_assertion(
        self,
        text: str,
        entity_text: str,
        entity_start: int,
        entity_end: int
    ) -> NegationResult:
        """
        Detect assertion status for a single entity.

        Args:
            text: Full clinical text
            entity_text: The entity text
            entity_start: Start position of entity in text
            entity_end: End position of entity in text

        Returns:
            NegationResult with assertion status
        """
        # Get text before and after entity within scope
        text_before = self._get_scope_before(text, entity_start)
        text_after = self._get_scope_after(text, entity_end)

        # Check word distance - only consider triggers within window
        words_before = self._word_distance(text_before)
        words_after = self._word_distance(text_after)

        # Check for pseudo-negation first (takes precedence)
        if self._is_pseudo_negation(text_before):
            return NegationResult(
                entity_text=entity_text,
                assertion=AssertionStatus.PRESENT,
                trigger_text=None,
                trigger_type="pseudo_negation",
                start_pos=entity_start,
                end_pos=entity_end,
                confidence=0.9,
                scope_text=text_before
            )

        # Priority order for assertion detection:
        # 1. Family history (most specific context)
        # 2. Historical (past vs current)
        # 3. Ruled out (explicit exclusion)
        # 4. Negation (absent)
        # 5. Uncertainty (possible)
        # 6. Default to present

        # Check FAMILY HISTORY
        if words_before <= self.window_size:
            trigger = self._find_trigger(text_before, self._family_history)
            if trigger:
                return NegationResult(
                    entity_text=entity_text,
                    assertion=AssertionStatus.FAMILY_HISTORY,
                    trigger_text=trigger[0],
                    trigger_type="family_history",
                    start_pos=entity_start,
                    end_pos=entity_end,
                    confidence=0.95,
                    scope_text=text_before
                )

        # Check HISTORICAL
        if words_before <= self.window_size:
            trigger = self._find_trigger(text_before, self._historical)
            if trigger:
                return NegationResult(
                    entity_text=entity_text,
                    assertion=AssertionStatus.HISTORICAL,
                    trigger_text=trigger[0],
                    trigger_type="historical",
                    start_pos=entity_start,
                    end_pos=entity_end,
                    confidence=0.9,
                    scope_text=text_before
                )

        # Check RULED OUT (before negation - more specific)
        if words_before <= self.window_size:
            trigger = self._find_trigger(text_before, self._ruled_out)
            if trigger:
                return NegationResult(
                    entity_text=entity_text,
                    assertion=AssertionStatus.RULED_OUT,
                    trigger_text=trigger[0],
                    trigger_type="ruled_out_pre",
                    start_pos=entity_start,
                    end_pos=entity_end,
                    confidence=0.95,
                    scope_text=text_before
                )

        # Check post-ruled out
        if words_after <= self.window_size:
            trigger = self._find_trigger(text_after, self._ruled_out)
            if trigger:
                return NegationResult(
                    entity_text=entity_text,
                    assertion=AssertionStatus.RULED_OUT,
                    trigger_text=trigger[0],
                    trigger_type="ruled_out_post",
                    start_pos=entity_start,
                    end_pos=entity_end,
                    confidence=0.9,
                    scope_text=text_after
                )

        # Check PRE-NEGATION (appears before entity)
        if words_before <= self.window_size:
            trigger = self._find_trigger(text_before, self._pre_negation)
            if trigger:
                return NegationResult(
                    entity_text=entity_text,
                    assertion=AssertionStatus.ABSENT,
                    trigger_text=trigger[0],
                    trigger_type="pre_negation",
                    start_pos=entity_start,
                    end_pos=entity_end,
                    confidence=0.95,
                    scope_text=text_before
                )

        # Check POST-NEGATION (appears after entity)
        if words_after <= self.window_size:
            trigger = self._find_trigger(text_after, self._post_negation)
            if trigger:
                return NegationResult(
                    entity_text=entity_text,
                    assertion=AssertionStatus.ABSENT,
                    trigger_text=trigger[0],
                    trigger_type="post_negation",
                    start_pos=entity_start,
                    end_pos=entity_end,
                    confidence=0.9,
                    scope_text=text_after
                )

        # Check UNCERTAINTY
        if words_before <= self.window_size:
            trigger = self._find_trigger(text_before, self._uncertainty)
            if trigger:
                return NegationResult(
                    entity_text=entity_text,
                    assertion=AssertionStatus.POSSIBLE,
                    trigger_text=trigger[0],
                    trigger_type="uncertainty",
                    start_pos=entity_start,
                    end_pos=entity_end,
                    confidence=0.85,
                    scope_text=text_before
                )

        # Check for question mark immediately before entity
        if entity_start > 0 and text[entity_start-1:entity_start] == '?':
            return NegationResult(
                entity_text=entity_text,
                assertion=AssertionStatus.POSSIBLE,
                trigger_text="?",
                trigger_type="uncertainty",
                start_pos=entity_start,
                end_pos=entity_end,
                confidence=0.8,
                scope_text="?"
            )

        # Default to PRESENT
        return NegationResult(
            entity_text=entity_text,
            assertion=AssertionStatus.PRESENT,
            trigger_text=None,
            trigger_type=None,
            start_pos=entity_start,
            end_pos=entity_end,
            confidence=1.0,
            scope_text=None
        )

    def detect_all(
        self,
        text: str,
        entities: List[Dict]
    ) -> Tuple[List[NegationResult], DetectionStats]:
        """
        Detect assertion status for multiple entities.

        Args:
            text: Full clinical text
            entities: List of entities with 'text', 'start_pos', 'end_pos' keys

        Returns:
            Tuple of (list of NegationResult, DetectionStats)
        """
        results = []
        stats = DetectionStats()

        for entity in entities:
            entity_text = entity.get('text', '')
            start_pos = entity.get('start_pos', 0)
            end_pos = entity.get('end_pos', start_pos + len(entity_text))

            result = self.detect_assertion(text, entity_text, start_pos, end_pos)
            results.append(result)

            # Update stats
            stats.total_entities += 1
            if result.assertion == AssertionStatus.PRESENT:
                stats.present += 1
            elif result.assertion == AssertionStatus.ABSENT:
                stats.absent += 1
            elif result.assertion == AssertionStatus.HISTORICAL:
                stats.historical += 1
            elif result.assertion == AssertionStatus.FAMILY_HISTORY:
                stats.family_history += 1
            elif result.assertion == AssertionStatus.POSSIBLE:
                stats.possible += 1
            elif result.assertion == AssertionStatus.RULED_OUT:
                stats.ruled_out += 1

        return results, stats

    def filter_for_snomed(
        self,
        entities: List[Dict],
        text: str,
        allow_statuses: Optional[Set[AssertionStatus]] = None
    ) -> Tuple[List[Dict], List[Dict]]:
        """
        Filter entities for SNOMED coding based on assertion status.

        Only PRESENT entities should become positive SNOMED diagnoses.
        Negated/absent entities are excluded from diagnosis coding.

        Args:
            entities: List of entities to filter
            text: Full clinical text
            allow_statuses: Set of statuses to allow (default: PRESENT only)

        Returns:
            Tuple of (allowed entities, excluded entities)
        """
        if allow_statuses is None:
            allow_statuses = {AssertionStatus.PRESENT}

        allowed = []
        excluded = []

        for entity in entities:
            entity_text = entity.get('text', '')
            start_pos = entity.get('start_pos', 0)
            end_pos = entity.get('end_pos', start_pos + len(entity_text))

            result = self.detect_assertion(text, entity_text, start_pos, end_pos)

            # Add assertion info to entity
            entity_with_assertion = {
                **entity,
                'assertion': result.assertion.value,
                'assertion_trigger': result.trigger_text,
                'assertion_confidence': result.confidence
            }

            if result.assertion in allow_statuses:
                allowed.append(entity_with_assertion)
            else:
                excluded.append(entity_with_assertion)

        return allowed, excluded

    def annotate_text(self, text: str, entities: List[Dict]) -> str:
        """
        Annotate text with assertion markers for visualization.

        Args:
            text: Original clinical text
            entities: List of entities with positions

        Returns:
            Text with assertion annotations
        """
        results, _ = self.detect_all(text, entities)

        # Sort by position (reverse order for safe replacement)
        sorted_results = sorted(results, key=lambda x: x.start_pos, reverse=True)

        annotated = text
        for result in sorted_results:
            status_marker = f"[{result.assertion.value.upper()}]"
            entity_annotated = f"{result.entity_text}{status_marker}"
            annotated = (
                annotated[:result.start_pos] +
                entity_annotated +
                annotated[result.end_pos:]
            )

        return annotated


def create_detector(window_size: int = 6) -> ClinicalNegationDetector:
    """Factory function to create a negation detector"""
    return ClinicalNegationDetector(window_size=window_size)


# =============================================================================
# EXAMPLE USAGE
# =============================================================================

if __name__ == "__main__":
    # Test examples
    detector = create_detector()

    test_cases = [
        # Negation examples
        ("No trauma", "trauma"),
        ("No headache", "headache"),
        ("No fever", "fever"),
        ("Denies pain", "pain"),
        ("Nil urinary symptoms", "urinary symptoms"),
        ("Without evidence of fracture", "fracture"),
        ("Negative for DVT", "DVT"),
        ("Free from infection", "infection"),
        ("Never had seizures", "seizures"),
        ("Absent reflexes", "reflexes"),

        # Present examples
        ("Patient has chest pain", "chest pain"),
        ("Presents with shortness of breath", "shortness of breath"),
        ("Diagnosed with pneumonia", "pneumonia"),

        # Historical examples
        ("History of MI", "MI"),
        ("PMH: diabetes", "diabetes"),
        ("Previous stroke in 2019", "stroke"),
        ("Known hypertension", "hypertension"),

        # Family history
        ("Family history of breast cancer", "breast cancer"),
        ("Mother had diabetes", "diabetes"),
        ("FHx: heart disease", "heart disease"),

        # Uncertainty
        ("Possible TIA", "TIA"),
        ("Query PE", "PE"),
        ("?appendicitis", "appendicitis"),
        ("Suspected MI", "MI"),
        ("Cannot rule out meningitis", "meningitis"),

        # Ruled out
        ("PE ruled out", "PE"),
        ("Excluded MI", "MI"),
        ("Unlikely to be cancer", "cancer"),
    ]

    print("Clinical Negation Detection Test Results")
    print("=" * 60)

    for text, entity in test_cases:
        # Find entity position
        match = re.search(re.escape(entity), text, re.IGNORECASE)
        if match:
            result = detector.detect_assertion(
                text, entity, match.start(), match.end()
            )
            print(f"\nText: \"{text}\"")
            print(f"Entity: \"{entity}\"")
            print(f"Assertion: {result.assertion.value}")
            if result.trigger_text:
                print(f"Trigger: \"{result.trigger_text}\"")
            print(f"Confidence: {result.confidence}")
