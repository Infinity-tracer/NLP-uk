import type { ProcessResult } from '../api/types';
import CollapsibleSection from './CollapsibleSection';

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
    <span className="badge badge-processed">High Confidence ({confPercent}%)</span>
  ) : (
    <span className="badge badge-review">Review Required ({confPercent}%)</span>
  );

  const formatDate = (iso: string) => {
    try {
      return new Date(iso).toLocaleString('en-GB');
    } catch {
      return iso;
    }
  };

  return (
    <div className="w-[300px] bg-gray-50/30 overflow-y-auto p-3">
      {/* Patient Info - Collapsible */}
      <CollapsibleSection title="Patient Info" icon="👤" defaultOpen={true}>
        <div className="space-y-3">
          <div className="info-row">
            <span className="info-label">Patient Name</span>
            <span className="info-value">{pt.name || '—'}</span>
          </div>
          <div className="info-row">
            <span className="info-label">NHS Number</span>
            <span className="info-value font-mono">{pt.nhs_number || '—'}</span>
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
        </div>
      </CollapsibleSection>

      {/* Document Info - Collapsible */}
      <CollapsibleSection title="Document Info" icon="📄" defaultOpen={true}>
        <div className="space-y-3">
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
            <div className="mt-1">{statusBadge}</div>
          </div>
          <div className="info-row">
            <span className="info-label">Confidence</span>
            <div className="mt-1">
              <div className="conf-bar-wrap w-full">
                <div
                  className={`conf-bar ${confPercent >= 75 ? 'conf-high' : confPercent >= 50 ? 'conf-mid' : 'conf-low'}`}
                  style={{ width: `${confPercent}%` }}
                />
              </div>
              <span className="text-xs text-[#444444] mt-1 block">
                {confPercent}% (threshold {Math.round(threshold * 100)}%)
              </span>
            </div>
          </div>
          <div className="info-row">
            <span className="info-label">Created Date</span>
            <span className="info-value">{formatDate(result.processed_at)}</span>
          </div>
          {result.is_sensitive && (
            <div className="info-row">
              <span className="info-label">Sensitivity</span>
              <span className="text-xs font-semibold text-[#b38600] bg-[#ffc107]/10 px-2 py-1 rounded">
                Safeguarding/Sensitive — patient summary filtered
              </span>
            </div>
          )}
        </div>
      </CollapsibleSection>

      {/* Clinical Specifics - Collapsible */}
      {Object.keys(specs).length > 0 && (
        <CollapsibleSection title="Clinical Specifics" icon="🏥" defaultOpen={false}>
          <div className="space-y-3">
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
          </div>
        </CollapsibleSection>
      )}

      {/* Pipeline Stages - Collapsible */}
      <CollapsibleSection title="Pipeline Stages" icon="⚙️" defaultOpen={false}>
        <div className="space-y-2">
          {Object.entries(stages).map(([key, stage]) => {
            if (!stage) return null;
            const bgColor = stage.status === 'done' ? 'bg-[#059652]/5 border-[#059652]/20' :
                          stage.status === 'partial' ? 'bg-[#ffc107]/5 border-[#ffc107]/30' :
                          stage.status === 'error' ? 'bg-[#df1529]/5 border-[#df1529]/20' :
                          'bg-gray-50 border-gray-200';
            const textColor = stage.status === 'done' ? 'text-[#059652]' :
                          stage.status === 'partial' ? 'text-[#b38600]' :
                          stage.status === 'error' ? 'text-[#df1529]' :
                          'text-[#768692]';
            const confText = stage.confidence != null ? ` (${Math.round(stage.confidence * 100)}%)` : '';
            return (
              <div key={key} className={`p-2.5 rounded-lg border ${bgColor}`}>
                <div className="flex justify-between text-xs">
                  <span className="font-semibold text-[#2c4964]">{key}</span>
                  <span className={`font-medium ${textColor}`}>{stage.status}{confText}</span>
                </div>
                {stage.error && (
                  <div className="text-xs text-[#df1529] mt-1.5 break-words">{stage.error}</div>
                )}
              </div>
            );
          })}
        </div>
      </CollapsibleSection>
    </div>
  );
}
