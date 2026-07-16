import { useState } from 'react';
import type { ProcessResult } from '../../api/types';

interface GPActionsTabProps {
  result: ProcessResult;
}

const ROLE_CONFIG = {
  doctor: {
    label: '👩‍⚕️ Doctor',
    bgClass: 'bg-blue-50',
    textClass: 'text-blue-700',
  },
  pharmacist: {
    label: '💊 Pharmacist',
    bgClass: 'bg-green-50',
    textClass: 'text-green-700',
  },
  reception: {
    label: '📋 Reception',
    bgClass: 'bg-yellow-50',
    textClass: 'text-yellow-700',
  },
};

function GPActionCard({ text }: { text: string }) {
  return (
    <div className="border border-blue-200 border-l-4 border-l-blue-600 rounded-lg p-3 mb-2 bg-gradient-to-r from-blue-50 to-white">
      <p className="text-sm text-gray-700">{text}</p>
      <div className="text-right mt-2">
        <button className="text-xs font-semibold text-nhs-blue border border-nhs-blue rounded px-3 py-1 hover:bg-blue-50">
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
      <div className={`inline-block text-[10px] font-bold uppercase tracking-wide px-2 py-1 rounded ${config.bgClass} ${config.textClass} mb-2`}>
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
  const [contactOpen, setContactOpen] = useState(true);
  const [documentOpen, setDocumentOpen] = useState(true);

  const gpActions = result.actions_structured?.gp_surgery_actions || {
    doctor: [],
    pharmacist: [],
    reception: [],
  };

  // Patient actions from comprehensive extraction
  const patientActions = result.actions_structured?.patient_actions || [];
  const patientBooking = result.actions_structured?.patient_booking || [];

  const hasAnyActions = (gpActions.doctor?.length || 0) +
                        (gpActions.pharmacist?.length || 0) +
                        (gpActions.reception?.length || 0) > 0;

  const hasPatientActions = patientActions.length > 0 || patientBooking.length > 0;

  // Check if document explicitly states "No action required" for GP
  const extractedText = result.extracted_text?.toLowerCase() || '';
  const noGPActionExplicit = extractedText.includes('no action required') ||
                             extractedText.includes('no gp action') ||
                             extractedText.includes('actions required of general practice (gp)') && extractedText.includes('no action required');

  const copyLink = () => {
    navigator.clipboard.writeText(window.location.href.split('#')[0]);
    alert('Page link copied to clipboard.');
  };

  return (
    <div className="space-y-4">
      <p className="text-xs text-gray-500">
        Actions the GP surgery must take based on this letter, split by who in the practice is responsible.
      </p>

      {/* GP Surgery Actions */}
      <div className="border border-gray-200 rounded-lg overflow-hidden">
        <div className="px-3 py-2 text-xs font-bold text-gray-600 bg-gray-50 border-b border-gray-200">
          GP Surgery Actions
        </div>
        <div className="p-3">
          {hasAnyActions ? (
            <>
              <RoleBlock role="doctor" actions={gpActions.doctor || []} />
              <RoleBlock role="pharmacist" actions={gpActions.pharmacist || []} />
              <RoleBlock role="reception" actions={gpActions.reception || []} />
            </>
          ) : noGPActionExplicit ? (
            <div className="flex items-center gap-2 p-3 bg-green-50 border border-green-200 rounded-lg">
              <span className="text-green-600 text-lg">✓</span>
              <span className="text-sm font-medium text-green-700">
                No GP action required — document explicitly states no actions needed.
              </span>
            </div>
          ) : (
            <div className="text-sm text-gray-400 italic">
              No GP surgery actions identified for this document.
            </div>
          )}
        </div>
      </div>

      {/* Patient Actions */}
      {hasPatientActions && (
        <div className="border border-green-200 rounded-lg overflow-hidden">
          <div className="px-3 py-2 text-xs font-bold text-green-700 bg-green-50 border-b border-green-200">
            🧑 Patient Actions
          </div>
          <div className="p-3 space-y-2">
            {patientActions.length > 0 && (
              <div>
                <div className="text-xs font-medium text-gray-500 mb-1">Actions for Patient:</div>
                {patientActions.map((action, i) => (
                  <div key={i} className="border border-green-200 border-l-4 border-l-green-500 rounded-lg p-3 mb-2 bg-gradient-to-r from-green-50 to-white">
                    <p className="text-sm text-gray-700">{action}</p>
                  </div>
                ))}
              </div>
            )}
            {patientBooking.length > 0 && (
              <div>
                <div className="text-xs font-medium text-gray-500 mb-1">Appointments to Book:</div>
                {patientBooking.map((action, i) => (
                  <div key={i} className="border border-teal-200 border-l-4 border-l-teal-500 rounded-lg p-3 mb-2 bg-gradient-to-r from-teal-50 to-white">
                    <p className="text-sm text-gray-700">{action}</p>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Contact section */}
      <div className="border border-gray-200 rounded-lg overflow-hidden">
        <button
          className="w-full px-3 py-2 text-xs font-bold text-gray-600 bg-gray-50 border-b border-gray-200 flex justify-between items-center"
          onClick={() => setContactOpen(!contactOpen)}
        >
          <span>Contact</span>
          <span>{contactOpen ? '▾' : '▸'}</span>
        </button>
        {contactOpen && (
          <div className="p-2">
            <button
              className="w-full text-left px-3 py-2 rounded hover:bg-blue-50 text-sm flex items-center gap-2"
              onClick={() => alert('In a live deployment this would open the follow-up messaging workflow.')}
            >
              ✉️ Send follow-up
            </button>
          </div>
        )}
      </div>

      {/* Document section */}
      <div className="border border-gray-200 rounded-lg overflow-hidden">
        <button
          className="w-full px-3 py-2 text-xs font-bold text-gray-600 bg-gray-50 border-b border-gray-200 flex justify-between items-center"
          onClick={() => setDocumentOpen(!documentOpen)}
        >
          <span>Document</span>
          <span>{documentOpen ? '▾' : '▸'}</span>
        </button>
        {documentOpen && (
          <div className="p-2">
            <button
              className="w-full text-left px-3 py-2 rounded hover:bg-gray-50 text-sm flex items-center gap-2"
              onClick={() => alert('Activity timeline would open here.')}
            >
              🕐 Open activity
            </button>
            <button
              className="w-full text-left px-3 py-2 rounded hover:bg-gray-50 text-sm flex items-center gap-2"
              onClick={copyLink}
            >
              🔗 Copy link
            </button>
            <button
              className="w-full text-left px-3 py-2 rounded hover:bg-gray-50 text-sm flex items-center gap-2"
              onClick={() => alert('Archive would move this document to the archive store.')}
            >
              🗑️ Archive document
            </button>
          </div>
        )}
      </div>

      <p className="text-xs text-gray-500 mt-3">
        Use <strong>Download</strong> for the full processed JSON. Approve and EMIS export stay in the bar below.
      </p>
    </div>
  );
}
