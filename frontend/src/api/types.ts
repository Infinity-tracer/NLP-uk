export interface PatientInfo {
  name: string;
  nhs_number: string;
  dob: string;
  sex: string;
  address?: string;
  hospital_number?: string;
  gp_practice?: string;
  gravida_parity?: string;
  edd?: string;
  gestational_age?: string;
  pathways_urgency?: string;
  presenting_complaint?: string;
}

export interface SNOMEDEntity {
  text: string;
  category: string;
  snomed_code: string;
  description: string;
  confidence: number;
  entity_id: string;
  source: string;
  clinical_category?: string;  // problems | treatments | medications | investigations | diagnoses
  result?: string;             // For investigations: "Pending", "Normal", etc.
  priority?: string;           // For investigations: "Urgent", "Routine"
  snomed_description?: string; // Alternative description field
}

export interface SNOMEDData {
  // 5 clinical categories with SNOMED codes
  problems: SNOMEDEntity[];       // Symptoms/issues (e.g., neck pain, tummy irritation)
  treatments: SNOMEDEntity[];     // Therapeutic procedures (e.g., Mental Health treatment, Chemo)
  medications: SNOMEDEntity[];    // Drugs (e.g., Thyroxine, Aspirin)
  investigations: SNOMEDEntity[]; // Diagnostic tests (e.g., CT Scan, MRI, Smear, Angio)
  diagnoses: SNOMEDEntity[];      // Confirmed conditions (e.g., ulcerative colitis)
  all_entities: SNOMEDEntity[];
  used_fallback: boolean;
  top3_fallback: SNOMEDEntity[];
  used_summary_fallback?: boolean;
  used_doctype_fallback?: boolean;
  snomed_confidence?: number;
}

export interface Medication {
  name: string;
  dose: string;
  raw: string;
}

export interface StructuredFields {
  admission_date?: string;
  discharge_date?: string;
  appointment_date?: string;
  consultant?: string;
  department?: string;
  hospital?: string;
  gp_actions?: string;
  diagnosis_text?: string;
  admission_method?: string;
  discharge_method?: string;
  procedure?: string;
  indication?: string;
  impression?: string;
}

export interface Summary {
  summary: string;
  confidence: number;
}

export interface RoleActions {
  doctor: string[];
  pharmacist: string[];
  reception: string[];
}

export interface ActionsStructured {
  sender_actions: RoleActions;
  gp_surgery_actions: RoleActions;
  patient_actions?: string[];
  patient_booking?: string[];
}

export interface Summaries {
  clinician: Summary;
  patient: Summary;
  pharmacist: Summary;
  follow_up_actions: string;
  actions_structured: ActionsStructured;
  llm_confidence: number;
}

export interface PipelineStage {
  status: 'done' | 'partial' | 'error' | 'skipped' | 'queued_for_layoutlmv3';
  confidence?: number;
  note?: string;
  error?: string;
  pages?: number;
  chars_extracted?: number;
  entities_found?: number;
  phi_entities_detected?: number;
  letter_type?: string;
}

export interface PipelineStages {
  tier0?: PipelineStage;
  tier1?: PipelineStage;
  tier2?: PipelineStage;
  track_a?: PipelineStage;
  track_b?: PipelineStage;
  hipaa?: PipelineStage;
}

export interface ClinicalSpecifics {
  [key: string]: string | number | Record<string, string | number>;
}

export interface DiaryEvent {
  event: string;
  due_date: string;
  responsible_party: string;
}

export interface TreatmentItem {
  term: string;
  snomed_code?: string;
  snomed_description?: string;
}

export interface InvestigationItem {
  term: string;
  result?: string;
  snomed_code?: string;
}

// Resolved clinical abbreviation
export interface ResolvedAbbreviation {
  abbreviation: string;
  expansion: string;
  category: string;
  position: number;
}

// Abbreviation resolution result
export interface AbbreviationResult {
  resolved: ResolvedAbbreviation[];
  stats: Record<string, number>;
}

// Medical NER Entity (17 categories)
export interface NEREntity {
  text: string;
  category: string;
  confidence: number;
  start_pos: number;
  end_pos: number;
  section?: string;
  normalized_text?: string;
  attributes?: Record<string, string | number>;
  evidence?: string;
}

// Medical NER Results (17 distinct categories)
export interface MedicalNERResult {
  diagnoses: NEREntity[];
  symptoms: NEREntity[];
  signs: NEREntity[];
  investigations: NEREntity[];
  procedures: NEREntity[];
  medications: NEREntity[];
  allergies: NEREntity[];
  social_history: NEREntity[];
  past_medical_history: NEREntity[];
  family_history: NEREntity[];
  discharge_advice: NEREntity[];
  follow_up_plan: NEREntity[];
  gp_actions: NEREntity[];
  hospital_actions: NEREntity[];
  referrals: NEREntity[];
  clinical_scores: NEREntity[];
  vital_signs: NEREntity[];
  stats: Record<string, number>;
}

export interface ProcessResult {
  doc_id: string;
  filename: string;
  processed_at: string;
  status: 'processing' | 'processed' | 'review_required' | 'error';
  error?: string;

  pages_processed: number;
  pipeline_stages: PipelineStages;
  unified_confidence: number;
  confidence_threshold: number;
  requires_review: boolean;

  letter_type: string;
  hospital_trust: string;
  is_sensitive: boolean;

  preview_pages: string[];
  preview_image: string | null;

  patient_info: PatientInfo;
  structured: StructuredFields;
  clinical_specifics: ClinicalSpecifics;

  extracted_text: string;       // Normalized text (used for NLP)
  raw_ocr_text?: string;        // Original OCR output before normalization
  icd_codes: string[];
  medications_raw: Medication[];

  snomed: SNOMEDData;
  summaries: Summaries;
  actions_structured: ActionsStructured;
  follow_up_actions: string;

  phi_entity_count: number;

  // Comprehensive extraction fields (Claude Sonnet 5)
  event_date?: string;
  letter_date?: string;
  conclusion?: string;
  recommendation?: string;
  diary_events?: DiaryEvent[];
  treatments?: TreatmentItem[];
  investigations?: InvestigationItem[];

  // Medical NER (17 categories)
  medical_ner?: MedicalNERResult;

  // Clinical abbreviations (both forms stored)
  abbreviations?: AbbreviationResult;
}

export type TabType = 'details' | 'coding' | 'followup' | 'gpactions';

export type AppState = 'upload' | 'processing' | 'result';

export const LETTER_TYPE_BUCKETS = [
  { key: 'HOSP', label: 'Hospital Discharge Summary (after admission into hospital)' },
  { key: 'CLIN', label: 'Clinical Letters/Report (after visiting specialists)' },
  { key: '111', label: '111 Report (seeking advice from Clinician over phone)' },
  { key: 'ED', label: 'Accident & Emergency Department report' },
  { key: 'AMB', label: 'Ambulance Report (When emergency services are called)' },
  { key: 'PRIV', label: 'Private Specialists clinical letter' },
  { key: 'EXT', label: 'External service providers (Boots, Spec savers – for Eye & ENT)' },
  { key: 'DES', label: 'Diabetic eye screening reports' },
  { key: 'OOH', label: 'Out of hours (East Berkshire Primary Care)' },
  { key: 'MISC', label: 'Miscellaneous' },
] as const;
