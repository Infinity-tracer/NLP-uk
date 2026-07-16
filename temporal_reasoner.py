"""
Temporal Clinical Reasoning Engine

Differentiates temporal states for medical entities:
- Current: Active now (presenting complaint, current symptoms)
- Historical: Past event (PMH, previous surgery)
- Resolved: Was present, now gone (resolved symptoms)
- Suspected: Under investigation (query, possible)
- Chronic: Long-standing ongoing condition
- Acute: Recent onset, active now

Clinical categories with temporal context:
- Current diagnosis vs Past medical history
- Current symptoms vs Resolved symptoms
- Previous surgeries vs Planned procedures
- Chronic diseases vs Acute presentations
- Family history (always historical by nature)
- Medication history vs Current medications
"""

import re
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Set


class TemporalState(Enum):
    """Temporal state for clinical entities"""
    CURRENT = "current"
    HISTORICAL = "historical"
    RESOLVED = "resolved"
    SUSPECTED = "suspected"
    CHRONIC = "chronic"
    ACUTE = "acute"


class ClinicalTemporalCategory(Enum):
    """Clinical category with temporal awareness"""
    CURRENT_DIAGNOSIS = "current_diagnosis"
    PAST_MEDICAL_HISTORY = "past_medical_history"
    PREVIOUS_SURGERY = "previous_surgery"
    RESOLVED_SYMPTOM = "resolved_symptom"
    CURRENT_SYMPTOM = "current_symptom"
    CHRONIC_DISEASE = "chronic_disease"
    FAMILY_HISTORY = "family_history"
    MEDICATION_HISTORY = "medication_history"
    CURRENT_MEDICATION = "current_medication"
    PLANNED_PROCEDURE = "planned_procedure"
    ACUTE_PRESENTATION = "acute_presentation"


@dataclass
class TemporalResult:
    """Result of temporal reasoning for an entity"""
    entity_text: str
    temporal_state: TemporalState
    clinical_category: Optional[ClinicalTemporalCategory] = None
    trigger_text: Optional[str] = None
    trigger_type: Optional[str] = None
    start_pos: int = 0
    end_pos: int = 0
    confidence: float = 1.0
    time_reference: Optional[str] = None  # "2019", "3 years ago", etc.
    duration: Optional[str] = None  # "chronic", "long-standing"


@dataclass
class TemporalStats:
    """Statistics from temporal reasoning"""
    total_entities: int = 0
    current: int = 0
    historical: int = 0
    resolved: int = 0
    suspected: int = 0
    chronic: int = 0
    acute: int = 0


# =============================================================================
# CURRENT/ACUTE TRIGGERS - Present now, recent onset
# =============================================================================

CURRENT_TRIGGERS = [
    # Presenting complaint markers
    r"\bpresents?\s+with\b",
    r"\bpresenting\s+(?:complaint|with)\b",
    r"\bcomplains?\s+of\b",
    r"\bcomplaining\s+of\b",
    r"\breports?\b",
    r"\breporting\b",
    r"\bdescribes?\b",
    r"\bdescribing\b",
    r"\bexperiencing\b",
    r"\bexperiences?\b",
    r"\bsuffering\s+from\b",
    r"\bsuffers?\s+from\b",
    r"\bcurrently\b",
    r"\bcurrent\b",
    r"\btoday\b",
    r"\bnow\b",
    r"\bat\s+present\b",
    r"\bpresently\b",
    r"\bongoing\b",
    r"\bactive\b",
    r"\bactively\b",
    r"\bstill\s+has\b",
    r"\bcontinues?\s+to\b",
    r"\bcontinuing\b",
    r"\bpersistent\b",
    r"\bpersists?\b",
    r"\bpersisting\b",

    # Examination findings (current)
    r"\bon\s+examination\b",
    r"\bo/e\b",
    r"\bexamination\s+(?:reveals?|shows?|demonstrates?)\b",
    r"\bfindings?\s+(?:of|include)\b",
    r"\bnoted\s+to\s+have\b",
    r"\bobserved\b",
    r"\bfound\s+to\s+have\b",
    r"\bdemonstrates?\b",
    r"\bshows?\b",
    r"\breveals?\b",
    r"\bdisplays?\b",
    r"\bexhibits?\b",

    # Today/recent
    r"\bthis\s+morning\b",
    r"\bthis\s+afternoon\b",
    r"\bthis\s+evening\b",
    r"\bearlier\s+today\b",
    r"\bjust\s+now\b",
    r"\brecently\b",
    r"\bsince\s+yesterday\b",
    r"\bover\s+(?:the\s+)?(?:last|past)\s+(?:few\s+)?(?:hours?|days?)\b",
]

ACUTE_TRIGGERS = [
    # Acute onset markers
    r"\bacute\b",
    r"\bacutely\b",
    r"\bsudden\b",
    r"\bsuddenly\b",
    r"\babrupt\b",
    r"\babruptly\b",
    r"\bnew\s+onset\b",
    r"\bnew\b",
    r"\brecent\s+onset\b",
    r"\brecent\b",
    r"\brapid\s+onset\b",
    r"\brapidly\b",
    r"\bwoke\s+(?:up\s+)?with\b",
    r"\bdeveloped\b",
    r"\bstarted\b",
    r"\bbegan\b",
    r"\bonset\b",
    r"\bfirst\s+episode\b",
    r"\bfirst\s+time\b",
    r"\binitial\s+presentation\b",

    # Time-specific acute
    r"\b(?:this|last)\s+(?:morning|night|evening)\b",
    r"\byesterday\b",
    r"\b\d+\s*(?:hour|hr)s?\s+ago\b",
    r"\b\d+\s*(?:day)s?\s+ago\b",
    r"\bsince\s+(?:this\s+)?(?:morning|yesterday|last\s+night)\b",

    # Emergency markers
    r"\bemergency\b",
    r"\burgent\b",
    r"\bcollapse[ds]?\b",
    r"\bfound\s+(?:collapsed|unresponsive)\b",
    r"\bbought\s+in\s+by\s+ambulance\b",
    r"\b999\s+call\b",
    r"\bblue\s+light\b",
]

# =============================================================================
# HISTORICAL/PAST TRIGGERS
# =============================================================================

HISTORICAL_TRIGGERS = [
    # Past medical history markers
    r"\bhistory\s+of\b",
    r"\bh/o\b",
    r"\bhx\s+of\b",
    r"\bhx:\b",
    r"\bpmh\b",
    r"\bpmhx\b",
    r"\bpast\s+medical\s+history\b",
    r"\bbackground\s+of\b",
    r"\bbackground\s+includes?\b",
    r"\bbackground:\b",
    r"\bmedical\s+history\b",
    r"\bpast\s+history\b",
    r"\bprevious\b",
    r"\bpreviously\b",
    r"\bprior\b",
    r"\bprior\s+to\b",
    r"\bpast\b",
    r"\bformer\b",
    r"\bformerly\b",
    r"\bknown\s+(?:case\s+of|to\s+have)\b",
    r"\bknown\b",
    r"\bestablished\b",
    r"\bdiagnosed\s+(?:with|in)\b",
    r"\bwas\s+diagnosed\b",
    r"\bhad\b",
    r"\bused\s+to\s+have\b",
    r"\bsuffered\s+(?:from|with)\b",
    r"\bhas\s+had\b",

    # Time references (past)
    r"\b\d+\s*(?:year|yr|month|week)s?\s+ago\b",
    r"\bin\s+(?:19|20)\d{2}\b",
    r"\bback\s+in\b",
    r"\bchildhood\b",
    r"\badolescent\b",
    r"\byouth\b",
    r"\bas\s+a\s+child\b",
    r"\bwhen\s+younger\b",
    r"\bremote\s+history\b",
    r"\bdistant\s+history\b",
    r"\byears\s+ago\b",
    r"\bmonths\s+ago\b",
    r"\blast\s+year\b",
    r"\bprevious\s+year\b",
    r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+(?:19|20)\d{2}\b",
]

# =============================================================================
# SURGERY/PROCEDURE HISTORY TRIGGERS
# =============================================================================

SURGERY_HISTORY_TRIGGERS = [
    r"\bprevious\s+(?:surgery|operation|procedure)\b",
    r"\bpast\s+(?:surgery|surgical)\b",
    r"\bsurgical\s+history\b",
    r"\bpsh\b",  # Past Surgical History
    r"\bhad\s+(?:a\s+)?(?:surgery|operation|procedure)\b",
    r"\bunderwent\b",
    r"\bpost[- ]?(?:op|operative)\b",
    r"\bpost\b",
    r"\bstatus\s+post\b",
    r"\bs/p\b",
    r"\bfollowing\s+(?:surgery|operation)\b",
    r"\bafter\s+(?:surgery|operation)\b",
    r"\bprevious\s+(?:appendectomy|cholecystectomy|hysterectomy|mastectomy|hip\s+replacement|knee\s+replacement|cabg|pci|angioplasty)\b",
    r"\b(?:appendectomy|cholecystectomy|hysterectomy|mastectomy)\s+in\s+(?:19|20)\d{2}\b",
]

# =============================================================================
# RESOLVED TRIGGERS - Was present, now gone
# =============================================================================

RESOLVED_TRIGGERS = [
    r"\bresolved\b",
    r"\bresolving\b",
    r"\bhas\s+resolved\b",
    r"\bnow\s+resolved\b",
    r"\bcompletely\s+resolved\b",
    r"\bfully\s+resolved\b",
    r"\bspontaneously\s+resolved\b",
    r"\bself[- ]?resolved\b",
    r"\bcleared\b",
    r"\bhas\s+cleared\b",
    r"\bnow\s+clear\b",
    r"\bsettled\b",
    r"\bhas\s+settled\b",
    r"\bnow\s+settled\b",
    r"\bimproved\b",
    r"\bimproving\b",
    r"\bsignificantly\s+improved\b",
    r"\bmuch\s+improved\b",
    r"\bbetter\b",
    r"\bmuch\s+better\b",
    r"\bno\s+longer\b",
    r"\bwent\s+away\b",
    r"\bgone\s+away\b",
    r"\bdisappeared\b",
    r"\babated\b",
    r"\bsubsided\b",
    r"\bremitted\b",
    r"\bin\s+remission\b",
    r"\bremission\b",
    r"\basymptomatic\b",
    r"\bsymptom[- ]?free\b",
    r"\bpain[- ]?free\b",
    r"\brecovered\b",
    r"\brecovery\b",
    r"\bfull\s+recovery\b",
    r"\bback\s+to\s+normal\b",
    r"\bnormalized\b",
    r"\bnormalised\b",
    r"\breturned\s+to\s+baseline\b",

    # Treatment success
    r"\btreated\s+successfully\b",
    r"\bsuccessfully\s+treated\b",
    r"\bcured\b",
    r"\beradicated\b",
]

# =============================================================================
# CHRONIC TRIGGERS - Long-standing, ongoing
# =============================================================================

CHRONIC_TRIGGERS = [
    r"\bchronic\b",
    r"\bchronically\b",
    r"\blong[- ]?standing\b",
    r"\blong[- ]?term\b",
    r"\blong[- ]?duration\b",
    r"\bprolonged\b",
    r"\bpersistent\b",
    r"\brecurrent\b",
    r"\brecurring\b",
    r"\bfrequent\b",
    r"\bintermittent\b",
    r"\bepisodic\b",
    r"\brelapsing\b",
    r"\brelapsing[- ]?remitting\b",
    r"\blifelong\b",
    r"\blife[- ]?long\b",
    r"\bsince\s+childhood\b",
    r"\bfor\s+many\s+years\b",
    r"\bfor\s+several\s+years\b",
    r"\bfor\s+\d+\s+years\b",
    r"\bover\s+\d+\s+years\b",
    r"\byears\s+of\b",
    r"\bmonths\s+of\b",
    r"\bwell[- ]?controlled\b",
    r"\bpoorly[- ]?controlled\b",
    r"\bstable\b",
    r"\bunstable\b",
    r"\bworsening\b",
    r"\bdeteriorating\b",
    r"\bprogressive\b",
    r"\bon[- ]?going\b",
    r"\bestablished\b",
    r"\bknown\b",

    # Chronic disease terminology
    r"\btype\s*[12]\s+diabet\w*\b",
    r"\bt[12]dm\b",
    r"\biddm\b",
    r"\bniddm\b",
    r"\bhypertension\b",
    r"\bhtn\b",
    r"\basthma\b",
    r"\bcopd\b",
    r"\bckd\b",
    r"\bchf\b",
    r"\baf\b",
    r"\batrial\s+fibrillation\b",
    r"\brheumatoid\s+arthritis\b",
    r"\bra\b",
    r"\bosteoarthritis\b",
    r"\boa\b",
    r"\bepilepsy\b",
    r"\bms\b",
    r"\bmultiple\s+sclerosis\b",
    r"\bparkinson\b",
    r"\bdementia\b",
    r"\balzheimer\b",
]

# =============================================================================
# SUSPECTED/QUERY TRIGGERS
# =============================================================================

SUSPECTED_TRIGGERS = [
    r"\bsuspected\b",
    r"\bsuspect\b",
    r"\bsuspicion\s+of\b",
    r"\bsuspicious\s+for\b",
    r"\bquery\b",
    r"\bqueried\b",
    r"\b\?\s*",
    r"\bpossible\b",
    r"\bpossibly\b",
    r"\bprobable\b",
    r"\bprobably\b",
    r"\blikely\b",
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
    r"\bawait(?:ing|s)?\s+(?:confirmation|results?)\b",
    r"\bpending\s+(?:confirmation|results?|investigation)\b",
    r"\bfor\s+investigation\b",
    r"\binvestigate\s+for\b",
    r"\bexclude\b",
    r"\brule\s+out\b",
    r"\br/o\b",
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
# MEDICATION HISTORY TRIGGERS
# =============================================================================

MEDICATION_HISTORY_TRIGGERS = [
    r"\bprevious(?:ly)?\s+(?:on|taking|took)\b",
    r"\bformer(?:ly)?\s+(?:on|taking)\b",
    r"\bused\s+to\s+take\b",
    r"\bwas\s+(?:on|taking)\b",
    r"\bstopped\b",
    r"\bdiscontinued\b",
    r"\bceased\b",
    r"\bchanged\s+from\b",
    r"\bswitched\s+from\b",
    r"\bprevious\s+medication\b",
    r"\bpast\s+medication\b",
    r"\bmedication\s+history\b",
    r"\bdrug\s+history\b",
    r"\bdhx\b",
    r"\ballergic\s+to\b",  # implies past exposure
    r"\bintolerant\s+to\b",
    r"\breaction\s+to\b",
    r"\badverse\s+(?:reaction|effect)\s+to\b",
    r"\btried\b",
    r"\bfailed\b",
    r"\bineffective\b",
]

CURRENT_MEDICATION_TRIGGERS = [
    r"\bcurrently\s+(?:on|taking)\b",
    r"\bcurrent\s+medication\b",
    r"\bregular\s+medication\b",
    r"\btakes?\b",
    r"\bon\b",
    r"\bprescribed\b",
    r"\bstarted\s+on\b",
    r"\bcommenced\b",
    r"\binitiated\b",
    r"\bcontinue[sd]?\b",
    r"\bmaintenance\b",
    r"\bdaily\b",
    r"\btwice\s+daily\b",
    r"\bbd\b",
    r"\btds\b",
    r"\bqds\b",
    r"\bod\b",
    r"\bprn\b",
    r"\bas\s+needed\b",
    r"\bregularly\b",
]

# =============================================================================
# SCOPE TERMINATORS
# =============================================================================

SCOPE_TERMINATORS = [
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
    r"\bwhereas\b",
    r"\bwhile\b",
    r"\bwhilst\b",
    r"\b(?:assessment|plan|impression|diagnosis|treatment):\s*",
    r"\b(?:examination|investigations?|results?):\s*",
]

SCOPE_PUNCTUATION = {'.', ';', ':', '\n', '\r'}


class ClinicalTemporalReasoner:
    """
    Clinical temporal reasoning engine.

    Differentiates temporal states for medical entities:
    - Current vs Historical
    - Acute vs Chronic
    - Resolved vs Ongoing
    - Suspected vs Confirmed
    """

    def __init__(self, window_size: int = 8):
        """
        Initialize temporal reasoner.

        Args:
            window_size: Number of words to check for triggers before/after entity
        """
        self.window_size = window_size

        # Compile patterns
        self._current = self._compile_patterns(CURRENT_TRIGGERS)
        self._acute = self._compile_patterns(ACUTE_TRIGGERS)
        self._historical = self._compile_patterns(HISTORICAL_TRIGGERS)
        self._surgery_history = self._compile_patterns(SURGERY_HISTORY_TRIGGERS)
        self._resolved = self._compile_patterns(RESOLVED_TRIGGERS)
        self._chronic = self._compile_patterns(CHRONIC_TRIGGERS)
        self._suspected = self._compile_patterns(SUSPECTED_TRIGGERS)
        self._family_history = self._compile_patterns(FAMILY_HISTORY_TRIGGERS)
        self._med_history = self._compile_patterns(MEDICATION_HISTORY_TRIGGERS)
        self._current_med = self._compile_patterns(CURRENT_MEDICATION_TRIGGERS)
        self._terminators = self._compile_patterns(SCOPE_TERMINATORS)

        # Time reference patterns
        self._time_refs = [
            re.compile(r'\b(\d+)\s*(year|yr|month|week|day|hour|hr)s?\s*ago\b', re.IGNORECASE),
            re.compile(r'\bin\s*((?:19|20)\d{2})\b', re.IGNORECASE),
            re.compile(r'\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s*((?:19|20)\d{2})\b', re.IGNORECASE),
            re.compile(r'\b(last|this)\s*(year|month|week)\b', re.IGNORECASE),
            re.compile(r'\b(yesterday|today|tonight)\b', re.IGNORECASE),
        ]

    def _compile_patterns(self, patterns: List[str]) -> List[re.Pattern]:
        """Compile regex patterns"""
        compiled = []
        for pattern in patterns:
            try:
                compiled.append(re.compile(pattern, re.IGNORECASE))
            except re.error:
                pass
        return compiled

    def _find_trigger(
        self,
        text: str,
        patterns: List[re.Pattern]
    ) -> Optional[Tuple[str, int, int]]:
        """Find first matching trigger"""
        for pattern in patterns:
            match = pattern.search(text)
            if match:
                return (match.group(), match.start(), match.end())
        return None

    def _contains_trigger(self, text: str, patterns: List[re.Pattern]) -> bool:
        """Check if text contains any trigger"""
        for pattern in patterns:
            if pattern.search(text):
                return True
        return False

    def _extract_time_reference(self, text: str) -> Optional[str]:
        """Extract time reference from text"""
        for pattern in self._time_refs:
            match = pattern.search(text)
            if match:
                return match.group()
        return None

    def _get_scope_before(self, text: str, entity_start: int) -> str:
        """Get text before entity within scope"""
        scope_start = 0

        for pattern in self._terminators:
            for match in pattern.finditer(text[:entity_start]):
                if match.end() > scope_start:
                    scope_start = match.end()

        for i, char in enumerate(text[:entity_start]):
            if char in SCOPE_PUNCTUATION:
                if i + 1 > scope_start:
                    scope_start = i + 1

        return text[scope_start:entity_start].strip()

    def _get_scope_after(self, text: str, entity_end: int) -> str:
        """Get text after entity within scope"""
        scope_end = len(text)
        remaining = text[entity_end:]

        for pattern in self._terminators:
            match = pattern.search(remaining)
            if match:
                potential_end = entity_end + match.start()
                if potential_end < scope_end:
                    scope_end = potential_end

        for i, char in enumerate(remaining):
            if char in SCOPE_PUNCTUATION:
                potential_end = entity_end + i
                if potential_end < scope_end:
                    scope_end = potential_end
                break

        return text[entity_end:scope_end].strip()

    def _word_distance(self, text: str) -> int:
        """Count words in text"""
        return len(text.split())

    def _detect_section_context(self, full_text: str, entity_start: int) -> Optional[str]:
        """Detect which section the entity is in"""
        section_patterns = [
            (r"(?:past\s+medical\s+history|pmh|pmhx|background)\s*:", "pmh"),
            (r"(?:presenting\s+complaint|pc|chief\s+complaint|cc)\s*:", "presenting"),
            (r"(?:history\s+of\s+presenting\s+complaint|hpc|hopi)\s*:", "hpc"),
            (r"(?:family\s+history|fhx|fh)\s*:", "family"),
            (r"(?:drug\s+history|dhx|dh|medications?)\s*:", "medications"),
            (r"(?:social\s+history|shx|sh)\s*:", "social"),
            (r"(?:surgical\s+history|psh|past\s+surgical)\s*:", "surgical"),
            (r"(?:examination|o/e|on\s+examination)\s*:", "examination"),
            (r"(?:investigations?|results?)\s*:", "investigations"),
            (r"(?:impression|diagnosis|assessment)\s*:", "diagnosis"),
            (r"(?:plan|management)\s*:", "plan"),
        ]

        text_before = full_text[:entity_start].lower()
        last_section = None
        last_pos = -1

        for pattern, section_name in section_patterns:
            for match in re.finditer(pattern, text_before, re.IGNORECASE):
                if match.end() > last_pos:
                    last_pos = match.end()
                    last_section = section_name

        return last_section

    def reason_temporal(
        self,
        text: str,
        entity_text: str,
        entity_start: int,
        entity_end: int,
        entity_type: Optional[str] = None
    ) -> TemporalResult:
        """
        Determine temporal state for an entity.

        Args:
            text: Full clinical text
            entity_text: The entity text
            entity_start: Start position
            entity_end: End position
            entity_type: Optional entity type hint (symptom, diagnosis, medication, etc.)

        Returns:
            TemporalResult with temporal state and clinical category
        """
        text_before = self._get_scope_before(text, entity_start)
        text_after = self._get_scope_after(text, entity_end)

        words_before = self._word_distance(text_before)
        words_after = self._word_distance(text_after)

        # Extract time reference
        time_ref = self._extract_time_reference(text_before) or self._extract_time_reference(text_after)

        # Detect section context
        section = self._detect_section_context(text, entity_start)

        # Priority-based temporal detection:
        # 1. Resolved (most specific - was present, now gone)
        # 2. Family history (always historical)
        # 3. Suspected (under investigation)
        # 4. Acute (recent onset)
        # 5. Chronic (long-standing)
        # 6. Historical (past)
        # 7. Current (default for symptoms in HPC/examination)

        # 1. Check RESOLVED
        if words_before <= self.window_size:
            trigger = self._find_trigger(text_before, self._resolved)
            if trigger:
                return TemporalResult(
                    entity_text=entity_text,
                    temporal_state=TemporalState.RESOLVED,
                    clinical_category=ClinicalTemporalCategory.RESOLVED_SYMPTOM,
                    trigger_text=trigger[0],
                    trigger_type="resolved",
                    start_pos=entity_start,
                    end_pos=entity_end,
                    confidence=0.95,
                    time_reference=time_ref,
                )

        if words_after <= self.window_size:
            trigger = self._find_trigger(text_after, self._resolved)
            if trigger:
                return TemporalResult(
                    entity_text=entity_text,
                    temporal_state=TemporalState.RESOLVED,
                    clinical_category=ClinicalTemporalCategory.RESOLVED_SYMPTOM,
                    trigger_text=trigger[0],
                    trigger_type="resolved_post",
                    start_pos=entity_start,
                    end_pos=entity_end,
                    confidence=0.9,
                    time_reference=time_ref,
                )

        # 2. Check FAMILY HISTORY
        if words_before <= self.window_size:
            trigger = self._find_trigger(text_before, self._family_history)
            if trigger:
                return TemporalResult(
                    entity_text=entity_text,
                    temporal_state=TemporalState.HISTORICAL,
                    clinical_category=ClinicalTemporalCategory.FAMILY_HISTORY,
                    trigger_text=trigger[0],
                    trigger_type="family_history",
                    start_pos=entity_start,
                    end_pos=entity_end,
                    confidence=0.95,
                )

        # Section-based family history
        if section == "family":
            return TemporalResult(
                entity_text=entity_text,
                temporal_state=TemporalState.HISTORICAL,
                clinical_category=ClinicalTemporalCategory.FAMILY_HISTORY,
                trigger_text=None,
                trigger_type="section_family",
                start_pos=entity_start,
                end_pos=entity_end,
                confidence=0.85,
            )

        # 3. Check SUSPECTED
        if words_before <= self.window_size:
            trigger = self._find_trigger(text_before, self._suspected)
            if trigger:
                return TemporalResult(
                    entity_text=entity_text,
                    temporal_state=TemporalState.SUSPECTED,
                    clinical_category=ClinicalTemporalCategory.CURRENT_DIAGNOSIS if section == "diagnosis" else None,
                    trigger_text=trigger[0],
                    trigger_type="suspected",
                    start_pos=entity_start,
                    end_pos=entity_end,
                    confidence=0.9,
                )

        # Check for ? immediately before
        if entity_start > 0 and text[entity_start-1:entity_start] == '?':
            return TemporalResult(
                entity_text=entity_text,
                temporal_state=TemporalState.SUSPECTED,
                trigger_text="?",
                trigger_type="query",
                start_pos=entity_start,
                end_pos=entity_end,
                confidence=0.85,
            )

        # 4. Check ACUTE
        if words_before <= self.window_size:
            trigger = self._find_trigger(text_before, self._acute)
            if trigger:
                return TemporalResult(
                    entity_text=entity_text,
                    temporal_state=TemporalState.ACUTE,
                    clinical_category=ClinicalTemporalCategory.ACUTE_PRESENTATION,
                    trigger_text=trigger[0],
                    trigger_type="acute",
                    start_pos=entity_start,
                    end_pos=entity_end,
                    confidence=0.9,
                    time_reference=time_ref,
                )

        # 5. Check CHRONIC
        if words_before <= self.window_size:
            trigger = self._find_trigger(text_before, self._chronic)
            if trigger:
                return TemporalResult(
                    entity_text=entity_text,
                    temporal_state=TemporalState.CHRONIC,
                    clinical_category=ClinicalTemporalCategory.CHRONIC_DISEASE,
                    trigger_text=trigger[0],
                    trigger_type="chronic",
                    start_pos=entity_start,
                    end_pos=entity_end,
                    confidence=0.9,
                    duration="chronic",
                )

        # Check entity text itself for chronic markers
        entity_lower = entity_text.lower()
        if any(term in entity_lower for term in ['chronic', 'type 1', 'type 2', 't1dm', 't2dm']):
            return TemporalResult(
                entity_text=entity_text,
                temporal_state=TemporalState.CHRONIC,
                clinical_category=ClinicalTemporalCategory.CHRONIC_DISEASE,
                trigger_text=None,
                trigger_type="entity_chronic",
                start_pos=entity_start,
                end_pos=entity_end,
                confidence=0.85,
                duration="chronic",
            )

        # 6. Check SURGERY HISTORY
        if words_before <= self.window_size:
            trigger = self._find_trigger(text_before, self._surgery_history)
            if trigger:
                return TemporalResult(
                    entity_text=entity_text,
                    temporal_state=TemporalState.HISTORICAL,
                    clinical_category=ClinicalTemporalCategory.PREVIOUS_SURGERY,
                    trigger_text=trigger[0],
                    trigger_type="surgery_history",
                    start_pos=entity_start,
                    end_pos=entity_end,
                    confidence=0.95,
                    time_reference=time_ref,
                )

        # Section-based surgical history
        if section == "surgical":
            return TemporalResult(
                entity_text=entity_text,
                temporal_state=TemporalState.HISTORICAL,
                clinical_category=ClinicalTemporalCategory.PREVIOUS_SURGERY,
                trigger_text=None,
                trigger_type="section_surgical",
                start_pos=entity_start,
                end_pos=entity_end,
                confidence=0.85,
                time_reference=time_ref,
            )

        # 7. Check HISTORICAL/PMH
        if words_before <= self.window_size:
            trigger = self._find_trigger(text_before, self._historical)
            if trigger:
                return TemporalResult(
                    entity_text=entity_text,
                    temporal_state=TemporalState.HISTORICAL,
                    clinical_category=ClinicalTemporalCategory.PAST_MEDICAL_HISTORY,
                    trigger_text=trigger[0],
                    trigger_type="historical",
                    start_pos=entity_start,
                    end_pos=entity_end,
                    confidence=0.9,
                    time_reference=time_ref,
                )

        # Section-based PMH
        if section == "pmh":
            return TemporalResult(
                entity_text=entity_text,
                temporal_state=TemporalState.HISTORICAL,
                clinical_category=ClinicalTemporalCategory.PAST_MEDICAL_HISTORY,
                trigger_text=None,
                trigger_type="section_pmh",
                start_pos=entity_start,
                end_pos=entity_end,
                confidence=0.85,
                time_reference=time_ref,
            )

        # 8. Check MEDICATION HISTORY
        if entity_type == "medication":
            if words_before <= self.window_size:
                trigger = self._find_trigger(text_before, self._med_history)
                if trigger:
                    return TemporalResult(
                        entity_text=entity_text,
                        temporal_state=TemporalState.HISTORICAL,
                        clinical_category=ClinicalTemporalCategory.MEDICATION_HISTORY,
                        trigger_text=trigger[0],
                        trigger_type="med_history",
                        start_pos=entity_start,
                        end_pos=entity_end,
                        confidence=0.9,
                    )

            # Check for current medication
            if words_before <= self.window_size:
                trigger = self._find_trigger(text_before, self._current_med)
                if trigger:
                    return TemporalResult(
                        entity_text=entity_text,
                        temporal_state=TemporalState.CURRENT,
                        clinical_category=ClinicalTemporalCategory.CURRENT_MEDICATION,
                        trigger_text=trigger[0],
                        trigger_type="current_med",
                        start_pos=entity_start,
                        end_pos=entity_end,
                        confidence=0.9,
                    )

        # 9. Check CURRENT
        if words_before <= self.window_size:
            trigger = self._find_trigger(text_before, self._current)
            if trigger:
                clinical_cat = None
                if entity_type == "symptom":
                    clinical_cat = ClinicalTemporalCategory.CURRENT_SYMPTOM
                elif entity_type == "diagnosis":
                    clinical_cat = ClinicalTemporalCategory.CURRENT_DIAGNOSIS

                return TemporalResult(
                    entity_text=entity_text,
                    temporal_state=TemporalState.CURRENT,
                    clinical_category=clinical_cat,
                    trigger_text=trigger[0],
                    trigger_type="current",
                    start_pos=entity_start,
                    end_pos=entity_end,
                    confidence=0.9,
                )

        # Section-based current (presenting complaint, HPC, examination)
        if section in ("presenting", "hpc", "examination"):
            clinical_cat = ClinicalTemporalCategory.CURRENT_SYMPTOM if entity_type == "symptom" else ClinicalTemporalCategory.ACUTE_PRESENTATION
            return TemporalResult(
                entity_text=entity_text,
                temporal_state=TemporalState.CURRENT,
                clinical_category=clinical_cat,
                trigger_text=None,
                trigger_type=f"section_{section}",
                start_pos=entity_start,
                end_pos=entity_end,
                confidence=0.8,
            )

        # Default: CURRENT for symptoms without other context
        return TemporalResult(
            entity_text=entity_text,
            temporal_state=TemporalState.CURRENT,
            clinical_category=ClinicalTemporalCategory.CURRENT_SYMPTOM if entity_type == "symptom" else None,
            trigger_text=None,
            trigger_type=None,
            start_pos=entity_start,
            end_pos=entity_end,
            confidence=0.7,
            time_reference=time_ref,
        )

    def reason_all(
        self,
        text: str,
        entities: List[Dict]
    ) -> Tuple[List[TemporalResult], TemporalStats]:
        """
        Determine temporal state for multiple entities.

        Args:
            text: Full clinical text
            entities: List of entities with 'text', 'start_pos', 'end_pos', optionally 'type'

        Returns:
            Tuple of (list of TemporalResult, TemporalStats)
        """
        results = []
        stats = TemporalStats()

        for entity in entities:
            entity_text = entity.get('text', '')
            start_pos = entity.get('start_pos', 0)
            end_pos = entity.get('end_pos', start_pos + len(entity_text))
            entity_type = entity.get('type') or entity.get('category')

            result = self.reason_temporal(text, entity_text, start_pos, end_pos, entity_type)
            results.append(result)

            # Update stats
            stats.total_entities += 1
            if result.temporal_state == TemporalState.CURRENT:
                stats.current += 1
            elif result.temporal_state == TemporalState.HISTORICAL:
                stats.historical += 1
            elif result.temporal_state == TemporalState.RESOLVED:
                stats.resolved += 1
            elif result.temporal_state == TemporalState.SUSPECTED:
                stats.suspected += 1
            elif result.temporal_state == TemporalState.CHRONIC:
                stats.chronic += 1
            elif result.temporal_state == TemporalState.ACUTE:
                stats.acute += 1

        return results, stats

    def categorize_by_temporal(
        self,
        entities: List[Dict],
        text: str
    ) -> Dict[str, List[Dict]]:
        """
        Categorize entities by temporal clinical category.

        Args:
            entities: List of entities
            text: Full clinical text

        Returns:
            Dict with categories as keys and lists of entities as values
        """
        categories = {
            "current_diagnosis": [],
            "past_medical_history": [],
            "previous_surgery": [],
            "resolved_symptom": [],
            "current_symptom": [],
            "chronic_disease": [],
            "family_history": [],
            "medication_history": [],
            "current_medication": [],
            "acute_presentation": [],
            "suspected": [],
            "uncategorized": [],
        }

        for entity in entities:
            entity_text = entity.get('text', '')
            start_pos = entity.get('start_pos', 0)
            end_pos = entity.get('end_pos', start_pos + len(entity_text))
            entity_type = entity.get('type') or entity.get('category')

            result = self.reason_temporal(text, entity_text, start_pos, end_pos, entity_type)

            # Add temporal info to entity
            entity_with_temporal = {
                **entity,
                'temporal_state': result.temporal_state.value,
                'temporal_trigger': result.trigger_text,
                'temporal_confidence': result.confidence,
                'time_reference': result.time_reference,
            }

            if result.clinical_category:
                entity_with_temporal['clinical_temporal_category'] = result.clinical_category.value
                categories[result.clinical_category.value].append(entity_with_temporal)
            elif result.temporal_state == TemporalState.SUSPECTED:
                categories["suspected"].append(entity_with_temporal)
            else:
                categories["uncategorized"].append(entity_with_temporal)

        return categories


def create_reasoner(window_size: int = 8) -> ClinicalTemporalReasoner:
    """Factory function to create a temporal reasoner"""
    return ClinicalTemporalReasoner(window_size=window_size)


# =============================================================================
# EXAMPLE USAGE
# =============================================================================

if __name__ == "__main__":
    reasoner = create_reasoner()

    test_cases = [
        # Historical
        ("History of asthma", "asthma"),
        ("PMH: diabetes, hypertension", "diabetes"),
        ("Previous TIA in 2019", "TIA"),
        ("Known epilepsy", "epilepsy"),

        # Current
        ("Presents with chest pain", "chest pain"),
        ("Current collapse", "collapse"),
        ("Complains of headache", "headache"),
        ("On examination: tender abdomen", "tender abdomen"),

        # Resolved
        ("Resolved slurred speech", "slurred speech"),
        ("Pain now settled", "Pain"),
        ("Symptoms have improved", "Symptoms"),

        # Chronic
        ("Chronic back pain", "back pain"),
        ("Long-standing COPD", "COPD"),
        ("Type 2 diabetes", "Type 2 diabetes"),

        # Acute
        ("Acute onset chest pain", "chest pain"),
        ("Sudden collapse", "collapse"),
        ("New confusion", "confusion"),

        # Suspected
        ("?PE", "PE"),
        ("Possible TIA", "TIA"),
        ("Query meningitis", "meningitis"),
        ("For investigation of anaemia", "anaemia"),

        # Family history
        ("Family history of breast cancer", "breast cancer"),
        ("Mother has diabetes", "diabetes"),

        # Surgery history
        ("Previous appendectomy", "appendectomy"),
        ("Post hip replacement", "hip replacement"),
    ]

    print("Temporal Clinical Reasoning Test Results")
    print("=" * 70)

    for text, entity in test_cases:
        match = re.search(re.escape(entity), text, re.IGNORECASE)
        if match:
            result = reasoner.reason_temporal(text, entity, match.start(), match.end())
            cat_str = f"[{result.clinical_category.value}]" if result.clinical_category else ""
            print(f"\nText: \"{text}\"")
            print(f"Entity: \"{entity}\"")
            print(f"Temporal: {result.temporal_state.value:12} {cat_str}")
            if result.trigger_text:
                print(f"Trigger: \"{result.trigger_text}\"")
            if result.time_reference:
                print(f"Time ref: {result.time_reference}")
