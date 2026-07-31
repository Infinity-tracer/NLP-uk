import type { ProcessResult } from '../../api/types';
import CollapsibleSection from '../CollapsibleSection';

interface GPActionsTabProps {
  result: ProcessResult;
}

const ROLE_CONFIG = {
  doctor: {
    label: '👩‍⚕️ Doctor',
    bgClass: 'bg-[#1977cc]/10',
    textClass: 'text-[#1977cc]',
  },
  pharmacist: {
    label: '💊 Pharmacist',
    bgClass: 'bg-[#059652]/10',
    textClass: 'text-[#059652]',
  },
  reception: {
    label: '📋 Reception',
    bgClass: 'bg-[#ffc107]/10',
    textClass: 'text-[#b38600]',
  },
};

function GPActionCard({ text }: { text: string }) {
  return (
    <div className="border border-[#1977cc]/20 border-l-4 border-l-[#1977cc] rounded-lg p-3 mb-2 bg-gradient-to-r from-[#1977cc]/5 to-white transition-all duration-300 hover:shadow-sm">
      <p className="text-sm text-gray-700">{text}</p>
      <div className="text-right mt-2">
        <button className="text-xs font-semibold text-[#1977cc] border border-[#1977cc] rounded-pill px-4 py-1 hover:bg-[#1977cc]/5 transition-all duration-300">
          Add
        </button>
      </div>
    </div>
  );
}

interface RoleBlockProps {
  role: 'doctor' | 'pharmacist' | 'reception';
  actions: string[];
}

function RoleBlock({ role, actions }: RoleBlockProps) {
  const config = ROLE_CONFIG[role];
  if (!actions || actions.length === 0) return null;

  return (
    <div className="mb-4">
      <div className={`inline-block text-[10px] font-bold uppercase tracking-wide px-2.5 py-1 rounded-pill ${config.bgClass} ${config.textClass} mb-2`}>
        {config.label}
      </div>
      <div>
        {actions.map((action, i) => (
          <GPActionCard key={i} text={action} />
        ))}
      </div>
    </div>
  );
}

export default function GPActionsTab({ result }: GPActionsTabProps) {
  const gpActions = result.actions_structured?.gp_surgery_actions || {
    doctor: [],
    pharmacist: [],
    reception: [],
  };

  const patientActions = result.actions_structured?.patient_actions || [];
  const patientBooking = result.actions_structured?.patient_booking || [];

  const hasAnyActions = (gpActions.doctor?.length || 0) +
                        (gpActions.pharmacist?.length || 0) +
                        (gpActions.reception?.length || 0) > 0;

  const hasPatientActions = patientActions.length > 0 || patientBooking.length > 0;

  const extractedText = result.extracted_text?.toLowerCase() || '';
  const noGPActionExplicit = extractedText.includes('no action required') ||
                             extractedText.includes('no gp action') ||
                             extractedText.includes('actions required of general practice (gp)') && extractedText.includes('no action required');

  const copyLink = () => {
    navigator.clipboard.writeText(window.location.href.split('#')[0]);
    alert('Page link copied to clipboard.');
  };

  const totalGPActions = (gpActions.doctor?.length || 0) + (gpActions.pharmacist?.length || 0) + (gpActions.reception?.length || 0);

  return (
    <div className="space-y-3">
      <p className="text-xs text-gray-500 mb-2">
        Actions the GP surgery must take based on this letter, split by who in the practice is responsible.
      </p>

      {/* GP Surgery Actions - Collapsible */}
      <CollapsibleSection
        title="GP Surgery Actions"
        icon="🏥"
        defaultOpen={true}
        badge={
          hasAnyActions && (
            <span className="ml-2 bg-[#1977cc]/10 text-[#1977cc] text-xs px-2 py-0.5 rounded-full font-semibold">
              {totalGPActions}
            </span>
          )
        }
      >
        {hasAnyActions ? (
          <>
            <RoleBlock role="doctor" actions={gpActions.doctor || []} />
            <RoleBlock role="pharmacist" actions={gpActions.pharmacist || []} />
            <RoleBlock role="reception" actions={gpActions.reception || []} />
          </>
        ) : noGPActionExplicit ? (
          <div className="flex items-center gap-2 p-3 bg-[#059652]/5 border border-[#059652]/20 rounded-lg">
            <span className="text-[#059652] text-lg">✓</span>
            <span className="text-sm font-medium text-[#059652]">
              No GP action required — document explicitly states no actions needed.
            </span>
          </div>
        ) : (
          <div className="text-sm text-gray-400 italic">
            No GP surgery actions identified for this document.
          </div>
        )}
      </CollapsibleSection>

      {/* Patient Actions - Collapsible */}
      {hasPatientActions && (
        <CollapsibleSection
          title="Patient Actions"
          icon="🧑"
          defaultOpen={true}
          badge={
            <span className="ml-2 bg-[#059652]/10 text-[#059652] text-xs px-2 py-0.5 rounded-full font-semibold">
              {patientActions.length + patientBooking.length}
            </span>
          }
        >
          {patientActions.length > 0 && (
            <div className="mb-3">
              <div className="text-xs font-medium text-gray-500 mb-2">Actions for Patient:</div>
              {patientActions.map((action, i) => (
                <div key={i} className="border border-[#059652]/20 border-l-4 border-l-[#059652] rounded-lg p-3 mb-2 bg-gradient-to-r from-[#059652]/5 to-white transition-all duration-300 hover:shadow-sm">
                  <p className="text-sm text-gray-700">{action}</p>
                </div>
              ))}
            </div>
          )}
          {patientBooking.length > 0 && (
            <div>
              <div className="text-xs font-medium text-gray-500 mb-2">Appointments to Book:</div>
              {patientBooking.map((action, i) => (
                <div key={i} className="border border-teal-200 border-l-4 border-l-teal-500 rounded-lg p-3 mb-2 bg-gradient-to-r from-teal-50 to-white transition-all duration-300 hover:shadow-sm">
                  <p className="text-sm text-gray-700">{action}</p>
                </div>
              ))}
            </div>
          )}
        </CollapsibleSection>
      )}

      {/* Contact - Collapsible */}
      <CollapsibleSection title="Contact" icon="✉️" defaultOpen={false}>
        <button
          className="w-full text-left px-3 py-2.5 rounded-lg hover:bg-[#1977cc]/5 text-sm flex items-center gap-2 transition-all duration-300"
          onClick={() => alert('In a live deployment this would open the follow-up messaging workflow.')}
        >
          ✉️ Send follow-up
        </button>
      </CollapsibleSection>

      {/* Document - Collapsible */}
      <CollapsibleSection title="Document" icon="📄" defaultOpen={false}>
        <div className="space-y-1">
          <button
            className="w-full text-left px-3 py-2.5 rounded-lg hover:bg-gray-50 text-sm flex items-center gap-2 transition-all duration-300"
            onClick={() => alert('Activity timeline would open here.')}
          >
            🕐 Open activity
          </button>
          <button
            className="w-full text-left px-3 py-2.5 rounded-lg hover:bg-gray-50 text-sm flex items-center gap-2 transition-all duration-300"
            onClick={copyLink}
          >
            🔗 Copy link
          </button>
          <button
            className="w-full text-left px-3 py-2.5 rounded-lg hover:bg-[#df1529]/5 text-sm flex items-center gap-2 transition-all duration-300 text-[#df1529]"
            onClick={() => alert('Archive would move this document to the archive store.')}
          >
            🗑️ Archive document
          </button>
        </div>
      </CollapsibleSection>

      <p className="text-xs text-gray-500 mt-3 p-3 bg-gray-50 rounded-lg">
        Use <strong>Download</strong> for the full processed JSON. Approve and EMIS export stay in the bar below.
      </p>
    </div>
  );
}
