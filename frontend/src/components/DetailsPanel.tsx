import type { ProcessResult, TabType } from '../api/types';
import DetailsTab from './tabs/DetailsTab';
import CodingTab from './tabs/CodingTab';
import FollowUpTab from './tabs/FollowUpTab';
import GPActionsTab from './tabs/GPActionsTab';

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
    <div className="w-[400px] border-r border-gray-200 flex flex-col overflow-hidden bg-white">
      {/* Tabs */}
      <div className="flex gap-1.5 px-3 pt-3 pb-2 border-b border-gray-200 bg-gray-50 flex-wrap">
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
      <div className="flex-1 overflow-y-auto p-4">
        {/* Alert banner */}
        {isHighConf ? (
          <div className="flex items-center gap-2 p-3 bg-green-50 border border-green-200 rounded-lg text-sm text-green-700 mb-4">
            ✅ High confidence — outputs auto-generated. Review and click Approve to confirm.
          </div>
        ) : (
          <div className="flex items-center gap-2 p-3 bg-yellow-50 border border-yellow-200 rounded-lg text-sm text-yellow-700 mb-4">
            ⚠️ Confidence below threshold — outputs generated, please review before approving
          </div>
        )}

        {activeTab === 'details' && <DetailsTab result={result} />}
        {activeTab === 'coding' && <CodingTab result={result} />}
        {activeTab === 'followup' && <FollowUpTab result={result} />}
        {activeTab === 'gpactions' && <GPActionsTab result={result} />}
      </div>

      {/* Action bar */}
      <div className="p-3 border-t border-gray-200 flex gap-2 flex-wrap">
        <button className="btn-secondary text-sm py-1.5 px-3">Assign</button>
        <button onClick={onReset} className="btn-secondary text-sm py-1.5 px-3">Refresh</button>
        <button onClick={onDownload} className="btn-secondary text-sm py-1.5 px-3">Download</button>
        <button className="btn-success text-sm py-1.5 px-3">✓ Approve</button>
        <button className="btn-primary text-sm py-1.5 px-3">Save to record</button>
      </div>
    </div>
  );
}
