"""
Clinical Abbreviation Resolver

Expands NHS/UK clinical abbreviations while preserving the original form.
Runs before entity extraction to improve NER accuracy.

Returns both:
  - Original abbreviation
  - Expanded full form
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple, Any
from enum import Enum


class AbbreviationCategory(Enum):
    """Categories of clinical abbreviations."""
    DIAGNOSIS = "diagnosis"
    SYMPTOM = "symptom"
    EXAMINATION = "examination"
    INVESTIGATION = "investigation"
    PROCEDURE = "procedure"
    MEDICATION = "medication"
    ANATOMY = "anatomy"
    VITAL_SIGN = "vital_sign"
    CLINICAL_SCORE = "clinical_score"
    HISTORY = "history"
    ADMINISTRATION = "administration"
    TIMING = "timing"
    ORGANISATION = "organisation"
    GENERAL = "general"


@dataclass
class ResolvedAbbreviation:
    """A resolved abbreviation with both forms."""
    abbreviation: str
    expansion: str
    category: AbbreviationCategory
    start_pos: int
    end_pos: int
    confidence: float = 1.0
    context_hint: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            "abbreviation": self.abbreviation,
            "expansion": self.expansion,
            "category": self.category.value,
            "start_pos": self.start_pos,
            "end_pos": self.end_pos,
            "confidence": self.confidence,
            "context_hint": self.context_hint,
        }


@dataclass
class ResolutionResult:
    """Result of abbreviation resolution."""
    original_text: str
    expanded_text: str
    resolved_abbreviations: List[ResolvedAbbreviation]
    stats: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "original_text": self.original_text,
            "expanded_text": self.expanded_text,
            "abbreviations": [a.to_dict() for a in self.resolved_abbreviations],
            "stats": self.stats,
        }


# Comprehensive NHS/UK Clinical Abbreviations Dictionary
# Format: abbreviation -> (expansion, category)
CLINICAL_ABBREVIATIONS: Dict[str, Tuple[str, AbbreviationCategory]] = {
    # ══════════════════════════════════════════════════════════════════════════
    # SYMPTOMS & CLINICAL FINDINGS
    # ══════════════════════════════════════════════════════════════════════════
    "LOC": ("Loss of Consciousness", AbbreviationCategory.SYMPTOM),
    "SOB": ("Shortness of Breath", AbbreviationCategory.SYMPTOM),
    "SOBOE": ("Shortness of Breath on Exertion", AbbreviationCategory.SYMPTOM),
    "DOE": ("Dyspnoea on Exertion", AbbreviationCategory.SYMPTOM),
    "PND": ("Paroxysmal Nocturnal Dyspnoea", AbbreviationCategory.SYMPTOM),
    "CP": ("Chest Pain", AbbreviationCategory.SYMPTOM),
    "N&V": ("Nausea and Vomiting", AbbreviationCategory.SYMPTOM),
    "N+V": ("Nausea and Vomiting", AbbreviationCategory.SYMPTOM),
    "D&V": ("Diarrhoea and Vomiting", AbbreviationCategory.SYMPTOM),
    "D+V": ("Diarrhoea and Vomiting", AbbreviationCategory.SYMPTOM),
    "HA": ("Headache", AbbreviationCategory.SYMPTOM),
    "H/A": ("Headache", AbbreviationCategory.SYMPTOM),
    "LBP": ("Lower Back Pain", AbbreviationCategory.SYMPTOM),
    "MSK": ("Musculoskeletal", AbbreviationCategory.SYMPTOM),
    "BPPV": ("Benign Paroxysmal Positional Vertigo", AbbreviationCategory.SYMPTOM),
    "GORD": ("Gastro-Oesophageal Reflux Disease", AbbreviationCategory.SYMPTOM),
    "GERD": ("Gastro-Esophageal Reflux Disease", AbbreviationCategory.SYMPTOM),
    "LUTS": ("Lower Urinary Tract Symptoms", AbbreviationCategory.SYMPTOM),
    "OA": ("Osteoarthritis", AbbreviationCategory.SYMPTOM),
    "RA": ("Rheumatoid Arthritis", AbbreviationCategory.SYMPTOM),
    "JVD": ("Jugular Venous Distension", AbbreviationCategory.SYMPTOM),

    # ══════════════════════════════════════════════════════════════════════════
    # DIAGNOSES & CONDITIONS
    # ══════════════════════════════════════════════════════════════════════════
    "TIA": ("Transient Ischaemic Attack", AbbreviationCategory.DIAGNOSIS),
    "CVA": ("Cerebrovascular Accident", AbbreviationCategory.DIAGNOSIS),
    "MI": ("Myocardial Infarction", AbbreviationCategory.DIAGNOSIS),
    "AMI": ("Acute Myocardial Infarction", AbbreviationCategory.DIAGNOSIS),
    "NSTEMI": ("Non-ST Elevation Myocardial Infarction", AbbreviationCategory.DIAGNOSIS),
    "STEMI": ("ST Elevation Myocardial Infarction", AbbreviationCategory.DIAGNOSIS),
    "ACS": ("Acute Coronary Syndrome", AbbreviationCategory.DIAGNOSIS),
    "AF": ("Atrial Fibrillation", AbbreviationCategory.DIAGNOSIS),
    "AFib": ("Atrial Fibrillation", AbbreviationCategory.DIAGNOSIS),
    "SVT": ("Supraventricular Tachycardia", AbbreviationCategory.DIAGNOSIS),
    "VT": ("Ventricular Tachycardia", AbbreviationCategory.DIAGNOSIS),
    "VF": ("Ventricular Fibrillation", AbbreviationCategory.DIAGNOSIS),
    "CHF": ("Congestive Heart Failure", AbbreviationCategory.DIAGNOSIS),
    "CCF": ("Congestive Cardiac Failure", AbbreviationCategory.DIAGNOSIS),
    "HF": ("Heart Failure", AbbreviationCategory.DIAGNOSIS),
    "HFrEF": ("Heart Failure with Reduced Ejection Fraction", AbbreviationCategory.DIAGNOSIS),
    "HFpEF": ("Heart Failure with Preserved Ejection Fraction", AbbreviationCategory.DIAGNOSIS),
    "HTN": ("Hypertension", AbbreviationCategory.DIAGNOSIS),
    "PE": ("Pulmonary Embolism", AbbreviationCategory.DIAGNOSIS),
    "DVT": ("Deep Vein Thrombosis", AbbreviationCategory.DIAGNOSIS),
    "VTE": ("Venous Thromboembolism", AbbreviationCategory.DIAGNOSIS),
    "COPD": ("Chronic Obstructive Pulmonary Disease", AbbreviationCategory.DIAGNOSIS),
    "LRTI": ("Lower Respiratory Tract Infection", AbbreviationCategory.DIAGNOSIS),
    "URTI": ("Upper Respiratory Tract Infection", AbbreviationCategory.DIAGNOSIS),
    "CAP": ("Community Acquired Pneumonia", AbbreviationCategory.DIAGNOSIS),
    "HAP": ("Hospital Acquired Pneumonia", AbbreviationCategory.DIAGNOSIS),
    "VAP": ("Ventilator Associated Pneumonia", AbbreviationCategory.DIAGNOSIS),
    "UTI": ("Urinary Tract Infection", AbbreviationCategory.DIAGNOSIS),
    "AKI": ("Acute Kidney Injury", AbbreviationCategory.DIAGNOSIS),
    "CKD": ("Chronic Kidney Disease", AbbreviationCategory.DIAGNOSIS),
    "ESRF": ("End Stage Renal Failure", AbbreviationCategory.DIAGNOSIS),
    "ESKD": ("End Stage Kidney Disease", AbbreviationCategory.DIAGNOSIS),
    "DM": ("Diabetes Mellitus", AbbreviationCategory.DIAGNOSIS),
    "T1DM": ("Type 1 Diabetes Mellitus", AbbreviationCategory.DIAGNOSIS),
    "T2DM": ("Type 2 Diabetes Mellitus", AbbreviationCategory.DIAGNOSIS),
    "IDDM": ("Insulin Dependent Diabetes Mellitus", AbbreviationCategory.DIAGNOSIS),
    "NIDDM": ("Non-Insulin Dependent Diabetes Mellitus", AbbreviationCategory.DIAGNOSIS),
    "DKA": ("Diabetic Ketoacidosis", AbbreviationCategory.DIAGNOSIS),
    "HHS": ("Hyperosmolar Hyperglycaemic State", AbbreviationCategory.DIAGNOSIS),
    "HONK": ("Hyperosmolar Non-Ketotic State", AbbreviationCategory.DIAGNOSIS),
    "SAH": ("Subarachnoid Haemorrhage", AbbreviationCategory.DIAGNOSIS),
    "SDH": ("Subdural Haematoma", AbbreviationCategory.DIAGNOSIS),
    "EDH": ("Extradural Haematoma", AbbreviationCategory.DIAGNOSIS),
    "ICH": ("Intracerebral Haemorrhage", AbbreviationCategory.DIAGNOSIS),
    "IHD": ("Ischaemic Heart Disease", AbbreviationCategory.DIAGNOSIS),
    "CAD": ("Coronary Artery Disease", AbbreviationCategory.DIAGNOSIS),
    "PVD": ("Peripheral Vascular Disease", AbbreviationCategory.DIAGNOSIS),
    "PAD": ("Peripheral Arterial Disease", AbbreviationCategory.DIAGNOSIS),
    "AAA": ("Abdominal Aortic Aneurysm", AbbreviationCategory.DIAGNOSIS),
    "IBD": ("Inflammatory Bowel Disease", AbbreviationCategory.DIAGNOSIS),
    "UC": ("Ulcerative Colitis", AbbreviationCategory.DIAGNOSIS),
    "CD": ("Crohn's Disease", AbbreviationCategory.DIAGNOSIS),
    "IBS": ("Irritable Bowel Syndrome", AbbreviationCategory.DIAGNOSIS),
    "PUD": ("Peptic Ulcer Disease", AbbreviationCategory.DIAGNOSIS),
    "GIB": ("Gastrointestinal Bleed", AbbreviationCategory.DIAGNOSIS),
    "UGIB": ("Upper Gastrointestinal Bleed", AbbreviationCategory.DIAGNOSIS),
    "LGIB": ("Lower Gastrointestinal Bleed", AbbreviationCategory.DIAGNOSIS),
    "SBO": ("Small Bowel Obstruction", AbbreviationCategory.DIAGNOSIS),
    "LBO": ("Large Bowel Obstruction", AbbreviationCategory.DIAGNOSIS),
    "BPH": ("Benign Prostatic Hyperplasia", AbbreviationCategory.DIAGNOSIS),
    "PCOS": ("Polycystic Ovary Syndrome", AbbreviationCategory.DIAGNOSIS),
    "PID": ("Pelvic Inflammatory Disease", AbbreviationCategory.DIAGNOSIS),
    "SLE": ("Systemic Lupus Erythematosus", AbbreviationCategory.DIAGNOSIS),
    "PMR": ("Polymyalgia Rheumatica", AbbreviationCategory.DIAGNOSIS),
    "GCA": ("Giant Cell Arteritis", AbbreviationCategory.DIAGNOSIS),
    "MS": ("Multiple Sclerosis", AbbreviationCategory.DIAGNOSIS),
    "PD": ("Parkinson's Disease", AbbreviationCategory.DIAGNOSIS),
    "AD": ("Alzheimer's Disease", AbbreviationCategory.DIAGNOSIS),
    "MND": ("Motor Neurone Disease", AbbreviationCategory.DIAGNOSIS),
    "ALS": ("Amyotrophic Lateral Sclerosis", AbbreviationCategory.DIAGNOSIS),
    "GBS": ("Guillain-Barré Syndrome", AbbreviationCategory.DIAGNOSIS),
    "CTS": ("Carpal Tunnel Syndrome", AbbreviationCategory.DIAGNOSIS),
    "TB": ("Tuberculosis", AbbreviationCategory.DIAGNOSIS),
    "HIV": ("Human Immunodeficiency Virus", AbbreviationCategory.DIAGNOSIS),
    "AIDS": ("Acquired Immunodeficiency Syndrome", AbbreviationCategory.DIAGNOSIS),
    "MRSA": ("Methicillin-Resistant Staphylococcus Aureus", AbbreviationCategory.DIAGNOSIS),
    "VRE": ("Vancomycin-Resistant Enterococcus", AbbreviationCategory.DIAGNOSIS),
    "C.diff": ("Clostridioides difficile", AbbreviationCategory.DIAGNOSIS),
    "CDI": ("Clostridioides difficile Infection", AbbreviationCategory.DIAGNOSIS),
    "CJD": ("Creutzfeldt-Jakob Disease", AbbreviationCategory.DIAGNOSIS),
    "ARDS": ("Acute Respiratory Distress Syndrome", AbbreviationCategory.DIAGNOSIS),
    "OSA": ("Obstructive Sleep Apnoea", AbbreviationCategory.DIAGNOSIS),
    "MODY": ("Maturity Onset Diabetes of the Young", AbbreviationCategory.DIAGNOSIS),

    # ══════════════════════════════════════════════════════════════════════════
    # EXAMINATION FINDINGS
    # ══════════════════════════════════════════════════════════════════════════
    "SNT": ("Soft Non-Tender", AbbreviationCategory.EXAMINATION),
    "SNNT": ("Soft Non-Tender Non-Distended", AbbreviationCategory.EXAMINATION),
    "BS": ("Bowel Sounds", AbbreviationCategory.EXAMINATION),
    "BS+": ("Bowel Sounds Present", AbbreviationCategory.EXAMINATION),
    "HS": ("Heart Sounds", AbbreviationCategory.EXAMINATION),
    "HSI+II": ("Heart Sounds I and II", AbbreviationCategory.EXAMINATION),
    "HS I+II": ("Heart Sounds I and II", AbbreviationCategory.EXAMINATION),
    "S1S2": ("First and Second Heart Sounds", AbbreviationCategory.EXAMINATION),
    "S1 S2": ("First and Second Heart Sounds", AbbreviationCategory.EXAMINATION),
    "NAD": ("No Abnormality Detected", AbbreviationCategory.EXAMINATION),
    "NIL": ("Nothing/None", AbbreviationCategory.EXAMINATION),
    "WNL": ("Within Normal Limits", AbbreviationCategory.EXAMINATION),
    "PERLA": ("Pupils Equal and Reactive to Light and Accommodation", AbbreviationCategory.EXAMINATION),
    "PERRLA": ("Pupils Equal Round Reactive to Light and Accommodation", AbbreviationCategory.EXAMINATION),
    "PEARL": ("Pupils Equal and Reactive to Light", AbbreviationCategory.EXAMINATION),
    "EOMI": ("Extra-Ocular Movements Intact", AbbreviationCategory.EXAMINATION),
    "EOM": ("Extra-Ocular Movements", AbbreviationCategory.EXAMINATION),
    "JVP": ("Jugular Venous Pressure", AbbreviationCategory.EXAMINATION),
    "CRT": ("Capillary Refill Time", AbbreviationCategory.EXAMINATION),
    "DTR": ("Deep Tendon Reflexes", AbbreviationCategory.EXAMINATION),
    "ROM": ("Range of Movement", AbbreviationCategory.EXAMINATION),
    "AROM": ("Active Range of Movement", AbbreviationCategory.EXAMINATION),
    "PROM": ("Passive Range of Movement", AbbreviationCategory.EXAMINATION),
    "TTP": ("Tenderness to Palpation", AbbreviationCategory.EXAMINATION),
    "RRR": ("Regular Rate and Rhythm", AbbreviationCategory.EXAMINATION),
    "CTAB": ("Clear to Auscultation Bilaterally", AbbreviationCategory.EXAMINATION),
    "AE": ("Air Entry", AbbreviationCategory.EXAMINATION),
    "AE=": ("Air Entry Equal", AbbreviationCategory.EXAMINATION),
    "AEBS": ("Air Entry Bilateral Satisfactory", AbbreviationCategory.EXAMINATION),
    "VE": ("Vesicular Breathing", AbbreviationCategory.EXAMINATION),
    "VBS": ("Vesicular Breath Sounds", AbbreviationCategory.EXAMINATION),
    "RUQ": ("Right Upper Quadrant", AbbreviationCategory.EXAMINATION),
    "LUQ": ("Left Upper Quadrant", AbbreviationCategory.EXAMINATION),
    "RLQ": ("Right Lower Quadrant", AbbreviationCategory.EXAMINATION),
    "LLQ": ("Left Lower Quadrant", AbbreviationCategory.EXAMINATION),
    "RIF": ("Right Iliac Fossa", AbbreviationCategory.EXAMINATION),
    "LIF": ("Left Iliac Fossa", AbbreviationCategory.EXAMINATION),
    "RMG": ("Renal Angle", AbbreviationCategory.EXAMINATION),
    "HSM": ("Hepatosplenomegaly", AbbreviationCategory.EXAMINATION),
    "AAO": ("Awake Alert Oriented", AbbreviationCategory.EXAMINATION),
    "A&O": ("Alert and Oriented", AbbreviationCategory.EXAMINATION),
    "AOx3": ("Alert and Oriented x3 (person, place, time)", AbbreviationCategory.EXAMINATION),
    "AOx4": ("Alert and Oriented x4 (person, place, time, situation)", AbbreviationCategory.EXAMINATION),

    # ══════════════════════════════════════════════════════════════════════════
    # ANATOMY
    # ══════════════════════════════════════════════════════════════════════════
    "UL": ("Upper Limb", AbbreviationCategory.ANATOMY),
    "LL": ("Lower Limb", AbbreviationCategory.ANATOMY),
    "UE": ("Upper Extremity", AbbreviationCategory.ANATOMY),
    "LE": ("Lower Extremity", AbbreviationCategory.ANATOMY),
    "RUL": ("Right Upper Lobe", AbbreviationCategory.ANATOMY),
    "RML": ("Right Middle Lobe", AbbreviationCategory.ANATOMY),
    "RLL": ("Right Lower Lobe", AbbreviationCategory.ANATOMY),
    "LUL": ("Left Upper Lobe", AbbreviationCategory.ANATOMY),
    "LLL": ("Left Lower Lobe", AbbreviationCategory.ANATOMY),
    "LAD": ("Left Anterior Descending", AbbreviationCategory.ANATOMY),
    "LCx": ("Left Circumflex", AbbreviationCategory.ANATOMY),
    "RCA": ("Right Coronary Artery", AbbreviationCategory.ANATOMY),
    "LV": ("Left Ventricle", AbbreviationCategory.ANATOMY),
    "RV": ("Right Ventricle", AbbreviationCategory.ANATOMY),
    "LA": ("Left Atrium", AbbreviationCategory.ANATOMY),
    "RA": ("Right Atrium", AbbreviationCategory.ANATOMY),
    "IVC": ("Inferior Vena Cava", AbbreviationCategory.ANATOMY),
    "SVC": ("Superior Vena Cava", AbbreviationCategory.ANATOMY),
    "PA": ("Pulmonary Artery", AbbreviationCategory.ANATOMY),
    "MCA": ("Middle Cerebral Artery", AbbreviationCategory.ANATOMY),
    "ACA": ("Anterior Cerebral Artery", AbbreviationCategory.ANATOMY),
    "PCA": ("Posterior Cerebral Artery", AbbreviationCategory.ANATOMY),
    "ICA": ("Internal Carotid Artery", AbbreviationCategory.ANATOMY),
    "ECA": ("External Carotid Artery", AbbreviationCategory.ANATOMY),
    "CCA": ("Common Carotid Artery", AbbreviationCategory.ANATOMY),
    "CNS": ("Central Nervous System", AbbreviationCategory.ANATOMY),
    "PNS": ("Peripheral Nervous System", AbbreviationCategory.ANATOMY),
    "ANS": ("Autonomic Nervous System", AbbreviationCategory.ANATOMY),
    "CN": ("Cranial Nerve", AbbreviationCategory.ANATOMY),
    "CN I": ("Cranial Nerve I (Olfactory)", AbbreviationCategory.ANATOMY),
    "CN II": ("Cranial Nerve II (Optic)", AbbreviationCategory.ANATOMY),
    "CN III": ("Cranial Nerve III (Oculomotor)", AbbreviationCategory.ANATOMY),
    "CN IV": ("Cranial Nerve IV (Trochlear)", AbbreviationCategory.ANATOMY),
    "CN V": ("Cranial Nerve V (Trigeminal)", AbbreviationCategory.ANATOMY),
    "CN VI": ("Cranial Nerve VI (Abducens)", AbbreviationCategory.ANATOMY),
    "CN VII": ("Cranial Nerve VII (Facial)", AbbreviationCategory.ANATOMY),
    "CN VIII": ("Cranial Nerve VIII (Vestibulocochlear)", AbbreviationCategory.ANATOMY),
    "CN IX": ("Cranial Nerve IX (Glossopharyngeal)", AbbreviationCategory.ANATOMY),
    "CN X": ("Cranial Nerve X (Vagus)", AbbreviationCategory.ANATOMY),
    "CN XI": ("Cranial Nerve XI (Accessory)", AbbreviationCategory.ANATOMY),
    "CN XII": ("Cranial Nerve XII (Hypoglossal)", AbbreviationCategory.ANATOMY),
    "CN II-XII": ("Cranial Nerves II-XII", AbbreviationCategory.ANATOMY),
    "CN 2-12": ("Cranial Nerves 2-12", AbbreviationCategory.ANATOMY),
    "GI": ("Gastrointestinal", AbbreviationCategory.ANATOMY),
    "GU": ("Genitourinary", AbbreviationCategory.ANATOMY),
    "CVS": ("Cardiovascular System", AbbreviationCategory.ANATOMY),
    "RS": ("Respiratory System", AbbreviationCategory.ANATOMY),
    "Resp": ("Respiratory", AbbreviationCategory.ANATOMY),
    "Neuro": ("Neurological", AbbreviationCategory.ANATOMY),
    "MSK": ("Musculoskeletal", AbbreviationCategory.ANATOMY),
    "ENT": ("Ear Nose and Throat", AbbreviationCategory.ANATOMY),
    "TMJ": ("Temporomandibular Joint", AbbreviationCategory.ANATOMY),
    "ACJ": ("Acromioclavicular Joint", AbbreviationCategory.ANATOMY),
    "MCP": ("Metacarpophalangeal", AbbreviationCategory.ANATOMY),
    "PIP": ("Proximal Interphalangeal", AbbreviationCategory.ANATOMY),
    "DIP": ("Distal Interphalangeal", AbbreviationCategory.ANATOMY),
    "MTP": ("Metatarsophalangeal", AbbreviationCategory.ANATOMY),
    "SI": ("Sacroiliac", AbbreviationCategory.ANATOMY),
    "C-spine": ("Cervical Spine", AbbreviationCategory.ANATOMY),
    "T-spine": ("Thoracic Spine", AbbreviationCategory.ANATOMY),
    "L-spine": ("Lumbar Spine", AbbreviationCategory.ANATOMY),

    # ══════════════════════════════════════════════════════════════════════════
    # VITAL SIGNS
    # ══════════════════════════════════════════════════════════════════════════
    "BP": ("Blood Pressure", AbbreviationCategory.VITAL_SIGN),
    "SBP": ("Systolic Blood Pressure", AbbreviationCategory.VITAL_SIGN),
    "DBP": ("Diastolic Blood Pressure", AbbreviationCategory.VITAL_SIGN),
    "MAP": ("Mean Arterial Pressure", AbbreviationCategory.VITAL_SIGN),
    "HR": ("Heart Rate", AbbreviationCategory.VITAL_SIGN),
    "PR": ("Pulse Rate", AbbreviationCategory.VITAL_SIGN),
    "RR": ("Respiratory Rate", AbbreviationCategory.VITAL_SIGN),
    "SpO2": ("Oxygen Saturation", AbbreviationCategory.VITAL_SIGN),
    "SaO2": ("Arterial Oxygen Saturation", AbbreviationCategory.VITAL_SIGN),
    "O2 sats": ("Oxygen Saturation", AbbreviationCategory.VITAL_SIGN),
    "Sats": ("Oxygen Saturation", AbbreviationCategory.VITAL_SIGN),
    "Temp": ("Temperature", AbbreviationCategory.VITAL_SIGN),
    "T": ("Temperature", AbbreviationCategory.VITAL_SIGN),
    "Wt": ("Weight", AbbreviationCategory.VITAL_SIGN),
    "Ht": ("Height", AbbreviationCategory.VITAL_SIGN),
    "BMI": ("Body Mass Index", AbbreviationCategory.VITAL_SIGN),
    "BSA": ("Body Surface Area", AbbreviationCategory.VITAL_SIGN),
    "CVP": ("Central Venous Pressure", AbbreviationCategory.VITAL_SIGN),
    "PAWP": ("Pulmonary Artery Wedge Pressure", AbbreviationCategory.VITAL_SIGN),
    "PCWP": ("Pulmonary Capillary Wedge Pressure", AbbreviationCategory.VITAL_SIGN),
    "CO": ("Cardiac Output", AbbreviationCategory.VITAL_SIGN),
    "CI": ("Cardiac Index", AbbreviationCategory.VITAL_SIGN),
    "SVR": ("Systemic Vascular Resistance", AbbreviationCategory.VITAL_SIGN),
    "PVR": ("Pulmonary Vascular Resistance", AbbreviationCategory.VITAL_SIGN),

    # ══════════════════════════════════════════════════════════════════════════
    # CLINICAL SCORES
    # ══════════════════════════════════════════════════════════════════════════
    "GCS": ("Glasgow Coma Scale", AbbreviationCategory.CLINICAL_SCORE),
    "AVPU": ("Alert Voice Pain Unresponsive", AbbreviationCategory.CLINICAL_SCORE),
    "NEWS": ("National Early Warning Score", AbbreviationCategory.CLINICAL_SCORE),
    "NEWS2": ("National Early Warning Score 2", AbbreviationCategory.CLINICAL_SCORE),
    "MEWS": ("Modified Early Warning Score", AbbreviationCategory.CLINICAL_SCORE),
    "qSOFA": ("Quick Sequential Organ Failure Assessment", AbbreviationCategory.CLINICAL_SCORE),
    "SOFA": ("Sequential Organ Failure Assessment", AbbreviationCategory.CLINICAL_SCORE),
    "APACHE": ("Acute Physiology and Chronic Health Evaluation", AbbreviationCategory.CLINICAL_SCORE),
    "APACHE II": ("Acute Physiology and Chronic Health Evaluation II", AbbreviationCategory.CLINICAL_SCORE),
    "CURB-65": ("Confusion Urea Respiratory Rate Blood Pressure Age 65", AbbreviationCategory.CLINICAL_SCORE),
    "CURB65": ("Confusion Urea Respiratory Rate Blood Pressure Age 65", AbbreviationCategory.CLINICAL_SCORE),
    "CRB-65": ("Confusion Respiratory Rate Blood Pressure Age 65", AbbreviationCategory.CLINICAL_SCORE),
    "Wells": ("Wells Score for DVT/PE", AbbreviationCategory.CLINICAL_SCORE),
    "PERC": ("Pulmonary Embolism Rule-out Criteria", AbbreviationCategory.CLINICAL_SCORE),
    "HEART": ("History ECG Age Risk Factors Troponin Score", AbbreviationCategory.CLINICAL_SCORE),
    "TIMI": ("Thrombolysis in Myocardial Infarction Score", AbbreviationCategory.CLINICAL_SCORE),
    "GRACE": ("Global Registry of Acute Coronary Events Score", AbbreviationCategory.CLINICAL_SCORE),
    "CHA2DS2-VASc": ("Congestive Heart Failure Hypertension Age Diabetes Stroke Vascular Disease Score", AbbreviationCategory.CLINICAL_SCORE),
    "CHADS2": ("Congestive Heart Failure Hypertension Age Diabetes Stroke Score", AbbreviationCategory.CLINICAL_SCORE),
    "HAS-BLED": ("Hypertension Abnormal Renal/Liver Function Stroke Bleeding Labile INR Elderly Drugs/Alcohol Score", AbbreviationCategory.CLINICAL_SCORE),
    "HASBLED": ("Hypertension Abnormal Renal/Liver Function Stroke Bleeding Labile INR Elderly Drugs/Alcohol Score", AbbreviationCategory.CLINICAL_SCORE),
    "Rockall": ("Rockall Score for GI Bleeding", AbbreviationCategory.CLINICAL_SCORE),
    "Blatchford": ("Glasgow-Blatchford Bleeding Score", AbbreviationCategory.CLINICAL_SCORE),
    "Child-Pugh": ("Child-Pugh Score for Liver Cirrhosis", AbbreviationCategory.CLINICAL_SCORE),
    "MELD": ("Model for End-Stage Liver Disease Score", AbbreviationCategory.CLINICAL_SCORE),
    "MMSE": ("Mini-Mental State Examination", AbbreviationCategory.CLINICAL_SCORE),
    "MoCA": ("Montreal Cognitive Assessment", AbbreviationCategory.CLINICAL_SCORE),
    "AMT": ("Abbreviated Mental Test", AbbreviationCategory.CLINICAL_SCORE),
    "AMT-4": ("Abbreviated Mental Test 4", AbbreviationCategory.CLINICAL_SCORE),
    "4AT": ("4 A's Test for Delirium", AbbreviationCategory.CLINICAL_SCORE),
    "CAM": ("Confusion Assessment Method", AbbreviationCategory.CLINICAL_SCORE),
    "PHQ-9": ("Patient Health Questionnaire 9", AbbreviationCategory.CLINICAL_SCORE),
    "PHQ9": ("Patient Health Questionnaire 9", AbbreviationCategory.CLINICAL_SCORE),
    "GAD-7": ("Generalised Anxiety Disorder 7", AbbreviationCategory.CLINICAL_SCORE),
    "GAD7": ("Generalised Anxiety Disorder 7", AbbreviationCategory.CLINICAL_SCORE),
    "AUDIT": ("Alcohol Use Disorders Identification Test", AbbreviationCategory.CLINICAL_SCORE),
    "CAGE": ("Cut Down Annoyed Guilty Eye-Opener Questionnaire", AbbreviationCategory.CLINICAL_SCORE),
    "FAST": ("Fast Alcohol Screening Test", AbbreviationCategory.CLINICAL_SCORE),
    "CFS": ("Clinical Frailty Scale", AbbreviationCategory.CLINICAL_SCORE),
    "Rockwood": ("Rockwood Clinical Frailty Scale", AbbreviationCategory.CLINICAL_SCORE),
    "Waterlow": ("Waterlow Pressure Ulcer Risk Assessment", AbbreviationCategory.CLINICAL_SCORE),
    "MUST": ("Malnutrition Universal Screening Tool", AbbreviationCategory.CLINICAL_SCORE),
    "Barthel": ("Barthel Index of Activities of Daily Living", AbbreviationCategory.CLINICAL_SCORE),
    "Katz": ("Katz Index of Independence in ADL", AbbreviationCategory.CLINICAL_SCORE),
    "ADL": ("Activities of Daily Living", AbbreviationCategory.CLINICAL_SCORE),
    "IADL": ("Instrumental Activities of Daily Living", AbbreviationCategory.CLINICAL_SCORE),
    "NIHSS": ("National Institutes of Health Stroke Scale", AbbreviationCategory.CLINICAL_SCORE),
    "mRS": ("Modified Rankin Scale", AbbreviationCategory.CLINICAL_SCORE),
    "ABCD2": ("Age Blood Pressure Clinical Features Duration Diabetes Score", AbbreviationCategory.CLINICAL_SCORE),
    "VAS": ("Visual Analogue Scale", AbbreviationCategory.CLINICAL_SCORE),
    "NRS": ("Numeric Rating Scale", AbbreviationCategory.CLINICAL_SCORE),

    # ══════════════════════════════════════════════════════════════════════════
    # INVESTIGATIONS & LAB TESTS
    # ══════════════════════════════════════════════════════════════════════════
    "FBC": ("Full Blood Count", AbbreviationCategory.INVESTIGATION),
    "CBC": ("Complete Blood Count", AbbreviationCategory.INVESTIGATION),
    "U&E": ("Urea and Electrolytes", AbbreviationCategory.INVESTIGATION),
    "U+E": ("Urea and Electrolytes", AbbreviationCategory.INVESTIGATION),
    "UE": ("Urea and Electrolytes", AbbreviationCategory.INVESTIGATION),
    "U&Es": ("Urea and Electrolytes", AbbreviationCategory.INVESTIGATION),
    "RFT": ("Renal Function Tests", AbbreviationCategory.INVESTIGATION),
    "LFT": ("Liver Function Tests", AbbreviationCategory.INVESTIGATION),
    "LFTs": ("Liver Function Tests", AbbreviationCategory.INVESTIGATION),
    "TFT": ("Thyroid Function Tests", AbbreviationCategory.INVESTIGATION),
    "TFTs": ("Thyroid Function Tests", AbbreviationCategory.INVESTIGATION),
    "BMP": ("Basic Metabolic Panel", AbbreviationCategory.INVESTIGATION),
    "CMP": ("Comprehensive Metabolic Panel", AbbreviationCategory.INVESTIGATION),
    "CRP": ("C-Reactive Protein", AbbreviationCategory.INVESTIGATION),
    "ESR": ("Erythrocyte Sedimentation Rate", AbbreviationCategory.INVESTIGATION),
    "PCT": ("Procalcitonin", AbbreviationCategory.INVESTIGATION),
    "INR": ("International Normalised Ratio", AbbreviationCategory.INVESTIGATION),
    "PT": ("Prothrombin Time", AbbreviationCategory.INVESTIGATION),
    "APTT": ("Activated Partial Thromboplastin Time", AbbreviationCategory.INVESTIGATION),
    "aPTT": ("Activated Partial Thromboplastin Time", AbbreviationCategory.INVESTIGATION),
    "PTT": ("Partial Thromboplastin Time", AbbreviationCategory.INVESTIGATION),
    "D-dimer": ("D-dimer", AbbreviationCategory.INVESTIGATION),
    "Trop": ("Troponin", AbbreviationCategory.INVESTIGATION),
    "TnI": ("Troponin I", AbbreviationCategory.INVESTIGATION),
    "TnT": ("Troponin T", AbbreviationCategory.INVESTIGATION),
    "hsTrop": ("High-Sensitivity Troponin", AbbreviationCategory.INVESTIGATION),
    "hsTnT": ("High-Sensitivity Troponin T", AbbreviationCategory.INVESTIGATION),
    "hsTnI": ("High-Sensitivity Troponin I", AbbreviationCategory.INVESTIGATION),
    "BNP": ("B-type Natriuretic Peptide", AbbreviationCategory.INVESTIGATION),
    "NT-proBNP": ("N-terminal Pro B-type Natriuretic Peptide", AbbreviationCategory.INVESTIGATION),
    "ABG": ("Arterial Blood Gas", AbbreviationCategory.INVESTIGATION),
    "VBG": ("Venous Blood Gas", AbbreviationCategory.INVESTIGATION),
    "CBG": ("Capillary Blood Glucose", AbbreviationCategory.INVESTIGATION),
    "BM": ("Blood Glucose (from Boehringer Mannheim)", AbbreviationCategory.INVESTIGATION),
    "HbA1c": ("Glycated Haemoglobin", AbbreviationCategory.INVESTIGATION),
    "A1c": ("Glycated Haemoglobin", AbbreviationCategory.INVESTIGATION),
    "OGTT": ("Oral Glucose Tolerance Test", AbbreviationCategory.INVESTIGATION),
    "eGFR": ("Estimated Glomerular Filtration Rate", AbbreviationCategory.INVESTIGATION),
    "GFR": ("Glomerular Filtration Rate", AbbreviationCategory.INVESTIGATION),
    "Cr": ("Creatinine", AbbreviationCategory.INVESTIGATION),
    "BUN": ("Blood Urea Nitrogen", AbbreviationCategory.INVESTIGATION),
    "Ur": ("Urea", AbbreviationCategory.INVESTIGATION),
    "Na": ("Sodium", AbbreviationCategory.INVESTIGATION),
    "K": ("Potassium", AbbreviationCategory.INVESTIGATION),
    "Cl": ("Chloride", AbbreviationCategory.INVESTIGATION),
    "Ca": ("Calcium", AbbreviationCategory.INVESTIGATION),
    "Mg": ("Magnesium", AbbreviationCategory.INVESTIGATION),
    "PO4": ("Phosphate", AbbreviationCategory.INVESTIGATION),
    "Phos": ("Phosphate", AbbreviationCategory.INVESTIGATION),
    "Hb": ("Haemoglobin", AbbreviationCategory.INVESTIGATION),
    "Hgb": ("Haemoglobin", AbbreviationCategory.INVESTIGATION),
    "Hct": ("Haematocrit", AbbreviationCategory.INVESTIGATION),
    "WBC": ("White Blood Cell Count", AbbreviationCategory.INVESTIGATION),
    "WCC": ("White Cell Count", AbbreviationCategory.INVESTIGATION),
    "Plt": ("Platelets", AbbreviationCategory.INVESTIGATION),
    "Plts": ("Platelets", AbbreviationCategory.INVESTIGATION),
    "MCV": ("Mean Corpuscular Volume", AbbreviationCategory.INVESTIGATION),
    "MCH": ("Mean Corpuscular Haemoglobin", AbbreviationCategory.INVESTIGATION),
    "MCHC": ("Mean Corpuscular Haemoglobin Concentration", AbbreviationCategory.INVESTIGATION),
    "RDW": ("Red Cell Distribution Width", AbbreviationCategory.INVESTIGATION),
    "Retics": ("Reticulocytes", AbbreviationCategory.INVESTIGATION),
    "Bili": ("Bilirubin", AbbreviationCategory.INVESTIGATION),
    "ALT": ("Alanine Aminotransferase", AbbreviationCategory.INVESTIGATION),
    "AST": ("Aspartate Aminotransferase", AbbreviationCategory.INVESTIGATION),
    "ALP": ("Alkaline Phosphatase", AbbreviationCategory.INVESTIGATION),
    "GGT": ("Gamma-Glutamyl Transferase", AbbreviationCategory.INVESTIGATION),
    "Alb": ("Albumin", AbbreviationCategory.INVESTIGATION),
    "TP": ("Total Protein", AbbreviationCategory.INVESTIGATION),
    "Glob": ("Globulin", AbbreviationCategory.INVESTIGATION),
    "TSH": ("Thyroid Stimulating Hormone", AbbreviationCategory.INVESTIGATION),
    "T3": ("Triiodothyronine", AbbreviationCategory.INVESTIGATION),
    "T4": ("Thyroxine", AbbreviationCategory.INVESTIGATION),
    "fT4": ("Free Thyroxine", AbbreviationCategory.INVESTIGATION),
    "fT3": ("Free Triiodothyronine", AbbreviationCategory.INVESTIGATION),
    "PTH": ("Parathyroid Hormone", AbbreviationCategory.INVESTIGATION),
    "PSA": ("Prostate Specific Antigen", AbbreviationCategory.INVESTIGATION),
    "AFP": ("Alpha-Fetoprotein", AbbreviationCategory.INVESTIGATION),
    "CEA": ("Carcinoembryonic Antigen", AbbreviationCategory.INVESTIGATION),
    "CA-125": ("Cancer Antigen 125", AbbreviationCategory.INVESTIGATION),
    "CA 19-9": ("Cancer Antigen 19-9", AbbreviationCategory.INVESTIGATION),
    "LDH": ("Lactate Dehydrogenase", AbbreviationCategory.INVESTIGATION),
    "CK": ("Creatine Kinase", AbbreviationCategory.INVESTIGATION),
    "CPK": ("Creatine Phosphokinase", AbbreviationCategory.INVESTIGATION),
    "Amylase": ("Amylase", AbbreviationCategory.INVESTIGATION),
    "Lipase": ("Lipase", AbbreviationCategory.INVESTIGATION),
    "B12": ("Vitamin B12", AbbreviationCategory.INVESTIGATION),
    "Folate": ("Folate", AbbreviationCategory.INVESTIGATION),
    "Ferritin": ("Ferritin", AbbreviationCategory.INVESTIGATION),
    "TIBC": ("Total Iron Binding Capacity", AbbreviationCategory.INVESTIGATION),
    "Iron": ("Iron", AbbreviationCategory.INVESTIGATION),
    "Lactate": ("Lactate", AbbreviationCategory.INVESTIGATION),
    "Ammonia": ("Ammonia", AbbreviationCategory.INVESTIGATION),

    # Imaging & Procedures
    "CXR": ("Chest X-Ray", AbbreviationCategory.INVESTIGATION),
    "AXR": ("Abdominal X-Ray", AbbreviationCategory.INVESTIGATION),
    "KUB": ("Kidneys Ureters Bladder X-Ray", AbbreviationCategory.INVESTIGATION),
    "CT": ("Computed Tomography", AbbreviationCategory.INVESTIGATION),
    "CTPA": ("CT Pulmonary Angiogram", AbbreviationCategory.INVESTIGATION),
    "CTA": ("CT Angiography", AbbreviationCategory.INVESTIGATION),
    "CTKUB": ("CT Kidneys Ureters Bladder", AbbreviationCategory.INVESTIGATION),
    "HRCT": ("High Resolution CT", AbbreviationCategory.INVESTIGATION),
    "MRI": ("Magnetic Resonance Imaging", AbbreviationCategory.INVESTIGATION),
    "MRA": ("Magnetic Resonance Angiography", AbbreviationCategory.INVESTIGATION),
    "MRCP": ("Magnetic Resonance Cholangiopancreatography", AbbreviationCategory.INVESTIGATION),
    "USS": ("Ultrasound Scan", AbbreviationCategory.INVESTIGATION),
    "US": ("Ultrasound", AbbreviationCategory.INVESTIGATION),
    "FAST": ("Focused Assessment with Sonography in Trauma", AbbreviationCategory.INVESTIGATION),
    "eFAST": ("Extended FAST", AbbreviationCategory.INVESTIGATION),
    "Echo": ("Echocardiogram", AbbreviationCategory.INVESTIGATION),
    "TTE": ("Transthoracic Echocardiogram", AbbreviationCategory.INVESTIGATION),
    "TOE": ("Transoesophageal Echocardiogram", AbbreviationCategory.INVESTIGATION),
    "TEE": ("Transesophageal Echocardiogram", AbbreviationCategory.INVESTIGATION),
    "ECG": ("Electrocardiogram", AbbreviationCategory.INVESTIGATION),
    "EKG": ("Electrocardiogram", AbbreviationCategory.INVESTIGATION),
    "EEG": ("Electroencephalogram", AbbreviationCategory.INVESTIGATION),
    "EMG": ("Electromyography", AbbreviationCategory.INVESTIGATION),
    "NCS": ("Nerve Conduction Studies", AbbreviationCategory.INVESTIGATION),
    "PFT": ("Pulmonary Function Tests", AbbreviationCategory.INVESTIGATION),
    "PFTs": ("Pulmonary Function Tests", AbbreviationCategory.INVESTIGATION),
    "Spirometry": ("Spirometry", AbbreviationCategory.INVESTIGATION),
    "FeNO": ("Fractional Exhaled Nitric Oxide", AbbreviationCategory.INVESTIGATION),
    "DEXA": ("Dual-Energy X-ray Absorptiometry", AbbreviationCategory.INVESTIGATION),
    "DXA": ("Dual-Energy X-ray Absorptiometry", AbbreviationCategory.INVESTIGATION),
    "V/Q": ("Ventilation/Perfusion Scan", AbbreviationCategory.INVESTIGATION),
    "VQ": ("Ventilation/Perfusion Scan", AbbreviationCategory.INVESTIGATION),
    "PET": ("Positron Emission Tomography", AbbreviationCategory.INVESTIGATION),
    "SPECT": ("Single Photon Emission Computed Tomography", AbbreviationCategory.INVESTIGATION),
    "MSU": ("Mid-Stream Urine", AbbreviationCategory.INVESTIGATION),
    "MSSU": ("Mid-Stream Specimen of Urine", AbbreviationCategory.INVESTIGATION),
    "CSU": ("Catheter Specimen of Urine", AbbreviationCategory.INVESTIGATION),
    "CSF": ("Cerebrospinal Fluid", AbbreviationCategory.INVESTIGATION),
    "LP": ("Lumbar Puncture", AbbreviationCategory.INVESTIGATION),
    "FNA": ("Fine Needle Aspiration", AbbreviationCategory.INVESTIGATION),
    "Bx": ("Biopsy", AbbreviationCategory.INVESTIGATION),
    "Histo": ("Histology", AbbreviationCategory.INVESTIGATION),

    # ══════════════════════════════════════════════════════════════════════════
    # PROCEDURES & INTERVENTIONS
    # ══════════════════════════════════════════════════════════════════════════
    "OGD": ("Oesophagogastroduodenoscopy", AbbreviationCategory.PROCEDURE),
    "EGD": ("Esophagogastroduodenoscopy", AbbreviationCategory.PROCEDURE),
    "ERCP": ("Endoscopic Retrograde Cholangiopancreatography", AbbreviationCategory.PROCEDURE),
    "EUS": ("Endoscopic Ultrasound", AbbreviationCategory.PROCEDURE),
    "PEG": ("Percutaneous Endoscopic Gastrostomy", AbbreviationCategory.PROCEDURE),
    "RIG": ("Radiologically Inserted Gastrostomy", AbbreviationCategory.PROCEDURE),
    "PICC": ("Peripherally Inserted Central Catheter", AbbreviationCategory.PROCEDURE),
    "CVC": ("Central Venous Catheter", AbbreviationCategory.PROCEDURE),
    "IJC": ("Internal Jugular Catheter", AbbreviationCategory.PROCEDURE),
    "SC": ("Subclavian Catheter", AbbreviationCategory.PROCEDURE),
    "Art line": ("Arterial Line", AbbreviationCategory.PROCEDURE),
    "A-line": ("Arterial Line", AbbreviationCategory.PROCEDURE),
    "PCI": ("Percutaneous Coronary Intervention", AbbreviationCategory.PROCEDURE),
    "CABG": ("Coronary Artery Bypass Graft", AbbreviationCategory.PROCEDURE),
    "AVR": ("Aortic Valve Replacement", AbbreviationCategory.PROCEDURE),
    "MVR": ("Mitral Valve Replacement", AbbreviationCategory.PROCEDURE),
    "TAVI": ("Transcatheter Aortic Valve Implantation", AbbreviationCategory.PROCEDURE),
    "TAVR": ("Transcatheter Aortic Valve Replacement", AbbreviationCategory.PROCEDURE),
    "ICD": ("Implantable Cardioverter Defibrillator", AbbreviationCategory.PROCEDURE),
    "PPM": ("Permanent Pacemaker", AbbreviationCategory.PROCEDURE),
    "CRT": ("Cardiac Resynchronisation Therapy", AbbreviationCategory.PROCEDURE),
    "CRT-D": ("Cardiac Resynchronisation Therapy Defibrillator", AbbreviationCategory.PROCEDURE),
    "CRT-P": ("Cardiac Resynchronisation Therapy Pacemaker", AbbreviationCategory.PROCEDURE),
    "DCCV": ("Direct Current Cardioversion", AbbreviationCategory.PROCEDURE),
    "DC cardioversion": ("Direct Current Cardioversion", AbbreviationCategory.PROCEDURE),
    "RFA": ("Radiofrequency Ablation", AbbreviationCategory.PROCEDURE),
    "CPR": ("Cardiopulmonary Resuscitation", AbbreviationCategory.PROCEDURE),
    "ROSC": ("Return of Spontaneous Circulation", AbbreviationCategory.PROCEDURE),
    "NIV": ("Non-Invasive Ventilation", AbbreviationCategory.PROCEDURE),
    "CPAP": ("Continuous Positive Airway Pressure", AbbreviationCategory.PROCEDURE),
    "BiPAP": ("Bilevel Positive Airway Pressure", AbbreviationCategory.PROCEDURE),
    "HFNC": ("High Flow Nasal Cannula", AbbreviationCategory.PROCEDURE),
    "HFNO": ("High Flow Nasal Oxygen", AbbreviationCategory.PROCEDURE),
    "IMV": ("Invasive Mechanical Ventilation", AbbreviationCategory.PROCEDURE),
    "ETT": ("Endotracheal Tube", AbbreviationCategory.PROCEDURE),
    "LMA": ("Laryngeal Mask Airway", AbbreviationCategory.PROCEDURE),
    "Trache": ("Tracheostomy", AbbreviationCategory.PROCEDURE),
    "NG": ("Nasogastric", AbbreviationCategory.PROCEDURE),
    "NGT": ("Nasogastric Tube", AbbreviationCategory.PROCEDURE),
    "NJ": ("Nasojejunal", AbbreviationCategory.PROCEDURE),
    "NJT": ("Nasojejunal Tube", AbbreviationCategory.PROCEDURE),
    "TPN": ("Total Parenteral Nutrition", AbbreviationCategory.PROCEDURE),
    "HD": ("Haemodialysis", AbbreviationCategory.PROCEDURE),
    "CRRT": ("Continuous Renal Replacement Therapy", AbbreviationCategory.PROCEDURE),
    "CVVH": ("Continuous Venovenous Haemofiltration", AbbreviationCategory.PROCEDURE),
    "CVVHD": ("Continuous Venovenous Haemodialysis", AbbreviationCategory.PROCEDURE),
    "CVVHDF": ("Continuous Venovenous Haemodiafiltration", AbbreviationCategory.PROCEDURE),
    "PD": ("Peritoneal Dialysis", AbbreviationCategory.PROCEDURE),
    "TURP": ("Transurethral Resection of Prostate", AbbreviationCategory.PROCEDURE),
    "TURBT": ("Transurethral Resection of Bladder Tumour", AbbreviationCategory.PROCEDURE),
    "PCNL": ("Percutaneous Nephrolithotomy", AbbreviationCategory.PROCEDURE),
    "URS": ("Ureteroscopy", AbbreviationCategory.PROCEDURE),
    "ESWL": ("Extracorporeal Shock Wave Lithotripsy", AbbreviationCategory.PROCEDURE),
    "THR": ("Total Hip Replacement", AbbreviationCategory.PROCEDURE),
    "TKR": ("Total Knee Replacement", AbbreviationCategory.PROCEDURE),
    "TSR": ("Total Shoulder Replacement", AbbreviationCategory.PROCEDURE),
    "ORIF": ("Open Reduction Internal Fixation", AbbreviationCategory.PROCEDURE),
    "IM nail": ("Intramedullary Nail", AbbreviationCategory.PROCEDURE),
    "DHS": ("Dynamic Hip Screw", AbbreviationCategory.PROCEDURE),
    "EUA": ("Examination Under Anaesthesia", AbbreviationCategory.PROCEDURE),
    "D&C": ("Dilation and Curettage", AbbreviationCategory.PROCEDURE),
    "LLETZ": ("Large Loop Excision of Transformation Zone", AbbreviationCategory.PROCEDURE),
    "LSCS": ("Lower Segment Caesarean Section", AbbreviationCategory.PROCEDURE),
    "C-section": ("Caesarean Section", AbbreviationCategory.PROCEDURE),
    "CS": ("Caesarean Section", AbbreviationCategory.PROCEDURE),
    "SVD": ("Spontaneous Vaginal Delivery", AbbreviationCategory.PROCEDURE),
    "NVD": ("Normal Vaginal Delivery", AbbreviationCategory.PROCEDURE),

    # ══════════════════════════════════════════════════════════════════════════
    # HISTORY TYPES
    # ══════════════════════════════════════════════════════════════════════════
    "PMH": ("Past Medical History", AbbreviationCategory.HISTORY),
    "PMHx": ("Past Medical History", AbbreviationCategory.HISTORY),
    "PSH": ("Past Surgical History", AbbreviationCategory.HISTORY),
    "PSHx": ("Past Surgical History", AbbreviationCategory.HISTORY),
    "FH": ("Family History", AbbreviationCategory.HISTORY),
    "FHx": ("Family History", AbbreviationCategory.HISTORY),
    "SH": ("Social History", AbbreviationCategory.HISTORY),
    "SHx": ("Social History", AbbreviationCategory.HISTORY),
    "DHx": ("Drug History", AbbreviationCategory.HISTORY),
    "DH": ("Drug History", AbbreviationCategory.HISTORY),
    "HPC": ("History of Presenting Complaint", AbbreviationCategory.HISTORY),
    "HPI": ("History of Present Illness", AbbreviationCategory.HISTORY),
    "PC": ("Presenting Complaint", AbbreviationCategory.HISTORY),
    "CC": ("Chief Complaint", AbbreviationCategory.HISTORY),
    "ROS": ("Review of Systems", AbbreviationCategory.HISTORY),
    "Hx": ("History", AbbreviationCategory.HISTORY),
    "H/O": ("History of", AbbreviationCategory.HISTORY),
    "C/O": ("Complaining of", AbbreviationCategory.HISTORY),
    "S/P": ("Status Post", AbbreviationCategory.HISTORY),
    "POD": ("Post-Operative Day", AbbreviationCategory.HISTORY),

    # ══════════════════════════════════════════════════════════════════════════
    # ALLERGY & MEDICATION STATUS
    # ══════════════════════════════════════════════════════════════════════════
    "NKDA": ("No Known Drug Allergies", AbbreviationCategory.MEDICATION),
    "NKA": ("No Known Allergies", AbbreviationCategory.MEDICATION),
    "NKFA": ("No Known Food Allergies", AbbreviationCategory.MEDICATION),

    # ══════════════════════════════════════════════════════════════════════════
    # MEDICATION ROUTES & TIMING
    # ══════════════════════════════════════════════════════════════════════════
    "PO": ("Per Os (By Mouth)", AbbreviationCategory.MEDICATION),
    "PR": ("Per Rectum", AbbreviationCategory.MEDICATION),
    "PV": ("Per Vagina", AbbreviationCategory.MEDICATION),
    "IM": ("Intramuscular", AbbreviationCategory.MEDICATION),
    "IV": ("Intravenous", AbbreviationCategory.MEDICATION),
    "SC": ("Subcutaneous", AbbreviationCategory.MEDICATION),
    "SL": ("Sublingual", AbbreviationCategory.MEDICATION),
    "TOP": ("Topical", AbbreviationCategory.MEDICATION),
    "INH": ("Inhaled", AbbreviationCategory.MEDICATION),
    "NEB": ("Nebulised", AbbreviationCategory.MEDICATION),
    "IT": ("Intrathecal", AbbreviationCategory.MEDICATION),
    "IO": ("Intraosseous", AbbreviationCategory.MEDICATION),
    "OD": ("Once Daily", AbbreviationCategory.TIMING),
    "BD": ("Twice Daily", AbbreviationCategory.TIMING),
    "TDS": ("Three Times Daily", AbbreviationCategory.TIMING),
    "QDS": ("Four Times Daily", AbbreviationCategory.TIMING),
    "QID": ("Four Times Daily", AbbreviationCategory.TIMING),
    "PRN": ("Pro Re Nata (As Required)", AbbreviationCategory.TIMING),
    "STAT": ("Immediately", AbbreviationCategory.TIMING),
    "Mane": ("In the Morning", AbbreviationCategory.TIMING),
    "Nocte": ("At Night", AbbreviationCategory.TIMING),
    "OM": ("Every Morning", AbbreviationCategory.TIMING),
    "ON": ("Every Night", AbbreviationCategory.TIMING),
    "AC": ("Before Meals", AbbreviationCategory.TIMING),
    "PC": ("After Meals", AbbreviationCategory.TIMING),
    "Q4H": ("Every 4 Hours", AbbreviationCategory.TIMING),
    "Q6H": ("Every 6 Hours", AbbreviationCategory.TIMING),
    "Q8H": ("Every 8 Hours", AbbreviationCategory.TIMING),
    "Q12H": ("Every 12 Hours", AbbreviationCategory.TIMING),

    # ══════════════════════════════════════════════════════════════════════════
    # ADMINISTRATION & STATUS
    # ══════════════════════════════════════════════════════════════════════════
    "TTO": ("To Take Out (Discharge Medications)", AbbreviationCategory.ADMINISTRATION),
    "TTA": ("To Take Away (Discharge Medications)", AbbreviationCategory.ADMINISTRATION),
    "TTH": ("To Take Home", AbbreviationCategory.ADMINISTRATION),
    "Rx": ("Prescription/Treatment", AbbreviationCategory.ADMINISTRATION),
    "Tx": ("Treatment/Transplant", AbbreviationCategory.ADMINISTRATION),
    "Dx": ("Diagnosis", AbbreviationCategory.ADMINISTRATION),
    "DDx": ("Differential Diagnosis", AbbreviationCategory.ADMINISTRATION),
    "Ix": ("Investigations", AbbreviationCategory.ADMINISTRATION),
    "Mx": ("Management", AbbreviationCategory.ADMINISTRATION),
    "Px": ("Prognosis", AbbreviationCategory.ADMINISTRATION),
    "Hx": ("History", AbbreviationCategory.ADMINISTRATION),
    "Sx": ("Symptoms/Surgery", AbbreviationCategory.ADMINISTRATION),
    "Fx": ("Fracture", AbbreviationCategory.ADMINISTRATION),
    "F/U": ("Follow-Up", AbbreviationCategory.ADMINISTRATION),
    "R/V": ("Review", AbbreviationCategory.ADMINISTRATION),
    "DNA": ("Did Not Attend", AbbreviationCategory.ADMINISTRATION),
    "WAS": ("Was Not Brought (children)", AbbreviationCategory.ADMINISTRATION),
    "CNA": ("Could Not Attend", AbbreviationCategory.ADMINISTRATION),
    "NBM": ("Nil By Mouth", AbbreviationCategory.ADMINISTRATION),
    "NPO": ("Nil Per Os (Nothing By Mouth)", AbbreviationCategory.ADMINISTRATION),
    "DNACPR": ("Do Not Attempt Cardiopulmonary Resuscitation", AbbreviationCategory.ADMINISTRATION),
    "DNAR": ("Do Not Attempt Resuscitation", AbbreviationCategory.ADMINISTRATION),
    "AND": ("Allow Natural Death", AbbreviationCategory.ADMINISTRATION),
    "ReSPECT": ("Recommended Summary Plan for Emergency Care and Treatment", AbbreviationCategory.ADMINISTRATION),
    "MCA": ("Mental Capacity Act", AbbreviationCategory.ADMINISTRATION),
    "DoLS": ("Deprivation of Liberty Safeguards", AbbreviationCategory.ADMINISTRATION),
    "LPA": ("Lasting Power of Attorney", AbbreviationCategory.ADMINISTRATION),
    "IMCA": ("Independent Mental Capacity Advocate", AbbreviationCategory.ADMINISTRATION),
    "SDM": ("Substitute Decision Maker", AbbreviationCategory.ADMINISTRATION),

    # ══════════════════════════════════════════════════════════════════════════
    # ORGANISATIONS & DEPARTMENTS
    # ══════════════════════════════════════════════════════════════════════════
    "NHS": ("National Health Service", AbbreviationCategory.ORGANISATION),
    "GP": ("General Practitioner", AbbreviationCategory.ORGANISATION),
    "A&E": ("Accident and Emergency", AbbreviationCategory.ORGANISATION),
    "ED": ("Emergency Department", AbbreviationCategory.ORGANISATION),
    "ICU": ("Intensive Care Unit", AbbreviationCategory.ORGANISATION),
    "ITU": ("Intensive Therapy Unit", AbbreviationCategory.ORGANISATION),
    "HDU": ("High Dependency Unit", AbbreviationCategory.ORGANISATION),
    "CCU": ("Coronary Care Unit", AbbreviationCategory.ORGANISATION),
    "NICU": ("Neonatal Intensive Care Unit", AbbreviationCategory.ORGANISATION),
    "PICU": ("Paediatric Intensive Care Unit", AbbreviationCategory.ORGANISATION),
    "SCBU": ("Special Care Baby Unit", AbbreviationCategory.ORGANISATION),
    "MAU": ("Medical Assessment Unit", AbbreviationCategory.ORGANISATION),
    "AMU": ("Acute Medical Unit", AbbreviationCategory.ORGANISATION),
    "SAU": ("Surgical Assessment Unit", AbbreviationCategory.ORGANISATION),
    "SDEC": ("Same Day Emergency Care", AbbreviationCategory.ORGANISATION),
    "OPD": ("Outpatient Department", AbbreviationCategory.ORGANISATION),
    "IPD": ("Inpatient Department", AbbreviationCategory.ORGANISATION),
    "AAU": ("Acute Assessment Unit", AbbreviationCategory.ORGANISATION),
    "CDU": ("Clinical Decision Unit", AbbreviationCategory.ORGANISATION),
    "EAU": ("Emergency Assessment Unit", AbbreviationCategory.ORGANISATION),
    "CEPOD": ("Confidential Enquiry into Perioperative Deaths", AbbreviationCategory.ORGANISATION),
    "MDT": ("Multidisciplinary Team", AbbreviationCategory.ORGANISATION),
    "MDM": ("Multidisciplinary Meeting", AbbreviationCategory.ORGANISATION),
    "NICE": ("National Institute for Health and Care Excellence", AbbreviationCategory.ORGANISATION),
    "BNF": ("British National Formulary", AbbreviationCategory.ORGANISATION),
    "GMC": ("General Medical Council", AbbreviationCategory.ORGANISATION),
    "NMC": ("Nursing and Midwifery Council", AbbreviationCategory.ORGANISATION),
    "CQC": ("Care Quality Commission", AbbreviationCategory.ORGANISATION),
    "CCG": ("Clinical Commissioning Group", AbbreviationCategory.ORGANISATION),
    "ICS": ("Integrated Care System", AbbreviationCategory.ORGANISATION),
    "ICB": ("Integrated Care Board", AbbreviationCategory.ORGANISATION),
    "PCN": ("Primary Care Network", AbbreviationCategory.ORGANISATION),
    "111": ("NHS 111 Service", AbbreviationCategory.ORGANISATION),
    "999": ("Emergency Services", AbbreviationCategory.ORGANISATION),

    # ══════════════════════════════════════════════════════════════════════════
    # GENERAL/MISCELLANEOUS
    # ══════════════════════════════════════════════════════════════════════════
    "Pt": ("Patient", AbbreviationCategory.GENERAL),
    "pt": ("Patient", AbbreviationCategory.GENERAL),
    "M": ("Male", AbbreviationCategory.GENERAL),
    "F": ("Female", AbbreviationCategory.GENERAL),
    "yo": ("Year Old", AbbreviationCategory.GENERAL),
    "y/o": ("Year Old", AbbreviationCategory.GENERAL),
    "YO": ("Year Old", AbbreviationCategory.GENERAL),
    "mo": ("Month Old", AbbreviationCategory.GENERAL),
    "wk": ("Week", AbbreviationCategory.GENERAL),
    "d": ("Day", AbbreviationCategory.GENERAL),
    "hr": ("Hour", AbbreviationCategory.GENERAL),
    "min": ("Minute", AbbreviationCategory.GENERAL),
    "sec": ("Second", AbbreviationCategory.GENERAL),
    "R": ("Right", AbbreviationCategory.GENERAL),
    "L": ("Left", AbbreviationCategory.GENERAL),
    "B/L": ("Bilateral", AbbreviationCategory.GENERAL),
    "bilat": ("Bilateral", AbbreviationCategory.GENERAL),
    "Ant": ("Anterior", AbbreviationCategory.GENERAL),
    "Post": ("Posterior", AbbreviationCategory.GENERAL),
    "Lat": ("Lateral", AbbreviationCategory.GENERAL),
    "Med": ("Medial", AbbreviationCategory.GENERAL),
    "Sup": ("Superior", AbbreviationCategory.GENERAL),
    "Inf": ("Inferior", AbbreviationCategory.GENERAL),
    "Prox": ("Proximal", AbbreviationCategory.GENERAL),
    "Dist": ("Distal", AbbreviationCategory.GENERAL),
    "+ve": ("Positive", AbbreviationCategory.GENERAL),
    "-ve": ("Negative", AbbreviationCategory.GENERAL),
    "c/w": ("Consistent With", AbbreviationCategory.GENERAL),
    "s/b": ("Seen By", AbbreviationCategory.GENERAL),
    "w/": ("With", AbbreviationCategory.GENERAL),
    "w/o": ("Without", AbbreviationCategory.GENERAL),
    "b/w": ("Between", AbbreviationCategory.GENERAL),
    "approx": ("Approximately", AbbreviationCategory.GENERAL),
    "~": ("Approximately", AbbreviationCategory.GENERAL),
    "++": ("Significant/Marked", AbbreviationCategory.GENERAL),
    "+++": ("Severe/Very Marked", AbbreviationCategory.GENERAL),
    "N/A": ("Not Applicable", AbbreviationCategory.GENERAL),
    "n/a": ("Not Applicable", AbbreviationCategory.GENERAL),
    "TBC": ("To Be Confirmed", AbbreviationCategory.GENERAL),
    "TBD": ("To Be Determined", AbbreviationCategory.GENERAL),
    "NB": ("Note Well (Nota Bene)", AbbreviationCategory.GENERAL),
    "i.e.": ("That Is", AbbreviationCategory.GENERAL),
    "e.g.": ("For Example", AbbreviationCategory.GENERAL),
    "cf.": ("Compare", AbbreviationCategory.GENERAL),
    "etc.": ("And So On", AbbreviationCategory.GENERAL),
    "vs": ("Versus", AbbreviationCategory.GENERAL),
    "re": ("Regarding", AbbreviationCategory.GENERAL),
    "Re": ("Regarding", AbbreviationCategory.GENERAL),
}

# Context-dependent abbreviations (multiple meanings based on context)
CONTEXT_DEPENDENT: Dict[str, List[Tuple[str, str, AbbreviationCategory]]] = {
    "MS": [
        ("Multiple Sclerosis", "neuro", AbbreviationCategory.DIAGNOSIS),
        ("Mitral Stenosis", "cardio", AbbreviationCategory.DIAGNOSIS),
        ("Mental Status", "psych", AbbreviationCategory.EXAMINATION),
        ("Morphine Sulphate", "medication", AbbreviationCategory.MEDICATION),
    ],
    "PD": [
        ("Parkinson's Disease", "neuro", AbbreviationCategory.DIAGNOSIS),
        ("Peritoneal Dialysis", "renal", AbbreviationCategory.PROCEDURE),
        ("Personality Disorder", "psych", AbbreviationCategory.DIAGNOSIS),
    ],
    "CHF": [
        ("Congestive Heart Failure", "cardio", AbbreviationCategory.DIAGNOSIS),
        ("Chronic Heart Failure", "cardio", AbbreviationCategory.DIAGNOSIS),
    ],
    "PE": [
        ("Pulmonary Embolism", "resp", AbbreviationCategory.DIAGNOSIS),
        ("Physical Examination", "exam", AbbreviationCategory.EXAMINATION),
        ("Pleural Effusion", "resp", AbbreviationCategory.DIAGNOSIS),
    ],
    "AF": [
        ("Atrial Fibrillation", "cardio", AbbreviationCategory.DIAGNOSIS),
        ("Afebrile", "vital", AbbreviationCategory.VITAL_SIGN),
    ],
    "AV": [
        ("Atrioventricular", "cardio", AbbreviationCategory.ANATOMY),
        ("Arteriovenous", "vascular", AbbreviationCategory.ANATOMY),
    ],
    "LA": [
        ("Left Atrium", "cardio", AbbreviationCategory.ANATOMY),
        ("Local Anaesthetic", "medication", AbbreviationCategory.MEDICATION),
    ],
    "RA": [
        ("Right Atrium", "cardio", AbbreviationCategory.ANATOMY),
        ("Rheumatoid Arthritis", "rheum", AbbreviationCategory.DIAGNOSIS),
        ("Room Air", "resp", AbbreviationCategory.VITAL_SIGN),
    ],
    "RR": [
        ("Respiratory Rate", "vital", AbbreviationCategory.VITAL_SIGN),
        ("Relative Risk", "stats", AbbreviationCategory.GENERAL),
    ],
    "CA": [
        ("Cancer/Carcinoma", "onc", AbbreviationCategory.DIAGNOSIS),
        ("Calcium", "lab", AbbreviationCategory.INVESTIGATION),
        ("Cardiac Arrest", "emergency", AbbreviationCategory.DIAGNOSIS),
    ],
    "PT": [
        ("Prothrombin Time", "lab", AbbreviationCategory.INVESTIGATION),
        ("Patient", "general", AbbreviationCategory.GENERAL),
        ("Physiotherapy", "therapy", AbbreviationCategory.PROCEDURE),
        ("Physical Therapy", "therapy", AbbreviationCategory.PROCEDURE),
    ],
    "OT": [
        ("Occupational Therapy", "therapy", AbbreviationCategory.PROCEDURE),
        ("Operating Theatre", "location", AbbreviationCategory.ORGANISATION),
    ],
    "HR": [
        ("Heart Rate", "vital", AbbreviationCategory.VITAL_SIGN),
        ("Human Resources", "admin", AbbreviationCategory.ORGANISATION),
    ],
}


class ClinicalAbbreviationResolver:
    """
    Resolves NHS/UK clinical abbreviations to their full forms.

    Preserves original abbreviation while adding expansion.
    Handles context-dependent abbreviations.
    """

    def __init__(
        self,
        custom_abbreviations: Optional[Dict[str, Tuple[str, AbbreviationCategory]]] = None,
        expand_in_text: bool = True,
    ):
        """
        Initialize the resolver.

        Args:
            custom_abbreviations: Additional abbreviations to include
            expand_in_text: Whether to expand abbreviations in output text
        """
        self.abbreviations = {**CLINICAL_ABBREVIATIONS}
        if custom_abbreviations:
            self.abbreviations.update(custom_abbreviations)

        self.expand_in_text = expand_in_text
        self._build_regex()

    def _build_regex(self) -> None:
        """Build compiled regex for efficient matching."""
        # Sort by length (longest first) to prevent partial matches
        sorted_abbrevs = sorted(self.abbreviations.keys(), key=len, reverse=True)

        # Build pattern with word boundaries
        # Handle special characters in abbreviations
        escaped = []
        for abbrev in sorted_abbrevs:
            esc = re.escape(abbrev)
            escaped.append(esc)

        pattern = r'\b(' + '|'.join(escaped) + r')\b'
        self.abbrev_regex = re.compile(pattern)

    def resolve(self, text: str) -> ResolutionResult:
        """
        Resolve all abbreviations in text.

        Args:
            text: Clinical document text

        Returns:
            ResolutionResult with original and expanded text
        """
        resolved: List[ResolvedAbbreviation] = []
        stats: Dict[str, int] = {cat.value: 0 for cat in AbbreviationCategory}
        stats["total"] = 0

        # Track positions to avoid duplicates
        seen_positions: Set[Tuple[int, int]] = set()

        # Find all matches
        for match in self.abbrev_regex.finditer(text):
            abbrev = match.group(1)
            start = match.start()
            end = match.end()

            # Skip if we've already processed this position
            if (start, end) in seen_positions:
                continue
            seen_positions.add((start, end))

            # Look up expansion
            if abbrev in self.abbreviations:
                expansion, category = self.abbreviations[abbrev]

                resolved.append(ResolvedAbbreviation(
                    abbreviation=abbrev,
                    expansion=expansion,
                    category=category,
                    start_pos=start,
                    end_pos=end,
                    confidence=1.0,
                ))

                stats[category.value] = stats.get(category.value, 0) + 1
                stats["total"] += 1

        # Sort by position (for consistent ordering)
        resolved.sort(key=lambda x: x.start_pos)

        # Build expanded text
        expanded_text = self._expand_text(text, resolved) if self.expand_in_text else text

        return ResolutionResult(
            original_text=text,
            expanded_text=expanded_text,
            resolved_abbreviations=resolved,
            stats=stats,
        )

    def _expand_text(
        self, text: str, resolved: List[ResolvedAbbreviation]
    ) -> str:
        """
        Build expanded text with abbreviations replaced.

        Format: "expansion (ABBREV)" to preserve both forms.
        """
        if not resolved:
            return text

        # Process in reverse order to maintain position accuracy
        result = text
        for abbrev in reversed(resolved):
            before = result[:abbrev.start_pos]
            after = result[abbrev.end_pos:]
            # Format: "Full Form (ABBREV)"
            replacement = f"{abbrev.expansion} ({abbrev.abbreviation})"
            result = before + replacement + after

        return result

    def resolve_with_context(
        self, text: str, context_hints: Optional[Dict[str, str]] = None
    ) -> ResolutionResult:
        """
        Resolve abbreviations with context-aware disambiguation.

        Args:
            text: Clinical document text
            context_hints: Optional hints like {"MS": "neuro"} to disambiguate

        Returns:
            ResolutionResult with context-aware expansions
        """
        # First do standard resolution
        result = self.resolve(text)

        # Then handle context-dependent abbreviations
        if context_hints:
            for abbrev in result.resolved_abbreviations:
                if abbrev.abbreviation in CONTEXT_DEPENDENT:
                    hint = context_hints.get(abbrev.abbreviation)
                    if hint:
                        for expansion, ctx, category in CONTEXT_DEPENDENT[abbrev.abbreviation]:
                            if ctx == hint:
                                abbrev.expansion = expansion
                                abbrev.category = category
                                abbrev.context_hint = hint
                                break

        return result

    def get_expansion(self, abbreviation: str) -> Optional[str]:
        """Get the expansion for a single abbreviation."""
        if abbreviation in self.abbreviations:
            return self.abbreviations[abbreviation][0]
        return None

    def get_category(self, abbreviation: str) -> Optional[AbbreviationCategory]:
        """Get the category for a single abbreviation."""
        if abbreviation in self.abbreviations:
            return self.abbreviations[abbreviation][1]
        return None

    def list_by_category(
        self, category: AbbreviationCategory
    ) -> List[Tuple[str, str]]:
        """List all abbreviations in a category."""
        return [
            (abbrev, expansion)
            for abbrev, (expansion, cat) in self.abbreviations.items()
            if cat == category
        ]


def resolve_clinical_abbreviations(text: str) -> Dict[str, Any]:
    """
    Convenience function to resolve abbreviations.

    Args:
        text: Clinical document text

    Returns:
        Dictionary with original text, expanded text, and abbreviations list
    """
    resolver = ClinicalAbbreviationResolver()
    result = resolver.resolve(text)
    return result.to_dict()


# Test
if __name__ == "__main__":
    test_text = """
    72 yo M with PMH of HTN, T2DM, AF, prev TIA presents with LOC and SOB.

    O/E: BP 145/92, HR 88, RR 18, SpO2 96% on RA, Temp 37.1
    CVS: HS I+II, no murmurs, JVP not raised
    Resp: AEBS, no crackles
    Abdo: SNT, BS+
    Neuro: GCS 15, CN II-XII intact, UL/LL power 5/5

    Allergies: NKDA

    Ix:
    - FBC, U&E, LFT, TFT
    - CRP, Trop, ABG
    - CXR, ECG
    - CT head

    Dx: ?TIA vs syncope

    Plan:
    - NBM pending investigation
    - IV fluids
    - Aspirin 300mg STAT
    - Referral to stroke team
    - F/U with GP in 2 weeks
    """

    resolver = ClinicalAbbreviationResolver()
    result = resolver.resolve(test_text)

    print("=" * 70)
    print("CLINICAL ABBREVIATION RESOLUTION")
    print("=" * 70)

    print("\n=== RESOLVED ABBREVIATIONS ===")
    for abbrev in result.resolved_abbreviations:
        print(f"  {abbrev.abbreviation:<12} -> {abbrev.expansion:<45} [{abbrev.category.value}]")

    print(f"\n=== STATS ===")
    for cat, count in sorted(result.stats.items()):
        if count > 0:
            print(f"  {cat:<20}: {count}")

    print("\n" + "=" * 70)
    print("EXPANDED TEXT (excerpt)")
    print("=" * 70)
    print(result.expanded_text[:1500] + "...")
