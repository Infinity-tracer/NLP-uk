"""
Medical OCR Text Normalizer

Preprocesses raw OCR output for clinical NLP pipelines:
- Corrects common OCR spelling errors using medical dictionary
- Normalizes punctuation, whitespace, and broken words
- Merges words split across lines
- Preserves section headings and bullet hierarchy
- Preserves clinical abbreviations
- Removes OCR artifacts
- Normalizes Unicode characters
"""

import re
import unicodedata
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field


@dataclass
class NormalizationResult:
    """Result of OCR normalization containing both raw and normalized text."""
    raw_text: str
    normalized_text: str
    corrections_made: List[Dict[str, str]] = field(default_factory=list)
    artifacts_removed: int = 0
    lines_merged: int = 0
    unicode_normalized: int = 0


# Common OCR misreadings in medical documents
OCR_CORRECTIONS: Dict[str, str] = {
    # Character substitution errors (l/I/1, 0/O, rn/m)
    "coIapse": "collapse",
    "coIIapse": "collapse",
    "col1apse": "collapse",
    "colIapse": "collapse",
    "faI1": "fall",
    "fa1l": "fall",
    "fal1": "fall",
    "waIk": "walk",
    "wa1k": "walk",
    "taIk": "talk",
    "ta1k": "talk",
    "paIn": "pain",
    "pa1n": "pain",
    "bIood": "blood",
    "b1ood": "blood",
    "bl00d": "blood",
    "cIinical": "clinical",
    "c1inical": "clinical",
    "clinicaI": "clinical",
    "medicaI": "medical",
    "med1cal": "medical",
    "rnedical": "medical",
    "rnedicine": "medicine",
    "medicaIly": "medically",
    "hospitaI": "hospital",
    "hosp1tal": "hospital",
    "hospita1": "hospital",
    "generaI": "general",
    "genera1": "general",
    "normaI": "normal",
    "norrnal": "normal",
    "abnormaI": "abnormal",
    "abnorrnal": "abnormal",
    "renai": "renal",
    "renaI": "renal",
    "urinarv": "urinary",
    "cardiaI": "cardiac",
    "card1ac": "cardiac",
    "surgicaI": "surgical",
    "surg1cal": "surgical",
    "neurologicaI": "neurological",
    "neuro1ogical": "neurological",
    "psychiatricaI": "psychiatric",
    "rnental": "mental",
    "mentaI": "mental",
    "physicaI": "physical",
    "phys1cal": "physical",
    "sociaI": "social",
    "soc1al": "social",
    "functionaI": "functional",
    "funct1onal": "functional",
    "emotionaI": "emotional",
    "emot1onal": "emotional",
    "behaviora1": "behavioral",
    "behavioraI": "behavioral",
    "cogn1tive": "cognitive",
    "cognitlve": "cognitive",

    # Common medical term OCR errors
    "shurred": "slurred",
    "slurrred": "slurred",
    "s1urred": "slurred",
    "gat": "gait",
    "gait": "gait",  # Already correct but common confusion
    "enxiety": "anxiety",
    "anxlety": "anxiety",
    "anx1ety": "anxiety",
    "cohol": "alcohol",
    "alcoho1": "alcohol",
    "a1cohol": "alcohol",
    "alcohoi": "alcohol",
    "depressiori": "depression",
    "depress1on": "depression",
    "depresslon": "depression",
    "hypertenslon": "hypertension",
    "hypertens1on": "hypertension",
    "diabeles": "diabetes",
    "d1abetes": "diabetes",
    "diabetles": "diabetes",
    "diarnoea": "diarrhoea",
    "diarrhoea": "diarrhoea",
    "diarrhea": "diarrhea",
    "nausea": "nausea",
    "nauesa": "nausea",
    "vorniting": "vomiting",
    "vom1ting": "vomiting",
    "vomltlng": "vomiting",
    "headacne": "headache",
    "headacha": "headache",
    "dizzlness": "dizziness",
    "d1zziness": "dizziness",
    "fatigue": "fatigue",
    "fat1gue": "fatigue",
    "fatlgue": "fatigue",
    "breathiess": "breathless",
    "breath1ess": "breathless",
    "breathelessness": "breathlessness",
    "dyspnoea": "dyspnoea",
    "dyspnea": "dyspnea",
    "palpitatlons": "palpitations",
    "palp1tations": "palpitations",
    "oederna": "oedema",
    "ederna": "edema",
    "oedema": "oedema",
    "swelllng": "swelling",
    "swe1ling": "swelling",
    "infiammation": "inflammation",
    "inf1ammation": "inflammation",
    "inflamrnation": "inflammation",
    "infectlon": "infection",
    "infect1on": "infection",
    "fractura": "fracture",
    "fraclure": "fracture",
    "arthritls": "arthritis",
    "arthr1tis": "arthritis",
    "osteoarthr1tis": "osteoarthritis",
    "rheumatolid": "rheumatoid",
    "rheurnatoid": "rheumatoid",
    "asthna": "asthma",
    "asthrrra": "asthma",
    "bronchitls": "bronchitis",
    "bronch1tis": "bronchitis",
    "pneuronia": "pneumonia",
    "pneumon1a": "pneumonia",
    "pneurnonia": "pneumonia",
    "ernbolism": "embolism",
    "embo1ism": "embolism",
    "thrornbosis": "thrombosis",
    "thromhos1s": "thrombosis",
    "infarctlon": "infarction",
    "infarct1on": "infarction",
    "ischaernic": "ischaemic",
    "ischaem1c": "ischaemic",
    "haemorrhage": "haemorrhage",
    "hernorrhage": "hemorrhage",
    "haernorrhage": "haemorrhage",
    "anaernia": "anaemia",
    "anern1a": "anemia",
    "anaem1a": "anaemia",
    "leukaernia": "leukaemia",
    "leucaernia": "leukaemia",
    "carcinorna": "carcinoma",
    "carc1noma": "carcinoma",
    "rnelanoma": "melanoma",
    "me1anoma": "melanoma",
    "lymphorna": "lymphoma",
    "lyrnphoma": "lymphoma",
    "sarçoma": "sarcoma",
    "sarcorna": "sarcoma",
    "demantia": "dementia",
    "dernentia": "dementia",
    "dernent1a": "dementia",
    "alzhelmer": "alzheimer",
    "alzheirner": "alzheimer",
    "parklnson": "parkinson",
    "park1nson": "parkinson",
    "epilepsy": "epilepsy",
    "ep1lepsy": "epilepsy",
    "seizura": "seizure",
    "se1zure": "seizure",
    "schizophrenla": "schizophrenia",
    "sch1zophrenia": "schizophrenia",
    "blpolar": "bipolar",
    "b1polar": "bipolar",

    # Anatomy terms
    "abdornen": "abdomen",
    "abdorinal": "abdominal",
    "abdorninal": "abdominal",
    "thoraclc": "thoracic",
    "thorac1c": "thoracic",
    "cervicaI": "cervical",
    "cerv1cal": "cervical",
    "lurnbar": "lumbar",
    "lurnbar": "lumbar",
    "sacraI": "sacral",
    "pelv1c": "pelvic",
    "pelvlc": "pelvic",
    "craniaI": "cranial",
    "cran1al": "cranial",
    "vertebraI": "vertebral",
    "vertebra1": "vertebral",
    "musculoskeletaI": "musculoskeletal",
    "cardiovascuIar": "cardiovascular",
    "card1ovascular": "cardiovascular",
    "gastrointestinaI": "gastrointestinal",
    "gastrolntestinal": "gastrointestinal",
    "respiratorv": "respiratory",
    "resp1ratory": "respiratory",
    "genitourinarv": "genitourinary",
    "gen1tourinary": "genitourinary",
    "endocrlne": "endocrine",
    "endocr1ne": "endocrine",
    "neurologlcal": "neurological",
    "neuro1og1cal": "neurological",
    "dermatologicaI": "dermatological",
    "ophthalrnological": "ophthalmological",
    "otolaryngologicaI": "otolaryngological",

    # Procedure terms
    "surgerv": "surgery",
    "surg3ry": "surgery",
    "operatlon": "operation",
    "operat1on": "operation",
    "procedura": "procedure",
    "procedurc": "procedure",
    "exarnination": "examination",
    "exarn1nation": "examination",
    "assessrnent": "assessment",
    "assessrnant": "assessment",
    "diagnos1s": "diagnosis",
    "d1agnosis": "diagnosis",
    "prognos1s": "prognosis",
    "prognosls": "prognosis",
    "treatrnent": "treatment",
    "treatrnant": "treatment",
    "thereapy": "therapy",
    "therapv": "therapy",
    "theraphy": "therapy",
    "rehabilltatlon": "rehabilitation",
    "rehab1litation": "rehabilitation",
    "physlotherapy": "physiotherapy",
    "physiotherapv": "physiotherapy",
    "radiotherapv": "radiotherapy",
    "chernotherapy": "chemotherapy",
    "chemo1herapy": "chemotherapy",
    "irnmunotherapy": "immunotherapy",
    "transfuslon": "transfusion",
    "transfus1on": "transfusion",
    "transplantation": "transplantation",
    "transplant": "transplant",
    "biopsy": "biopsy",
    "b1opsy": "biopsy",
    "endoscopv": "endoscopy",
    "endoscopy": "endoscopy",
    "colonoscopv": "colonoscopy",
    "colonoscopy": "colonoscopy",
    "gastroscopv": "gastroscopy",
    "gastroscopy": "gastroscopy",
    "sigrnoidoscopy": "sigmoidoscopy",
    "s1gmoidoscopy": "sigmoidoscopy",
    "cystoscopv": "cystoscopy",
    "cystoscopy": "cystoscopy",
    "bronchoscopv": "bronchoscopy",
    "bronchoscopy": "bronchoscopy",
    "laparoscopv": "laparoscopy",
    "laparoscopy": "laparoscopy",
    "arthrcscopv": "arthroscopy",
    "arthroscopy": "arthroscopy",
    "angiographv": "angiography",
    "angiography": "angiography",
    "echocardiographv": "echocardiography",
    "echocardiography": "echocardiography",
    "electrocardiographv": "electrocardiography",
    "electrocardiography": "electrocardiography",
    "rnanometry": "manometry",
    "manornetry": "manometry",

    # Medication terms
    "rnedication": "medication",
    "med1cation": "medication",
    "prescriptlon": "prescription",
    "prescript1on": "prescription",
    "dosaga": "dosage",
    "dosaqe": "dosage",
    "tabIet": "tablet",
    "tab1et": "tablet",
    "capsuIe": "capsule",
    "capsu1e": "capsule",
    "injectlon": "injection",
    "inject1on": "injection",
    "infuslon": "infusion",
    "infus1on": "infusion",
    "inhaIer": "inhaler",
    "inha1er": "inhaler",
    "antiblotic": "antibiotic",
    "antib1otic": "antibiotic",
    "analgesic": "analgesic",
    "ana1gesic": "analgesic",
    "anaesthetlc": "anaesthetic",
    "anaesthet1c": "anaesthetic",
    "anticoaguIant": "anticoagulant",
    "ant1coagulant": "anticoagulant",
    "antldepressant": "antidepressant",
    "anti-depressant": "antidepressant",
    "antlhypertensive": "antihypertensive",
    "anti-hypertensive": "antihypertensive",
    "antldiabetic": "antidiabetic",
    "anti-dlabetic": "antidiabetic",
    "ant1histamine": "antihistamine",
    "antihistarnine": "antihistamine",
    "antlpsychotic": "antipsychotic",
    "anti-psychotic": "antipsychotic",
    "bronchodiIator": "bronchodilator",
    "bronchod1lator": "bronchodilator",
    "corticosterold": "corticosteroid",
    "corticostero1d": "corticosteroid",
    "lrnmunosuppressant": "immunosuppressant",
    "immunosupressant": "immunosuppressant",
    "diuretic": "diuretic",
    "d1uretic": "diuretic",
    "laxatlve": "laxative",
    "1axative": "laxative",
    "sedatlve": "sedative",
    "sedat1ve": "sedative",
    "stlmulant": "stimulant",
    "st1mulant": "stimulant",
    "vacclne": "vaccine",
    "vacc1ne": "vaccine",

    # Common drug names with OCR errors
    "paracetamoI": "paracetamol",
    "paracetamo1": "paracetamol",
    "ibuprofen": "ibuprofen",
    "1buprofen": "ibuprofen",
    "arnoxicillin": "amoxicillin",
    "amoxici11in": "amoxicillin",
    "arnpicillin": "ampicillin",
    "penicl11in": "penicillin",
    "penici1lin": "penicillin",
    "rnetformin": "metformin",
    "metforrn1n": "metformin",
    "orneprazole": "omeprazole",
    "omeprazo1e": "omeprazole",
    "lansoprazo1e": "lansoprazole",
    "pantoprazo1e": "pantoprazole",
    "atorvastatln": "atorvastatin",
    "atorvastat1n": "atorvastatin",
    "sirnvastatin": "simvastatin",
    "s1mvastatin": "simvastatin",
    "arnlodipine": "amlodipine",
    "amlod1pine": "amlodipine",
    "rarnipril": "ramipril",
    "rarnlpril": "ramipril",
    "lisinopriI": "lisinopril",
    "lis1nopril": "lisinopril",
    "bisoproIol": "bisoprolol",
    "b1soprolol": "bisoprolol",
    "atenol0l": "atenolol",
    "ateno1ol": "atenolol",
    "rnetoprolol": "metoprolol",
    "metoproloI": "metoprolol",
    "warfarln": "warfarin",
    "warfar1n": "warfarin",
    "aspirln": "aspirin",
    "asp1rin": "aspirin",
    "clopldogrel": "clopidogrel",
    "clop1dogrel": "clopidogrel",
    "apixaban": "apixaban",
    "ap1xaban": "apixaban",
    "rivaroxaban": "rivaroxaban",
    "r1varoxaban": "rivaroxaban",
    "levothyrox1ne": "levothyroxine",
    "levothyroxlne": "levothyroxine",
    "arniodarone": "amiodarone",
    "am1odarone": "amiodarone",
    "diazeparn": "diazepam",
    "d1azepam": "diazepam",
    "lorazeparn": "lorazepam",
    "1orazepam": "lorazepam",
    "sertraIine": "sertraline",
    "sertra1ine": "sertraline",
    "cltaIopram": "citalopram",
    "c1talopram": "citalopram",
    "fluoxetlne": "fluoxetine",
    "f1uoxetine": "fluoxetine",
    "rnirtazapine": "mirtazapine",
    "m1rtazapine": "mirtazapine",
    "gabapentln": "gabapentin",
    "gabapent1n": "gabapentin",
    "pregaballn": "pregabalin",
    "pregaba1in": "pregabalin",
    "rnorphine": "morphine",
    "morph1ne": "morphine",
    "codeine": "codeine",
    "code1ne": "codeine",
    "trarnadol": "tramadol",
    "trarnadoI": "tramadol",
    "fentanyI": "fentanyl",
    "fentany1": "fentanyl",
    "oxycodone": "oxycodone",
    "0xycodone": "oxycodone",
    "macrogoI": "macrogol",
    "macrogo1": "macrogol",
    "lactuIose": "lactulose",
    "lactu1ose": "lactulose",
    "senna": "senna",
    "docusate": "docusate",
    "rnovicol": "movicol",
    "mov1col": "movicol",

    # Investigation/test terms
    "x-ray": "X-ray",
    "xray": "X-ray",
    "X-rav": "X-ray",
    "ultrasonography": "ultrasonography",
    "u1trasonography": "ultrasonography",
    "u1trasound": "ultrasound",
    "UItra sound": "ultrasound",
    "rnagnetic": "magnetic",
    "magnet1c": "magnetic",
    "rnonance": "resonance",
    "resonanca": "resonance",
    "cornputed": "computed",
    "computed": "computed",
    "tomographv": "tomography",
    "tornography": "tomography",
    "radiograph": "radiograph",
    "rad1ograph": "radiograph",
    "fluoroscopv": "fluoroscopy",
    "f1uoroscopy": "fluoroscopy",
    "rnammography": "mammography",
    "mammographv": "mammography",
    "histologv": "histology",
    "h1stology": "histology",
    "pathologv": "pathology",
    "patho1ogy": "pathology",
    "cytologv": "cytology",
    "cyto1ogy": "cytology",
    "rnicrobiology": "microbiology",
    "m1crobiology": "microbiology",
    "haernatology": "haematology",
    "haematologv": "haematology",
    "blochemistry": "biochemistry",
    "biochernistry": "biochemistry",
    "irnmunology": "immunology",
    "immunologv": "immunology",
    "serologv": "serology",
    "sero1ogy": "serology",

    # Common clinical phrases OCR errors
    "no abnorrnality": "no abnormality",
    "no abnorrna1ity": "no abnormality",
    "unrernarkable": "unremarkable",
    "unremarkab1e": "unremarkable",
    "withln normal limlts": "within normal limits",
    "w1thin normal l1mits": "within normal limits",
    "no slgnificant": "no significant",
    "no s1gnificant": "no significant",
    "clnically": "clinically",
    "cl1nically": "clinically",
    "historv": "history",
    "h1story": "history",
    "farnily": "family",
    "fam1ly": "family",
    "rnedical history": "medical history",
    "rnedlcal history": "medical history",
    "presenting cornplaint": "presenting complaint",
    "present1ng complaint": "presenting complaint",
    "chief cornplaint": "chief complaint",
    "ch1ef complaint": "chief complaint",
    "differentia1": "differential",
    "differentiaI": "differential",
    "impresslon": "impression",
    "impress1on": "impression",
    "recornmendation": "recommendation",
    "recornrnendation": "recommendation",
    "fo11ow-up": "follow-up",
    "foIIow-up": "follow-up",
    "follow up": "follow-up",
    "foIIow up": "follow-up",
    "dlscharge": "discharge",
    "d1scharge": "discharge",
    "adrnission": "admission",
    "adm1ssion": "admission",
    "transfer": "transfer",
    "referraI": "referral",
    "referra1": "referral",
    "consuItation": "consultation",
    "consu1tation": "consultation",
    "appointrnent": "appointment",
    "appo1ntment": "appointment",
}

# Clinical abbreviations to preserve (case-sensitive)
CLINICAL_ABBREVIATIONS: set = {
    # Common clinical abbreviations
    "NHS", "GP", "A&E", "ED", "ICU", "ITU", "CCU", "HDU", "NICU", "PICU", "SCBU",
    "OPD", "IPD", "ENT", "GI", "GU", "CVS", "CNS", "PNS", "MSK", "Resp", "Cardio",
    "Neuro", "Psych", "Ortho", "Obs", "Gynae", "Paeds", "Geriatrics",
    # Vital signs
    "BP", "HR", "RR", "SpO2", "Temp", "GCS", "AVPU", "NEWS", "MEWS",
    # Tests and investigations
    "FBC", "U&E", "LFT", "TFT", "HbA1c", "eGFR", "CRP", "ESR", "INR", "PT", "APTT",
    "ABG", "VBG", "ECG", "EKG", "EEG", "EMG", "NCS", "MRI", "CT", "CXR", "AXR", "USS",
    "PET", "SPECT", "DEXA", "LP", "CSF", "MSU", "MSSU", "C&S",
    # Diagnoses
    "COPD", "CHF", "CCF", "MI", "ACS", "NSTEMI", "STEMI", "AF", "SVT", "VT", "VF",
    "PE", "DVT", "CVA", "TIA", "SAH", "SDH", "EDH", "ICH", "DKA", "HHS", "AKI", "CKD",
    "UTI", "LRTI", "URTI", "CAP", "HAP", "VAP", "MRSA", "VRE", "C.diff", "HIV", "AIDS",
    "TB", "MS", "PD", "AD", "MND", "GBS", "SLE", "RA", "OA", "PMR", "GCA", "IBD", "UC",
    "CD", "IBS", "GORD", "GERD", "PUD", "AAA", "PAD", "CVI", "BPH", "PCOS", "PID",
    # Treatments
    "IV", "IM", "SC", "PO", "PR", "SL", "TOP", "INH", "NEB", "CPAP", "BiPAP", "NIV",
    "HFNO", "PEG", "NG", "NJ", "TPN", "PICC", "CVC", "Hickman", "TEDS", "Flowtron",
    "PRN", "OD", "BD", "TDS", "QDS", "STAT", "OM", "ON", "Mane", "Nocte",
    # Procedures
    "TURP", "TURBT", "ERCP", "PCI", "CABG", "AVR", "MVR", "TVR", "TAVI", "ICD", "PPM",
    "CRT", "AICD", "AV", "RFA", "ESWL", "PCNL", "URS", "TKR", "THR", "TSR", "ACL",
    # Organisations
    "NICE", "BNF", "GMC", "NMC", "CQC", "CCG", "ICS", "PCN", "NHSE", "PHE", "UKHSA",
    # Scoring systems
    "CURB-65", "Wells", "PERC", "HEART", "TIMI", "GRACE", "CHA2DS2-VASc", "HAS-BLED",
    "SOFA", "qSOFA", "Apache", "APACHE", "Rockall", "Blatchford", "Child-Pugh", "MELD",
    # Other common
    "PMH", "DHx", "SHx", "FHx", "Hx", "Dx", "DDx", "Rx", "Tx", "Ix", "Mx", "Px",
    "O/E", "C/O", "H/O", "S/P", "NAD", "WNL", "NKA", "NKDA", "NPO", "NBM", "TTO",
    "OTC", "Appt", "F/U", "R/V", "DNA", "WAS", "CNA",
}

# Section heading patterns to preserve
SECTION_HEADING_PATTERNS: List[str] = [
    r"^(DIAGNOSIS|Diagnosis|diagnosis):?\s*$",
    r"^(HISTORY|History|history):?\s*$",
    r"^(EXAMINATION|Examination|examination):?\s*$",
    r"^(INVESTIGATIONS?|Investigations?|investigations?):?\s*$",
    r"^(MANAGEMENT|Management|management):?\s*$",
    r"^(PLAN|Plan|plan):?\s*$",
    r"^(MEDICATIONS?|Medications?|medications?):?\s*$",
    r"^(ALLERGIES|Allergies|allergies):?\s*$",
    r"^(IMPRESSION|Impression|impression):?\s*$",
    r"^(CONCLUSION|Conclusion|conclusion):?\s*$",
    r"^(RECOMMENDATION|Recommendation|recommendation):?\s*$",
    r"^(SUMMARY|Summary|summary):?\s*$",
    r"^(ASSESSMENT|Assessment|assessment):?\s*$",
    r"^(PROCEDURE|Procedure|procedure):?\s*$",
    r"^(FINDINGS?|Findings?|findings?):?\s*$",
    r"^(PRESENTING COMPLAINT|Presenting [Cc]omplaint):?\s*$",
    r"^(CHIEF COMPLAINT|Chief [Cc]omplaint):?\s*$",
    r"^(PAST MEDICAL HISTORY|Past [Mm]edical [Hh]istory|PMH):?\s*$",
    r"^(DRUG HISTORY|Drug [Hh]istory|DHx):?\s*$",
    r"^(SOCIAL HISTORY|Social [Hh]istory|SHx):?\s*$",
    r"^(FAMILY HISTORY|Family [Hh]istory|FHx):?\s*$",
    r"^(FOLLOW[- ]?UP|Follow[- ]?[Uu]p):?\s*$",
    r"^(DISCHARGE SUMMARY|Discharge [Ss]ummary):?\s*$",
    r"^(GP ACTIONS?|GP [Aa]ctions?|Actions Required):?\s*$",
    r"^(CLINICAL DETAILS?|Clinical [Dd]etails?):?\s*$",
    r"^(OPERATION|Operation|OPERATIVE NOTES?):?\s*$",
    r"^(POST[- ]?OP|Post[- ]?[Oo]p|POST[- ]?OPERATIVE):?\s*$",
    r"^(SPECIMENS?|Specimens?):?\s*$",
    r"^(RESULTS?|Results?):?\s*$",
    r"^(VITAL SIGNS?|Vital [Ss]igns?|Vitals?|OBSERVATIONS?|Observations?):?\s*$",
]

# Unicode replacements for common OCR artifacts
UNICODE_REPLACEMENTS: Dict[str, str] = {
    "‘": "'",   # Left single quote
    "’": "'",   # Right single quote
    "“": '"',   # Left double quote
    "”": '"',   # Right double quote
    "–": "-",   # En dash
    "—": "-",   # Em dash
    "…": "...", # Ellipsis
    " ": " ",   # Non-breaking space
    "­": "",    # Soft hyphen
    "​": "",    # Zero-width space
    "‌": "",    # Zero-width non-joiner
    "‍": "",    # Zero-width joiner
    "﻿": "",    # Byte order mark
    "·": ".",   # Middle dot
    "•": "-",   # Bullet
    "‣": "-",   # Triangular bullet
    "⁃": "-",   # Hyphen bullet
    "▪": "-",   # Black small square
    "▫": "-",   # White small square
    "●": "-",   # Black circle
    "○": "-",   # White circle
    "°": " degrees ",  # Degree symbol
    "±": "+/-", # Plus-minus
    "×": "x",   # Multiplication sign
    "÷": "/",   # Division sign
    "−": "-",   # Minus sign
    "≤": "<=",  # Less than or equal
    "≥": ">=",  # Greater than or equal
    "¼": "1/4", # One quarter
    "½": "1/2", # One half
    "¾": "3/4", # Three quarters
    "²": "2",   # Superscript 2
    "³": "3",   # Superscript 3
    "¹": "1",   # Superscript 1
    "⁰": "0",   # Superscript 0
    "⁴": "4",   # Superscript 4
    "⁵": "5",   # Superscript 5
    "⁶": "6",   # Superscript 6
    "⁷": "7",   # Superscript 7
    "⁸": "8",   # Superscript 8
    "⁹": "9",   # Superscript 9
    "®": "(R)", # Registered trademark
    "™": "(TM)", # Trademark
    "©": "(C)", # Copyright
    "£": "GBP", # Pound sign
    "€": "EUR", # Euro sign
    "§": "S",   # Section sign
    "¶": "",    # Pilcrow
    "«": '"',   # Left-pointing double angle
    "»": '"',   # Right-pointing double angle
}

# OCR artifact patterns to remove
OCR_ARTIFACT_PATTERNS: List[str] = [
    r"[|]{3,}",           # Multiple pipe characters
    r"[_]{5,}",           # Long underscores (form lines)
    r"[\-]{5,}",          # Long dashes (separator lines)
    r"[=]{5,}",           # Long equals (separator lines)
    r"[\.]{5,}",          # Long dots (form fill)
    r"[\*]{3,}",          # Multiple asterisks
    r"[#]{3,}",           # Multiple hash marks
    r"~{3,}",             # Multiple tildes
    r"\[\s*\]",           # Empty brackets
    r"\(\s*\)",           # Empty parentheses
    r"\{\s*\}",           # Empty braces
    r"<\s*>",             # Empty angle brackets
    r"\bPage\s+\d+\s+of\s+\d+\b",  # Page numbers
    r"\bPg\.\s*\d+\b",    # Short page numbers
    r"^\s*\d+\s*$",       # Standalone page numbers
    r"\x0c",              # Form feed character
    r"[\x00-\x08\x0b\x0e-\x1f\x7f]",  # Control characters
]


class MedicalTextNormalizer:
    """
    Normalizes raw OCR text from medical documents for NLP processing.

    Handles:
    - Common OCR character substitution errors
    - Medical terminology corrections
    - Line-break word merging
    - Unicode normalization
    - Artifact removal
    - Section heading preservation
    - Clinical abbreviation preservation
    - Bullet point hierarchy preservation
    """

    def __init__(
        self,
        custom_corrections: Optional[Dict[str, str]] = None,
        custom_abbreviations: Optional[set] = None,
        preserve_line_breaks: bool = False,
    ):
        """
        Initialize the normalizer.

        Args:
            custom_corrections: Additional OCR corrections to apply
            custom_abbreviations: Additional clinical abbreviations to preserve
            preserve_line_breaks: Whether to keep original line breaks
        """
        self.corrections = {**OCR_CORRECTIONS}
        if custom_corrections:
            self.corrections.update(custom_corrections)

        self.abbreviations = CLINICAL_ABBREVIATIONS.copy()
        if custom_abbreviations:
            self.abbreviations.update(custom_abbreviations)

        self.preserve_line_breaks = preserve_line_breaks

        # Compile section heading patterns
        self.section_patterns = [
            re.compile(p, re.MULTILINE) for p in SECTION_HEADING_PATTERNS
        ]

        # Compile artifact patterns
        self.artifact_patterns = [
            re.compile(p, re.MULTILINE) for p in OCR_ARTIFACT_PATTERNS
        ]

        # Build correction regex (case-insensitive for most)
        self._build_correction_regex()

    def _build_correction_regex(self) -> None:
        """Build compiled regex for OCR corrections."""
        # Sort by length (longest first) to prevent partial matches
        sorted_terms = sorted(self.corrections.keys(), key=len, reverse=True)

        # Escape special regex characters and join with |
        escaped = [re.escape(term) for term in sorted_terms]
        pattern = r'\b(' + '|'.join(escaped) + r')\b'

        self.correction_regex = re.compile(pattern, re.IGNORECASE)

    def normalize(self, raw_text: str) -> NormalizationResult:
        """
        Normalize raw OCR text for clinical NLP processing.

        Args:
            raw_text: Raw OCR output text

        Returns:
            NormalizationResult with both raw and normalized text
        """
        result = NormalizationResult(raw_text=raw_text, normalized_text=raw_text)

        text = raw_text

        # Step 1: Normalize Unicode characters
        text, unicode_count = self._normalize_unicode(text)
        result.unicode_normalized = unicode_count

        # Step 2: Remove OCR artifacts
        text, artifacts_count = self._remove_artifacts(text)
        result.artifacts_removed = artifacts_count

        # Step 3: Normalize whitespace (preserve structure)
        text = self._normalize_whitespace(text)

        # Step 4: Merge words split across lines
        text, lines_merged = self._merge_split_words(text)
        result.lines_merged = lines_merged

        # Step 5: Apply OCR corrections
        text, corrections = self._apply_corrections(text)
        result.corrections_made = corrections

        # Step 6: Normalize punctuation
        text = self._normalize_punctuation(text)

        # Step 7: Preserve and clean section headings
        text = self._clean_section_headings(text)

        # Step 8: Preserve bullet hierarchy
        text = self._normalize_bullets(text)

        # Step 9: Final cleanup
        text = self._final_cleanup(text)

        result.normalized_text = text
        return result

    def _normalize_unicode(self, text: str) -> Tuple[str, int]:
        """Normalize Unicode characters to ASCII equivalents."""
        count = 0

        # Apply explicit replacements
        for old, new in UNICODE_REPLACEMENTS.items():
            if old in text:
                occurrences = text.count(old)
                text = text.replace(old, new)
                count += occurrences

        # Normalize remaining Unicode to NFKC form
        normalized = unicodedata.normalize('NFKC', text)
        if normalized != text:
            count += 1

        return normalized, count

    def _remove_artifacts(self, text: str) -> Tuple[str, int]:
        """Remove common OCR artifacts."""
        count = 0

        for pattern in self.artifact_patterns:
            matches = pattern.findall(text)
            if matches:
                count += len(matches)
                text = pattern.sub('', text)

        return text, count

    def _normalize_whitespace(self, text: str) -> str:
        """Normalize whitespace while preserving paragraph structure."""
        # Replace tabs with spaces
        text = text.replace('\t', ' ')

        # Collapse multiple spaces to single space
        text = re.sub(r'[ ]+', ' ', text)

        # Normalize line endings
        text = text.replace('\r\n', '\n').replace('\r', '\n')

        # Collapse more than 2 consecutive newlines to 2
        text = re.sub(r'\n{3,}', '\n\n', text)

        # Remove spaces at start/end of lines
        text = re.sub(r'[ ]+\n', '\n', text)
        text = re.sub(r'\n[ ]+', '\n', text)

        return text.strip()

    def _merge_split_words(self, text: str) -> Tuple[str, int]:
        """Merge words that were split across lines by OCR."""
        count = 0

        # Pattern for hyphenated line breaks: word- \n continuation
        hyphen_pattern = re.compile(r'(\w+)-\s*\n\s*(\w+)')

        def merge_hyphenated(match):
            nonlocal count
            word1, word2 = match.groups()
            merged = word1 + word2

            # Check if merged word is in corrections or looks valid
            if merged.lower() in self.corrections.values() or len(merged) > 3:
                count += 1
                return merged
            return match.group(0)

        text = hyphen_pattern.sub(merge_hyphenated, text)

        # Pattern for words split without hyphen (common in multi-column OCR)
        # Only merge if the result is a known medical term
        split_pattern = re.compile(r'(\w{2,})\s*\n\s*(\w{2,})')

        def maybe_merge_split(match):
            nonlocal count
            word1, word2 = match.groups()
            merged = word1 + word2
            merged_lower = merged.lower()

            # Only merge if it creates a known medical term
            if merged_lower in self.corrections.values():
                count += 1
                return merged
            return match.group(0)

        # Apply conservatively - only in specific contexts
        # This is intentionally limited to avoid over-merging

        return text, count

    def _apply_corrections(self, text: str) -> Tuple[str, List[Dict[str, str]]]:
        """Apply OCR correction dictionary."""
        corrections_made = []

        def replace_match(match):
            original = match.group(0)
            key = original.lower()

            # Find the correction (case-insensitive lookup)
            for k, v in self.corrections.items():
                if k.lower() == key:
                    # Preserve original case pattern if possible
                    if original.isupper():
                        replacement = v.upper()
                    elif original[0].isupper():
                        replacement = v.capitalize()
                    else:
                        replacement = v

                    corrections_made.append({
                        'original': original,
                        'corrected': replacement,
                        'position': match.start()
                    })
                    return replacement

            return original

        text = self.correction_regex.sub(replace_match, text)

        return text, corrections_made

    def _normalize_punctuation(self, text: str) -> str:
        """Normalize punctuation for consistent parsing."""
        # Fix common OCR punctuation errors

        # Multiple periods to single (but preserve ellipsis)
        text = re.sub(r'\.{4,}', '...', text)

        # Fix spacing around punctuation
        text = re.sub(r'\s+([,;:!?])', r'\1', text)
        text = re.sub(r'([,;:])(?!\s)(?!$)', r'\1 ', text)

        # Fix missing space after period (but not decimals or abbreviations)
        text = re.sub(r'\.([A-Z])', r'. \1', text)

        # Fix OCR'd fractions (e.g., "1 /2" -> "1/2")
        text = re.sub(r'(\d)\s*/\s*(\d)', r'\1/\2', text)

        # Normalize quote marks
        text = re.sub(r"[''`]", "'", text)
        text = re.sub(r'[""]', '"', text)

        return text

    def _clean_section_headings(self, text: str) -> str:
        """Preserve and clean section headings."""
        lines = text.split('\n')
        cleaned_lines = []

        for line in lines:
            stripped = line.strip()

            # Check if line matches a section heading pattern
            is_heading = False
            for pattern in self.section_patterns:
                if pattern.match(stripped):
                    is_heading = True
                    break

            if is_heading:
                # Ensure heading is on its own line with proper formatting
                # Add colon if missing
                if not stripped.endswith(':'):
                    stripped = stripped.rstrip(':') + ':'

                # Ensure blank line before heading (unless first line)
                if cleaned_lines and cleaned_lines[-1].strip():
                    cleaned_lines.append('')

                cleaned_lines.append(stripped)
            else:
                cleaned_lines.append(line)

        return '\n'.join(cleaned_lines)

    def _normalize_bullets(self, text: str) -> str:
        """Normalize bullet points while preserving hierarchy."""
        # Common bullet patterns from OCR
        bullet_patterns = [
            (r'^[\s]*[•·▪▸►◦○●]\s*', '- '),
            (r'^[\s]*[\-\*]\s+', '- '),
            (r'^[\s]*(\d+)[.)]\s+', r'\1. '),
            (r'^[\s]*([a-z])[.)]\s+', r'\1) '),
            (r'^[\s]*([ivxIVX]+)[.)]\s+', r'\1. '),
        ]

        lines = text.split('\n')
        normalized_lines = []

        for line in lines:
            normalized = line
            for pattern, replacement in bullet_patterns:
                normalized = re.sub(pattern, replacement, normalized)
            normalized_lines.append(normalized)

        return '\n'.join(normalized_lines)

    def _final_cleanup(self, text: str) -> str:
        """Final cleanup pass."""
        # Remove any remaining control characters
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)

        # Collapse excessive whitespace one more time
        text = re.sub(r' {2,}', ' ', text)
        text = re.sub(r'\n{3,}', '\n\n', text)

        # Ensure text ends with single newline
        text = text.strip() + '\n'

        return text

    def get_statistics(self, result: NormalizationResult) -> Dict:
        """Get statistics about the normalization process."""
        raw_len = len(result.raw_text)
        norm_len = len(result.normalized_text)

        return {
            'raw_length': raw_len,
            'normalized_length': norm_len,
            'length_change': norm_len - raw_len,
            'length_change_percent': round((norm_len - raw_len) / raw_len * 100, 2) if raw_len > 0 else 0,
            'corrections_count': len(result.corrections_made),
            'artifacts_removed': result.artifacts_removed,
            'lines_merged': result.lines_merged,
            'unicode_normalized': result.unicode_normalized,
            'corrections': result.corrections_made[:10],  # First 10 for preview
        }


def normalize_medical_text(
    raw_text: str,
    custom_corrections: Optional[Dict[str, str]] = None,
    return_stats: bool = False
) -> Tuple[str, str] | Tuple[str, str, Dict]:
    """
    Convenience function to normalize medical OCR text.

    Args:
        raw_text: Raw OCR output
        custom_corrections: Optional additional corrections
        return_stats: Whether to return statistics

    Returns:
        Tuple of (raw_text, normalized_text) or
        Tuple of (raw_text, normalized_text, stats) if return_stats=True
    """
    normalizer = MedicalTextNormalizer(custom_corrections=custom_corrections)
    result = normalizer.normalize(raw_text)

    if return_stats:
        stats = normalizer.get_statistics(result)
        return result.raw_text, result.normalized_text, stats

    return result.raw_text, result.normalized_text


# Standalone test
if __name__ == '__main__':
    test_text = """
    DISCHARGE SUMMARY

    Patient presented with coIapse and shurred speech.
    History of enxiety and cohol abuse.

    Examination:
    - BIood pressure: 140/90
    - Gat: unsteady
    - NormaI neuro1ogical examination otherwise

    Diagnosis: Syncope, likely vasovagal

    Medications on Discharge:
    - Paracetamo1 500mg QDS PRN
    - Omeprazo1e 20mg OD
    - MacrogoI compound (MovicoI) 1 sachet BD

    FoIIow-up: GP in 2 weeks

    |||||______|||||
    Page 1 of 1
    """

    normalizer = MedicalTextNormalizer()
    result = normalizer.normalize(test_text)
    stats = normalizer.get_statistics(result)

    print("=" * 60)
    print("RAW TEXT:")
    print("=" * 60)
    print(result.raw_text)

    print("\n" + "=" * 60)
    print("NORMALIZED TEXT:")
    print("=" * 60)
    print(result.normalized_text)

    print("\n" + "=" * 60)
    print("STATISTICS:")
    print("=" * 60)
    for key, value in stats.items():
        print(f"  {key}: {value}")
