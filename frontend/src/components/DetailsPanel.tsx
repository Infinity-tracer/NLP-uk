import type { ProcessResult, TabType } from '../api/types';
import DetailsTab from './tabs/DetailsTab';
import CodingTab from './tabs/CodingTab';
import FollowUpTab from './tabs/FollowUpTab';
import GPActionsTab from './tabs/GPActionsTab';
import { IconCheckCircle, IconAlertCircle, IconDownload, IconRefresh, IconCheck } from './icons/Icons';

interface DetailsPanelProps {
  result: ProcessResult;
  activeTab: TabType;
  onTabChange: (tab: TabType) => void;
  onDownload: () => void;
  onReset: () => void;
}

const TABS: { id: TabType; label: string }[] = [
  { id: 'details', label: 'Details' },
  { id: 'coding', label: 'Coding' },
  { id: 'followup', label: 'Follow-up' },
  { id: 'gpactions', label: 'GP Actions' },
];

export default function DetailsPanel({
  result,
  activeTab,
  onTabChange,
  onDownload,
  onReset,
}: DetailsPanelProps) {
  const threshold = result.confidence_threshold || 0.75;
  const isHighConf = result.unified_confidence >= threshold;

  return (
    <div className="w-full h-full border-r border-gray-200 flex flex-col overflow-hidden bg-white">
      {/* Tabs */}
      <div className="flex gap-2 px-4 pt-4 pb-3 border-b border-gray-100 bg-gray-50/50 flex-wrap">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => onTabChange(tab.id)}
            className={`tab ${activeTab === tab.id ? 'active' : ''}`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-y-auto p-5">
        {/* Alert banner */}
        {isHighConf ? (
          <div className="flex items-center gap-3 p-4 bg-[#059652]/5 border border-[#059652]/20 rounded-lg text-sm text-[#059652] mb-5">
            <span className="w-6 h-6 bg-[#059652]/10 rounded-full flex items-center justify-center flex-shrink-0">
              <IconCheckCircle size={14} />
            </span>
            <span>High confidence — outputs auto-generated. Review and click Approve to confirm.</span>
          </div>
        ) : (
          <div className="flex items-center gap-3 p-4 bg-[#ffc107]/5 border border-[#ffc107]/30 rounded-lg text-sm text-[#b38600] mb-5">
            <span className="w-6 h-6 bg-[#ffc107]/10 rounded-full flex items-center justify-center flex-shrink-0">
              <IconAlertCircle size={14} />
            </span>
            <span>Confidence below threshold — outputs generated, please review before approving</span>
          </div>
        )}

        {activeTab === 'details' && <DetailsTab result={result} />}
        {activeTab === 'coding' && <CodingTab result={result} />}
        {activeTab === 'followup' && <FollowUpTab result={result} />}
        {activeTab === 'gpactions' && <GPActionsTab result={result} />}
      </div>

      {/* Action bar */}
      <div className="p-4 border-t border-gray-100 bg-gray-50/30 flex gap-2 flex-wrap">
        <button className="btn-secondary text-sm py-2 px-4">Assign</button>
        <button onClick={onReset} className="btn-secondary text-sm py-2 px-4 flex items-center gap-1.5">
          <IconRefresh size={14} />
          Refresh
        </button>
        <button onClick={onDownload} className="btn-secondary text-sm py-2 px-4 flex items-center gap-1.5">
          <IconDownload size={14} />
          Download
        </button>
        <button className="btn-success text-sm py-2 px-4 flex items-center gap-1.5">
          <IconCheck size={14} />
          Approve
        </button>
        <button className="btn-primary text-sm py-2 px-4">Save to record</button>
      </div>
    </div>
  );
}
