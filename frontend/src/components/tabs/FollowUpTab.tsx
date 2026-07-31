import type { ProcessResult } from '../../api/types';
import CollapsibleSection from '../CollapsibleSection';
import { IconClipboard, IconCalendar, IconCheckCircle, IconHospital, IconUser, IconPill, IconPlus } from '../icons/Icons';

interface FollowUpTabProps {
  result: ProcessResult;
}

interface RoleActionsBlockProps {
  role: 'doctor' | 'pharmacist' | 'reception';
  actions: string[];
}

const ROLE_CONFIG = {
  doctor: {
    label: 'Doctor',
    icon: <IconUser size={14} />,
    bgClass: 'bg-[#1977cc]/10',
    textClass: 'text-[#1977cc]',
    borderClass: 'border-[#1977cc]/20',
  },
  pharmacist: {
    label: 'Pharmacist',
    icon: <IconPill size={14} />,
    bgClass: 'bg-[#059652]/10',
    textClass: 'text-[#059652]',
    borderClass: 'border-[#059652]/20',
  },
  reception: {
    label: 'Reception',
    icon: <IconClipboard size={14} />,
    bgClass: 'bg-[#ffc107]/10',
    textClass: 'text-[#b38600]',
    borderClass: 'border-[#ffc107]/30',
  },
};

function ActionCard({ text }: { text: string }) {
  return (
    <div className="border border-purple-200 border-l-4 border-l-purple-500 rounded-lg p-3 mb-2 bg-gradient-to-r from-purple-50 to-white transition-all duration-300 hover:shadow-sm">
      <p className="text-sm text-gray-700">{text}</p>
      <div className="text-right mt-2">
        <button className="text-xs font-semibold text-[#1977cc] border border-[#1977cc] rounded-full px-4 py-1 hover:bg-[#1977cc]/5 transition-all duration-300">
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
      <div className={`inline-flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wide px-2.5 py-1 rounded-full ${config.bgClass} ${config.textClass} mb-2`}>
        {config.icon}
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

  const diaryEvents = result.diary_events || [];
  const recommendation = result.recommendation || '';

  return (
    <div className="space-y-3">
      {/* Recommendation - Collapsible */}
      {recommendation && (
        <CollapsibleSection title="Recommendation" icon={<IconClipboard size={14} />} defaultOpen={true}>
          <div className="text-sm text-gray-700 leading-relaxed">
            {recommendation}
          </div>
        </CollapsibleSection>
      )}

      {/* Diary Events - Collapsible */}
      <CollapsibleSection
        title="Diary Events"
        icon={<IconCalendar size={14} />}
        defaultOpen={diaryEvents.length > 0}
        badge={
          diaryEvents.length > 0 && (
            <span className="ml-2 bg-[#1977cc]/10 text-[#1977cc] text-xs px-2 py-0.5 rounded-full font-semibold">
              {diaryEvents.length}
            </span>
          )
        }
      >
        {diaryEvents.length > 0 ? (
          <div className="space-y-2">
            {diaryEvents.map((event, i) => (
              <div key={i} className="border border-orange-200 border-l-4 border-l-orange-500 rounded-lg p-3 bg-gradient-to-r from-orange-50 to-white transition-all duration-300 hover:shadow-sm">
                <p className="text-sm font-medium text-gray-800">{event.event}</p>
                <div className="flex gap-4 mt-1 text-xs text-gray-500">
                  {event.due_date && (
                    <span className="flex items-center gap-1">
                      <IconCalendar size={12} />
                      {event.due_date}
                    </span>
                  )}
                  {event.responsible_party && (
                    <span className="flex items-center gap-1">
                      <IconUser size={12} />
                      {event.responsible_party}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-sm text-gray-400 italic">
            No scheduled follow-up events found.
          </div>
        )}
      </CollapsibleSection>

      {/* To-do - Collapsible */}
      <CollapsibleSection
        title="To-do"
        icon={<IconCheckCircle size={14} />}
        defaultOpen={true}
        badge={
          <button className="ml-auto text-xs text-[#1977cc] hover:underline font-semibold flex items-center gap-1">
            <IconPlus size={12} />
            Add task
          </button>
        }
      >
        <div className="text-sm text-gray-400 italic">
          No tasks assigned to this document.
        </div>
      </CollapsibleSection>

      {/* Sender Actions - Collapsible */}
      <CollapsibleSection
        title="Sender Actions"
        icon={<IconHospital size={14} />}
        defaultOpen={hasAnyActions}
        badge={
          hasAnyActions && (
            <span className="ml-2 bg-purple-100 text-purple-700 text-xs px-2 py-0.5 rounded-full font-semibold">
              {(senderActions.doctor?.length || 0) + (senderActions.pharmacist?.length || 0) + (senderActions.reception?.length || 0)}
            </span>
          )
        }
      >
        <div className="text-xs text-gray-500 mb-3">
          Actions the hospital/clinic/specialist has planned or committed to
        </div>
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
      </CollapsibleSection>

      {/* Done - Collapsible */}
      <CollapsibleSection title="Completed" icon={<IconCheckCircle size={14} />} defaultOpen={false}>
        <div className="text-sm text-gray-400 italic">
          No completed tasks for this document.
        </div>
      </CollapsibleSection>
    </div>
  );
}
