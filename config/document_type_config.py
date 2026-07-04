"""
document_type_config.py
------------------------
Central registry of all 21 document types identified from the 40-document
clinical dataset (Batches 1–5, April 2026).

CONFIDENCE THRESHOLD PHILOSOPHY (aligned with Project Letter D3/D5/D7):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
The system is ALWAYS ASSISTIVE — summaries and actions are ALWAYS generated
regardless of confidence score. The threshold is a QUALITY INDICATOR used
to badge outputs for the reviewing clinician, not a gate that blocks output.

  Above threshold  → ✅ High Confidence badge (outputs likely accurate)
  75–100% of thr   → ⚠️ Check Outputs badge (review recommended)
  Below 75% of thr → ⚠️ Low Confidence badge (careful review needed)

Thresholds are calibrated to REAL AWS service output ranges observed on
scanned NHS clinical documents:
  - AWS Textract on scanned PDFs:              0.75 – 0.92
  - AWS Comprehend Medical InferSNOMEDCT:      0.30 – 0.65  (inherently low)
  - AWS Bedrock Claude (self-eval proxy):      0.75 – 0.85
  - Weighted UCS (40% Textract + 20% SNOMED + 40% LLM):  0.62 – 0.82

Setting thresholds above 0.80 for scanned documents means EVERY document
flags as low confidence, defeating the purpose. Thresholds below are set
to differentiate genuinely low-quality extractions from good ones.
"""

from __future__ import annotations
from typing import Dict, List

# ── Document type registry ───────────────────────────────────────────────────
# confidence_threshold: the UCS value above which outputs are marked
#   "High Confidence" (✅). Set based on real observed AWS output ranges.

DOCUMENT_TYPES: Dict[str, dict] = {

    # ── Prefix 1: Inpatient ──────────────────────────────────────────────────
    "Discharge Summary": {
        "prefix": "1",
        "confidence_threshold": 0.72,   # Clean laser-printed Frimley/RBH letters
        "domain": "Acute inpatient",
        "signals": ["discharge summary", "discharge date", "discharging consultant",
                    "length of stay", "discharge summary completed by"],
        "page_strategy": "all",
    },
    "CAMHS Discharge Summary": {
        "prefix": "1",
        "confidence_threshold": 0.70,
        "domain": "Paediatric mental health",
        "signals": ["camhs", "child and adolescent", "mental health service",
                    "brief psychosocial intervention", "bpi"],
        "page_strategy": "all",
    },

    # ── Prefix 2: Specialist outpatient ─────────────────────────────────────
    "Cancer Surveillance Letter": {
        "prefix": "2",
        "confidence_threshold": 0.72,
        "domain": "Oncology",
        "signals": ["surveillance", "adenocarcinoma", "hemicolectomy", "colorectal surveillance",
                    "tnm", "cea", "chemotherapy", "oncology"],
        "page_strategy": "all",
    },
    "HIV / GUM Clinic Letter": {
        "prefix": "2",
        "confidence_threshold": 0.72,
        "domain": "Sexual health / HIV",
        "signals": ["hiv", "gum clinic", "garden clinic", "sexual health", "antiretroviral",
                    "cd4", "viral load", "art regimen", "dolutegravir", "tenofovir"],
        "page_strategy": "all",
    },
    "Maternity / Diabetes Letter": {
        "prefix": "2",
        "confidence_threshold": 0.70,
        "domain": "Obstetric endocrinology",
        "signals": ["gestational diabetes", "antenatal", "maternity", "glucose tolerance",
                    "pip code", "blood glucose monitoring", "midwives"],
        "page_strategy": "all",
    },
    "Surgical Outpatient Letter": {
        "prefix": "2",
        "confidence_threshold": 0.72,
        "domain": "Surgery pre-operative",
        "signals": ["hernia", "supra-umbilical", "upper gi", "open repair", "mesh repair",
                    "brachioplasty", "pre-op", "pre op", "surgical consent"],
        "page_strategy": "all",
    },

    # ── Prefix 3: 111 / Triage ───────────────────────────────────────────────
    "111 First ED Report": {
        "prefix": "3",
        "confidence_threshold": 0.62,   # Dense small-font text, lower OCR quality
        "domain": "NHS 111 triage / urgent care",
        "signals": ["111 first ed report", "nhs111 encounter", "pathways disposition",
                    "pathways assessment", "attendance activity", "111 first"],
        "page_strategy": "all",
    },

    # ── Prefix 4: Emergency Department ───────────────────────────────────────
    "ED Discharge Letter": {
        "prefix": "4",
        "confidence_threshold": 0.68,   # Mixed font sizes, arrival-method tables
        "domain": "Emergency medicine",
        "signals": ["frimley emergency", "patient discharge letter", "attendance reason",
                    "arrival method", "source of referral", "mode of arrival",
                    "presenting complaint:", "place of accident"],
        "page_strategy": "all",
        "trust_variants": ["Frimley Health", "Royal Berkshire Hospital", "Kettering General"],
    },

    # ── Prefix 5: Ambulance ──────────────────────────────────────────────────
    "Ambulance Clinical Report": {
        "prefix": "5",
        # All-caps multi-column tables — SNOMED excluded from UCS for this type
        # Confidence = 50% Textract + 50% LLM only (see compute_unified_confidence)
        "confidence_threshold": 0.62,   # OBS-004: lower due to table-heavy OCR
        "domain": "Prehospital / ambulance",
        "signals": ["south central ambulance service", "patient clinical report",
                    "gp patient report v3", "scas clinician", "news2 score",
                    "pops score", "nature of call", "incident number",
                    "conveyance", "at patient side"],
        "page_strategy": "all",  # CRITICAL: page 6 contains clinical conclusion (OBS-005)
        "versions": ["GP Report for Information v4.7.1 (2 pages)",
                     "GP Patient Report v3.62 (6-9 pages)"],
    },

    # ── Prefix 6: Specialist outpatient (complex) ────────────────────────────
    "Renal / Nephrology Letter": {
        "prefix": "6",
        "confidence_threshold": 0.72,
        "domain": "Nephrology / CKD monitoring",
        "signals": ["nephrologist", "nephrology", "berkshire kidney", "egfr",
                    "creatinine", "renal medicine", "albumin creatinine ratio",
                    "remote monitoring team", "kidney unit"],
        "page_strategy": "all",
    },
    "Paediatric Cardiology Letter": {
        "prefix": "6",
        "confidence_threshold": 0.70,
        "domain": "Paediatric cardiology",
        "signals": ["paediatric cardiol", "paediatric and fetal cardiologist",
                    "congenital heart", "ep mdt", "ablation", "svt",
                    "supraventricular tachycardia", "accessory pathway", "atenolol"],
        "page_strategy": "all",
    },
    "Medication / Prescriber Letter": {
        "prefix": "6/9",
        "confidence_threshold": 0.72,
        "domain": "Online prescribing / weight management",
        "signals": ["expert health", "notification of consultation", "kwikpen",
                    "weight management", "glp-1", "mounjaro", "semaglutide",
                    "ozempic", "wegovy", "weight loss programme"],
        "page_strategy": "page1_clinical",  # OBS-006: pages 2+ are lifestyle Q&A noise
    },

    # ── Prefix 7: Complex outpatient ─────────────────────────────────────────
    "Mental Health Inpatient Discharge": {
        "prefix": "7",
        "confidence_threshold": 0.68,
        "domain": "Psychiatry inpatient",
        "signals": ["mental health inpatient discharge", "prospect park hospital",
                    "crhtt", "cmht", "snowdrop ward", "section 2", "section 3",
                    "mental health act", "inpatient consultant"],
        "page_strategy": "all",
        "sensitive": True,  # OBS-007: contains overdose/MH crisis details
    },
    "Antenatal Discharge Summary": {
        "prefix": "7",
        "confidence_threshold": 0.68,
        "domain": "Obstetrics",
        "signals": ["antenatal discharge", "estimate delivery date", "estimate gestational age",
                    "gravida & parity", "reduced fetal movement", "mdau",
                    "antenatal discharge summary"],
        "page_strategy": "all",
        "sensitive": True,  # OBS-007: may contain bereavement markers (Poppy, neonatal death)
    },
    "Early Pregnancy / Gynaecology Letter": {
        "prefix": "7",
        "confidence_threshold": 0.68,
        "domain": "Early pregnancy / gynaecology",
        "signals": ["ugcc", "epau", "early pregnancy", "gestational sac", "transvaginal",
                    "intrauterine pregnancy", "gravida", "uncertain viability",
                    "emergency gynaecology"],
        "page_strategy": "all",
    },
    "Pre-admission Letter": {
        "prefix": "7",
        "confidence_threshold": 0.70,
        "domain": "Surgical booking",
        "signals": ["fasting instructions", "hospital admission has been scheduled",
                    "do not eat after", "admission instructions", "day surgery unit",
                    "bring this letter with you"],
        "page_strategy": "all",
    },

    # ── Prefix 8: Ophthalmology outpatient ───────────────────────────────────
    "Ophthalmology Letter": {
        "prefix": "8",
        "confidence_threshold": 0.70,
        "domain": "Ophthalmology / medical retina",
        "signals": ["diabetic retinopathy", "medical retina", "ophthalmology",
                    "proliferative retinopathy", "macular oedema", "visual acuity",
                    "iop", "fundus exam", "prp", "panretinal", "neovascularisation",
                    "nvd", "nve", "slit lamp", "ophthalmic"],
        "page_strategy": "all",
        "dr_grading": "R0-R3A, M0-M1, P0-P1",  # NHS Diabetic Retinopathy grading
    },

    # ── Prefix 9: Ophthalmology referral + mixed ──────────────────────────────
    "Ophthalmology Referral": {
        "prefix": "9",
        "confidence_threshold": 0.62,   # OBS-004: complex prescription tables (Evolutio)
        "domain": "Community eye referral (Evolutio / eRefer)",
        "signals": ["evolutio ophthalmology", "evolutio care innovations",
                    "patient ophthalmology referral", "east berkshire community eye service",
                    "erefer referral", "referral id number", "triager action required",
                    "odtc.co.uk"],
        "page_strategy": "all",
    },

    # ── Prefix 10: General outpatient ─────────────────────────────────────────
    "Psychiatry Outpatient Letter": {
        "prefix": "10",
        "confidence_threshold": 0.72,
        "domain": "Outpatient psychiatry",
        "signals": ["psychiatrist", "psychiatric", "bipolar", "icd10", "icd-10",
                    "quetiapine", "lisdexamfetamine", "consultant psychiatrist"],
        "page_strategy": "all",
    },
    "Haematology Outpatient Letter": {
        "prefix": "10",
        "confidence_threshold": 0.70,
        "domain": "Haematology / oncology",
        "signals": ["haematology", "myeloma", "multiple myeloma", "lenalidomide",
                    "bortezomib", "protein electrophoresis", "paraprotein"],
        "page_strategy": "all",
    },
    "Procedure Report": {
        "prefix": "10",
        "confidence_threshold": 0.72,
        "domain": "Endoscopy / procedural",
        "signals": ["endoscopy", "ogd", "colonoscopy", "gastroscopy", "oesophageal",
                    "colonography", "procedure report", "endoscopist"],
        "page_strategy": "all",
    },
}

# Ordered list of type names for the classifier (priority matters — specific before general)
CLASSIFICATION_ORDER: List[str] = [
    "Ambulance Clinical Report",
    "Ophthalmology Referral",
    "Medication / Prescriber Letter",
    "ED Discharge Letter",
    "111 First ED Report",
    "Mental Health Inpatient Discharge",
    "Antenatal Discharge Summary",
    "Cancer Surveillance Letter",
    "HIV / GUM Clinic Letter",
    "Early Pregnancy / Gynaecology Letter",
    "Pre-admission Letter",
    "Maternity / Diabetes Letter",
    "Surgical Outpatient Letter",
    "Procedure Report",
    "CAMHS Discharge Summary",
    "Discharge Summary",
    "Ophthalmology Letter",
    "Renal / Nephrology Letter",
    "Paediatric Cardiology Letter",
    "Psychiatry Outpatient Letter",
    "Haematology Outpatient Letter",
]

# ── Convenience accessors ────────────────────────────────────────────────────

def get_threshold(letter_type: str) -> float:
    """Return the calibrated confidence threshold for a document type.
    Thresholds reflect real AWS Textract + Comprehend Medical + Bedrock output
    ranges on scanned NHS clinical documents (40-document corpus, April 2026).
    """
    cfg = DOCUMENT_TYPES.get(letter_type, {})
    return cfg.get("confidence_threshold", 0.72)   # default 0.72, not 0.85


def get_page_strategy(letter_type: str) -> str:
    """Return the page processing strategy for a document type.
    'all'             — concatenate all pages (default)
    'page1_clinical'  — use all pages for OCR but limit LLM input to page 1
    """
    cfg = DOCUMENT_TYPES.get(letter_type, {})
    return cfg.get("page_strategy", "all")


def is_sensitive_type(letter_type: str) -> bool:
    """Return True if this document type is flagged as inherently sensitive."""
    cfg = DOCUMENT_TYPES.get(letter_type, {})
    return cfg.get("sensitive", False)


def all_type_names() -> List[str]:
    """Return all 21 registered document type names."""
    return list(DOCUMENT_TYPES.keys())
