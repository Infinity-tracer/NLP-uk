"""
Medical Named Entity Recognition (NER) Module

Extracts clinical entities into 17 distinct categories with no overlap.
Each entity is assigned to exactly one category based on:
  1. Section context (where it appears in the document)
  2. Linguistic patterns (how it's described)
  3. Category-specific validation rules
  4. Priority-based conflict resolution
"""

import re
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple, Any
from collections import defaultdict


class EntityCategory(Enum):
    """17 distinct clinical entity categories."""
    DIAGNOSIS = "diagnosis"
    SYMPTOM = "symptom"
    SIGN = "sign"
    INVESTIGATION = "investigation"
    PROCEDURE = "procedure"
    MEDICATION = "medication"
    ALLERGY = "allergy"
    SOCIAL_HISTORY = "social_history"
    PAST_MEDICAL_HISTORY = "past_medical_history"
    FAMILY_HISTORY = "family_history"
    DISCHARGE_ADVICE = "discharge_advice"
    FOLLOW_UP_PLAN = "follow_up_plan"
    GP_ACTION = "gp_action"
    HOSPITAL_ACTION = "hospital_action"
    REFERRAL = "referral"
    CLINICAL_SCORE = "clinical_score"
    VITAL_SIGN = "vital_sign"


@dataclass
class MedicalEntity:
    """A single extracted medical entity."""
    text: str
    category: EntityCategory
    confidence: float
    start_pos: int
    end_pos: int
    section: Optional[str] = None
    normalized_text: Optional[str] = None
    attributes: Dict[str, Any] = field(default_factory=dict)
    evidence: str = ""

    def to_dict(self) -> Dict:
        return {
            "text": self.text,
            "category": self.category.value,
            "confidence": round(self.confidence, 3),
            "start_pos": self.start_pos,
            "end_pos": self.end_pos,
            "section": self.section,
            "normalized_text": self.normalized_text,
            "attributes": self.attributes,
            "evidence": self.evidence,
        }


@dataclass
class NERResult:
    """Complete NER extraction result."""
    entities: List[MedicalEntity]
    by_category: Dict[str, List[MedicalEntity]]
    extraction_stats: Dict[str, int]

    def to_dict(self) -> Dict:
        return {
            "entities": [e.to_dict() for e in self.entities],
            "by_category": {
                cat: [e.to_dict() for e in ents]
                for cat, ents in self.by_category.items()
            },
            "stats": self.extraction_stats,
        }


# Section patterns for context-aware extraction
SECTION_PATTERNS: Dict[str, List[str]] = {
    "diagnosis": [
        r"(?:^|\n)\s*(?:DIAGNOS[IE]S?|IMPRESSION|CONCLUSION|ASSESSMENT)\s*:?\s*",
        r"(?:^|\n)\s*(?:PRIMARY|SECONDARY|WORKING|DIFFERENTIAL)\s+DIAGNOS[IE]S?\s*:?\s*",
        r"(?:^|\n)\s*(?:FINAL|PRINCIPAL)\s+DIAGNOS[IE]S?\s*:?\s*",
    ],
    "symptom": [
        r"(?:^|\n)\s*(?:PRESENTING\s+)?COMPLAINT[S]?\s*:?\s*",
        r"(?:^|\n)\s*(?:CHIEF\s+)?COMPLAINT[S]?\s*:?\s*",
        r"(?:^|\n)\s*HISTORY\s+OF\s+PRESENTING\s+(?:ILLNESS|COMPLAINT)\s*:?\s*",
        r"(?:^|\n)\s*(?:HPC|HPI)\s*:?\s*",
        r"(?:^|\n)\s*SYMPTOMS?\s*:?\s*",
    ],
    "sign": [
        r"(?:^|\n)\s*(?:PHYSICAL\s+)?EXAMINATION\s*:?\s*",
        r"(?:^|\n)\s*(?:ON\s+)?EXAMINATION\s*:?\s*",
        r"(?:^|\n)\s*(?:O/E|EXAM|FINDINGS)\s*:?\s*",
        r"(?:^|\n)\s*CLINICAL\s+(?:EXAMINATION|FINDINGS)\s*:?\s*",
    ],
    "investigation": [
        r"(?:^|\n)\s*INVESTIGATION[S]?\s*:?\s*",
        r"(?:^|\n)\s*(?:LAB(?:ORATORY)?|BLOOD)\s+(?:RESULTS?|TESTS?)\s*:?\s*",
        r"(?:^|\n)\s*(?:IMAGING|RADIOLOGY)\s*:?\s*",
        r"(?:^|\n)\s*(?:TEST|IX)\s+RESULTS?\s*:?\s*",
        r"(?:^|\n)\s*RESULTS?\s*:?\s*",
    ],
    "procedure": [
        r"(?:^|\n)\s*PROCEDURE[S]?\s*:?\s*",
        r"(?:^|\n)\s*(?:OPERATIVE|OPERATION)\s+(?:NOTES?|DETAILS?|FINDINGS?)\s*:?\s*",
        r"(?:^|\n)\s*(?:SURGICAL|INTERVENTION)\s*:?\s*",
        r"(?:^|\n)\s*TREATMENT\s+(?:GIVEN|PROVIDED|PERFORMED)\s*:?\s*",
    ],
    "medication": [
        r"(?:^|\n)\s*(?:CURRENT\s+)?MEDICATION[S]?\s*:?\s*",
        r"(?:^|\n)\s*(?:DISCHARGE\s+)?(?:DRUGS?|MEDICINES?|PRESCRIPTIONS?)\s*:?\s*",
        r"(?:^|\n)\s*(?:TTO|TTA|TTH)\s*:?\s*",
        r"(?:^|\n)\s*(?:DRUGS?\s+ON\s+)?(?:ADMISSION|DISCHARGE)\s*:?\s*",
    ],
    "allergy": [
        r"(?:^|\n)\s*ALLERG(?:Y|IES)\s*:?\s*",
        r"(?:^|\n)\s*(?:DRUG\s+)?ALLERG(?:Y|IES)\s*:?\s*",
        r"(?:^|\n)\s*(?:ADVERSE\s+)?REACTIONS?\s*:?\s*",
        r"(?:^|\n)\s*(?:NKDA|NKA)\s*",
    ],
    "social_history": [
        r"(?:^|\n)\s*SOCIAL\s+HISTORY\s*:?\s*",
        r"(?:^|\n)\s*(?:SHx|SH)\s*:?\s*",
        r"(?:^|\n)\s*(?:OCCUPATION|LIFESTYLE|LIVING\s+SITUATION)\s*:?\s*",
    ],
    "past_medical_history": [
        r"(?:^|\n)\s*(?:PAST\s+)?MEDICAL\s+HISTORY\s*:?\s*",
        r"(?:^|\n)\s*(?:PMH|PMHx)\s*:?\s*",
        r"(?:^|\n)\s*(?:BACKGROUND|PREVIOUS)\s+(?:HISTORY|CONDITIONS?)\s*:?\s*",
        r"(?:^|\n)\s*CO-?MORBIDITIES\s*:?\s*",
    ],
    "family_history": [
        r"(?:^|\n)\s*FAMILY\s+HISTORY\s*:?\s*",
        r"(?:^|\n)\s*(?:FHx|FH)\s*:?\s*",
    ],
    "discharge_advice": [
        r"(?:^|\n)\s*(?:DISCHARGE\s+)?ADVICE\s*:?\s*",
        r"(?:^|\n)\s*(?:PATIENT\s+)?(?:INFORMATION|INSTRUCTIONS?)\s*:?\s*",
        r"(?:^|\n)\s*SAFETY\s+NET(?:TING)?\s*:?\s*",
        r"(?:^|\n)\s*(?:WARNING\s+)?SIGNS?\s+TO\s+(?:WATCH|LOOK)\s*:?\s*",
    ],
    "follow_up": [
        r"(?:^|\n)\s*FOLLOW[- ]?UP\s*:?\s*",
        r"(?:^|\n)\s*(?:F/U|FU)\s*:?\s*",
        r"(?:^|\n)\s*(?:OUTPATIENT\s+)?(?:APPOINTMENT|CLINIC)\s*:?\s*",
        r"(?:^|\n)\s*PLAN\s*:?\s*",
    ],
    "gp_action": [
        r"(?:^|\n)\s*(?:GP|GENERAL\s+PRACTICE?)\s+(?:ACTIONS?|TO\s+DO)\s*:?\s*",
        r"(?:^|\n)\s*ACTIONS?\s+(?:FOR|REQUIRED\s+(?:OF|BY))\s+(?:GP|GENERAL\s+PRACTICE?)\s*:?\s*",
        r"(?:^|\n)\s*(?:PRIMARY\s+CARE|GP)\s+(?:FOLLOW[- ]?UP|REVIEW)\s*:?\s*",
    ],
    "hospital_action": [
        r"(?:^|\n)\s*(?:HOSPITAL|SECONDARY\s+CARE)\s+(?:ACTIONS?|TO\s+DO)\s*:?\s*",
        r"(?:^|\n)\s*(?:OUTPATIENT|OPD)\s+(?:ACTIONS?|PLAN)\s*:?\s*",
        r"(?:^|\n)\s*(?:INPATIENT\s+)?(?:MANAGEMENT|TREATMENT)\s+PLAN\s*:?\s*",
    ],
    "referral": [
        r"(?:^|\n)\s*REFERRAL[S]?\s*:?\s*",
        r"(?:^|\n)\s*(?:REFERRED|REFER)\s+TO\s*:?\s*",
        r"(?:^|\n)\s*(?:SPECIALTY|SPECIALIST)\s+REFERRAL\s*:?\s*",
    ],
    "vital_sign": [
        r"(?:^|\n)\s*(?:VITAL\s+)?SIGNS?\s*:?\s*",
        r"(?:^|\n)\s*(?:OBSERVATIONS?|OBS)\s*:?\s*",
        r"(?:^|\n)\s*(?:NURSING\s+)?(?:OBSERVATIONS?|PARAMETERS?)\s*:?\s*",
    ],
    "clinical_score": [
        r"(?:^|\n)\s*(?:CLINICAL\s+)?SCORE[S]?\s*:?\s*",
        r"(?:^|\n)\s*(?:ASSESSMENT\s+)?SCORE[S]?\s*:?\s*",
        r"(?:^|\n)\s*(?:NEWS|MEWS|GCS|CURB-?65|Wells)\s*:?\s*",
    ],
}


# Category-specific keyword patterns
CATEGORY_KEYWORDS: Dict[EntityCategory, Dict[str, Any]] = {
    EntityCategory.DIAGNOSIS: {
        "patterns": [
            r"\b(?:diagnosed?\s+(?:with|as)|diagnosis\s+(?:of|is|was))\s+([^,.\n]+)",
            r"\b(?:confirmed|established|primary|secondary)\s+(?:diagnosis\s+(?:of\s+)?)?([^,.\n]+)",
            r"\b(?:impression|assessment)\s*:\s*([^,.\n]+)",
        ],
        "suffixes": [
            "syndrome", "disease", "disorder", "itis", "osis", "emia", "uria",
            "pathy", "plasia", "trophy", "ectomy", "cancer", "carcinoma",
            "melanoma", "lymphoma", "sarcoma", "failure", "insufficiency",
        ],
        "terms": {
            "myocardial infarction", "heart failure", "atrial fibrillation",
            "stroke", "tia", "transient ischaemic attack", "pneumonia",
            "copd", "asthma", "diabetes", "hypertension", "hypotension",
            "sepsis", "cellulitis", "uti", "urinary tract infection",
            "aki", "acute kidney injury", "ckd", "chronic kidney disease",
            "dvt", "deep vein thrombosis", "pe", "pulmonary embolism",
            "gord", "gerd", "ibs", "crohn", "ulcerative colitis",
            "epilepsy", "dementia", "alzheimer", "parkinson",
            "depression", "anxiety", "bipolar", "schizophrenia",
            "fracture", "osteoarthritis", "rheumatoid arthritis",
            "anaemia", "anemia", "leukaemia", "leukemia",
        },
    },
    EntityCategory.SYMPTOM: {
        "patterns": [
            r"\b(?:complain(?:s|ed|ing)?\s+of|c/o|presents?\s+with)\s+([^,.\n]+)",
            r"\b(?:reports?|describes?|experiencing)\s+([^,.\n]+)",
            r"\b(?:history\s+of)\s+([^,.\n]+?)(?:\s+for\s+\d)",
        ],
        "terms": {
            "pain", "ache", "discomfort", "tenderness", "soreness",
            "headache", "migraine", "chest pain", "abdominal pain", "back pain",
            "nausea", "vomiting", "diarrhoea", "diarrhea", "constipation",
            "dyspnoea", "dyspnea", "breathlessness", "shortness of breath",
            "cough", "wheeze", "sputum", "haemoptysis", "hemoptysis",
            "palpitations", "dizziness", "vertigo", "syncope", "collapse",
            "fatigue", "lethargy", "malaise", "weakness", "tired",
            "fever", "rigors", "chills", "night sweats",
            "weight loss", "weight gain", "appetite loss", "anorexia",
            "insomnia", "sleep disturbance", "confusion", "memory loss",
            "numbness", "tingling", "paraesthesia", "paresthesia",
            "swelling", "oedema", "edema", "rash", "itch", "pruritus",
            "blurred vision", "diplopia", "hearing loss", "tinnitus",
            "dysuria", "frequency", "urgency", "haematuria", "hematuria",
            "dysphagia", "odynophagia", "heartburn", "reflux",
            "claudication", "cramps", "spasms", "tremor",
        },
        "modifiers": [
            "acute", "chronic", "intermittent", "constant", "severe",
            "mild", "moderate", "worsening", "improving", "sudden",
        ],
    },
    EntityCategory.SIGN: {
        "patterns": [
            r"\b(?:on\s+examination|o/e|examination\s+(?:reveals?|shows?))\s*:?\s*([^,.\n]+)",
            r"\b(?:found\s+to\s+have|noted|observed)\s+([^,.\n]+)",
        ],
        "terms": {
            "tenderness", "guarding", "rigidity", "rebound",
            "hepatomegaly", "splenomegaly", "lymphadenopathy",
            "crepitations", "crackles", "wheeze", "rhonchi", "stridor",
            "murmur", "gallop", "rub", "thrill", "heave",
            "jvp", "jugular venous pressure", "peripheral oedema",
            "cyanosis", "pallor", "jaundice", "clubbing",
            "asterixis", "tremor", "nystagmus", "papilloedema",
            "focal neurology", "weakness", "sensory loss",
            "brudzinski", "kernig", "babinski", "romberg",
            "murphy", "mcburney", "rovsing", "psoas",
        },
        "anatomy_prefix": [
            "abdominal", "chest", "cardiac", "respiratory", "neurological",
            "musculoskeletal", "dermatological", "head", "neck", "limb",
        ],
    },
    EntityCategory.INVESTIGATION: {
        "patterns": [
            r"\b((?:blood|urine|stool|csf)\s+(?:test|culture|sample)s?)\b",
            r"\b((?:ct|mri|x-?ray|ultrasound|echo|ecg|ekg|eeg)\s*(?:scan|study)?)\b",
            r"\b(fbc|u&e|lft|tft|crp|esr|inr|abg|vbg|bnp|troponin)\b",
            r"\b((?:blood|serum|plasma)\s+\w+\s+(?:level|concentration))\b",
        ],
        "terms": {
            "fbc", "full blood count", "cbc", "complete blood count",
            "u&e", "urea and electrolytes", "renal function",
            "lft", "liver function", "lfts",
            "tft", "thyroid function", "tfts",
            "hba1c", "glucose", "blood sugar", "fasting glucose",
            "crp", "c-reactive protein", "esr", "sed rate",
            "inr", "pt", "aptt", "coagulation", "clotting",
            "troponin", "bnp", "nt-probnp", "cardiac enzymes",
            "abg", "arterial blood gas", "vbg", "venous blood gas",
            "blood cultures", "urine culture", "msu", "mssu",
            "chest x-ray", "cxr", "abdominal x-ray", "axr",
            "ct scan", "ct head", "ct abdomen", "ct chest", "ctpa",
            "mri", "mri brain", "mri spine", "mri knee",
            "ultrasound", "uss", "abdominal ultrasound", "renal ultrasound",
            "echocardiogram", "echo", "tte", "toe",
            "ecg", "ekg", "electrocardiogram", "12-lead ecg",
            "eeg", "electroencephalogram",
            "endoscopy", "gastroscopy", "egd", "colonoscopy",
            "bronchoscopy", "cystoscopy", "sigmoidoscopy",
            "biopsy", "histology", "cytology", "fna",
            "lumbar puncture", "lp", "csf analysis",
            "spirometry", "lung function", "pfts",
            "24-hour tape", "holter", "ambulatory ecg",
            "angiography", "angiogram", "coronary angiogram",
            "bone scan", "dexa", "bone density",
        },
    },
    EntityCategory.PROCEDURE: {
        "patterns": [
            r"\b(?:underwent|performed|had)\s+(?:a\s+)?([^,.\n]+(?:ectomy|otomy|oscopy|plasty|pexy|rrhaphy))",
            r"\b(?:procedure|operation|surgery)\s*:\s*([^,.\n]+)",
        ],
        "terms": {
            "appendicectomy", "appendectomy", "cholecystectomy",
            "colectomy", "hemicolectomy", "gastrectomy",
            "nephrectomy", "cystectomy", "prostatectomy",
            "hysterectomy", "oophorectomy", "mastectomy",
            "thyroidectomy", "parathyroidectomy",
            "laminectomy", "discectomy", "spinal fusion",
            "knee replacement", "hip replacement", "arthroplasty",
            "arthroscopy", "acl reconstruction",
            "cabg", "coronary artery bypass", "bypass surgery",
            "pci", "angioplasty", "stent", "stenting",
            "pacemaker", "icd", "defibrillator implant",
            "ablation", "cardioversion", "defibrillation",
            "intubation", "ventilation", "tracheostomy",
            "chest drain", "thoracentesis", "paracentesis",
            "dialysis", "haemodialysis", "hemodialysis", "pd",
            "transfusion", "blood transfusion",
            "biopsy", "excision", "resection", "debridement",
            "suturing", "wound closure", "skin graft",
            "reduction", "fixation", "orif", "plating",
            "catheterisation", "catheterization", "catheter insertion",
            "ng tube", "peg insertion", "feeding tube",
            "lumbar puncture", "joint aspiration", "injection",
        },
        "suffixes": [
            "ectomy", "otomy", "ostomy", "oscopy", "plasty",
            "pexy", "rrhaphy", "centesis", "tripsy",
        ],
    },
    EntityCategory.MEDICATION: {
        "patterns": [
            r"\b(\w+)\s+(\d+(?:\.\d+)?)\s*(mg|mcg|g|ml|units?|iu)\b",
            r"\b(\w+)\s+(od|bd|tds|qds|prn|mane|nocte|stat)\b",
        ],
        "terms": {
            "paracetamol", "acetaminophen", "ibuprofen", "naproxen",
            "aspirin", "codeine", "tramadol", "morphine", "oxycodone",
            "amoxicillin", "co-amoxiclav", "flucloxacillin", "penicillin",
            "clarithromycin", "azithromycin", "doxycycline", "metronidazole",
            "ciprofloxacin", "trimethoprim", "nitrofurantoin",
            "omeprazole", "lansoprazole", "pantoprazole", "ranitidine",
            "metformin", "gliclazide", "insulin", "sitagliptin",
            "atorvastatin", "simvastatin", "rosuvastatin", "pravastatin",
            "amlodipine", "ramipril", "lisinopril", "enalapril",
            "bisoprolol", "atenolol", "metoprolol", "carvedilol",
            "furosemide", "bendroflumethiazide", "spironolactone",
            "warfarin", "apixaban", "rivaroxaban", "edoxaban", "dabigatran",
            "clopidogrel", "ticagrelor", "prasugrel",
            "prednisolone", "hydrocortisone", "dexamethasone",
            "salbutamol", "ipratropium", "tiotropium", "salmeterol",
            "beclometasone", "fluticasone", "budesonide",
            "sertraline", "citalopram", "fluoxetine", "mirtazapine",
            "amitriptyline", "gabapentin", "pregabalin",
            "diazepam", "lorazepam", "zopiclone", "temazepam",
            "levothyroxine", "carbimazole", "propylthiouracil",
            "methotrexate", "azathioprine", "hydroxychloroquine",
            "allopurinol", "colchicine", "febuxostat",
            "lactulose", "senna", "macrogol", "movicol", "laxido",
            "cyclizine", "ondansetron", "metoclopramide", "domperidone",
            "enoxaparin", "dalteparin", "tinzaparin", "heparin",
        },
        "dosage_forms": [
            "tablet", "capsule", "syrup", "solution", "suspension",
            "injection", "infusion", "patch", "cream", "ointment",
            "inhaler", "nebuliser", "nebulizer", "drops", "spray",
            "suppository", "pessary", "enema",
        ],
    },
    EntityCategory.ALLERGY: {
        "patterns": [
            r"\b(?:allerg(?:y|ies|ic)\s+to)\s+([^,.\n]+)",
            r"\b(?:allergies?)\s*:\s*([^,.\n]+)",
            r"\b(nkda|nka|no\s+known\s+(?:drug\s+)?allerg(?:y|ies))\b",
        ],
        "terms": {
            "penicillin", "amoxicillin", "cephalosporin",
            "sulfa", "sulfonamide", "trimethoprim",
            "nsaid", "aspirin", "ibuprofen",
            "codeine", "morphine", "opioid",
            "latex", "plaster", "adhesive",
            "contrast", "iodine", "gadolinium",
            "egg", "peanut", "tree nut", "shellfish", "fish",
            "wheat", "gluten", "dairy", "lactose", "soya",
            "bee", "wasp", "insect",
            "nkda", "nka", "no known allergies",
        },
        "reaction_types": [
            "anaphylaxis", "rash", "urticaria", "angioedema",
            "bronchospasm", "gi upset", "nausea", "vomiting",
        ],
    },
    EntityCategory.SOCIAL_HISTORY: {
        "patterns": [
            r"\b(?:smok(?:es?|ing|er)|tobacco)\s*:?\s*([^,.\n]+)",
            r"\b(?:alcohol|etoh|drinking)\s*:?\s*([^,.\n]+)",
            r"\b(?:occupation|works?\s+as|employed\s+as)\s*:?\s*([^,.\n]+)",
            r"\b(?:lives?\s+(?:with|alone|independently))\s*([^,.\n]*)",
        ],
        "terms": {
            "smoker", "non-smoker", "ex-smoker", "never smoked",
            "pack years", "cigarettes", "tobacco", "vaping",
            "alcohol", "units", "teetotal", "social drinker",
            "recreational drugs", "cannabis", "cocaine", "ivdu",
            "married", "single", "divorced", "widowed", "partner",
            "lives alone", "lives with family", "care home", "nursing home",
            "independent", "housebound", "mobility aid", "wheelchair",
            "carer", "package of care", "social services",
            "employed", "unemployed", "retired", "student",
        },
    },
    EntityCategory.PAST_MEDICAL_HISTORY: {
        "patterns": [
            r"\b(?:past\s+(?:medical\s+)?history\s+(?:of|includes?))\s+([^,.\n]+)",
            r"\b(?:pmh|background)\s*:\s*([^,.\n]+)",
            r"\b(?:known|history\s+of)\s+(\w+(?:\s+\w+){0,3})\b",
        ],
        "context_markers": [
            "previously", "known", "background", "history of",
            "diagnosed in", "since", "longstanding",
        ],
    },
    EntityCategory.FAMILY_HISTORY: {
        "patterns": [
            r"\b(?:family\s+history\s+of)\s+([^,.\n]+)",
            r"\b(?:mother|father|brother|sister|parent|sibling)\s+(?:had|has|with|died\s+of)\s+([^,.\n]+)",
            r"\b(?:fhx?)\s*:\s*([^,.\n]+)",
        ],
        "relatives": [
            "mother", "father", "parent", "brother", "sister", "sibling",
            "grandmother", "grandfather", "grandparent", "aunt", "uncle",
            "son", "daughter", "child", "cousin",
        ],
    },
    EntityCategory.DISCHARGE_ADVICE: {
        "patterns": [
            r"\b(?:advised?\s+to)\s+([^,.\n]+)",
            r"\b(?:should|must|need\s+to)\s+([^,.\n]+)",
            r"\b(?:return\s+if|seek\s+(?:medical\s+)?(?:help|attention|advice)\s+if)\s+([^,.\n]+)",
        ],
        "terms": {
            "rest", "elevate", "ice", "compress",
            "return if", "seek help if", "call 999",
            "paracetamol for pain", "adequate fluid",
            "wound care", "dressing change", "keep dry",
            "avoid driving", "avoid alcohol", "avoid heavy lifting",
            "gradually increase activity", "light duties",
            "sick note", "fit note", "time off work",
        },
    },
    EntityCategory.FOLLOW_UP_PLAN: {
        "patterns": [
            r"\b(?:follow[- ]?up|f/u)\s+(?:in|with|at)\s+([^,.\n]+)",
            r"\b(?:review|see)\s+(?:in|by)\s+([^,.\n]+)",
            r"\b(?:appointment|appt)\s+(?:in|with|for)\s+([^,.\n]+)",
            r"\b(?:clinic)\s+(?:in|appointment)\s+([^,.\n]+)",
        ],
        "timeframes": [
            "days", "weeks", "months", "week", "month",
            "1 week", "2 weeks", "6 weeks", "3 months", "6 months",
        ],
        "terms": {
            "follow-up", "follow up", "review", "appointment",
            "outpatient", "clinic", "consultant", "specialist",
            "repeat bloods", "check", "monitor",
        },
    },
    EntityCategory.GP_ACTION: {
        "patterns": [
            r"\b(?:gp\s+to)\s+([^,.\n]+)",
            r"\b(?:please|kindly)\s+(?:arrange|organise|check|review|monitor)\s+([^,.\n]+)",
            r"\b(?:for\s+gp)\s*:\s*([^,.\n]+)",
        ],
        "action_verbs": [
            "prescribe", "continue", "stop", "review", "monitor",
            "check", "arrange", "refer", "chase", "repeat",
            "increase", "decrease", "titrate", "adjust",
        ],
        "terms": {
            "continue medication", "stop medication",
            "repeat bloods", "check blood pressure",
            "monitor renal function", "titrate dose",
            "review in", "follow up", "chase results",
            "refer to", "onward referral",
        },
    },
    EntityCategory.HOSPITAL_ACTION: {
        "patterns": [
            r"\b(?:hospital|we\s+will|(?:specialty|consultant)\s+to)\s+([^,.\n]+)",
            r"\b(?:outpatient|opd)\s+(?:appointment|follow[- ]?up)\s+([^,.\n]+)",
        ],
        "terms": {
            "outpatient appointment", "clinic follow-up",
            "repeat imaging", "surveillance scan",
            "mdt discussion", "mdt review",
            "pending biopsy", "await histology",
            "further investigation", "admit if",
        },
    },
    EntityCategory.REFERRAL: {
        "patterns": [
            r"\b(?:referr?(?:ed|al)\s+to)\s+([^,.\n]+)",
            r"\b(?:refer\s+to)\s+([^,.\n]+)",
            r"\b(?:for\s+(?:urgent\s+)?(?:\d+-?week)?\s*referral\s+to)\s+([^,.\n]+)",
        ],
        "specialties": [
            "cardiology", "respiratory", "gastroenterology", "neurology",
            "nephrology", "endocrinology", "rheumatology", "dermatology",
            "haematology", "oncology", "urology", "gynaecology",
            "orthopaedics", "ent", "ophthalmology", "psychiatry",
            "geriatrics", "paediatrics", "surgery", "plastics",
            "physiotherapy", "occupational therapy", "dietitian",
            "speech therapy", "palliative care", "pain clinic",
        ],
        "urgency": [
            "urgent", "2-week wait", "2ww", "routine", "soon",
            "emergency", "immediate", "priority",
        ],
    },
    EntityCategory.VITAL_SIGN: {
        "patterns": [
            r"\b(?:bp|blood\s+pressure)\s*:?\s*(\d{2,3}/\d{2,3})\s*(?:mmhg)?",
            r"\b(?:hr|heart\s+rate|pulse)\s*:?\s*(\d{2,3})\s*(?:bpm|/min)?",
            r"\b(?:rr|resp(?:iratory)?\s+rate)\s*:?\s*(\d{1,2})\s*(?:/min)?",
            r"\b(?:spo2|sats?|o2\s+sats?)\s*:?\s*(\d{2,3})\s*%?",
            r"\b(?:temp(?:erature)?)\s*:?\s*(\d{2}(?:\.\d)?)\s*(?:°?c|celsius)?",
            r"\b(?:gcs)\s*:?\s*(\d{1,2}(?:/15)?)",
        ],
        "terms": {
            "blood pressure", "bp", "systolic", "diastolic",
            "heart rate", "hr", "pulse", "bpm",
            "respiratory rate", "rr", "breaths per minute",
            "oxygen saturation", "spo2", "sats", "o2 sats",
            "temperature", "temp", "pyrexia", "afebrile", "febrile",
            "gcs", "glasgow coma scale", "avpu",
            "capillary refill", "crt",
            "weight", "height", "bmi", "body mass index",
        },
        "ranges": {
            "bp_systolic": (90, 140),
            "bp_diastolic": (60, 90),
            "hr": (60, 100),
            "rr": (12, 20),
            "spo2": (94, 100),
            "temp": (36.0, 37.5),
            "gcs": (15, 15),
        },
    },
    EntityCategory.CLINICAL_SCORE: {
        "patterns": [
            r"\b(news(?:2)?)\s*(?:score)?\s*:?\s*(\d{1,2})",
            r"\b(mews)\s*(?:score)?\s*:?\s*(\d{1,2})",
            r"\b(gcs)\s*:?\s*(\d{1,2}(?:/15)?)",
            r"\b(curb-?65)\s*(?:score)?\s*:?\s*(\d)",
            r"\b(wells)\s*(?:score)?\s*:?\s*(\d(?:\.\d)?)",
            r"\b(cha2ds2-vasc)\s*(?:score)?\s*:?\s*(\d)",
            r"\b(has-?bled)\s*(?:score)?\s*:?\s*(\d)",
            r"\b(sofa)\s*(?:score)?\s*:?\s*(\d{1,2})",
            r"\b(qsofa)\s*(?:score)?\s*:?\s*(\d)",
            r"\b(apache)\s*(?:ii|2)?\s*(?:score)?\s*:?\s*(\d{1,2})",
            r"\b(rockall)\s*(?:score)?\s*:?\s*(\d{1,2})",
            r"\b(blatchford)\s*(?:score)?\s*:?\s*(\d{1,2})",
            r"\b(child-?pugh)\s*(?:score|class)?\s*:?\s*([abc]|\d{1,2})",
            r"\b(meld)\s*(?:score)?\s*:?\s*(\d{1,2})",
            r"\b(mmse)\s*(?:score)?\s*:?\s*(\d{1,2}(?:/30)?)",
            r"\b(moca)\s*(?:score)?\s*:?\s*(\d{1,2}(?:/30)?)",
            r"\b(phq-?9)\s*(?:score)?\s*:?\s*(\d{1,2})",
            r"\b(gad-?7)\s*(?:score)?\s*:?\s*(\d{1,2})",
        ],
        "scores": {
            "news", "news2", "mews", "gcs",
            "curb-65", "curb65", "wells", "perc",
            "cha2ds2-vasc", "chads2", "has-bled", "hasbled",
            "sofa", "qsofa", "apache", "apache ii",
            "rockall", "blatchford", "child-pugh", "meld",
            "mmse", "moca", "ace-iii", "ami",
            "phq-9", "phq9", "gad-7", "gad7",
            "audit", "cage", "fast",
            "frailty", "clinical frailty scale", "cfs",
            "waterlow", "must", "malnutrition",
            "barthel", "katz", "adl",
        },
    },
}


class MedicalNER:
    """
    Medical Named Entity Recognition engine.

    Extracts entities into 17 distinct categories with no overlap.
    Uses section context, linguistic patterns, and priority rules.
    """

    def __init__(self):
        self._compile_patterns()
        self._build_term_index()

    def _compile_patterns(self) -> None:
        """Compile all regex patterns for efficiency."""
        self.section_regex = {}
        for section, patterns in SECTION_PATTERNS.items():
            self.section_regex[section] = [
                re.compile(p, re.IGNORECASE | re.MULTILINE)
                for p in patterns
            ]

        self.category_regex = {}
        for category, config in CATEGORY_KEYWORDS.items():
            if "patterns" in config:
                self.category_regex[category] = [
                    re.compile(p, re.IGNORECASE)
                    for p in config["patterns"]
                ]

    def _build_term_index(self) -> None:
        """Build reverse index: term -> category for quick lookup."""
        self.term_to_category: Dict[str, EntityCategory] = {}

        # Priority order for conflict resolution (higher index = higher priority)
        priority_order = [
            EntityCategory.SOCIAL_HISTORY,
            EntityCategory.FAMILY_HISTORY,
            EntityCategory.PAST_MEDICAL_HISTORY,
            EntityCategory.DISCHARGE_ADVICE,
            EntityCategory.HOSPITAL_ACTION,
            EntityCategory.GP_ACTION,
            EntityCategory.FOLLOW_UP_PLAN,
            EntityCategory.REFERRAL,
            EntityCategory.CLINICAL_SCORE,
            EntityCategory.VITAL_SIGN,
            EntityCategory.ALLERGY,
            EntityCategory.SYMPTOM,
            EntityCategory.SIGN,
            EntityCategory.INVESTIGATION,
            EntityCategory.PROCEDURE,
            EntityCategory.MEDICATION,
            EntityCategory.DIAGNOSIS,
        ]

        # Build index with priority (later entries override earlier)
        for category in priority_order:
            config = CATEGORY_KEYWORDS.get(category, {})
            terms = config.get("terms", set())
            for term in terms:
                self.term_to_category[term.lower()] = category

    def extract(self, text: str) -> NERResult:
        """
        Extract all medical entities from text.

        Args:
            text: Clinical document text (ideally normalized)

        Returns:
            NERResult with entities categorized into 17 types
        """
        # Step 1: Detect document sections
        sections = self._detect_sections(text)

        # Step 2: Extract entities by category
        all_entities: List[MedicalEntity] = []

        # Extract in specific order to handle overlaps correctly
        extraction_order = [
            (EntityCategory.VITAL_SIGN, self._extract_vital_signs),
            (EntityCategory.CLINICAL_SCORE, self._extract_clinical_scores),
            (EntityCategory.ALLERGY, self._extract_allergies),
            (EntityCategory.MEDICATION, self._extract_medications),
            (EntityCategory.INVESTIGATION, self._extract_investigations),
            (EntityCategory.PROCEDURE, self._extract_procedures),
            (EntityCategory.REFERRAL, self._extract_referrals),
            (EntityCategory.GP_ACTION, self._extract_gp_actions),
            (EntityCategory.HOSPITAL_ACTION, self._extract_hospital_actions),
            (EntityCategory.FOLLOW_UP_PLAN, self._extract_follow_up),
            (EntityCategory.DISCHARGE_ADVICE, self._extract_discharge_advice),
            (EntityCategory.FAMILY_HISTORY, self._extract_family_history),
            (EntityCategory.SOCIAL_HISTORY, self._extract_social_history),
            (EntityCategory.PAST_MEDICAL_HISTORY, self._extract_pmh),
            (EntityCategory.SIGN, self._extract_signs),
            (EntityCategory.SYMPTOM, self._extract_symptoms),
            (EntityCategory.DIAGNOSIS, self._extract_diagnoses),
        ]

        # Track which text spans have been assigned
        assigned_spans: Set[Tuple[int, int]] = set()

        for category, extractor in extraction_order:
            entities = extractor(text, sections, assigned_spans)
            for entity in entities:
                # Check for overlap
                span = (entity.start_pos, entity.end_pos)
                if not self._overlaps_assigned(span, assigned_spans):
                    all_entities.append(entity)
                    assigned_spans.add(span)

        # Step 3: Organize by category
        by_category: Dict[str, List[MedicalEntity]] = defaultdict(list)
        for entity in all_entities:
            by_category[entity.category.value].append(entity)

        # Step 4: Calculate stats
        stats = {cat.value: len(by_category[cat.value]) for cat in EntityCategory}
        stats["total"] = len(all_entities)

        return NERResult(
            entities=all_entities,
            by_category=dict(by_category),
            extraction_stats=stats,
        )

    def _overlaps_assigned(
        self, span: Tuple[int, int], assigned: Set[Tuple[int, int]]
    ) -> bool:
        """Check if span overlaps with any assigned span."""
        start, end = span
        for a_start, a_end in assigned:
            if start < a_end and end > a_start:
                return True
        return False

    def _detect_sections(self, text: str) -> List[Dict]:
        """Detect document sections and their boundaries."""
        sections = []

        for section_type, patterns in self.section_regex.items():
            for pattern in patterns:
                for match in pattern.finditer(text):
                    sections.append({
                        "type": section_type,
                        "start": match.end(),
                        "header_start": match.start(),
                        "header_text": match.group(0).strip(),
                    })

        # Sort by position
        sections.sort(key=lambda x: x["start"])

        # Calculate end positions (next section start or end of text)
        for i, section in enumerate(sections):
            if i + 1 < len(sections):
                section["end"] = sections[i + 1]["header_start"]
            else:
                section["end"] = len(text)

        return sections

    def _get_section_at(self, pos: int, sections: List[Dict]) -> Optional[str]:
        """Get section type at a given position."""
        for section in sections:
            if section["start"] <= pos < section["end"]:
                return section["type"]
        return None

    def _extract_vital_signs(
        self, text: str, sections: List[Dict], assigned: Set[Tuple[int, int]]
    ) -> List[MedicalEntity]:
        """Extract vital signs with values."""
        entities = []
        config = CATEGORY_KEYWORDS[EntityCategory.VITAL_SIGN]

        for pattern in self.category_regex.get(EntityCategory.VITAL_SIGN, []):
            for match in pattern.finditer(text):
                value = match.group(1)
                entities.append(MedicalEntity(
                    text=match.group(0).strip(),
                    category=EntityCategory.VITAL_SIGN,
                    confidence=0.95,
                    start_pos=match.start(),
                    end_pos=match.end(),
                    section=self._get_section_at(match.start(), sections),
                    attributes={"value": value},
                    evidence="Pattern match on vital sign format",
                ))

        return entities

    def _extract_clinical_scores(
        self, text: str, sections: List[Dict], assigned: Set[Tuple[int, int]]
    ) -> List[MedicalEntity]:
        """Extract clinical scoring systems."""
        entities = []

        for pattern in self.category_regex.get(EntityCategory.CLINICAL_SCORE, []):
            for match in pattern.finditer(text):
                score_name = match.group(1).upper()
                score_value = match.group(2)
                entities.append(MedicalEntity(
                    text=match.group(0).strip(),
                    category=EntityCategory.CLINICAL_SCORE,
                    confidence=0.95,
                    start_pos=match.start(),
                    end_pos=match.end(),
                    section=self._get_section_at(match.start(), sections),
                    attributes={"score_name": score_name, "value": score_value},
                    evidence="Pattern match on clinical score",
                ))

        return entities

    def _extract_allergies(
        self, text: str, sections: List[Dict], assigned: Set[Tuple[int, int]]
    ) -> List[MedicalEntity]:
        """Extract allergies and adverse reactions."""
        entities = []
        config = CATEGORY_KEYWORDS[EntityCategory.ALLERGY]

        for pattern in self.category_regex.get(EntityCategory.ALLERGY, []):
            for match in pattern.finditer(text):
                allergen = match.group(1).strip()
                if allergen.lower() in ("nkda", "nka"):
                    allergen = "No known drug allergies"

                entities.append(MedicalEntity(
                    text=allergen,
                    category=EntityCategory.ALLERGY,
                    confidence=0.90,
                    start_pos=match.start(),
                    end_pos=match.end(),
                    section=self._get_section_at(match.start(), sections),
                    evidence="Allergy pattern match",
                ))

        # Also extract from allergy sections
        for section in sections:
            if section["type"] == "allergy":
                section_text = text[section["start"]:section["end"]]
                for term in config.get("terms", []):
                    term_pattern = re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE)
                    for match in term_pattern.finditer(section_text):
                        abs_start = section["start"] + match.start()
                        abs_end = section["start"] + match.end()
                        if not self._overlaps_assigned((abs_start, abs_end), assigned):
                            entities.append(MedicalEntity(
                                text=match.group(0),
                                category=EntityCategory.ALLERGY,
                                confidence=0.85,
                                start_pos=abs_start,
                                end_pos=abs_end,
                                section="allergy",
                                evidence="Term found in allergy section",
                            ))

        return entities

    def _extract_medications(
        self, text: str, sections: List[Dict], assigned: Set[Tuple[int, int]]
    ) -> List[MedicalEntity]:
        """Extract medications with dosages."""
        entities = []
        config = CATEGORY_KEYWORDS[EntityCategory.MEDICATION]

        # Pattern: drug name + dose + unit
        dose_pattern = re.compile(
            r"\b([A-Za-z][\w-]+)\s+(\d+(?:\.\d+)?)\s*(mg|mcg|g|ml|units?|iu)\b",
            re.IGNORECASE
        )
        for match in dose_pattern.finditer(text):
            drug = match.group(1)
            dose = match.group(2)
            unit = match.group(3)

            # Validate it's a known medication or in medication section
            section = self._get_section_at(match.start(), sections)
            is_med_section = section == "medication"
            is_known_drug = drug.lower() in config.get("terms", set())

            if is_med_section or is_known_drug:
                entities.append(MedicalEntity(
                    text=match.group(0).strip(),
                    category=EntityCategory.MEDICATION,
                    confidence=0.90 if is_known_drug else 0.75,
                    start_pos=match.start(),
                    end_pos=match.end(),
                    section=section,
                    normalized_text=drug.lower(),
                    attributes={"drug": drug, "dose": dose, "unit": unit},
                    evidence="Medication pattern with dosage",
                ))

        # Pattern: drug name + frequency
        freq_pattern = re.compile(
            r"\b([A-Za-z][\w-]+)\s+(od|bd|tds|qds|prn|mane|nocte|stat|once\s+daily|twice\s+daily)\b",
            re.IGNORECASE
        )
        for match in freq_pattern.finditer(text):
            drug = match.group(1)
            freq = match.group(2)

            section = self._get_section_at(match.start(), sections)
            is_known_drug = drug.lower() in config.get("terms", set())

            if is_known_drug:
                span = (match.start(), match.end())
                if not self._overlaps_assigned(span, assigned):
                    entities.append(MedicalEntity(
                        text=match.group(0).strip(),
                        category=EntityCategory.MEDICATION,
                        confidence=0.85,
                        start_pos=match.start(),
                        end_pos=match.end(),
                        section=section,
                        attributes={"drug": drug, "frequency": freq},
                        evidence="Medication with frequency",
                    ))

        # Extract known medications by name
        for term in config.get("terms", set()):
            term_pattern = re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE)
            for match in term_pattern.finditer(text):
                span = (match.start(), match.end())
                if not self._overlaps_assigned(span, assigned):
                    section = self._get_section_at(match.start(), sections)
                    # Higher confidence if in medication section
                    conf = 0.85 if section == "medication" else 0.70
                    entities.append(MedicalEntity(
                        text=match.group(0),
                        category=EntityCategory.MEDICATION,
                        confidence=conf,
                        start_pos=match.start(),
                        end_pos=match.end(),
                        section=section,
                        normalized_text=term,
                        evidence="Known medication term",
                    ))

        return entities

    def _extract_investigations(
        self, text: str, sections: List[Dict], assigned: Set[Tuple[int, int]]
    ) -> List[MedicalEntity]:
        """Extract investigations and test results."""
        entities = []
        config = CATEGORY_KEYWORDS[EntityCategory.INVESTIGATION]

        # Extract known investigation terms
        for term in config.get("terms", set()):
            term_pattern = re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE)
            for match in term_pattern.finditer(text):
                span = (match.start(), match.end())
                if not self._overlaps_assigned(span, assigned):
                    section = self._get_section_at(match.start(), sections)
                    conf = 0.90 if section == "investigation" else 0.75
                    entities.append(MedicalEntity(
                        text=match.group(0),
                        category=EntityCategory.INVESTIGATION,
                        confidence=conf,
                        start_pos=match.start(),
                        end_pos=match.end(),
                        section=section,
                        normalized_text=term,
                        evidence="Known investigation term",
                    ))

        # Extract lab values with results
        lab_pattern = re.compile(
            r"\b((?:Hb|WCC|Plt|Na|K|Cr|Ur|CRP|INR|Bili|ALT|ALP|GGT|Alb|eGFR|HbA1c|TSH|T4|Trop)\s*[:\s]\s*[\d.]+)",
            re.IGNORECASE
        )
        for match in lab_pattern.finditer(text):
            span = (match.start(), match.end())
            if not self._overlaps_assigned(span, assigned):
                entities.append(MedicalEntity(
                    text=match.group(0).strip(),
                    category=EntityCategory.INVESTIGATION,
                    confidence=0.90,
                    start_pos=match.start(),
                    end_pos=match.end(),
                    section=self._get_section_at(match.start(), sections),
                    evidence="Lab result pattern",
                ))

        return entities

    def _extract_procedures(
        self, text: str, sections: List[Dict], assigned: Set[Tuple[int, int]]
    ) -> List[MedicalEntity]:
        """Extract surgical and medical procedures."""
        entities = []
        config = CATEGORY_KEYWORDS[EntityCategory.PROCEDURE]

        # Extract by suffix patterns
        suffix_pattern = re.compile(
            r"\b\w+(?:ectomy|otomy|ostomy|oscopy|plasty|pexy|rrhaphy|centesis|tripsy)\b",
            re.IGNORECASE
        )
        for match in suffix_pattern.finditer(text):
            span = (match.start(), match.end())
            if not self._overlaps_assigned(span, assigned):
                entities.append(MedicalEntity(
                    text=match.group(0),
                    category=EntityCategory.PROCEDURE,
                    confidence=0.90,
                    start_pos=match.start(),
                    end_pos=match.end(),
                    section=self._get_section_at(match.start(), sections),
                    evidence="Procedure suffix pattern",
                ))

        # Extract known procedures
        for term in config.get("terms", set()):
            term_pattern = re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE)
            for match in term_pattern.finditer(text):
                span = (match.start(), match.end())
                if not self._overlaps_assigned(span, assigned):
                    section = self._get_section_at(match.start(), sections)
                    conf = 0.90 if section == "procedure" else 0.80
                    entities.append(MedicalEntity(
                        text=match.group(0),
                        category=EntityCategory.PROCEDURE,
                        confidence=conf,
                        start_pos=match.start(),
                        end_pos=match.end(),
                        section=section,
                        normalized_text=term,
                        evidence="Known procedure term",
                    ))

        return entities

    def _extract_referrals(
        self, text: str, sections: List[Dict], assigned: Set[Tuple[int, int]]
    ) -> List[MedicalEntity]:
        """Extract referrals to specialists/services."""
        entities = []
        config = CATEGORY_KEYWORDS[EntityCategory.REFERRAL]

        for pattern in self.category_regex.get(EntityCategory.REFERRAL, []):
            for match in pattern.finditer(text):
                referral_to = match.group(1).strip()
                entities.append(MedicalEntity(
                    text=match.group(0).strip(),
                    category=EntityCategory.REFERRAL,
                    confidence=0.90,
                    start_pos=match.start(),
                    end_pos=match.end(),
                    section=self._get_section_at(match.start(), sections),
                    attributes={"specialty": referral_to},
                    evidence="Referral pattern match",
                ))

        return entities

    def _extract_gp_actions(
        self, text: str, sections: List[Dict], assigned: Set[Tuple[int, int]]
    ) -> List[MedicalEntity]:
        """Extract actions required by GP."""
        entities = []

        for pattern in self.category_regex.get(EntityCategory.GP_ACTION, []):
            for match in pattern.finditer(text):
                action = match.group(1).strip()
                entities.append(MedicalEntity(
                    text=action,
                    category=EntityCategory.GP_ACTION,
                    confidence=0.90,
                    start_pos=match.start(),
                    end_pos=match.end(),
                    section=self._get_section_at(match.start(), sections),
                    evidence="GP action pattern",
                ))

        # Extract from GP action sections
        for section in sections:
            if section["type"] == "gp_action":
                section_text = text[section["start"]:section["end"]]
                # Split by bullet points or newlines
                items = re.split(r'(?:^|\n)\s*[-•*]\s*|(?:^|\n)\s*\d+[.)]\s*', section_text)
                pos = section["start"]
                for item in items:
                    item = item.strip()
                    if item and len(item) > 5:
                        entities.append(MedicalEntity(
                            text=item[:200],  # Cap length
                            category=EntityCategory.GP_ACTION,
                            confidence=0.85,
                            start_pos=pos,
                            end_pos=pos + len(item),
                            section="gp_action",
                            evidence="Item in GP action section",
                        ))
                    pos += len(item) + 1

        return entities

    def _extract_hospital_actions(
        self, text: str, sections: List[Dict], assigned: Set[Tuple[int, int]]
    ) -> List[MedicalEntity]:
        """Extract actions for hospital/secondary care."""
        entities = []

        for pattern in self.category_regex.get(EntityCategory.HOSPITAL_ACTION, []):
            for match in pattern.finditer(text):
                action = match.group(1).strip()
                entities.append(MedicalEntity(
                    text=action,
                    category=EntityCategory.HOSPITAL_ACTION,
                    confidence=0.85,
                    start_pos=match.start(),
                    end_pos=match.end(),
                    section=self._get_section_at(match.start(), sections),
                    evidence="Hospital action pattern",
                ))

        return entities

    def _extract_follow_up(
        self, text: str, sections: List[Dict], assigned: Set[Tuple[int, int]]
    ) -> List[MedicalEntity]:
        """Extract follow-up plans and appointments."""
        entities = []

        for pattern in self.category_regex.get(EntityCategory.FOLLOW_UP_PLAN, []):
            for match in pattern.finditer(text):
                plan = match.group(1).strip()
                entities.append(MedicalEntity(
                    text=match.group(0).strip(),
                    category=EntityCategory.FOLLOW_UP_PLAN,
                    confidence=0.90,
                    start_pos=match.start(),
                    end_pos=match.end(),
                    section=self._get_section_at(match.start(), sections),
                    attributes={"timeframe": plan},
                    evidence="Follow-up pattern match",
                ))

        return entities

    def _extract_discharge_advice(
        self, text: str, sections: List[Dict], assigned: Set[Tuple[int, int]]
    ) -> List[MedicalEntity]:
        """Extract discharge advice and patient instructions."""
        entities = []

        for pattern in self.category_regex.get(EntityCategory.DISCHARGE_ADVICE, []):
            for match in pattern.finditer(text):
                advice = match.group(1).strip()
                entities.append(MedicalEntity(
                    text=advice,
                    category=EntityCategory.DISCHARGE_ADVICE,
                    confidence=0.85,
                    start_pos=match.start(),
                    end_pos=match.end(),
                    section=self._get_section_at(match.start(), sections),
                    evidence="Discharge advice pattern",
                ))

        # Extract from advice sections
        for section in sections:
            if section["type"] == "discharge_advice":
                section_text = text[section["start"]:section["end"]]
                items = re.split(r'(?:^|\n)\s*[-•*]\s*|(?:^|\n)\s*\d+[.)]\s*', section_text)
                for item in items:
                    item = item.strip()
                    if item and len(item) > 5:
                        entities.append(MedicalEntity(
                            text=item[:200],
                            category=EntityCategory.DISCHARGE_ADVICE,
                            confidence=0.80,
                            start_pos=section["start"],
                            end_pos=section["end"],
                            section="discharge_advice",
                            evidence="Item in discharge advice section",
                        ))

        return entities

    def _extract_family_history(
        self, text: str, sections: List[Dict], assigned: Set[Tuple[int, int]]
    ) -> List[MedicalEntity]:
        """Extract family history items."""
        entities = []
        config = CATEGORY_KEYWORDS[EntityCategory.FAMILY_HISTORY]

        for pattern in self.category_regex.get(EntityCategory.FAMILY_HISTORY, []):
            for match in pattern.finditer(text):
                condition = match.group(1).strip()
                entities.append(MedicalEntity(
                    text=match.group(0).strip(),
                    category=EntityCategory.FAMILY_HISTORY,
                    confidence=0.90,
                    start_pos=match.start(),
                    end_pos=match.end(),
                    section=self._get_section_at(match.start(), sections),
                    attributes={"condition": condition},
                    evidence="Family history pattern",
                ))

        return entities

    def _extract_social_history(
        self, text: str, sections: List[Dict], assigned: Set[Tuple[int, int]]
    ) -> List[MedicalEntity]:
        """Extract social history items."""
        entities = []
        config = CATEGORY_KEYWORDS[EntityCategory.SOCIAL_HISTORY]

        for pattern in self.category_regex.get(EntityCategory.SOCIAL_HISTORY, []):
            for match in pattern.finditer(text):
                detail = match.group(1).strip() if match.lastindex else match.group(0).strip()
                entities.append(MedicalEntity(
                    text=match.group(0).strip(),
                    category=EntityCategory.SOCIAL_HISTORY,
                    confidence=0.85,
                    start_pos=match.start(),
                    end_pos=match.end(),
                    section=self._get_section_at(match.start(), sections),
                    evidence="Social history pattern",
                ))

        # Extract from social history sections
        for section in sections:
            if section["type"] == "social_history":
                section_text = text[section["start"]:section["end"]]
                for term in config.get("terms", set()):
                    term_pattern = re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE)
                    for match in term_pattern.finditer(section_text):
                        abs_start = section["start"] + match.start()
                        abs_end = section["start"] + match.end()
                        if not self._overlaps_assigned((abs_start, abs_end), assigned):
                            entities.append(MedicalEntity(
                                text=match.group(0),
                                category=EntityCategory.SOCIAL_HISTORY,
                                confidence=0.80,
                                start_pos=abs_start,
                                end_pos=abs_end,
                                section="social_history",
                                evidence="Term in social history section",
                            ))

        return entities

    def _extract_pmh(
        self, text: str, sections: List[Dict], assigned: Set[Tuple[int, int]]
    ) -> List[MedicalEntity]:
        """Extract past medical history items."""
        entities = []
        config = CATEGORY_KEYWORDS[EntityCategory.PAST_MEDICAL_HISTORY]

        for pattern in self.category_regex.get(EntityCategory.PAST_MEDICAL_HISTORY, []):
            for match in pattern.finditer(text):
                condition = match.group(1).strip()
                entities.append(MedicalEntity(
                    text=condition,
                    category=EntityCategory.PAST_MEDICAL_HISTORY,
                    confidence=0.85,
                    start_pos=match.start(),
                    end_pos=match.end(),
                    section=self._get_section_at(match.start(), sections),
                    evidence="PMH pattern match",
                ))

        # Extract conditions from PMH sections
        diagnosis_terms = CATEGORY_KEYWORDS[EntityCategory.DIAGNOSIS].get("terms", set())
        for section in sections:
            if section["type"] == "past_medical_history":
                section_text = text[section["start"]:section["end"]]
                for term in diagnosis_terms:
                    term_pattern = re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE)
                    for match in term_pattern.finditer(section_text):
                        abs_start = section["start"] + match.start()
                        abs_end = section["start"] + match.end()
                        if not self._overlaps_assigned((abs_start, abs_end), assigned):
                            entities.append(MedicalEntity(
                                text=match.group(0),
                                category=EntityCategory.PAST_MEDICAL_HISTORY,
                                confidence=0.85,
                                start_pos=abs_start,
                                end_pos=abs_end,
                                section="past_medical_history",
                                evidence="Condition in PMH section (not current diagnosis)",
                            ))

        return entities

    def _extract_signs(
        self, text: str, sections: List[Dict], assigned: Set[Tuple[int, int]]
    ) -> List[MedicalEntity]:
        """Extract clinical signs from examination."""
        entities = []
        config = CATEGORY_KEYWORDS[EntityCategory.SIGN]

        # Extract from examination sections
        for section in sections:
            if section["type"] == "sign":
                section_text = text[section["start"]:section["end"]]
                for term in config.get("terms", set()):
                    term_pattern = re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE)
                    for match in term_pattern.finditer(section_text):
                        abs_start = section["start"] + match.start()
                        abs_end = section["start"] + match.end()
                        if not self._overlaps_assigned((abs_start, abs_end), assigned):
                            entities.append(MedicalEntity(
                                text=match.group(0),
                                category=EntityCategory.SIGN,
                                confidence=0.85,
                                start_pos=abs_start,
                                end_pos=abs_end,
                                section="sign",
                                evidence="Sign found in examination section",
                            ))

        # Pattern-based extraction
        for pattern in self.category_regex.get(EntityCategory.SIGN, []):
            for match in pattern.finditer(text):
                finding = match.group(1).strip()
                span = (match.start(), match.end())
                if not self._overlaps_assigned(span, assigned):
                    entities.append(MedicalEntity(
                        text=finding,
                        category=EntityCategory.SIGN,
                        confidence=0.80,
                        start_pos=match.start(),
                        end_pos=match.end(),
                        section=self._get_section_at(match.start(), sections),
                        evidence="Sign pattern match",
                    ))

        return entities

    def _extract_symptoms(
        self, text: str, sections: List[Dict], assigned: Set[Tuple[int, int]]
    ) -> List[MedicalEntity]:
        """Extract patient-reported symptoms."""
        entities = []
        config = CATEGORY_KEYWORDS[EntityCategory.SYMPTOM]

        # Pattern-based extraction (complaints, reports, etc.)
        for pattern in self.category_regex.get(EntityCategory.SYMPTOM, []):
            for match in pattern.finditer(text):
                symptom = match.group(1).strip()
                span = (match.start(), match.end())
                if not self._overlaps_assigned(span, assigned):
                    entities.append(MedicalEntity(
                        text=symptom,
                        category=EntityCategory.SYMPTOM,
                        confidence=0.85,
                        start_pos=match.start(),
                        end_pos=match.end(),
                        section=self._get_section_at(match.start(), sections),
                        evidence="Symptom pattern match",
                    ))

        # Extract known symptoms
        for term in config.get("terms", set()):
            term_pattern = re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE)
            for match in term_pattern.finditer(text):
                span = (match.start(), match.end())
                if not self._overlaps_assigned(span, assigned):
                    section = self._get_section_at(match.start(), sections)
                    # Higher confidence if in symptom/complaint section
                    conf = 0.85 if section == "symptom" else 0.70
                    entities.append(MedicalEntity(
                        text=match.group(0),
                        category=EntityCategory.SYMPTOM,
                        confidence=conf,
                        start_pos=match.start(),
                        end_pos=match.end(),
                        section=section,
                        normalized_text=term,
                        evidence="Known symptom term",
                    ))

        return entities

    def _extract_diagnoses(
        self, text: str, sections: List[Dict], assigned: Set[Tuple[int, int]]
    ) -> List[MedicalEntity]:
        """Extract confirmed diagnoses (final catch-all for conditions)."""
        entities = []
        config = CATEGORY_KEYWORDS[EntityCategory.DIAGNOSIS]

        # Extract from diagnosis sections (highest confidence)
        for section in sections:
            if section["type"] == "diagnosis":
                section_text = text[section["start"]:section["end"]]

                # Extract known diagnosis terms
                for term in config.get("terms", set()):
                    term_pattern = re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE)
                    for match in term_pattern.finditer(section_text):
                        abs_start = section["start"] + match.start()
                        abs_end = section["start"] + match.end()
                        if not self._overlaps_assigned((abs_start, abs_end), assigned):
                            entities.append(MedicalEntity(
                                text=match.group(0),
                                category=EntityCategory.DIAGNOSIS,
                                confidence=0.95,
                                start_pos=abs_start,
                                end_pos=abs_end,
                                section="diagnosis",
                                normalized_text=term,
                                evidence="Diagnosis term in diagnosis section",
                            ))

                # Extract by suffix patterns in diagnosis section
                for suffix in config.get("suffixes", []):
                    suffix_pattern = re.compile(rf"\b\w*{suffix}\b", re.IGNORECASE)
                    for match in suffix_pattern.finditer(section_text):
                        abs_start = section["start"] + match.start()
                        abs_end = section["start"] + match.end()
                        if not self._overlaps_assigned((abs_start, abs_end), assigned):
                            entities.append(MedicalEntity(
                                text=match.group(0),
                                category=EntityCategory.DIAGNOSIS,
                                confidence=0.90,
                                start_pos=abs_start,
                                end_pos=abs_end,
                                section="diagnosis",
                                evidence="Diagnosis suffix in diagnosis section",
                            ))

        # Pattern-based diagnosis extraction (lower confidence outside sections)
        for pattern in self.category_regex.get(EntityCategory.DIAGNOSIS, []):
            for match in pattern.finditer(text):
                diagnosis = match.group(1).strip()
                span = (match.start(), match.end())
                if not self._overlaps_assigned(span, assigned):
                    entities.append(MedicalEntity(
                        text=diagnosis,
                        category=EntityCategory.DIAGNOSIS,
                        confidence=0.80,
                        start_pos=match.start(),
                        end_pos=match.end(),
                        section=self._get_section_at(match.start(), sections),
                        evidence="Diagnosis pattern match",
                    ))

        return entities


def extract_medical_entities(text: str) -> Dict[str, Any]:
    """
    Convenience function to extract all medical entities.

    Args:
        text: Clinical document text

    Returns:
        Dictionary with entities organized by category
    """
    ner = MedicalNER()
    result = ner.extract(text)
    return result.to_dict()


# Test
if __name__ == "__main__":
    test_text = """
    DISCHARGE SUMMARY

    Presenting Complaint:
    72-year-old male presenting with chest pain and shortness of breath for 2 days.
    Also reports nausea and dizziness.

    Past Medical History:
    - Hypertension
    - Type 2 diabetes mellitus
    - Previous MI 2018

    Family History:
    Father died of heart attack aged 65.

    Social History:
    Ex-smoker, 20 pack years. Alcohol: 10 units/week. Lives with wife, independent.

    Allergies: Penicillin (rash), NKDA otherwise

    Examination:
    BP: 145/92 mmHg, HR: 88 bpm, RR: 18, SpO2: 96% on air, Temp: 37.1
    Chest: bilateral crackles. Heart: regular, no murmurs.
    Abdomen: soft, non-tender.

    Investigations:
    ECG: sinus rhythm, no acute changes
    Troponin: 45 ng/L (raised)
    FBC: Hb 128, WCC 9.2, Plt 245
    U&E: Na 138, K 4.2, Cr 98, eGFR 65
    CXR: mild pulmonary oedema

    Diagnosis:
    1. NSTEMI
    2. Acute pulmonary oedema
    3. Hypertension - poorly controlled

    Procedure:
    Coronary angiogram performed - 70% LAD stenosis. PCI with drug-eluting stent.

    Medications on Discharge:
    - Aspirin 75mg OD
    - Clopidogrel 75mg OD
    - Atorvastatin 80mg ON
    - Bisoprolol 5mg OD
    - Ramipril 5mg OD
    - GTN spray PRN

    GP Actions:
    - Please check BP in 2 weeks
    - Repeat U&E in 1 week (new ramipril)
    - Continue dual antiplatelet therapy for 12 months

    Follow-up:
    - Cardiology clinic in 6 weeks
    - Cardiac rehabilitation referral

    Discharge Advice:
    - Avoid driving for 1 week
    - Return if chest pain recurs
    - Gradually increase activity

    Referral: Cardiac rehabilitation
    """

    ner = MedicalNER()
    result = ner.extract(test_text)

    print("=" * 70)
    print("MEDICAL NER EXTRACTION RESULTS")
    print("=" * 70)

    for category in EntityCategory:
        entities = result.by_category.get(category.value, [])
        if entities:
            print(f"\n{category.value.upper()} ({len(entities)}):")
            print("-" * 40)
            for e in entities:
                print(f"  • {e.text[:60]:<60} [{e.confidence:.0%}]")

    print("\n" + "=" * 70)
    print("EXTRACTION STATS:")
    print("=" * 70)
    for cat, count in sorted(result.extraction_stats.items()):
        if count > 0:
            print(f"  {cat:<25}: {count}")
