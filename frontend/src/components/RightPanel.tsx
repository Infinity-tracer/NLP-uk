import type { ProcessResult } from '../api/types';

interface RightPanelProps {
  result: ProcessResult;
}

const CLINICAL_SPECIFICS_LABELS: Record<string, string> = {
  differential_diagnosis: 'Differential Dx',
  urgency: 'Urgency',
  encounter_type: 'Encounter Type',
  assessing_clinician: 'Assessing Clinician',
  tnm_staging: 'TNM Staging',
  cea_value: 'CEA',
  cd4_count: 'CD4 Count',
  viral_load: 'Viral Load',
  art_regimen: 'ART Regimen',
  ogtt_results: 'OGTT Results',
  edd: 'EDD',
  gestational_age: 'Gestational Age',
  gravida_parity: 'G/P Status',
  visual_acuity: 'Visual Acuity',
  iop: 'IOP',
  news2_score: 'NEWS2 Score',
  admission_date: 'Admission Date',
  discharge_date: 'Discharge Date',
  presenting_complaint: 'Presenting Complaint',
  referral_reason: 'Referral Reason',
  provider: 'Provider',
};

export default function RightPanel({ result }: RightPanelProps) {
  const pt = result.patient_info || {};
  const specs = result.clinical_specifics || {};
  const stages = result.pipeline_stages || {};
  const threshold = result.confidence_threshold || 0.75;
  const confPercent = Math.round((result.unified_confidence || 0) * 100);

  const statusBadge = result.unified_confidence >= threshold ? (
    <span className="badge badge-processed">✅ High Confidence ({confPercent}%)</span>
  ) : (
    <span className="badge badge-review">⚠️ Review Required ({confPercent}%)</span>
  );

  const formatDate = (iso: string) => {
    try {
      return new Date(iso).toLocaleString('en-GB');
    } catch {
      return iso;
    }
  };

  return (
    <div className="w-[280px] bg-white overflow-y-auto">
      {/* Patient Info */}
      <section className="border-b border-gray-200 p-4">
        <h4 className="text-xs font-bold text-gray-500 uppercase tracking-wide mb-3">Patient Info</h4>
        <div className="info-row">
          <span className="info-label">Patient Name</span>
          <span className="info-value">{pt.name || '—'}</span>
        </div>
        <div className="info-row">
          <span className="info-label">NHS Number</span>
          <span className="info-value">{pt.nhs_number || '—'}</span>
        </div>
        <div className="info-row">
          <span className="info-label">Date of Birth</span>
          <span className="info-value">{pt.dob || '—'}</span>
        </div>
        <div className="info-row">
          <span className="info-label">Sex</span>
          <span className="info-value">{pt.sex || '—'}</span>
        </div>
        {pt.gravida_parity && (
          <div className="info-row">
            <span className="info-label">G/P</span>
            <span className="info-value">{pt.gravida_parity}</span>
          </div>
        )}
        {pt.edd && (
          <div className="info-row">
            <span className="info-label">EDD</span>
            <span className="info-value">{pt.edd}</span>
          </div>
        )}
        {pt.gestational_age && (
          <div className="info-row">
            <span className="info-label">Gest. Age</span>
            <span className="info-value">{pt.gestational_age}</span>
          </div>
        )}
      </section>

      {/* Document Info */}
      <section className="border-b border-gray-200 p-4">
        <h4 className="text-xs font-bold text-gray-500 uppercase tracking-wide mb-3">Document Info</h4>
        <div className="info-row">
          <span className="info-label">Name</span>
          <span className="info-value break-all">{result.filename || '—'}</span>
        </div>
        <div className="info-row">
          <span className="info-label">Letter Type</span>
          <span className="info-value">{result.letter_type || '—'}</span>
        </div>
        <div className="info-row">
          <span className="info-label">Hospital Name</span>
          <span className="info-value text-xs">{result.hospital_trust || '—'}</span>
        </div>
        <div className="info-row">
          <span className="info-label">Status</span>
          <div>{statusBadge}</div>
        </div>
        <div className="info-row">
          <span className="info-label">Confidence</span>
          <span className="info-value">
            {confPercent}% (threshold {Math.round(threshold * 100)}%)
          </span>
        </div>
        <div className="info-row">
          <span className="info-label">Created Date</span>
          <span className="info-value">{formatDate(result.processed_at)}</span>
        </div>
        {result.is_sensitive && (
          <div className="info-row">
            <span className="info-label">⚠️ Sensitivity</span>
            <span className="info-value text-yellow-700 text-xs font-semibold">
              Safeguarding/Sensitive — patient summary filtered
            </span>
          </div>
        )}
      </section>

      {/* Clinical Specifics */}
      {Object.keys(specs).length > 0 && (
        <section className="border-b border-gray-200 p-4">
          <h4 className="text-xs font-bold text-gray-500 uppercase tracking-wide mb-3">Clinical Specifics</h4>
          {Object.entries(specs).map(([key, value]) => {
            const label = CLINICAL_SPECIFICS_LABELS[key] || key.replace(/_/g, ' ');
            const displayValue = typeof value === 'object'
              ? Object.entries(value).map(([k, v]) => `${k}: ${v}`).join(' | ')
              : String(value);
            return (
              <div key={key} className="info-row">
                <span className="info-label">{label}</span>
                <span className="info-value break-words">{displayValue}</span>
              </div>
            );
          })}
        </section>
      )}

      {/* Pipeline Stages */}
      <section className="p-4">
        <h4 className="text-xs font-bold text-gray-500 uppercase tracking-wide mb-3">Pipeline Stages</h4>
        {Object.entries(stages).map(([key, stage]) => {
          if (!stage) return null;
          const color = stage.status === 'done' ? 'text-green-600' :
                        stage.status === 'partial' ? 'text-yellow-600' :
                        stage.status === 'error' ? 'text-red-600' :
                        'text-gray-500';
          const confText = stage.confidence != null ? ` (${Math.round(stage.confidence * 100)}%)` : '';
          return (
            <div key={key} className="py-1 border-b border-gray-100 last:border-0">
              <div className="flex justify-between text-xs">
                <span className="font-semibold">{key}</span>
                <span className={color}>{stage.status}{confText}</span>
              </div>
              {stage.error && (
                <div className="text-xs text-red-600 mt-0.5 break-words">{stage.error}</div>
              )}
            </div>
          );
        })}
      </section>
    </div>
  );
}
