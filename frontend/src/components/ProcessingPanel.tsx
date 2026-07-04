import { useEffect, useState } from 'react';

interface ProcessingPanelProps {
  filename: string;
}

const PIPELINE_STEPS = [
  { id: 'upload', label: 'Document uploaded' },
  { id: 't0', label: 'Tier 0 — Image preprocessing' },
  { id: 't1', label: 'Tier 1 — AWS Textract OCR' },
  { id: 'ta', label: 'Track A — SNOMED entity mapping' },
  { id: 'tb', label: 'Track B — AI summarization (Claude)' },
  { id: 'conf', label: 'Confidence aggregation & routing' },
];

export default function ProcessingPanel({ filename }: ProcessingPanelProps) {
  const [currentStep, setCurrentStep] = useState(0);

  useEffect(() => {
    const delays = [0, 400, 2000, 5000, 9000, 13000];
    const timers: ReturnType<typeof setTimeout>[] = [];

    delays.forEach((delay, i) => {
      const timer = setTimeout(() => {
        setCurrentStep(i);
      }, delay);
      timers.push(timer);
    });

    return () => {
      timers.forEach(clearTimeout);
    };
  }, []);

  return (
    <div className="flex-1 flex flex-col items-center justify-center p-8">
      {/* Spinner */}
      <div className="w-14 h-14 border-4 border-blue-100 border-t-nhs-blue rounded-full animate-spin mb-6" />

      <h3 className="text-lg font-semibold text-nhs-dark mb-2">Processing Document...</h3>
      <p className="text-sm text-gray-500 mb-5">Running full clinical NLP pipeline</p>

      {/* Pipeline steps */}
      <div className="bg-white rounded-xl p-5 max-w-md w-full shadow-sm">
        {PIPELINE_STEPS.map((step, i) => {
          let status: 'done' | 'active' | 'pending' = 'pending';
          if (i < currentStep) status = 'done';
          else if (i === currentStep) status = 'active';

          return (
            <div
              key={step.id}
              className={`flex items-center gap-3 py-2 text-sm ${
                status === 'done' ? 'text-green-600' :
                status === 'active' ? 'text-nhs-blue font-semibold' :
                'text-gray-400'
              }`}
            >
              <div
                className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${
                  status === 'done' ? 'bg-green-500' :
                  status === 'active' ? 'bg-nhs-blue' :
                  'bg-gray-300'
                }`}
              />
              {step.label}
            </div>
          );
        })}
      </div>

      <p className="text-xs text-gray-400 mt-4">
        Processing: {filename}
      </p>
    </div>
  );
}
