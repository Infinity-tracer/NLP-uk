export type ProcessingStatus = 'queued' | 'processing' | 'completed' | 'failed' | 'review_required' | 'success' | 'review';

export interface TierStatus {
  tier: string;
  status: ProcessingStatus | string;
  duration_ms?: number;
  confidence?: number;
  error?: string;
  output_path?: string;
}

export interface PipelineJobResponse {
  job_id: string;
  status: ProcessingStatus;
  message: string;
}

export interface PipelineStatusResponse {
  job_id: string;
  status: ProcessingStatus;
  current_tier?: string;
  progress_percent: number;
  tiers: TierStatus[];
  error?: string;
}

export interface Tier0Response {
  status: string;
  total_pages: number;
  preprocessed_images: string[];
  failed_pages: any[];
  processing_time_ms: number;
}

export interface Tier1Response {
  status: string;
  pages_processed: number;
  output_files: string[];
  average_confidence?: number;
  processing_time_ms: number;
}

export interface TrackAResponse {
  status: string;
  entities: {
    text: string;
    category: string;
    type: string;
    score: number;
  }[];
  snomed_codes: {
    code: string;
    description: string;
    score: number;
    source_text: string;
  }[];
  processing_time_ms: number;
}

export interface TrackBResponse {
  status: string;
  summary: string;
  key_findings: string[];
  action_plans: {
    clinician?: string[];
    patient?: string[];
    pharmacist?: string[];
  };
  processing_time_ms: number;
}

export interface PipelineResultResponse {
  job_id: string;
  status: ProcessingStatus;
  document_name: string;
  total_processing_time_ms: number;
  tier0?: Tier0Response;
  tier1?: Tier1Response;
  tier2?: any;
  tier3?: any;
  track_a?: TrackAResponse;
  track_b?: TrackBResponse;
  audit_trail: any[];
}

export interface HealthResponse {
  status: string;
  version: string;
  timestamp: string;
  dependencies: Record<string, string>;
}
