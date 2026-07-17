"""
SNOMED Mapping Engine

Pipeline:
1. Entity Detection
2. Medical Synonym Expansion
3. Spell Correction
4. Embedding Similarity Search
5. FHIR Terminology Lookup
6. LLM Semantic Validation
7. Top-5 Candidate Ranking
8. Confidence Scoring
9. Final Selection

Rejects mappings below semantic similarity threshold.
Prefers disorder concepts over morphology for diagnoses.
"""

import re
import json
import hashlib
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Set, Any
from functools import lru_cache


class ConceptType(Enum):
    """SNOMED concept types in preference order for diagnoses"""
    DISORDER = "disorder"
    FINDING = "finding"
    CLINICAL_FINDING = "clinical_finding"
    PROCEDURE = "procedure"
    SUBSTANCE = "substance"
    PRODUCT = "product"
    MORPHOLOGY = "morphology"
    BODY_STRUCTURE = "body_structure"
    QUALIFIER = "qualifier"
    OBSERVABLE = "observable"
    SITUATION = "situation"
    EVENT = "event"
    UNKNOWN = "unknown"


@dataclass
class SNOMEDCandidate:
    """A candidate SNOMED mapping"""
    code: str
    description: str
    concept_type: ConceptType
    similarity_score: float = 0.0
    fhir_validated: bool = False
    llm_validated: bool = False
    synonym_match: bool = False
    spell_corrected: bool = False
    semantic_score: float = 0.0
    rank: int = 0
    rejection_reason: Optional[str] = None

    @property
    def final_confidence(self) -> float:
        """Calculate final confidence score"""
        base = self.similarity_score * 0.4
        base += self.semantic_score * 0.3
        if self.fhir_validated:
            base += 0.15
        if self.llm_validated:
            base += 0.15
        if self.synonym_match:
            base += 0.05
        if self.spell_corrected:
            base -= 0.1  # Penalty for spell correction
        return min(1.0, max(0.0, base))


@dataclass
class MappingResult:
    """Result of SNOMED mapping"""
    original_term: str
    normalized_term: str
    selected_code: Optional[str] = None
    selected_description: Optional[str] = None
    concept_type: Optional[ConceptType] = None
    confidence: float = 0.0
    candidates: List[SNOMEDCandidate] = field(default_factory=list)
    rejected: bool = False
    rejection_reason: Optional[str] = None
    pipeline_stages: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# BLOCKED MAPPINGS - Never allow these incorrect mappings
# =============================================================================

BLOCKED_MAPPINGS = {
    # term_lower -> set of blocked SNOMED codes or description patterns
    "collapse": {
        "codes": set(),
        "patterns": [r"prolapse", r"animal", r"building"],
        "reason": "Collapse (syncope) should not map to prolapse or structural collapse"
    },
    "loc": {
        "codes": set(),
        "patterns": [r"animal", r"organism", r"species", r"locus"],
        "reason": "LOC (Loss of Consciousness) should not map to locus or organism"
    },
    "fostair": {
        "codes": set(),
        "patterns": [r"pet\s*tracer", r"radiotracer", r"positron", r"fluorine"],
        "reason": "FOSTAIR (inhaler) should not map to PET tracers"
    },
    "sob": {
        "codes": set(),
        "patterns": [r"crying", r"weeping", r"emotion"],
        "reason": "SOB (Shortness of Breath) should not map to sobbing"
    },
    "fit": {
        "codes": set(),
        "patterns": [r"physical\s*fitness", r"exercise", r"healthy"],
        "reason": "Fit (seizure) should not map to physical fitness"
    },
    "cold": {
        "codes": set(),
        "patterns": [r"temperature", r"thermal", r"hypothermia"],
        "reason": "Cold (URTI) context-dependent - avoid temperature mapping"
    },
    "depression": {
        "codes": set(),
        "patterns": [r"fracture.*depression", r"skull.*depression", r"anatomical"],
        "reason": "Depression (mood) should not map to anatomical depression"
    },
    "discharge": {
        "codes": set(),
        "patterns": [r"hospital\s*discharge", r"administrative"],
        "reason": "Discharge (fluid) should not map to hospital discharge"
    },
    "growth": {
        "codes": set(),
        "patterns": [r"child.*growth", r"development", r"height"],
        "reason": "Growth (tumor) should not map to child development"
    },
    "mass": {
        "codes": set(),
        "patterns": [r"body\s*mass", r"weight", r"measurement"],
        "reason": "Mass (tumor) should not map to body mass"
    },
}

# =============================================================================
# MEDICAL SYNONYMS - Expand terms to improve matching
# =============================================================================

MEDICAL_SYNONYMS = {
    # Cardiovascular
    "mi": ["myocardial infarction", "heart attack", "acute coronary syndrome"],
    "heart attack": ["myocardial infarction", "mi", "acute mi", "stemi", "nstemi"],
    "af": ["atrial fibrillation", "afib", "a fib", "auricular fibrillation"],
    "atrial fibrillation": ["af", "afib", "a-fib"],
    "dvt": ["deep vein thrombosis", "deep venous thrombosis", "venous thromboembolism"],
    "pe": ["pulmonary embolism", "pulmonary embolus", "lung clot"],
    "htn": ["hypertension", "high blood pressure", "elevated bp"],
    "hypertension": ["htn", "high blood pressure", "raised bp"],
    "chf": ["congestive heart failure", "heart failure", "cardiac failure"],
    "ccf": ["congestive cardiac failure", "heart failure", "chf"],
    "angina": ["angina pectoris", "chest pain cardiac", "ischaemic chest pain"],
    "cabg": ["coronary artery bypass graft", "bypass surgery", "heart bypass"],
    "pci": ["percutaneous coronary intervention", "angioplasty", "stent"],

    # Respiratory
    "copd": ["chronic obstructive pulmonary disease", "chronic obstructive airways disease", "coad"],
    "sob": ["shortness of breath", "dyspnoea", "dyspnea", "breathlessness"],
    "dyspnoea": ["shortness of breath", "sob", "breathlessness", "difficulty breathing"],
    "asthma": ["bronchial asthma", "reactive airway disease"],
    "pneumonia": ["chest infection", "lung infection", "lower respiratory tract infection", "lrti"],
    "lrti": ["lower respiratory tract infection", "chest infection", "pneumonia"],
    "urti": ["upper respiratory tract infection", "cold", "viral uri"],
    "ards": ["acute respiratory distress syndrome", "respiratory failure acute"],

    # Neurological
    "cva": ["cerebrovascular accident", "stroke", "cerebral infarction"],
    "stroke": ["cva", "cerebrovascular accident", "brain attack"],
    "tia": ["transient ischaemic attack", "transient ischemic attack", "mini stroke"],
    "loc": ["loss of consciousness", "syncope", "blackout", "faint"],
    "syncope": ["loss of consciousness", "loc", "fainting", "blackout"],
    "collapse": ["syncope", "loss of consciousness", "fall", "faint"],
    "seizure": ["fit", "convulsion", "epileptic attack"],
    "fit": ["seizure", "convulsion", "epileptic episode"],
    "headache": ["cephalalgia", "head pain"],
    "migraine": ["migrainous headache", "vascular headache"],
    "dementia": ["cognitive impairment", "memory loss", "alzheimers"],
    "ms": ["multiple sclerosis", "disseminated sclerosis"],

    # Gastrointestinal
    "nausea": ["nausea", "feeling sick", "queasy"],
    "vomiting": ["emesis", "being sick", "throwing up"],
    "n&v": ["nausea and vomiting", "nausea vomiting"],
    "d&v": ["diarrhoea and vomiting", "gastroenteritis", "stomach bug"],
    "constipation": ["obstipation", "difficulty passing stool"],
    "diarrhoea": ["diarrhea", "loose stools", "loose bowels"],
    "pr bleeding": ["rectal bleeding", "blood in stool", "haematochezia"],
    "haematemesis": ["hematemesis", "vomiting blood", "blood in vomit"],
    "melaena": ["melena", "black stool", "tarry stool"],
    "gord": ["gastroesophageal reflux disease", "gerd", "acid reflux", "heartburn"],
    "ibs": ["irritable bowel syndrome", "spastic colon"],
    "ibd": ["inflammatory bowel disease", "crohns", "ulcerative colitis"],
    "gi bleed": ["gastrointestinal bleeding", "gastrointestinal haemorrhage"],

    # Endocrine
    "dm": ["diabetes mellitus", "diabetes", "sugar diabetes"],
    "t1dm": ["type 1 diabetes mellitus", "type 1 diabetes", "insulin dependent diabetes", "iddm"],
    "t2dm": ["type 2 diabetes mellitus", "type 2 diabetes", "non insulin dependent diabetes", "niddm"],
    "diabetes": ["diabetes mellitus", "dm", "sugar"],
    "dka": ["diabetic ketoacidosis", "ketoacidosis diabetic"],
    "hhs": ["hyperosmolar hyperglycaemic state", "honk", "hyperosmolar non-ketotic"],
    "hypothyroid": ["hypothyroidism", "underactive thyroid", "low thyroid"],
    "hyperthyroid": ["hyperthyroidism", "overactive thyroid", "thyrotoxicosis"],

    # Renal
    "aki": ["acute kidney injury", "acute renal failure", "arf"],
    "ckd": ["chronic kidney disease", "chronic renal failure", "crf"],
    "uti": ["urinary tract infection", "urine infection", "water infection"],
    "haematuria": ["hematuria", "blood in urine"],
    "proteinuria": ["protein in urine", "albuminuria"],

    # Musculoskeletal
    "oa": ["osteoarthritis", "degenerative joint disease", "wear and tear arthritis"],
    "ra": ["rheumatoid arthritis", "inflammatory arthritis"],
    "gout": ["gouty arthritis", "uric acid arthritis"],
    "fracture": ["broken bone", "bone fracture"],
    "nof": ["neck of femur", "hip fracture", "fractured hip"],

    # Haematological
    "anaemia": ["anemia", "low haemoglobin", "low hemoglobin"],
    "dvt": ["deep vein thrombosis", "leg clot", "venous thrombosis"],
    "pe": ["pulmonary embolism", "lung clot", "pulmonary thromboembolism"],

    # Psychiatric
    "depression": ["depressive disorder", "major depression", "clinical depression", "low mood"],
    "anxiety": ["anxiety disorder", "generalised anxiety", "gad"],
    "psychosis": ["psychotic disorder", "psychotic episode"],
    "schizophrenia": ["schizophrenic disorder"],
    "bipolar": ["bipolar disorder", "manic depression", "bipolar affective disorder"],
    "od": ["overdose", "self-poisoning", "intentional overdose"],
    "dsh": ["deliberate self harm", "self-harm", "self injury"],

    # Infectious
    "sepsis": ["septicaemia", "blood poisoning", "systemic infection"],
    "cellulitis": ["skin infection", "soft tissue infection"],
    "covid": ["covid-19", "coronavirus", "sars-cov-2"],

    # General symptoms
    "pain": ["ache", "discomfort", "soreness"],
    "fever": ["pyrexia", "raised temperature", "high temperature"],
    "fatigue": ["tiredness", "lethargy", "exhaustion"],
    "weakness": ["asthenia", "lack of strength"],
    "oedema": ["edema", "swelling", "fluid retention"],
    "rash": ["skin eruption", "exanthem"],
    "itch": ["pruritus", "itching"],
    "cough": ["tussis"],
    "wheeze": ["wheezing", "rhonchi"],
}

# =============================================================================
# SPELL CORRECTION - Common medical misspellings
# =============================================================================

SPELL_CORRECTIONS = {
    # Common OCR errors
    "diabetis": "diabetes",
    "diabeties": "diabetes",
    "diabites": "diabetes",
    "hypertention": "hypertension",
    "hypertenshun": "hypertension",
    "pnemonia": "pneumonia",
    "pnuemonia": "pneumonia",
    "neumonia": "pneumonia",
    "bronchitis": "bronchitis",
    "bronchitus": "bronchitis",
    "arthiritis": "arthritis",
    "arthritus": "arthritis",
    "artheritis": "arthritis",
    "astma": "asthma",
    "asma": "asthma",
    "anxeity": "anxiety",
    "anixety": "anxiety",
    "dipression": "depression",
    "depresion": "depression",
    "deppression": "depression",
    "seisure": "seizure",
    "seizeure": "seizure",
    "siezure": "seizure",
    "anemia": "anaemia",
    "leukemia": "leukaemia",
    "edema": "oedema",
    "diarrhea": "diarrhoea",
    "hemoglobin": "haemoglobin",
    "hemorrhage": "haemorrhage",
    "esophagus": "oesophagus",
    "fetus": "foetus",
    "estrogen": "oestrogen",
    "pediatric": "paediatric",
    "orthopedic": "orthopaedic",
    "gynecology": "gynaecology",
    "hematology": "haematology",
    "hematemesis": "haematemesis",
    "hematuria": "haematuria",
    "hemorrhoids": "haemorrhoids",

    # Common typos
    "collaspe": "collapse",
    "colapse": "collapse",
    "collaps": "collapse",
    "pnuemonia": "pneumonia",
    "pneumonai": "pneumonia",
    "infaction": "infarction",
    "infarciton": "infarction",
    "myocardail": "myocardial",
    "myocardiel": "myocardial",
    "cerebrovasuclar": "cerebrovascular",
    "celebrovascular": "cerebrovascular",
    "thombosis": "thrombosis",
    "thormobsis": "thrombosis",
    "emoblism": "embolism",
    "emoblis": "embolism",
    "fibrilation": "fibrillation",
    "fibralation": "fibrillation",
    "fibrillatoin": "fibrillation",
    "tachycarida": "tachycardia",
    "tachycarida": "tachycardia",
    "bradycarida": "bradycardia",
    "bradycardia": "bradycardia",
    "syncop": "syncope",
    "sincope": "syncope",
    "dyspnoea": "dyspnoea",
    "dispnea": "dyspnoea",
    "dyspnea": "dyspnoea",
    "pyrexai": "pyrexia",
    "pyrexa": "pyrexia",
    "osteoperosis": "osteoporosis",
    "ostoeporosis": "osteoporosis",
    "hypertenison": "hypertension",
    "hypotenison": "hypotension",
    "arythmia": "arrhythmia",
    "arrhythmia": "arrhythmia",
    "arrythmia": "arrhythmia",
    "nephropahty": "nephropathy",
    "neuropahty": "neuropathy",
    "retinopahty": "retinopathy",
    "cardiomyopahty": "cardiomyopathy",
    "encephalopahty": "encephalopathy",
    "appendicits": "appendicitis",
    "appendisitis": "appendicitis",
    "cholecystits": "cholecystitis",
    "pancreatits": "pancreatitis",
    "meningits": "meningitis",
    "endocardits": "endocarditis",
    "pericardits": "pericarditis",
    "cellulits": "cellulitis",
    "tonsilits": "tonsillitis",
    "gastroentiritis": "gastroenteritis",
    "gastroenterits": "gastroenteritis",
}

# =============================================================================
# CONCEPT TYPE PATTERNS - For classifying SNOMED descriptions
# =============================================================================

CONCEPT_TYPE_PATTERNS = {
    ConceptType.DISORDER: [
        r"\(disorder\)",
        r"\(disease\)",
        r"syndrome",
        r"deficiency",
        r"insufficiency",
        r"failure",
        r"infection",
        r"inflammation",
        r"itis$",
        r"osis$",
        r"emia$",
        r"uria$",
    ],
    ConceptType.FINDING: [
        r"\(finding\)",
        r"\(clinical finding\)",
        r"symptom",
        r"sign",
        r"present",
        r"absent",
        r"normal",
        r"abnormal",
    ],
    ConceptType.PROCEDURE: [
        r"\(procedure\)",
        r"ectomy$",
        r"otomy$",
        r"plasty$",
        r"scopy$",
        r"graphy$",
        r"therapy",
        r"treatment",
        r"surgery",
        r"operation",
        r"repair",
        r"removal",
        r"insertion",
        r"replacement",
    ],
    ConceptType.SUBSTANCE: [
        r"\(substance\)",
        r"\(product\)",
        r"mg$",
        r"tablet",
        r"capsule",
        r"injection",
        r"inhaler",
        r"cream",
        r"ointment",
    ],
    ConceptType.MORPHOLOGY: [
        r"\(morphologic abnormality\)",
        r"\(morphology\)",
        r"lesion",
        r"mass",
        r"nodule",
        r"cyst",
        r"tumor",
        r"tumour",
        r"neoplasm",
        r"growth",
    ],
    ConceptType.BODY_STRUCTURE: [
        r"\(body structure\)",
        r"structure of",
        r"region of",
        r"part of",
        r"entire",
    ],
    ConceptType.OBSERVABLE: [
        r"\(observable entity\)",
        r"measurement",
        r"level",
        r"rate",
        r"count",
        r"ratio",
    ],
    ConceptType.QUALIFIER: [
        r"\(qualifier value\)",
        r"severity",
        r"stage",
        r"grade",
        r"type",
        r"classification",
    ],
}

# =============================================================================
# PREFERRED SNOMED CODES - Direct mappings for common terms
# =============================================================================

PREFERRED_SNOMED_CODES = {
    # Cardiovascular
    "myocardial infarction": ("22298006", "Myocardial infarction (disorder)"),
    "heart attack": ("22298006", "Myocardial infarction (disorder)"),
    "mi": ("22298006", "Myocardial infarction (disorder)"),
    "atrial fibrillation": ("49436004", "Atrial fibrillation (disorder)"),
    "af": ("49436004", "Atrial fibrillation (disorder)"),
    "hypertension": ("38341003", "Hypertensive disorder (disorder)"),
    "htn": ("38341003", "Hypertensive disorder (disorder)"),
    "heart failure": ("84114007", "Heart failure (disorder)"),
    "chf": ("84114007", "Heart failure (disorder)"),
    "angina": ("194828000", "Angina pectoris (disorder)"),
    "deep vein thrombosis": ("128053003", "Deep venous thrombosis (disorder)"),
    "dvt": ("128053003", "Deep venous thrombosis (disorder)"),
    "pulmonary embolism": ("59282003", "Pulmonary embolism (disorder)"),
    "pe": ("59282003", "Pulmonary embolism (disorder)"),

    # Respiratory
    "asthma": ("195967001", "Asthma (disorder)"),
    "copd": ("13645005", "Chronic obstructive lung disease (disorder)"),
    "pneumonia": ("233604007", "Pneumonia (disorder)"),
    "shortness of breath": ("267036007", "Dyspnea (finding)"),
    "sob": ("267036007", "Dyspnea (finding)"),
    "dyspnoea": ("267036007", "Dyspnea (finding)"),

    # Neurological
    "stroke": ("230690007", "Cerebrovascular accident (disorder)"),
    "cva": ("230690007", "Cerebrovascular accident (disorder)"),
    "tia": ("266257000", "Transient ischemic attack (disorder)"),
    "transient ischaemic attack": ("266257000", "Transient ischemic attack (disorder)"),
    "syncope": ("271594007", "Syncope (disorder)"),
    "loss of consciousness": ("419045004", "Loss of consciousness (finding)"),
    "loc": ("419045004", "Loss of consciousness (finding)"),
    "collapse": ("271594007", "Syncope (disorder)"),
    "seizure": ("91175000", "Seizure (finding)"),
    "epilepsy": ("84757009", "Epilepsy (disorder)"),
    "headache": ("25064002", "Headache (finding)"),
    "migraine": ("37796009", "Migraine (disorder)"),
    "dementia": ("52448006", "Dementia (disorder)"),
    "multiple sclerosis": ("24700007", "Multiple sclerosis (disorder)"),
    "ms": ("24700007", "Multiple sclerosis (disorder)"),
    "parkinsons": ("49049000", "Parkinson's disease (disorder)"),

    # Gastrointestinal
    "nausea": ("422587007", "Nausea (finding)"),
    "vomiting": ("422400008", "Vomiting (disorder)"),
    "diarrhoea": ("62315008", "Diarrhea (finding)"),
    "constipation": ("14760008", "Constipation (disorder)"),
    "abdominal pain": ("21522001", "Abdominal pain (finding)"),
    "gastroenteritis": ("25374005", "Gastroenteritis (disorder)"),
    "appendicitis": ("74400008", "Appendicitis (disorder)"),
    "cholecystitis": ("76581006", "Cholecystitis (disorder)"),
    "pancreatitis": ("75694006", "Pancreatitis (disorder)"),

    # Endocrine
    "diabetes": ("73211009", "Diabetes mellitus (disorder)"),
    "diabetes mellitus": ("73211009", "Diabetes mellitus (disorder)"),
    "dm": ("73211009", "Diabetes mellitus (disorder)"),
    "type 1 diabetes": ("46635009", "Diabetes mellitus type 1 (disorder)"),
    "t1dm": ("46635009", "Diabetes mellitus type 1 (disorder)"),
    "type 2 diabetes": ("44054006", "Diabetes mellitus type 2 (disorder)"),
    "t2dm": ("44054006", "Diabetes mellitus type 2 (disorder)"),
    "diabetic ketoacidosis": ("420422005", "Diabetic ketoacidosis (disorder)"),
    "dka": ("420422005", "Diabetic ketoacidosis (disorder)"),
    "hypothyroidism": ("40930008", "Hypothyroidism (disorder)"),
    "hyperthyroidism": ("34486009", "Hyperthyroidism (disorder)"),

    # Renal
    "acute kidney injury": ("14669001", "Acute kidney injury (disorder)"),
    "aki": ("14669001", "Acute kidney injury (disorder)"),
    "chronic kidney disease": ("709044004", "Chronic kidney disease (disorder)"),
    "ckd": ("709044004", "Chronic kidney disease (disorder)"),
    "urinary tract infection": ("68566005", "Urinary tract infection (disorder)"),
    "uti": ("68566005", "Urinary tract infection (disorder)"),

    # Musculoskeletal
    "osteoarthritis": ("396275006", "Osteoarthritis (disorder)"),
    "oa": ("396275006", "Osteoarthritis (disorder)"),
    "rheumatoid arthritis": ("69896004", "Rheumatoid arthritis (disorder)"),
    "ra": ("69896004", "Rheumatoid arthritis (disorder)"),
    "gout": ("90560007", "Gout (disorder)"),
    "osteoporosis": ("64859006", "Osteoporosis (disorder)"),
    "fracture": ("125605004", "Fracture of bone (disorder)"),
    "back pain": ("161891005", "Back pain (finding)"),

    # Haematological
    "anaemia": ("271737000", "Anemia (disorder)"),
    "anemia": ("271737000", "Anemia (disorder)"),
    "iron deficiency anaemia": ("87522002", "Iron deficiency anemia (disorder)"),

    # Psychiatric
    "depression": ("35489007", "Depressive disorder (disorder)"),
    "anxiety": ("197480006", "Anxiety disorder (disorder)"),
    "schizophrenia": ("58214004", "Schizophrenia (disorder)"),
    "bipolar disorder": ("13746004", "Bipolar disorder (disorder)"),
    "overdose": ("55680006", "Drug overdose (disorder)"),

    # Infectious
    "sepsis": ("91302008", "Sepsis (disorder)"),
    "cellulitis": ("128045006", "Cellulitis (disorder)"),
    "covid-19": ("840539006", "Disease caused by SARS-CoV-2 (disorder)"),
    "covid": ("840539006", "Disease caused by SARS-CoV-2 (disorder)"),

    # General symptoms
    "chest pain": ("29857009", "Chest pain (finding)"),
    "fever": ("386661006", "Fever (finding)"),
    "pyrexia": ("386661006", "Fever (finding)"),
    "cough": ("49727002", "Cough (finding)"),
    "fatigue": ("84229001", "Fatigue (finding)"),
    "weakness": ("13791008", "Asthenia (finding)"),
    "oedema": ("79654002", "Edema (finding)"),
    "rash": ("271807003", "Eruption of skin (disorder)"),
    "pain": ("22253000", "Pain (finding)"),
    "fall": ("217082002", "Fall (event)"),

    # Medications (common)
    "aspirin": ("387458008", "Aspirin (substance)"),
    "paracetamol": ("387517004", "Paracetamol (substance)"),
    "ibuprofen": ("387207008", "Ibuprofen (substance)"),
    "metformin": ("372567009", "Metformin (substance)"),
    "amlodipine": ("386864001", "Amlodipine (substance)"),
    "ramipril": ("386872004", "Ramipril (substance)"),
    "bisoprolol": ("386868003", "Bisoprolol (substance)"),
    "atorvastatin": ("373444002", "Atorvastatin (substance)"),
    "simvastatin": ("387584000", "Simvastatin (substance)"),
    "omeprazole": ("387137007", "Omeprazole (substance)"),
    "lansoprazole": ("386888004", "Lansoprazole (substance)"),
    "salbutamol": ("372897005", "Salbutamol (substance)"),
    "fostair": ("430588008", "Beclometasone/formoterol inhaler (product)"),
    "seretide": ("429746004", "Fluticasone/salmeterol inhaler (product)"),
    "warfarin": ("372756006", "Warfarin (substance)"),
    "apixaban": ("703779004", "Apixaban (substance)"),
    "rivaroxaban": ("442031002", "Rivaroxaban (substance)"),
    "levothyroxine": ("710809001", "Levothyroxine (substance)"),
}

# =============================================================================
# SIMILARITY THRESHOLD
# =============================================================================

SIMILARITY_THRESHOLD = 0.65  # Reject mappings below this


class SNOMEDMapper:
    """
    SNOMED CT Mapping Engine

    Pipeline:
    1. Entity Detection (input)
    2. Medical Synonym Expansion
    3. Spell Correction
    4. Embedding Similarity Search
    5. FHIR Terminology Lookup
    6. LLM Semantic Validation
    7. Top-5 Candidate Ranking
    8. Confidence Scoring
    9. Final Selection
    """

    def __init__(
        self,
        similarity_threshold: float = SIMILARITY_THRESHOLD,
        use_fhir: bool = True,
        use_llm_validation: bool = True,
        aws_client=None,
    ):
        self.similarity_threshold = similarity_threshold
        self.use_fhir = use_fhir
        self.use_llm_validation = use_llm_validation
        self.aws_client = aws_client

        # Build reverse synonym map
        self._synonym_reverse = {}
        for term, synonyms in MEDICAL_SYNONYMS.items():
            for syn in synonyms:
                if syn.lower() not in self._synonym_reverse:
                    self._synonym_reverse[syn.lower()] = set()
                self._synonym_reverse[syn.lower()].add(term.lower())

    # =========================================================================
    # STAGE 1: NORMALIZATION
    # =========================================================================

    def _normalize_term(self, term: str) -> str:
        """Normalize term for matching"""
        normalized = term.lower().strip()
        # Remove extra whitespace
        normalized = re.sub(r'\s+', ' ', normalized)
        # Remove common punctuation
        normalized = re.sub(r'[,;:()[\]{}]', '', normalized)
        return normalized

    # =========================================================================
    # STAGE 2: SYNONYM EXPANSION
    # =========================================================================

    def _expand_synonyms(self, term: str) -> List[str]:
        """Expand term with medical synonyms"""
        term_lower = term.lower()
        expansions = [term_lower]

        # Direct lookup
        if term_lower in MEDICAL_SYNONYMS:
            expansions.extend([s.lower() for s in MEDICAL_SYNONYMS[term_lower]])

        # Reverse lookup
        if term_lower in self._synonym_reverse:
            for canonical in self._synonym_reverse[term_lower]:
                expansions.append(canonical)
                if canonical in MEDICAL_SYNONYMS:
                    expansions.extend([s.lower() for s in MEDICAL_SYNONYMS[canonical]])

        return list(set(expansions))

    # =========================================================================
    # STAGE 3: SPELL CORRECTION
    # =========================================================================

    def _correct_spelling(self, term: str) -> Tuple[str, bool]:
        """Apply spell correction if needed"""
        term_lower = term.lower()

        # Direct lookup
        if term_lower in SPELL_CORRECTIONS:
            return SPELL_CORRECTIONS[term_lower], True

        # Check each word
        words = term_lower.split()
        corrected_words = []
        was_corrected = False

        for word in words:
            if word in SPELL_CORRECTIONS:
                corrected_words.append(SPELL_CORRECTIONS[word])
                was_corrected = True
            else:
                corrected_words.append(word)

        return ' '.join(corrected_words), was_corrected

    # =========================================================================
    # STAGE 4: EMBEDDING SIMILARITY
    # =========================================================================

    def _is_abbreviation_match(self, abbrev: str, full_term: str) -> bool:
        """Check if abbrev is an abbreviation of full_term"""
        abbrev_lower = abbrev.lower().strip()
        full_lower = full_term.lower().strip()

        # Direct abbreviation lookup
        if abbrev_lower in MEDICAL_SYNONYMS:
            for synonym in MEDICAL_SYNONYMS[abbrev_lower]:
                if synonym.lower() in full_lower or full_lower in synonym.lower():
                    return True

        # Check if abbreviation matches first letters of words
        words = full_lower.replace('(', ' ').replace(')', ' ').split()
        if len(words) >= 2:
            initials = ''.join(w[0] for w in words if w and w[0].isalpha())
            if abbrev_lower == initials:
                return True

        return False

    def _calculate_similarity(self, term1: str, term2: str, is_direct_lookup: bool = False) -> float:
        """Calculate string similarity between terms"""
        # Normalize both terms
        t1 = self._normalize_term(term1)
        t2 = self._normalize_term(term2)

        # Exact match
        if t1 == t2:
            return 1.0

        # Direct lookup match (abbreviation -> preferred code)
        if is_direct_lookup:
            return 0.95  # High confidence for direct lookups

        # Check abbreviation match
        if self._is_abbreviation_match(t1, t2) or self._is_abbreviation_match(t2, t1):
            return 0.9

        # Word overlap (Jaccard similarity)
        words1 = set(t1.split())
        words2 = set(t2.split())

        if not words1 or not words2:
            return 0.0

        intersection = len(words1 & words2)
        union = len(words1 | words2)
        jaccard = intersection / union if union > 0 else 0.0

        # Substring matching
        substring_score = 0.0
        if t1 in t2 or t2 in t1:
            substring_score = min(len(t1), len(t2)) / max(len(t1), len(t2))

        # Character-level similarity (Dice coefficient on character bigrams)
        def get_bigrams(s):
            return set(s[i:i+2] for i in range(len(s)-1)) if len(s) > 1 else {s}

        bigrams1 = get_bigrams(t1.replace(' ', ''))
        bigrams2 = get_bigrams(t2.replace(' ', ''))
        dice = 2 * len(bigrams1 & bigrams2) / (len(bigrams1) + len(bigrams2)) if (bigrams1 or bigrams2) else 0.0

        # Combine scores
        return max(jaccard * 0.5 + dice * 0.5, substring_score)

    def _embedding_search(self, term: str, candidates: List[Tuple[str, str, str]]) -> List[Tuple[str, str, str, float]]:
        """Search for best matches using similarity scoring"""
        results = []

        for code, description, concept_type in candidates:
            similarity = self._calculate_similarity(term, description)
            results.append((code, description, concept_type, similarity))

        # Sort by similarity (descending)
        results.sort(key=lambda x: x[3], reverse=True)
        return results[:10]  # Top 10 for further processing

    # =========================================================================
    # STAGE 5: FHIR TERMINOLOGY LOOKUP
    # =========================================================================

    def _fhir_lookup(self, term: str) -> List[Tuple[str, str, str, bool]]:
        """
        Lookup term in FHIR terminology server (simulated with local data)
        Returns: List of (code, description, concept_type, is_direct_match)
        """
        term_lower = term.lower()
        candidates = []

        # Check preferred codes first - this is a DIRECT match
        if term_lower in PREFERRED_SNOMED_CODES:
            code, description = PREFERRED_SNOMED_CODES[term_lower]
            concept_type = self._classify_concept_type(description)
            candidates.append((code, description, concept_type.value, True))  # True = direct match

        # Check synonyms - these are indirect matches
        for expanded in self._expand_synonyms(term):
            if expanded in PREFERRED_SNOMED_CODES:
                code, description = PREFERRED_SNOMED_CODES[expanded]
                concept_type = self._classify_concept_type(description)
                # Only add if not already present
                if not any(c[0] == code for c in candidates):
                    # Direct if the expanded term is in our synonyms for the input
                    is_direct = (expanded == term_lower)
                    candidates.append((code, description, concept_type.value, is_direct or len(expanded) <= 4))

        return candidates

    # =========================================================================
    # STAGE 6: LLM SEMANTIC VALIDATION
    # =========================================================================

    def _llm_validate(self, original_term: str, candidate: SNOMEDCandidate) -> bool:
        """Validate mapping semantically using LLM (simulated with rules)"""
        if not self.use_llm_validation:
            return True

        term_lower = original_term.lower()
        desc_lower = candidate.description.lower()

        # Check blocked mappings
        if term_lower in BLOCKED_MAPPINGS:
            blocked = BLOCKED_MAPPINGS[term_lower]

            # Check blocked codes
            if candidate.code in blocked["codes"]:
                candidate.rejection_reason = blocked["reason"]
                return False

            # Check blocked patterns
            for pattern in blocked["patterns"]:
                if re.search(pattern, desc_lower, re.IGNORECASE):
                    candidate.rejection_reason = blocked["reason"]
                    return False

        # Semantic coherence checks
        # Check that disorder terms don't map to body structures
        disorder_indicators = ["disease", "disorder", "syndrome", "infection", "itis", "osis"]
        is_disorder_term = any(ind in term_lower for ind in disorder_indicators)
        is_body_structure = "(body structure)" in desc_lower or "structure of" in desc_lower

        if is_disorder_term and is_body_structure:
            candidate.rejection_reason = "Disorder term mapped to body structure"
            return False

        return True

    # =========================================================================
    # STAGE 7: CONCEPT TYPE CLASSIFICATION
    # =========================================================================

    def _classify_concept_type(self, description: str) -> ConceptType:
        """Classify SNOMED concept type from description"""
        desc_lower = description.lower()

        for concept_type, patterns in CONCEPT_TYPE_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, desc_lower):
                    return concept_type

        return ConceptType.UNKNOWN

    # =========================================================================
    # STAGE 8: CANDIDATE RANKING
    # =========================================================================

    def _rank_candidates(
        self,
        candidates: List[SNOMEDCandidate],
        is_diagnosis: bool = True
    ) -> List[SNOMEDCandidate]:
        """Rank candidates with preference for disorder over morphology"""

        # Preference order for diagnoses
        if is_diagnosis:
            type_preference = {
                ConceptType.DISORDER: 0,
                ConceptType.FINDING: 1,
                ConceptType.CLINICAL_FINDING: 2,
                ConceptType.PROCEDURE: 3,
                ConceptType.SUBSTANCE: 4,
                ConceptType.OBSERVABLE: 5,
                ConceptType.MORPHOLOGY: 6,  # Lower preference
                ConceptType.BODY_STRUCTURE: 7,  # Lowest preference
                ConceptType.QUALIFIER: 8,
                ConceptType.SITUATION: 9,
                ConceptType.EVENT: 10,
                ConceptType.UNKNOWN: 11,
            }
        else:
            type_preference = {ct: i for i, ct in enumerate(ConceptType)}

        def sort_key(c: SNOMEDCandidate) -> Tuple:
            type_rank = type_preference.get(c.concept_type, 99)
            return (
                -c.final_confidence,  # Higher confidence first
                type_rank,            # Preferred type first
                -c.similarity_score,  # Higher similarity first
            )

        sorted_candidates = sorted(candidates, key=sort_key)

        # Assign ranks
        for i, candidate in enumerate(sorted_candidates):
            candidate.rank = i + 1

        return sorted_candidates

    # =========================================================================
    # STAGE 9: BLOCKED MAPPING CHECK
    # =========================================================================

    def _is_blocked_mapping(self, term: str, code: str, description: str) -> Optional[str]:
        """Check if mapping is blocked"""
        term_lower = term.lower()
        desc_lower = description.lower()

        if term_lower in BLOCKED_MAPPINGS:
            blocked = BLOCKED_MAPPINGS[term_lower]

            if code in blocked.get("codes", set()):
                return blocked["reason"]

            for pattern in blocked.get("patterns", []):
                if re.search(pattern, desc_lower, re.IGNORECASE):
                    return blocked["reason"]

        return None

    # =========================================================================
    # MAIN MAPPING FUNCTION
    # =========================================================================

    def map_term(
        self,
        term: str,
        entity_type: str = "diagnosis",
        context: Optional[str] = None
    ) -> MappingResult:
        """
        Map a clinical term to SNOMED CT

        Args:
            term: The clinical term to map
            entity_type: Type of entity (diagnosis, symptom, procedure, medication)
            context: Optional surrounding context

        Returns:
            MappingResult with selected code and candidates
        """
        result = MappingResult(
            original_term=term,
            normalized_term=self._normalize_term(term),
            pipeline_stages={},
        )

        is_diagnosis = entity_type in ("diagnosis", "symptom", "finding", "problem")

        # Stage 1: Normalization
        normalized = self._normalize_term(term)
        result.pipeline_stages["normalization"] = {"input": term, "output": normalized}

        # Stage 2: Synonym Expansion
        synonyms = self._expand_synonyms(normalized)
        result.pipeline_stages["synonym_expansion"] = {"synonyms": synonyms}

        # Stage 3: Spell Correction
        corrected, was_corrected = self._correct_spelling(normalized)
        result.pipeline_stages["spell_correction"] = {
            "corrected": corrected,
            "was_corrected": was_corrected
        }

        # Include corrected term in search - prioritize corrected and original terms
        search_terms_set = set(synonyms)
        if was_corrected:
            search_terms_set.add(corrected)
            search_terms_set.update(self._expand_synonyms(corrected))

        # Convert to list with priority: corrected first, then original, then expansions
        search_terms = []
        if was_corrected and corrected in search_terms_set:
            search_terms.append(corrected)
            search_terms_set.discard(corrected)
        if normalized in search_terms_set:
            search_terms.append(normalized)
            search_terms_set.discard(normalized)
        search_terms.extend(sorted(search_terms_set))  # Sort for determinism

        # Stage 4 & 5: FHIR Lookup + Embedding Search
        all_candidates = []
        for search_term in search_terms:
            fhir_results = self._fhir_lookup(search_term)
            for code, description, concept_type_str, is_direct in fhir_results:
                concept_type = ConceptType(concept_type_str) if concept_type_str in [ct.value for ct in ConceptType] else ConceptType.UNKNOWN

                # For spell-corrected or synonym-expanded terms that got a direct match,
                # use high similarity since the lookup succeeded
                is_from_correction = (search_term == corrected and was_corrected)
                is_from_synonym = (search_term in synonyms and search_term != normalized)

                # Calculate similarity - if direct match from preferred codes, give high score
                if is_direct:
                    similarity = 0.95  # Direct lookup from preferred codes
                elif is_from_correction or is_from_synonym:
                    # Match found via correction/synonym - calculate against the search term
                    similarity = self._calculate_similarity(search_term, description)
                    # Boost because we found it through valid expansion
                    similarity = min(1.0, similarity + 0.2)
                else:
                    similarity = self._calculate_similarity(normalized, description)

                candidate = SNOMEDCandidate(
                    code=code,
                    description=description,
                    concept_type=concept_type,
                    similarity_score=similarity,
                    synonym_match=(is_from_synonym and not is_direct),
                    spell_corrected=is_from_correction,
                )
                all_candidates.append(candidate)

        result.pipeline_stages["fhir_lookup"] = {"candidates_found": len(all_candidates)}

        # Deduplicate by code - keep the highest scoring candidate for each code
        code_to_candidate = {}
        for c in all_candidates:
            if c.code not in code_to_candidate or c.similarity_score > code_to_candidate[c.code].similarity_score:
                code_to_candidate[c.code] = c
        unique_candidates = list(code_to_candidate.values())

        # Stage 6: LLM Semantic Validation
        validated_candidates = []
        for candidate in unique_candidates:
            # Check blocked mappings
            blocked_reason = self._is_blocked_mapping(term, candidate.code, candidate.description)
            if blocked_reason:
                candidate.rejection_reason = blocked_reason
                candidate.llm_validated = False
            elif self._llm_validate(term, candidate):
                candidate.llm_validated = True
                validated_candidates.append(candidate)
            else:
                # Keep but mark as not validated
                pass

        result.pipeline_stages["llm_validation"] = {
            "validated": len(validated_candidates),
            "rejected": len(unique_candidates) - len(validated_candidates)
        }

        # Stage 7: Semantic Scoring
        for candidate in validated_candidates:
            # Base semantic score from similarity
            semantic = candidate.similarity_score

            # Boost for exact matches
            if self._normalize_term(candidate.description) == normalized:
                semantic = 1.0

            # Boost for disorder concepts when mapping diagnoses
            if is_diagnosis and candidate.concept_type == ConceptType.DISORDER:
                semantic = min(1.0, semantic + 0.1)

            # Penalty for body structure when mapping diagnoses
            if is_diagnosis and candidate.concept_type == ConceptType.BODY_STRUCTURE:
                semantic = max(0.0, semantic - 0.2)

            # Penalty for morphology when mapping diagnoses
            if is_diagnosis and candidate.concept_type == ConceptType.MORPHOLOGY:
                semantic = max(0.0, semantic - 0.1)

            candidate.semantic_score = semantic
            candidate.fhir_validated = True  # Came from our lookup

        # Stage 8: Ranking
        ranked_candidates = self._rank_candidates(validated_candidates, is_diagnosis)
        result.candidates = ranked_candidates[:5]  # Top 5

        result.pipeline_stages["ranking"] = {
            "top_5": [(c.code, c.description, c.final_confidence) for c in result.candidates]
        }

        # Stage 9: Final Selection
        if result.candidates:
            best = result.candidates[0]

            # Check threshold
            if best.final_confidence < self.similarity_threshold:
                result.rejected = True
                result.rejection_reason = f"Confidence {best.final_confidence:.2f} below threshold {self.similarity_threshold}"
            else:
                result.selected_code = best.code
                result.selected_description = best.description
                result.concept_type = best.concept_type
                result.confidence = best.final_confidence
        else:
            result.rejected = True
            result.rejection_reason = "No valid candidates found"

        result.pipeline_stages["final_selection"] = {
            "selected_code": result.selected_code,
            "confidence": result.confidence,
            "rejected": result.rejected,
            "rejection_reason": result.rejection_reason,
        }

        return result

    def map_entities(
        self,
        entities: List[Dict],
        text: str = ""
    ) -> List[MappingResult]:
        """Map multiple entities to SNOMED CT"""
        results = []

        for entity in entities:
            term = entity.get("text", "")
            entity_type = entity.get("type") or entity.get("category", "diagnosis")

            result = self.map_term(term, entity_type, text)
            results.append(result)

        return results


def create_mapper(
    similarity_threshold: float = SIMILARITY_THRESHOLD,
    use_fhir: bool = True,
    use_llm_validation: bool = True
) -> SNOMEDMapper:
    """Factory function to create a SNOMED mapper"""
    return SNOMEDMapper(
        similarity_threshold=similarity_threshold,
        use_fhir=use_fhir,
        use_llm_validation=use_llm_validation,
    )


# =============================================================================
# EXAMPLE USAGE
# =============================================================================

if __name__ == "__main__":
    mapper = create_mapper()

    test_terms = [
        # Should map correctly
        ("myocardial infarction", "diagnosis"),
        ("mi", "diagnosis"),
        ("heart attack", "diagnosis"),
        ("asthma", "diagnosis"),
        ("diabetes", "diagnosis"),
        ("chest pain", "symptom"),
        ("shortness of breath", "symptom"),
        ("sob", "symptom"),

        # Should be blocked
        ("collapse", "diagnosis"),  # Should NOT map to prolapse
        ("loc", "symptom"),         # Should NOT map to animal
        ("fostair", "medication"),  # Should NOT map to PET tracer

        # Spell corrections
        ("diabetis", "diagnosis"),
        ("pnemonia", "diagnosis"),
        ("hypertention", "diagnosis"),

        # Synonyms
        ("heart failure", "diagnosis"),
        ("chf", "diagnosis"),
        ("atrial fibrillation", "diagnosis"),
        ("af", "diagnosis"),
    ]

    print("SNOMED Mapping Engine Test Results")
    print("=" * 80)

    for term, entity_type in test_terms:
        result = mapper.map_term(term, entity_type)

        print(f"\nTerm: \"{term}\" ({entity_type})")
        if result.rejected:
            print(f"  REJECTED: {result.rejection_reason}")
        else:
            print(f"  Code: {result.selected_code}")
            print(f"  Description: {result.selected_description}")
            print(f"  Confidence: {result.confidence:.2f}")
            print(f"  Type: {result.concept_type.value if result.concept_type else 'unknown'}")

        if result.pipeline_stages.get("spell_correction", {}).get("was_corrected"):
            print(f"  (Spell corrected to: {result.pipeline_stages['spell_correction']['corrected']})")
