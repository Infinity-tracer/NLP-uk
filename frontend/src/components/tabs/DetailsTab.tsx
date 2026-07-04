import { useState } from 'react';
import type { ProcessResult } from '../../api/types';
import { LETTER_TYPE_BUCKETS } from '../../api/types';

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
  const summary = result.summaries?.clinician?.summary || 'Not available';
  const predictedBucket = mapLetterTypeToBucket(result.letter_type || '');

  const [selectedBucket, setSelectedBucket] = useState(predictedBucket);
  const [eventDate, setEventDate] = useState(result.structured?.admission_date || '');
  const [letterDate, setLetterDate] = useState(result.structured?.discharge_date || result.structured?.appointment_date || '');
  const [sender, setSender] = useState(result.structured?.admission_method || '');
  const [consultant, setConsultant] = useState(result.structured?.consultant || '');
  const [department, setDepartment] = useState(result.structured?.department || '');
  const [conclusion, setConclusion] = useState(result.structured?.diagnosis_text || result.structured?.indication || result.structured?.impression || '');

  const isOverride = selectedBucket !== predictedBucket;

  return (
    <div className="space-y-4">
      {/* Summary */}
      <div>
        <label className="field-label">Summary</label>
        <div className="summary-box relative">
          <button
            className="absolute top-2 right-2 text-gray-400 hover:text-gray-600"
            onClick={() => navigator.clipboard.writeText(summary)}
            title="Copy"
          >
            📋
          </button>
          {summary}
        </div>
      </div>

      {/* Letter Type */}
      <div>
        <div className="flex items-center gap-2 mb-1">
          <label className="field-label mb-0">Letter type</label>
          {!isOverride && predictedBucket && (
            <span className="text-[10px] font-bold tracking-wide bg-green-100 text-green-700 border border-green-200 px-2 py-0.5 rounded-full">
              Auto-detected
            </span>
          )}
          {isOverride && (
            <span className="text-[10px] font-bold tracking-wide bg-yellow-100 text-yellow-700 border border-yellow-200 px-2 py-0.5 rounded-full">
              Manual override
            </span>
          )}
        </div>
        {predictedBucket && (
          <div className="text-xs text-gray-500 mb-1.5">
            Predicted as <strong className="text-nhs-dark">{result.letter_type}</strong>
            {isOverride && (
              <button
                onClick={() => setSelectedBucket(predictedBucket)}
                className="ml-2 text-nhs-blue hover:underline"
              >
                Reset to prediction
              </button>
            )}
          </div>
        )}
        <select
          value={selectedBucket}
          onChange={(e) => setSelectedBucket(e.target.value)}
          className="field-input cursor-pointer"
        >
          <option value="">Select letter type...</option>
          {LETTER_TYPE_BUCKETS.map((bucket) => (
            <option key={bucket.key} value={bucket.label}>
              {bucket.label}
            </option>
          ))}
        </select>
        <p className="text-[10px] text-gray-400 mt-1">
          Dropdown is a fallback override if the prediction is wrong.
        </p>
      </div>

      {/* Date fields */}
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

      {/* Sender */}
      <div>
        <label className="field-label">Sender Name</label>
        <input
          type="text"
          value={sender}
          onChange={(e) => setSender(e.target.value)}
          className="field-input"
        />
      </div>

      {/* Consultant */}
      <div>
        <label className="field-label">Consultant Name</label>
        <input
          type="text"
          value={consultant}
          onChange={(e) => setConsultant(e.target.value)}
          className="field-input"
        />
      </div>

      {/* Department */}
      <div>
        <label className="field-label">Department</label>
        <input
          type="text"
          value={department}
          onChange={(e) => setDepartment(e.target.value)}
          className="field-input"
        />
      </div>

      {/* Conclusion */}
      <div>
        <label className="field-label">Conclusion</label>
        <textarea
          value={conclusion}
          onChange={(e) => setConclusion(e.target.value)}
          placeholder="None"
          rows={3}
          className="field-input resize-y"
        />
      </div>
    </div>
  );
}
