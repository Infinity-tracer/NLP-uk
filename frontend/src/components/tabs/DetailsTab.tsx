import { useState } from 'react';
import type { ProcessResult } from '../../api/types';
import { LETTER_TYPE_BUCKETS } from '../../api/types';
import CollapsibleSection from '../CollapsibleSection';

interface DetailsTabProps {
  result: ProcessResult;
}

function mapLetterTypeToBucket(letterType: string): string {
  const type = letterType.toLowerCase();

  if (type.includes('discharge summary') || type.includes('mental health inpatient') || type.includes('antenatal discharge') || type.includes('camhs')) {
    return 'Hospital Discharge Summary (after admission into hospital)';
  }
  if (type.includes('ed discharge')) return 'Accident & Emergency Department report';
  if (type.includes('111')) return '111 Report (seeking advice from Clinician over phone)';
  if (type.includes('ambulance')) return 'Ambulance Report (When emergency services are called)';
  if (type.includes('ophthalmology referral')) return 'External service providers (Boots, Spec savers – for Eye & ENT)';
  if (type.includes('ophthalmology letter')) return 'Diabetic eye screening reports';
  if (type.includes('prescriber') || type.includes('medication')) return 'Private Specialists clinical letter';

  if (type.includes('referral') || type.includes('outpatient') || type.includes('clinical') ||
      type.includes('cancer') || type.includes('hiv') || type.includes('maternity') ||
      type.includes('surgical') || type.includes('procedure') || type.includes('psychiatry') ||
      type.includes('renal') || type.includes('paediatric') || type.includes('pregnancy') ||
      type.includes('pre-admission') || type.includes('haematology')) {
    return 'Clinical Letters/Report (after visiting specialists)';
  }

  return 'Miscellaneous';
}

export default function DetailsTab({ result }: DetailsTabProps) {
  const bulletSummary = result.summaries?.bullet_summary;
  const clinicianSummary = result.summaries?.clinician_summary || result.summaries?.clinician?.summary;
  const hasBulletSummary = Array.isArray(bulletSummary) && bulletSummary.length > 0;
  const summary = hasBulletSummary ? bulletSummary.join('\n') : (clinicianSummary || 'Not available');
  const predictedRaw = result.letter_type || '';
  const predictedBucket = mapLetterTypeToBucket(predictedRaw);

  const [selectedValue, setSelectedValue] = useState(predictedRaw || predictedBucket);
  const [eventDate, setEventDate] = useState(result.event_date || result.structured?.admission_date || '');
  const [letterDate, setLetterDate] = useState(result.letter_date || result.structured?.discharge_date || result.structured?.appointment_date || '');
  const [sender, setSender] = useState(result.hospital_trust || result.structured?.hospital || result.structured?.admission_method || '');
  const [consultant, setConsultant] = useState(result.structured?.consultant || '');
  const [department, setDepartment] = useState(result.structured?.department || '');
  const [conclusion, setConclusion] = useState(result.conclusion || result.structured?.diagnosis_text || result.structured?.indication || result.structured?.impression || '');

  const isOverride = selectedValue !== predictedRaw && selectedValue !== predictedBucket;

  return (
    <div className="space-y-3">
      {/* Summary - Collapsible */}
      <CollapsibleSection title="Summary" icon="📋" defaultOpen={true}>
        <div className="summary-box relative">
          <button
            className="absolute top-2 right-2 text-gray-400 hover:text-gray-600 transition-colors"
            onClick={() => navigator.clipboard.writeText(summary)}
            title="Copy"
          >
            📋
          </button>
          {hasBulletSummary ? (
            <ul className="space-y-1.5">
              {bulletSummary.map((line, i) => (
                <li key={i} className="text-sm flex items-start gap-2">
                  <span className="text-[#1977cc] font-bold">•</span>
                  <span>{line}</span>
                </li>
              ))}
            </ul>
          ) : summary.includes('- ') ? (
            <ul className="list-disc list-inside space-y-1">
              {summary.split('\n').filter(line => line.trim()).map((line, i) => (
                <li key={i} className="text-sm">
                  {line.replace(/^-\s*/, '')}
                </li>
              ))}
            </ul>
          ) : (
            <span style={{ whiteSpace: 'pre-line' }}>{summary}</span>
          )}
        </div>
      </CollapsibleSection>

      {/* Letter Type - Collapsible */}
      <CollapsibleSection
        title="Letter Type"
        icon="📑"
        defaultOpen={true}
        badge={
          !isOverride && predictedRaw ? (
            <span className="text-[10px] font-bold tracking-wide bg-[#059652]/10 text-[#059652] border border-[#059652]/20 px-2 py-0.5 rounded-full ml-2">
              Auto-detected
            </span>
          ) : isOverride ? (
            <span className="text-[10px] font-bold tracking-wide bg-[#ffc107]/10 text-[#b38600] border border-[#ffc107]/30 px-2 py-0.5 rounded-full ml-2">
              Manual override
            </span>
          ) : null
        }
      >
        <div>
          {isOverride && predictedRaw && (
            <button
              onClick={() => setSelectedValue(predictedRaw)}
              className="text-xs text-[#1977cc] hover:underline mb-2 block"
            >
              Reset to auto-detected
            </button>
          )}
          <select
            value={selectedValue}
            onChange={(e) => setSelectedValue(e.target.value)}
            className="field-input cursor-pointer"
          >
            {predictedRaw && (
              <option value={predictedRaw}>{predictedRaw}</option>
            )}
            <option value="" disabled>── Or select category ──</option>
            {LETTER_TYPE_BUCKETS.map((bucket) => (
              <option key={bucket.key} value={bucket.label}>
                {bucket.label}
              </option>
            ))}
          </select>
          <p className="text-[10px] text-gray-400 mt-1.5">
            Change if needed.
          </p>
        </div>
      </CollapsibleSection>

      {/* Dates - Collapsible */}
      <CollapsibleSection title="Dates" icon="📅" defaultOpen={true}>
        <div className="flex gap-3">
          <div className="flex-1">
            <label className="field-label">Event Date</label>
            <input
              type="text"
              value={eventDate}
              onChange={(e) => setEventDate(e.target.value)}
              placeholder="DD/MM/YYYY"
              className="field-input"
            />
          </div>
          <div className="flex-1">
            <label className="field-label">Letter Date</label>
            <input
              type="text"
              value={letterDate}
              onChange={(e) => setLetterDate(e.target.value)}
              placeholder="DD/MM/YYYY"
              className="field-input"
            />
          </div>
        </div>
      </CollapsibleSection>

      {/* Sender & Consultant - Collapsible */}
      <CollapsibleSection title="Sender Details" icon="🏥" defaultOpen={true}>
        <div className="space-y-3">
          <div>
            <label className="field-label">Sender Name</label>
            <input
              type="text"
              value={sender}
              onChange={(e) => setSender(e.target.value)}
              className="field-input"
            />
          </div>
          <div>
            <label className="field-label">Consultant Name</label>
            <input
              type="text"
              value={consultant}
              onChange={(e) => setConsultant(e.target.value)}
              className="field-input"
            />
          </div>
          <div>
            <label className="field-label">Department</label>
            <input
              type="text"
              value={department}
              onChange={(e) => setDepartment(e.target.value)}
              className="field-input"
            />
          </div>
        </div>
      </CollapsibleSection>

      {/* Conclusion - Collapsible */}
      <CollapsibleSection title="Conclusion" icon="✅" defaultOpen={true}>
        <textarea
          value={conclusion}
          onChange={(e) => setConclusion(e.target.value)}
          placeholder="None"
          rows={3}
          className="field-input resize-y"
        />
      </CollapsibleSection>
    </div>
  );
}
