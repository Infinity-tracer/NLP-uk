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

// Assertion status for clinical entities (negation detection)
export type AssertionStatus = 'present' | 'absent' | 'historical' | 'family_history' | 'possible' | 'ruled_out';

// Temporal state for clinical entities
export type TemporalState = 'current' | 'historical' | 'resolved' | 'suspected' | 'chronic' | 'acute';

// Clinical temporal category
export type ClinicalTemporalCategory =
  | 'current_diagnosis'
  | 'past_medical_history'
  | 'previous_surgery'
  | 'resolved_symptom'
  | 'current_symptom'
  | 'chronic_disease'
  | 'family_history'
  | 'medication_history'
  | 'current_medication'
  | 'acute_presentation';

// SNOMED concept type
export type SNOMEDConceptType =
  | 'disorder'
  | 'finding'
  | 'clinical_finding'
  | 'procedure'
  | 'substance'
  | 'product'
  | 'morphology'
  | 'body_structure'
  | 'qualifier'
  | 'observable'
  | 'situation'
  | 'event'
  | 'unknown';

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
  // Assertion status from negation detection
  assertion?: AssertionStatus;           // present, absent, historical, family_history, possible, ruled_out
  assertion_trigger?: string | null;     // The trigger phrase (e.g., "No", "Denies", "History of")
  assertion_confidence?: number;         // Confidence in the assertion
  // Temporal state from temporal reasoning
  temporal_state?: TemporalState;        // current, historical, resolved, suspected, chronic, acute
  temporal_trigger?: string | null;      // The trigger phrase (e.g., "History of", "Resolved", "Chronic")
  temporal_confidence?: number;          // Confidence in the temporal classification
  clinical_temporal_category?: ClinicalTemporalCategory;  // More specific category
  time_reference?: string;               // Time reference (e.g., "2019", "3 years ago")
  // SNOMED mapping pipeline info
  concept_type?: SNOMEDConceptType;      // disorder, finding, procedure, etc.
  spell_corrected?: boolean;             // True if term was spell-corrected
  synonym_matched?: boolean;             // True if mapped via synonym
  mapping_rejected?: boolean;            // True if mapping was rejected (low confidence)
  rejection_reason?: string;             // Reason for rejection
}

// Temporal state distribution stats
export interface TemporalStats {
  current: number;
  historical: number;
  resolved: number;
  suspected: number;
  chronic: number;
  acute: number;
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
  // Negation detection: entities that were filtered out (absent/ruled out)
  negated_entities?: SNOMEDEntity[];
  // Temporal reasoning: distribution of temporal states
  temporal_stats?: TemporalStats;
}

// Structured medication data from medication extractor
export interface StructuredMedicationData {
  drug_name: string | null;
  strength: string | null;       // e.g., "40mg"
  dose: string | null;           // e.g., "2 tablets"
  route: string | null;          // e.g., "oral", "intravenous"
  frequency: string | null;      // Expanded: "twice daily"
  frequency_code: string | null; // Original: "BD", "OD", "TDS"
  duration: string | null;       // e.g., "7 days"
  status: MedicationStatus;
  form: string | null;           // e.g., "tablet", "capsule"
  instructions: string | null;   // e.g., "with food"
  confidence: number;
}

// Medication status
export type MedicationStatus =
  | 'current'
  | 'discontinued'
  | 'new'
  | 'changed'
  | 'on_hold'
  | 'prn'
  | 'unknown';

// Route of administration
export type RouteOfAdministration =
  | 'oral'
  | 'sublingual'
  | 'buccal'
  | 'topical'
  | 'transdermal'
  | 'inhalation'
  | 'nebulised'
  | 'nasal'
  | 'ophthalmic'
  | 'otic'
  | 'rectal'
  | 'vaginal'
  | 'intravenous'
  | 'intramuscular'
  | 'subcutaneous'
  | 'intradermal'
  | 'intrathecal'
  | 'epidural'
  | 'peg'
  | 'ng'
  | 'unknown';

// UK Prescribing frequency codes
export type FrequencyCode =
  | 'OD'    // Once daily
  | 'BD'    // Twice daily
  | 'TDS'   // Three times daily
  | 'QDS'   // Four times daily
  | 'PRN'   // As required
  | 'STAT'  // Immediately
  | 'OM'    // Every morning
  | 'ON'    // At night
  | 'NOCTE' // At night (Latin)
  | 'Q2H'   // Every 2 hours
  | 'Q4H'   // Every 4 hours
  | 'Q6H'   // Every 6 hours
  | 'Q8H'   // Every 8 hours
  | 'Q12H'  // Every 12 hours
  | 'WEEKLY'
  | '2X WEEKLY'
  | '3X WEEKLY'
  | 'AC'    // Before meals
  | 'PC'    // After meals
  | 'CC'    // With food
  | 'ALT'   // Alternate days
  | 'CONT'; // Continuous

export interface Medication {
  name: string;
  dose: string;
  raw: string;
  // Full structured data (when medication_extractor is available)
  structured?: StructuredMedicationData;
}

// Investigation category
export type InvestigationCategory =
  | 'blood_test'
  | 'imaging'
  | 'cardiology'
  | 'microbiology'
  | 'histology'
  | 'endoscopy'
  | 'pulmonary'
  | 'urine'
  | 'other';

// Finding status
export type FindingStatus =
  | 'normal'
  | 'abnormal'
  | 'pending'
  | 'not_done'
  | 'unknown';

// Parsed investigation with separated name and finding
export interface ParsedInvestigation {
  investigation: string;              // Investigation name (expanded)
  investigation_abbrev: string | null; // Original abbreviation if used
  finding: string | null;             // The result/finding
  finding_status: FindingStatus;      // normal/abnormal/pending/unknown
  category: InvestigationCategory;    // blood_test/imaging/cardiology/etc.
  raw_text: string;                   // Original text
  confidence: number;                 // Extraction confidence
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
  // Assertion status from negation detection
  assertion?: AssertionStatus;
  assertion_trigger?: string | null;
  assertion_confidence?: number;
  // Temporal state from temporal reasoning
  temporal_state?: TemporalState;
  temporal_trigger?: string | null;
  temporal_confidence?: number;
  clinical_temporal_category?: ClinicalTemporalCategory;
  time_reference?: string;
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

  // Parsed investigations with separated names and findings
  parsed_investigations?: ParsedInvestigation[];
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
