import { useEffect, useState } from 'react';

interface ProcessingPanelProps {
  filename: string;
}

const PIPELINE_STEPS = [
  { id: 'upload', label: 'Document uploaded', icon: '📄' },
  { id: 'ocr', label: 'AWS Textract OCR', icon: '🔍' },
  { id: 'llm', label: 'Claude AI extraction', icon: '🤖' },
  { id: 'struct', label: 'Structuring output', icon: '✅' },
];

export default function ProcessingPanel({ filename }: ProcessingPanelProps) {
  const [currentStep, setCurrentStep] = useState(0);

  useEffect(() => {
    const delays = [0, 500, 3000, 8000];
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
    <div className="flex-1 flex flex-col items-center justify-center p-8 animate-fade-in">
      {/* MediLab Spinner */}
      <div className="relative mb-8">
        <div className="w-20 h-20 border-4 border-[#1977cc]/20 rounded-full" />
        <div className="absolute top-0 left-0 w-20 h-20 border-4 border-transparent border-t-[#1977cc] rounded-full animate-spin" />
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 text-2xl">
          {PIPELINE_STEPS[currentStep]?.icon || '📄'}
        </div>
      </div>

      <h3 className="text-xl font-semibold text-[#2c4964] mb-2 font-heading">Processing Document...</h3>
      <p className="text-sm text-[#444444] mb-6">Running AI-powered extraction pipeline</p>

      {/* Pipeline steps - MediLab Style */}
      <div className="bg-white rounded-lg p-6 max-w-md w-full shadow-medilab">
        {PIPELINE_STEPS.map((step, i) => {
          let status: 'done' | 'active' | 'pending' = 'pending';
          if (i < currentStep) status = 'done';
          else if (i === currentStep) status = 'active';

          return (
            <div
              key={step.id}
              className={`flex items-center gap-4 py-3 text-sm transition-all duration-300 ${
                status === 'done' ? 'text-[#059652]' :
                status === 'active' ? 'text-[#1977cc] font-semibold' :
                'text-gray-400'
              }`}
            >
              <div
                className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 transition-all duration-300 ${
                  status === 'done' ? 'bg-[#059652]/10 text-[#059652]' :
                  status === 'active' ? 'bg-[#1977cc]/10 text-[#1977cc]' :
                  'bg-gray-100 text-gray-400'
                }`}
              >
                {status === 'done' ? '✓' : step.icon}
              </div>
              <span>{step.label}</span>
              {status === 'active' && (
                <div className="ml-auto flex gap-1">
                  <span className="w-1.5 h-1.5 bg-[#1977cc] rounded-full animate-pulse" />
                  <span className="w-1.5 h-1.5 bg-[#1977cc] rounded-full animate-pulse" style={{ animationDelay: '0.2s' }} />
                  <span className="w-1.5 h-1.5 bg-[#1977cc] rounded-full animate-pulse" style={{ animationDelay: '0.4s' }} />
                </div>
              )}
            </div>
          );
        })}
      </div>

      <p className="text-xs text-[#768692] mt-5">
        Processing: <span className="font-medium text-[#2c4964]">{filename}</span>
      </p>
    </div>
  );
}
