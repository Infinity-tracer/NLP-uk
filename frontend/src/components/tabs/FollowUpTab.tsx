import type { ProcessResult } from '../../api/types';

interface FollowUpTabProps {
  result: ProcessResult;
}

interface RoleActionsBlockProps {
  role: 'doctor' | 'pharmacist' | 'reception';
  actions: string[];
}

const ROLE_CONFIG = {
  doctor: {
    label: '👩‍⚕️ Doctor',
    bgClass: 'bg-blue-50',
    textClass: 'text-blue-700',
    borderClass: 'border-blue-200',
  },
  pharmacist: {
    label: '💊 Pharmacist',
    bgClass: 'bg-green-50',
    textClass: 'text-green-700',
    borderClass: 'border-green-200',
  },
  reception: {
    label: '📋 Reception',
    bgClass: 'bg-yellow-50',
    textClass: 'text-yellow-700',
    borderClass: 'border-yellow-200',
  },
};

function ActionCard({ text }: { text: string }) {
  return (
    <div className="border border-purple-200 border-l-4 border-l-purple-500 rounded-lg p-3 mb-2 bg-gradient-to-r from-purple-50 to-white">
      <p className="text-sm text-gray-700">{text}</p>
      <div className="text-right mt-2">
        <button className="text-xs font-semibold text-nhs-blue border border-nhs-blue rounded px-3 py-1 hover:bg-blue-50">
          Add
        </button>
      </div>
    </div>
  );
}

function RoleActionsBlock({ role, actions }: RoleActionsBlockProps) {
  const config = ROLE_CONFIG[role];
  if (!actions || actions.length === 0) return null;

  return (
    <div className="mb-4">
      <div className={`inline-block text-[10px] font-bold uppercase tracking-wide px-2 py-1 rounded ${config.bgClass} ${config.textClass} mb-2`}>
        {config.label}
      </div>
      <div>
        {actions.map((action, i) => (
          <ActionCard key={i} text={action} />
        ))}
      </div>
    </div>
  );
}

export default function FollowUpTab({ result }: FollowUpTabProps) {
  const senderActions = result.actions_structured?.sender_actions || {
    doctor: [],
    pharmacist: [],
    reception: [],
  };

  const hasAnyActions = (senderActions.doctor?.length || 0) +
                        (senderActions.pharmacist?.length || 0) +
                        (senderActions.reception?.length || 0) > 0;

  return (
    <div className="space-y-4">
      {/* To-do section */}
      <div className="border border-gray-200 rounded-lg overflow-hidden">
        <div className="flex justify-between items-center px-3 py-2 text-xs font-bold text-gray-600 bg-gray-50 border-b border-gray-200">
          <span>To-do</span>
          <span className="text-nhs-blue cursor-pointer">Add new task</span>
        </div>
        <div className="p-3 text-sm text-gray-400 italic">
          No tasks assigned to this document.
        </div>
      </div>

      {/* What the Sender Will Do */}
      <div className="border border-gray-200 rounded-lg overflow-hidden">
        <div className="px-3 py-2 text-xs font-bold text-gray-600 bg-gray-50 border-b border-gray-200">
          What the Sender Will Do
        </div>
        <div className="text-xs text-gray-500 px-3 pt-2 pb-1">
          Actions the hospital/clinic/specialist has planned or committed to
        </div>
        <div className="p-3">
          {hasAnyActions ? (
            <>
              <RoleActionsBlock role="doctor" actions={senderActions.doctor || []} />
              <RoleActionsBlock role="pharmacist" actions={senderActions.pharmacist || []} />
              <RoleActionsBlock role="reception" actions={senderActions.reception || []} />
            </>
          ) : (
            <div className="text-sm text-gray-400 italic">
              No sender actions identified for this document.
            </div>
          )}
        </div>
      </div>

      {/* Done section */}
      <div className="border border-gray-200 rounded-lg overflow-hidden">
        <div className="px-3 py-2 text-xs font-bold text-gray-600 bg-gray-50 border-b border-gray-200">
          Done
        </div>
        <div className="p-3 text-sm text-gray-400 italic">
          No completed tasks for this document.
        </div>
      </div>
    </div>
  );
}
