import type { ProcessResult, SNOMEDEntity } from '../../api/types';
import CollapsibleSection from '../CollapsibleSection';
import { IconCode, IconStethoscope, IconSyringe, IconPill, IconFlask, IconClipboard, IconBarChart, IconHistory, IconRefresh } from '../icons/Icons';

interface CodingTabProps {
  result: ProcessResult;
}

type ClinicalCategory = 'problems' | 'treatments' | 'medications' | 'investigations' | 'diagnoses';

const CATEGORY_CONFIG: Record<ClinicalCategory, {
  label: string;
  icon: React.ReactNode;
  description: string;
  border: string;
  bg: string;
  text: string;
  headerBg: string;
}> = {
  problems: {
    label: 'Problems / Issues',
    icon: <IconStethoscope size={14} />,
    description: 'Symptoms and findings',
    border: 'border-orange-500',
    bg: 'bg-orange-50',
    text: 'text-orange-700',
    headerBg: 'bg-orange-100',
  },
  treatments: {
    label: 'Treatment',
    icon: <IconSyringe size={14} />,
    description: 'Therapeutic procedures',
    border: 'border-purple-500',
    bg: 'bg-purple-50',
    text: 'text-purple-700',
    headerBg: 'bg-purple-100',
  },
  medications: {
    label: 'Medication',
    icon: <IconPill size={14} />,
    description: 'Drugs and substances',
    border: 'border-blue-500',
    bg: 'bg-blue-50',
    text: 'text-blue-700',
    headerBg: 'bg-blue-100',
  },
  investigations: {
    label: 'Investigation',
    icon: <IconFlask size={14} />,
    description: 'Diagnostic tests',
    border: 'border-teal-500',
    bg: 'bg-teal-50',
    text: 'text-teal-700',
    headerBg: 'bg-teal-100',
  },
  diagnoses: {
    label: 'Diagnosis',
    icon: <IconClipboard size={14} />,
    description: 'Confirmed conditions',
    border: 'border-red-500',
    bg: 'bg-red-50',
    text: 'text-red-700',
    headerBg: 'bg-red-100',
  },
};

function SNOMEDCard({ entity, category }: { entity: SNOMEDEntity; category: ClinicalCategory }) {
  const config = CATEGORY_CONFIG[category];
  const confPercent = Math.round((entity.confidence || 0) * 100);
  const confColor = confPercent >= 80 ? 'text-[#059652]' : confPercent >= 60 ? 'text-[#b38600]' : 'text-[#df1529]';

  const priority = (entity as { priority?: string }).priority;
  const result = (entity as { result?: string }).result;
  const isUrgent = priority?.toLowerCase() === 'urgent';
  const isPending = result?.toLowerCase() === 'pending';

  return (
    <div className={`border ${config.border} border-l-4 rounded-lg p-3 mb-2 ${config.bg} transition-all duration-300 hover:shadow-sm`}>
      <div className="flex justify-between items-start gap-2">
        <div className="flex-1">
          <span className="font-bold text-gray-800">{entity.text}</span>
          {entity.snomed_code && (
            <code className="ml-2 bg-white/70 text-[#1977cc] px-1.5 py-0.5 rounded font-mono font-bold text-xs">
              {entity.snomed_code}
            </code>
          )}
          {priority && (
            <span className={`ml-2 text-[10px] font-bold uppercase px-1.5 py-0.5 rounded ${
              isUrgent
                ? 'bg-[#df1529]/10 text-[#df1529] border border-[#df1529]/20'
                : 'bg-gray-100 text-gray-600 border border-gray-300'
            }`}>
              {priority}
            </span>
          )}
          {isPending && (
            <span className="ml-2 text-[10px] font-bold uppercase px-1.5 py-0.5 rounded bg-[#ffc107]/10 text-[#b38600] border border-[#ffc107]/30">
              Pending
            </span>
          )}
        </div>
        {confPercent > 0 && (
          <span className={`text-xs font-bold ${confColor}`}>{confPercent}%</span>
        )}
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

  return (
    <CollapsibleSection
      title={config.label}
      icon={config.icon}
      defaultOpen={entities.length > 0}
      badge={
        <span className="ml-2 bg-white/70 text-gray-600 text-xs px-2 py-0.5 rounded-full font-semibold">
          {entities.length}
        </span>
      }
    >
      {entities.length > 0 ? (
        entities.map((entity, i) => (
          <SNOMEDCard key={entity.entity_id || i} entity={entity} category={category} />
        ))
      ) : (
        <div className="text-sm text-gray-400 italic">
          No {config.label.toLowerCase()} identified
        </div>
      )}
    </CollapsibleSection>
  );
}

export default function CodingTab({ result }: CodingTabProps) {
  const problems = result.snomed?.problems || [];
  const treatments = result.snomed?.treatments || [];
  const medications = result.snomed?.medications || [];
  const investigations = result.snomed?.investigations || [];
  const diagnoses = result.snomed?.diagnoses || [];

  const icdCodes = result.icd_codes || [];
  const medsRaw = result.medications_raw || [];

  const allEntities = [...diagnoses, ...problems, ...treatments, ...medications, ...investigations];
  const totalEntities = allEntities.length;

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
    <div className="space-y-3">
      {/* Header */}
      <CollapsibleSection title="SNOMED CT Overview" icon={<IconCode size={14} />} defaultOpen={true}>
        <div className="flex items-center justify-between mb-3">
          <div>
            <div className="text-sm font-semibold text-[#2c4964]">Clinical Coding</div>
            <div className="text-xs text-gray-500 mt-0.5">
              {totalEntities} entities extracted • {snomedConfidence}% SNOMED confidence
            </div>
          </div>
          <div className="flex items-center gap-2 text-gray-400">
            <span className="cursor-pointer hover:text-[#1977cc] transition-colors" title="History">
              <IconHistory size={16} />
            </span>
            <span className="cursor-pointer hover:text-[#1977cc] transition-colors" title="Refresh">
              <IconRefresh size={16} />
            </span>
          </div>
        </div>

        {/* Active Problem/Diagnosis Card */}
        {activeProblem && (
          <div className="border border-gray-200 border-l-4 border-l-[#df1529] rounded-lg p-3 bg-white">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-bold text-gray-800">{activeProblem.text}</span>
              <span className="text-[10px] font-bold uppercase tracking-wide bg-[#df1529]/10 text-[#df1529] px-2 py-0.5 rounded-full">
                {diagnoses.includes(activeProblem) ? 'Diagnosis' : 'Problem'}
              </span>
              <span className="text-[10px] font-bold uppercase tracking-wide bg-[#059652]/10 text-[#059652] px-2 py-0.5 rounded-full">Active</span>
            </div>
            {activeProblem.snomed_code && (
              <div className="text-xs font-mono font-semibold text-[#1977cc] mt-1">
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
      </CollapsibleSection>

      {/* 5 Clinical Categories - Each Collapsible */}
      <CategorySection category="diagnoses" entities={diagnoses} />
      <CategorySection category="problems" entities={problems} />
      <CategorySection category="treatments" entities={treatments} />
      <CategorySection category="medications" entities={medications} />
      <CategorySection category="investigations" entities={investigations} />

      {totalEntities === 0 && (
        <div className="text-sm text-gray-400 italic p-4 bg-gray-50 rounded-lg">
          No SNOMED CT entities identified — check ICD codes or medication extraction below.
        </div>
      )}

      {/* ICD Codes - Collapsible */}
      <CollapsibleSection title="ICD Codes" icon={<IconClipboard size={14} />} defaultOpen={icdCodes.length > 0}>
        <div className="flex flex-wrap gap-1">
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
      </CollapsibleSection>

      {/* Medications - Collapsible */}
      <CollapsibleSection title="Medications (Text)" icon={<IconPill size={14} />} defaultOpen={medsRaw.length > 0}>
        <div className="flex flex-wrap gap-1">
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
      </CollapsibleSection>

      {/* Confidence - Collapsible */}
      <CollapsibleSection title="Confidence Score" icon={<IconBarChart size={14} />} defaultOpen={true}>
        <div className="flex items-center gap-3">
          <span className="text-2xl font-bold text-[#1977cc]">{confPercent}%</span>
          <div className="flex-1">
            <div className="conf-bar-wrap">
              <div className={`conf-bar ${confClass}`} style={{ width: `${Math.min(confPercent, 100)}%` }} />
            </div>
          </div>
        </div>
        <div className="text-xs text-gray-500 mt-2">
          Threshold: {thresholdPercent}% ({result.letter_type || 'default'}) | Textract + SNOMED + LLM weighted
        </div>
      </CollapsibleSection>
    </div>
  );
}
