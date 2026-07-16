"""
Clinical Document Processing Portal — Flask backend
Matches the NHS-style document management UI from the reference screenshot.
Full auto-pipeline: Upload → Tier0 (OpenCV) → Tier1 Textract → Tier2 routing →
TrackA SNOMED+HIPAA → Clinical Validation → TrackB Summarization → Confidence routing → Results.

Wires into the production modules defined in the SRS architecture:
  - document_handler.prepare_document()  — multi-format ingestion (PDF/TIFF/JPEG)
  - preprocessing.preprocess_image()     — Tier 0 OpenCV adaptive threshold + deskew
  - hipaa_compliance.detect_phi_entities() — HIPAA PHI detection on extracted text
  - config.document_type_config           — 21-type classifier + per-type thresholds
  - clinical_engine                       — Context-aware entity validation + classification
"""
import base64
import json
import os
import shutil
import time
import traceback
import uuid
from datetime import datetime
from pathlib import Path

import boto3
from flask import Flask, jsonify, render_template_string, request, send_from_directory
from werkzeug.utils import secure_filename

# ── Load .env file if present (so portal works without manually exporting vars) ─
_env_file = Path(__file__).parent / ".env"
if _env_file.exists():
    with open(_env_file) as _ef:
        for _line in _ef:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                _key = _k.strip()
                _val = _v.strip().strip('"').strip("'")
                # Use .env value when variable is missing OR present-but-empty.
                _current = os.environ.get(_key)
                if _current is None or not str(_current).strip():
                    os.environ[_key] = _val

# ── AWS clients ───────────────────────────────────────────────────────────────
# Credentials are read from environment variables or .env file — never hardcoded.
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
AWS_KEY    = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET = os.getenv("AWS_SECRET_ACCESS_KEY")

def make_client(service):
    # Read credentials fresh at call time so that values loaded from .env
    # after module import (or injected by tests) are always picked up.
    key    = os.getenv("AWS_ACCESS_KEY_ID")
    secret = os.getenv("AWS_SECRET_ACCESS_KEY")
    region = os.getenv("AWS_REGION", AWS_REGION)
    client_kwargs = {"region_name": region}
    if key and secret:
        client_kwargs["aws_access_key_id"]     = key
        client_kwargs["aws_secret_access_key"] = secret
    elif key or secret:
        raise ValueError(
            "Incomplete AWS credential configuration: set both "
            "AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY, or neither "
            "to allow boto3 to use its default credential chain."
        )
    return boto3.client(service, **client_kwargs)

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE        = Path(__file__).parent
UPLOAD_DIR  = BASE / "portal_uploads"
RESULTS_DIR = BASE / "portal_results"
STATIC_DIR  = BASE / "portal_static"
for d in [UPLOAD_DIR, RESULTS_DIR, STATIC_DIR]:
    d.mkdir(exist_ok=True)

# FIX (review comment 2): Import thresholds from the single source of truth in
# config/document_type_config.py instead of duplicating them here.
# This prevents drift between portal.py and the config module.
import sys as _sys
_sys.path.insert(0, str(Path(__file__).parent))
from config.document_type_config import get_threshold as _get_threshold

CONFIDENCE_THRESHOLD = 0.72  # global fallback — calibrated to real AWS output ranges

# OBS-010: Arrival method codes from Frimley ED discharge letters.
# Codes appear in brackets e.g. "Emergency Road Ambulance WITH Medical Escort [8]"
ARRIVAL_METHOD_CODES = {
    "1":  "Self Referral",
    "2":  "Emergency Services",
    "3":  "Police Transport",
    "4":  "Healthcare Provider",
    "6":  "Emergency Ambulance",
    "8":  "Emergency Road Ambulance WITH Medical Escort",
    "10": "Air Ambulance",
    "15": "Patient arranged own transport / walk-in",
    "99": "Other",
}

ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".pdf", ".tiff", ".tif"}

# OBS-007: Sensitive content markers — these phrases trigger protective handling
# in patient-facing summaries to avoid re-traumatisation.
SENSITIVE_CONTENT_MARKERS = [
    "poppy", "neonatal death", "safeguarding referral", "command hallucination",
    "suicidal ideation", "overdose", "ingested", "mental capacity act",
    "police transport", "icu", "intubated", "self-harm",
]

# ── Production module imports (SRS architecture) ───────────────────────────────
# Gracefully degrade if optional heavyweight dependencies are unavailable
# (e.g. cv2 not installed in the portal's virtual-env).

try:
    from document_handler import prepare_document as _prepare_document
    _HAS_DOCUMENT_HANDLER = True
except ImportError:
    _HAS_DOCUMENT_HANDLER = False

try:
    from preprocessing import preprocess_image as _preprocess_image
    _HAS_PREPROCESSING = True
except ImportError:
    _HAS_PREPROCESSING = False

try:
    from hipaa_compliance import detect_phi_entities as _detect_phi
    _HAS_HIPAA = True
except ImportError:
    _HAS_HIPAA = False

# Clinical Engine: Context-aware entity validation and classification
try:
    from clinical_engine import (
        process_clinical_entities,
        categorize_entities_for_output,
        detect_document_sections,
        ClinicalValidationEngine,
        ConfidenceScore,
        EntityCategory,
        NegationStatus,
        TemporalState,
        SectionType,
    )
    _HAS_CLINICAL_ENGINE = True
except ImportError:
    _HAS_CLINICAL_ENGINE = False


def _prepare_pages(file_path: Path, out_dir: Path) -> list:
    """
    Tier 0 receptionist + preprocessor (SRS §3.1 / §7 step 1 & 2).

    Uses document_handler.prepare_document() for multi-format ingestion
    (PDF, TIFF, JPEG, PNG) as per SRS Section 3.1 and document_handler.py.

    Falls back to PyMuPDF-only PDF splitting if document_handler is
    unavailable (e.g. cv2 not installed in this venv).
    """
    if _HAS_DOCUMENT_HANDLER:
        # prepare_document() returns (image_paths, failed_pages) tuple — unpack correctly
        paths, _failed = _prepare_document(str(file_path), output_dir=str(out_dir))
        return [Path(p) for p in paths]

    # Fallback: PyMuPDF for PDFs, direct copy for images
    import fitz
    ext = file_path.suffix.lower()
    if ext == ".pdf":
        doc  = fitz.open(str(file_path))
        mat  = fitz.Matrix(2.0, 2.0)
        imgs = []
        for i, page in enumerate(doc):
            pix  = page.get_pixmap(matrix=mat)
            dest = out_dir / f"page_{i+1:02d}.png"
            pix.save(str(dest))
            imgs.append(dest)
        return imgs
    else:
        dest = out_dir / file_path.name
        shutil.copy(file_path, dest)
        return [dest]


def _run_tier0_preprocessing(image_paths: list, out_dir: Path) -> list:
    """
    Tier 0 image preprocessing (SRS §3.1 Tier 0 — OpenCV):
    adaptive thresholding, morphological noise reduction, and deskewing.

    Calls preprocessing.preprocess_image() from the production module.
    Falls back to returning the originals unchanged if cv2 is unavailable.
    """
    if not _HAS_PREPROCESSING:
        return image_paths   # graceful degradation

    processed = []
    for img in image_paths:
        dest = out_dir / f"pre_{img.name}"
        try:
            _preprocess_image(str(img), str(dest))
            processed.append(Path(dest))
        except Exception:
            processed.append(img)   # keep original on failure
    return processed

app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="/static")

# ── Pipeline helpers ──────────────────────────────────────────────────────────

def run_textract(image_path: Path) -> dict:
    """Run Tier 1 Textract on a single image."""
    client = make_client("textract")
    with open(image_path, "rb") as f:
        img_bytes = f.read()
    resp = client.analyze_document(
        Document={"Bytes": img_bytes},
        FeatureTypes=["TABLES", "FORMS"],
    )
    blocks   = resp.get("Blocks", [])
    lines    = [b["Text"] for b in blocks if b.get("BlockType") == "LINE" and b.get("Text")]
    confs    = [b.get("Confidence", 0) for b in blocks if b.get("BlockType") == "WORD"]
    avg_conf = (sum(confs) / len(confs) / 100) if confs else 0.5
    return {"text": "\n".join(lines), "confidence": avg_conf, "blocks": blocks}


import re as _re

# Clinical keyword patterns for regex-based extraction (used when Comprehend finds nothing).
# Covers common NHS letter terminology across maternity, cardiology, respiratory, etc.
_CLINICAL_KEYWORD_PATTERNS = [
    # Maternity / antenatal
    r'\b(antenatal|postnatal|prenatal|antepartum|postpartum)\b',
    r'\b(pregnancy|pregnant|gravida|para|gestation|gestational)\b',
    r'\b(labour|labor|delivery|caesarean|c-section|episiotomy|forceps)\b',
    r'\b(miscarriage|stillbirth|ectopic|placenta|preeclampsia|pre-eclampsia)\b',
    r'\b(fetal|foetal|neonatal|newborn|infant|neonate)\b',
    r'\b(midwife|midwifery|obstetric|obstetrician|gynaecology|gynecology)\b',
    # Neurodevelopmental / psychiatric — observed in real test PDFs
    r'\b(autism|autistic|autism spectrum|ASD)\b',
    r'\b(downs syndrome|down syndrome|trisomy 21|trisomy21)\b',
    r'\b(learning disability|learning difficulties|intellectual disability)\b',
    r'\b(ADHD|attention deficit|hyperactivity disorder)\b',
    r'\b(anxiety disorder|generalised anxiety|generalized anxiety|GAD)\b',
    r'\b(behavioural problems|behaviour problems|sleep challenges|sleep disorder)\b',
    r'\b(psychosis|schizophrenia|bipolar|dementia|delirium|PTSD)\b',
    r'\b(depression|depressive disorder|major depression|low mood)\b',
    # Neurological — observed in real test PDFs
    r'\b(epilepsy|epileptic|seizure|convulsion|blackout|loss of consciousness)\b',
    r'\b(migraine|headache|cluster headache|tension headache)\b',
    r'\b(stroke|TIA|transient ischaemic|transient ischemic)\b',
    r'\b(neuropathy|multiple sclerosis|Parkinson|tremor)\b',
    # Cardiology
    r'\b(heart failure|cardiac failure|reduced ejection fraction|HFrEF)\b',
    r'\b(atrial fibrillation|AF|arrhythmia|tachycardia|bradycardia|SVT|DVT|PE)\b',
    r'\b(coronary artery|angina|myocardial infarction|heart attack|pacemaker)\b',
    r'\b(hypertension|hypotension|blood pressure|hypertensive)\b',
    r'\b(hypercholesterolaemia|hyperlipidaemia|high cholesterol)\b',
    # Respiratory
    r'\b(asthma|COPD|pneumonia|bronchitis|respiratory tract infection|LRTI|URTI)\b',
    r'\b(dyspnoea|shortness of breath|breathlessness|wheeze|cough)\b',
    # Gastroenterology — observed in real test PDFs
    r'\b(abdominal bloating|bloating|distension)\b',
    r'\b(rectal bleeding|blood in stool|haematochezia|melaena)\b',
    r'\b(epigastric|oesophagitis|esophagitis|gastroesophageal|GORD|GERD)\b',
    r'\b(diarrhoea|diarrhea|constipation|bowel|vomiting|nausea|IBS)\b',
    r'\b(hypophosphataemia|hypophosphatemia|phosphate|electrolyte)\b',
    # Renal / urological
    r'\b(urinary tract infection|UTI|cystitis|pyelonephritis)\b',
    r'\b(chronic kidney disease|CKD|renal failure|eGFR|creatinine)\b',
    r'\b(solitary kidney|nephrectomy|renal calculus|kidney stone)\b',
    r'\b(lower urinary tract|LUTS|urinary retention|prostate|PSA)\b',
    # Oncology
    r'\b(carcinoma|cancer|malignancy|tumour|tumor|lymphoma|leukaemia|leukemia)\b',
    r'\b(bladder cancer|urothelial|transitional cell|renal cell)\b',
    r'\b(pulmonary embol|venous thromboembol|DVT|thrombosis|anticoagul)\b',
    # Endocrine / metabolic
    r'\b(diabetes|diabetic|hyperglycaemia|hypoglycaemia|HbA1c|insulin)\b',
    r'\b(obesity|overweight|BMI|body mass index)\b',
    r'\b(hypothyroid|hyperthyroid|thyroid|thyroxine)\b',
    # Musculoskeletal / skin — observed in real test PDFs
    r'\b(eczema|dermatitis|psoriasis|urticaria|rash|impetigo)\b',
    r'\b(fibromyalgia|chronic pain|myalgia|arthritis|gout|osteoporosis)\b',
    r'\b(fracture|laceration|contusion|haematoma|haemorrhage|hemorrhage)\b',
    # Gynaecology / fertility
    r'\b(endometriosis|fibroids|menorrhagia|dysmenorrhoea|PCOS)\b',
    r'\b(miscarriage|ectopic|recurrent pregnancy loss|subfertility)\b',
    # Common conditions / symptoms
    r'\b(infection|sepsis|cellulitis|abscess|cyanosis|syncope|collapse)\b',
    r'\b(pain|swelling|bleeding|fever|fatigue|nausea|vomiting|dizziness)\b',
    r'\b(anaemia|anemia|haemoglobin|hemoglobin|iron deficiency|ferritin)\b',
    # Procedures / investigations
    r'\b(blood pressure|ECG|MRI|CT scan|ultrasound|echocardiogram|echo)\b',
    r'\b(gastroscopy|colonoscopy|endoscopy|biopsy|laparoscopy|cystoscopy)\b',
    r'\b(haemoglobin|HbA1c|eGFR|creatinine|LFT|FBC|PSA|TSH|INR)\b',
    # Medications
    r'\b(aspirin|paracetamol|ibuprofen|metformin|atenolol|amlodipine|ramipril)\b',
    r'\b(amoxicillin|penicillin|fluoxetine|sertraline|citalopram|warfarin|heparin)\b',
    r'\b(insulin|salbutamol|omeprazole|lansoprazole|methotrexate|prednisolone)\b',
    r'\b(botox|botulinum|levetiracetam|solifenacin|dalteparin|entresto|losartan)\b',
]

# Non-diagnostic / generic words that should never become SNOMED condition codes.
_SNOMED_NON_CONDITION_TERMS = {
    # Administrative / generic
    "treatment", "advice", "consultation", "review", "assessment", "follow-up",
    "follow up", "referral", "service", "doctor", "patient", "outcome", "question",
    "answer", "date", "prescribed", "prescription", "medication", "history",
    # Vital signs / exam status — not diagnoses
    "alert", "oriented", "vitally stable", "stable", "conscious", "coherent",
    "responsive", "cooperative", "combative", "unresponsive", "gcse", "gcs",
    "pulse", "bp", "spo2", "rr", "hr", "temp", "temperature", "o2 sat",
    "blood pressure", "heart rate", "respiratory rate", "oxygen saturation",
    # Neurological exam shorthand
    "a&ox4", "a&ox3", "a+ox4", "a+ox3", "aox4", "aox3",
    # Exam narrative words
    "well", "comfortable", "distressed", "noted", "found", "seen", "reported",
    "appearing", "appears", "presents", "complaint", "complaints", "comments",
    # Generic abbreviations that Comprehend misidentifies
    "pm", "am", "od", "bd", "tds", "qds", "prn", "sos", "nkda", "nka",
    "hx", "fx", "dx", "rx", "sx", "tx", "cx", "e/o", "h/o", "k/c/o",
    # Non-clinical filler
    "nil", "none", "normal", "unremarkable", "nab", "nak", "no", "not",
}

# FALSE POSITIVE SNOMED TERMS - terms that AWS Comprehend incorrectly identifies
# These should NEVER appear in SNOMED output - they are hallucinations or misclassifications
_SNOMED_FALSE_POSITIVE_TERMS = {
    # Anatomy terms (should not be coded as conditions/diagnoses)
    "disc", "disk", "rectum", "colon", "anus", "anal", "sigmoid", "descending",
    "mucosa", "tissue", "skin", "tag", "tags", "anal skin tag", "skin tags",
    # Procedure fragments misidentified as conditions
    "eua", "lrb", "flexible", "sigmoidoscopy", "banding", "excision",
    # Non-specific terms
    "specimen", "specimens", "source", "type", "tests", "collected",
    "priority", "urgent", "routine", "description",
    # Document structure terms
    "diagnosis", "post-op", "pre-op", "instructions", "information",
    "details", "section", "actions", "required", "pending",
}

# SNOMED codes that are false positives (anatomy, procedure fragments)
_SNOMED_FALSE_POSITIVE_CODES = {
    # Anatomy codes - should not appear as diagnoses/problems
    "34402009",   # Rectum structure
    "71854001",   # Colon structure
    "53505006",   # Anal structure
    "60184004",   # Sigmoid colon structure
    "32713005",   # Descending colon structure
    "414781009",  # Mucosa structure
    "39937001",   # Skin structure
    # Procedure fragments
    "73761001",   # Colonoscopy (should be in investigations, not diagnoses)
    "44441009",   # Flexible sigmoidoscopy (should be in treatments/investigations)
    # Non-specific/generic
    "123037004",  # Body structure
    "91723000",   # Anatomical structure
}

def _extract_keywords_from_text(text: str) -> list:
    """Extract candidate clinical terms from text using regex patterns.
    Returns list of unique matched terms (lowercased, deduplicated)."""
    found = {}
    text_lower = text.lower()
    for pattern in _CLINICAL_KEYWORD_PATTERNS:
        for m in _re.finditer(pattern, text_lower, _re.IGNORECASE):
            term = m.group(0).strip()
            if term and len(term) >= 4 and term not in found:
                found[term] = term
    return list(found.values())


def _is_condition_like_entity(entity: dict, top_desc: str = "") -> bool:
    """Accept only clinically meaningful entities: actual conditions, diagnoses, and
    significant symptoms. Filters out exam observations, vital sign notations,
    short abbreviations, and generic status terms.
    """
    cat   = (entity.get("Category", "") or "").upper()
    etype = (entity.get("Type", "") or "").upper()
    traits = {(t.get("Name", "") or "").upper() for t in entity.get("Traits", [])}
    txt   = (entity.get("Text", "") or "").strip().lower()
    desc  = (top_desc or "").strip().lower()
    score = float(entity.get("Score", 0.0))

    # Reject blank or blocklisted terms
    if not txt or txt in _SNOMED_NON_CONDITION_TERMS:
        return False

    # Reject very short text (1-3 chars) — almost always abbreviations or noise
    if len(txt) <= 3:
        return False

    # Reject single ALL-CAPS tokens that are not known clinical acronyms
    _VALID_CLINICAL_ACRONYMS = {
        "copd", "afib", "af", "uti", "dvt", "pe", "mi", "aki", "ckd",
        "chf", "htn", "dm", "ra", "sle", "ms", "hiv", "std", "ptsd",
        "adhd", "ocd", "gord", "gerd", "ibs", "ibd",
    }
    raw_txt = (entity.get("Text", "") or "").strip()
    if raw_txt.isupper() and len(raw_txt) <= 4 and txt not in _VALID_CLINICAL_ACRONYMS:
        return False

    # Reject pure administrative / generic categories
    if any(x in cat for x in ("MEDICATION", "TEST")):
        return False

    # Reject SNOMED descriptions that are pure exam/observation findings (not diagnoses)
    _EXAM_FINDING_DESC_PATTERNS = (
        "mentally alert", "oriented to person", "normal vital", "vital capacity",
        "observable entity", "pM category", "clinical finding (finding)",
        "normal", "finding of",
    )
    _EXAM_FINDING_DESC_EXACT = {
        "mentally alert (finding)",
        "oriented to person, time and place (finding)",
        "normal vital capacity (finding)",
        "pm category (observable entity)",
        "pM category (observable entity)",
    }
    if desc in _EXAM_FINDING_DESC_EXACT:
        return False
    if any(p in desc for p in _EXAM_FINDING_DESC_PATTERNS) and score < 0.85:
        return False

    # PROCEDURE: only allow high-confidence, clinically specific procedures
    _GENERIC_PROCEDURE_TERMS = {
        "evaluation procedure", "patient encounter procedure", "consultation",
        "hospital admission", "patient discharge", "follow-up encounter",
        "referral to service", "emergency department patient visit",
    }
    if "PROCEDURE" in cat or "TREATMENT" in cat:
        if desc in _GENERIC_PROCEDURE_TERMS:
            return False
        if "encounter" in desc:
            return False
        return score >= 0.65

    # ANATOMY: reject unless it is a named clinical finding (e.g. 'solitary kidney')
    if "ANATOMY" in cat:
        return score >= 0.80

    # Keep genuine condition/diagnosis/symptom signals
    if "MEDICAL_CONDITION" in cat or "DIAGNOSIS" in cat:
        return True
    if etype in {"DX_NAME", "DIAGNOSIS", "MEDICAL_CONDITION"}:
        return True
    if "DIAGNOSIS" in traits or "SYMPTOM" in traits or "SIGN" in traits:
        return True
    return False


def _snomed_lookup_term(term: str, client, base_conf: float = 0.6) -> dict | None:
    """Call infer_snomedct on a single clinical term. Returns entry dict or None."""
    try:
        sr = client.infer_snomedct(Text=term)
        sr_entities = sr.get("Entities", [])
        if not sr_entities:
            return None
        se = sr_entities[0]
        concepts = se.get("SNOMEDCTConcepts", [])
        if not concepts:
            return None
        code = concepts[0].get("Code", "")
        if not code:
            return None
        if not _is_condition_like_entity(se, concepts[0].get("Description", "")):
            return None
        conf = round(base_conf * se.get("Score", 0.5), 3)
        cat  = se.get("Category", "MEDICAL_CONDITION")
        return {
            "text":        term,
            "category":    cat,
            "snomed_code": code,
            "description": concepts[0].get("Description", ""),
            "confidence":  conf,
            "entity_id":   str(uuid.uuid4())[:8],
            "source":      "term_extraction",
        }
    except Exception:
        return None


def _snomed_term_fallback(text: str, client) -> list:
    """SRS §3.2 semantic fallback: when InferSNOMEDCT returns 0 entities on the full
    document text, extract individual clinical terms via two methods and map each to SNOMED.

    Fixed based on real clinical data analysis:
    - Previously returned only top-3: missed secondary conditions (e.g. autism + learning
      disability + trisomy 21 all present in same document)
    - Previously capped collection at 8: too low for multi-condition documents
    - Now collects up to 20 candidates and returns top-6 ranked by confidence
    - Method A threshold lowered from 0.15 to 0.10 to catch sparse/scanned documents
    - Method A candidate pool increased from 10 to 20
    """
    results, seen_codes, seen_terms = [], set(), set()

    # ── Method A: detect_entities_v2 with lowered threshold ────────────────────
    try:
        resp = client.detect_entities_v2(Text=text[:10000])
        raw  = resp.get("Entities", [])
    except Exception:
        raw = []

    # Broader type set: include PROTECTED_HEALTH_INFORMATION only if clinical
    CLINICAL_TYPES = {"DX_NAME", "MEDICAL_CONDITION", "SIGN", "SYMPTOM", "DIAGNOSIS"}
    method_a = sorted(
        [e for e in raw if e.get("Type") in CLINICAL_TYPES and e.get("Score", 0) > 0.10],
        key=lambda x: x.get("Score", 0), reverse=True
    )[:20]  # increased from 10 → 20 to catch all conditions in multi-problem documents

    for entity in method_a:
        term = entity.get("Text", "").strip()
        term_lower = term.lower()
        if (
            not term
            or len(term) < 3
            or term_lower in seen_terms
            or term_lower in _SNOMED_NON_CONDITION_TERMS
        ):
            continue
        seen_terms.add(term_lower)
        entry = _snomed_lookup_term(term, client, base_conf=entity.get("Score", 0.5))
        if entry and entry["snomed_code"] not in seen_codes:
            seen_codes.add(entry["snomed_code"])
            results.append(entry)

    # ── Method B: regex keyword extraction (fills gap when Method A finds nothing) ──
    # Always run Method B regardless of Method A results to catch domain terms
    # Comprehend misses (e.g. 'downs syndrome', 'trisomy 21', 'botox', 'migraine')
    keywords = _extract_keywords_from_text(text)
    for kw in keywords:
        if len(results) >= 20:  # raised from 8 → 20
            break
        if kw in seen_terms or kw in seen_codes:
            continue
        seen_terms.add(kw)
        entry = _snomed_lookup_term(kw, client, base_conf=0.60)
        if entry and entry["snomed_code"] not in seen_codes:
            seen_codes.add(entry["snomed_code"])
            results.append(entry)

    results.sort(key=lambda x: x["confidence"], reverse=True)
    return results[:6]  # increased from 3 → 6: captures all significant + minor conditions


# ── Guaranteed SNOMED codes by document type (absolute last resort) ────────────
# Every document type maps to 3 clinically appropriate SNOMED CT codes.
# Used only when all AWS Comprehend paths return nothing (very sparse text/OCR failure).
_DOCTYPE_SNOMED_CODES: dict = {
    "Antenatal Discharge Summary": [
        {"text": "Antenatal care",    "category": "MEDICAL_CONDITION", "snomed_code": "134435003", "description": "Routine antenatal care (procedure)",        "confidence": 0.82, "entity_id": "dt-1", "source": "document_type"},
        {"text": "Normal pregnancy",  "category": "MEDICAL_CONDITION", "snomed_code": "72892002",  "description": "Normal pregnancy",                           "confidence": 0.80, "entity_id": "dt-2", "source": "document_type"},
        {"text": "Patient discharge", "category": "PROCEDURE",         "snomed_code": "58000006",  "description": "Patient discharge (procedure)",               "confidence": 0.75, "entity_id": "dt-3", "source": "document_type"},
    ],
    "Discharge Summary": [
        {"text": "Patient discharge",     "category": "PROCEDURE",         "snomed_code": "58000006",  "description": "Patient discharge (procedure)",           "confidence": 0.82, "entity_id": "dt-1", "source": "document_type"},
        {"text": "Inpatient admission",   "category": "PROCEDURE",         "snomed_code": "32485007",  "description": "Hospital admission (procedure)",          "confidence": 0.78, "entity_id": "dt-2", "source": "document_type"},
        {"text": "Clinical assessment",   "category": "PROCEDURE",         "snomed_code": "386053000", "description": "Evaluation procedure (procedure)",        "confidence": 0.74, "entity_id": "dt-3", "source": "document_type"},
    ],
    "Referral Letter": [
        {"text": "Referral to specialist", "category": "PROCEDURE",        "snomed_code": "306206005", "description": "Referral to service (procedure)",         "confidence": 0.82, "entity_id": "dt-1", "source": "document_type"},
        {"text": "Clinical assessment",    "category": "PROCEDURE",        "snomed_code": "386053000", "description": "Evaluation procedure (procedure)",        "confidence": 0.77, "entity_id": "dt-2", "source": "document_type"},
        {"text": "Follow-up care",         "category": "PROCEDURE",        "snomed_code": "394700006", "description": "Follow-up encounter (procedure)",         "confidence": 0.73, "entity_id": "dt-3", "source": "document_type"},
    ],
    "Outpatient Letter": [
        {"text": "Outpatient consultation","category": "PROCEDURE",        "snomed_code": "11429006",  "description": "Consultation (procedure)",                 "confidence": 0.82, "entity_id": "dt-1", "source": "document_type"},
        {"text": "Clinical review",        "category": "PROCEDURE",        "snomed_code": "394700006", "description": "Follow-up encounter (procedure)",         "confidence": 0.77, "entity_id": "dt-2", "source": "document_type"},
        {"text": "Medical history",        "category": "MEDICAL_CONDITION","snomed_code": "392521001", "description": "Review of systems (procedure)",           "confidence": 0.72, "entity_id": "dt-3", "source": "document_type"},
    ],
    "Ambulance Clinical Report": [
        {"text": "Emergency ambulance",    "category": "PROCEDURE",        "snomed_code": "409971007", "description": "Emergency ambulance transport (procedure)","confidence": 0.85, "entity_id": "dt-1", "source": "document_type"},
        {"text": "Clinical assessment",    "category": "PROCEDURE",        "snomed_code": "386053000", "description": "Evaluation procedure (procedure)",         "confidence": 0.80, "entity_id": "dt-2", "source": "document_type"},
        {"text": "Patient handover",       "category": "PROCEDURE",        "snomed_code": "397943006", "description": "Clinical handover (procedure)",            "confidence": 0.74, "entity_id": "dt-3", "source": "document_type"},
    ],
    "111 First ED Report": [
        {"text": "Emergency assessment",   "category": "PROCEDURE",        "snomed_code": "50849002",  "description": "Emergency department patient visit",       "confidence": 0.84, "entity_id": "dt-1", "source": "document_type"},
        {"text": "Triage assessment",      "category": "PROCEDURE",        "snomed_code": "386053000", "description": "Evaluation procedure (procedure)",         "confidence": 0.79, "entity_id": "dt-2", "source": "document_type"},
        {"text": "Urgent care",            "category": "PROCEDURE",        "snomed_code": "182813001", "description": "Emergency treatment (procedure)",          "confidence": 0.74, "entity_id": "dt-3", "source": "document_type"},
    ],
    "Ophthalmology Referral": [
        {"text": "Eye examination",        "category": "PROCEDURE",        "snomed_code": "36228007",  "description": "Ophthalmic examination and evaluation",    "confidence": 0.83, "entity_id": "dt-1", "source": "document_type"},
        {"text": "Referral to specialist", "category": "PROCEDURE",        "snomed_code": "306206005", "description": "Referral to service (procedure)",          "confidence": 0.78, "entity_id": "dt-2", "source": "document_type"},
        {"text": "Visual assessment",      "category": "PROCEDURE",        "snomed_code": "281004",    "description": "Examination of visual field",              "confidence": 0.73, "entity_id": "dt-3", "source": "document_type"},
    ],
    "Cardiology": [
        {"text": "Cardiac assessment",     "category": "PROCEDURE",        "snomed_code": "180256009", "description": "Cardiological investigation (procedure)",  "confidence": 0.83, "entity_id": "dt-1", "source": "document_type"},
        {"text": "ECG",                    "category": "PROCEDURE",        "snomed_code": "29303009",  "description": "Electrocardiographic procedure",            "confidence": 0.80, "entity_id": "dt-2", "source": "document_type"},
        {"text": "Heart disease",          "category": "MEDICAL_CONDITION","snomed_code": "56265001",  "description": "Heart disease",                            "confidence": 0.74, "entity_id": "dt-3", "source": "document_type"},
    ],
    # Generic fallback used when letter_type is unknown
    "_default": [
        {"text": "Clinical assessment",    "category": "PROCEDURE",        "snomed_code": "386053000", "description": "Evaluation procedure (procedure)",         "confidence": 0.70, "entity_id": "dt-1", "source": "document_type"},
        {"text": "Medical consultation",   "category": "PROCEDURE",        "snomed_code": "11429006",  "description": "Consultation (procedure)",                 "confidence": 0.68, "entity_id": "dt-2", "source": "document_type"},
        {"text": "Healthcare encounter",   "category": "PROCEDURE",        "snomed_code": "308335008", "description": "Patient encounter procedure",              "confidence": 0.65, "entity_id": "dt-3", "source": "document_type"},
    ],
}

def _get_doctype_snomed_codes(letter_type: str) -> list:
    """Return guaranteed SNOMED codes for a given document type.
    Falls back to _default if the type is not in the table.
    Each entry has a unique entity_id so the JS renderer treats them correctly.
    """
    import uuid as _uuid_mod
    base = _DOCTYPE_SNOMED_CODES.get(letter_type) or _DOCTYPE_SNOMED_CODES.get("_default", [])
    # Assign fresh entity_ids so they are unique per document
    return [{**e, "entity_id": str(_uuid_mod.uuid4())[:8]} for e in base]


def _categorize_snomed_entity(entity: dict, description: str, traits: list) -> str:
    """Categorize SNOMED entity into one of 5 clinical categories:
    - problems: Symptoms, findings, conditions (e.g., neck pain, tummy irritation)
    - treatments: Therapeutic procedures (e.g., Mental Health treatment, Chemo)
    - medications: Drugs and substances (e.g., Thyroxine, Aspirin)
    - investigations: Diagnostic tests (e.g., CT Scan, MRI, Smear, Angio)
    - diagnoses: Confirmed conditions (e.g., ulcerative colitis)
    """
    desc_lower = description.lower()
    text_lower = entity.get("Text", "").lower()
    category = entity.get("Category", "").upper()
    entity_type = entity.get("Type", "").upper()

    # Check traits for DIAGNOSIS marker
    trait_names = [t.get("Name", "").upper() for t in traits]
    if "DIAGNOSIS" in trait_names:
        return "diagnoses"

    # Category-based classification from Comprehend Medical
    if category in ("MEDICATION", "GENERIC_NAME", "BRAND_NAME"):
        return "medications"
    if category == "TEST_NAME" or entity_type == "TEST_NAME":
        return "investigations"
    if category == "PROCEDURE_NAME" or entity_type == "PROCEDURE_NAME":
        # Distinguish treatment procedures from diagnostic procedures
        if any(x in desc_lower for x in ["imaging", "scan", "x-ray", "xray", "radiograph",
                                          "angiograph", "endoscop", "colonoscop", "gastroscop",
                                          "mammograph", "ultrasound", "mri", "ct ", "pet ",
                                          "biopsy", "smear", "blood test", "urine test",
                                          "ecg", "ekg", "echocardiog", "spirometr"]):
            return "investigations"
        return "treatments"
    if category == "TREATMENT_NAME" or entity_type == "TREATMENT_NAME":
        return "treatments"

    # SNOMED description-based classification (from semantic tag in parentheses)
    if "(procedure)" in desc_lower:
        # Check if it's a diagnostic/investigative procedure
        if any(x in desc_lower for x in ["imaging", "scan", "radiograph", "endoscop",
                                          "examination", "measurement", "test", "biopsy",
                                          "assessment", "screening", "angiograph"]):
            return "investigations"
        # Check if it's a therapeutic procedure
        if any(x in desc_lower for x in ["therapy", "treatment", "chemotherapy", "radiotherapy",
                                          "surgery", "surgical", "repair", "removal", "excision",
                                          "transplant", "infusion", "injection", "counseling",
                                          "rehabilitation", "physiotherapy"]):
            return "treatments"
        return "treatments"  # Default procedures to treatments

    if "(substance)" in desc_lower or "(product)" in desc_lower:
        return "medications"

    # Text-based classification for common patterns
    # Investigations (diagnostic procedures and tests)
    if any(x in text_lower for x in ["ct ", "ct scan", "mri", "x-ray", "xray", "ultrasound",
                                      "blood test", "urine test", "ecg", "ekg", "angio",
                                      "colonoscopy", "endoscopy", "biopsy", "smear",
                                      "mammogram", "pet scan", "bone scan", "histology",
                                      "tissue", "sigmoidoscopy", "gastroscopy", "cystoscopy",
                                      "bronchoscopy", "laparoscopy", "arthroscopy"]):
        return "investigations"

    # Treatments (therapeutic procedures)
    if any(x in text_lower for x in ["chemotherapy", "radiotherapy", "therapy", "treatment",
                                      "surgery", "physiotherapy", "counseling", "rehabilitation",
                                      "injection", "excision", "removal", "repair", "banding",
                                      "phenol", "sclerotherapy", "ablation", "resection"]):
        return "treatments"

    # Medications (common drug patterns)
    if any(x in text_lower for x in ["mg", "mcg", "ml", "tablet", "capsule", "injection",
                                      "aspirin", "paracetamol", "ibuprofen", "metformin"]):
        return "medications"

    # Symptoms/findings go to problems
    if "SYMPTOM" in trait_names or "SIGN" in trait_names:
        return "problems"
    if "(finding)" in desc_lower or "(disorder)" in desc_lower or "(situation)" in desc_lower:
        return "problems"

    # Inflammation findings should be problems (not anatomy)
    if any(x in text_lower for x in ["inflamed", "inflammation", "inflam", "colitis", "itis"]):
        return "problems"

    # Default to problems for unclassified medical conditions
    return "problems"


def run_comprehend_medical(text: str) -> dict:
    """Run SNOMED mapping via Comprehend Medical with 5-category classification.

    Categories (as requested):
    - problems: Symptoms, issues (e.g., neck pain, tummy irritation) with SNOMED
    - treatments: Therapeutic procedures (e.g., Mental Health treatment, Chemo) with SNOMED
    - medications: Drugs (e.g., Thyroxine, Aspirin) with SNOMED
    - investigations: Diagnostic tests (e.g., CT Scan, MRI, Smear, Angio) with SNOMED
    - diagnoses: Confirmed conditions (e.g., ulcerative colitis) with SNOMED

    Primary path: InferSNOMEDCT on full document text.
    Fallback path: detect_entities_v2 → per-term InferSNOMEDCT → top results.
    """
    client = make_client("comprehendmedical")

    # Initialize 5 category buckets
    problems, treatments, medications, investigations, diagnoses = [], [], [], [], []
    all_entities = []
    seen_codes = set()

    # ── Primary: InferSNOMEDCT for SNOMED codes ──
    try:
        resp = client.infer_snomedct(Text=text[:10000])
        snomed_entities = resp.get("Entities", [])
    except Exception as e:
        import sys
        print(f"[WARN] InferSNOMEDCT failed: {e}", file=sys.stderr)
        snomed_entities = []

    for e in snomed_entities:
        concepts = e.get("SNOMEDCTConcepts", [])
        # Get the highest-scoring SNOMED concept
        if concepts:
            top = max(concepts, key=lambda c: c.get("Score", 0))
        else:
            continue
        code = top.get("Code", "")
        if not code or code in seen_codes:
            continue

        # FALSE POSITIVE FILTERING - remove hallucinated/anatomy codes
        text_val = e.get("Text", "").strip()
        text_lower = text_val.lower()
        if text_lower in _SNOMED_FALSE_POSITIVE_TERMS:
            continue
        if code in _SNOMED_FALSE_POSITIVE_CODES:
            continue
        # Filter anatomy-only descriptions (structure, body part without pathology)
        description = top.get("Description", "")
        desc_lower = description.lower()
        if "(body structure)" in desc_lower or "structure of" in desc_lower:
            continue
        if desc_lower.endswith("structure") and "disorder" not in desc_lower:
            continue

        seen_codes.add(code)

        score = float(top.get("Score", e.get("Score", 0)))
        traits = e.get("Traits", [])

        entry = {
            "text":        text_val,
            "category":    e.get("Category", ""),
            "snomed_code": code,
            "description": description,
            "confidence":  round(score, 3),
            "entity_id":   str(uuid.uuid4())[:8],
            "source":      "comprehend_snomed",
        }

        # Categorize into 5 buckets
        bucket = _categorize_snomed_entity(e, description, traits)
        entry["clinical_category"] = bucket

        if bucket == "problems":
            problems.append(entry)
        elif bucket == "treatments":
            treatments.append(entry)
        elif bucket == "medications":
            medications.append(entry)
        elif bucket == "investigations":
            investigations.append(entry)
        elif bucket == "diagnoses":
            diagnoses.append(entry)

        all_entities.append(entry)

    # ── Secondary: detect_entities_v2 for medications ──
    try:
        resp_v2 = client.detect_entities_v2(Text=text[:10000])
        v2_entities = resp_v2.get("Entities", [])
    except Exception:
        v2_entities = []

    for e in v2_entities:
        entity_type = e.get("Type", "").upper()
        category = e.get("Category", "").upper()
        text_val = e.get("Text", "").strip()

        if not text_val or len(text_val) < 2:
            continue

        # Only process medication entities not already captured
        if category == "MEDICATION" or entity_type in ("GENERIC_NAME", "BRAND_NAME"):
            # Try to get SNOMED code for this medication
            try:
                med_resp = client.infer_snomedct(Text=text_val)
                med_entities = med_resp.get("Entities", [])
                if med_entities:
                    med_concepts = med_entities[0].get("SNOMEDCTConcepts", [])
                    if med_concepts:
                        top_med = max(med_concepts, key=lambda c: c.get("Score", 0))
                        code = top_med.get("Code", "")
                        if code and code not in seen_codes:
                            seen_codes.add(code)
                            entry = {
                                "text":        text_val,
                                "category":    "MEDICATION",
                                "snomed_code": code,
                                "description": top_med.get("Description", ""),
                                "confidence":  round(float(top_med.get("Score", e.get("Score", 0.7))), 3),
                                "entity_id":   str(uuid.uuid4())[:8],
                                "source":      "comprehend_medication",
                                "clinical_category": "medications",
                            }
                            medications.append(entry)
                            all_entities.append(entry)
            except Exception:
                pass

        # Also capture TEST_NAME entities as investigations
        elif category == "TEST_TREATMENT_PROCEDURE" and entity_type == "TEST_NAME":
            try:
                test_resp = client.infer_snomedct(Text=text_val)
                test_entities = test_resp.get("Entities", [])
                if test_entities:
                    test_concepts = test_entities[0].get("SNOMEDCTConcepts", [])
                    if test_concepts:
                        top_test = max(test_concepts, key=lambda c: c.get("Score", 0))
                        code = top_test.get("Code", "")
                        if code and code not in seen_codes:
                            seen_codes.add(code)
                            entry = {
                                "text":        text_val,
                                "category":    "TEST_NAME",
                                "snomed_code": code,
                                "description": top_test.get("Description", ""),
                                "confidence":  round(float(top_test.get("Score", e.get("Score", 0.7))), 3),
                                "entity_id":   str(uuid.uuid4())[:8],
                                "source":      "comprehend_investigation",
                                "clinical_category": "investigations",
                            }
                            investigations.append(entry)
                            all_entities.append(entry)
            except Exception:
                pass

    # ── Fallback: term-by-term extraction when nothing found ──
    used_fallback = False
    top3_fallback: list = []
    if not all_entities:
        top3_fallback = _snomed_term_fallback(text, client)
        used_fallback = bool(top3_fallback)
        for entry in top3_fallback:
            desc = entry.get("description", "")
            cat = entry.get("category", "").upper()

            # Classify fallback entries
            if "MEDICATION" in cat or "(substance)" in desc.lower() or "(product)" in desc.lower():
                entry["clinical_category"] = "medications"
                medications.append(entry)
            elif "(procedure)" in desc.lower():
                if any(x in desc.lower() for x in ["scan", "imaging", "test", "examination"]):
                    entry["clinical_category"] = "investigations"
                    investigations.append(entry)
                else:
                    entry["clinical_category"] = "treatments"
                    treatments.append(entry)
            elif "DIAGNOSIS" in cat or "(disorder)" in desc.lower():
                entry["clinical_category"] = "diagnoses"
                diagnoses.append(entry)
            else:
                entry["clinical_category"] = "problems"
                problems.append(entry)
            all_entities.append(entry)

    # ── Clinical Engine Validation (when available) ──────────────────────────────
    # Apply context-aware validation to remove false positives
    validation_warnings = []
    if _HAS_CLINICAL_ENGINE:
        try:
            validator = ClinicalValidationEngine()

            # Validate each category
            def validate_bucket(bucket: list, category_name: str) -> list:
                validated = []
                for entity in bucket:
                    # Quick validation checks
                    text_lower = entity.get("text", "").lower()
                    snomed_code = entity.get("snomed_code", "")
                    snomed_desc = entity.get("description", "")

                    # Check anatomy blocklist
                    if text_lower in validator.ANATOMY_BLOCKLIST:
                        continue
                    if snomed_code in validator.ANATOMY_SNOMED_CODES:
                        continue
                    if snomed_code in validator.PROCEDURE_SNOMED_CODES and category_name == "diagnoses":
                        continue
                    if snomed_desc and "(body structure)" in snomed_desc.lower():
                        continue

                    validated.append(entity)
                return validated

            # Apply validation
            diagnoses = validate_bucket(diagnoses, "diagnoses")
            problems = validate_bucket(problems, "problems")
            treatments = validate_bucket(treatments, "treatments")
            investigations = validate_bucket(investigations, "investigations")

            # Rebuild all_entities
            all_entities = diagnoses + problems + treatments + medications + investigations

            import sys
            print(f"[DEBUG] Clinical validation applied: "
                  f"diagnoses={len(diagnoses)}, problems={len(problems)}, treatments={len(treatments)}, "
                  f"medications={len(medications)}, investigations={len(investigations)}",
                  file=sys.stderr)

        except Exception as e:
            import sys
            print(f"[WARN] Clinical validation failed: {e}", file=sys.stderr)
            validation_warnings.append(f"Clinical validation error: {e}")

    # Calculate confidence
    if all_entities:
        snomed_conf = sum(e.get("confidence", 0) for e in all_entities) / len(all_entities)
    else:
        snomed_conf = 0.3

    # Sort each bucket by confidence (highest first)
    for bucket in [problems, treatments, medications, investigations, diagnoses]:
        bucket.sort(key=lambda x: x.get("confidence", 0), reverse=True)

    import sys
    print(f"[DEBUG] SNOMED extraction: problems={len(problems)}, treatments={len(treatments)}, "
          f"medications={len(medications)}, investigations={len(investigations)}, diagnoses={len(diagnoses)}",
          file=sys.stderr)

    return {
        "entities":              snomed_entities,
        "all_entities":          all_entities,
        "problems":              problems,
        "treatments":            treatments,
        "medications":           medications,
        "investigations":        investigations,
        "diagnoses":             diagnoses,
        "snomed_confidence":     round(snomed_conf, 3),
        "used_fallback":         used_fallback,
        "top3_fallback":         top3_fallback,
        "validation_warnings":   validation_warnings,
    }


def _rewrite_summary_without_age(summary_text: str, patient_sex: str = "") -> str:
    """Remove demographics/identifiers from summary and keep concise clinical content."""
    import re as _re
    txt = (summary_text or "").strip()
    if not txt:
        return txt

    # Remove common age mentions.
    txt = _re.sub(r'\b\d{1,3}\s*[- ]?\s*year\s*[- ]?\s*old\b', '', txt, flags=_re.IGNORECASE)
    txt = _re.sub(r'\bage\s*(?:of)?\s*\d{1,3}\b', '', txt, flags=_re.IGNORECASE)
    txt = _re.sub(r'\baged\s*\d{1,3}\b', '', txt, flags=_re.IGNORECASE)
    txt = _re.sub(r'\b\d{1,3}\s*(?:yo|y/o)\b', '', txt, flags=_re.IGNORECASE)
    txt = _re.sub(r'\b\d{1,3}\s*[mMfF]\b', '', txt)  # e.g. 29M / 52F
    txt = _re.sub(r'\(\s*\d{1,3}\s*\)', '', txt)

    # Remove direct identifiers and demographic labels from generated summary text.
    txt = _re.sub(r'(?i)\bNHS\s*(?:No|Number|#)?[:\s]*\d[\d\s]{8,14}\d\b', '', txt)
    txt = _re.sub(r'(?i)\b(?:DOB|D\.?\s*O\.?\s*B\.?|Date\s*of\s*birth)\b[:\s-]*[^\.,;\n]*', '', txt)
    txt = _re.sub(r'(?i)\b(?:Patient\s*Name|Name|Address|Hospital\s*Number|MRN)\b[:\s-]*[^\.,;\n]*', '', txt)
    txt = _re.sub(r'(?i)\b(?:Mr|Mrs|Ms|Miss|Dr)\.?\s+[A-Z][A-Za-z\'\-]+(?:\s+[A-Z][A-Za-z\'\-]+){0,2}\b', 'patient', txt)
    txt = _re.sub(r'(?i)\bsex[:\s-]*(?:male|female|m|f)\b', '', txt)

    txt = _re.sub(r'\s{2,}', ' ', txt).strip(" ,.-")

    sex = (patient_sex or "").strip().lower()
    if sex in ("m", "male"):
        label = "male patient"
    elif sex in ("f", "female"):
        label = "female patient"
    else:
        label = "patient"

    # Ensure first phrase is a single demographic subject, never duplicated.
    txt = _re.sub(r'(?i)^(the\s+)?(male|female)\s+patient\b', r'\2 patient', txt).strip()
    if txt and not _re.match(r'(?i)^(male|female)\s+patient\b', txt):
        txt = _re.sub(r'(?i)^(the\s+)?patient\b', label, txt, count=1)
        if not _re.match(r'(?i)^(male|female)\s+patient\b', txt):
            txt = f"{label.capitalize()} {txt[0].lower() + txt[1:]}" if txt else label.capitalize()
    # Collapse accidental double subjects if model returned one and we prepended one.
    txt = _re.sub(r'(?i)^(male|female)\s+patient\s+(?:the\s+)?\1\s+patient\b', r'\1 patient', txt).strip()

    return txt.strip()


def run_bedrock_summarization(text: str, snomed_data: dict, letter_type: str = "", patient_sex: str = "") -> dict:
    """Generate role-based summaries via Claude on Bedrock, tailored per document type."""
    client = make_client("bedrock-runtime")
    MODEL  = "arn:aws:bedrock:eu-west-2:654654155641:inference-profile/eu.anthropic.claude-sonnet-5"

    problems  = [e["text"] for e in snomed_data.get("problems", [])]
    meds      = [e["text"] for e in snomed_data.get("medications", [])]
    diagnoses = [e["text"] for e in snomed_data.get("diagnoses", [])]

    # OBS-006: Expert Health Q&A documents have clinical content only on page 1.
    # Pages 2-5 contain lifestyle education Q&A that would dilute the clinical summary.
    # Limit Bedrock input to 1500 chars for this type to ensure page-1-only extraction.
    text_for_llm = text[:1500] if "Prescriber" in letter_type else text[:4000]

    # OBS-007: Detect sensitive/safeguarding content to apply protective patient summary rules.
    is_sensitive = contains_sensitive_content(text)

    context = f"""Document type: {letter_type}

Clinical document text:
{text_for_llm}

Extracted clinical entities:
- Problems/Findings: {', '.join(problems) or 'None identified'}
- Medications: {', '.join(meds) or 'None identified'}
- Diagnoses: {', '.join(diagnoses) or 'None identified'}"""

    def call_claude(prompt: str, max_tokens: int = 150) -> str:
        # Explicit no-markdown system instruction prepended to every prompt.
        # Claude on Bedrock respects this reliably when placed at the start.
        system_instruction = (
            "You are a clinical documentation assistant writing terse NHS GP-handover summaries. "
            "STRICT RULES: "
            "1. Plain text ONLY — no markdown, no bullet points, no numbered lists, no bold, no headers. "
            "2. Maximum 2 sentences. Maximum 40 words TOTAL. Stop writing after 40 words. "
            "3. Use clinical shorthand: abbreviate freely (T1DM, PRP, HTN, OD, BD, DOB, Hb, BP etc.). "
            "4. Content = encounter type + key diagnosis/findings + key clinical values ONLY. "
            "5. DO NOT include: follow-up plans, next appointments, referrals, GP actions, patient advice, or management plans. "
            "   Those are handled by separate tabs — keep them OUT of this summary. "
            "6. Only include values, dates, names that appear verbatim in the source text. "
            "Example: 'Ophthalmology review T1DM. Bilateral proliferative diabetic retinopathy; PRP completed June 2025; HbA1c 8.2% Dec 2025; neuropathy noted; insulin pump discussed.'"
        )
        clean_prompt = system_instruction + "\n\n" + prompt
        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": clean_prompt}]
        })
        resp = client.invoke_model(modelId=MODEL, body=body, contentType="application/json")
        resp_body = json.loads(resp["body"].read())
        # Handle different response formats
        if "content" in resp_body and resp_body["content"]:
            raw = resp_body["content"][0].get("text", "").strip()
        elif "completion" in resp_body:
            raw = resp_body["completion"].strip()
        else:
            raw = str(resp_body).strip()
        # Belt-and-suspenders: strip any residual markdown Claude ignored
        import re as _re
        clean = _re.sub(r'\*{1,2}([^*\n]+)\*{1,2}', r'\1', raw)  # **bold** / *italic*
        clean = _re.sub(r'^#{1,3}\s+', '', clean, flags=_re.MULTILINE)  # ## headers
        clean = _re.sub(r'^[-–—]{3,}\s*$', '', clean, flags=_re.MULTILINE)  # --- dividers
        clean = clean.strip()
        # Hard word-count safety net: clip at 45 words, re-terminate at last sentence end
        _words = clean.split()
        if len(_words) > 45:
            _truncated = ' '.join(_words[:55])
            # Try to end at a clean sentence boundary
            for _end_char in ['.', '!', '?']:
                _last = _truncated.rfind(_end_char)
                if _last > len(_truncated) // 2:  # only if boundary is in 2nd half
                    _truncated = _truncated[:_last + 1]
                    break
            clean = _truncated
        return clean

    # ── Type-specific clinician prompt ─────────────────────────────────────────
    demo_guard = (
        " Use 'male patient' or 'female patient' where relevant. "
        "Do NOT mention exact age or year-old wording. "
        "Do NOT include patient identifiers: name, DOB/date of birth, NHS number, address, or hospital number."
    )

    if "111" in letter_type:
        clin_prompt = (f"{context}\n\nThis is a 111 First ED triage report. Write a clinical handover summary (3-4 sentences) "
                       "covering: presenting complaint, differential diagnosis, acuity, treatment given, and disposition/referral decision."
                       + demo_guard)
    elif "Cancer" in letter_type:
        clin_prompt = (f"{context}\n\nThis is a cancer surveillance clinic letter. Summarise: cancer type and staging, "
                       "previous treatment, current surveillance findings, next steps and surveillance schedule. Be oncology-precise.")
    elif "HIV" in letter_type or "GUM" in letter_type:
        clin_prompt = (f"{context}\n\nThis is an HIV/GUM clinic letter. Summarise: HIV status, CD4/viral load, "
                       "ART regimen changes, comorbidities addressed, and follow-up plan.")
    elif "Maternity" in letter_type:
        clin_prompt = (f"{context}\n\nThis is a maternity/diabetes letter. Summarise: gestational diabetes status, "
                       "OGTT results, monitoring plan, equipment prescribed, and GP actions needed.")
    elif "Psychiatric" in letter_type or "Psychiatry" in letter_type:
        clin_prompt = (f"{context}\n\nThis is a psychiatry outpatient letter. Summarise: diagnoses (with ICD codes), "
                       "current medications and recent changes, clinical progress, and next review.")
    elif "Procedure" in letter_type:
        clin_prompt = (f"{context}\n\nThis is a procedure/endoscopy report. Summarise: indication, key findings, "
                       "impression, biopsy/sampling if done, and recommendations.")
    elif "Surgical" in letter_type:
        clin_prompt = (f"{context}\n\nThis is a pre-operative surgical outpatient letter. Summarise: diagnosis, "
                       "planned procedure, risks discussed, and GP actions required.")
    elif "Mental Health Inpatient" in letter_type:
        clin_prompt = (f"{context}\n\nThis is a mental health inpatient discharge summary. Summarise: "
                       "admission circumstances (including any MHA section), primary diagnosis, "
                       "clinical progress on ward, medications at discharge, and community follow-up plan "
                       "(CRHTT/CMHT). Note any medication monitoring requirements (e.g. lithium levels).")
    elif "Ophthalmology Referral" in letter_type:
        clin_prompt = (f"{context}\n\nThis is an ophthalmology referral letter (via Evolutio/eRefer). Summarise: "
                       "referral reason and pathway, priority (routine/urgent), optometrist findings, "
                       "visual acuity and IOP if recorded, and which provider the patient is being referred to.")
    elif "Ophthalmology" in letter_type:
        clin_prompt = (f"{context}\n\nThis is an ophthalmology outpatient/medical retina clinic letter. Summarise: "
                       "diagnosis (with retinopathy grading e.g. R2M1P0), key findings per eye (VA, IOP, fundoscopy), "
                       "treatment given or planned (PRP, laser, injection), and follow-up interval. "
                       "Note any urgent actions required.")
    elif "Renal" in letter_type or "Nephrology" in letter_type:
        clin_prompt = (f"{context}\n\nThis is a renal/nephrology remote monitoring letter. Summarise: "
                       "current kidney function (eGFR, creatinine, albumin), trends vs previous, "
                       "any treatment changes required, and next review/test date.")
    elif "Paediatric Cardiology" in letter_type:
        clin_prompt = (f"{context}\n\nThis is a paediatric cardiology outpatient letter. Summarise: "
                       "cardiac diagnosis, current symptoms on/off medication, medication changes, "
                       "planned investigations or procedures (e.g. ablation, EP MDT), and follow-up plan.")
    elif "Early Pregnancy" in letter_type or "Gynaecology" in letter_type:
        clin_prompt = (f"{context}\n\nWrite a CONCISE clinical summary (2-3 sentences ONLY). "
                       "Include: presenting complaint, scan findings, diagnosis, next steps. Be brief.")
    elif "Antenatal Discharge" in letter_type:
        clin_prompt = (f"{context}\n\nWrite a CONCISE clinical summary (2-3 sentences ONLY). "
                       "Include: admission reason, gestational age, key findings, discharge plan. Be brief.")
    elif "Pre-admission" in letter_type:
        clin_prompt = (f"{context}\n\nThis is a pre-admission/surgical booking letter. Summarise: "
                       "scheduled procedure, date, speciality, clinician, and key pre-operative instructions "
                       "for the patient (fasting, medication, transport).")
    elif "Discharge" in letter_type:
        clin_prompt = (f"{context}\n\nWrite a CONCISE clinical summary (2-3 sentences ONLY). "
                       "Include: admission reason, diagnosis, procedures performed, discharge condition. Be brief.")
    elif "ADHD" in letter_type or "Neurodevelopmental" in letter_type:
        clin_prompt = (f"{context}\n\nThis is an ADHD/neurodevelopmental assessment letter. "
                       "Summarise (max 4 sentences, max 70 words): assessment date, whether DSM-5 criteria for ADHD were met, "
                       "alternative diagnosis reached, informant report findings, outcome (discharged/referred), and any DVLA advice."
                       + demo_guard)
    elif "Urology" in letter_type:
        clin_prompt = (f"{context}\n\nThis is a urology outpatient letter. "
                       "Summarise (max 4 sentences, max 70 words): PSA value and trend, imaging findings (mpMRI/PI-RADS if present), "
                       "clinical decision (biopsy/monitoring), new medications with dose, and follow-up plan with timeframe."
                       + demo_guard)
    elif "Dermatology" in letter_type:
        clin_prompt = (f"{context}\n\nThis is a dermatology clinic letter. "
                       "Summarise (max 4 sentences, max 70 words): diagnosis, investigations done or planned (patch testing, bloods), "
                       "treatments prescribed (creams/emollients with names), and follow-up appointments."
                       + demo_guard)
    elif "CTPLD" in letter_type or "Community Psychiatry" in letter_type:
        clin_prompt = (f"{context}\n\nThis is a CTPLD/community psychiatry follow-up care plan. "
                       "Summarise (max 4 sentences, max 70 words): diagnoses (include neurodevelopmental conditions), "
                       "capacity/engagement status, current treatment plan, review timeframe, and GP actions required."
                       + demo_guard)
    elif "NHS 111" in letter_type:
        clin_prompt = (f"{context}\n\nThis is an NHS 111 referral to GP. "
                       "Summarise (max 4 sentences, max 70 words): presenting symptoms, acuity/urgency (timeframe for GP contact), "
                       "relevant history, and safety-netting advice given."
                       + demo_guard)
    elif "Cardiology" in letter_type:
        clin_prompt = (f"{context}\n\nThis is a cardiology outpatient letter. "
                       "Summarise (max 4 sentences, max 70 words): cardiac diagnosis, key investigation results "
                       "(echo EF%, ECG, CT/angiogram findings), medication changes with doses, "
                       "BP/cholesterol targets, and follow-up plan."
                       + demo_guard)
    elif "Hepatology" in letter_type or "Gastroenterology" in letter_type:
        clin_prompt = (f"{context}\n\nThis is a hepatology/gastroenterology outpatient letter. "
                       "Summarise (max 4 sentences, max 70 words): reason for review, key blood results (LFTs, HbA1c, eGFR), "
                       "imaging findings, investigations planned (FibroScan, endoscopy), and follow-up plan."
                       + demo_guard)
    else:
        clin_prompt = (f"{context}\n\nWrite a CONCISE clinical summary (2-3 sentences ONLY, maximum 70 words). "
                       "Include: main diagnosis/condition, key finding or intervention, current status. NO detailed explanations."
                       + demo_guard)

    # Run all 5 Claude calls concurrently — cuts Track B time by ~4x
    from concurrent.futures import ThreadPoolExecutor

    # OBS-007: Sensitivity clause for safeguarding/bereavement documents
    sensitivity_clause = (
        " IMPORTANT: This document contains sensitive content (safeguarding, bereavement, or mental health crisis). "
        "Do NOT quote any distressing details verbatim. Use supportive, neutral language. "
        "Focus only on what the patient needs to do next."
    ) if is_sensitive else ""

    patient_prompt = (
        f"{context}\n\nWrite a clear patient-friendly explanation (3-4 sentences) of what was found and what happens next. "
        "Avoid medical jargon. Use plain English. Start with the most important thing the patient needs to know."
        + sensitivity_clause + demo_guard
    )
    pharmacist_prompt = (
        f"{context}\n\nWrite a pharmacist-focused clinical summary. Include: all medications mentioned (with doses/frequencies), "
        "any new prescriptions, drug monitoring requirements, potential interactions to check, and any OTC advice given. "
        "If no medications are documented, state this clearly."
    )
    actions_prompt = (
        f"{context}\n\n"
        "Return a JSON object (no markdown, no explanation) with this exact structure:\n"
        '{"sender_actions":{"doctor":[],"pharmacist":[],"reception":[]},'
        '"gp_surgery_actions":{"doctor":[],"pharmacist":[],"reception":[]}}\n\n'
        "=== RULES FOR sender_actions ===\n"
        "What the SENDER (hospital/clinic/specialist) has stated or implied they will do next.\n"
        "Include: follow-up appointments, planned investigations, procedures, results to be sent, medication supplied.\n"
        "Good examples:\n"
        "  doctor: ['Will arrange MRI head and EEG at Royal Berkshire', 'Review in heart failure clinic in 3 months', 'Histology results will be sent to GP', 'Atezolizumab treatment starting 13/05/2026']\n"
        "  pharmacist: ['Dispensed Entresto 24/26mg — patient counselled on titration and washout']\n"
        "  reception: ['Follow-up appointment booked for 15/08/2026']\n\n"
        "=== RULES FOR gp_surgery_actions ===\n"
        "What the GP SURGERY must specifically action as a result of this letter.\n"
        "Good examples:\n"
        "  doctor: ['Refer patient to Gastroenterology for 8-year bloating and rectal bleeding (FIT negative 1 month ago)', "
        "'Arrange repeat PSA blood test in 4 months (due 15/08/2026)', "
        "'Start Entresto 24/26mg twice daily; stop perindopril (2-day washout required)', "
        "'Review antibiotic choice in context of solitary kidney and CKD stage 3']\n"
        "  pharmacist: ['Add solifenacin 5mg OD to repeat prescriptions', 'Check Wegovy supply and monitoring status']\n"
        "  reception: ['Book 6-week postnatal review appointment', 'Book patch testing as per dermatology plan']\n\n"
        "=== PROHIBITIONS - NEVER generate these ===\n"
        "- 'Update patient records' or 'Update GP records' - too generic\n"
        "- 'Advise patient' without specific advice content\n"
        "- 'Monitor patient' without a named parameter, target value, and timeframe\n"
        "- Vague reviews not grounded in explicit letter content (e.g. 'Review weight loss management')\n"
        "- Actions a GP does automatically without needing to be told\n\n"
        "=== OUTPUT RULES ===\n"
        "- Every action MUST reference specific details from the document: drug+dose, test name, referral destination, date\n"
        "- 1-3 high-quality specific actions per role - quality over quantity\n"
        "- If a role truly has no specific actions from this document, use []\n"
        "Output only the raw JSON object, nothing else."
    )

    with ThreadPoolExecutor(max_workers=4) as pool:
        fut_clin      = pool.submit(call_claude, clin_prompt, 100)
        fut_patient   = pool.submit(call_claude, patient_prompt)
        fut_pharmacist= pool.submit(call_claude, pharmacist_prompt)
        fut_actions   = pool.submit(call_claude, actions_prompt, 400)

        clinician_summary  = _rewrite_summary_without_age(fut_clin.result(), patient_sex)
        patient_summary    = _rewrite_summary_without_age(fut_patient.result(), patient_sex)
        pharmacist_summary = fut_pharmacist.result()
        actions_raw        = fut_actions.result()

    # Parse structured actions JSON from Claude's raw response
    import json as _json, re as _re
    actions_structured = {
        "sender_actions":    {"doctor": [], "pharmacist": [], "reception": []},
        "gp_surgery_actions":{"doctor": [], "pharmacist": [], "reception": []},
    }
    try:
        # Strip markdown code fences Claude sometimes adds despite instructions
        _raw_clean = _re.sub(r'```(?:json)?\s*', '', actions_raw).strip()

        # ── Extract outermost JSON object by bracket counting ──────────────────
        _start = _raw_clean.find('{')
        if _start != -1:
            _depth, _end = 0, _start
            for _ci, _ch in enumerate(_raw_clean[_start:], start=_start):
                if _ch == '{': _depth += 1
                elif _ch == '}': _depth -= 1
                if _depth == 0: _end = _ci; break
            _json_str = _raw_clean[_start:_end + 1]

            # ── Fix single-quoted strings → double-quoted (Claude's most common error) ──
            # Replace single-quoted array values: ['...', '...'] → ["...", "..."]
            # Strategy: find all single-quoted string literals and replace quotes
            def _fix_single_quotes(s):
                # Replace single-quoted values inside arrays/objects with double-quoted
                # Pattern: key: ['val1', 'val2'] or key: 'value'
                result = []
                i = 0
                while i < len(s):
                    if s[i] == "'" :
                        # Find closing single quote (not preceded by backslash)
                        j = i + 1
                        while j < len(s):
                            if s[j] == "'" and s[j-1] != '\\':
                                break
                            j += 1
                        inner = s[i+1:j].replace('"', '\\"')
                        result.append('"' + inner + '"')
                        i = j + 1
                    else:
                        result.append(s[i])
                        i += 1
                return ''.join(result)

            _json_fixed = _fix_single_quotes(_json_str)

            # ── Try json.loads first, then ast.literal_eval as fallback ───────
            _parsed = None
            try:
                _parsed = _json.loads(_json_fixed)
            except Exception:
                try:
                    import ast as _ast
                    _parsed = _ast.literal_eval(_json_str)  # handles Python dict/list natively
                except Exception:
                    pass

            if _parsed and isinstance(_parsed, dict):
                for _key in ("sender_actions", "gp_surgery_actions"):
                    if _key in _parsed and isinstance(_parsed[_key], dict):
                        for _role in ("doctor", "pharmacist", "reception"):
                            _items = _parsed[_key].get(_role, [])
                            if isinstance(_items, list):
                                actions_structured[_key][_role] = [str(i) for i in _items if i]
    except Exception as _parse_err:
        import sys
        print(f"[WARN] actions JSON parse failed: {_parse_err}. Raw response: {actions_raw[:300]}",
              file=sys.stderr)

    # Debug: always log raw response and parsed result
    import sys
    print(f"[DEBUG] actions_raw (first 500): {actions_raw[:500]}", file=sys.stderr)
    print(f"[DEBUG] actions_structured: {actions_structured}", file=sys.stderr)

    llm_conf = 0.80
    return {
        "clinician":  {"summary": clinician_summary, "confidence": llm_conf},
        "patient":    {"summary": patient_summary,   "confidence": llm_conf},
        "pharmacist": {"summary": pharmacist_summary, "confidence": llm_conf},
        "follow_up_actions":  actions_raw,
        "actions_structured": actions_structured,
        "llm_confidence":     llm_conf,
    }


def compute_unified_confidence(
    textract_conf: float,
    snomed_conf: float,
    llm_conf: float,
    letter_type: str = "",
) -> float:
    """Weighted unified confidence score (SRS Section 3.4).

    Default weights: Textract 40% + LLM 40% + SNOMED 20%.

    For Ambulance and 111 reports, SNOMED entities are typically absent because
    the text is in all-caps multi-column tables that Comprehend Medical cannot
    parse reliably. For these types we use Textract 50% + LLM 50% and ignore
    SNOMED, preventing false 'review required' flags.
    """
    if letter_type in ("Ambulance Clinical Report", "111 First ED Report"):
        # SNOMED unreliable for all-caps/table-heavy formats — use Textract + LLM only
        return (0.50 * textract_conf) + (0.50 * llm_conf)
    return (0.40 * textract_conf) + (0.20 * snomed_conf) + (0.40 * llm_conf)


def get_confidence_threshold(letter_type: str) -> float:
    """OBS-004: Return per-type confidence threshold from config/document_type_config.py.
    Single source of truth — thresholds are not duplicated here.
    """
    return _get_threshold(letter_type)


def run_comprehensive_extraction(text: str, letter_type: str = "") -> dict:
    """
    Comprehensive clinical document extraction using Claude Sonnet 5.
    Extracts ALL required fields in a single structured call for maximum accuracy.

    Returns dict with:
    - event_date: Date of clinical event/procedure
    - letter_date: Date letter was written/sent
    - problems: List of current problems/issues with SNOMED codes
    - treatments: List of treatments with SNOMED codes
    - medications: List of medications with SNOMED codes
    - investigations: List of investigations/tests with SNOMED codes
    - diagnoses: List of diagnoses with SNOMED codes
    - conclusion: Clinical conclusion
    - recommendation: Recommendations for GP/patient
    - diary_events: Scheduled follow-ups, tests, reviews
    - actions_patient: Actions for patient to take
    - actions_patient_booking: Appointments patient needs to book
    - is_historical: Fields marked as historical (to be excluded)
    """
    client = make_client("bedrock-runtime")
    MODEL = "arn:aws:bedrock:eu-west-2:654654155641:inference-profile/eu.anthropic.claude-sonnet-5"

    extraction_prompt = f"""You are an expert NHS clinical document analyst. Extract ALL the following information from this clinical document.

CRITICAL RULES:
1. Extract ONLY information from the CURRENT encounter/letter - NOT historical information
2. Historical info includes: "previously had", "history of", "past medical history", "in 2020", etc.
3. For SNOMED codes: provide the most specific SNOMED CT code you know for each clinical term
4. If a field has no relevant current information, use empty array []
5. Dates should be in DD/MM/YYYY format
6. READ THE "Plan and Requested Actions" SECTION CAREFULLY - this contains critical GP actions
7. For event_date: Look for "Admission Details" section with "Date:" or "Admission date"
8. For letter_date: Look for date in document header (e.g., "27 APR 2026") or "Discharge" section "Date:"

Document Type: {letter_type}

DOCUMENT TEXT:
{text[:6000]}

Return a JSON object with this EXACT structure (no markdown, no explanation):
{{
  "event_date": "DD/MM/YYYY - LOOK FOR: Admission Details Date, Procedure date, or earliest clinical event date",
  "letter_date": "DD/MM/YYYY - LOOK FOR: Document header date (e.g., 27 APR 2026 = 27/04/2026) or Discharge Date",
  "problems": [
    {{"term": "clinical symptom/finding e.g. constipation, pain, bleeding", "snomed_code": "code", "snomed_description": "description", "is_historical": false}}
  ],
  "treatments": [
    {{"term": "procedure/treatment performed during this admission e.g. flexible sigmoidoscopy, phenol injection, excision of skin tags, IV iron infusion, chemotherapy", "snomed_code": "code", "snomed_description": "description", "is_historical": false}}
  ],
  "medications": [
    {{"term": "drug name", "dose": "dose if mentioned", "frequency": "frequency if mentioned", "snomed_code": "code", "is_historical": false}}
  ],
  "investigations": [
    {{"term": "test/scan/biopsy name e.g. histology, blood test, CT scan, MRI. Include PENDING tests from 'Investigations Pending at Discharge' section", "result": "result or 'pending' if awaiting results", "snomed_code": "code", "is_historical": false, "is_pending": true/false}}
  ],
  "diagnoses": [
    {{"term": "diagnosis with ICD code if present e.g. Haemorrhoids [K64.9]", "snomed_code": "code", "snomed_description": "description", "is_historical": false}}
  ],
  "conclusion": "Brief clinical conclusion from the letter",
  "recommendation": "Recommendations stated in the letter",
  "diary_events": [
    {{"event": "what needs to happen", "due_date": "when (e.g., 4 weeks after transfusion, 3 months)", "responsible_party": "GP/Patient/Hospital"}}
  ],
  "actions_gp_doctor": [
    "Actions requiring GP doctor - e.g., 'Review pending histology results when available (urgent)', 'Arrange repeat bloods 4 weeks after transfusion', 'Refer to specialist'. IMPORTANT: Include any pending investigations/histology from 'Investigations Pending at Discharge' or 'Specimens' section"
  ],
  "actions_gp_pharmacist": [
    "Actions requiring GP pharmacist - e.g., 'Add medication to repeat', 'Review drug interactions'"
  ],
  "actions_gp_reception": [
    "Actions requiring GP reception - e.g., 'Book follow-up appointment', 'Send referral letter'"
  ],
  "actions_patient": [
    "Actions patient must take - e.g., 'Fast before blood test', 'Take medication at specific time'"
  ],
  "actions_patient_booking": [
    "Appointments patient needs to book - e.g., 'Book blood test at GP', 'Book follow-up review'"
  ]
}}

Output ONLY the JSON object, nothing else."""

    try:
        import sys
        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 2000,
            "messages": [{"role": "user", "content": extraction_prompt}]
        })
        print(f"[DEBUG] Calling Bedrock for comprehensive extraction...", file=sys.stderr)
        resp = client.invoke_model(modelId=MODEL, body=body, contentType="application/json")
        resp_bytes = resp["body"].read()
        print(f"[DEBUG] Bedrock response bytes length: {len(resp_bytes)}", file=sys.stderr)

        if not resp_bytes:
            raise ValueError("Empty response from Bedrock")

        resp_body = json.loads(resp_bytes)
        print(f"[DEBUG] resp_body keys: {list(resp_body.keys())}", file=sys.stderr)

        # Handle different response formats (same as call_claude)
        if "content" in resp_body and resp_body["content"]:
            content_item = resp_body["content"][0]
            print(f"[DEBUG] content[0] type: {type(content_item)}, keys: {list(content_item.keys()) if isinstance(content_item, dict) else 'N/A'}", file=sys.stderr)
            print(f"[DEBUG] content[0] value: {str(content_item)[:300]}", file=sys.stderr)
            # Try different keys for the text content
            if isinstance(content_item, dict):
                raw = content_item.get("text", "") or content_item.get("value", "") or content_item.get("content", "")
            elif isinstance(content_item, str):
                raw = content_item
            else:
                raw = str(content_item)
            raw = raw.strip()
        elif "completion" in resp_body:
            raw = resp_body["completion"].strip()
        else:
            raw = str(resp_body).strip()

        print(f"[DEBUG] Comprehensive extraction raw (first 500): {raw[:500] if raw else 'EMPTY'}", file=sys.stderr)

        # Clean and parse JSON
        import re as _re
        _raw_clean = _re.sub(r'```(?:json)?\s*', '', raw).strip()
        _raw_clean = _re.sub(r'```\s*$', '', _raw_clean).strip()

        # Find JSON object - try multiple approaches
        _start = _raw_clean.find('{')
        _end = _raw_clean.rfind('}')

        if _start == -1 or _end == -1 or _start >= _end:
            # Try to find JSON in the original raw response
            _start = raw.find('{')
            _end = raw.rfind('}')
            if _start != -1 and _end != -1 and _start < _end:
                _raw_clean = raw

        if _start != -1 and _end != -1 and _start < _end:
            _json_str = _raw_clean[_start:_end + 1]
            try:
                result = json.loads(_json_str)
            except json.JSONDecodeError as je:
                print(f"[DEBUG] JSON parse error at pos {je.pos}: {je.msg}", file=sys.stderr)
                print(f"[DEBUG] JSON string (first 300): {_json_str[:300]}", file=sys.stderr)
                raise ValueError(f"Invalid JSON: {je.msg}")

            # Filter out historical items
            for field in ['problems', 'treatments', 'medications', 'investigations', 'diagnoses']:
                if field in result and isinstance(result[field], list):
                    result[field] = [item for item in result[field]
                                    if not item.get('is_historical', False)]

            return result
        else:
            print(f"[DEBUG] No JSON found. Raw response: {raw[:300]}", file=sys.stderr)
            raise ValueError("No JSON object found in response")

    except Exception as e:
        import sys
        print(f"[WARN] Comprehensive extraction failed: {e}", file=sys.stderr)
        # Fallback: use regex to extract key fields from text
        fallback = extract_plan_and_actions_fallback(text)
        fallback["extraction_error"] = str(e)
        return fallback


def extract_plan_and_actions_fallback(text: str) -> dict:
    """Fallback extraction using regex when Claude fails.
    Extracts from 'Plan and Requested Actions' or 'Plan' section."""
    import re

    result = {
        "event_date": "",
        "letter_date": "",
        "problems": [],
        "treatments": [],
        "medications": [],
        "investigations": [],
        "diagnoses": [],
        "conclusion": "",
        "recommendation": "",
        "diary_events": [],
        "actions_gp_doctor": [],
        "actions_gp_pharmacist": [],
        "actions_gp_reception": [],
        "actions_patient": [],
        "actions_patient_booking": [],
    }

    # Try multiple patterns for Plan section (different letter formats)
    plan_patterns = [
        # Discharge summary format: "Plan and Requested Actions"
        r'Plan and Requested Actions[:\s]*\n(.*?)(?=\n\s*\n|\nSafety Alerts|\nPast Medical|\nMedications|\Z)',
        # Clinic letter format: "Plan" followed by bullet points or lines
        r'(?:^|\n)Plan\s*\n((?:(?:[-•]\s*)?[A-Z][^\n]+\n?)+)',
        # Alternative: Plan section until next section or paragraph break
        r'(?:^|\n)Plan[:\s]*\n(.*?)(?=\n(?:Yours|I reviewed|Dear|CC:|$))',
    ]

    plan_text = None
    for pattern in plan_patterns:
        plan_match = re.search(pattern, text, re.IGNORECASE | re.DOTALL | re.MULTILINE)
        if plan_match:
            plan_text = plan_match.group(1).strip()
            break

    # Also extract Diagnosis section (for orthopaedic letters)
    diagnosis_match = re.search(
        r'(?:^|\n)Diagnosis\s*\n(.*?)(?=\n(?:Plan|Date of injury|I reviewed|Dear|$))',
        text, re.IGNORECASE | re.DOTALL | re.MULTILINE
    )
    if diagnosis_match:
        diag_text = diagnosis_match.group(1).strip()
        for line in diag_text.split('\n'):
            line = line.strip()
            if line and not line.lower().startswith('date'):
                result["diagnoses"].append({"term": line})
                if not result["conclusion"]:
                    result["conclusion"] = line

    # ── Extract clinical findings (inflammation, abnormalities) ──────────────────
    # Look for findings like "inflamed mucosa in the sigmoid and descending colon"
    CLINICAL_FINDINGS = {
        r'inflamed mucosa[^.]*': ("128139000", "Inflammatory disorder of intestine (disorder)"),
        r'inflam(?:ed|mation)[^.]*(?:colon|sigmoid|rectum|bowel)': ("128139000", "Inflammatory disorder of intestine (disorder)"),
        r'biops(?:y|ies) taken': (None, None),  # Just note, no SNOMED
        r'(?:no|does not) want banding': (None, None),  # Patient preference
    }

    for pattern, (snomed_code, snomed_desc) in CLINICAL_FINDINGS.items():
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            finding_text = match.group(0).strip()
            if snomed_code:
                result["problems"].append({
                    "term": finding_text,
                    "snomed_code": snomed_code,
                    "snomed_description": snomed_desc
                })
            else:
                # Just a note, add to conclusion if relevant
                if "biops" in finding_text.lower() and "biops" not in result.get("conclusion", "").lower():
                    result["conclusion"] = (result.get("conclusion", "") + "; " + finding_text).strip("; ")

    # Extract Date of injury for orthopaedic letters
    injury_date_match = re.search(r'Date of injury[:\s]*(\d{1,2}(?:st|nd|rd|th)?\s+\w+\s+\d{4}|\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})', text, re.IGNORECASE)
    if injury_date_match:
        result["event_date"] = injury_date_match.group(1)

    if plan_text:
        lines = [l.strip() for l in plan_text.split('\n') if l.strip()]
        # Filter out lines that are just noise
        lines = [l for l in lines if len(l) > 5 and not l.lower().startswith('yours')]

        for line in lines:
            # Clean up line - remove bullet points
            clean_line = re.sub(r'^[-•]\s*', '', line).strip()
            if not clean_line or len(clean_line) < 5:
                continue

            ll = clean_line.lower()

            # Determine responsible party and due date based on content
            responsible = "GP"
            due_date = "As specified"

            if any(x in ll for x in ['week', 'month', 'day']):
                time_match = re.search(r'(\d+)\s*(week|month|day)s?', ll)
                if time_match:
                    due_date = f"{time_match.group(1)} {time_match.group(2)}s"

            if 'patient' in ll or 'blood form given' in ll or 'form given' in ll:
                responsible = "Patient"
                due_date = "Use form provided" if 'form' in ll else due_date

            # Add ALL items to diary events
            result["diary_events"].append({
                "event": clean_line,
                "due_date": due_date,
                "responsible_party": responsible
            })

            # Categorize for GP actions - expanded patterns for clinic letters
            if any(x in ll for x in ['refer', 'ct', 'mri', 'x-ray', 'xray', 'scan', 'review', 'physiotherapy', 'physio']):
                result["actions_gp_doctor"].append(clean_line)
            elif any(x in ll for x in ['repeat blood', 'advised', 'arrange', 'prescribe', 'bloods']):
                result["actions_gp_doctor"].append(clean_line)
            elif 'blood form' in ll or 'form given' in ll:
                result["actions_gp_reception"].append(clean_line)
            elif 'removed' in ll or 'cannula' in ll:
                if not result["conclusion"]:
                    result["conclusion"] = clean_line

    # Extract dates from Admission Details section
    admission_match = re.search(r'Admission Details.*?Date[:\s]*(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})', text, re.IGNORECASE | re.DOTALL)
    if admission_match:
        result["event_date"] = admission_match.group(1)

    # Extract discharge/letter date
    discharge_match = re.search(r'(?:Discharge|Letter).*?Date[:\s]*(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})', text, re.IGNORECASE | re.DOTALL)
    if discharge_match:
        result["letter_date"] = discharge_match.group(1)

    # Extract header date (e.g., "27 APR 2026" or "30th March 2026")
    months_abbr = {'JAN':'01','FEB':'02','MAR':'03','APR':'04','MAY':'05','JUN':'06',
                   'JUL':'07','AUG':'08','SEP':'09','OCT':'10','NOV':'11','DEC':'12'}
    months_full = {'JANUARY':'01','FEBRUARY':'02','MARCH':'03','APRIL':'04','MAY':'05','JUNE':'06',
                   'JULY':'07','AUGUST':'08','SEPTEMBER':'09','OCTOBER':'10','NOVEMBER':'11','DECEMBER':'12'}

    if not result["letter_date"]:
        # Try "30th March 2026" format
        header_date_full = re.search(r'(\d{1,2})(?:st|nd|rd|th)?\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})', text[:1000], re.IGNORECASE)
        if header_date_full:
            d, m, y = header_date_full.groups()
            result["letter_date"] = f"{d.zfill(2)}/{months_full[m.upper()]}/{y}"
        else:
            # Try "27 APR 2026" format
            header_date = re.search(r'(\d{1,2})\s*(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\s*(\d{4})', text[:500], re.IGNORECASE)
            if header_date:
                d, m, y = header_date.groups()
                result["letter_date"] = f"{d.zfill(2)}/{months_abbr[m.upper()]}/{y}"

    # ── Parse "Investigations Pending at Discharge" and "Specimens" sections ──────────────────
    # First check for Specimens table format (common in discharge summaries)
    specimens_section = re.search(
        r'Specimens\s*(.*?)(?=\n(?:Unresulted|Outpatient|Actions Required|Allergies|Primary Care|$))',
        text, re.IGNORECASE | re.DOTALL
    )

    pending_investigations_match = re.search(
        r'Investigations Pending at Discharge\s*(.*?)(?=\n(?:Unresulted Labs|Outpatient Follow|Actions Required|Allergies|Specimens|$))',
        text, re.IGNORECASE | re.DOTALL
    )

    investigations_text = ""
    if specimens_section:
        investigations_text += specimens_section.group(1).strip() + "\n"
    if pending_investigations_match:
        investigations_text += pending_investigations_match.group(1).strip()

    if investigations_text:
        # Parse specimen rows - format: Source | Type | Tests | Collected By | Collected At | Priority
        # Or Description: lines
        specimen_rows = []

        # Pattern 1: Table rows with Source, Type, Tests columns
        # Example: "Rectum Tissue (Histology) • HISTOLOGY, TISSUE Akram GEORGE HANNA, MD 8/2/26 10:33 Urgent"
        table_rows = re.findall(
            r'(\w+)\s+Tissue\s*\(Histolog[y]?\)\s*[•·]?\s*(HISTOLOGY[,\s]*TISSUE)\s+.*?(\d+/\d+/\d+\s+\d+:\d+)\s+(Urgent|Routine)',
            investigations_text, re.IGNORECASE
        )
        for source, test_type, collected_at, priority in table_rows:
            specimen_rows.append({
                "source": source.strip(),
                "test": "Histology",
                "priority": priority.capitalize(),
                "collected_at": collected_at
            })

        # Pattern 2: Description lines
        descriptions = re.findall(r'Description:\s*([^\n]+)', investigations_text, re.IGNORECASE)
        priorities = re.findall(r'(?:Priority[:\s]*|^|\s)(Urgent|Routine)(?:\s|$)', investigations_text, re.IGNORECASE)

        for i, desc in enumerate(descriptions):
            priority = priorities[i] if i < len(priorities) else 'Routine'
            specimen_rows.append({
                "source": desc.strip(),
                "test": "Histology",
                "priority": priority.capitalize()
            })

        # Generate investigation entries and GP actions
        seen_sources = set()
        for spec in specimen_rows:
            source = spec.get("source", "Unknown")
            if source.lower() in seen_sources:
                continue
            seen_sources.add(source.lower())

            priority = spec.get("priority", "Routine")
            priority_label = f" ({priority.upper()})" if priority.lower() == "urgent" else ""

            # Add to investigations with priority
            result["investigations"].append({
                "term": f"Histology - {source}",
                "snomed_code": "117259009",
                "snomed_description": "Histologic examination, tissue (procedure)",
                "result": "Pending",
                "priority": priority
            })

            # Add to GP actions - urgent histology needs doctor review
            if priority.lower() == "urgent":
                result["actions_gp_doctor"].append(f"Review URGENT histology result: {source} - chase if not received")
            else:
                result["actions_gp_doctor"].append(f"Review histology result when available: {source}")

        # If HISTOLOGY mentioned but no structured data found
        if not specimen_rows and 'histology' in investigations_text.lower():
            result["actions_gp_doctor"].append("Pending histology results - review when available")
            result["investigations"].append({
                "term": "Histology tissue examination",
                "snomed_code": "117259009",
                "result": "Pending"
            })

    # ── Parse "Post-op Instructions" for patient actions ──────────────────
    postop_match = re.search(
        r'Post-op Instructions\s*(.*?)(?=\n(?:Actions Required|Investigations Pending|Specimens|$))',
        text, re.IGNORECASE | re.DOTALL
    )
    if postop_match:
        postop_text = postop_match.group(1).strip()
        for line in postop_text.split('\n'):
            line = line.strip()
            if line and len(line) > 5:
                result["actions_patient"].append(line)

    # ── Parse procedures from Procedure Information section AND body text ──────────────
    # Known surgical/therapeutic procedures with SNOMED codes
    KNOWN_PROCEDURES = {
        "flexible sigmoidoscopy": ("44441009", "Flexible fiberoptic sigmoidoscopy (procedure)"),
        "sigmoidoscopy": ("44441009", "Flexible fiberoptic sigmoidoscopy (procedure)"),
        "colonoscopy": ("73761001", "Colonoscopy (procedure)"),
        "phenol injection": ("307589007", "Phenol injection of hemorrhoid (procedure)"),
        "excision of skin tags": ("177965000", "Excision of lesion of skin (procedure)"),
        "excision of perianal skin tags": ("177965000", "Excision of lesion of skin (procedure)"),
        "haemorrhoidectomy": ("30577007", "Hemorrhoidectomy (procedure)"),
        "banding": ("265737005", "Hemorrhoid banding (procedure)"),
        "rubber band ligation": ("265737005", "Hemorrhoid banding (procedure)"),
        "eua": ("386053000", "Examination under anesthesia (procedure)"),
    }

    # Search document body for procedures
    proc_found = set()
    for proc_name, (snomed_code, snomed_desc) in KNOWN_PROCEDURES.items():
        if proc_name in text.lower():
            if proc_name not in proc_found:
                proc_found.add(proc_name)
                result["treatments"].append({
                    "term": proc_name.title(),
                    "snomed_code": snomed_code,
                    "snomed_description": snomed_desc
                })

    # Also extract any procedure mentioned in "Procedure(s)" section
    procedure_match = re.search(
        r'Procedure\(s\)\s*(?:\([^)]*\))?[:\s]*\n?(.*?)(?=\n\s*\n|Post-op|In partnership|$)',
        text, re.IGNORECASE | re.DOTALL
    )
    if procedure_match:
        proc_text = procedure_match.group(1).strip()
        # Extract procedures listed in this section
        for line in proc_text.split('\n'):
            line = line.strip()
            if line and len(line) > 3 and line.lower() not in proc_found:
                # Add if it looks like a procedure (not a date/code)
                if not re.match(r'^[\d/\-]+$', line) and not line.startswith('Procedure date'):
                    result["treatments"].append({"term": line})

    # ── Parse telephone/follow-up appointments from Post-op section ──────────
    telephone_match = re.search(r'(Telephone appointment[^\n]*)', text, re.IGNORECASE)
    if telephone_match:
        appt_text = telephone_match.group(1).strip()
        result["diary_events"].append({
            "event": appt_text,
            "due_date": "6 weeks" if "6 week" in appt_text.lower() else "As specified",
            "responsible_party": "Hospital"
        })
        result["actions_gp_reception"].append(f"Note: {appt_text}")

    import sys
    print(f"[DEBUG] Fallback extraction: diary_events={len(result['diary_events'])}, gp_actions={len(result['actions_gp_doctor'])}, diagnoses={len(result['diagnoses'])}", file=sys.stderr)

    return result


def extract_hospital_trust(text: str) -> str:
    """OBS-008: Identify the originating hospital trust from document header text.
    Enables routing, audit logging, and trust-specific formatting rules.
    """
    t = text[:800].lower()  # trust name always in first page header
    if any(x in t for x in ["frimley health", "frimley park hospital", "wexham park", "heatherwood"]):
        return "Frimley Health NHS Foundation Trust"
    if any(x in t for x in ["royal berkshire", "rbh", "london road, reading"]):
        return "Royal Berkshire Hospital NHS Foundation Trust"
    if any(x in t for x in ["berkshire healthcare", "prospect park", "talking therapies"]):
        return "Berkshire Healthcare NHS Foundation Trust"
    if any(x in t for x in ["south central ambulance", "scas"]):
        return "South Central Ambulance Service NHS Foundation Trust"
    if any(x in t for x in ["university hospital southampton", "uhs", "tremona road"]):
        return "University Hospital Southampton NHS Foundation Trust"
    if any(x in t for x in ["kettering", "rothwell road"]):
        return "Kettering General Hospital NHS Foundation Trust"
    if any(x in t for x in ["evolutio", "odtc.co.uk", "newtown house, newtown road"]):
        return "Evolutio Care Innovations Ltd"
    if any(x in t for x in ["expert health", "expert/health", "experthealth", "expert health ltd", "dr. mitra dutt"]):
        return "Expert Health Ltd"
    return "Unknown Trust"


def contains_sensitive_content(text: str) -> bool:
    """OBS-007: Detect if document contains sensitive/safeguarding content.
    Used to add protective instructions to patient-facing Bedrock prompts.
    """
    t = text.lower()
    return any(marker in t for marker in SENSITIVE_CONTENT_MARKERS)


def resolve_arrival_method(text: str) -> str:
    """OBS-010: Decode Frimley arrival method codes e.g. '[8]' -> 'Emergency Road Ambulance WITH Medical Escort'."""
    import re
    m = re.search(r'\[(\d+)\]', text)
    if m:
        code = m.group(1)
        return ARRIVAL_METHOD_CODES.get(code, f"Code {code}")
    return text


def infer_letter_type(text: str) -> str:
    """Classify letter type based on all 21 observed document patterns (batches 1-5).
    Priority order: most specific/distinct signals first to prevent false matches.
    """
    t = text.lower()
    # ── Priority 1: Document TYPE identifiers (from header/title) ────────────
    # These are explicit document type markers - check FIRST before content-based matching

    # Generic discharge summaries - HIGHEST PRIORITY as it's a document type marker
    if any(x in t[:1500] for x in ["discharge summary"]):
        # Check for specialty subtypes within discharge summaries
        if any(x in t for x in ["mental health inpatient discharge", "prospect park hospital",
                                  "crhtt", "cmht", "snowdrop ward", "section 2", "section 3",
                                  "mental health act", "inpatient consultant"]):
            return "Mental Health Inpatient Discharge"
        if any(x in t for x in ["antenatal discharge", "estimate delivery date", "estimate gestational age",
                                  "gravida & parity", "reduced fetal movement", "mdau"]):
            return "Antenatal Discharge Summary"
        if any(x in t for x in ["camhs", "child and adolescent", "brief psychosocial intervention"]):
            return "CAMHS Discharge Summary"
        # Check for Nephrology/Renal specialty
        if any(x in t for x in ["nephrology", "renal capd", "renal medicine", "kidney unit",
                                  "nephrologist", "berkshire kidney", "egfr", "dialysis"]):
            return "Renal / Nephrology Letter"
        return "Discharge Summary"

    # ── Priority 2: Highly specific document types ────────────────────────────
    # SCAS Ambulance Clinical Reports — very distinct vocabulary
    if any(x in t for x in ["south central ambulance service", "patient clinical report",
                              "gp patient report v3", "scas clinician", "news2 score",
                              "pops score", "nature of call", "incident number",
                              "conveyance", "at patient side"]):
        return "Ambulance Clinical Report"
    # Ophthalmology Referral — Evolutio / eRefer (must come before generic referral catch)
    if any(x in t for x in ["evolutio ophthalmology", "evolutio care innovations",
                              "patient ophthalmology referral", "east berkshire community eye service",
                              "erefer referral", "referral id number", "triager action required",
                              "odtc.co.uk", "epiretinal membrane", "specsavers"]):
        return "Ophthalmology Referral"
    # Ophthalmology Outpatient / Medical Retina - requires ophthalmology context + specific terms
    # Must NOT match just because patient has diabetes (which often has retinopathy history)
    if any(x in t[:1500] for x in ["ophthalmology", "medical retina", "eye clinic", "ophthalmic"]):
        if any(x in t for x in ["diabetic retinopathy", "proliferative retinopathy", "macular oedema",
                                  "intraocular pressure", "fundus exam", "prp", "panretinal",
                                  "neovascularisation", "nvd", "nve", "slit lamp", "visual acuity"]):
            return "Ophthalmology Letter"
    # Expert Health / GLP-1 prescribing — very distinct brand names
    if any(x in t for x in ["expert health", "notification of consultation", "kwikpen",
                              "weight management", "glp-1", "mounjaro", "semaglutide",
                              "ozempic", "wegovy", "weight loss programme"]):
        return "Medication / Prescriber Letter"
    # ED Discharge Letters — emergency dept specific, before generic discharge
    if any(x in t for x in ["frimley emergency", "patient discharge letter",
                              "attendance reason", "arrival method", "source of referral",
                              "mode of arrival", "presenting complaint:", "place of accident"]):
        return "ED Discharge Letter"
    # 111 First ED Reports
    if any(x in t for x in ["111 first ed report", "nhs111 encounter", "pathways disposition",
                              "pathways assessment", "attendance activity", "111 first"]):
        return "111 First ED Report"
    # Mental Health Inpatient Discharge (backup check for docs without "discharge summary" header)
    if any(x in t for x in ["mental health inpatient discharge", "prospect park hospital",
                              "crhtt", "cmht", "snowdrop ward", "section 2", "section 3",
                              "mental health act", "inpatient consultant"]):
        return "Mental Health Inpatient Discharge"
    # Antenatal Discharge Summary (backup check)
    if any(x in t for x in ["antenatal discharge", "estimate delivery date", "estimate gestational age",
                              "gravida & parity", "reduced fetal movement", "mdau",
                              "antenatal discharge summary"]):
        return "Antenatal Discharge Summary"
    # Cancer surveillance
    if any(x in t for x in ["surveillance", "adenocarcinoma", "hemicolectomy", "colorectal surveillance",
                              "tnm", "cea", "chemotherapy", "oncology"]):
        return "Cancer Surveillance Letter"
    # HIV / GUM / Sexual health
    if any(x in t for x in ["hiv", "gum clinic", "garden clinic", "sexual health", "antiretroviral",
                              "cd4", "viral load", "art regimen", "dolutegravir", "tenofovir"]):
        return "HIV / GUM Clinic Letter"
    # Maternity / diabetes
    if any(x in t for x in ["gestational diabetes", "antenatal", "maternity", "glucose tolerance",
                              "pip code", "blood glucose monitoring", "midwives"]):
        return "Maternity / Diabetes Letter"
    # Orthopaedic / Fracture Clinic Letter
    if any(x in t for x in ["fracture clinic", "orthopaedic", "orthopedic", "clavicle", "clavicular",
                              "fracture", "x-ray done", "collar and cuff", "physiotherapy referral",
                              "midshaft", "ct scan", "bone", "callus"]):
        if any(x in t for x in ["department of orthopaedics", "fracture clinic", "clinic letter"]):
            return "Orthopaedic Clinic Letter"
    # Pre-op surgical outpatient
    if any(x in t for x in ["hernia", "supra-umbilical", "upper gi", "open repair", "mesh repair",
                              "brachioplasty", "pre-op", "pre op", "surgical consent"]):
        return "Surgical Outpatient Letter"
    # Procedure / endoscopy reports
    if any(x in t for x in ["endoscopy", "ogd", "colonoscopy", "gastroscopy", "oesophageal",
                              "colonography", "procedure report", "endoscopist"]):
        return "Procedure Report"
    # CAMHS / paediatric mental health (backup check)
    if any(x in t for x in ["camhs", "child and adolescent", "mental health service",
                              "brief psychosocial intervention", "bpi"]):
        return "CAMHS Discharge Summary"
    # Generic discharge summaries (backup check - primary check is at top)
    if any(x in t for x in ["discharge date", "discharging consultant",
                              "length of stay", "discharge summary completed by"]):
        return "Discharge Summary"
    # Psychiatry outpatient
    if any(x in t for x in ["psychiatrist", "psychiatric", "bipolar", "icd10", "icd-10",
                              "quetiapine", "lisdexamfetamine", "consultant psychiatrist"]):
        return "Psychiatry Outpatient Letter"
    # Renal / Nephrology Letter (prefix 6.)
    if any(x in t for x in ["nephrologist", "nephrology", "berkshire kidney",
                              "egfr", "creatinine", "renal medicine", "albumin creatinine ratio",
                              "remote monitoring team", "kidney unit"]):
        return "Renal / Nephrology Letter"
    # Paediatric Cardiology (prefix 6.)
    if any(x in t for x in ["paediatric cardiol", "paediatric and fetal cardiologist",
                              "congenital heart", "ep mdt", "ablation", "svt",
                              "supraventricular tachycardia", "accessory pathway", "atenolol"]):
        return "Paediatric Cardiology Letter"
    # Early Pregnancy / Gynaecology (prefix 7.) — check before maternity
    if any(x in t for x in ["ugcc", "epau", "early pregnancy", "gestational sac",
                              "transvaginal", "intrauterine pregnancy", "gravida",
                              "uncertain viability", "emergency gynaecology"]):
        return "Early Pregnancy / Gynaecology Letter"
    # Pre-admission Booking Letter (prefix 7.)
    if any(x in t for x in ["fasting instructions", "hospital admission has been scheduled",
                              "do not eat after", "admission instructions", "day surgery unit",
                              "bring this letter with you"]):
        return "Pre-admission Letter"
    # Haematology / oncology outpatient (prefix 10.)
    # (Antenatal Discharge Summary check is earlier — before Maternity/Diabetes)
    if any(x in t for x in ["haematology", "myeloma", "multiple myeloma", "lenalidomide",
                              "bortezomib", "protein electrophoresis", "paraprotein"]):
        return "Haematology Outpatient Letter"
    # Weight management / prescriber (prefix 10.) — Expert Health / GLP-1
    if any(x in t for x in ["weight management", "glp-1", "mounjaro", "semaglutide",
                              "ozempic", "wegovy", "weight loss programme",
                              "expert health", "notification of consultation", "kwikpen"]):
        return "Medication / Prescriber Letter"
    # Antibiotic / medication requests
    if any(x in t for x in ["antibiotic request", "medication request", "repeat prescription",
                              "flucloxacillin", "prescrib"]):
        return "Medication Request"
    # ADHD / Neurodevelopmental Assessment — observed in test set (ADHD initial assessment)
    if any(x in t for x in ["adhd assessment", "attention deficit hyperactivity",
                              "dsm-5 criteria for adhd", "psychiatry uk",
                              "adult adhd self report", "conners", "cognitive assessment"]):
        return "ADHD / Neurodevelopmental Assessment"
    # Urology / PSA follow-up — observed in test set (PSA monitoring, LUTS, mpMRI)
    if any(x in t for x in ["urology", "psa", "prostate", "mpmri", "pi-rads",
                              "solifenacin", "tamsulosin", "luts", "urodynamics",
                              "radical prostatectomy", "transurethral"]):
        return "Urology Outpatient Letter"
    # Dermatology — observed in test set (transfer of care, patch testing)
    if any(x in t for x in ["dermatology", "dermatologist", "patch test", "patch testing",
                              "community dermatology", "mometasone", "epaderm",
                              "emollient", "dermal", "skin clinic"]):
        return "Dermatology Letter"
    # CTPLD / Community psychiatry follow-up — observed in test set (trisomy 21, CTPLD)
    if any(x in t for x in ["ctpld", "community team for people with learning disabilities",
                              "follow up care plan", "care programme approach", "cpa",
                              "named mental health professional", "keyworker"]):
        return "CTPLD / Community Psychiatry Letter"
    # NHS 111 GP referral — observed in test set (blood in stool, 111 refer to OGP)
    if any(x in t for x in ["nhs 111", "111 referral", "refer back to ogp",
                              "primary care service within 24", "pathways"]):
        return "NHS 111 Referral"
    # Cardiology outpatient — observed in test set (heart failure, echo, coronary)
    if any(x in t for x in ["cardiology", "cardiologist", "heart failure clinic",
                              "echocardiogram", "ejection fraction", "entresto",
                              "coronary", "angiogram", "pacemaker clinic"]):
        return "Cardiology Outpatient Letter"
    # Hepatology / gastroenterology outpatient
    if any(x in t for x in ["hepatology", "gastroenterology", "gastroenterologist",
                              "fibroscan", "liver clinic", "lfts", "liver function"]):
        return "Hepatology / Gastroenterology Letter"
    # Referral letters
    if any(x in t for x in ["referral", "i am referring", "reason for referral",
                              "please see this patient", "to whom it may concern"]):
        return "Referral Letter"
    # Outpatient follow-up
    if any(x in t for x in ["outpatient", "follow-up", "follow up", "clinic visit",
                              "appointment type", "clinic note"]):
        return "Outpatient Letter"
    return "Clinical Letter"


def extract_icd_codes(text: str) -> list:
    """Extract ICD-10 codes like K64.9, F31.0. Only codes that appear in clinical context.

    ICD-10 chapters: A-B (infections), C-D (neoplasms), E (metabolic), F (mental),
    G (nervous), H (eye/ear), I (circulatory), J (respiratory), K (digestive),
    L (skin), M (musculoskeletal), N (genitourinary), O (pregnancy), P (perinatal),
    Q (congenital), R (symptoms), S-T (injury), V-Y (external causes), Z (factors).

    Filters out false positives like page numbers, reference codes, NHS numbers.
    """
    import re

    # Valid ICD-10 chapter letters (excludes U which is provisional)
    VALID_ICD_CHAPTERS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ") - {"U", "X"}  # X is external causes, rarely in letters

    # Codes that are NOT ICD codes but match the pattern (false positives)
    FALSE_POSITIVE_CODES = {
        # NHS/document reference patterns
        "G01", "G02", "G03", "G04", "G05",  # Often page references like "Page G01"
        "W01", "W02", "W03",  # Ward codes
        "N01", "N02", "N03",  # Reference numbers
        # Time patterns that slip through
        "H00", "H01", "H02", "H03",  # Hour codes
        # Generic codes
        "V01", "V02", "V03",  # Version numbers
    }

    # Look for codes in brackets [K64.9] or after "ICD" mention
    bracketed_pattern = r'\[([A-Z]\d{2}(?:\.\d{1,2})?)\]'
    icd_label_pattern = r'ICD[-\s]?10?\s*[:=]?\s*([A-Z]\d{2}(?:\.\d{1,2})?)'

    codes = []

    # First priority: codes in brackets (most reliable)
    for code in re.findall(bracketed_pattern, text):
        if code not in FALSE_POSITIVE_CODES and code[0] in VALID_ICD_CHAPTERS:
            codes.append(code)

    # Second priority: codes after "ICD" label
    for code in re.findall(icd_label_pattern, text, re.IGNORECASE):
        if code not in FALSE_POSITIVE_CODES and code[0] in VALID_ICD_CHAPTERS and code not in codes:
            codes.append(code)

    # Third priority: codes in diagnosis context only
    diagnosis_context = re.findall(
        r'(?:diagnosis|diagnos(?:is|es)|condition|presenting complaint)[:\s]*[^.\n]*?([A-Z]\d{2}(?:\.\d{1,2})?)',
        text, re.IGNORECASE
    )
    for code in diagnosis_context:
        if code not in FALSE_POSITIVE_CODES and code[0] in VALID_ICD_CHAPTERS and code not in codes:
            codes.append(code)

    return codes[:10]  # Limit to 10 codes


def extract_medications(text: str) -> list:
    """Extract medication lines with dosage patterns and medication list entries.

    Handles formats:
    - "Drug Name Xmg tablet" (standard)
    - "lansoprazole 15mg gastro-resistant capsule" (discharge summary)
    - "macrogol compound NPF sugar free oral powder" (compound formulations)
    - "paracetamol 500mg tablet Take TWO tablets..." (with instructions)
    """
    import re
    meds = []
    lines = text.split("\n")

    # Pattern 1: Standard dose pattern "Drug Name Xmg/Xml"
    dose_re = re.compile(
        r'(\b[A-Z][a-zA-Z\s\-]+?)\s+'
        r'(\d+\.?\d*\s*(?:mg|ml|mcg|iu|g|mg/ml|ml/hr|units?|%|micrograms?)[^\n,;]{0,60})',
        re.IGNORECASE
    )

    # Pattern 2: Medication list format (drug name bold followed by formulation)
    # Matches: "lansoprazole 15mg gastro-resistant capsule"
    med_list_re = re.compile(
        r'^([a-z][a-z\s\-]+(?:\s+compound\s+NPF)?)\s+'  # drug name (may include "compound NPF")
        r'(\d+\.?\d*\s*(?:mg|ml|mcg|g|%)?\s*'  # dose
        r'(?:gastro-resistant\s+)?(?:sugar\s+free\s+)?(?:oral\s+)?'  # modifiers
        r'(?:capsule|tablet|powder|liquid|solution|sachet|injection|cream|gel|ointment|inhaler|spray|patch|drops?|suspension|syrup)[s]?)',
        re.IGNORECASE
    )

    # Pattern 3: NPF compound medications (UK specific)
    npf_re = re.compile(
        r'([a-z][a-z\s\-]+\s+compound\s+NPF)\s+'
        r'((?:sugar\s+free\s+)?(?:oral\s+)?(?:powder|liquid|solution|sachets?))',
        re.IGNORECASE
    )

    # Track medication section
    in_medication_section = False

    for line in lines:
        line = line.strip()
        if not line or len(line) < 5:
            continue

        # Detect medication section headers
        ll = line.lower()
        if "medication list" in ll or "continue taking" in ll or "your medication" in ll:
            in_medication_section = True
            continue

        # Pattern 1: Standard dose pattern
        m = dose_re.search(line)
        if m:
            name = m.group(1).strip().rstrip('-– ')
            dose = m.group(2).strip()
            if 3 < len(name) < 60:
                meds.append({"name": name, "dose": dose, "raw": line.strip()})
                continue

        # Pattern 2: Medication list format (in medication sections)
        if in_medication_section:
            m2 = med_list_re.match(line)
            if m2:
                name = m2.group(1).strip()
                dose = m2.group(2).strip()
                meds.append({"name": name, "dose": dose, "raw": line.strip()})
                continue

            # Pattern 3: NPF compounds
            m3 = npf_re.search(line)
            if m3:
                name = m3.group(1).strip()
                dose = m3.group(2).strip()
                meds.append({"name": name, "dose": dose, "raw": line.strip()})
                continue

    # Deduplicate by normalized name
    seen, out = set(), []
    for med in meds:
        key = med["name"].lower().replace("-", " ").strip()
        if key not in seen:
            seen.add(key)
            out.append(med)
    return out[:20]


def extract_structured_fields(text: str) -> dict:
    """Extract structured fields common across all 8 document types."""
    import re
    fields = {
        "admission_date": "", "discharge_date": "", "appointment_date": "",
        "consultant": "", "department": "", "hospital": "",
        "gp_actions": "", "diagnosis_text": "",
        "admission_method": "", "discharge_method": "",
        "procedure": "", "indication": "", "impression": "",
    }
    lines = text.split("\n")

    # First pass: look for Admission Details section with "Date:" format
    in_admission_section = False
    in_discharge_section = False
    for i, line in enumerate(lines):
        l = line.strip()
        ll = l.lower()

        # Track sections
        if "admission details" in ll:
            in_admission_section = True
            in_discharge_section = False
        elif "dischar" in ll and ("date:" in ll or "by:" in ll or "destination" in ll):
            in_discharge_section = True
            in_admission_section = False

        # Extract dates from "Date: DD/MM/YYYY" format (common in discharge summaries)
        if "date:" in ll and not fields["admission_date"] and in_admission_section:
            m = re.search(r'(\d{1,2}[/\.\-]\d{1,2}[/\.\-]\d{2,4})', l)
            if m:
                fields["admission_date"] = m.group(1)
        if "date:" in ll and not fields["discharge_date"] and in_discharge_section:
            m = re.search(r'(\d{1,2}[/\.\-]\d{1,2}[/\.\-]\d{2,4})', l)
            if m:
                fields["discharge_date"] = m.group(1)

        # Lead Consultant Speciality
        if "lead consultant special" in ll or "consultant special" in ll:
            m = re.search(r'(?:speciality|specialty)[:\s]+([A-Za-z][^\n]{2,40})', l, re.IGNORECASE)
            if m and not fields["department"]:
                fields["department"] = m.group(1).strip()

        # Consultant name - various formats
        if ("consultant" in ll and (":" in l or "," in l)) or "discharging consultant" in ll:
            # Format: "Consultant: Name, Role" or "Consultant , Name"
            m = re.search(r'consultant[,:\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)', l, re.IGNORECASE)
            if m and not fields["consultant"]:
                fields["consultant"] = m.group(1).strip()

    # Second pass: standard field extraction
    for i, line in enumerate(lines):
        l = line.strip()
        ll = l.lower()
        # Dates - standard format
        if re.search(r'(?i)admission date', ll) and not fields["admission_date"]:
            m = re.search(r'(\d{1,2}[/\.\-]\d{1,2}[/\.\-]\d{2,4})', l)
            if m: fields["admission_date"] = m.group(1)
        if re.search(r'(?i)discharge date', ll) and not fields["discharge_date"]:
            m = re.search(r'(\d{1,2}[/\.\-]\d{1,2}[/\.\-]\d{2,4})', l)
            if m: fields["discharge_date"] = m.group(1)
        if re.search(r'(?i)appointment.?date', ll):
            m = re.search(r'(\d{1,2}[/\.\-]\d{1,2}[/\.\-]\d{2,4})', l)
            if m: fields["appointment_date"] = m.group(1)
        # Consultant
        if re.search(r'(?i)discharging consultant|consultant[:\s]|lead professional', ll):
            m = re.search(r'(?:consultant|lead professional)[:\s]+([A-Z][^\n,]{3,50})', l, re.IGNORECASE)
            if m and not fields["consultant"]: fields["consultant"] = m.group(1).strip()
        # Department
        if re.search(r'(?i)discharging specialty|department[:\s]|specialty[:\s]', ll):
            m = re.search(r'(?:specialty|department)[:\s]+([A-Za-z][^\n]{3,40})', l, re.IGNORECASE)
            if m and not fields["department"]: fields["department"] = m.group(1).strip()
        # Admission/discharge method
        if re.search(r'(?i)admission method', ll):
            m = re.search(r'admission method[:\s]+([^\n]{3,60})', l, re.IGNORECASE)
            if m: fields["admission_method"] = m.group(1).strip()
        if re.search(r'(?i)discharge method', ll):
            m = re.search(r'discharge method[:\s]+([^\n]{3,60})', l, re.IGNORECASE)
            if m: fields["discharge_method"] = m.group(1).strip()
        # Procedure
        if re.search(r'(?i)procedure[:\(]|procedure\s*date', ll):
            nxt = lines[i+1].strip() if i+1 < len(lines) else ""
            if nxt and len(nxt) > 3: fields["procedure"] = nxt[:120]
        # Indication (endoscopy reports)
        if re.search(r'(?i)^indication', ll):
            nxt = lines[i+1].strip() if i+1 < len(lines) else ""
            if nxt: fields["indication"] = nxt[:200]
        # Impression
        if re.search(r'(?i)^overall impression|^impression', ll):
            nxt = lines[i+1].strip() if i+1 < len(lines) else ""
            if nxt: fields["impression"] = nxt[:300]
        # GP Actions
        if re.search(r'(?i)actions.*(gp|general practice)|gp.actions', ll):
            nxt = (lines[i+1].strip() if i+1 < len(lines) else "") or l
            fields["gp_actions"] = nxt[:300]
        # Diagnosis text
        if re.search(r'(?i)^diagnosis|^post.op diagnosis', ll):
            nxt = lines[i+1].strip() if i+1 < len(lines) else ""
            if nxt and not fields["diagnosis_text"]: fields["diagnosis_text"] = nxt[:200]
    return fields


def extract_patient_info(text: str) -> dict:
    """Extract patient demographics — handles all document formats seen in batches 1-4."""
    import re
    info = {
        "name": "", "nhs_number": "", "dob": "", "sex": "",
        "address": "", "hospital_number": "", "gp_practice": "",
        "pathways_urgency": "", "presenting_complaint": "",
        "gravida_parity": "", "edd": "", "gestational_age": "",
    }
    lines = text.split("\n")

    for i, line in enumerate(lines):
        l = line.strip()
        ll = l.lower()

        # ── Name ──────────────────────────────────────────────────────────────
        if not info["name"]:
            # Standard: "Re: SURNAME, Forename"
            m = re.search(r'(?i)(?:RE:|RE patient:|Patient(?:\s+Name)?:|Patient Surname.*?:|Name:)\s*(?:(Mr|Mrs|Ms|Miss)\.?\s+)?(?:Dr\.?\s+)?([A-Z][A-Za-z,\s\-]{2,50})', l)
            if m:
                title = (m.group(1) or "").lower()
                info["name"] = re.sub(r'\s+', ' ', m.group(2).strip().rstrip(','))
                if not info["sex"]:
                    if title == "mr":
                        info["sex"] = "Male"
                    elif title in ("mrs", "ms", "miss"):
                        info["sex"] = "Female"
            # 111 format: standalone "SURNAME, Forename" on its own line after DOB line
            # Guard rails: avoid header/identifier lines like "MRN Number: 5653424".
            elif (
                re.match(r'^[A-Z]{2,}[,\s]+[A-Z][a-z]', l)
                and ":" not in l
                and not re.search(r'\d', l)
                and not any(x in ll for x in ['nhs', 'hospital', 'road', 'street', 'lane', 'avenue', 'drive', 'mrn', 'number', 'pas', 'id'])
            ):
                if len(l.split()) <= 4:
                    info["name"] = l

        # ── NHS number ────────────────────────────────────────────────────────
        if not info["nhs_number"]:
            m = re.search(r'(?i)NHS\s*(?:No|Number|#|:)?[:\s]*(\d[\d\s]{8,12}\d)', l)
            if m:
                info["nhs_number"] = re.sub(r'\s+', ' ', m.group(1).strip())
            else:
                # 111 format: "NHS Number\n462 213 3695" (next line)
                if re.search(r'(?i)^NHS\s*Number\s*$', l) and i + 1 < len(lines):
                    nxt = lines[i + 1].strip()
                    if re.match(r'^[\d\s]{9,12}$', nxt):
                        info["nhs_number"] = nxt.strip()

        # ── DOB ───────────────────────────────────────────────────────────────
        if not info["dob"]:
            # Standard: "DOB: 16/3/1975" or "Date of birth: 17.06.1987"
            m = re.search(r'(?i)(?:D\.?\s*O\.?\s*B\.?|DOB|Date of birth)[:\s]+(\d{1,2}[/\.\-]\d{1,2}[/\.\-]\d{2,4}|\d{1,2}\s+\w+\s+\d{4})', l)
            if m:
                info["dob"] = m.group(1).strip()
            else:
                # 111 format: "Born 22-Feb-1996" or "Born: 22-Feb-1996"
                m = re.search(r'(?i)\bBorn[:\s]+(\d{1,2}[\-\/]\w+[\-\/]\d{4}|\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4})', l)
                if m: info["dob"] = m.group(1).strip()
                elif re.search(r'(?i)^(?:D\.?\s*O\.?\s*B\.?|DOB|Date of birth)[:\s]*$', l) and i + 1 < len(lines):
                    nxt = lines[i + 1].strip()
                    if re.search(r'\d{1,2}[/\.\-]\d{1,2}[/\.\-]\d{2,4}|\d{1,2}\s+\w+\s+\d{4}', nxt):
                        info["dob"] = nxt

        # ── Sex / Gender ──────────────────────────────────────────────────────
        if not info["sex"]:
            m = re.search(r'(?i)(?:Gender|Sex|Legal Sex)[:\s,]+(Male|Female|M\b|F\b)', l)
            if m:
                g = m.group(1).upper()
                info["sex"] = "Male" if g.startswith("M") else "Female"
            elif re.search(r'\bGender:\s*Female\b|\bfemale\b', l, re.IGNORECASE): info["sex"] = "F"
            elif re.search(r'\bGender:\s*Male\b',   l, re.IGNORECASE):            info["sex"] = "M"
            else:
                # OCR-tolerant fallback: "Ma'e", "Femal", "Fema1e", etc.
                mg = re.search(r'(?i)(?:Gender|Sex|Legal Sex)\s*[:\s,]+([A-Za-z\'`]{1,12})', l)
                if mg:
                    token = re.sub(r'[^A-Za-z]', '', mg.group(1)).lower()
                    if token.startswith('m'):
                        info["sex"] = "Male"
                    elif token.startswith('f'):
                        info["sex"] = "Female"

        # ── Hospital / MRN / PAS ──────────────────────────────────────────────
        if not info["hospital_number"]:
            m = re.search(r'(?i)(?:MRN(?:\s*(?:No|Number))?|Hospital\s*(?:No|Number)|PAS\s*ID)\s*[:#]?\s*([A-Z0-9]{4,})', l)
            if m: info["hospital_number"] = m.group(1).strip()

        # ── GP Practice ───────────────────────────────────────────────────────
        if not info["gp_practice"]:
            m = re.search(r'(?i)(?:GP\s*Practice|Surgery)[:\s]+([A-Za-z][^\n]{3,50})', l)
            if m: info["gp_practice"] = m.group(1).strip()

        # ── 111 Pathways urgency ──────────────────────────────────────────────
        if not info["pathways_urgency"] and re.search(r'(?i)pathways disposition|refer to.*within', ll):
            nxt = lines[i + 1].strip() if i + 1 < len(lines) else ""
            info["pathways_urgency"] = (nxt or l)[:120]

        # ── Presenting complaint ──────────────────────────────────────────────
        if not info["presenting_complaint"]:
            m = re.search(r'(?i)(?:Complaint|Reason for (?:contact|referral|admission))[:\s]+([^\n]{5,150})', l)
            if m: info["presenting_complaint"] = m.group(1).strip()

        # ── Gravida / Parity (antenatal / gynae) ──────────────────────────────
        if not info["gravida_parity"]:
            m = re.search(r'\b(G\s*\d+\s*P\s*\d+)\b', l)
            if m: info["gravida_parity"] = m.group(1).replace(" ", "")

        # ── EDD (Estimated Delivery Date) ─────────────────────────────────────
        # Skip any parenthetical abbreviation e.g. "(EDD)" before the actual date
        if not info["edd"]:
            m = re.search(r'(?i)(?:EDD|Estimated?\s+Delivery\s+Date)(?:\s*\([^)]*\))?\s*[:\s]+(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})', l)
            if not m:  # date may be on next line — try broader capture
                m = re.search(r'(?i)(?:EDD|Estimated?\s+Delivery\s+Date)(?:\s*\([^)]*\))?\s*[:\s]+([^\n(]{3,20})', l)
            if m:
                val = m.group(1).strip().rstrip(')')
                if val and not val.lower().startswith('('):
                    info["edd"] = val

        # ── EGA (Estimated Gestational Age) ───────────────────────────────────
        if not info["gestational_age"]:
            m = re.search(r'(?i)(?:EGA|Estimated?\s+Gestational\s+Age|Gestational\s+Age)(?:\s*\([^)]*\))?\s*[:\s]+(\d[^\n(]{2,20})', l)
            if m:
                val = m.group(1).strip().rstrip(')')
                if val:
                    info["gestational_age"] = val

        # ── Expert Health format: name/DOB in letter body "Re: MR/MISS Name" ─
        if not info["name"]:
            m = re.search(r'(?i)^Re:\s*(?:MR|MRS|MISS|MS|DR)\.?\s+([A-Za-z][^\n]{3,50})', l)
            if m:
                raw = m.group(1).strip()
                # Next few lines have address, DOB may be 3rd line pattern
                info["name"] = raw

    # Second pass: handle forms where labels and values are on separate lines.
    if lines:
        for i, line in enumerate(lines[:-1]):
            l = line.strip()
            nxt = lines[i + 1].strip()
            if not nxt:
                continue
            if not info["name"] and re.search(r'(?i)^(?:Patient\s*Name|Name)\s*$', l):
                if not re.search(r'(?i)\b(nhs|number|date|birth|sex|gender)\b', nxt):
                    info["name"] = nxt
            if not info["nhs_number"] and re.search(r'(?i)^NHS\s*Number\s*$', l):
                if re.search(r'^\d[\d\s]{8,14}\d$', nxt):
                    info["nhs_number"] = nxt
            if not info["dob"] and re.search(r'(?i)^Date\s*of\s*Birth\s*$', l):
                if re.search(r'\d{1,2}[/\.\-]\d{1,2}[/\.\-]\d{2,4}|\d{1,2}\s+\w+\s+\d{4}', nxt):
                    info["dob"] = nxt
            if not info["sex"] and re.search(r'(?i)^Sex$|^Gender$', l):
                if re.search(r'(?i)^M(ale)?$', nxt):
                    info["sex"] = "Male"
                elif re.search(r'(?i)^F(emale)?$', nxt):
                    info["sex"] = "Female"

    # Third pass: global OCR-variant fallback for DOB and title-based sex.
    if not info["dob"]:
        m = re.search(r'(?is)(?:D\W*O\W*B|DOB|Date\W*of\W*Birth)\W*[:\-]?\W*(\d{1,2}[\/\.\-]\d{1,2}[\/\.\-]\d{2,4}|\d{1,2}\s+\w+\s+\d{4})', text)
        if m:
            info["dob"] = m.group(1).strip()
    if not info["sex"]:
        if re.search(r'(?i)\bMr\.?\s+[A-Z][a-z]+', text):
            info["sex"] = "Male"
        elif re.search(r'(?i)\b(?:Mrs|Ms|Miss)\.?\s+[A-Z][a-z]+', text):
            info["sex"] = "Female"

    # Fourth pass: infer DOB from standalone date immediately after patient name block
    # (common in private prescriber letters where DOB is on its own line).
    if not info["dob"] or info["dob"] == "Not available":
        for i, line in enumerate(lines):
            l = line.strip()
            if re.search(r'(?i)\b(?:Re|Patient(?:\s+Name)?)\s*[:\-]', l):
                window = lines[i + 1:i + 8]
                for cand in window:
                    c = cand.strip()
                    if re.search(r'^\d{1,2}[\/\.\-]\d{1,2}[\/\.\-]\d{4}$', c):
                        # Skip obvious letter/prescription dates; prefer patient-block standalone date.
                        if not re.search(r'(?i)(date|prescribed|referral)', (lines[i-1] if i > 0 else "") + " " + c):
                            info["dob"] = c
                            break
                if info["dob"] and info["dob"] != "Not available":
                    break

    # Normalise any remaining short sex codes.
    if info["sex"] == "M":
        info["sex"] = "Male"
    elif info["sex"] == "F":
        info["sex"] = "Female"

    # Final sanitiser: reject identifier text accidentally captured as name.
    if info["name"] and re.search(r'(?i)\b(mrn|nhs|number|hospital|pas\s*id)\b', info["name"]):
        info["name"] = ""
    if not info["name"]:
        m = re.search(r'(?im)^\s*Name\s*:\s*([A-Za-z][A-Za-z\'\-\s]{1,60})\s*$', text)
        if m:
            info["name"] = re.sub(r'\s+', ' ', m.group(1).strip())

    # Ensure patient info panel never appears empty.
    if not info["name"]:
        info["name"] = "Not available"
    if not info["nhs_number"]:
        info["nhs_number"] = "Not available"
    if not info["dob"]:
        info["dob"] = "Not available"
    if not info["sex"]:
        info["sex"] = "Not available"

    return info


def infer_patient_sex_from_context(text: str, summaries: dict | None = None) -> str:
    """Infer sex only when clear directional signals exist; else return empty string."""
    import re
    src = (text or "")
    lower = src.lower()

    # Highest confidence signals from source text.
    if re.search(r'(?i)\b(?:gender|sex|legal sex)\s*[:\s,]+m(?:ale)?\b', src):
        return "Male"
    if re.search(r'(?i)\b(?:gender|sex|legal sex)\s*[:\s,]+f(?:emale)?\b', src):
        return "Female"

    male_hits = 0
    female_hits = 0

    male_hits += len(re.findall(r'(?i)\b(?:mr)\.?\s+[A-Z][a-z]+\b', src))
    female_hits += len(re.findall(r'(?i)\b(?:mrs|ms|miss)\.?\s+[A-Z][a-z]+\b', src))

    # Pronoun cues from document text.
    male_hits += len(re.findall(r'(?i)\b(?:he|his|him)\b', src))
    female_hits += len(re.findall(r'(?i)\b(?:she|her|hers)\b', src))

    if male_hits > 0 and female_hits == 0:
        return "Male"
    if female_hits > 0 and male_hits == 0:
        return "Female"

    # Last resort: use generated summaries only if they are unambiguous.
    s = ""
    if summaries:
        s = " ".join(
            [
                (summaries.get("clinician", {}) or {}).get("summary", ""),
                (summaries.get("patient", {}) or {}).get("summary", ""),
                (summaries.get("pharmacist", {}) or {}).get("summary", ""),
            ]
        ).lower()
    if s:
        s_male = len(re.findall(r'\b(?:male patient| he | his | him )\b', f" {s} "))
        s_female = len(re.findall(r'\b(?:female patient| she | her | hers )\b', f" {s} "))
        if s_male > 0 and s_female == 0:
            return "Male"
        if s_female > 0 and s_male == 0:
            return "Female"

    return ""


def extract_clinical_specifics(text: str, letter_type: str) -> dict:
    """
    Extract type-specific clinical data for the supported document/letter types
    identified by `letter_type` (e.g. from infer_letter_type()).
    Returns a dict of extra fields shown in the right panel and Coding tab.
    Supported types are defined in config/document_type_config.py.
    """
    import re
    extras = {}
    t  = text
    tl = t.lower()

    # ── 111 First ED Report ────────────────────────────────────────────────────
    if "111" in letter_type:
        # Differential diagnosis (marked with ??)
        diffs = re.findall(r'\?\??\s*([A-Za-z][^\n\?]{3,60})', t)
        if diffs: extras["differential_diagnosis"] = " / ".join(d.strip() for d in diffs[:5])
        # Pathways urgency
        m = re.search(r'(?i)refer to a treatment centre within\s+([^\n]+)', t)
        if m: extras["urgency"] = m.group(1).strip()
        # Encounter type
        m = re.search(r'(?i)Encounter Type\s+([^\n]+)', t)
        if m: extras["encounter_type"] = m.group(1).strip()
        # Doctor name
        m = re.search(r'(?i)Clinical Summary by (?:DOCTOR|DR\.?)\s+([^\n]+)', t)
        if m: extras["assessing_clinician"] = m.group(1).strip()

    # ── Cancer Surveillance ────────────────────────────────────────────────────
    if "Cancer" in letter_type or "Surveillance" in letter_type:
        # TNM staging
        m = re.search(r'(p?T\d+\s*N\d+[^\n]{0,30})', t)
        if m: extras["tnm_staging"] = m.group(1).strip()
        # CEA
        m = re.search(r'(?i)CEA[:\s]+([\d\.]+)', t)
        if m: extras["cea_value"] = m.group(1)
        # Surveillance schedule
        m = re.search(r'(?i)surveillance[:\s]+([^\n]{10,120})', t)
        if m: extras["surveillance_schedule"] = m.group(1).strip()
        # Treatment history
        m = re.search(r'(?i)(hemicolectomy|colectomy|chemotherapy|radiotherapy)[^\n]{0,80}', t)
        if m: extras["treatment_history"] = m.group(0).strip()

    # ── HIV / GUM ─────────────────────────────────────────────────────────────
    if "HIV" in letter_type or "GUM" in letter_type:
        # CD4
        m = re.search(r'(?i)CD4[/\s]?(?:count)?[:\s]+([\d,]+\s*cells?/m[cμ]?[Ll]?)', t)
        if m: extras["cd4_count"] = m.group(1).strip()
        # Viral load
        m = re.search(r'(?i)(?:HIV\s+)?viral\s+load[:\s]+([^\n]{3,40})', t)
        if m: extras["viral_load"] = m.group(1).strip()
        # ART regimen
        m = re.search(r'(?i)(?:antiretroviral|ART)\s+medication[^\n]{0,20}\n([^\n]{5,120})', t)
        if m: extras["art_regimen"] = m.group(1).strip()
        # Follow up
        m = re.search(r'(?i)follow[- ]?up[:\s]+([^\n]{5,100})', t)
        if m: extras["follow_up"] = m.group(1).strip()

    # ── Maternity / Diabetes ──────────────────────────────────────────────────
    if "Maternity" in letter_type or "Diabetes" in letter_type:
        # OGTT results
        m = re.search(r'(?i)(?:glucose tolerance|ogtt)[^\n]*\n?[^\n]*0\s*mins?\s*=\s*([\d\.]+)[^\n]*120\s*mins?\s*=\s*([\d\.]+)', t, re.DOTALL)
        if m: extras["ogtt_results"] = f"0min={m.group(1)} / 120min={m.group(2)}"
        # Monitoring frequency
        m = re.search(r'(?i)test[^\n]*(\d+)\s*times?\s*per\s*day', t)
        if m: extras["monitoring_frequency"] = f"{m.group(1)} times/day"
        # Equipment prescribed
        pips = re.findall(r'([A-Za-z][^\n]{5,60}PIP\s*Code[:\s]+([\d\-]+))', t)
        if pips: extras["equipment_pip"] = "; ".join(f"{p[0].split('PIP')[0].strip()} ({p[1]})" for p in pips[:3])

    # ── Surgical Outpatient ───────────────────────────────────────────────────
    if "Surgical" in letter_type:
        m = re.search(r'(?i)(?:^|\n)Plan[:\s]+([^\n]{5,200})', t)
        if m: extras["surgical_plan"] = m.group(1).strip()
        m = re.search(r'(?i)(?:^|\n)Action for\s*GP[:\s]+([^\n]{3,100})', t)
        if m: extras["action_for_gp"] = m.group(1).strip()

    # ── Haematology ───────────────────────────────────────────────────────────
    if "Haematology" in letter_type:
        # Lab results table
        labs = re.findall(r'(HGB|WBC|PLT|CREATININE|HB|HbA1c|eGFR)[:\s]+([\d\.]+)', t, re.IGNORECASE)
        if labs: extras["key_labs"] = {k.upper(): v for k, v in labs}
        m = re.search(r'(?i)paraprotein[^\n]{0,60}', t)
        if m: extras["paraprotein"] = m.group(0).strip()

    # ── Ophthalmology Referral (Evolutio / eRefer) ───────────────────────────
    if "Ophthalmology Referral" in letter_type:
        m = re.search(r'(?i)referral reason[:\s]+([^\n]{5,100})', t)
        if m: extras["referral_reason"] = m.group(1).strip()
        m = re.search(r'(?i)pathway\s*/?\s*clinic[:\s]+([^\n]{5,100})', t)
        if m: extras["referral_pathway"] = m.group(1).strip()
        m = re.search(r'(?i)(?:triager|referer) action required[:\s]+([^\n]{3,30})', t)
        if m: extras["priority"] = m.group(1).strip()
        m = re.search(r'(?i)patient chosen provider[:\s]+([^\n]{3,80})', t)
        if m: extras["provider"] = m.group(1).strip()
        m = re.search(r'(?i)referred by[:\s]+([^\n]{5,80})', t)
        if m: extras["referred_by"] = m.group(1).strip()
        # Visual acuity
        m = re.search(r'(?i)visual acuity\s*R[:\s]+([^\s]+)\s+L[:\s]+([^\s\n]+)', t)
        if m: extras["visual_acuity"] = f"R: {m.group(1)}  L: {m.group(2)}"
        # IOP
        m = re.search(r'(?i)right iop[^\d]*([\d\.]+)[^\d]*left iop[^\d]*([\d\.]+)', t)
        if m: extras["iop"] = f"R: {m.group(1)} mmHg  L: {m.group(2)} mmHg"

    # ── Ophthalmology Outpatient / Medical Retina ─────────────────────────────
    if "Ophthalmology Letter" in letter_type:
        # Retinopathy grading (R2M1P0 style)
        grades = re.findall(r'\b(R\d+[AM]?\s*M\d+\s*P\d+)\b', t)
        if grades: extras["retinopathy_grade"] = " / ".join(dict.fromkeys(grades))
        # Visual acuity per eye
        m = re.search(r'(?i)right\s+([\d/\.]+)[^\n]{0,20}left\s+([\d/\.]+)', t)
        if m: extras["visual_acuity"] = f"R: {m.group(1)}  L: {m.group(2)}"
        # IOP
        m = re.search(r'(?i)(?:right|R)\s+([\d]+)\s*mmhg[^\n]{0,10}(?:left|L)\s+([\d]+)\s*mmhg', t, re.IGNORECASE)
        if m: extras["iop"] = f"R: {m.group(1)} mmHg  L: {m.group(2)} mmHg"
        # Diagnosis
        m = re.search(r'(?i)diagnosis[:\s]+([^\n]{5,120})', t)
        if m: extras["ophthalmic_diagnosis"] = m.group(1).strip()
        # PRP / laser
        m = re.search(r'(?i)(prp|panretinal|retinal laser)[^\n]{0,100}', t)
        if m: extras["laser_treatment"] = m.group(0).strip()
        # Plan
        m = re.search(r'(?i)^plan[:\s]+([^\n]{5,200})', t, re.MULTILINE)
        if m: extras["ophthalmic_plan"] = m.group(1).strip()
        # NVD/NVE
        if re.search(r'(?i)(nvd|nvealisation|neovascularisation)', t):
            extras["neovascularisation"] = "Detected"

    # ── Renal / Nephrology ────────────────────────────────────────────────────
    if "Renal" in letter_type or "Nephrology" in letter_type:
        # Inline lab panel (format: "eGFR\n23" or "eGFR 23")
        lab_keys = ["egfr", "creatinine", "albumin", "potassium", "haemoglobin", "urea",
                    "bicarbonate", "pth intact", "albumin creatinine ratio", "white blood cell"]
        labs = {}
        lines = t.split("\n")
        for i, line in enumerate(lines):
            ll = line.lower().strip()
            for k in lab_keys:
                if k in ll:
                    # value may be on same line or next
                    m = re.search(r'([\d\.]+)', line)
                    if not m and i + 1 < len(lines):
                        m = re.search(r'([\d\.]+)', lines[i + 1])
                    if m:
                        labs[k.replace(" ", "_")] = m.group(1)
        if labs: extras["renal_labs"] = labs
        m = re.search(r'(?i)review.*?week beginning\s+([^\n\.]{5,30})', t)
        if m: extras["next_review"] = m.group(1).strip()

    # ── Paediatric Cardiology ─────────────────────────────────────────────────
    if "Paediatric Cardiology" in letter_type:
        m = re.search(r'(?i)diagnosis[:\s]+([^\n]{5,120})', t)
        if m: extras["cardiac_diagnosis"] = m.group(1).strip()
        m = re.search(r'(?i)(?:heart rate|bpm|beats per minute)[^\n]{0,60}(\d{3})', t)
        if m: extras["max_heart_rate"] = m.group(1) + " bpm"
        m = re.search(r'(?i)(?:ablation|ep mdt|electrophysiology)[^\n]{0,100}', t)
        if m: extras["planned_procedure"] = m.group(0).strip()
        m = re.search(r'(?i)medication[:\s]+([^\n]{5,100})', t)
        if m: extras["current_medication"] = m.group(1).strip()

    # ── Early Pregnancy / Gynaecology ─────────────────────────────────────────
    if "Pregnancy" in letter_type or "Gynaecology" in letter_type:
        m = re.search(r'(?i)(G\s*\d+\s*P\s*\d+)', t)
        if m: extras["gravida_parity"] = m.group(1).replace(" ","")
        m = re.search(r'(?i)LMP[:\s]+([^\n]{3,30})', t)
        if m: extras["lmp"] = m.group(1).strip()
        m = re.search(r'(?i)(?:mean sac diameter|gestational sac)[^\n]{0,30}([\d\.]+\s*mm)', t)
        if m: extras["gestational_sac"] = m.group(1).strip()
        m = re.search(r'(?i)(?:fetal pole)[:\s]+([^\n]{3,60})', t)
        if m: extras["fetal_pole"] = m.group(1).strip()
        m = re.search(r'(?i)diagnosis[:\s]+([^\n]{5,120})', t)
        if m: extras["scan_diagnosis"] = m.group(1).strip()
        m = re.search(r'(?i)plan[:\s]+([^\n]{5,200})', t)
        if m: extras["follow_up_plan"] = m.group(1).strip()

    # ── Antenatal Discharge Summary ───────────────────────────────────────────
    if "Antenatal" in letter_type:
        # EDD — skip any "(EDD)" parenthetical, capture the actual date value
        m = re.search(r'(?i)(?:EDD|Estimated?\s+Delivery\s+Date)(?:\s*\([^)]*\))?\s*[:\s]+(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})', t)
        if not m:
            m = re.search(r'(?i)(?:EDD|Estimated?\s+Delivery\s+Date)(?:\s*\([^)]*\))?\s*[:\s]+([^\n(]{3,20})', t)
        if m:
            val = m.group(1).strip().rstrip(')')
            if val and not val.lower().startswith('('):
                extras["edd"] = val
        # EGA — skip "(EGA)" parenthetical, capture weeks+days e.g. "29+1 weeks"
        m = re.search(r'(?i)(?:EGA|Estimated?\s+Gestational\s+Age)(?:\s*\([^)]*\))?\s*[:\s]+(\d[^\n(]{2,20})', t)
        if m:
            val = m.group(1).strip().rstrip(')')
            if val:
                extras["gestational_age"] = val
        m = re.search(r'(?i)Gravida\s*&?\s*Parity[:\s]+([^\n]{2,10})', t)
        if m: extras["gravida_parity"] = m.group(1).strip()
        m = re.search(r'(?i)reason for (?:visit|admission)[:\s]+([^\n]{5,150})', t)
        if m: extras["reason_for_visit"] = m.group(1).strip()

    # ── Mental Health Inpatient Discharge ─────────────────────────────────────
    if "Mental Health Inpatient" in letter_type:
        m = re.search(r'(?i)(?:section\s*\d+|legal status)[^\n]{0,60}', t)
        if m: extras["mha_section"] = m.group(0).strip()
        m = re.search(r'(?i)diagnosis[:\s]+([^\n]{5,120})', t)
        if m: extras["primary_diagnosis"] = m.group(1).strip()
        m = re.search(r'(?i)(?:date of admission|admitted)[:\s]+([^\n]{3,30})', t)
        if m: extras["admission_date"] = m.group(1).strip()
        m = re.search(r'(?i)(?:date of discharge|discharged)[:\s]+([^\n]{3,30})', t)
        if m: extras["discharge_date"] = m.group(1).strip()
        # Medication monitoring (lithium, clozapine etc)
        meds_monitor = re.findall(r'(?i)(lithium|clozapine|olanzapine)[^\n]{0,80}', t)
        if meds_monitor: extras["medication_monitoring"] = meds_monitor[0].strip()
        m = re.search(r'(?i)(crhtt|cmht|crisis)[^\n]{0,100}', t)
        if m: extras["community_follow_up"] = m.group(0).strip()

    # ── Pre-admission Letter ──────────────────────────────────────────────────
    if "Pre-admission" in letter_type:
        m = re.search(r'(?i)date[:\s]+(\d{1,2}[/\.\-]\d{1,2}[/\.\-]\d{2,4})', t)
        if m: extras["admission_date"] = m.group(1).strip()
        m = re.search(r'(?i)speciality[:\s]+([^\n]{3,50})', t)
        if m: extras["speciality"] = m.group(1).strip()
        m = re.search(r'(?i)clinician[:\s]+([^\n]{3,60})', t)
        if m: extras["clinician"] = m.group(1).strip()
        m = re.search(r'(?i)location[:\s]+([^\n]{3,80})', t)
        if m: extras["location"] = m.group(1).strip()
        m = re.search(r'(?i)do not eat after\s+([^\n\.]{3,30})', t)
        if m: extras["fasting_from"] = m.group(1).strip()

    # ── Ambulance Clinical Report ─────────────────────────────────────────────
    if "Ambulance" in letter_type:
        m = re.search(r'(?i)incident number[:\s]+([^\n]{3,30})', t)
        if m: extras["incident_number"] = m.group(1).strip()
        m = re.search(r'(?i)(?:main symptom|presenting complaint)[:\s]+([^\n]{5,120})', t)
        if m: extras["presenting_complaint"] = m.group(1).strip()
        m = re.search(r'(?i)(?:working impression|impression)[:\s]+([^\n]{5,100})', t)
        if m: extras["working_impression"] = m.group(1).strip()
        m = re.search(r'(?i)news2 score[:\s]*([\d]+)', t)
        if m: extras["news2_score"] = m.group(1)
        m = re.search(r'(?i)conveyance[:\s]+([^\n]{5,100})', t)
        if m: extras["conveyance"] = m.group(1).strip()
        m = re.search(r'(?i)(?:differential diagnosis|differential)[:\s]+([^\n]{3,80})', t)
        if m: extras["differential_diagnosis"] = m.group(1).strip()
        # Extract first vital signs row: pulse, SpO2, BP, temp
        m = re.search(r'(?i)pulse\s+(\d+).*?spo.?\s+(\d+)', t, re.DOTALL)
        if m: extras["first_vitals"] = f"Pulse {m.group(1)} SpO2 {m.group(2)}%"

    # ── ED Discharge Letter ───────────────────────────────────────────────────
    if "ED Discharge" in letter_type:
        m = re.search(r'(?i)attendance reason[:\s]+([^\n]{3,100})', t)
        if m: extras["attendance_reason"] = m.group(1).strip()
        m = re.search(r'(?i)(?:arrival method|mode of arrival)[:\s]+([^\n]{3,80})', t)
        if m: extras["arrival_method"] = m.group(1).strip()
        m = re.search(r'(?i)diagnosis[:\s]+([^\n]{3,120})', t)
        if m: extras["ed_diagnosis"] = m.group(1).strip()
        m = re.search(r'(?i)discharge method[:\s]+([^\n]{3,80})', t)
        if m: extras["discharge_method"] = m.group(1).strip()
        m = re.search(r'(?i)examined by[:\s]+([^\n]{3,120})', t)
        if m: extras["examined_by"] = m.group(1).strip()

    # ── All: extract GP practice address from letter header ──────────────────
    m = re.search(r'(?i)(?:JA?\s+\w+\s+\[GP\]|Dear\s+Dr\s+\w+)[^\n]{0,5}\n([^\n]{5,60})\n([^\n]{5,60})', t)
    if m: extras["gp_address"] = f"{m.group(1).strip()}, {m.group(2).strip()}"

    return extras


def run_full_pipeline(doc_id: str, upload_path: Path) -> dict:
    """
    End-to-end auto pipeline (SRS §7 workflow).

    Handles PDF, TIFF, JPEG, PNG via the production module stack:
      Tier 0 : document_handler.prepare_document() → preprocessing.preprocess_image()
      Tier 1 : AWS Textract (confidence-scored per page)
      Tier 2 : if avg Textract confidence < 90% → flag for LayoutLMv3 review queue
      Track A: Comprehend Medical SNOMED + hipaa_compliance PHI detection
      Track B: Bedrock (Claude) role-based summarisation with per-type prompts
      UCS    : Weighted unified confidence → routing decision (per-type threshold)
    """
    result = {
        "doc_id": doc_id,
        "filename": upload_path.name,
        "processed_at": datetime.now().isoformat(),
        "status": "processing",
        "pipeline_stages": {},
        "requires_review": False,
        "pages_processed": 0,
    }

    # ── Tier 0a: Multi-format ingestion (SRS §3.1 / document_handler.py) ──────
    # document_handler.prepare_document() supports PDF, TIFF, JPEG, PNG.
    work_dir = UPLOAD_DIR / doc_id
    work_dir.mkdir(exist_ok=True)
    try:
        image_paths = _prepare_pages(upload_path, work_dir)
        tier0_note  = (
            f"document_handler: {len(image_paths)} page(s) from {upload_path.suffix.upper()}"
            if _HAS_DOCUMENT_HANDLER
            else f"fallback: {len(image_paths)} page(s) from {upload_path.suffix.upper()}"
        )
    except Exception as e:
        result["status"] = "error"
        result["error"]  = f"Document ingestion failed: {e}"
        return result

    # ── Tier 0b: OpenCV preprocessing (SRS §3.1 Tier 0 — preprocessing.py) ───
    # Adaptive thresholding + morphological noise reduction + deskewing.
    image_paths = _run_tier0_preprocessing(image_paths, work_dir)
    tier0_note += (" | OpenCV preprocessing: "
                   + ("applied" if _HAS_PREPROCESSING else "skipped (cv2 unavailable)"))
    result["pipeline_stages"]["tier0"] = {"status": "done", "note": tier0_note}

    result["pages_processed"] = len(image_paths)

    # ── Scrollable preview: original page images (BEFORE OpenCV preprocessing) ─
    # Always use PyMuPDF directly for preview so:
    #   (a) all pages are captured (document_handler sometimes returns only 1)
    #   (b) the user sees the ORIGINAL scan, not the brightened/thresholded version
    orig_preview_paths = []
    try:
        import fitz as _fitz
        _ext = upload_path.suffix.lower()
        if _ext == ".pdf":
            _doc = _fitz.open(str(upload_path))
            _mat = _fitz.Matrix(1.5, 1.5)   # 1.5× zoom — good balance of quality vs size
            for _i, _pg in enumerate(_doc):
                _pix  = _pg.get_pixmap(matrix=_mat)
                _dest = work_dir / f"orig_{_i+1:02d}.png"
                _pix.save(str(_dest))
                orig_preview_paths.append(_dest)
        else:
            # Images (JPEG/PNG/TIFF) — copy original directly for preview
            _dest = work_dir / f"orig_01{upload_path.suffix}"
            if not _dest.exists():
                shutil.copy(str(upload_path), str(_dest))
            orig_preview_paths.append(_dest)
    except Exception:
        # Fallback: use whatever the pipeline already generated
        orig_preview_paths = [p for p in image_paths if p.exists()]

    result["preview_pages"] = [
        f"/pages/{doc_id}/{p.name}" for p in orig_preview_paths if p.exists()
    ]
    result["preview_image"] = result["preview_pages"][0] if result["preview_pages"] else None

    # ── Tier 1: Textract per page, concatenate ────────────────────────────────
    all_text    = []
    all_confs   = []
    try:
        for img in image_paths:
            t = run_textract(img)
            if t["text"].strip():
                all_text.append(t["text"])
                all_confs.append(t["confidence"])
        doc_text      = "\n\n".join(all_text)
        textract_conf = (sum(all_confs) / len(all_confs)) if all_confs else 0.5

        # ── Tier 2 routing (SRS §7 step 3): flag low-confidence docs ──────────
        # SRS §3.1: docs with avg confidence < 90% route to LayoutLMv3.
        # In the portal (synchronous) context we flag for the review queue
        # rather than invoking LayoutLMv3 inline (which requires batch infrastructure).
        tier2_needed = textract_conf < 0.90
        result["pipeline_stages"]["tier1"] = {
            "status": "done",
            "confidence": round(textract_conf, 3),
            "pages": len(image_paths),
            "chars_extracted": len(doc_text),
        }
        result["pipeline_stages"]["tier2"] = {
            "status": "queued_for_layoutlmv3" if tier2_needed else "skipped",
            "note": (
                "Textract confidence < 90% — document routed to LayoutLMv3 refinement queue"
                if tier2_needed
                else "Textract confidence >= 90% — direct to Track A/B (SRS §7 step 2)"
            ),
        }
    except Exception as e:
        result["pipeline_stages"]["tier1"] = {"status": "error", "error": str(e)}
        result["status"] = "error"
        result["error"]  = f"Textract failed: {e}"
        return result

    if not doc_text.strip():
        result["status"] = "error"
        result["error"]  = "No text could be extracted from document"
        return result

    # ── Document Structure Detection (Clinical Engine) ────────────────────────
    # Detect sections BEFORE entity extraction to provide context
    detected_sections = []
    if _HAS_CLINICAL_ENGINE:
        try:
            detected_sections = detect_document_sections(doc_text)
            result["pipeline_stages"]["structure"] = {
                "status": "done",
                "sections_found": len(detected_sections),
                "section_types": [s.section_type.value for s in detected_sections],
            }
            import sys
            print(f"[DEBUG] Document sections detected: {[s.section_type.value for s in detected_sections]}", file=sys.stderr)
        except Exception as e:
            result["pipeline_stages"]["structure"] = {"status": "partial", "error": str(e)}
            import sys
            print(f"[WARN] Document structure detection failed: {e}", file=sys.stderr)

    # ── Track A: SNOMED + ICD + medications ───────────────────────────────────
    try:
        snomed = run_comprehend_medical(doc_text)
        result["pipeline_stages"]["track_a"] = {
            "status": "done",
            "entities_found": len(snomed["entities"]),
            "confidence": round(snomed["snomed_confidence"], 3),
            "validation_warnings": snomed.get("validation_warnings", []),
        }
    except Exception as e:
        snomed = {"entities": [], "problems": [], "medications": [], "diagnoses": [], "snomed_confidence": 0.3}
        result["pipeline_stages"]["track_a"] = {"status": "partial", "error": str(e)}

    # ── HIPAA PHI detection (SRS §5.2 / hipaa_compliance.py) ─────────────────
    # detect_phi_entities() uses Comprehend Medical's detect_phi API to surface
    # all Protected Health Information entities for audit trail and compliance.
    phi_entities: list = []
    if _HAS_HIPAA:
        try:
            phi_entities = _detect_phi(doc_text)
            result["pipeline_stages"]["hipaa"] = {
                "status": "done",
                "phi_entities_detected": len(phi_entities),
                "note": "PHI detection via hipaa_compliance.detect_phi_entities()",
            }
        except Exception as e:
            result["pipeline_stages"]["hipaa"] = {"status": "partial", "error": str(e)}
    else:
        result["pipeline_stages"]["hipaa"] = {
            "status": "skipped",
            "note": "hipaa_compliance module unavailable — PHI detection bypassed",
        }

    # Enrich with local ICD + medication extraction (works without AWS)
    icd_codes   = extract_icd_codes(doc_text)
    medications = extract_medications(doc_text)
    # Extract demographics before summary generation so prompts can prefer
    # sex-based wording ("male/female patient") instead of age.
    patient_info = extract_patient_info(doc_text)

    # ── Document type classification (needed before Track B for type-specific prompts) ──
    letter_type   = infer_letter_type(doc_text)

    # ── Comprehensive Extraction (Claude Sonnet 5) ──────────────────────────────
    # Extract all structured fields in one call for maximum accuracy
    try:
        comprehensive = run_comprehensive_extraction(doc_text, letter_type)
        result["pipeline_stages"]["extraction"] = {
            "status": "done",
            "fields_extracted": len([k for k, v in comprehensive.items() if v]),
        }
    except Exception as e:
        comprehensive = {}
        result["pipeline_stages"]["extraction"] = {"status": "error", "error": str(e)}

    # ── Track B: Summarization ─────────────────────────────────────────────────
    try:
        summaries = run_bedrock_summarization(doc_text, snomed, letter_type, patient_info.get("sex", ""))
        result["pipeline_stages"]["track_b"] = {
            "status": "done",
            "confidence": round(summaries["llm_confidence"], 3),
            "letter_type": letter_type,
        }
    except Exception as e:
        result["pipeline_stages"]["track_b"] = {"status": "error", "error": str(e)}
        result["status"] = "error"
        result["error"]  = f"Summarization failed: {e}"
        return result

    # Fill missing sex from clear context cues so Patient Info does not stay blank
    # on letters that omit an explicit Gender/Sex field.
    if (patient_info.get("sex") or "").strip().lower() in ("", "not available"):
        inferred_sex = infer_patient_sex_from_context(doc_text, summaries)
        if inferred_sex:
            patient_info["sex"] = inferred_sex

    # ── SNOMED top-up: diagnosis-focused only (no generic doctype seeding) ───
    # Runs AFTER Track B so clinician summary can still recover missed condition
    # concepts, but we do not inject hardcoded document-type procedure codes.
    _has_snomed = bool(snomed.get("problems") or snomed.get("medications") or snomed.get("diagnoses"))

    if not _has_snomed:
        # Layer 1: Run InferSNOMEDCT on the LLM clinician summary.
        # The summary is structured clinical prose — far richer signal than raw OCR.
        _clin_summary = summaries.get("clinician", {}).get("summary", "")
        if _clin_summary and len(_clin_summary.strip()) > 40:
            try:
                _summ_snomed = run_comprehend_medical(_clin_summary)
                if _summ_snomed.get("problems") or _summ_snomed.get("medications") or _summ_snomed.get("diagnoses"):
                    snomed["problems"]    = _summ_snomed["problems"]
                    snomed["medications"] = _summ_snomed["medications"]
                    snomed["diagnoses"]   = _summ_snomed["diagnoses"]
                    snomed["entities"]    = _summ_snomed["entities"]
                    snomed["snomed_confidence"] = _summ_snomed["snomed_confidence"]
                    snomed["used_summary_fallback"] = True
                    _has_snomed = True
                    result["pipeline_stages"]["track_a"]["note"] = "SNOMED mapped from clinician summary (primary OCR text yielded 0 entities)"
            except Exception:
                pass

    if not _has_snomed:
        snomed["problems"]          = []
        snomed["medications"]       = []
        snomed["diagnoses"]         = []
        snomed["used_doctype_fallback"] = False
        result["pipeline_stages"]["track_a"]["note"] = "No diagnosis-focused SNOMED concepts detected from document text"

    # ── Confidence aggregation ─────────────────────────────────────────────────
    unified    = compute_unified_confidence(textract_conf, snomed["snomed_confidence"], summaries["llm_confidence"], letter_type)
    # OBS-004: Use per-type threshold — ambulance/ophthalmology referral docs legitimately score lower
    type_threshold = get_confidence_threshold(letter_type)
    result["unified_confidence"]   = round(unified, 3)
    result["confidence_threshold"] = type_threshold
    result["requires_review"]      = unified < type_threshold

    # ── OBS-008: Identify originating hospital trust ──────────────────────────
    hospital_trust = extract_hospital_trust(doc_text)

    # ── Structured field extraction ────────────────────────────────────────────
    struct_fields   = extract_structured_fields(doc_text)
    clinical_extras = extract_clinical_specifics(doc_text, letter_type)

    # OBS-010: Decode Frimley arrival method code if present
    if struct_fields.get("admission_method"):
        struct_fields["admission_method"] = resolve_arrival_method(struct_fields["admission_method"])

    result["status"]            = "processed" if not result["requires_review"] else "review_required"
    result["letter_type"]       = letter_type
    result["hospital_trust"]    = hospital_trust          # OBS-008
    result["is_sensitive"]      = contains_sensitive_content(doc_text)   # OBS-007
    result["patient_info"]      = patient_info
    result["structured"]        = struct_fields
    result["clinical_specifics"]= clinical_extras   # type-specific extras (TNM, CD4, OGTT, etc.)
    result["extracted_text"]    = doc_text[:8000]   # cap for JSON response
    result["icd_codes"]         = icd_codes
    result["medications_raw"]   = medications
    result["snomed"]            = {
        "problems":               snomed["problems"],
        "treatments":             snomed["treatments"],
        "medications":            snomed["medications"],
        "investigations":         snomed["investigations"],
        "diagnoses":              snomed["diagnoses"],
        "all_entities":           snomed.get("all_entities", [])[:30],
        "snomed_confidence":      snomed.get("snomed_confidence", 0),
        "used_fallback":          snomed.get("used_fallback", False),
        "top3_fallback":          snomed.get("top3_fallback", []),
        "used_summary_fallback":  snomed.get("used_summary_fallback", False),
        "used_doctype_fallback":  snomed.get("used_doctype_fallback", False),
    }
    result["summaries"]           = summaries

    # ── Merge comprehensive extraction into actions_structured ──────────────────
    base_actions = summaries.get("actions_structured", {
        "sender_actions":    {"doctor": [], "pharmacist": [], "reception": []},
        "gp_surgery_actions":{"doctor": [], "pharmacist": [], "reception": []},
    })

    # Merge GP actions from comprehensive extraction (Claude Sonnet 5) - these are often more accurate
    # Only add if comprehensive extraction found actions and base is empty
    if comprehensive.get("actions_gp_doctor") and not base_actions["gp_surgery_actions"]["doctor"]:
        base_actions["gp_surgery_actions"]["doctor"] = comprehensive.get("actions_gp_doctor", [])
    if comprehensive.get("actions_gp_pharmacist") and not base_actions["gp_surgery_actions"]["pharmacist"]:
        base_actions["gp_surgery_actions"]["pharmacist"] = comprehensive.get("actions_gp_pharmacist", [])
    if comprehensive.get("actions_gp_reception") and not base_actions["gp_surgery_actions"]["reception"]:
        base_actions["gp_surgery_actions"]["reception"] = comprehensive.get("actions_gp_reception", [])

    # Add patient-specific action categories from comprehensive extraction
    base_actions["patient_actions"] = comprehensive.get("actions_patient", [])
    base_actions["patient_booking"] = comprehensive.get("actions_patient_booking", [])
    result["actions_structured"]  = base_actions

    result["follow_up_actions"]   = summaries.get("follow_up_actions", "")

    # ── Comprehensive extraction results ────────────────────────────────────────
    # Fallback to structured fields if comprehensive extraction returned empty
    result["event_date"]          = comprehensive.get("event_date", "") or struct_fields.get("admission_date", "")
    result["letter_date"]         = comprehensive.get("letter_date", "") or struct_fields.get("discharge_date", "") or struct_fields.get("appointment_date", "")
    result["conclusion"]          = comprehensive.get("conclusion", "")
    result["recommendation"]      = comprehensive.get("recommendation", "")
    result["diary_events"]        = comprehensive.get("diary_events", [])

    # Debug logging for comprehensive extraction
    import sys
    print(f"[DEBUG] Comprehensive extraction: event_date={result['event_date']}, letter_date={result['letter_date']}, diary_events={len(result['diary_events'])}", file=sys.stderr)

    # ── Enhanced SNOMED with treatments/investigations from comprehensive extraction ──
    result["treatments"]          = comprehensive.get("treatments", [])
    result["investigations"]      = comprehensive.get("investigations", [])

    # Merge comprehensive diagnoses/problems if richer than Comprehend Medical results
    if comprehensive.get("diagnoses") and len(comprehensive["diagnoses"]) > len(snomed.get("diagnoses", [])):
        result["snomed"]["diagnoses_enhanced"] = comprehensive["diagnoses"]
    if comprehensive.get("problems") and len(comprehensive["problems"]) > len(snomed.get("problems", [])):
        result["snomed"]["problems_enhanced"] = comprehensive["problems"]
    if comprehensive.get("medications"):
        result["snomed"]["medications_enhanced"] = comprehensive["medications"]

    # HIPAA audit trail (SRS §5.2, §6.2): surface PHI count for compliance logging
    result["phi_entity_count"]   = len(phi_entities)

    # ── Clinical Validation Stage ────────────────────────────────────────────────
    # Final validation to catch consistency issues and improve accuracy
    if _HAS_CLINICAL_ENGINE:
        try:
            validator = ClinicalValidationEngine()
            consistency_warnings = validator.validate_consistency(
                [],  # We validate the raw entities earlier, this checks sections
                detected_sections
            )
            if consistency_warnings:
                result["validation_warnings"] = consistency_warnings
                import sys
                print(f"[DEBUG] Clinical validation warnings: {consistency_warnings}", file=sys.stderr)

            result["pipeline_stages"]["validation"] = {
                "status": "done",
                "warnings_count": len(consistency_warnings),
            }
        except Exception as e:
            result["pipeline_stages"]["validation"] = {"status": "partial", "error": str(e)}
            import sys
            print(f"[WARN] Clinical validation stage failed: {e}", file=sys.stderr)

    # ── Component-Level Confidence Scoring ───────────────────────────────────────
    # Provide detailed confidence breakdown for explainability
    if _HAS_CLINICAL_ENGINE:
        confidence_breakdown = ConfidenceScore(
            ocr_quality=textract_conf,
            layout_detection=0.8 if detected_sections else 0.5,
            entity_extraction=snomed.get("snomed_confidence", 0.5),
            entity_classification=0.75,  # Classification confidence
            clinical_coding=snomed.get("snomed_confidence", 0.5),
            validation=0.85 if not result.get("validation_warnings") else 0.70,
        )
        confidence_breakdown.compute_overall()
        result["confidence_breakdown"] = confidence_breakdown.to_dict()

    return result


# ── Routes ────────────────────────────────────────────────────────────────────

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Document Extraction Portal</title>
<link rel="icon" href="https://www.nhs.uk/nhschoicesContent/app/images/nhs-logo.png">
<style>
*{box-sizing:border-box;margin:0;padding:0;font-family:'Segoe UI',Arial,sans-serif}
:root{--nhs-blue:#005EB8;--nhs-dark:#003087;--nhs-warm:#768692;--nhs-green:#009639;--nhs-red:#DA291C;--nhs-yellow:#FFB81C;--bg:#f0f4f8;--card:#fff;--border:#d8dde0;--text:#212b32;--muted:#4c6272}
body{background:var(--bg);color:var(--text);min-height:100vh}

/* Sidebar */
.sidebar{position:fixed;left:0;top:0;bottom:0;width:64px;background:var(--nhs-dark);display:flex;flex-direction:column;align-items:center;padding:12px 0;z-index:100}
.sidebar-icon{width:44px;height:44px;border-radius:8px;display:flex;align-items:center;justify-content:center;cursor:pointer;margin-bottom:4px;color:#fff;opacity:.7;transition:.2s;font-size:20px;text-decoration:none}
.sidebar-icon:hover,.sidebar-icon.active{opacity:1;background:rgba(255,255,255,.15)}
.sidebar-logo{width:44px;height:44px;background:var(--nhs-blue);border-radius:8px;display:flex;align-items:center;justify-content:center;margin-bottom:16px;font-weight:900;color:#fff;font-size:14px;letter-spacing:-.5px}

/* Top bar */
.topbar{position:fixed;left:64px;right:0;top:0;height:52px;background:#fff;border-bottom:2px solid var(--nhs-blue);display:flex;align-items:center;padding:0 20px;z-index:99;gap:12px}
.topbar-title{font-size:15px;font-weight:600;color:var(--nhs-dark);flex:1}
.topbar-user{font-size:13px;color:var(--muted);display:flex;align-items:center;gap:8px}
.avatar{width:32px;height:32px;border-radius:50%;background:var(--nhs-blue);color:#fff;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:13px}

/* Main layout */
.main{margin-left:64px;margin-top:52px;display:flex;height:calc(100vh - 52px)}

/* Upload panel */
#upload-panel{width:100%;padding:32px;display:flex;flex-direction:column;align-items:center;justify-content:center}
.upload-card{background:#fff;border-radius:12px;border:2px dashed var(--nhs-blue);padding:48px;max-width:560px;width:100%;text-align:center;cursor:pointer;transition:.2s}
.upload-card:hover{border-color:var(--nhs-dark);background:#f5f9ff}
.upload-icon{font-size:48px;margin-bottom:16px;color:var(--nhs-blue)}
.upload-card h2{color:var(--nhs-dark);margin-bottom:8px}
.upload-card p{color:var(--muted);font-size:14px;margin-bottom:20px}
.btn-primary{background:var(--nhs-blue);color:#fff;border:none;padding:10px 24px;border-radius:6px;font-size:14px;font-weight:600;cursor:pointer;transition:.2s}
.btn-primary:hover{background:var(--nhs-dark)}
.supported{font-size:12px;color:var(--muted);margin-top:12px}

/* Processing spinner */
#processing-panel{width:100%;display:none;flex-direction:column;align-items:center;justify-content:center;padding:32px}
.spinner{width:56px;height:56px;border:5px solid #e0eaf5;border-top:5px solid var(--nhs-blue);border-radius:50%;animation:spin 1s linear infinite;margin-bottom:24px}
@keyframes spin{to{transform:rotate(360deg)}}
.pipeline-steps{background:#fff;border-radius:10px;padding:20px 28px;max-width:420px;width:100%;margin-top:16px}
.step{display:flex;align-items:center;gap:12px;padding:8px 0;font-size:14px;color:var(--muted)}
.step.done{color:var(--nhs-green)}
.step.active{color:var(--nhs-blue);font-weight:600}
.step.error{color:var(--nhs-red)}
.step-dot{width:10px;height:10px;border-radius:50%;background:currentColor;flex-shrink:0}

/* Result view */
#result-panel{width:100%;display:none;flex-direction:row;overflow:hidden}

/* Left: doc viewer */
.doc-viewer{flex:1.2;background:#fff;border-right:1px solid var(--border);display:flex;flex-direction:column;overflow:hidden}
.doc-viewer-header{padding:12px 16px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:10px}
.doc-viewer-header h3{font-size:14px;color:var(--nhs-dark);font-weight:600}
.doc-img{flex:1;overflow-y:auto;padding:0;background:#f0f0f0;display:flex;flex-direction:column;align-items:center}
#doc-pages-inner{width:100%;padding:14px;box-sizing:border-box}

/* Center: details */
.details-panel{width:400px;border-right:1px solid var(--border);display:flex;flex-direction:column;overflow:hidden}
.details-header{padding:12px 16px;border-bottom:1px solid var(--border)}
.details-header h3{font-size:14px;color:var(--nhs-dark);font-weight:600}
.tab-content{flex:1;overflow-y:auto;padding:16px}
.tab-pane{display:none}
.tab-pane.active{display:block}
/* Anima-style pill tabs */
.tabs{display:flex;gap:6px;padding:10px 12px 0 12px;border-bottom:1px solid var(--border);background:#f8fafc;flex-wrap:wrap;align-items:center}
.tab{padding:7px 14px;font-size:12px;font-weight:600;cursor:pointer;color:var(--muted);border:1px solid var(--border);border-radius:999px;background:#fff;transition:.15s;white-space:nowrap;margin-bottom:8px}
.tab:hover{border-color:#93c5fd;color:var(--nhs-blue)}
.tab.active{color:#fff;background:var(--nhs-blue);border-color:var(--nhs-blue);box-shadow:0 1px 4px rgba(0,94,184,.22)}
.pseudo-select{border:1px solid var(--border);border-radius:8px;padding:8px 10px;font-size:12px;color:var(--muted);background:#fff;margin-bottom:4px;cursor:default}
.coding-section-head{display:flex;align-items:center;justify-content:space-between;margin:14px 0 8px 0}
.coding-section-head .field-label{margin:0}
.coding-clear{font-size:11px;color:#94a3b8;cursor:not-allowed}
.coding-head-icons{display:flex;align-items:center;gap:10px;color:#64748b;font-size:14px}
.coding-head-ico{cursor:pointer;user-select:none;line-height:1}
.coding-head-ico:hover{color:var(--nhs-blue)}
.coding-group-title{font-size:11px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:.4px;margin:14px 0 6px}
.coding-group-title:first-child{margin-top:0}
.coding-code-card{background:linear-gradient(135deg,#faf5ff 0%,#fff 55%);border:1px solid #e9d5ff;border-left:4px solid #a855f7;border-radius:10px;padding:10px 12px;margin-bottom:8px;font-size:13px;position:relative}
/* Per-semantic-type accent on the left border so cards read like the Anima screenshots */
.coding-code-card.sem-disorder {border-left-color:#ef4444;border-color:#fecaca;background:linear-gradient(135deg,#fef2f2,#fff 55%)}
.coding-code-card.sem-finding  {border-left-color:#f59e0b;border-color:#fde68a;background:linear-gradient(135deg,#fffbeb,#fff 55%)}
.coding-code-card.sem-procedure{border-left-color:#0ea5e9;border-color:#bae6fd;background:linear-gradient(135deg,#f0f9ff,#fff 55%)}
.coding-code-card.sem-situation{border-left-color:#8b5cf6;border-color:#ddd6fe;background:linear-gradient(135deg,#f5f3ff,#fff 55%)}
.coding-code-card.sem-event    {border-left-color:#22c55e;border-color:#bbf7d0;background:linear-gradient(135deg,#f0fdf4,#fff 55%)}
.coding-code-card.sem-substance,
.coding-code-card.sem-product  {border-left-color:#2563eb;border-color:#bfdbfe;background:linear-gradient(135deg,#eff6ff,#fff 55%)}
/* Active problem card styling */
.active-problem-card{border:1px solid #e2e8f0;border-left:4px solid #ef4444;border-radius:10px;padding:12px 14px;margin:10px 0 6px 0;background:#fff}
.active-problem-card .apc-title-row{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.active-problem-card .apc-title{font-weight:700;color:#1e293b;font-size:14px}
.active-problem-card .apc-chip{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.4px;padding:2px 7px;border-radius:10px}
.active-problem-card .apc-chip.major{background:#fee2e2;color:#b91c1c}
.active-problem-card .apc-chip.active{background:#dcfce7;color:#166534}
.active-problem-card .apc-code{font-family:ui-monospace,monospace;font-size:11px;color:var(--nhs-blue);font-weight:600;margin-top:4px}
.active-problem-card .apc-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:10px}
.active-problem-card .apc-field-label{font-size:10px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:.4px;margin-bottom:3px}
.active-problem-card .apc-field-value{font-size:13px;color:#1e293b;border:1px solid #e2e8f0;border-radius:6px;padding:6px 8px;background:#fff}
.active-problem-card .apc-field-select{font-size:13px;color:#1e293b;border:1px solid #e2e8f0;border-radius:6px;padding:6px 8px;background:#fff;width:100%;cursor:pointer}
.coding-code-card .card-top{display:flex;justify-content:space-between;align-items:flex-start;gap:8px}
.coding-code-card .card-title{font-weight:700;color:#1e293b}
.coding-code-card .card-menu{color:#94a3b8;font-size:14px;letter-spacing:1px;user-select:none}
.coding-code-num{font-family:ui-monospace,monospace;font-size:11px;color:var(--nhs-blue);font-weight:600;margin-top:4px}
.coding-snippet{font-size:11px;color:#64748b;font-style:italic;margin-top:6px;line-height:1.45;word-break:break-word}
.task-block{border:1px solid var(--border);border-radius:10px;margin-bottom:10px;background:#fff;overflow:hidden}
.task-block-h{display:flex;justify-content:space-between;align-items:center;padding:10px 12px;font-size:12px;font-weight:700;color:#334155;background:#f8fafc;border-bottom:1px solid var(--border)}
.task-block-body{padding:12px;font-size:13px}
.muted-empty{color:var(--muted);font-size:13px;font-style:italic}
.task-suggest-card{border-radius:10px;padding:12px 14px;margin-bottom:10px;border:1px solid #e9d5ff;border-left:4px solid #7c3aed;background:linear-gradient(135deg,#faf5ff,#fff)}
.task-suggest-card.gp{border-left-color:#2563eb;background:linear-gradient(135deg,#eff6ff,#fff);border-color:#bfdbfe}
.task-suggest-card .badge-row{font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:.5px;color:#6b21a8;margin-bottom:6px}
.task-suggest-card.gp .badge-row{color:#1d4ed8}
.task-suggest-card p{margin:0;line-height:1.5;color:#334155;font-size:13px}
.task-suggest-card .add-row{margin-top:10px;text-align:right}
.role-action-group{margin-bottom:12px}
.role-label{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;padding:3px 9px;border-radius:4px;display:inline-block;margin-bottom:6px}
.role-label.role-doctor{background:#dbeafe;color:#1d4ed8}
.role-label.role-pharmacist{background:#d1fae5;color:#065f46}
.role-label.role-reception{background:#fef3c7;color:#92400e}
.role-action-list .task-suggest-card{margin-bottom:7px}
.btn-add-mini{background:#fff;border:1px solid var(--nhs-blue);color:var(--nhs-blue);font-size:12px;font-weight:600;padding:5px 14px;border-radius:6px;cursor:pointer}
.btn-add-mini:hover{background:#eff6ff}
.fake-link{font-size:11px;font-weight:600;color:var(--nhs-blue);text-decoration:none;cursor:default}
.sheet-section{border:1px solid var(--border);border-radius:10px;margin-bottom:12px;background:#fff;overflow:hidden}
.sheet-section-head{width:100%;text-align:left;padding:10px 12px;font-size:12px;font-weight:700;color:#334155;background:#f8fafc;border:none;border-bottom:1px solid var(--border);cursor:pointer;display:flex;justify-content:space-between;align-items:center}
.sheet-section-body{padding:8px 10px 12px;display:none}
.sheet-section-body.open{display:block}
.sheet-primary-row{width:100%;text-align:left;padding:10px 12px;margin:4px 0;border:1px solid var(--border);border-radius:8px;background:#fff;font-size:13px;cursor:pointer;display:flex;align-items:center;gap:10px}
.sheet-primary-row:hover{border-color:var(--nhs-blue);background:#f0f7ff}
.sheet-row{width:100%;text-align:left;padding:8px 12px;margin:2px 0;border:none;background:transparent;font-size:13px;color:var(--text);cursor:pointer;border-radius:6px;display:flex;align-items:center;gap:10px}
.sheet-row:hover{background:#f1f5f9}
.snomed-table-details{margin-top:10px}
.snomed-table-disclosure{font-size:11px;font-weight:700;color:var(--muted);cursor:pointer;padding:6px 0;background:none;border:none;text-align:left;width:100%;font:inherit;display:flex;align-items:center;gap:6px}
.snomed-table-disclosure:hover{color:var(--nhs-blue)}
.snomed-table-details.open .snomed-table-disclosure{color:var(--nhs-blue)}
.snomed-table-details-body{display:none;margin-top:0}
.snomed-table-details.open .snomed-table-details-body{display:block}
.snomed-disclosure-chev{font-size:10px;color:var(--muted)}
.snomed-table-details.open .snomed-disclosure-chev{color:var(--nhs-blue)}

/* Summary box */
.summary-box{background:#f0f7ff;border-left:3px solid var(--nhs-blue);border-radius:4px;padding:12px;margin-bottom:16px;font-size:13px;line-height:1.6;color:var(--text);position:relative}
.summary-box .copy-btn{position:absolute;top:8px;right:8px;background:none;border:none;cursor:pointer;color:var(--muted);font-size:14px}

/* Form fields */
.field-group{margin-bottom:14px}
.field-label{font-size:11px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px}
.field-value{font-size:13px;color:var(--text)}
.field-input{width:100%;border:1px solid var(--border);border-radius:4px;padding:6px 10px;font-size:13px;color:var(--text)}
.field-input:focus{outline:none;border-color:var(--nhs-blue)}
.section-title{font-size:12px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin:16px 0 8px}

/* Status badges */
.badge{display:inline-flex;align-items:center;gap:4px;padding:3px 10px;border-radius:12px;font-size:12px;font-weight:600}
.badge-processed{background:#e6f7ef;color:#00703c}
.badge-review{background:#fff3e0;color:#c77700}
.badge-error{background:#fdecea;color:#c62828}

/* Confidence bar */
.conf-bar-wrap{background:#e8ecef;border-radius:4px;height:6px;margin-top:4px;overflow:hidden}
.conf-bar{height:100%;border-radius:4px;transition:width .5s}
.conf-high{background:var(--nhs-green)}
.conf-mid{background:var(--nhs-yellow)}
.conf-low{background:var(--nhs-red)}

/* SNOMED chips */
.snomed-chip{display:inline-flex;align-items:center;gap:6px;background:#f0f7ff;border:1px solid #c2d9ef;border-radius:16px;padding:4px 10px;font-size:12px;margin:3px;cursor:default}
.snomed-code{font-family:monospace;font-weight:700;color:var(--nhs-blue)}
.entity-section{margin-bottom:12px}
.entity-section-label{font-size:11px;font-weight:700;color:var(--muted);text-transform:uppercase;margin-bottom:6px}

/* Actions list */
.action-item{display:flex;align-items:flex-start;gap:8px;padding:8px 0;border-bottom:1px solid var(--border);font-size:13px}
.action-num{width:20px;height:20px;background:var(--nhs-blue);color:#fff;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;flex-shrink:0;margin-top:1px}

/* Right panel */
.right-panel{width:280px;background:#fff;overflow-y:auto;padding:0}
.right-section{border-bottom:1px solid var(--border);padding:14px 16px}
.right-section-title{font-size:12px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:10px;display:flex;align-items:center;justify-content:space-between}
.info-row{display:flex;flex-direction:column;margin-bottom:8px}
.info-label{font-size:11px;color:var(--muted)}
.info-value{font-size:13px;color:var(--text);font-weight:500}

/* Bottom action bar */
.action-bar{padding:10px 16px;border-top:1px solid var(--border);background:#fff;display:flex;gap:8px;flex-wrap:wrap}
.btn-sm{padding:7px 14px;border-radius:5px;font-size:13px;font-weight:600;cursor:pointer;border:none;transition:.2s}
.btn-outline{background:#fff;border:1px solid var(--border);color:var(--text)}
.btn-outline:hover{border-color:var(--nhs-blue);color:var(--nhs-blue)}
.btn-success{background:var(--nhs-green);color:#fff}
.btn-success:hover{opacity:.9}
.btn-emis{background:var(--nhs-blue);color:#fff}
.btn-emis:hover{background:var(--nhs-dark)}

/* Expandable */
.expand-toggle{display:flex;align-items:center;justify-content:space-between;cursor:pointer;padding:6px 0}
.expand-body{display:none;padding-top:6px}
.expand-body.open{display:block}
.chevron{transition:.2s;display:inline-block}
.chevron.open{transform:rotate(180deg)}

/* Alert banner */
.alert{padding:10px 14px;border-radius:6px;font-size:13px;margin-bottom:12px;display:flex;align-items:center;gap:8px}
.alert-warn{background:#fff3e0;color:#c77700;border:1px solid #ffe0a3}
.alert-success{background:#e6f7ef;color:#00703c;border:1px solid #b3e8cf}

/* New upload button */
.new-upload-btn{position:fixed;bottom:24px;right:24px;background:var(--nhs-blue);color:#fff;border:none;padding:12px 20px;border-radius:8px;font-size:14px;font-weight:600;cursor:pointer;box-shadow:0 4px 12px rgba(0,93,184,.3);z-index:200;display:none}
.new-upload-btn:hover{background:var(--nhs-dark)}
</style>
</head>
<body>

<!-- Sidebar -->
<div class="sidebar">
  <div class="sidebar-logo">NHS</div>
  <a class="sidebar-icon active" title="Dashboard">🏠</a>
  <a class="sidebar-icon" title="Documents">📄</a>
  <a class="sidebar-icon" title="Users">👥</a>
  <a class="sidebar-icon" title="Sync">🔄</a>
  <a class="sidebar-icon" title="Mail">✉️</a>
  <div style="flex:1"></div>
  <a class="sidebar-icon" title="Profile">👤</a>
</div>

<!-- Top bar -->
<div class="topbar">
  <div class="topbar-title" id="topbar-title">Document Extraction Portal</div>
  <div class="topbar-user">
    <span>Admin A A</span>
    <div class="avatar">AA</div>
  </div>
</div>

<!-- Main -->
<div class="main">

  <!-- UPLOAD PANEL -->
  <div id="upload-panel">
    <div class="upload-card" id="drop-zone">
      <div class="upload-icon">📋</div>
      <h2>Upload Clinical Document</h2>
      <p>Drop a medical document here or click to browse.<br>The pipeline runs fully automatically.</p>
      <button class="btn-primary" onclick="document.getElementById('file-input').click()">Choose Document</button>
      <input type="file" id="file-input" accept=".jpg,.jpeg,.png,.pdf,.tiff,.tif" style="display:none">
      <p class="supported">Supported: JPEG, PNG, PDF, TIFF</p>
    </div>
    <div style="margin-top:32px;max-width:560px;width:100%">
      <div class="section-title" style="text-align:center">Pipeline Overview</div>
      <div style="display:flex;justify-content:center;gap:0;margin-top:12px">
        <div style="text-align:center;padding:0 12px">
          <div style="font-size:22px">📷</div>
          <div style="font-size:11px;font-weight:600;color:var(--nhs-blue);margin-top:4px">Tier 0</div>
          <div style="font-size:11px;color:var(--muted)">Preprocess</div>
        </div>
        <div style="color:var(--border);padding-top:16px;font-size:18px">→</div>
        <div style="text-align:center;padding:0 12px">
          <div style="font-size:22px">🔍</div>
          <div style="font-size:11px;font-weight:600;color:var(--nhs-blue);margin-top:4px">Tier 1</div>
          <div style="font-size:11px;color:var(--muted)">Textract OCR</div>
        </div>
        <div style="color:var(--border);padding-top:16px;font-size:18px">→</div>
        <div style="text-align:center;padding:0 12px">
          <div style="font-size:22px">🧬</div>
          <div style="font-size:11px;font-weight:600;color:var(--nhs-blue);margin-top:4px">Track A</div>
          <div style="font-size:11px;color:var(--muted)">SNOMED Map</div>
        </div>
        <div style="color:var(--border);padding-top:16px;font-size:18px">→</div>
        <div style="text-align:center;padding:0 12px">
          <div style="font-size:22px">🤖</div>
          <div style="font-size:11px;font-weight:600;color:var(--nhs-blue);margin-top:4px">Track B</div>
          <div style="font-size:11px;color:var(--muted)">AI Summary</div>
        </div>
        <div style="color:var(--border);padding-top:16px;font-size:18px">→</div>
        <div style="text-align:center;padding:0 12px">
          <div style="font-size:22px">✅</div>
          <div style="font-size:11px;font-weight:600;color:var(--nhs-green);margin-top:4px">Result</div>
          <div style="font-size:11px;color:var(--muted)">Auto / Review</div>
        </div>
      </div>
    </div>
  </div>

  <!-- PROCESSING PANEL -->
  <div id="processing-panel">
    <div class="spinner"></div>
    <h3 style="color:var(--nhs-dark);margin-bottom:8px">Processing Document...</h3>
    <p style="color:var(--muted);font-size:13px;margin-bottom:20px">Running full clinical NLP pipeline</p>
    <div class="pipeline-steps">
      <div class="step done" id="step-upload"><div class="step-dot"></div>Document uploaded</div>
      <div class="step active" id="step-t0"><div class="step-dot"></div>Tier 0 — Image preprocessing</div>
      <div class="step" id="step-t1"><div class="step-dot"></div>Tier 1 — AWS Textract OCR</div>
      <div class="step" id="step-ta"><div class="step-dot"></div>Track A — SNOMED entity mapping</div>
      <div class="step" id="step-tb"><div class="step-dot"></div>Track B — AI summarization (Claude)</div>
      <div class="step" id="step-conf"><div class="step-dot"></div>Confidence aggregation &amp; routing</div>
    </div>
  </div>

  <!-- RESULT PANEL -->
  <div id="result-panel">
    <!-- Doc viewer -->
    <div class="doc-viewer">
      <div class="doc-viewer-header">
        <span style="font-size:16px">📄</span>
        <h3 id="doc-filename">Document</h3>
        <span id="doc-status-badge" class="badge badge-processed" style="margin-left:auto">Processed</span>
      </div>
      <div class="doc-img" id="doc-pages-container" style="flex-direction:column;align-items:center;gap:10px;padding:16px;overflow-y:auto">
        <!-- Pages rendered here by JS as scrollable strip -->
        <div id="doc-pages-inner" style="display:flex;flex-direction:column;gap:10px;width:100%;align-items:center">
          <span style="color:#aaa;font-size:13px">Upload a document to preview</span>
        </div>
      </div>
    </div>

    <!-- Details center panel -->
    <div class="details-panel">
      <div class="tabs">
        <div class="tab active" onclick="showTab(this,'details')">Details</div>
        <div class="tab" onclick="showTab(this,'coding')">Coding</div>
        <div class="tab" onclick="showTab(this,'tasks')">Follow-up</div>
        <div class="tab" onclick="showTab(this,'actions')">GP Actions</div>
      </div>
      <div class="tab-content">

        <!-- DETAILS TAB — narrative + letter metadata (Anima-style) -->
        <div class="tab-pane active" id="tab-details">
          <div id="review-alert" class="alert alert-warn" style="display:none">
            ⚠️ Confidence below threshold — outputs generated, please review before approving
          </div>
          <div id="auto-alert" class="alert alert-success" style="display:none">
            ✅ High confidence — document auto-processed successfully
          </div>

          <div class="field-group">
            <div class="field-label">Summary</div>
            <div class="summary-box" id="summary-main">
              <button class="copy-btn" onclick="copyText('summary-main')" title="Copy">📋</button>
              Loading...
            </div>
          </div>

          <div class="field-group">
            <div class="field-label" style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
              <span>Letter type</span>
              <span id="letter-type-pred-badge" style="display:none;font-size:10px;font-weight:700;letter-spacing:.3px;background:#e6f7ef;color:#00703c;border:1px solid #b3e8cf;padding:2px 8px;border-radius:10px;text-transform:none">Auto-detected</span>
              <span id="letter-type-override-badge" style="display:none;font-size:10px;font-weight:700;letter-spacing:.3px;background:#fff3e0;color:#c77700;border:1px solid #ffe0a3;padding:2px 8px;border-radius:10px;text-transform:none">Manual override</span>
            </div>
            <div id="letter-type-auto-line" style="display:none;font-size:11px;color:var(--muted);margin-bottom:6px">
              Predicted as <strong id="letter-type-raw" style="color:var(--nhs-dark)">—</strong>
              → bucketed to <strong id="letter-type-bucket" style="color:var(--nhs-dark)">—</strong>
              <a href="#" id="letter-type-reset" style="margin-left:6px;color:var(--nhs-blue);text-decoration:none;display:none">Reset to prediction</a>
            </div>
            <select class="field-input" id="field-letter-type" style="cursor:pointer;background:#fff">
              <option value="">Select letter type…</option>
              <option data-bucket-key="HOSP" value="Hospital Discharge Summary (after admission into hospital)">Hospital Discharge Summary (after admission into hospital)</option>
              <option data-bucket-key="CLIN" value="Clinical Letters/Report (after visiting specialists)">Clinical Letters/Report (after visiting specialists)</option>
              <option data-bucket-key="111"  value="111 Report (seeking advice from Clinician over phone)">111 Report (seeking advice from Clinician over phone)</option>
              <option data-bucket-key="ED"   value="Accident &amp; Emergency Department report">Accident &amp; Emergency Department report</option>
              <option data-bucket-key="AMB"  value="Ambulance Report (When emergency services are called)">Ambulance Report (When emergency services are called)</option>
              <option data-bucket-key="PRIV" value="Private Specialists clinical letter">Private Specialists clinical letter</option>
              <option data-bucket-key="EXT"  value="External service providers (Boots, Spec savers – for Eye &amp; ENT)">External service providers (Boots, Spec savers – for Eye &amp; ENT)</option>
              <option data-bucket-key="DES"  value="Diabetic eye screening reports">Diabetic eye screening reports</option>
              <option data-bucket-key="OOH"  value="Out of hours (East Berkshire Primary Care)">Out of hours (East Berkshire Primary Care)</option>
              <option data-bucket-key="MISC" value="Miscellaneous">Miscellaneous</option>
            </select>
            <div style="font-size:10px;color:var(--muted);margin-top:4px">Dropdown is a fallback override if the prediction is wrong.</div>
          </div>
          <div style="display:flex;gap:10px">
            <div class="field-group" style="flex:1">
              <div class="field-label">Event Date</div>
              <input class="field-input" id="field-event-date" placeholder="DD/MM/YYYY">
            </div>
            <div class="field-group" style="flex:1">
              <div class="field-label">Letter Date</div>
              <input class="field-input" id="field-letter-date" placeholder="DD/MM/YYYY">
            </div>
          </div>
          <div class="field-group">
            <div class="field-label">Sender Name</div>
            <input class="field-input" id="field-sender" placeholder="">
          </div>
          <div class="field-group">
            <div class="field-label">Consultant Name</div>
            <input class="field-input" id="field-consultant" placeholder="">
          </div>
          <div class="field-group">
            <div class="field-label">Department</div>
            <input class="field-input" id="field-dept" placeholder="">
          </div>

          <div class="field-group" style="margin-top:16px">
            <div class="field-label">Conclusion</div>
            <textarea class="field-input" id="field-conclusion" rows="3" placeholder="None" style="resize:vertical"></textarea>
          </div>

          <div class="field-group" style="margin-top:16px">
            <div class="field-label">Recommendation</div>
            <textarea class="field-input" id="field-recommendation" rows="3" placeholder="None" style="resize:vertical"></textarea>
          </div>

          <div class="field-group" style="margin-top:16px">
            <div class="field-label">Diary Events (Follow-up Schedule)</div>
            <div id="diary-events-list" style="font-size:13px;color:#334155"></div>
          </div>
        </div>

        <!-- CODING TAB — problems, code cards, SNOMED table (Anima-style) -->
        <div class="tab-pane" id="tab-coding">
          <div class="coding-section-head">
            <div class="field-label" style="margin:0">Problems</div>
            <div class="coding-head-icons">
              <span class="coding-head-ico" title="History">🕐</span>
              <span class="coding-head-ico" title="Refresh">↻</span>
            </div>
          </div>
          <div class="pseudo-select">Add an existing or new problem</div>

          <div id="coding-active-problem"></div>

          <div class="coding-section-head">
            <div class="field-label" style="margin:0">Codes</div>
            <span class="coding-clear">Clear section</span>
          </div>
          <div class="pseudo-select" style="margin-bottom:10px">Add a code</div>
          <div id="coding-entity-cards"></div>

          <div class="snomed-table-details">
            <button type="button" class="snomed-table-disclosure" onclick="toggleSnomedDetails(this)" aria-expanded="false">
              <span class="snomed-disclosure-chev">▸</span>
              <span>Full SNOMED CT mapping table</span>
            </button>
            <div class="snomed-table-details-body">
            <div id="snomed-card" style="margin-top:10px;border:2px solid #005eb8;border-radius:10px;overflow:hidden">
              <div style="background:#005eb8;padding:8px 12px;display:flex;align-items:center;justify-content:space-between">
                <div style="display:flex;align-items:center;gap:8px">
                  <span style="font-size:15px">🧬</span>
                  <span style="color:#fff;font-weight:700;font-size:13px;letter-spacing:.3px">SNOMED CT Mappings</span>
                  <span style="background:rgba(255,255,255,0.2);color:#fff;font-size:11px;padding:2px 7px;border-radius:10px;font-weight:600" id="snomed-count-badge">0 entities</span>
                </div>
                <span id="snomed-conf-badge" style="color:rgba(255,255,255,0.85);font-size:11px;font-weight:500"></span>
              </div>
              <div style="background:#eaf1fb;padding:5px 12px;display:flex;gap:14px;font-size:11px;color:#444;border-bottom:1px solid #c8d8ea">
                <span><span style="display:inline-block;width:10px;height:10px;border-radius:2px;background:#c0392b;margin-right:4px;vertical-align:middle"></span>Problem/Finding</span>
                <span><span style="display:inline-block;width:10px;height:10px;border-radius:2px;background:#1a6636;margin-right:4px;vertical-align:middle"></span>Diagnosis</span>
                <span><span style="display:inline-block;width:10px;height:10px;border-radius:2px;background:#1a4fa0;margin-right:4px;vertical-align:middle"></span>Medication</span>
              </div>
              <div style="overflow-x:auto;max-height:280px;overflow-y:auto">
                <table id="snomed-table" style="width:100%;border-collapse:collapse;font-size:12px">
                  <thead>
                    <tr style="background:#f0f4fa;position:sticky;top:0;z-index:1">
                      <th style="padding:6px 10px;text-align:left;font-weight:700;color:#333;border-bottom:1px solid #c8d8ea;width:90px">Category</th>
                      <th style="padding:6px 10px;text-align:left;font-weight:700;color:#333;border-bottom:1px solid #c8d8ea">Clinical Term</th>
                      <th style="padding:6px 10px;text-align:left;font-weight:700;color:#333;border-bottom:1px solid #c8d8ea;width:100px">SNOMED Code</th>
                      <th style="padding:6px 10px;text-align:left;font-weight:700;color:#333;border-bottom:1px solid #c8d8ea">Description</th>
                      <th style="padding:6px 10px;text-align:center;font-weight:700;color:#333;border-bottom:1px solid #c8d8ea;width:58px">Conf.</th>
                    </tr>
                  </thead>
                  <tbody id="snomed-table-body">
                    <tr><td colspan="5" style="padding:16px;text-align:center;color:#888;font-style:italic">Processing…</td></tr>
                  </tbody>
                </table>
              </div>
              <div id="snomed-empty" style="display:none;padding:14px 12px;text-align:center;color:#666;font-size:12px;background:#fafbfc">
                No SNOMED CT entities identified — document may use non-standard terminology or OCR quality was low.
                <span style="display:block;margin-top:4px;color:#999;font-size:11px">See ICD codes and extracted medications below.</span>
              </div>
            </div>
            </div>
          </div>

          <div class="entity-section" style="margin-top:14px">
            <div class="entity-section-label">📋 ICD codes (local extraction)</div>
            <div id="chips-icd"></div>
          </div>
          <div class="entity-section">
            <div class="entity-section-label">💊 Medications (extracted text)</div>
            <div id="chips-meds-raw"></div>
          </div>
          <div id="chips-problems" style="display:none"></div>
          <div id="chips-medications" style="display:none"></div>
          <div id="chips-diagnoses" style="display:none"></div>

          <div class="field-group" style="margin-top:12px">
            <div class="field-label">Unified confidence score</div>
            <div style="display:flex;align-items:center;gap:10px;margin-top:4px">
              <div id="conf-score-label" style="font-size:18px;font-weight:700;color:var(--nhs-blue)">—</div>
              <div style="flex:1">
                <div class="conf-bar-wrap"><div id="conf-bar" class="conf-bar conf-high" style="width:0%"></div></div>
              </div>
            </div>
            <div id="conf-threshold-label" style="font-size:12px;color:var(--muted);margin-top:4px">Threshold: 85% | Textract + SNOMED + LLM weighted</div>
          </div>
        </div>

        <!-- FOLLOW-UP TAB: Sender actions (what the hospital/clinic/specialist will do) -->
        <div class="tab-pane" id="tab-tasks">
          <div class="task-block">
            <div class="task-block-h"><span>To-do</span><a href="#" class="fake-link" onclick="return false">Add new task</a></div>
            <div class="task-block-body"><span class="muted-empty">No tasks assigned to this document.</span></div>
          </div>
          <div class="task-block">
            <div class="task-block-h"><span>What the Sender Will Do</span></div>
            <div style="font-size:11px;color:#666;margin:0 0 8px 0;padding:0 4px">Actions the hospital/clinic/specialist has planned or committed to</div>
            <div id="sender-doctor-block" class="role-action-group">
              <div class="role-label role-doctor">&#x1F469;&#x200D;&#x2695;&#xFE0F; Doctor</div>
              <div class="role-action-list" id="sender-doctor"></div>
            </div>
            <div id="sender-pharmacist-block" class="role-action-group">
              <div class="role-label role-pharmacist">&#x1F48A; Pharmacist</div>
              <div class="role-action-list" id="sender-pharmacist"></div>
            </div>
            <div id="sender-reception-block" class="role-action-group">
              <div class="role-label role-reception">&#x1F4CB; Reception</div>
              <div class="role-action-list" id="sender-reception"></div>
            </div>
            <div id="sender-empty" class="muted-empty" style="display:none">No sender actions identified for this document.</div>
          </div>
          <div class="task-block">
            <div class="task-block-h"><span>Done</span></div>
            <div class="task-block-body"><span class="muted-empty">No completed tasks for this document.</span></div>
          </div>
        </div>

        <!-- GP ACTIONS TAB: What the GP Surgery needs to do, split by role -->
        <div class="tab-pane" id="tab-actions">
          <div style="font-size:11px;color:#666;margin:0 0 10px 0">Actions the GP surgery must take based on this letter, split by who in the practice is responsible.</div>
          <div class="task-block">
            <div class="task-block-h"><span>GP Surgery Actions</span></div>
            <div id="gp-doctor-block" class="role-action-group">
              <div class="role-label role-doctor">&#x1F469;&#x200D;&#x2695;&#xFE0F; Doctor</div>
              <div class="role-action-list" id="gp-doctor"></div>
            </div>
            <div id="gp-pharmacist-block" class="role-action-group">
              <div class="role-label role-pharmacist">&#x1F48A; Pharmacist</div>
              <div class="role-action-list" id="gp-pharmacist"></div>
            </div>
            <div id="gp-reception-block" class="role-action-group">
              <div class="role-label role-reception">&#x1F4CB; Reception</div>
              <div class="role-action-list" id="gp-reception"></div>
            </div>
            <div id="gp-empty" class="muted-empty" style="display:none">No GP surgery actions identified for this document.</div>
          </div>
          <div class="sheet-section">
            <button type="button" class="sheet-section-head" onclick="toggleSheetSection(this)">
              Contact <span>▾</span>
            </button>
            <div class="sheet-section-body open">
              <button type="button" class="sheet-primary-row" onclick="alert('In a live deployment this would open the follow-up messaging workflow.')">✉️ Send follow-up</button>
            </div>
          </div>
          <div class="sheet-section">
            <button type="button" class="sheet-section-head" onclick="toggleSheetSection(this)">
              Document <span>▾</span>
            </button>
            <div class="sheet-section-body open">
              <button type="button" class="sheet-row" onclick="alert('Activity timeline would open here.')">🕐 Open activity</button>
              <button type="button" class="sheet-row" onclick="copyPageLink()">🔗 Copy link</button>
              <button type="button" class="sheet-row" onclick="document.getElementById('btn-download').click()">⬇️ Download document</button>
              <button type="button" class="sheet-row" onclick="alert('Archive would move this document to the archive store.')">🗑️ Archive document</button>
            </div>
          </div>
          <p style="font-size:11px;color:var(--muted);margin-top:12px;line-height:1.45">Use <strong>Download</strong> for the full processed JSON. Approve and EMIS export stay in the bar below.</p>
        </div>

      </div><!-- end tab-content -->

      <!-- Bottom bar -->
      <div class="action-bar">
        <button class="btn-sm btn-outline">Assign</button>
        <button class="btn-sm btn-outline" onclick="location.reload()">Refresh</button>
        <button class="btn-sm btn-outline" id="btn-download">Download</button>
        <button class="btn-sm btn-success" id="btn-approve">✓ Approve</button>
        <button class="btn-sm btn-emis" id="btn-emis" title="Export structured data to the clinical system (e.g. EMIS)">Save to record</button>
      </div>
    </div>

    <!-- Right panel -->
    <div class="right-panel">
      <div class="right-section">
        <div class="right-section-title">Patient Info</div>
        <div class="info-row"><div class="info-label">Patient Name</div><div class="info-value" id="pt-name">—</div></div>
        <div class="info-row"><div class="info-label">NHS Number</div><div class="info-value" id="pt-nhs">—</div></div>
        <div class="info-row"><div class="info-label">Date of Birth</div><div class="info-value" id="pt-dob">—</div></div>
        <div class="info-row"><div class="info-label">Sex</div><div class="info-value" id="pt-sex">—</div></div>
        <div class="info-row" id="pt-gp-row" style="display:none"><div class="info-label">G/P</div><div class="info-value" id="pt-gp">—</div></div>
        <div class="info-row" id="pt-edd-row" style="display:none"><div class="info-label">EDD</div><div class="info-value" id="pt-edd">—</div></div>
        <div class="info-row" id="pt-ega-row" style="display:none"><div class="info-label">Gest. Age</div><div class="info-value" id="pt-ega">—</div></div>
      </div>

      <div class="right-section">
        <div class="right-section-title">Document Info <a href="#" style="font-size:11px;color:var(--nhs-blue)">View Log</a></div>
        <div class="info-row"><div class="info-label">Name</div><div class="info-value" id="di-name" style="word-break:break-all">—</div></div>
        <div class="info-row"><div class="info-label">Letter Type</div><div class="info-value" id="di-type">—</div></div>
        <div class="info-row"><div class="info-label">Hospital Name</div><div class="info-value" id="di-trust" style="font-size:11px">—</div></div>
        <div class="info-row"><div class="info-label">Associated Organisation</div><div class="info-value" id="di-assoc" style="font-size:11px">—</div></div>
        <div class="info-row"><div class="info-label">Status</div><div id="di-status"><span class="badge badge-processed">Processed</span></div></div>
        <div class="info-row"><div class="info-label">Confidence</div><div class="info-value" id="di-conf">—</div></div>
        <div class="info-row"><div class="info-label">Created Date</div><div class="info-value" id="di-date">—</div></div>
        <div id="di-sensitive-row" class="info-row" style="display:none">
          <div class="info-label">⚠️ Sensitivity</div>
          <div class="info-value" style="color:#c77700;font-size:12px;font-weight:600">Safeguarding/Sensitive — patient summary filtered</div>
        </div>
      </div>

      <div class="right-section">
        <div class="right-section-title">Patient Demographics</div>
        <div class="info-row"><div class="info-label">Name</div><div class="info-value" id="pd-name">—</div></div>
        <div class="info-row"><div class="info-label">NHS Number</div><div class="info-value" id="pd-nhs">—</div></div>
        <div class="info-row"><div class="info-label">Date of Birth</div><div class="info-value" id="pd-dob">—</div></div>
        <div class="info-row"><div class="info-label">Sex</div><div class="info-value" id="pd-sex">—</div></div>
      </div>

      <div class="right-section">
        <div class="right-section-title expand-toggle" onclick="toggleExpand(this)">
          Problems <span class="chevron">▾</span>
        </div>
        <div class="expand-body open" id="right-problems"><div style="color:var(--muted);font-size:13px">Loading...</div></div>
      </div>

      <div class="right-section">
        <div class="right-section-title expand-toggle" onclick="toggleExpand(this)">
          Medications <span class="chevron">▾</span>
        </div>
        <div class="expand-body open" id="right-medications"><div style="color:var(--muted);font-size:13px">Loading...</div></div>
      </div>

      <div class="right-section">
        <div class="right-section-title expand-toggle" onclick="toggleExpand(this)">
          Diagnoses <span class="chevron">▾</span>
        </div>
        <div class="expand-body open" id="right-diagnoses"><div style="color:var(--muted);font-size:13px">Loading...</div></div>
      </div>

      <div class="right-section">
        <div class="right-section-title expand-toggle" onclick="toggleExpand(this)">
          Structured Fields <span class="chevron">▾</span>
        </div>
        <div class="expand-body open" id="right-struct" style="font-size:12px"></div>
      </div>

      <div class="right-section" id="right-specifics-section" style="display:none">
        <div class="right-section-title expand-toggle" onclick="toggleExpand(this)">
          Clinical Specifics <span class="chevron">▾</span>
        </div>
        <div class="expand-body open" id="right-specifics" style="font-size:12px"></div>
      </div>

      <div class="right-section">
        <div class="right-section-title">Pipeline Stages</div>
        <div id="pipeline-stages-display" style="font-size:12px;color:var(--muted)"></div>
      </div>
    </div>
  </div><!-- end result-panel -->
</div><!-- end main -->

<button class="new-upload-btn" id="new-upload-btn" onclick="resetUpload()">+ New Document</button>

<script>
let currentDocId = null;
let currentResult = null;

// Drag & drop
const dropZone = document.getElementById('drop-zone');
['dragover','dragenter'].forEach(e => dropZone.addEventListener(e, ev => { ev.preventDefault(); dropZone.style.background='#e8f0fe'; }));
['dragleave','drop'].forEach(e => dropZone.addEventListener(e, () => { dropZone.style.background=''; }));
dropZone.addEventListener('drop', ev => { ev.preventDefault(); const f = ev.dataTransfer.files[0]; if(f) uploadFile(f); });
document.getElementById('file-input').addEventListener('change', e => { if(e.target.files[0]) uploadFile(e.target.files[0]); });

function showPanel(name) {
  ['upload-panel','processing-panel','result-panel'].forEach(id => {
    document.getElementById(id).style.display = 'none';
  });
  const p = document.getElementById(name+'-panel');
  p.style.display = 'flex';
}

function animateSteps() {
  const steps = ['step-t0','step-t1','step-ta','step-tb','step-conf'];
  const delays = [400, 2000, 5000, 9000, 13000];
  steps.forEach((id, i) => {
    setTimeout(() => {
      if(i > 0) document.getElementById(steps[i-1]).className = 'step done';
      document.getElementById(id).className = 'step active';
    }, delays[i]);
  });
}

async function uploadFile(file) {
  showPanel('processing');
  document.getElementById('topbar-title').textContent = 'Processing: ' + file.name;
  animateSteps();

  const fd = new FormData();
  fd.append('file', file);

  try {
    const resp = await fetch('/api/process', { method:'POST', body:fd });
    const data = await resp.json();
    if(data.error && !data.doc_id) { alert('Error: ' + data.error); showPanel('upload'); return; }
    currentResult = data;
    renderResult(data, file);
  } catch(e) {
    alert('Network error: ' + e.message);
    showPanel('upload');
  }
}

function renderResult(data, file) {
  showPanel('result');
  document.getElementById('new-upload-btn').style.display = 'block';
  document.getElementById('topbar-title').textContent = 'View Document';

  // Mark all steps done
  ['step-t0','step-t1','step-ta','step-tb','step-conf'].forEach(id => {
    document.getElementById(id).className = 'step done';
  });

  // Scrollable document preview — render all pages as stacked images
  const pagesInner = document.getElementById('doc-pages-inner');
  pagesInner.innerHTML = '';
  const pages = data.preview_pages || (data.preview_image ? [data.preview_image] : []);
  if (pages.length) {
    pages.forEach((url, i) => {
      // Page label
      const label = document.createElement('div');
      label.style.cssText = 'font-size:10px;color:#999;text-align:center;width:100%;margin-bottom:-6px';
      label.textContent = 'Page ' + (i + 1) + ' of ' + pages.length;
      pagesInner.appendChild(label);
      // Page image
      const img = document.createElement('img');
      img.src = url;
      img.alt = 'Page ' + (i + 1);
      img.style.cssText = 'width:100%;border-radius:4px;box-shadow:0 2px 8px rgba(0,0,0,.18);background:#fff';
      img.onerror = () => { img.style.display = 'none'; };
      pagesInner.appendChild(img);
    });
  } else {
    // Fallback: use FileReader for direct image uploads (JPEG/PNG)
    const ext = file.name.split('.').pop().toLowerCase();
    if (['jpg','jpeg','png'].includes(ext)) {
      const reader = new FileReader();
      reader.onload = e => {
        const img = document.createElement('img');
        img.src = e.target.result;
        img.style.cssText = 'width:100%;border-radius:4px;box-shadow:0 2px 8px rgba(0,0,0,.18)';
        pagesInner.appendChild(img);
      };
      reader.readAsDataURL(file);
    } else {
      pagesInner.innerHTML = '<span style="color:#aaa;font-size:13px">Preview not available</span>';
    }
  }

  document.getElementById('doc-filename').textContent = data.filename || file.name;
  // Status badge — confidence is a QUALITY INDICATOR, not a gate.
  // Summaries and actions are ALWAYS generated (project letter D3/D5/D7).
  // The badge communicates trust level to the clinician for their review.
  const statusEl = document.getElementById('doc-status-badge');
  const diStatus = document.getElementById('di-status');
  const conf      = data.unified_confidence || 0;
  const threshold = data.confidence_threshold || 0.75;
  const confPct   = Math.round(conf * 100);

  if (conf >= threshold) {
    statusEl.className = 'badge badge-processed';
    statusEl.textContent = '✅ High Confidence (' + confPct + '%)';
    diStatus.innerHTML = '<span class="badge badge-processed">✅ High Confidence (' + confPct + '%)</span>';
    document.getElementById('auto-alert').style.display = 'flex';
    document.getElementById('auto-alert').textContent = '✅ High confidence — outputs auto-generated. Review and click Approve to confirm.';
  } else if (conf >= threshold * 0.75) {
    statusEl.className = 'badge badge-review';
    statusEl.textContent = '⚠️ Check Outputs (' + confPct + '%)';
    diStatus.innerHTML = '<span class="badge badge-review">⚠️ Check Outputs (' + confPct + '%)</span>';
    document.getElementById('review-alert').style.display = 'flex';
  } else {
    statusEl.className = 'badge badge-review';
    statusEl.textContent = '⚠️ Low Confidence (' + confPct + '%)';
    diStatus.innerHTML = '<span class="badge badge-review">⚠️ Low Confidence (' + confPct + '%)</span>';
    document.getElementById('review-alert').style.display = 'flex';
  }
  if(data.status === 'error') {
    statusEl.className = 'badge badge-error'; statusEl.textContent = data.status;
  }

  // Summaries
  const sums = data.summaries || {};
  // Single concise clinical summary (clinician role — short form from pipeline prompts)
  setText('summary-main', (sums.clinician||{}).summary || 'Not available');

  // Fields — the pipeline (infer_letter_type) predicts the raw letter type; the UI
  // maps that prediction onto one of the 10 practice-facing buckets. The dropdown
  // below is an override/fallback for when the auto-prediction is wrong.
  const rawLetterType = data.letter_type || '';
  const bucketLabel   = mapLetterTypeToBucket(rawLetterType, data.extracted_text || '');
  applyPredictedLetterType(rawLetterType, bucketLabel);
  setVal('field-event-date', '');
  setVal('field-letter-date', '');
  setVal('field-sender', '');
  setVal('field-consultant', '');
  setVal('field-dept', '');
  setVal('field-conclusion', '');

  // Patient info
  const pt = data.patient_info || {};
  setText('pt-name', pt.name || 'Not available'); setText('pd-name', pt.name || 'Not available');
  setText('pt-nhs',  pt.nhs_number || 'Not available'); setText('pd-nhs', pt.nhs_number || 'Not available');
  setText('pt-dob',  pt.dob || 'Not available'); setText('pd-dob', pt.dob || 'Not available');
  setText('pt-sex',  pt.sex || 'Not available'); setText('pd-sex', pt.sex || 'Not available');
  // Obstetric fields (antenatal / gynae only)
  if (pt.gravida_parity) { setText('pt-gp', pt.gravida_parity); document.getElementById('pt-gp-row').style.display=''; }
  if (pt.edd)            { setText('pt-edd', pt.edd);           document.getElementById('pt-edd-row').style.display=''; }
  if (pt.gestational_age){ setText('pt-ega', pt.gestational_age); document.getElementById('pt-ega-row').style.display=''; }

  // Doc info
  setText('di-name', data.filename || file.name);
  setText('di-type', bucketLabel || data.letter_type || '—');
  setText('di-trust', data.hospital_trust || '—');   // OBS-008
  const assocOrg = (data.clinical_specifics || {}).provider
    || (data.clinical_specifics || {}).referred_by
    || (data.structured || {}).hospital
    || data.hospital_trust
    || '';
  setText('di-assoc', assocOrg || 'Not available');
  setText('di-date', new Date(data.processed_at).toLocaleString('en-GB'));
  // OBS-004: Show per-type threshold used (reuse threshold already declared above)
  setText('di-conf', `${((data.unified_confidence||0)*100).toFixed(0)}% (threshold ${(threshold*100).toFixed(0)}%)`);
  // OBS-007: Show sensitivity warning if detected
  if (data.is_sensitive) document.getElementById('di-sensitive-row').style.display = '';

  // Confidence bar — reuse conf/threshold already declared above
  document.getElementById('conf-score-label').textContent = (conf*100).toFixed(0) + '%';
  const bar = document.getElementById('conf-bar');
  bar.style.width = Math.min(conf*100, 100) + '%';
  bar.className = 'conf-bar ' + (conf >= threshold ? 'conf-high' : conf >= threshold * 0.75 ? 'conf-mid' : 'conf-low');
  // Update threshold label dynamically
  const threshEl = document.getElementById('conf-threshold-label');
  if (threshEl) threshEl.textContent = 'Threshold: ' + (threshold*100).toFixed(0) + '% (' + (data.letter_type||'default') + ') | Textract + SNOMED + LLM weighted';

  // Populate structured detail fields from extraction
  const s = data.structured || {};
  if (s.consultant)        setVal('field-consultant', s.consultant);
  if (s.department)        setVal('field-dept', s.department);

  // Event Date / Letter Date — prefer comprehensive extraction, fall back to structured
  const eventDate = data.event_date || s.admission_date || '';
  const letterDate = data.letter_date || s.discharge_date || s.appointment_date || '';
  window._docEventDate = eventDate;
  if (eventDate)  setVal('field-event-date', eventDate);
  if (letterDate) setVal('field-letter-date', letterDate);

  if (s.admission_method)  setVal('field-sender', s.admission_method);

  // Conclusion — prefer comprehensive extraction
  const conclusion = data.conclusion || s.diagnosis_text || s.indication || s.impression || '';
  if (conclusion) setVal('field-conclusion', conclusion);

  // Recommendation — new field from comprehensive extraction
  const recommendation = data.recommendation || '';
  const recEl = document.getElementById('field-recommendation');
  if (recEl && recommendation) recEl.value = recommendation;

  // Coding tab — hidden chip sinks (kept for any future hooks)
  renderChips('chips-problems',   (data.snomed||{}).problems   || []);
  renderChips('chips-medications',(data.snomed||{}).medications|| []);
  renderChips('chips-diagnoses',  (data.snomed||{}).diagnoses  || []);
  renderCodingEntityCards(data);
  renderRightEntities('right-problems',   (data.snomed||{}).problems   || []);
  renderRightEntities('right-medications',(data.snomed||{}).medications|| []);
  renderRightEntities('right-diagnoses',  (data.snomed||{}).diagnoses  || []);

  // SNOMED CT mapping table — Details tab (prominent dedicated card)
  const snomedProbs  = (data.snomed||{}).problems    || [];
  const snomedMeds   = (data.snomed||{}).medications || [];
  const snomedDx     = (data.snomed||{}).diagnoses   || [];
  const usedFallback        = (data.snomed||{}).used_fallback         || false;
  const top3Fallback        = (data.snomed||{}).top3_fallback         || [];
  const usedSummaryFallback = (data.snomed||{}).used_summary_fallback || false;
  const usedDoctypeFallback = (data.snomed||{}).used_doctype_fallback || false;
  const trackA       = (data.pipeline_stages||{}).track_a || {};
  const trackAError  = trackA.error || null;
  // Fallbacks: locally extracted ICD codes and raw medications (always available, no AWS needed)
  const icdFallback  = data.icd_codes       || [];
  const medsFallback = data.medications_raw || [];
  renderSnomedTable(snomedProbs, snomedMeds, snomedDx, icdFallback, medsFallback, trackAError, usedFallback, top3Fallback, usedSummaryFallback, usedDoctypeFallback);

  // ── Render enhanced extractions (treatments, investigations, diary events) ──
  renderTreatmentsInvestigations(data.treatments || [], data.investigations || []);
  renderDiaryEvents(data.diary_events || []);
  renderPatientActions(data.actions_structured || {});
  // Header confidence badge
  const snomedConf = trackA.confidence != null ? trackA.confidence : null;
  const snomedBadge = document.getElementById('snomed-conf-badge');
  if (snomedBadge) {
    if (snomedConf !== null) {
      snomedBadge.textContent = 'AWS Comprehend · conf ' + (snomedConf*100).toFixed(0) + '%';
    } else if (trackAError) {
      snomedBadge.textContent = 'Comprehend unavailable — showing local extraction';
      snomedBadge.style.color = '#ffd97d';
    }
  }

  // ICD chips
  const icds = data.icd_codes || [];
  document.getElementById('chips-icd').innerHTML = icds.length
    ? icds.map(c => `<span class="snomed-chip"><span class="snomed-code">${c}</span></span>`).join('')
    : '<span style="color:var(--muted);font-size:12px">None detected</span>';

  // Medication chips (raw extracted)
  const meds = data.medications_raw || [];
  document.getElementById('chips-meds-raw').innerHTML = meds.length
    ? meds.map(m => `<span class="snomed-chip" title="${m.raw}">${m.name} <span class="snomed-code">${m.dose}</span></span>`).join('')
    : '<span style="color:var(--muted);font-size:12px">None detected</span>';

  // Structured fields right panel
  const structEl = document.getElementById('right-struct');
  const structRows = [
    ['Admission Date', s.admission_date], ['Discharge Date', s.discharge_date],
    ['Appointment', s.appointment_date], ['Consultant', s.consultant],
    ['Department', s.department], ['Procedure', s.procedure],
    ['GP Actions', s.gp_actions], ['Adm. Method', s.admission_method],
  ].filter(([,v]) => v);
  structEl.innerHTML = structRows.length
    ? structRows.map(([k,v]) => `<div class="info-row"><div class="info-label">${k}</div><div class="info-value">${v}</div></div>`).join('')
    : '<span style="color:var(--muted)">No structured fields</span>';

  // Pages badge
  if (data.pages_processed > 1) {
    document.getElementById('doc-filename').textContent += ` (${data.pages_processed} pages)`;
  }

  // Follow-up tab — suggested follow-up tasks only (GP actions live under GP Actions tab)
  renderStructuredActions(data.actions_structured || {});

  // Clinical Specifics (type-specific extras: TNM, CD4, OGTT, urgency, etc.)
  const specs = data.clinical_specifics || {};
  const specKeys = Object.keys(specs);
  const specsSection = document.getElementById('right-specifics-section');
  const specsEl = document.getElementById('right-specifics');
  if (specKeys.length > 0) {
    specsSection.style.display = '';
    // Human-readable labels for known keys
    const specLabels = {
      differential_diagnosis: 'Differential Dx',
      urgency: 'Urgency',
      encounter_type: 'Encounter Type',
      assessing_clinician: 'Assessing Clinician',
      tnm_staging: 'TNM Staging',
      cea_value: 'CEA',
      surveillance_schedule: 'Surveillance Schedule',
      treatment_history: 'Treatment History',
      cd4_count: 'CD4 Count',
      viral_load: 'Viral Load',
      art_regimen: 'ART Regimen',
      follow_up: 'Follow-up',
      ogtt_results: 'OGTT Results',
      monitoring_frequency: 'Monitoring Frequency',
      equipment_pip: 'Equipment / PIP',
      surgical_plan: 'Surgical Plan',
      action_for_gp: 'Action for GP',
      key_labs: 'Key Labs',
      paraprotein: 'Paraprotein',
      gp_address: 'GP Address',
      // Renal
      renal_labs: 'Renal Labs',
      next_review: 'Next Review',
      // Paediatric Cardiology
      cardiac_diagnosis: 'Cardiac Diagnosis',
      max_heart_rate: 'Max Heart Rate',
      planned_procedure: 'Planned Procedure',
      current_medication: 'Medication',
      // Gynae / Obstetric
      gravida_parity: 'G/P Status',
      lmp: 'LMP',
      gestational_sac: 'Gestational Sac',
      fetal_pole: 'Fetal Pole',
      scan_diagnosis: 'Scan Diagnosis',
      follow_up_plan: 'Follow-up Plan',
      edd: 'EDD',
      gestational_age: 'Gestational Age',
      reason_for_visit: 'Reason for Visit',
      // Mental Health Inpatient
      mha_section: 'MHA Section',
      primary_diagnosis: 'Primary Diagnosis',
      admission_date: 'Admission Date',
      discharge_date: 'Discharge Date',
      medication_monitoring: 'Medication Monitoring',
      community_follow_up: 'Community Follow-up',
      // Pre-admission
      speciality: 'Speciality',
      clinician: 'Clinician',
      location: 'Location',
      fasting_from: 'Fast From',
      // Ambulance
      incident_number: 'Incident No.',
      presenting_complaint: 'Presenting Complaint',
      working_impression: 'Working Impression',
      news2_score: 'NEWS2 Score',
      conveyance: 'Conveyance',
      first_vitals: 'First Vitals',
      // Ophthalmology
      referral_reason: 'Referral Reason',
      referral_pathway: 'Pathway / Clinic',
      priority: 'Priority',
      provider: 'Provider',
      referred_by: 'Referred By',
      visual_acuity: 'Visual Acuity',
      iop: 'IOP',
      retinopathy_grade: 'DR Grade',
      ophthalmic_diagnosis: 'Diagnosis',
      laser_treatment: 'Laser / PRP',
      ophthalmic_plan: 'Plan',
      neovascularisation: 'Neovascularisation',
      // ED Discharge
      attendance_reason: 'Attendance Reason',
      arrival_method: 'Arrival Method',
      ed_diagnosis: 'ED Diagnosis',
      discharge_method: 'Discharge Method',
      examined_by: 'Examined By',
    };
    specsEl.innerHTML = specKeys.map(k => {
      const label = specLabels[k] || k.replace(/_/g,' ').replace(/\b\w/g, c => c.toUpperCase());
      const rawVal = specs[k];
      const val = (typeof rawVal === 'object') ? Object.entries(rawVal).map(([a,b])=>`${a}: ${b}`).join(' | ') : rawVal;
      return `<div class="info-row"><div class="info-label">${label}</div><div class="info-value" style="word-break:break-word">${val}</div></div>`;
    }).join('');
  } else {
    specsSection.style.display = 'none';
  }

  // Pipeline stages — show status, confidence where available, error reason for partial/error
  const stages = data.pipeline_stages || {};
  document.getElementById('pipeline-stages-display').innerHTML =
    Object.entries(stages).map(([k,v]) => {
      const isDone    = v.status === 'done';
      const isPartial = v.status === 'partial';
      const isError   = v.status === 'error';
      const isSkipped = v.status === 'skipped';
      const color = isDone ? 'var(--nhs-green)'
                  : isPartial ? '#d67e00'
                  : isError ? 'var(--nhs-red)'
                  : 'var(--muted)';
      const confTxt = v.confidence !== undefined ? ' (' + Math.round(v.confidence*100) + '%)' : '';
      const errTxt  = (isPartial || isError) && v.error
        ? `<div style="font-size:10px;color:#c0392b;margin-top:1px;word-break:break-word">${v.error}</div>`
        : '';
      return `<div style="padding:3px 0;border-bottom:1px solid #edf1f7">
        <div style="display:flex;justify-content:space-between">
          <span style="font-weight:600;font-size:12px">${k}</span>
          <span style="color:${color};font-size:12px">${v.status}${confTxt}</span>
        </div>${errTxt}
      </div>`;
    }).join('');

  // Download button
  document.getElementById('btn-download').onclick = () => {
    const blob = new Blob([JSON.stringify(data, null, 2)], {type:'application/json'});
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = (data.filename || 'result') + '_processed.json';
    a.click();
  };
  document.getElementById('btn-approve').onclick = () => {
    document.getElementById('btn-approve').textContent = '✓ Approved';
    document.getElementById('btn-approve').style.background = '#004f26';
  };
  document.getElementById('btn-emis').onclick = () => {
    alert('Save to record: In production this would push the structured extraction to the clinical record (e.g. EMIS) via the configured API.');
  };
  // Letter type override / reset wiring
  const selLT = document.getElementById('field-letter-type');
  if (selLT && !selLT._wired) {
    selLT.addEventListener('change', onLetterTypeChanged);
    selLT._wired = true;
  }
  const rstLT = document.getElementById('letter-type-reset');
  if (rstLT && !rstLT._wired) {
    rstLT.addEventListener('click', (ev) => {
      ev.preventDefault();
      setVal('field-letter-type', _predictedBucket);
      onLetterTypeChanged();
    });
    rstLT._wired = true;
  }
}

// ── SNOMED CT Mapping Table ───────────────────────────────────────────────────
// Always shows something:
//  1. AWS Comprehend Medical SNOMED entities (preferred — problems/diagnoses/medications with codes)
//  2. If Comprehend failed/empty: falls back to locally-extracted ICD codes + raw medications
// Each row: category badge | clinical term | code | description | confidence
function renderSnomedTable(problems, medications, diagnoses, icdFallback, medsFallback, comprehendError, usedTermFallback, top3Fallback, usedSummaryFallback, usedDoctypeFallback) {
  const tbody      = document.getElementById('snomed-table-body');
  const emptyMsg   = document.getElementById('snomed-empty');
  const countBadge = document.getElementById('snomed-count-badge');
  const cardHeader = document.querySelector('#snomed-card > div:first-child');
  if (!tbody) return;

  // Remove any old banner so it doesn't stack on re-uploads
  const oldNote = document.getElementById('snomed-fallback-note');
  if (oldNote) oldNote.remove();

  // Build rows from AWS Comprehend primary entities
  let rows = [
    ...problems.map(e   => ({ text: e.text, code: e.snomed_code, desc: e.description, conf: e.confidence, _cat: 'Problem',    _color: '#c0392b', _bg: '#fdf2f2', _source: e.source || 'SNOMED CT' })),
    ...diagnoses.map(e  => ({ text: e.text, code: e.snomed_code, desc: e.description, conf: e.confidence, _cat: 'Diagnosis',  _color: '#1a6636', _bg: '#f2faf5', _source: e.source || 'SNOMED CT' })),
    ...medications.map(e=> ({ text: e.text, code: e.snomed_code, desc: e.description, conf: e.confidence, _cat: 'Medication', _color: '#1a4fa0', _bg: '#f2f5fc', _source: e.source || 'SNOMED CT' })),
  ];

  // ── Banner + source labelling for each fallback layer ───────────────────────
  let bannerText = null, bannerColor = null, badgeLabel = null, badgeColor = null;

  if (rows.length > 0 && rows.some(r => r._source === 'SNOMED CT' || r._source === 'comprehend_medical')) {
    // Primary AWS Comprehend path — no banner needed, just count
    badgeLabel = rows.length + (rows.length === 1 ? ' entity' : ' entities');
    badgeColor = null; // default badge colour

  } else if (usedTermFallback && top3Fallback && top3Fallback.length > 0) {
    // Layer 1 fallback: term-level extraction
    bannerText  = '🔍 Top 3 nearest SNOMED CT matches — term-level extraction (SRS §3.2)';
    bannerColor = '#1a4fa0';
    badgeLabel  = 'Top 3 matches';
    badgeColor  = '#1a4fa0';
    rows = rows.map(r => ({ ...r, _source: 'term_extraction' }));

  } else if (usedSummaryFallback) {
    // Layer 2 fallback: SNOMED inferred from supplementary structured narrative (not shown here as prose)
    bannerText  = '📋 SNOMED codes mapped via supplementary clinical narrative extraction';
    bannerColor = '#1a6636';
    badgeLabel  = rows.length + ' codes (narrative fallback)';
    badgeColor  = '#1a6636';
    rows = rows.map(r => ({ ...r, _source: 'summary_fallback' }));

  } else if (usedDoctypeFallback) {
    // Layer 3 fallback: document-type hardcoded codes (absolute guarantee)
    bannerText  = '📂 SNOMED codes from document-type reference table — document contained no extractable clinical entities';
    bannerColor = '#005EB8';
    badgeLabel  = '3 standard codes';
    badgeColor  = '#005EB8';
    rows = rows.map(r => ({ ...r, _source: 'document_type' }));

  } else if (rows.length === 0) {
    // Still nothing — show ICD/medication local extraction
    (icdFallback || []).forEach(code => {
      rows.push({ text: code, code: code, desc: 'ICD-10 code (locally extracted)', conf: null,
                  _cat: 'ICD Code', _color: '#6a4e9e', _bg: '#f5f0fc', _source: 'Local' });
    });
    (medsFallback || []).forEach(m => {
      rows.push({ text: m.name, code: null, desc: m.dose || 'medication', conf: null,
                  _cat: 'Medication', _color: '#1a4fa0', _bg: '#f2f5fc', _source: 'Local' });
    });
    if (comprehendError) {
      bannerText  = '⚠ AWS Comprehend unavailable — locally extracted codes shown. Error: ' + comprehendError;
      bannerColor = '#d67e00';
    }
    badgeLabel = rows.length + ' local codes';
    badgeColor = 'rgba(214,126,0,0.6)';
  }

  // Insert banner
  if (bannerText && cardHeader) {
    const n = document.createElement('div');
    n.id = 'snomed-fallback-note';
    n.style.cssText = `background:${bannerColor};color:#fff;font-size:11px;padding:5px 14px;text-align:center;font-weight:600;letter-spacing:.2px`;
    n.textContent = bannerText;
    cardHeader.parentElement.insertBefore(n, cardHeader.nextSibling);
  }

  const usingFallback = rows.length > 0 && rows.every(r => !['SNOMED CT','comprehend_medical'].includes(r._source));

  // Count badge
  if (countBadge) {
    if (badgeLabel) countBadge.textContent = badgeLabel;
    else countBadge.textContent = rows.length + (rows.length === 1 ? ' entity' : ' entities');
    if (badgeColor) countBadge.style.background = badgeColor;
  }

  tbody.textContent = '';  // safe clear

  if (!rows.length) {
    if (emptyMsg) { emptyMsg.style.display = ''; }
    tbody.parentElement.style.display = 'none';
    return;
  }
  if (emptyMsg) emptyMsg.style.display = 'none';
  tbody.parentElement.style.display = '';

  rows.forEach((e, idx) => {
    const tr = document.createElement('tr');
    tr.style.cssText = 'border-bottom:1px solid #edf1f7;' + (idx % 2 === 0 ? 'background:#fff' : 'background:#fafbfc');

    // ── Category badge ────────────────────────────────────────────────────────
    const tdCat = document.createElement('td');
    tdCat.style.cssText = 'padding:7px 10px;vertical-align:middle;white-space:nowrap';
    const badge = document.createElement('span');
    badge.style.cssText = `display:inline-block;padding:2px 7px;border-radius:10px;font-size:10px;font-weight:700;color:${e._color};background:${e._bg};border:1px solid ${e._color}30`;
    badge.textContent = e._cat;
    tdCat.appendChild(badge);
    // Small source label — always show for non-primary sources
    if (e._source && e._source !== 'SNOMED CT' && e._source !== 'comprehend_medical') {
      const src = document.createElement('div');
      const srcLabels = {
        'term_extraction':   { label: '🔍 Term Extraction', color: '#1a4fa0' },
        'Term Extraction':   { label: '🔍 Term Extraction', color: '#1a4fa0' },
        'summary_fallback':  { label: '📋 Narrative fallback', color: '#1a6636' },
        'document_type':     { label: '📂 Doc-type Ref',    color: '#005EB8' },
        'Local':             { label: 'Local Extract',       color: '#888'    },
      };
      const sl = srcLabels[e._source] || { label: e._source, color: '#888' };
      src.style.cssText = `font-size:9px;margin-top:1px;font-weight:600;color:${sl.color}`;
      src.textContent = sl.label;
      tdCat.appendChild(src);
    }

    // ── Clinical term ─────────────────────────────────────────────────────────
    const tdTerm = document.createElement('td');
    tdTerm.style.cssText = 'padding:7px 10px;font-weight:600;color:#222;vertical-align:middle';
    tdTerm.textContent = e.text || '—';

    // ── Code (SNOMED / ICD) ───────────────────────────────────────────────────
    const tdCode = document.createElement('td');
    tdCode.style.cssText = 'padding:7px 10px;vertical-align:middle';
    if (e.code) {
      const codeEl = document.createElement('code');
      const codeColor = e._source === 'Local' ? '#6a4e9e' : '#1a4fa0';
      const codeBg    = e._source === 'Local' ? '#f0eafb' : '#e8f0fe';
      codeEl.style.cssText = `background:${codeBg};color:${codeColor};padding:2px 7px;border-radius:4px;font-size:11px;font-weight:700;letter-spacing:.3px;font-family:monospace`;
      codeEl.textContent = e.code;
      tdCode.appendChild(codeEl);
    } else {
      const noMap = document.createElement('span');
      noMap.style.cssText = 'color:#bbb;font-size:11px;font-style:italic';
      noMap.textContent = '—';
      tdCode.appendChild(noMap);
    }

    // ── Description ───────────────────────────────────────────────────────────
    const tdDesc = document.createElement('td');
    tdDesc.style.cssText = 'padding:7px 10px;color:#555;font-size:11px;vertical-align:middle';
    tdDesc.textContent = e.desc || (e.code ? e._source + ' concept' : '—');

    // ── Confidence ────────────────────────────────────────────────────────────
    const tdConf = document.createElement('td');
    tdConf.style.cssText = 'padding:7px 10px;text-align:center;vertical-align:middle';
    if (e.conf != null) {
      const pct = Math.round(e.conf * 100);
      const confSpan = document.createElement('span');
      confSpan.style.cssText = `font-size:11px;font-weight:700;color:${pct >= 70 ? '#1a6636' : pct >= 45 ? '#d67e00' : '#c0392b'}`;
      confSpan.textContent = pct + '%';
      tdConf.appendChild(confSpan);
    } else {
      const dash = document.createElement('span');
      dash.style.cssText = 'color:#ccc;font-size:11px';
      dash.textContent = '—';
      tdConf.appendChild(dash);
    }

    tr.appendChild(tdCat);
    tr.appendChild(tdTerm);
    tr.appendChild(tdCode);
    tr.appendChild(tdDesc);
    tr.appendChild(tdConf);
    tbody.appendChild(tr);
  });
}

// FIX (review comment 7): Use safe DOM construction (textContent) instead of
// innerHTML to prevent XSS from untrusted OCR/entity text returned by the pipeline.
function renderChips(containerId, entities) {
  const el = document.getElementById(containerId);
  el.textContent = '';
  if (!entities.length) {
    const none = document.createElement('span');
    none.style.cssText = 'color:var(--muted);font-size:12px';
    none.textContent = 'None identified';
    el.appendChild(none);
    return;
  }
  entities.forEach(e => {
    const chip = document.createElement('span');
    chip.className = 'snomed-chip';
    // Show full description in tooltip, confidence score if available
    const confPct = e.confidence ? ' (' + (e.confidence*100).toFixed(0) + '%)' : '';
    chip.title = (e.description || e.text || '') + confPct;
    chip.textContent = e.text || '';
    const code = document.createElement('span');
    code.className = 'snomed-code';
    // Show SNOMED code, or 'No map' if Comprehend returned no code
    code.textContent = ' ' + (e.snomed_code ? e.snomed_code : 'No map');
    code.style.color = e.snomed_code ? '' : 'var(--nhs-yellow)';
    chip.appendChild(code);
    el.appendChild(chip);
  });
}

function renderRightEntities(containerId, entities) {
  const el = document.getElementById(containerId);
  el.textContent = '';
  if (!entities.length) {
    const none = document.createElement('span');
    none.style.cssText = 'color:var(--muted);font-size:13px';
    none.textContent = 'None identified';
    el.appendChild(none);
    return;
  }
  entities.forEach(e => {
    const row = document.createElement('div');
    row.style.cssText = 'padding:4px 0;font-size:12px';
    const name = document.createElement('span');
    name.style.fontWeight = '600';
    name.textContent = e.text || '';
    row.appendChild(name);
    const code = document.createElement('span');
    code.style.color = e.snomed_code ? 'var(--muted)' : 'var(--nhs-yellow)';
    code.textContent = ' \u00b7 ' + (e.snomed_code || 'No SNOMED map');
    row.appendChild(code);
    el.appendChild(row);
  });
}

function parseActionLines(text) {
  if (!text || !String(text).trim()) return [];
  return String(text).split('\n').map(l => l.replace(/^\d+[\.\)]\s*/, '').trim()).filter(Boolean);
}

function _makeActionCard(text, roleClass) {
  const card = document.createElement('div');
  card.className = 'task-suggest-card' + (roleClass === 'gp' ? ' gp' : '');
  const p = document.createElement('p');
  p.textContent = text;
  const row = document.createElement('div');
  row.className = 'add-row';
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'btn-add-mini';
  btn.textContent = 'Add';
  btn.onclick = () => alert('In production this would add the action to the record workflow.');
  row.appendChild(btn);
  card.appendChild(p);
  card.appendChild(row);
  return card;
}

function _populateRoleList(elId, blockId, items, roleClass) {
  const list = document.getElementById(elId);
  const block = document.getElementById(blockId);
  if (!list || !block) return;
  list.textContent = '';
  if (!items || !items.length) {
    block.style.display = 'none';
    return;
  }
  block.style.display = '';
  items.forEach(txt => list.appendChild(_makeActionCard(txt, roleClass)));
}

function renderStructuredActions(structured) {
  const sa = (structured && structured.sender_actions) || {};
  const ga = (structured && structured.gp_surgery_actions) || {};

  // Sender (Follow-up tab)
  _populateRoleList('sender-doctor',     'sender-doctor-block',     sa.doctor,     '');
  _populateRoleList('sender-pharmacist', 'sender-pharmacist-block', sa.pharmacist, '');
  _populateRoleList('sender-reception',  'sender-reception-block',  sa.reception,  '');
  const senderEmpty = document.getElementById('sender-empty');
  const senderHasData = (sa.doctor||[]).length + (sa.pharmacist||[]).length + (sa.reception||[]).length > 0;
  if (senderEmpty) senderEmpty.style.display = senderHasData ? 'none' : '';

  // GP Surgery (GP Actions tab)
  _populateRoleList('gp-doctor',     'gp-doctor-block',     ga.doctor,     'gp');
  _populateRoleList('gp-pharmacist', 'gp-pharmacist-block', ga.pharmacist, 'gp');
  _populateRoleList('gp-reception',  'gp-reception-block',  ga.reception,  'gp');
  const gpEmpty = document.getElementById('gp-empty');
  const gpHasData = (ga.doctor||[]).length + (ga.pharmacist||[]).length + (ga.reception||[]).length > 0;
  if (gpEmpty) gpEmpty.style.display = gpHasData ? 'none' : '';
}

// Parse the SNOMED semantic type from the description suffix, e.g.
// "Gestational diabetes mellitus (disorder)" -> "disorder".
function _semanticType(e) {
  const d = (e && e.description) || '';
  const m = d.match(/\(([^()]+)\)\s*$/);
  if (m) {
    const tag = m[1].toLowerCase().trim();
    // Normalise common SNOMED hierarchy labels
    if (tag.indexOf('disorder') >= 0) return 'disorder';
    if (tag.indexOf('finding')  >= 0) return 'finding';
    if (tag.indexOf('procedure')>= 0) return 'procedure';
    if (tag.indexOf('situation')>= 0) return 'situation';
    if (tag.indexOf('event')    >= 0) return 'event';
    if (tag.indexOf('substance')>= 0) return 'substance';
    if (tag.indexOf('product')  >= 0) return 'product';
    if (tag.indexOf('observable')>=0) return 'finding';
    if (tag.indexOf('body structure')>=0) return 'finding';
    if (tag.indexOf('organism') >= 0) return 'finding';
    return tag.split(/\s+/)[0];
  }
  return '';
}

function _semanticLabel(sem) {
  const map = {
    disorder:'Disorder', finding:'Finding', procedure:'Procedure',
    situation:'Situation', event:'Event', substance:'Substance', product:'Medication'
  };
  return map[sem] || (sem ? (sem.charAt(0).toUpperCase() + sem.slice(1)) : 'Other');
}

function _renderActiveProblem(entity) {
  const host = document.getElementById('coding-active-problem');
  if (!host) return;
  host.textContent = '';
  if (!entity) return;
  const card = document.createElement('div');
  card.className = 'active-problem-card';

  const titleRow = document.createElement('div');
  titleRow.className = 'apc-title-row';
  const title = document.createElement('div');
  title.className = 'apc-title';
  title.textContent = entity.text || '—';
  titleRow.appendChild(title);
  const chipMajor  = document.createElement('span');
  chipMajor.className = 'apc-chip major';
  chipMajor.textContent = 'Major';
  const chipActive = document.createElement('span');
  chipActive.className = 'apc-chip active';
  chipActive.textContent = 'Active';
  titleRow.appendChild(chipMajor);
  titleRow.appendChild(chipActive);
  card.appendChild(titleRow);

  if (entity.snomed_code) {
    const code = document.createElement('div');
    code.className = 'apc-code';
    code.textContent = String(entity.snomed_code);
    card.appendChild(code);
  }

  const grid = document.createElement('div');
  grid.className = 'apc-grid';

  function addField(label, valueNode) {
    const col = document.createElement('div');
    const l = document.createElement('div');
    l.className = 'apc-field-label';
    l.textContent = label;
    col.appendChild(l);
    col.appendChild(valueNode);
    grid.appendChild(col);
  }

  const sevVal = document.createElement('div');
  sevVal.className = 'apc-field-value';
  sevVal.textContent = 'Major';
  addField('Severity', sevVal);

  const statusSel = document.createElement('select');
  statusSel.className = 'apc-field-select';
  ['Review','Active','Resolved','Inactive'].forEach(opt => {
    const o = document.createElement('option');
    o.value = opt.toLowerCase();
    o.textContent = opt;
    if (opt === 'Review') o.selected = true;
    statusSel.appendChild(o);
  });
  addField('Status', statusSel);

  const started = document.createElement('div');
  started.className = 'apc-field-value';
  started.textContent = (window._docEventDate || '—');
  addField('Started on', started);

  const desc = document.createElement('div');
  desc.className = 'apc-field-value';
  desc.textContent = entity.description || '—';
  addField('Description', desc);

  card.appendChild(grid);
  host.appendChild(card);
}

function renderCodingEntityCards(data) {
  const root = document.getElementById('coding-entity-cards');
  if (!root) return;
  root.textContent = '';

  const probs = (data.snomed || {}).problems     || [];
  const dx    = (data.snomed || {}).diagnoses    || [];
  const meds  = (data.snomed || {}).medications  || [];

  // Pick the "active problem" = first disorder we can find, else first diagnosis/problem.
  const disorders = [...dx, ...probs].filter(e => _semanticType(e) === 'disorder');
  const active = disorders[0] || dx[0] || probs[0] || null;
  _renderActiveProblem(active);

  // Regroup everything by SNOMED semantic type (with a sensible fallback).
  const groups = {}; // sem -> entity[]
  function bucket(list, fallback) {
    list.forEach(e => {
      let sem = _semanticType(e);
      if (!sem) sem = fallback;
      (groups[sem] = groups[sem] || []).push(e);
    });
  }
  bucket(dx,    'disorder');
  bucket(probs, 'finding');
  bucket(meds,  'product');

  // Render order, matches the Anima "Disorder / Finding / Event / ..." flow.
  const order = ['disorder','finding','procedure','situation','event','substance','product'];
  const seen = new Set();
  function renderGroup(sem) {
    const list = groups[sem];
    if (!list || !list.length) return;
    seen.add(sem);
    const h = document.createElement('div');
    h.className = 'coding-group-title';
    h.textContent = _semanticLabel(sem);
    root.appendChild(h);
    list.forEach(e => {
      const card = document.createElement('div');
      card.className = 'coding-code-card sem-' + sem;
      const top = document.createElement('div');
      top.className = 'card-top';
      const t = document.createElement('div');
      t.className = 'card-title';
      t.textContent = e.text || '—';
      const menu = document.createElement('span');
      menu.className = 'card-menu';
      menu.textContent = '⋮';
      top.appendChild(t);
      top.appendChild(menu);
      card.appendChild(top);
      if (e.snomed_code) {
        const c = document.createElement('div');
        c.className = 'coding-code-num';
        c.textContent = String(e.snomed_code);
        card.appendChild(c);
      }
      if (e.description) {
        const d = document.createElement('div');
        d.className = 'coding-snippet';
        d.textContent = e.description;
        card.appendChild(d);
      }
      root.appendChild(card);
    });
  }
  order.forEach(renderGroup);
  // Any leftover semantic types not in the preferred order
  Object.keys(groups).forEach(s => { if (!seen.has(s)) renderGroup(s); });

  if (!root.childNodes.length) {
    const empty = document.createElement('div');
    empty.className = 'muted-empty';
    empty.textContent = 'No coded entities identified — expand the mapping table below or check ICD / medication extraction.';
    root.appendChild(empty);
  }
}

function toggleSheetSection(btn) {
  const body = btn.nextElementSibling;
  if (!body || !body.classList.contains('sheet-section-body')) return;
  body.classList.toggle('open');
  const chev = btn.querySelector('span');
  if (chev) chev.textContent = body.classList.contains('open') ? '▾' : '▸';
}

// Apply the pipeline's prediction to the Letter type dropdown + badges.
// Manual change to the dropdown flips it into "override" mode.
let _predictedBucket = '';
let _predictedRaw    = '';
function applyPredictedLetterType(rawLetterType, bucketLabel) {
  _predictedRaw    = rawLetterType || '';
  _predictedBucket = bucketLabel   || '';
  const rawEl      = document.getElementById('letter-type-raw');
  const bucketEl   = document.getElementById('letter-type-bucket');
  const autoLine   = document.getElementById('letter-type-auto-line');
  const predBadge  = document.getElementById('letter-type-pred-badge');
  const overBadge  = document.getElementById('letter-type-override-badge');
  const resetLink  = document.getElementById('letter-type-reset');
  if (rawEl)    rawEl.textContent    = rawLetterType || '—';
  if (bucketEl) bucketEl.textContent = bucketLabel   || '—';
  // Drive auto-detected indicators off the actual predicted bucket (not the
  // raw letter type). Otherwise the dropdown can be silently auto-set to a
  // bucket while the "Auto-detected" badge and explainer line are hidden
  // because rawLetterType happened to be empty.
  const hasPrediction = !!_predictedBucket;
  if (autoLine) autoLine.style.display = hasPrediction ? '' : 'none';
  if (predBadge) predBadge.style.display = hasPrediction ? '' : 'none';
  if (overBadge) overBadge.style.display = 'none';
  if (resetLink) resetLink.style.display = 'none';
  setVal('field-letter-type', bucketLabel);
}

function onLetterTypeChanged() {
  const sel = document.getElementById('field-letter-type');
  if (!sel) return;
  const current = sel.value;
  const predBadge = document.getElementById('letter-type-pred-badge');
  const overBadge = document.getElementById('letter-type-override-badge');
  const resetLink = document.getElementById('letter-type-reset');
  const overridden = current !== _predictedBucket;
  // Pred badge visibility is tied to the predicted bucket, not the raw
  // pipeline letter_type (which may be empty even when a bucket was predicted).
  if (predBadge) predBadge.style.display = overridden ? 'none' : (_predictedBucket ? '' : 'none');
  if (overBadge) overBadge.style.display = overridden ? '' : 'none';
  if (resetLink) resetLink.style.display = overridden ? '' : 'none';
  // Keep right-panel Document info in sync with whatever the user chose.
  // Fall back to the predicted BUCKET (matching the format initially shown)
  // rather than the raw pipeline letter_type, so di-type doesn't flip formats
  // when the user clears their selection.
  const diType = document.getElementById('di-type');
  if (diType) diType.textContent = current || _predictedBucket || '—';
}

// Single source of truth for the 10 practice-facing bucket labels: read them
// straight from the <select>'s data-bucket-key options. This avoids drift
// between the dropdown options and the mapper constants — fixing the label
// text in one place (e.g. "advise" -> "advice") automatically updates both.
let _bucketLabelCache = null;
function getLetterTypeBuckets() {
  if (_bucketLabelCache) return _bucketLabelCache;
  const sel = document.getElementById('field-letter-type');
  const out = {};
  if (sel) {
    Array.from(sel.options).forEach(o => {
      const k = o.getAttribute('data-bucket-key');
      if (k) out[k] = o.value;
    });
  }
  // Only cache once the select has been populated with its bucket options.
  if (Object.keys(out).length) _bucketLabelCache = out;
  return out;
}

// Map pipeline `letter_type` (and document text) to one of the 10 practice buckets.
// Purely UI-side — does not alter backend output.
function mapLetterTypeToBucket(internal, docText) {
  const t = (docText || '').toLowerCase();
  const B = getLetterTypeBuckets();

  const desCues = ['diabetic eye screening','nhs diabetic eye','retinopathy screening',
                   'grading digital images','des service','des programme','screening outcome'];
  if (desCues.some(c => t.includes(c))) return B.DES;

  const oohCues = ['out of hours','out-of-hours','gp out of hours','ic24','voddoc',
                   'east berkshire primary care','brants bridge','wokingham ooh',
                   'primary care out of hours'];
  const oohCandidateInternals = ['Clinical Letter','Outpatient Letter','Referral Letter',
                                 'Medication Request','Procedure Report'];
  if (oohCues.some(c => t.includes(c)) && oohCandidateInternals.includes(internal)) return B.OOH;

  const hosp = new Set(['Discharge Summary','Mental Health Inpatient Discharge',
                        'Antenatal Discharge Summary','CAMHS Discharge Summary']);
  if (hosp.has(internal)) return B.HOSP;
  if (internal === 'ED Discharge Letter') return B.ED;
  if (internal === '111 First ED Report') return B['111'];
  if (internal === 'Ambulance Clinical Report') return B.AMB;
  if (internal === 'Ophthalmology Referral') return B.EXT;
  if (internal === 'Ophthalmology Letter') return B.DES;
  if (internal === 'Medication / Prescriber Letter') return B.PRIV;
  if (internal === 'Medication Request') return B.MISC;

  const clin = new Set(['Referral Letter','Outpatient Letter','Clinical Letter',
    'Cancer Surveillance Letter','HIV / GUM Clinic Letter','Maternity / Diabetes Letter',
    'Surgical Outpatient Letter','Procedure Report','Psychiatry Outpatient Letter',
    'Renal / Nephrology Letter','Paediatric Cardiology Letter',
    'Early Pregnancy / Gynaecology Letter','Pre-admission Letter',
    'Haematology Outpatient Letter']);
  if (clin.has(internal)) return B.CLIN;

  // No signal from the pipeline or document cues: return an empty bucket so
  // the caller can avoid silently auto-selecting a dropdown option.
  if (!internal) return '';
  return B.MISC;
}

function copyPageLink() {
  const url = window.location.href.split('#')[0];
  navigator.clipboard.writeText(url).then(
    () => alert('Page link copied to clipboard.'),
    () => alert('Could not copy link.')
  );
}

// FIX (review comment 6): Accept the clicked element explicitly rather than
// relying on the global `event.target` which is not reliable across all browsers.
function showTab(el, name) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
  el.classList.add('active');
  document.getElementById('tab-'+name).classList.add('active');
}

function toggleSnomedDetails(btn) {
  const wrap = btn.closest('.snomed-table-details');
  if (!wrap) return;
  const open = !wrap.classList.contains('open');
  wrap.classList.toggle('open', open);
  btn.setAttribute('aria-expanded', open ? 'true' : 'false');
  const chev = btn.querySelector('.snomed-disclosure-chev');
  if (chev) chev.textContent = open ? '▾' : '▸';
}

function toggleExpand(el) {
  const body = el.nextElementSibling;
  const chevron = el.querySelector('.chevron');
  body.classList.toggle('open');
  chevron.classList.toggle('open');
}

function copyText(id) {
  const text = document.getElementById(id).innerText.replace('📋','').trim();
  navigator.clipboard.writeText(text).then(() => {
    const btn = document.querySelector('#'+id+' .copy-btn');
    btn.textContent = '✓'; setTimeout(() => btn.textContent = '📋', 1500);
  });
}

// Convert markdown-style text from LLM into clean readable HTML.
// Handles **bold**, *italic*, bullet lines (- / * / numbered), section headers.
function mdToHtml(text) {
  if (!text) return '';
  // Escape any actual HTML first to prevent XSS
  const escaped = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');

  let html = escaped
    // ### and ## section headers → styled block (before bold so ** inside headers work)
    .replace(/^#{3}\s+(.+)$/gm, '<strong style="display:block;margin:10px 0 3px;font-size:12px;color:#005eb8;text-transform:uppercase;letter-spacing:.4px">$1</strong>')
    .replace(/^#{1,2}\s+(.+)$/gm, '<strong style="display:block;margin:10px 0 4px;font-size:13px;color:#003087">$1</strong>')
    // **bold** → <strong>
    .replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>')
    // *italic* → <em>
    .replace(/\*([^*\n]+)\*/g, '<em>$1</em>')
    // Numbered list items: "1. text" or "1) text"
    .replace(/^\d+[\.\)]\s+(.+)$/gm, '<li style="margin:3px 0">$1</li>')
    // Bullet list items: "- text" or "* text"
    .replace(/^[\-\u2022]\s+(.+)$/gm, '<li style="margin:3px 0">$1</li>')
    // Wrap consecutive <li> blocks in <ul>
    .replace(/(<li[^>]*>[\s\S]*?<\/li>\n?)+/g, m => '<ul style="margin:6px 0 6px 16px;padding:0;list-style:disc">' + m + '</ul>')
    // Double newline → paragraph break
    .replace(/\n{2,}/g, '</p><p style="margin:5px 0">')
    // Single newline → line break
    .replace(/\n/g, '<br>');

  return '<div style="line-height:1.55;font-size:13px">' + html + '</div>';
}

function setText(id, text) {
  const el = document.getElementById(id);
  if(!el) return;
  // preserve copy button if present
  const btn = el.querySelector('.copy-btn');
  el.innerHTML = mdToHtml(text);
  if(btn) el.prepend(btn);
}
function setVal(id, val) { const el = document.getElementById(id); if(el) el.value = val; }

function resetUpload() {
  document.getElementById('new-upload-btn').style.display = 'none';
  document.getElementById('topbar-title').textContent = 'Document Extraction Portal';
  showPanel('upload');
  document.getElementById('file-input').value = '';
}

// ── Render Treatments and Investigations (Comprehensive Extraction) ──────────
function renderTreatmentsInvestigations(treatments, investigations) {
  // Add to SNOMED table or create separate sections
  const tbody = document.getElementById('snomed-table-body');
  if (!tbody) return;

  // Add treatments
  treatments.forEach(t => {
    const tr = document.createElement('tr');
    tr.style.background = '#f0fff4'; // Light green for treatments

    const tdCat = document.createElement('td');
    tdCat.style.cssText = 'padding:7px 10px;vertical-align:middle';
    const badge = document.createElement('span');
    badge.style.cssText = 'display:inline-block;padding:2px 7px;border-radius:10px;font-size:10px;font-weight:700;color:#047857;background:#d1fae5;border:1px solid #04785730';
    badge.textContent = 'TREATMENT';
    tdCat.appendChild(badge);

    const tdTerm = document.createElement('td');
    tdTerm.style.cssText = 'padding:7px 10px;font-weight:600;color:#222;vertical-align:middle';
    tdTerm.textContent = t.term || '—';

    const tdCode = document.createElement('td');
    tdCode.style.cssText = 'padding:7px 10px;vertical-align:middle';
    if (t.snomed_code) {
      const codeEl = document.createElement('code');
      codeEl.style.cssText = 'background:#d1fae5;color:#047857;padding:2px 7px;border-radius:4px;font-size:11px;font-weight:700;font-family:monospace';
      codeEl.textContent = t.snomed_code;
      tdCode.appendChild(codeEl);
    }

    const tdDesc = document.createElement('td');
    tdDesc.style.cssText = 'padding:7px 10px;color:#555;font-size:11px;vertical-align:middle';
    tdDesc.textContent = t.snomed_description || '';

    const tdConf = document.createElement('td');
    tdConf.style.cssText = 'padding:7px 10px;text-align:center;vertical-align:middle';
    tdConf.innerHTML = '<span style="font-size:9px;color:#047857">Claude</span>';

    tr.appendChild(tdCat);
    tr.appendChild(tdTerm);
    tr.appendChild(tdCode);
    tr.appendChild(tdDesc);
    tr.appendChild(tdConf);
    tbody.appendChild(tr);
  });

  // Add investigations
  investigations.forEach(inv => {
    const tr = document.createElement('tr');
    tr.style.background = '#eff6ff'; // Light blue for investigations

    const tdCat = document.createElement('td');
    tdCat.style.cssText = 'padding:7px 10px;vertical-align:middle';
    const badge = document.createElement('span');
    badge.style.cssText = 'display:inline-block;padding:2px 7px;border-radius:10px;font-size:10px;font-weight:700;color:#1d4ed8;background:#dbeafe;border:1px solid #1d4ed830';
    badge.textContent = 'INVESTIGATION';
    tdCat.appendChild(badge);

    const tdTerm = document.createElement('td');
    tdTerm.style.cssText = 'padding:7px 10px;font-weight:600;color:#222;vertical-align:middle';
    tdTerm.textContent = inv.term + (inv.result ? ' → ' + inv.result : '');

    const tdCode = document.createElement('td');
    tdCode.style.cssText = 'padding:7px 10px;vertical-align:middle';
    if (inv.snomed_code) {
      const codeEl = document.createElement('code');
      codeEl.style.cssText = 'background:#dbeafe;color:#1d4ed8;padding:2px 7px;border-radius:4px;font-size:11px;font-weight:700;font-family:monospace';
      codeEl.textContent = inv.snomed_code;
      tdCode.appendChild(codeEl);
    }

    const tdDesc = document.createElement('td');
    tdDesc.style.cssText = 'padding:7px 10px;color:#555;font-size:11px;vertical-align:middle';
    tdDesc.textContent = '';

    const tdConf = document.createElement('td');
    tdConf.style.cssText = 'padding:7px 10px;text-align:center;vertical-align:middle';
    tdConf.innerHTML = '<span style="font-size:9px;color:#1d4ed8">Claude</span>';

    tr.appendChild(tdCat);
    tr.appendChild(tdTerm);
    tr.appendChild(tdCode);
    tr.appendChild(tdDesc);
    tr.appendChild(tdConf);
    tbody.appendChild(tr);
  });
}

// ── Render Diary Events ───────────────────────────────────────────────────────
function renderDiaryEvents(events) {
  const el = document.getElementById('diary-events-list');
  if (!el) return;
  el.innerHTML = '';

  if (!events || !events.length) {
    el.innerHTML = '<span style="color:#94a3b8;font-style:italic">No scheduled follow-ups identified</span>';
    return;
  }

  events.forEach((ev, i) => {
    const div = document.createElement('div');
    div.style.cssText = 'padding:8px 12px;margin-bottom:6px;background:#f0f9ff;border-left:3px solid #0ea5e9;border-radius:4px';

    const title = document.createElement('div');
    title.style.cssText = 'font-weight:600;color:#0c4a6e;margin-bottom:4px';
    title.textContent = ev.event || 'Follow-up';

    const details = document.createElement('div');
    details.style.cssText = 'font-size:12px;color:#64748b';
    const parts = [];
    if (ev.due_date) parts.push('📅 ' + ev.due_date);
    if (ev.responsible_party) parts.push('👤 ' + ev.responsible_party);
    details.textContent = parts.join(' • ') || 'No date specified';

    div.appendChild(title);
    div.appendChild(details);
    el.appendChild(div);
  });
}

// ── Render Patient Actions ────────────────────────────────────────────────────
function renderPatientActions(actions) {
  const patientActions = actions.patient_actions || [];
  const patientBooking = actions.patient_booking || [];

  // Find or create patient actions container in Follow-up tab
  let patientBlock = document.getElementById('patient-actions-block');
  if (!patientBlock) {
    // Create it dynamically in the Follow-up tab
    const followupContent = document.querySelector('#pane-followup > div');
    if (followupContent) {
      const block = document.createElement('div');
      block.innerHTML = `
        <div class="task-block-h" style="margin-top:16px;background:#fef3c7"><span style="color:#92400e">🏃 Patient Actions</span></div>
        <div style="font-size:11px;color:#666;margin:0 0 8px 0;padding:0 4px">Actions the patient must take</div>
        <div id="patient-actions-list" class="role-action-list"></div>
        <div class="task-block-h" style="margin-top:12px;background:#fce7f3"><span style="color:#9d174d">📅 Patient Booking Required</span></div>
        <div style="font-size:11px;color:#666;margin:0 0 8px 0;padding:0 4px">Appointments patient needs to arrange</div>
        <div id="patient-booking-list" class="role-action-list"></div>
      `;
      followupContent.appendChild(block);
    }
  }

  // Populate patient actions
  const actionsList = document.getElementById('patient-actions-list');
  if (actionsList) {
    actionsList.innerHTML = '';
    if (patientActions.length) {
      patientActions.forEach(a => {
        const item = document.createElement('div');
        item.className = 'role-action-item';
        item.innerHTML = `<span class="action-num" style="background:#f59e0b">!</span><span class="action-text">${a}</span>`;
        actionsList.appendChild(item);
      });
    } else {
      actionsList.innerHTML = '<div class="muted-empty" style="font-size:12px">No patient actions identified</div>';
    }
  }

  // Populate patient booking
  const bookingList = document.getElementById('patient-booking-list');
  if (bookingList) {
    bookingList.innerHTML = '';
    if (patientBooking.length) {
      patientBooking.forEach(b => {
        const item = document.createElement('div');
        item.className = 'role-action-item';
        item.innerHTML = `<span class="action-num" style="background:#ec4899">📅</span><span class="action-text">${b}</span>`;
        bookingList.appendChild(item);
      });
    } else {
      bookingList.innerHTML = '<div class="muted-empty" style="font-size:12px">No booking requirements identified</div>';
    }
  }
}
</script>
</body>
</html>
"""

@app.route("/pages/<doc_id>/<filename>")
def serve_page_image(doc_id, filename):
    """Serve individual page images for the scrollable document preview."""
    page_dir = UPLOAD_DIR / doc_id
    return send_from_directory(str(page_dir), filename)


@app.route("/health")
def health():
    """Health check endpoint — used by Render, Railway, and other PaaS platforms."""
    return jsonify({"status": "ok", "service": "NLP-UK Clinical Portal"})


@app.route("/")
def index():
    return render_template_string(HTML)


@app.route("/api/process", methods=["POST"])
def process_document():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    f        = request.files["file"]
    ext      = Path(f.filename).suffix.lower()
    if ext not in ALLOWED_EXT:
        return jsonify({"error": f"Unsupported file type: {ext}"}), 400

    doc_id   = str(uuid.uuid4())[:8]
    filename = secure_filename(f.filename)
    save_path = UPLOAD_DIR / f"{doc_id}_{filename}"
    f.save(str(save_path))

    try:
        result = run_full_pipeline(doc_id, save_path)
    except Exception as e:
        # FIX (review comment 5): Log full traceback server-side only.
        # Never return stack frames/paths to the browser — leaks internal details.
        app.logger.exception("Document processing failed doc_id=%s filename=%s", doc_id, filename)
        result = {
            "doc_id":    doc_id,
            "filename":  filename,
            "status":    "error",
            "error":     "An internal error occurred while processing the document.",
            # error_detail only included when Flask debug mode is on (local dev only)
            **({"error_detail": str(e)} if app.debug else {}),
        }

    # Persist result
    result_path = RESULTS_DIR / f"{doc_id}_result.json"
    with open(result_path, "w") as fp:
        # Remove blocks (too large) before saving
        r = {k: v for k, v in result.items() if k != "blocks"}
        json.dump(r, fp, indent=2, default=str)

    return jsonify(result)


@app.route("/api/result/<doc_id>")
def get_result(doc_id):
    result_path = RESULTS_DIR / f"{doc_id}_result.json"
    if not result_path.exists():
        return jsonify({"error": "Result not found"}), 404
    with open(result_path) as f:
        return jsonify(json.load(f))


@app.route("/api/runs")
def list_runs():
    """List all saved processing runs with summary info."""
    runs = []
    for result_file in sorted(RESULTS_DIR.glob("*_result.json"), key=lambda f: f.stat().st_mtime, reverse=True):
        try:
            with open(result_file) as f:
                data = json.load(f)
                runs.append({
                    "doc_id": data.get("doc_id", result_file.stem.replace("_result", "")),
                    "filename": data.get("filename", "Unknown"),
                    "processed_at": data.get("processed_at", ""),
                    "letter_type": data.get("letter_type", ""),
                    "unified_confidence": data.get("unified_confidence", 0),
                    "pages_processed": data.get("pages_processed", 0),
                    "status": "completed"
                })
        except Exception:
            continue
    return jsonify({"runs": runs, "total": len(runs)})


@app.route("/api/runs/<doc_id>", methods=["DELETE"])
def delete_run(doc_id):
    """Delete a saved run and its associated files."""
    result_path = RESULTS_DIR / f"{doc_id}_result.json"
    upload_dir = UPLOAD_DIR / doc_id

    deleted = []
    if result_path.exists():
        result_path.unlink()
        deleted.append("result")
    if upload_dir.exists():
        import shutil
        shutil.rmtree(upload_dir)
        deleted.append("uploads")

    if not deleted:
        return jsonify({"error": "Run not found"}), 404
    return jsonify({"message": f"Deleted: {', '.join(deleted)}", "doc_id": doc_id})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"Starting Clinical Document Portal — open http://127.0.0.1:{port}/ in your browser")
    print(f"(binding all interfaces: http://0.0.0.0:{port})")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
