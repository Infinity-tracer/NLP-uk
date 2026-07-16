import { useState } from 'react';
import type { ProcessResult, SNOMEDEntity } from '../../api/types';

interface CodingTabProps {
  result: ProcessResult;
}

// 5 clinical categories as specified
type ClinicalCategory = 'problems' | 'treatments' | 'medications' | 'investigations' | 'diagnoses';

const CATEGORY_CONFIG: Record<ClinicalCategory, {
  label: string;
  icon: string;
  description: string;
  border: string;
  bg: string;
  text: string;
  headerBg: string;
}> = {
  problems: {
    label: 'Problems / Issues',
    icon: '🩺',
    description: 'Symptoms and findings (e.g., neck pain, tummy irritation)',
    border: 'border-orange-500',
    bg: 'bg-orange-50',
    text: 'text-orange-700',
    headerBg: 'bg-orange-100',
  },
  treatments: {
    label: 'Treatment',
    icon: '💉',
    description: 'Therapeutic procedures (e.g., Mental Health treatment, Chemo)',
    border: 'border-purple-500',
    bg: 'bg-purple-50',
    text: 'text-purple-700',
    headerBg: 'bg-purple-100',
  },
  medications: {
    label: 'Medication',
    icon: '💊',
    description: 'Drugs and substances (e.g., Thyroxine, Aspirin)',
    border: 'border-blue-500',
    bg: 'bg-blue-50',
    text: 'text-blue-700',
    headerBg: 'bg-blue-100',
  },
  investigations: {
    label: 'Investigation',
    icon: '🔬',
    description: 'Diagnostic tests (e.g., CT Scan, MRI, Smear, Angio)',
    border: 'border-teal-500',
    bg: 'bg-teal-50',
    text: 'text-teal-700',
    headerBg: 'bg-teal-100',
  },
  diagnoses: {
    label: 'Diagnosis',
    icon: '📋',
    description: 'Confirmed conditions (e.g., ulcerative colitis)',
    border: 'border-red-500',
    bg: 'bg-red-50',
    text: 'text-red-700',
    headerBg: 'bg-red-100',
  },
};

function SNOMEDCard({ entity, category }: { entity: SNOMEDEntity; category: ClinicalCategory }) {
  const config = CATEGORY_CONFIG[category];
  const confPercent = Math.round((entity.confidence || 0) * 100);
  const confColor = confPercent >= 80 ? 'text-green-600' : confPercent >= 60 ? 'text-yellow-600' : 'text-orange-600';

  return (
    <div className={`border ${config.border} border-l-4 rounded-lg p-3 mb-2 ${config.bg}`}>
      <div className="flex justify-between items-start gap-2">
        <div className="flex-1">
          <span className="font-bold text-gray-800">{entity.text}</span>
          {entity.snomed_code && (
            <code className="ml-2 bg-white/70 text-nhs-blue px-1.5 py-0.5 rounded font-mono font-bold text-xs">
              {entity.snomed_code}
            </code>
          )}
        </div>
        <span className={`text-xs font-bold ${confColor}`}>{confPercent}%</span>
      </div>
      {entity.description && (
        <div className="text-xs text-gray-600 mt-1 italic">
          {entity.description}
        </div>
      )}
    </div>
  );
}

function CategorySection({
  category,
  entities
}: {
  category: ClinicalCategory;
  entities: SNOMEDEntity[];
}) {
  const config = CATEGORY_CONFIG[category];
  const [expanded, setExpanded] = useState(true);

  return (
    <div className="border border-gray-200 rounded-lg overflow-hidden mb-3">
      <button
        onClick={() => setExpanded(!expanded)}
        className={`w-full px-3 py-2 flex items-center justify-between ${config.headerBg} border-b border-gray-200`}
      >
        <div className="flex items-center gap-2">
          <span>{config.icon}</span>
          <span className={`font-bold text-sm ${config.text}`}>{config.label}</span>
          <span className="bg-white/70 text-gray-600 text-xs px-2 py-0.5 rounded-full font-semibold">
            {entities.length}
          </span>
        </div>
        <span className="text-gray-400">{expanded ? '▾' : '▸'}</span>
      </button>

      {expanded && (
        <div className="p-3">
          {entities.length > 0 ? (
            entities.map((entity, i) => (
              <SNOMEDCard key={entity.entity_id || i} entity={entity} category={category} />
            ))
          ) : (
            <div className="text-sm text-gray-400 italic">
              No {config.label.toLowerCase()} identified
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function CodingTab({ result }: CodingTabProps) {
  const [showTable, setShowTable] = useState(false);

  // Get 5 categories from SNOMED data
  const problems = result.snomed?.problems || [];
  const treatments = result.snomed?.treatments || [];
  const medications = result.snomed?.medications || [];
  const investigations = result.snomed?.investigations || [];
  const diagnoses = result.snomed?.diagnoses || [];

  const icdCodes = result.icd_codes || [];
  const medsRaw = result.medications_raw || [];

  const allEntities = [...diagnoses, ...problems, ...treatments, ...medications, ...investigations];
  const totalEntities = allEntities.length;

  // Primary diagnosis/problem for the main card
  const activeProblem = diagnoses[0] || problems[0] || null;

  const confPercent = Math.round((result.unified_confidence || 0) * 100);
  const threshold = result.confidence_threshold || 0.75;
  const thresholdPercent = Math.round(threshold * 100);
  const confClass = result.unified_confidence >= threshold ? 'conf-high' :
                    result.unified_confidence >= threshold * 0.75 ? 'conf-mid' : 'conf-low';

  const snomedConfidence = result.snomed?.snomed_confidence
    ? Math.round(result.snomed.snomed_confidence * 100)
    : 0;

  return (
    <div className="space-y-4">
      {/* Header with SNOMED confidence */}
      <div className="flex items-center justify-between">
        <div>
          <span className="field-label mb-0">Clinical Coding (SNOMED CT)</span>
          <div className="text-xs text-gray-500 mt-0.5">
            {totalEntities} entities extracted • {snomedConfidence}% SNOMED confidence
          </div>
        </div>
        <div className="flex items-center gap-2 text-gray-400">
          <span className="cursor-pointer hover:text-nhs-blue" title="History">🕐</span>
          <span className="cursor-pointer hover:text-nhs-blue" title="Refresh">↻</span>
        </div>
      </div>

      {/* Active Problem/Diagnosis Card */}
      {activeProblem && (
        <div className="border border-gray-200 border-l-4 border-l-red-500 rounded-lg p-3 bg-white">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-bold text-gray-800">{activeProblem.text}</span>
            <span className="text-[10px] font-bold uppercase tracking-wide bg-red-100 text-red-700 px-2 py-0.5 rounded-full">
              {diagnoses.includes(activeProblem) ? 'Diagnosis' : 'Problem'}
            </span>
            <span className="text-[10px] font-bold uppercase tracking-wide bg-green-100 text-green-700 px-2 py-0.5 rounded-full">Active</span>
          </div>
          {activeProblem.snomed_code && (
            <div className="text-xs font-mono font-semibold text-nhs-blue mt-1">
              SNOMED: {activeProblem.snomed_code}
            </div>
          )}
          {activeProblem.description && (
            <div className="text-xs text-gray-500 mt-1">
              {activeProblem.description}
            </div>
          )}
        </div>
      )}

      {/* 5 Clinical Categories */}
      <div className="space-y-2">
        <CategorySection category="diagnoses" entities={diagnoses} />
        <CategorySection category="problems" entities={problems} />
        <CategorySection category="treatments" entities={treatments} />
        <CategorySection category="medications" entities={medications} />
        <CategorySection category="investigations" entities={investigations} />
      </div>

      {totalEntities === 0 && (
        <div className="text-sm text-gray-400 italic p-4 bg-gray-50 rounded-lg">
          No SNOMED CT entities identified — check ICD codes or medication extraction below.
        </div>
      )}

      {/* Full SNOMED Table */}
      <div className="mt-4">
        <button
          onClick={() => setShowTable(!showTable)}
          className="text-xs font-bold text-gray-500 hover:text-nhs-blue flex items-center gap-1"
        >
          <span className="text-[10px]">{showTable ? '▾' : '▸'}</span>
          Full SNOMED CT mapping table
        </button>
        {showTable && (
          <div className="mt-2 border-2 border-nhs-blue rounded-lg overflow-hidden">
            <div className="bg-nhs-blue px-3 py-2 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span>🧬</span>
                <span className="text-white font-bold text-sm">SNOMED CT Mappings</span>
                <span className="bg-white/20 text-white text-xs px-2 py-0.5 rounded-full font-semibold">
                  {totalEntities} entities
                </span>
              </div>
            </div>
            <div className="bg-blue-50 px-3 py-1 text-xs text-gray-600 flex gap-3 border-b border-blue-200 flex-wrap">
              <span><span className="inline-block w-2.5 h-2.5 rounded bg-red-500 mr-1 align-middle" />Diagnosis</span>
              <span><span className="inline-block w-2.5 h-2.5 rounded bg-orange-500 mr-1 align-middle" />Problem</span>
              <span><span className="inline-block w-2.5 h-2.5 rounded bg-purple-500 mr-1 align-middle" />Treatment</span>
              <span><span className="inline-block w-2.5 h-2.5 rounded bg-blue-500 mr-1 align-middle" />Medication</span>
              <span><span className="inline-block w-2.5 h-2.5 rounded bg-teal-500 mr-1 align-middle" />Investigation</span>
            </div>
            <div className="max-h-64 overflow-y-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="bg-gray-50 sticky top-0">
                    <th className="px-2 py-1.5 text-left font-bold text-gray-700 border-b border-gray-200">Category</th>
                    <th className="px-2 py-1.5 text-left font-bold text-gray-700 border-b border-gray-200">Term</th>
                    <th className="px-2 py-1.5 text-left font-bold text-gray-700 border-b border-gray-200">SNOMED Code</th>
                    <th className="px-2 py-1.5 text-left font-bold text-gray-700 border-b border-gray-200">Description</th>
                    <th className="px-2 py-1.5 text-center font-bold text-gray-700 border-b border-gray-200">Conf.</th>
                  </tr>
                </thead>
                <tbody>
                  {allEntities.map((e, i) => {
                    const confPct = Math.round((e.confidence || 0) * 100);
                    const confColor = confPct >= 70 ? 'text-green-600' : confPct >= 45 ? 'text-yellow-600' : 'text-red-600';
                    const catKey = (e.clinical_category || 'problems') as ClinicalCategory;
                    const catConfig = CATEGORY_CONFIG[catKey] || CATEGORY_CONFIG.problems;
                    return (
                      <tr key={e.entity_id || i} className={i % 2 === 0 ? 'bg-white' : 'bg-gray-50'}>
                        <td className="px-2 py-1.5 border-b border-gray-100">
                          <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${catConfig.bg} ${catConfig.text}`}>
                            {catConfig.icon} {catConfig.label}
                          </span>
                        </td>
                        <td className="px-2 py-1.5 font-semibold text-gray-800 border-b border-gray-100">{e.text}</td>
                        <td className="px-2 py-1.5 border-b border-gray-100">
                          {e.snomed_code ? (
                            <code className="bg-blue-100 text-nhs-blue px-1.5 py-0.5 rounded font-mono font-bold text-[11px]">
                              {e.snomed_code}
                            </code>
                          ) : '—'}
                        </td>
                        <td className="px-2 py-1.5 text-gray-500 border-b border-gray-100 max-w-xs truncate" title={e.description}>
                          {e.description || '—'}
                        </td>
                        <td className={`px-2 py-1.5 text-center font-bold border-b border-gray-100 ${confColor}`}>
                          {confPct}%
                        </td>
                      </tr>
                    );
                  })}
                  {totalEntities === 0 && (
                    <tr>
                      <td colSpan={5} className="px-4 py-4 text-center text-gray-400 italic">
                        No SNOMED CT entities identified
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>

      {/* ICD Codes */}
      <div className="mt-4">
        <div className="field-label flex items-center gap-1">📋 ICD codes (local extraction)</div>
        <div className="flex flex-wrap gap-1 mt-1">
          {icdCodes.length > 0 ? (
            icdCodes.map((code, i) => (
              <span key={i} className="snomed-chip">
                <span className="snomed-code">{code}</span>
              </span>
            ))
          ) : (
            <span className="text-xs text-gray-400">None detected</span>
          )}
        </div>
      </div>

      {/* Medications (text extraction) */}
      <div className="mt-4">
        <div className="field-label flex items-center gap-1">💊 Medications (text extraction)</div>
        <div className="flex flex-wrap gap-1 mt-1">
          {medsRaw.length > 0 ? (
            medsRaw.map((m, i) => (
              <span key={i} className="snomed-chip" title={m.raw}>
                {m.name} <span className="snomed-code">{m.dose}</span>
              </span>
            ))
          ) : (
            <span className="text-xs text-gray-400">None detected</span>
          )}
        </div>
      </div>

      {/* Confidence bar */}
      <div className="mt-4">
        <div className="field-label">Unified confidence score</div>
        <div className="flex items-center gap-3 mt-1">
          <span className="text-xl font-bold text-nhs-blue">{confPercent}%</span>
          <div className="flex-1">
            <div className="conf-bar-wrap">
              <div className={`conf-bar ${confClass}`} style={{ width: `${Math.min(confPercent, 100)}%` }} />
            </div>
          </div>
        </div>
        <div className="text-xs text-gray-500 mt-1">
          Threshold: {thresholdPercent}% ({result.letter_type || 'default'}) | Textract + SNOMED + LLM weighted
        </div>
      </div>
    </div>
  );
}
