import { useState } from 'react';
import type { ProcessResult, SNOMEDEntity } from '../../api/types';

interface CodingTabProps {
  result: ProcessResult;
}

type SemanticType = 'disorder' | 'finding' | 'procedure' | 'situation' | 'event' | 'substance' | 'product' | 'other';

const SEMANTIC_COLORS: Record<SemanticType, { border: string; bg: string; text: string }> = {
  disorder: { border: 'border-red-500', bg: 'bg-red-50', text: 'text-red-700' },
  finding: { border: 'border-orange-500', bg: 'bg-orange-50', text: 'text-orange-700' },
  procedure: { border: 'border-blue-500', bg: 'bg-blue-50', text: 'text-blue-700' },
  situation: { border: 'border-purple-500', bg: 'bg-purple-50', text: 'text-purple-700' },
  event: { border: 'border-green-500', bg: 'bg-green-50', text: 'text-green-700' },
  substance: { border: 'border-blue-600', bg: 'bg-blue-50', text: 'text-blue-800' },
  product: { border: 'border-blue-600', bg: 'bg-blue-50', text: 'text-blue-800' },
  other: { border: 'border-gray-400', bg: 'bg-gray-50', text: 'text-gray-700' },
};

function getSemanticType(entity: SNOMEDEntity): SemanticType {
  const desc = (entity.description || '').toLowerCase();
  const match = desc.match(/\(([^()]+)\)\s*$/);
  if (match) {
    const tag = match[1].toLowerCase();
    if (tag.includes('disorder')) return 'disorder';
    if (tag.includes('finding') || tag.includes('observable')) return 'finding';
    if (tag.includes('procedure')) return 'procedure';
    if (tag.includes('situation')) return 'situation';
    if (tag.includes('event')) return 'event';
    if (tag.includes('substance')) return 'substance';
    if (tag.includes('product')) return 'product';
  }
  return 'other';
}

function getSemanticLabel(type: SemanticType): string {
  const labels: Record<SemanticType, string> = {
    disorder: 'Disorder',
    finding: 'Finding',
    procedure: 'Procedure',
    situation: 'Situation',
    event: 'Event',
    substance: 'Substance',
    product: 'Medication',
    other: 'Other',
  };
  return labels[type];
}

function groupBySemanticType(entities: SNOMEDEntity[]): Record<SemanticType, SNOMEDEntity[]> {
  const groups: Record<SemanticType, SNOMEDEntity[]> = {
    disorder: [], finding: [], procedure: [], situation: [], event: [], substance: [], product: [], other: []
  };
  for (const e of entities) {
    const type = getSemanticType(e);
    groups[type].push(e);
  }
  return groups;
}

export default function CodingTab({ result }: CodingTabProps) {
  const [showTable, setShowTable] = useState(false);

  const problems = result.snomed?.problems || [];
  const diagnoses = result.snomed?.diagnoses || [];
  const medications = result.snomed?.medications || [];
  const icdCodes = result.icd_codes || [];
  const medsRaw = result.medications_raw || [];

  const allEntities = [...diagnoses, ...problems, ...medications];
  const grouped = groupBySemanticType(allEntities);

  const activeProblem = diagnoses[0] || problems.find(e => getSemanticType(e) === 'disorder') || problems[0] || null;

  const confPercent = Math.round((result.unified_confidence || 0) * 100);
  const threshold = result.confidence_threshold || 0.75;
  const thresholdPercent = Math.round(threshold * 100);
  const confClass = result.unified_confidence >= threshold ? 'conf-high' :
                    result.unified_confidence >= threshold * 0.75 ? 'conf-mid' : 'conf-low';

  return (
    <div className="space-y-4">
      {/* Problems header */}
      <div className="flex items-center justify-between">
        <span className="field-label mb-0">Problems</span>
        <div className="flex items-center gap-2 text-gray-400">
          <span className="cursor-pointer hover:text-nhs-blue" title="History">🕐</span>
          <span className="cursor-pointer hover:text-nhs-blue" title="Refresh">↻</span>
        </div>
      </div>
      <div className="border border-gray-200 rounded-lg px-3 py-2 text-xs text-gray-500 bg-white">
        Add an existing or new problem
      </div>

      {/* Active Problem Card */}
      {activeProblem && (
        <div className="border border-gray-200 border-l-4 border-l-red-500 rounded-lg p-3 bg-white">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-bold text-gray-800">{activeProblem.text}</span>
            <span className="text-[10px] font-bold uppercase tracking-wide bg-red-100 text-red-700 px-2 py-0.5 rounded-full">Major</span>
            <span className="text-[10px] font-bold uppercase tracking-wide bg-green-100 text-green-700 px-2 py-0.5 rounded-full">Active</span>
          </div>
          {activeProblem.snomed_code && (
            <div className="text-xs font-mono font-semibold text-nhs-blue mt-1">
              {activeProblem.snomed_code}
            </div>
          )}
          <div className="grid grid-cols-2 gap-3 mt-3">
            <div>
              <div className="text-[10px] font-bold text-gray-500 uppercase tracking-wide mb-0.5">Severity</div>
              <div className="text-sm border border-gray-200 rounded px-2 py-1">Major</div>
            </div>
            <div>
              <div className="text-[10px] font-bold text-gray-500 uppercase tracking-wide mb-0.5">Status</div>
              <select className="text-sm border border-gray-200 rounded px-2 py-1 w-full">
                <option>Review</option>
                <option>Active</option>
                <option>Resolved</option>
                <option>Inactive</option>
              </select>
            </div>
            <div>
              <div className="text-[10px] font-bold text-gray-500 uppercase tracking-wide mb-0.5">Started on</div>
              <div className="text-sm border border-gray-200 rounded px-2 py-1">
                {result.structured?.admission_date || '—'}
              </div>
            </div>
            <div>
              <div className="text-[10px] font-bold text-gray-500 uppercase tracking-wide mb-0.5">Description</div>
              <div className="text-sm border border-gray-200 rounded px-2 py-1 truncate">
                {activeProblem.description || '—'}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Codes section */}
      <div className="flex items-center justify-between">
        <span className="field-label mb-0">Codes</span>
        <span className="text-xs text-gray-400">Clear section</span>
      </div>
      <div className="border border-gray-200 rounded-lg px-3 py-2 text-xs text-gray-500 bg-white mb-2">
        Add a code
      </div>

      {/* Grouped SNOMED cards */}
      {(['disorder', 'finding', 'procedure', 'situation', 'event', 'substance', 'product'] as SemanticType[]).map((semType) => {
        const entities = grouped[semType];
        if (!entities.length) return null;
        const colors = SEMANTIC_COLORS[semType];
        return (
          <div key={semType}>
            <div className="text-xs font-bold text-gray-500 uppercase tracking-wide mt-3 mb-2">
              {getSemanticLabel(semType)}
            </div>
            {entities.map((e, i) => (
              <div
                key={e.entity_id || i}
                className={`border ${colors.border} border-l-4 rounded-lg p-3 mb-2 ${colors.bg}`}
              >
                <div className="flex justify-between items-start gap-2">
                  <span className="font-bold text-gray-800">{e.text}</span>
                  <span className="text-gray-400">⋮</span>
                </div>
                {e.snomed_code && (
                  <div className="text-xs font-mono font-semibold text-nhs-blue mt-1">
                    {e.snomed_code}
                  </div>
                )}
                {e.description && (
                  <div className="text-xs text-gray-500 italic mt-1.5 break-words">
                    {e.description}
                  </div>
                )}
              </div>
            ))}
          </div>
        );
      })}

      {allEntities.length === 0 && (
        <div className="text-sm text-gray-400 italic">
          No coded entities identified — expand the mapping table below or check ICD / medication extraction.
        </div>
      )}

      {/* SNOMED Table disclosure */}
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
                  {allEntities.length} entities
                </span>
              </div>
            </div>
            <div className="bg-blue-50 px-3 py-1 text-xs text-gray-600 flex gap-4 border-b border-blue-200">
              <span><span className="inline-block w-2.5 h-2.5 rounded bg-red-600 mr-1 align-middle" />Problem</span>
              <span><span className="inline-block w-2.5 h-2.5 rounded bg-green-600 mr-1 align-middle" />Diagnosis</span>
              <span><span className="inline-block w-2.5 h-2.5 rounded bg-blue-600 mr-1 align-middle" />Medication</span>
            </div>
            <div className="max-h-64 overflow-y-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="bg-gray-50 sticky top-0">
                    <th className="px-2 py-1.5 text-left font-bold text-gray-700 border-b border-gray-200">Category</th>
                    <th className="px-2 py-1.5 text-left font-bold text-gray-700 border-b border-gray-200">Term</th>
                    <th className="px-2 py-1.5 text-left font-bold text-gray-700 border-b border-gray-200">Code</th>
                    <th className="px-2 py-1.5 text-left font-bold text-gray-700 border-b border-gray-200">Description</th>
                    <th className="px-2 py-1.5 text-center font-bold text-gray-700 border-b border-gray-200">Conf.</th>
                  </tr>
                </thead>
                <tbody>
                  {allEntities.map((e, i) => {
                    const confPct = Math.round((e.confidence || 0) * 100);
                    const confColor = confPct >= 70 ? 'text-green-600' : confPct >= 45 ? 'text-yellow-600' : 'text-red-600';
                    return (
                      <tr key={e.entity_id || i} className={i % 2 === 0 ? 'bg-white' : 'bg-gray-50'}>
                        <td className="px-2 py-1.5 border-b border-gray-100">
                          <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${SEMANTIC_COLORS[getSemanticType(e)].bg} ${SEMANTIC_COLORS[getSemanticType(e)].text}`}>
                            {e.category || getSemanticLabel(getSemanticType(e))}
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
                        <td className="px-2 py-1.5 text-gray-500 border-b border-gray-100">{e.description || '—'}</td>
                        <td className={`px-2 py-1.5 text-center font-bold border-b border-gray-100 ${confColor}`}>
                          {confPct}%
                        </td>
                      </tr>
                    );
                  })}
                  {allEntities.length === 0 && (
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

      {/* Medications */}
      <div className="mt-4">
        <div className="field-label flex items-center gap-1">💊 Medications (extracted text)</div>
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
