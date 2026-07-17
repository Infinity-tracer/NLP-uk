"""
Investigation Parser

Separates investigation names from findings/results.

Example:
    Input:  "FBC - unremarkable"
    Output: Investigation: Full Blood Count
            Finding: Unremarkable

Excludes measurements (Height, Weight, BSA, BMI) from investigations.
"""

import re
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional, Tuple
from enum import Enum


class InvestigationCategory(Enum):
    """Category of investigation"""
    BLOOD_TEST = "blood_test"
    IMAGING = "imaging"
    CARDIOLOGY = "cardiology"
    MICROBIOLOGY = "microbiology"
    HISTOLOGY = "histology"
    ENDOSCOPY = "endoscopy"
    PULMONARY = "pulmonary"
    URINE = "urine"
    OTHER = "other"


class FindingStatus(Enum):
    """Status/interpretation of finding"""
    NORMAL = "normal"
    ABNORMAL = "abnormal"
    PENDING = "pending"
    NOT_DONE = "not_done"
    UNKNOWN = "unknown"


@dataclass
class ParsedInvestigation:
    """Parsed investigation with separated name and finding"""
    investigation: str              # Investigation name (expanded)
    investigation_abbrev: Optional[str]  # Original abbreviation if used
    finding: Optional[str]          # The result/finding
    finding_status: str             # normal/abnormal/pending/unknown
    category: str                   # blood_test/imaging/cardiology/etc.
    raw_text: str                   # Original text
    confidence: float               # Extraction confidence

    def to_dict(self) -> Dict:
        return asdict(self)


# Investigations that should be EXCLUDED (measurements, not investigations)
EXCLUDED_TERMS = {
    # Vital signs / measurements
    "height", "weight", "bsa", "bmi", "body mass index", "body surface area",
    "temperature", "temp", "pulse", "heart rate", "hr", "bp", "blood pressure",
    "respiratory rate", "rr", "oxygen saturation", "spo2", "sats", "o2 sats",
    "pain score", "gcs", "glasgow coma scale", "avpu",
    # Demographics
    "age", "dob", "date of birth", "sex", "gender",
}

# Section headers to skip
SECTION_HEADERS = {
    "investigations", "investigation", "results", "result", "findings", "tests",
    "bloods", "imaging", "radiology", "observations", "vitals", "vital signs",
}

# Investigation name expansions (abbreviation -> full name)
INVESTIGATION_EXPANSIONS = {
    # Blood tests - Haematology
    "fbc": "Full Blood Count",
    "full blood count": "Full Blood Count",
    "cbc": "Complete Blood Count",
    "hb": "Haemoglobin",
    "haemoglobin": "Haemoglobin",
    "hemoglobin": "Haemoglobin",
    "wcc": "White Cell Count",
    "wbc": "White Blood Cell Count",
    "plt": "Platelet Count",
    "platelets": "Platelet Count",
    "mcv": "Mean Corpuscular Volume",
    "mch": "Mean Corpuscular Haemoglobin",
    "mchc": "Mean Corpuscular Haemoglobin Concentration",
    "rdw": "Red Cell Distribution Width",
    "retic": "Reticulocyte Count",
    "reticulocytes": "Reticulocyte Count",
    "esr": "Erythrocyte Sedimentation Rate",
    "blood film": "Blood Film",
    "film": "Blood Film",
    "coag": "Coagulation Screen",
    "coagulation": "Coagulation Screen",
    "clotting": "Clotting Screen",
    "pt": "Prothrombin Time",
    "inr": "International Normalised Ratio",
    "aptt": "Activated Partial Thromboplastin Time",
    "fibrinogen": "Fibrinogen",
    "d-dimer": "D-Dimer",
    "d dimer": "D-Dimer",
    "ddimer": "D-Dimer",

    # Blood tests - Biochemistry
    "u&e": "Urea and Electrolytes",
    "u+e": "Urea and Electrolytes",
    "ue": "Urea and Electrolytes",
    "u&es": "Urea and Electrolytes",
    "urea and electrolytes": "Urea and Electrolytes",
    "renal function": "Renal Function",
    "renal": "Renal Function",
    "lft": "Liver Function Tests",
    "lfts": "Liver Function Tests",
    "liver function": "Liver Function Tests",
    "liver function tests": "Liver Function Tests",
    "tfts": "Thyroid Function Tests",
    "tft": "Thyroid Function Tests",
    "thyroid function": "Thyroid Function Tests",
    "thyroid": "Thyroid Function Tests",
    "tsh": "Thyroid Stimulating Hormone",
    "t4": "Free T4",
    "free t4": "Free T4",
    "t3": "Free T3",
    "bone profile": "Bone Profile",
    "calcium": "Calcium",
    "ca": "Calcium",
    "phosphate": "Phosphate",
    "magnesium": "Magnesium",
    "mg": "Magnesium",
    "glucose": "Glucose",
    "blood glucose": "Blood Glucose",
    "bg": "Blood Glucose",
    "cbg": "Capillary Blood Glucose",
    "hba1c": "HbA1c",
    "glycated haemoglobin": "HbA1c",
    "crp": "C-Reactive Protein",
    "c-reactive protein": "C-Reactive Protein",
    "procalcitonin": "Procalcitonin",
    "lactate": "Lactate",
    "ammonia": "Ammonia",
    "lipids": "Lipid Profile",
    "lipid profile": "Lipid Profile",
    "cholesterol": "Cholesterol",
    "hdl": "HDL Cholesterol",
    "ldl": "LDL Cholesterol",
    "triglycerides": "Triglycerides",
    "tg": "Triglycerides",
    "amylase": "Amylase",
    "lipase": "Lipase",
    "ck": "Creatine Kinase",
    "creatine kinase": "Creatine Kinase",
    "troponin": "Troponin",
    "trop": "Troponin",
    "hs-trop": "High-Sensitivity Troponin",
    "hstrop": "High-Sensitivity Troponin",
    "bnp": "B-Type Natriuretic Peptide",
    "nt-probnp": "NT-proBNP",
    "ntprobnp": "NT-proBNP",
    "ferritin": "Ferritin",
    "iron studies": "Iron Studies",
    "iron": "Iron Studies",
    "tibc": "Total Iron Binding Capacity",
    "transferrin": "Transferrin",
    "b12": "Vitamin B12",
    "vitamin b12": "Vitamin B12",
    "folate": "Folate",
    "folic acid": "Folate",
    "vitamin d": "Vitamin D",
    "vit d": "Vitamin D",
    "25-oh vitamin d": "Vitamin D",
    "psa": "Prostate Specific Antigen",
    "cea": "Carcinoembryonic Antigen",
    "ca125": "CA-125",
    "ca 125": "CA-125",
    "ca19-9": "CA 19-9",
    "ca 19-9": "CA 19-9",
    "afp": "Alpha-Fetoprotein",
    "alpha fetoprotein": "Alpha-Fetoprotein",

    # Blood tests - Blood gases
    "abg": "Arterial Blood Gas",
    "arterial blood gas": "Arterial Blood Gas",
    "vbg": "Venous Blood Gas",
    "venous blood gas": "Venous Blood Gas",
    "blood gas": "Blood Gas",

    # Blood tests - Immunology
    "immunoglobulins": "Immunoglobulins",
    "iga": "IgA",
    "igg": "IgG",
    "igm": "IgM",
    "ige": "IgE",
    "complement": "Complement",
    "c3": "Complement C3",
    "c4": "Complement C4",
    "ana": "Antinuclear Antibody",
    "anca": "Anti-Neutrophil Cytoplasmic Antibody",
    "anti-ccp": "Anti-CCP Antibody",
    "rheumatoid factor": "Rheumatoid Factor",
    "rf": "Rheumatoid Factor",

    # Microbiology
    "blood culture": "Blood Culture",
    "blood cultures": "Blood Cultures",
    "bc": "Blood Culture",
    "urine culture": "Urine Culture",
    "urine mc&s": "Urine Microscopy Culture and Sensitivity",
    "urine mcs": "Urine Microscopy Culture and Sensitivity",
    "msu": "Mid-Stream Urine",
    "csu": "Catheter Specimen Urine",
    "sputum culture": "Sputum Culture",
    "sputum mc&s": "Sputum Microscopy Culture and Sensitivity",
    "wound swab": "Wound Swab",
    "throat swab": "Throat Swab",
    "stool culture": "Stool Culture",
    "stool mc&s": "Stool Microscopy Culture and Sensitivity",
    "c diff": "Clostridium Difficile",
    "c. diff": "Clostridium Difficile",
    "cdiff": "Clostridium Difficile",
    "mrsa screen": "MRSA Screen",
    "mrsa": "MRSA Screen",
    "covid": "COVID-19 PCR",
    "covid pcr": "COVID-19 PCR",
    "covid-19": "COVID-19 PCR",
    "sars-cov-2": "COVID-19 PCR",
    "flu": "Influenza PCR",
    "influenza": "Influenza PCR",
    "rsv": "RSV PCR",
    "respiratory viral panel": "Respiratory Viral Panel",
    "viral screen": "Viral Screen",
    "hiv": "HIV Screen",
    "hepatitis": "Hepatitis Screen",
    "hep b": "Hepatitis B",
    "hbsag": "Hepatitis B Surface Antigen",
    "hep c": "Hepatitis C",
    "hcv": "Hepatitis C",
    "ebv": "Epstein-Barr Virus",
    "cmv": "Cytomegalovirus",
    "monospot": "Monospot",
    "tb": "Tuberculosis",
    "quantiferon": "Quantiferon-TB Gold",
    "mantoux": "Mantoux Test",

    # Urine tests
    "urinalysis": "Urinalysis",
    "urine dip": "Urine Dipstick",
    "dipstick": "Urine Dipstick",
    "urine": "Urinalysis",
    "upcr": "Urine Protein:Creatinine Ratio",
    "uacr": "Urine Albumin:Creatinine Ratio",
    "acr": "Albumin:Creatinine Ratio",
    "24h urine": "24-Hour Urine Collection",
    "24 hour urine": "24-Hour Urine Collection",
    "pregnancy test": "Pregnancy Test",
    "hcg": "HCG (Pregnancy Test)",
    "bhcg": "Beta-HCG",

    # Imaging - X-ray
    "cxr": "Chest X-Ray",
    "chest x-ray": "Chest X-Ray",
    "chest xray": "Chest X-Ray",
    "chest radiograph": "Chest X-Ray",
    "axr": "Abdominal X-Ray",
    "abdominal x-ray": "Abdominal X-Ray",
    "abdominal xray": "Abdominal X-Ray",
    "kub": "Kidneys Ureters Bladder X-Ray",
    "x-ray": "X-Ray",
    "xray": "X-Ray",
    "radiograph": "X-Ray",
    "plain film": "Plain Film X-Ray",
    "spine x-ray": "Spine X-Ray",
    "c-spine": "Cervical Spine X-Ray",
    "l-spine": "Lumbar Spine X-Ray",
    "hip x-ray": "Hip X-Ray",
    "knee x-ray": "Knee X-Ray",
    "ankle x-ray": "Ankle X-Ray",
    "shoulder x-ray": "Shoulder X-Ray",
    "hand x-ray": "Hand X-Ray",
    "wrist x-ray": "Wrist X-Ray",

    # Imaging - CT
    "ct": "CT Scan",
    "ct scan": "CT Scan",
    "cat scan": "CT Scan",
    "ct head": "CT Head",
    "ctb": "CT Brain",
    "ct brain": "CT Brain",
    "cta": "CT Angiogram",
    "ct angiogram": "CT Angiogram",
    "ctpa": "CT Pulmonary Angiogram",
    "ct pulmonary angiogram": "CT Pulmonary Angiogram",
    "ct chest": "CT Chest",
    "hrct": "High Resolution CT Chest",
    "ct abdomen": "CT Abdomen",
    "ct abdo": "CT Abdomen",
    "ct abdomen pelvis": "CT Abdomen and Pelvis",
    "ct ap": "CT Abdomen and Pelvis",
    "ct kub": "CT Kidneys Ureters Bladder",
    "ct urogram": "CT Urogram",
    "ct spine": "CT Spine",
    "ct c-spine": "CT Cervical Spine",

    # Imaging - MRI
    "mri": "MRI",
    "mri scan": "MRI Scan",
    "mri head": "MRI Head",
    "mri brain": "MRI Brain",
    "mra": "MR Angiogram",
    "mrcp": "MR Cholangiopancreatography",
    "mri spine": "MRI Spine",
    "mri c-spine": "MRI Cervical Spine",
    "mri l-spine": "MRI Lumbar Spine",
    "mri knee": "MRI Knee",
    "mri shoulder": "MRI Shoulder",
    "mri abdomen": "MRI Abdomen",
    "mri pelvis": "MRI Pelvis",
    "mri liver": "MRI Liver",
    "cardiac mri": "Cardiac MRI",

    # Imaging - Ultrasound
    "us": "Ultrasound",
    "uss": "Ultrasound Scan",
    "ultrasound": "Ultrasound",
    "scan": "Ultrasound Scan",
    "abdominal ultrasound": "Abdominal Ultrasound",
    "abdo uss": "Abdominal Ultrasound",
    "renal ultrasound": "Renal Ultrasound",
    "renal uss": "Renal Ultrasound",
    "pelvic ultrasound": "Pelvic Ultrasound",
    "pelvic uss": "Pelvic Ultrasound",
    "tvs": "Transvaginal Ultrasound",
    "transvaginal": "Transvaginal Ultrasound",
    "testicular ultrasound": "Testicular Ultrasound",
    "scrotal ultrasound": "Scrotal Ultrasound",
    "thyroid ultrasound": "Thyroid Ultrasound",
    "carotid doppler": "Carotid Doppler",
    "doppler": "Doppler Ultrasound",
    "dvt scan": "DVT Ultrasound",
    "leg doppler": "Lower Limb Doppler",
    "echo": "Echocardiogram",
    "echocardiogram": "Echocardiogram",
    "tte": "Transthoracic Echocardiogram",
    "toe": "Transoesophageal Echocardiogram",
    "tee": "Transoesophageal Echocardiogram",
    "bubble echo": "Bubble Echocardiogram",

    # Imaging - Nuclear medicine
    "nuclear medicine": "Nuclear Medicine Scan",
    "bone scan": "Bone Scan",
    "isotope bone scan": "Isotope Bone Scan",
    "pet": "PET Scan",
    "pet scan": "PET Scan",
    "pet-ct": "PET-CT Scan",
    "v/q scan": "Ventilation/Perfusion Scan",
    "vq scan": "Ventilation/Perfusion Scan",
    "lung perfusion scan": "Lung Perfusion Scan",
    "myocardial perfusion": "Myocardial Perfusion Scan",
    "mps": "Myocardial Perfusion Scan",
    "muga": "MUGA Scan",
    "thyroid scan": "Thyroid Scan",
    "renal scan": "Renal Scan",
    "dmsa": "DMSA Scan",
    "mag3": "MAG3 Renogram",

    # Cardiology
    "ecg": "ECG",
    "ekg": "ECG",
    "electrocardiogram": "ECG",
    "12 lead ecg": "12-Lead ECG",
    "holter": "Holter Monitor",
    "24h tape": "24-Hour Holter Monitor",
    "24 hour tape": "24-Hour Holter Monitor",
    "7 day tape": "7-Day Holter Monitor",
    "event recorder": "Event Recorder",
    "loop recorder": "Loop Recorder",
    "tilt table": "Tilt Table Test",
    "exercise tolerance test": "Exercise Tolerance Test",
    "ett": "Exercise Tolerance Test",
    "stress test": "Stress Test",
    "stress echo": "Stress Echocardiogram",
    "dobutamine stress echo": "Dobutamine Stress Echo",
    "cardiac catheter": "Cardiac Catheterisation",
    "angiogram": "Coronary Angiogram",
    "coronary angiogram": "Coronary Angiogram",
    "angio": "Angiogram",
    "ep study": "Electrophysiology Study",
    "electrophysiology study": "Electrophysiology Study",

    # Pulmonary
    "spirometry": "Spirometry",
    "lung function": "Lung Function Tests",
    "lung function tests": "Lung Function Tests",
    "pfts": "Pulmonary Function Tests",
    "pft": "Pulmonary Function Tests",
    "fev1": "FEV1",
    "fvc": "FVC",
    "peak flow": "Peak Expiratory Flow Rate",
    "pefr": "Peak Expiratory Flow Rate",
    "dlco": "Diffusing Capacity",
    "gas transfer": "Gas Transfer",
    "sleep study": "Sleep Study",
    "polysomnography": "Polysomnography",
    "oximetry": "Overnight Oximetry",
    "overnight oximetry": "Overnight Oximetry",

    # Endoscopy
    "endoscopy": "Endoscopy",
    "ogd": "Oesophagogastroduodenoscopy",
    "oesophagogastroduodenoscopy": "Oesophagogastroduodenoscopy",
    "gastroscopy": "Gastroscopy",
    "upper gi endoscopy": "Upper GI Endoscopy",
    "colonoscopy": "Colonoscopy",
    "flexible sigmoidoscopy": "Flexible Sigmoidoscopy",
    "sigmoidoscopy": "Sigmoidoscopy",
    "ercp": "ERCP",
    "eus": "Endoscopic Ultrasound",
    "capsule endoscopy": "Capsule Endoscopy",
    "bronchoscopy": "Bronchoscopy",
    "cystoscopy": "Cystoscopy",
    "laryngoscopy": "Laryngoscopy",
    "colposcopy": "Colposcopy",
    "hysteroscopy": "Hysteroscopy",
    "arthroscopy": "Arthroscopy",

    # Histology/Biopsy
    "biopsy": "Biopsy",
    "histology": "Histology",
    "cytology": "Cytology",
    "fna": "Fine Needle Aspiration",
    "fine needle aspiration": "Fine Needle Aspiration",
    "core biopsy": "Core Biopsy",
    "bone marrow": "Bone Marrow Biopsy",
    "bone marrow biopsy": "Bone Marrow Biopsy",
    "bma": "Bone Marrow Aspirate",
    "lymph node biopsy": "Lymph Node Biopsy",
    "liver biopsy": "Liver Biopsy",
    "renal biopsy": "Renal Biopsy",
    "skin biopsy": "Skin Biopsy",
    "smear": "Smear",
    "cervical smear": "Cervical Smear",
    "pap smear": "Pap Smear",

    # Neurology
    "eeg": "EEG",
    "electroencephalogram": "EEG",
    "emg": "EMG",
    "electromyography": "EMG",
    "nerve conduction": "Nerve Conduction Studies",
    "ncs": "Nerve Conduction Studies",
    "lumbar puncture": "Lumbar Puncture",
    "lp": "Lumbar Puncture",
    "csf": "CSF Analysis",
    "csf analysis": "CSF Analysis",

    # Other
    "dexa": "DEXA Scan",
    "dxa": "DEXA Scan",
    "bone density": "Bone Density Scan",
    "mammogram": "Mammogram",
    "mammography": "Mammography",
    "audiometry": "Audiometry",
    "hearing test": "Audiometry",
    "visual fields": "Visual Fields",
    "oct": "Optical Coherence Tomography",
    "fluorescein angiography": "Fluorescein Angiography",
    "genetic testing": "Genetic Testing",
    "karyotype": "Karyotype",
    "chromosomal analysis": "Chromosomal Analysis",
}

# Finding/result patterns that indicate normal
NORMAL_FINDINGS = {
    "normal", "unremarkable", "wnl", "within normal limits", "nad", "no abnormality detected",
    "no abnormality", "nil acute", "nil significant", "nothing abnormal", "no acute",
    "no significant abnormality", "no acute findings", "clear", "negative", "satisfactory",
    "no evidence of", "stable", "unchanged", "no change", "resolved", "improved",
    "essentially normal", "grossly normal", "clinically normal", "reassuring",
}

# Finding/result patterns that indicate abnormal
ABNORMAL_FINDINGS = {
    "abnormal", "positive", "elevated", "raised", "high", "low", "decreased", "reduced",
    "increased", "deranged", "impaired", "significant", "concerning", "suspicious",
    "consistent with", "suggestive of", "shows", "demonstrates", "confirms", "reveals",
    "detected", "present", "identified", "noted", "seen", "observed", "found",
    "new", "acute", "active", "progressive", "worsening", "deteriorating",
}

# Pending/awaited patterns
PENDING_FINDINGS = {
    "pending", "awaited", "awaiting", "sent", "requested", "ordered", "to be done",
    "results awaited", "result pending", "awaiting result", "not yet available",
    "in progress", "processing", "being processed",
}

# Investigation category mapping
CATEGORY_PATTERNS = {
    InvestigationCategory.BLOOD_TEST: [
        "blood", "fbc", "cbc", "u&e", "lft", "tft", "crp", "glucose", "hba1c",
        "troponin", "bnp", "lipid", "iron", "b12", "folate", "vitamin", "psa",
        "coag", "clotting", "d-dimer", "ferritin", "esr", "gas", "abg", "vbg",
    ],
    InvestigationCategory.IMAGING: [
        "x-ray", "xray", "cxr", "axr", "ct", "mri", "ultrasound", "uss", "scan",
        "radiograph", "pet", "nuclear", "dexa", "mammogram",
    ],
    InvestigationCategory.CARDIOLOGY: [
        "ecg", "ekg", "echo", "holter", "tape", "stress", "angiogram", "catheter",
    ],
    InvestigationCategory.MICROBIOLOGY: [
        "culture", "swab", "mc&s", "mcs", "mrsa", "covid", "pcr", "viral",
        "hiv", "hepatitis", "tb", "quantiferon",
    ],
    InvestigationCategory.HISTOLOGY: [
        "biopsy", "histology", "cytology", "fna", "bone marrow", "smear",
    ],
    InvestigationCategory.ENDOSCOPY: [
        "endoscopy", "ogd", "gastroscopy", "colonoscopy", "sigmoidoscopy",
        "ercp", "bronchoscopy", "cystoscopy",
    ],
    InvestigationCategory.PULMONARY: [
        "spirometry", "lung function", "pft", "peak flow", "sleep study",
        "oximetry",
    ],
    InvestigationCategory.URINE: [
        "urine", "urinalysis", "dipstick", "msu", "csu", "upcr", "uacr",
        "pregnancy", "hcg",
    ],
}


class InvestigationParser:
    """
    Parser that separates investigation names from findings.

    Handles formats:
    - "FBC: normal"
    - "FBC - unremarkable"
    - "FBC unremarkable"
    - "FBC showed normal values"
    - "Normal FBC"
    """

    def __init__(self):
        self.expansions = INVESTIGATION_EXPANSIONS
        self.excluded = EXCLUDED_TERMS
        self.section_headers = SECTION_HEADERS
        self.normal_findings = NORMAL_FINDINGS
        self.abnormal_findings = ABNORMAL_FINDINGS
        self.pending_findings = PENDING_FINDINGS
        self.category_patterns = CATEGORY_PATTERNS

        self._compile_patterns()

    def _compile_patterns(self):
        """Compile regex patterns"""

        # Pattern: Investigation : Finding (colon separator - preferred)
        self.colon_pattern = re.compile(
            r'^([^:]+?)\s*:\s*(.+)$',
            re.IGNORECASE
        )

        # Pattern: Investigation - Finding (dash separator with whitespace required)
        # Requires space around dash to avoid matching "D-dimer", "CT-scan" etc.
        self.dash_pattern = re.compile(
            r'^(.+?)\s+[-–]\s+(.+)$',
            re.IGNORECASE
        )

        # Pattern: Investigation (Finding) or Investigation [Finding]
        self.bracket_pattern = re.compile(
            r'^([^(\[]+?)\s*[(\[]([^)\]]+)[)\]]',
            re.IGNORECASE
        )

        # Pattern: Investigation showed/revealed/demonstrated Finding
        self.verb_pattern = re.compile(
            r'^(.+?)\s+(?:showed?|reveal(?:ed|s)?|demonstrat(?:ed|es)?|'
            r'confirm(?:ed|s)?|indicat(?:ed|es)?|suggest(?:ed|s)?)\s+(.+)$',
            re.IGNORECASE
        )

        # Pattern: Finding Investigation (e.g., "Normal ECG")
        self.finding_first_pattern = re.compile(
            r'^(normal|abnormal|unremarkable|positive|negative|clear|stable)\s+(.+)$',
            re.IGNORECASE
        )

        # Pattern: Investigation = Finding
        self.equals_pattern = re.compile(
            r'^([^=]+?)\s*=\s*(.+)$',
            re.IGNORECASE
        )

    def parse(self, text: str) -> List[ParsedInvestigation]:
        """
        Parse text and extract investigations with findings.

        Args:
            text: Clinical text containing investigation results

        Returns:
            List of ParsedInvestigation objects
        """
        results = []

        lines = text.split('\n')
        for line in lines:
            line = line.strip()
            if not line or len(line) < 2:
                continue

            parsed = self._parse_line(line)
            if parsed:
                results.append(parsed)

        return results

    def parse_single(self, text: str) -> Optional[ParsedInvestigation]:
        """Parse a single investigation string"""
        return self._parse_line(text.strip())

    def _parse_line(self, line: str) -> Optional[ParsedInvestigation]:
        """Parse a single line for investigation and finding"""

        original_line = line

        # Check if this is an excluded term (measurement)
        line_lower = line.lower().strip()
        # Remove trailing colon for comparison
        line_base = line_lower.rstrip(':').strip()

        # Skip section headers
        if line_base in self.section_headers:
            return None

        for excluded in self.excluded:
            if excluded in line_lower:
                # Skip if the line is primarily about an excluded term
                if line_lower.startswith(excluded) or line_lower == excluded:
                    return None

        investigation = None
        finding = None

        # Try different patterns in order of specificity
        # Pattern 1: Colon separator (most common, e.g., "FBC: normal")
        match = self.colon_pattern.match(line)
        if match:
            investigation = match.group(1).strip()
            finding = match.group(2).strip()
        else:
            # Pattern 2: Dash with spaces (e.g., "FBC - normal", not "D-dimer")
            match = self.dash_pattern.match(line)
            if match:
                investigation = match.group(1).strip()
                finding = match.group(2).strip()
            else:
                # Pattern 3: Brackets
                match = self.bracket_pattern.match(line)
                if match:
                    investigation = match.group(1).strip()
                    finding = match.group(2).strip()
                else:
                    # Pattern 4: Verb connector
                    match = self.verb_pattern.match(line)
                    if match:
                        investigation = match.group(1).strip()
                        finding = match.group(2).strip()
                    else:
                        # Pattern 5: Finding first (e.g., "Normal ECG")
                        match = self.finding_first_pattern.match(line)
                        if match:
                            finding = match.group(1).strip()
                            investigation = match.group(2).strip()
                        else:
                            # Pattern 6: Equals sign
                            match = self.equals_pattern.match(line)
                            if match:
                                investigation = match.group(1).strip()
                                finding = match.group(2).strip()
                            else:
                                # No separator found - assume entire line is investigation name
                                investigation = line

        if not investigation:
            return None

        # Clean up investigation name
        investigation = self._clean_investigation(investigation)
        if not investigation:
            return None

        # Check again if cleaned investigation is excluded
        inv_lower = investigation.lower()
        for excluded in self.excluded:
            if inv_lower == excluded or inv_lower.startswith(excluded + " "):
                return None

        # Expand abbreviation
        investigation_expanded, abbrev = self._expand_investigation(investigation)

        # Determine finding status
        finding_status = self._determine_finding_status(finding)

        # Determine category
        category = self._determine_category(investigation_expanded, inv_lower)

        # Calculate confidence
        confidence = self._calculate_confidence(investigation_expanded, finding, finding_status)

        return ParsedInvestigation(
            investigation=investigation_expanded,
            investigation_abbrev=abbrev,
            finding=finding,
            finding_status=finding_status,
            category=category,
            raw_text=original_line,
            confidence=confidence
        )

    def _clean_investigation(self, text: str) -> Optional[str]:
        """Clean investigation name"""

        # Remove common prefixes
        text = re.sub(r'^(?:the\s+|a\s+|an\s+)', '', text, flags=re.IGNORECASE)

        # Remove trailing punctuation
        text = text.rstrip('.:;,')

        # Remove leading numbers/bullets
        text = re.sub(r'^[\d\.\-\•\*]+\s*', '', text)

        # Clean whitespace
        text = ' '.join(text.split())

        if len(text) < 2:
            return None

        return text

    def _expand_investigation(self, investigation: str) -> Tuple[str, Optional[str]]:
        """Expand abbreviation to full name"""

        inv_lower = investigation.lower().strip()

        # Direct lookup
        if inv_lower in self.expansions:
            return self.expansions[inv_lower], investigation

        # Try without common suffixes
        for suffix in [' test', ' tests', ' scan', ' study']:
            if inv_lower.endswith(suffix):
                base = inv_lower[:-len(suffix)]
                if base in self.expansions:
                    return self.expansions[base], investigation

        # No expansion found - return original with title case
        return investigation.title() if investigation.islower() else investigation, None

    def _determine_finding_status(self, finding: Optional[str]) -> str:
        """Determine if finding is normal, abnormal, pending, or unknown"""

        if not finding:
            return FindingStatus.UNKNOWN.value

        finding_lower = finding.lower()

        # Check for pending
        for pattern in self.pending_findings:
            if pattern in finding_lower:
                return FindingStatus.PENDING.value

        # Check for normal
        for pattern in self.normal_findings:
            if pattern in finding_lower:
                return FindingStatus.NORMAL.value

        # Check for abnormal
        for pattern in self.abnormal_findings:
            if pattern in finding_lower:
                return FindingStatus.ABNORMAL.value

        # Default to unknown if finding exists but status unclear
        return FindingStatus.UNKNOWN.value

    def _determine_category(self, investigation: str, inv_lower: str) -> str:
        """Determine investigation category"""

        for category, patterns in self.category_patterns.items():
            for pattern in patterns:
                if pattern in inv_lower:
                    return category.value

        return InvestigationCategory.OTHER.value

    def _calculate_confidence(self, investigation: str, finding: Optional[str],
                             finding_status: str) -> float:
        """Calculate confidence score"""

        score = 0.0

        # Known investigation name
        if investigation.lower() in self.expansions or \
           any(investigation.lower() in v.lower() for v in self.expansions.values()):
            score += 0.5
        else:
            score += 0.3

        # Has finding
        if finding:
            score += 0.3

        # Finding status determined
        if finding_status != FindingStatus.UNKNOWN.value:
            score += 0.2

        return min(score, 1.0)


def parse_investigations(text: str) -> List[Dict]:
    """
    Convenience function to parse investigations from text.

    Args:
        text: Clinical text containing investigation results

    Returns:
        List of investigation dictionaries
    """
    parser = InvestigationParser()
    results = parser.parse(text)
    return [r.to_dict() for r in results]


if __name__ == "__main__":
    # Test the parser
    test_cases = [
        "FBC: unremarkable",
        "FBC - normal",
        "ECG: Normal sinus rhythm",
        "CXR showed no acute changes",
        "Normal ECG",
        "U&E - within normal limits",
        "CT Head: No acute intracranial pathology",
        "MRI Brain revealed white matter changes",
        "Blood cultures: No growth at 48 hours",
        "Troponin: 15 (elevated)",
        "LFTs deranged",
        "CRP = 45",
        "Urine dipstick: positive for leucocytes",
        "D-dimer: negative",
        "CTPA: No pulmonary embolism",
        "Echo: Good LV function, EF 55%",
        "Spirometry: Obstructive pattern",
        "OGD: Barrett's oesophagus",
        "Colonoscopy: Normal to caecum",
        "Bone marrow biopsy: Pending",
        # These should be EXCLUDED
        "Height: 175cm",
        "Weight: 80kg",
        "BMI: 26",
        "BSA: 1.9m2",
        "BP: 120/80",
    ]

    parser = InvestigationParser()

    print("=" * 80)
    print("INVESTIGATION PARSER TEST")
    print("=" * 80)

    for test in test_cases:
        print(f"\nInput: {test}")
        result = parser.parse_single(test)
        if result:
            print(f"  Investigation: {result.investigation}")
            if result.investigation_abbrev:
                print(f"  Abbreviation:  {result.investigation_abbrev}")
            print(f"  Finding:       {result.finding or '(none)'}")
            print(f"  Status:        {result.finding_status}")
            print(f"  Category:      {result.category}")
            print(f"  Confidence:    {result.confidence:.2f}")
        else:
            print("  [EXCLUDED - not an investigation]")

    print("\n" + "=" * 80)
    print("MULTI-LINE EXTRACTION TEST")
    print("=" * 80)

    clinical_text = """
    Investigations:
    FBC: Unremarkable
    U&E: Na 138, K 4.2, Cr 89 - all normal
    LFTs: Mildly elevated ALT
    CRP: 12 (slightly raised)
    ECG: Sinus rhythm, rate 72
    CXR: Clear lung fields, no cardiomegaly
    CT Head: No acute intracranial pathology
    Blood cultures: Pending

    Observations:
    Height: 178cm
    Weight: 85kg
    BMI: 26.8
    BP: 135/82
    HR: 72
    """

    results = parser.parse(clinical_text)
    print(f"\nExtracted {len(results)} investigations:")
    for i, r in enumerate(results, 1):
        status_icon = "[OK]" if r.finding_status == "normal" else \
                      "[!!]" if r.finding_status == "abnormal" else \
                      "[??]" if r.finding_status == "pending" else "[--]"
        print(f"  {i}. {status_icon} {r.investigation}: {r.finding or '(no finding)'}")
