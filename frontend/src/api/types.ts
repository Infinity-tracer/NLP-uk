// ═══════════════════════════════════════════════════════════════════════════════
// NHS Clinical Document NLP Pipeline - TypeScript Types
// Redesigned output schema with standardized clinical entities
// ═══════════════════════════════════════════════════════════════════════════════

// ────────────────────────────────────────────────────────────────────────────────
// CORE CLINICAL ENTITY (Standardized across all categories)
// ────────────────────────────────────────────────────────────────────────────────

/**
 * Assertion status for clinical entities (negation detection)
 */
export type AssertionStatus =
  | 'present'        // Entity is affirmed/present
  | 'absent'         // Negated (e.g., "no chest pain")
  | 'historical'     // Past occurrence
  | 'family_history' // Family member's condition
  | 'possible'       // Uncertain/suspected
  | 'ruled_out';     // Explicitly excluded

/**
 * Temporal status for clinical entities
 */
export type TemporalStatus =
  | 'current'     // Active/ongoing
  | 'historical'  // Past/resolved
  | 'chronic'     // Long-standing
  | 'acute'       // Recent onset
  | 'resolved'    // No longer active
  | 'suspected';  // Under investigation

/**
 * Ontology system identifier
 */
export type OntologySystem =
  | 'SNOMED-CT'
  | 'ICD-10'
  | 'dm+d'        // NHS dictionary of medicines and devices
  | 'OPCS-4'      // Operative procedures
  | 'READ'        // Read codes (legacy)
  | 'LOCAL'       // Local/internal codes
  | 'NONE';       // No ontology mapping

/**
 * Document section where entity was found
 */
export type ClinicalSection =
  | 'presenting_complaint'
  | 'history_presenting_complaint'
  | 'past_medical_history'
  | 'surgical_history'
  | 'medication'
  | 'allergies'
  | 'social_history'
  | 'family_history'
  | 'examination'
  | 'investigations'
  | 'diagnosis'
  | 'differential_diagnosis'
  | 'treatment'
  | 'discharge'
  | 'advice'
  | 'gp_actions'
  | 'follow_up'
  | 'referral'
  | 'prognosis'
  | 'header'
  | 'unknown';

/**
 * Evidence span - REQUIRED for every entity.
 * Entities without evidence are discarded (no hallucination policy).
 */
export interface EvidenceSpan {
  text: string;                      // The exact text span from document
  page: number;                      // 1-indexed page number
  line: number;                      // 1-indexed line number within page
  sentence: string;                  // Full sentence containing the entity
  char_start: number;                // Character offset start in document
  char_end: number;                  // Character offset end in document
}

/**
 * Standardized clinical entity - ALL extracted entities follow this schema.
 *
 * EVIDENCE REQUIREMENT: Every entity MUST have a valid evidence span.
 * Entities without supporting evidence are discarded during extraction.
 * This prevents hallucination and ensures traceability.
 */
export interface ClinicalEntity {
  // Core identification
  text: string;                      // Original text as found in document
  normalized_text: string;           // Standardized/canonical form

  // ═══════════════════════════════════════════════════════════════════════════════
  // EVIDENCE (REQUIRED) - No evidence = entity discarded
  // ═══════════════════════════════════════════════════════════════════════════════
  evidence: EvidenceSpan;            // REQUIRED: Source text span from document

  // Ontology coding (must reference originating text via evidence)
  ontology_code: string | null;      // Code (e.g., "22298006" for MI)
  ontology_system: OntologySystem;   // Which coding system
  ontology_description?: string;     // Human-readable term from ontology
  ontology_source_text?: string;     // Original text that was mapped to ontology

  // Confidence & validation
  confidence: number;                // 0.0-1.0 extraction confidence
  mapping_confidence?: number;       // 0.0-1.0 ontology mapping confidence
  validated: boolean;                // Passed medical validation
  validation_note?: string;          // If rejected, why

  // Clinical context
  assertion_status: AssertionStatus; // Negation/affirmation
  temporal_status: TemporalStatus;   // When did this occur
  section: ClinicalSection;          // Which part of document

  // Deduplication
  canonical_form?: string;           // Merged canonical name
  aliases?: string[];                // Alternative terms merged

  // Additional context
  attributes?: Record<string, string | number | boolean>;
}

// ────────────────────────────────────────────────────────────────────────────────
// DOMAIN-SPECIFIC ENTITY EXTENSIONS
// ────────────────────────────────────────────────────────────────────────────────

/**
 * Diagnosis entity with additional clinical classification
 */
export interface DiagnosisEntity extends ClinicalEntity {
  icd10_code?: string;               // ICD-10 mapping
  icd10_description?: string;
  severity?: 'mild' | 'moderate' | 'severe';
  certainty?: 'confirmed' | 'provisional' | 'differential' | 'working';
}

/**
 * Symptom entity with onset and characteristics
 */
export interface SymptomEntity extends ClinicalEntity {
  onset?: string;                    // When started
  duration?: string;                 // How long
  severity?: string;                 // Patient-reported severity
  character?: string;                // Nature of symptom
  site?: string;                     // Body location
  radiation?: string;                // Where it spreads
  aggravating_factors?: string[];
  relieving_factors?: string[];
}

/**
 * Medication entity with dosing information
 */
export interface MedicationEntity extends ClinicalEntity {
  // Drug identification
  drug_name: string;                 // Generic/brand name
  dm_d_code?: string;                // NHS dm+d code
  bnf_code?: string;                 // BNF code

  // Dosing
  dose: string | null;               // Amount per administration
  strength: string | null;           // Concentration (e.g., "40mg")
  form: string | null;               // tablet/capsule/liquid etc.
  route: string | null;              // oral/IV/IM etc.

  // Frequency
  frequency: string | null;          // Expanded (e.g., "twice daily")
  frequency_code: string | null;     // Abbreviated (e.g., "BD")

  // Status & duration
  duration: string | null;           // Course length
  status: MedicationStatus;          // current/stopped/new etc.
  instructions: string | null;       // Special instructions
}

export type MedicationStatus =
  | 'current'
  | 'new'
  | 'discontinued'
  | 'changed'
  | 'on_hold'
  | 'prn'
  | 'unknown';

/**
 * Investigation entity with results
 */
export interface InvestigationEntity extends ClinicalEntity {
  investigation_name: string;        // Full name
  investigation_abbrev?: string;     // Abbreviation (e.g., "FBC")

  // Results
  result: string | null;             // Result value/finding
  result_status: 'normal' | 'abnormal' | 'pending' | 'not_done' | 'unknown';
  reference_range?: string;          // Normal range
  unit?: string;                     // Measurement unit

  // Classification
  category: InvestigationCategory;
  priority?: 'urgent' | 'routine' | 'stat';
  specimen_type?: string;
}

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

/**
 * Vital sign entity
 */
export interface VitalEntity extends ClinicalEntity {
  vital_type: VitalType;
  value: string;
  numeric_value: number | null;
  unit: string;
  status: VitalStatus;
  timestamp?: string;

  // BP specific
  systolic?: number;
  diastolic?: number;

  // GCS specific
  gcs_eye?: number;
  gcs_verbal?: number;
  gcs_motor?: number;
}

export type VitalType =
  | 'temperature'
  | 'pulse'
  | 'heart_rate'
  | 'respiratory_rate'
  | 'blood_pressure'
  | 'systolic_bp'
  | 'diastolic_bp'
  | 'spo2'
  | 'gcs'
  | 'pain_score'
  | 'avpu'
  | 'weight'
  | 'height'
  | 'bmi'
  | 'blood_glucose';

export type VitalStatus =
  | 'normal'
  | 'low'
  | 'high'
  | 'critical_low'
  | 'critical_high'
  | 'unknown';

/**
 * Procedure entity
 */
export interface ProcedureEntity extends ClinicalEntity {
  procedure_name: string;
  opcs4_code?: string;               // OPCS-4 code
  opcs4_description?: string;

  date_performed?: string;
  surgeon?: string;
  indication?: string;
  findings?: string;
  complications?: string;
}

/**
 * Referral entity
 */
export interface ReferralEntity extends ClinicalEntity {
  referral_type: 'routine' | 'urgent' | '2ww' | 'emergency';
  specialty: string;
  reason: string;
  target_date?: string;
  facility?: string;
}

/**
 * Action entity (GP/Hospital/Patient actions)
 */
export interface ActionEntity extends ClinicalEntity {
  action_type: 'gp_action' | 'hospital_action' | 'patient_action';
  action_text: string;
  responsible_party?: string;
  due_date?: string;
  priority?: 'urgent' | 'routine' | 'when_possible';
}

/**
 * Follow-up entity
 */
export interface FollowUpEntity extends ClinicalEntity {
  follow_up_type: 'appointment' | 'test' | 'review' | 'contact';
  timeframe: string;
  specialty?: string;
  instructions?: string;
  contact?: string;
}

// ────────────────────────────────────────────────────────────────────────────────
// OUTPUT SCHEMA - Main Result Structure
// ────────────────────────────────────────────────────────────────────────────────

/**
 * Document metadata
 */
export interface DocumentMetadata {
  doc_id: string;
  filename: string;
  processed_at: string;
  status: 'processing' | 'processed' | 'review_required' | 'error';
  error?: string;

  // Document properties
  pages_processed: number;
  document_type: DocumentType;
  document_type_confidence: number;
  hospital_trust: string;
  is_sensitive: boolean;

  // Pipeline info
  pipeline_stages: PipelineStages;

  // Preview
  preview_pages: string[];
  preview_image: string | null;
}

export type DocumentType =
  | 'ed_discharge'
  | 'clinic_letter'
  | 'radiology'
  | 'histopathology'
  | 'operative_notes'
  | 'referral_letter'
  | 'gp_letter'
  | 'mental_health'
  | 'discharge_summary'
  | 'unknown';

export interface PipelineStages {
  tier0?: PipelineStage;
  tier1?: PipelineStage;
  tier2?: PipelineStage;
  track_a?: PipelineStage;
  track_b?: PipelineStage;
  hipaa?: PipelineStage;
  ocr_normalization?: PipelineStage;
  abbreviation_resolution?: PipelineStage;
  structure?: PipelineStage;
  ner?: PipelineStage;
  nhs_parser?: PipelineStage;
  extraction?: PipelineStage;
  validation?: PipelineStage;
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

/**
 * Summary output
 */
export interface Summary {
  summary: string;
  confidence: number;
}

export interface Summaries {
  clinician: Summary;
  patient: Summary;
  pharmacist: Summary;
  follow_up_actions: string;
}

/**
 * Patient information
 */
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

/**
 * Confidence scores breakdown
 */
export interface ConfidenceScores {
  ocr: number;
  ner: number;
  snomed: number;
  medication: number;
  investigation: number;
  summary: number;
  classification: number;
  overall: number;
  threshold: number;
  weights: {
    ocr: number;
    ner: number;
    snomed: number;
    medication: number;
    investigation: number;
    summary: number;
    classification: number;
  };
}

/**
 * Coding output - ontology mappings
 */
export interface CodingOutput {
  snomed_codes: ClinicalEntity[];     // All SNOMED-CT mappings
  icd10_codes: string[];              // ICD-10 codes
  opcs4_codes?: string[];             // Operative procedure codes
  dm_d_codes?: string[];              // Medication codes

  // Stats
  total_codes: number;
  mapping_confidence: number;
  validation_rejected: ClinicalEntity[];  // Entities that failed validation
}

/**
 * Main process result - redesigned output schema
 */
export interface ProcessResult {
  // ═══════════════════════════════════════════════════════════════════════════════
  // METADATA
  // ═══════════════════════════════════════════════════════════════════════════════
  metadata: DocumentMetadata;

  // ═══════════════════════════════════════════════════════════════════════════════
  // SUMMARY
  // ═══════════════════════════════════════════════════════════════════════════════
  summary: Summaries;

  // ═══════════════════════════════════════════════════════════════════════════════
  // CLINICAL ENTITIES (Standardized schema)
  // ═══════════════════════════════════════════════════════════════════════════════

  /** Primary diagnoses identified */
  diagnoses: DiagnosisEntity[];

  /** Symptoms and complaints */
  symptoms: SymptomEntity[];

  /** Current and historical medications */
  medications: MedicationEntity[];

  /** Investigations/tests (labs, imaging, etc.) */
  investigations: InvestigationEntity[];

  /** Vital signs */
  vitals: VitalEntity[];

  /** Procedures performed or planned */
  procedures: ProcedureEntity[];

  /** Referrals made */
  referrals: ReferralEntity[];

  /** GP actions required */
  gp_actions: ActionEntity[];

  /** Hospital actions required */
  hospital_actions: ActionEntity[];

  /** Follow-up plans */
  follow_up: FollowUpEntity[];

  // ═══════════════════════════════════════════════════════════════════════════════
  // CODING
  // ═══════════════════════════════════════════════════════════════════════════════
  coding: CodingOutput;

  // ═══════════════════════════════════════════════════════════════════════════════
  // CONFIDENCE
  // ═══════════════════════════════════════════════════════════════════════════════
  confidence: ConfidenceScores;

  // ═══════════════════════════════════════════════════════════════════════════════
  // PATIENT & DOCUMENT INFO
  // ═══════════════════════════════════════════════════════════════════════════════
  patient_info: PatientInfo;
  extracted_text: string;
  raw_ocr_text?: string;

  // ═══════════════════════════════════════════════════════════════════════════════
  // LEGACY COMPATIBILITY (to be deprecated)
  // ═══════════════════════════════════════════════════════════════════════════════

  // These fields maintain backward compatibility with existing frontend
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
  confidence_scores?: ConfidenceScores;
  letter_type: string;
  hospital_trust: string;
  is_sensitive: boolean;
  preview_pages: string[];
  preview_image: string | null;
  structured: StructuredFields;
  clinical_specifics: ClinicalSpecifics;
  icd_codes: string[];
  medications_raw: Medication[];
  snomed: SNOMEDData;
  summaries: Summaries;
  actions_structured: ActionsStructured;
  follow_up_actions: string;
  phi_entity_count: number;
  medical_ner?: MedicalNERResult;
  abbreviations?: AbbreviationResult;
  parsed_investigations?: ParsedInvestigation[];
  vital_signs?: VitalSign[];
  parsed_document?: ParsedDocument;
  nhs_document_data?: NHSDocumentData;
  event_date?: string;
  letter_date?: string;
  conclusion?: string;
  recommendation?: string;
  diary_events?: DiaryEvent[];
  treatments?: TreatmentItem[];
}

// ────────────────────────────────────────────────────────────────────────────────
// LEGACY TYPES (Preserved for backward compatibility)
// ────────────────────────────────────────────────────────────────────────────────

export interface SNOMEDEntity {
  text: string;
  category: string;
  snomed_code: string;
  description: string;
  confidence: number;
  entity_id: string;
  source: string;
  clinical_category?: string;
  result?: string;
  priority?: string;
  snomed_description?: string;
  assertion?: AssertionStatus;
  assertion_trigger?: string | null;
  assertion_confidence?: number;
  temporal_state?: TemporalStatus;
  temporal_trigger?: string | null;
  temporal_confidence?: number;
  clinical_temporal_category?: ClinicalTemporalCategory;
  time_reference?: string;
  concept_type?: SNOMEDConceptType;
  spell_corrected?: boolean;
  synonym_matched?: boolean;
  mapping_rejected?: boolean;
  rejection_reason?: string;
  canonical_form?: string;
  aliases?: string[];
  snomed_codes_all?: string[];
}

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

export interface TemporalStats {
  current: number;
  historical: number;
  resolved: number;
  suspected: number;
  chronic: number;
  acute: number;
}

export interface RejectedEntity extends SNOMEDEntity {
  validation_rejected: true;
  rejection_reason: string;
}

export interface SNOMEDData {
  problems: SNOMEDEntity[];
  treatments: SNOMEDEntity[];
  medications: SNOMEDEntity[];
  investigations: SNOMEDEntity[];
  diagnoses: SNOMEDEntity[];
  all_entities: SNOMEDEntity[];
  used_fallback: boolean;
  top3_fallback: SNOMEDEntity[];
  used_summary_fallback?: boolean;
  used_doctype_fallback?: boolean;
  snomed_confidence?: number;
  negated_entities?: SNOMEDEntity[];
  temporal_stats?: TemporalStats;
  validation_rejected?: RejectedEntity[];
}

export interface StructuredMedicationData {
  drug_name: string | null;
  strength: string | null;
  dose: string | null;
  route: string | null;
  frequency: string | null;
  frequency_code: string | null;
  duration: string | null;
  status: MedicationStatus;
  form: string | null;
  instructions: string | null;
  confidence: number;
}

export interface Medication {
  name: string;
  dose: string;
  raw: string;
  structured?: StructuredMedicationData;
}

export interface ParsedInvestigation {
  investigation: string;
  investigation_abbrev: string | null;
  finding: string | null;
  finding_status: 'normal' | 'abnormal' | 'pending' | 'not_done' | 'unknown';
  category: InvestigationCategory;
  raw_text: string;
  confidence: number;
}

export interface VitalSign {
  vital_type: VitalType;
  value: string;
  numeric_value: number | null;
  unit: string;
  timestamp: string | null;
  status: VitalStatus;
  raw_text: string;
  confidence: number;
  systolic?: number;
  diastolic?: number;
  gcs_eye?: number;
  gcs_verbal?: number;
  gcs_motor?: number;
}

export interface DocumentSection {
  section_type: ClinicalSection;
  heading: string;
  start_line: number;
  end_line: number;
  content: string;
  confidence: number;
}

export interface ParsedDocument {
  sections: DocumentSection[];
  section_order: ClinicalSection[];
  document_type: string | null;
  stats: Record<string, number>;
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

export interface ResolvedAbbreviation {
  abbreviation: string;
  expansion: string;
  category: string;
  position: number;
}

export interface AbbreviationResult {
  resolved: ResolvedAbbreviation[];
  stats: Record<string, number>;
}

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
  assertion?: AssertionStatus;
  assertion_trigger?: string | null;
  assertion_confidence?: number;
  temporal_state?: TemporalStatus;
  temporal_trigger?: string | null;
  temporal_confidence?: number;
  clinical_temporal_category?: ClinicalTemporalCategory;
  time_reference?: string;
}

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

// NHS Document types
export type NHSDocumentTypeEnum =
  | 'ed_discharge'
  | 'clinic_letter'
  | 'radiology'
  | 'histopathology'
  | 'operative_notes'
  | 'referral_letter'
  | 'gp_letter'
  | 'mental_health'
  | 'discharge_summary'
  | 'unknown';

export interface NHSExtractedSection {
  name: string;
  content: string;
  confidence: number;
}

export interface EDDischargeData {
  triage_category?: string;
  arrival_time?: string;
  departure_time?: string;
  presenting_complaint?: string;
  ed_diagnosis?: string;
  disposition?: string;
}

export interface RadiologyData {
  examination_type?: string;
  clinical_indication?: string;
  technique?: string;
  findings?: string;
  impression?: string;
  comparison?: string;
}

export interface HistopathologyData {
  specimen_type?: string;
  specimen_site?: string;
  macroscopy?: string;
  microscopy?: string;
  diagnosis?: string;
  grade?: string;
  stage?: string;
  margins?: string;
}

export interface OperativeData {
  operation_name?: string;
  surgeon?: string;
  anaesthetist?: string;
  anaesthesia_type?: string;
  indication?: string;
  operative_findings?: string;
  procedure_details?: string;
  blood_loss?: string;
  complications?: string;
  post_op_instructions?: string;
}

export interface MentalHealthData {
  mental_state?: string;
  risk_assessment?: string;
  mha_status?: string;
  capacity_assessment?: string;
  care_plan?: string;
}

export interface DischargeSummaryData {
  admission_date?: string;
  discharge_date?: string;
  admission_reason?: string;
  inpatient_course?: string;
  discharge_diagnosis?: string;
  discharge_medications?: string[];
  follow_up_plan?: string;
  gp_actions?: string[];
}

export interface NHSDocumentData {
  document_type: NHSDocumentTypeEnum;
  document_type_name: string;
  document_type_confidence: number;
  date?: string;
  author?: string;
  recipient?: string;
  signals_matched: string[];
  sections: NHSExtractedSection[];
  ed_specific?: EDDischargeData;
  radiology_specific?: RadiologyData;
  histopathology_specific?: HistopathologyData;
  operative_specific?: OperativeData;
  mental_health_specific?: MentalHealthData;
  discharge_specific?: DischargeSummaryData;
}

// ────────────────────────────────────────────────────────────────────────────────
// UI TYPES
// ────────────────────────────────────────────────────────────────────────────────

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
