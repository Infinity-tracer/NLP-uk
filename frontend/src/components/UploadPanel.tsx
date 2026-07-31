import { useCallback, useState, useRef, DragEvent } from 'react';
import type { PipelineMode } from '../api/documentApi';

interface UploadPanelProps {
  onFileUpload: (file: File, mode: PipelineMode) => void;
  error: string | null;
}

const ALLOWED_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.pdf', '.tiff', '.tif'];

export default function UploadPanel({ onFileUpload, error }: UploadPanelProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [pipelineMode, setPipelineMode] = useState<PipelineMode>('full');
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleDragOver = useCallback((e: DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback(() => {
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback((e: DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) {
      onFileUpload(file, pipelineMode);
    }
  }, [onFileUpload, pipelineMode]);

  const handleFileChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      onFileUpload(file, pipelineMode);
    }
  }, [onFileUpload, pipelineMode]);

  const handleClick = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  return (
    <div className="flex-1 flex flex-col items-center justify-center p-8">
      <div
        className={`bg-white rounded-xl border-2 border-dashed p-12 max-w-xl w-full text-center cursor-pointer transition-all ${
          isDragging ? 'border-nhs-dark bg-blue-50' : 'border-nhs-blue hover:border-nhs-dark hover:bg-blue-50/50'
        }`}
        onDragOver={handleDragOver}
        onDragEnter={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={handleClick}
      >
        <div className="text-5xl mb-4">📋</div>
        <h2 className="text-xl font-semibold text-nhs-dark mb-2">Upload Clinical Document</h2>
        <p className="text-gray-500 text-sm mb-5">
          Drop a medical document here or click to browse.<br />
          The pipeline runs fully automatically.
        </p>
        <button className="btn-primary">Choose Document</button>
        <input
          ref={fileInputRef}
          type="file"
          accept={ALLOWED_EXTENSIONS.join(',')}
          onChange={handleFileChange}
          className="hidden"
        />
        <p className="text-xs text-gray-400 mt-3">
          Supported: JPEG, PNG, PDF, TIFF
        </p>
      </div>

      {error && (
        <div className="mt-4 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm max-w-xl w-full">
          Error: {error}
        </div>
      )}

      {/* Pipeline Mode Toggle */}
      <div className="mt-6 max-w-xl w-full bg-white rounded-xl p-5 border border-gray-200">
        <div className="text-xs font-bold text-gray-500 uppercase tracking-wide text-center mb-4">
          Select Processing Mode
        </div>
        <div className="flex gap-3 justify-center">
          <button
            onClick={() => setPipelineMode('full')}
            className={`flex-1 max-w-[220px] p-4 rounded-xl border-2 text-center transition-all ${
              pipelineMode === 'full'
                ? 'border-nhs-blue bg-blue-50'
                : 'border-gray-200 bg-white hover:border-gray-300'
            }`}
          >
            <div className="text-3xl mb-2">🔬</div>
            <div className="font-bold text-nhs-dark mb-1">Full Pipeline</div>
            <div className="text-xs text-gray-500">
              Multi-stage NLP with SNOMED mapping, negation detection, validation
            </div>
          </button>
          <button
            onClick={() => setPipelineMode('llm')}
            className={`flex-1 max-w-[220px] p-4 rounded-xl border-2 text-center transition-all ${
              pipelineMode === 'llm'
                ? 'border-nhs-blue bg-blue-50'
                : 'border-gray-200 bg-white hover:border-gray-300'
            }`}
          >
            <div className="text-3xl mb-2">🤖</div>
            <div className="font-bold text-nhs-dark mb-1">Direct LLM</div>
            <div className="text-xs text-gray-500">
              Fast single-shot extraction via Claude AI - simpler but effective
            </div>
          </button>
        </div>
      </div>

      {/* Pipeline Overview */}
      <div className="mt-6 max-w-xl w-full">
        <div className="text-xs font-bold text-gray-500 uppercase tracking-wide text-center mb-3">
          {pipelineMode === 'full' ? 'Full Pipeline Overview' : 'LLM Direct Pipeline'}
        </div>
        {pipelineMode === 'full' ? (
          <div className="flex justify-center items-center gap-0">
            {[
              { icon: '📷', tier: 'Tier 0', label: 'Preprocess' },
              { icon: '🔍', tier: 'Tier 1', label: 'Textract OCR' },
              { icon: '🧬', tier: 'Track A', label: 'SNOMED Map' },
              { icon: '🤖', tier: 'Track B', label: 'AI Summary' },
              { icon: '✅', tier: 'Result', label: 'Auto / Review', isGreen: true },
            ].map((step, i, arr) => (
              <div key={step.tier} className="flex items-center">
                <div className="text-center px-3">
                  <div className="text-2xl">{step.icon}</div>
                  <div className={`text-xs font-semibold mt-1 ${step.isGreen ? 'text-green-600' : 'text-nhs-blue'}`}>
                    {step.tier}
                  </div>
                  <div className="text-xs text-gray-500">{step.label}</div>
                </div>
                {i < arr.length - 1 && (
                  <div className="text-gray-300 text-lg pt-4">→</div>
                )}
              </div>
            ))}
          </div>
        ) : (
          <div className="flex justify-center items-center gap-0">
            {[
              { icon: '📄', tier: 'Upload', label: 'PDF/Image' },
              { icon: '🔍', tier: 'OCR', label: 'Textract' },
              { icon: '🤖', tier: 'Claude', label: 'Extract All' },
              { icon: '✅', tier: 'Result', label: 'Structured', isGreen: true },
            ].map((step, i, arr) => (
              <div key={step.tier} className="flex items-center">
                <div className="text-center px-5">
                  <div className="text-3xl">{step.icon}</div>
                  <div className={`text-xs font-semibold mt-1 ${step.isGreen ? 'text-green-600' : 'text-nhs-blue'}`}>
                    {step.tier}
                  </div>
                  <div className="text-xs text-gray-500">{step.label}</div>
                </div>
                {i < arr.length - 1 && (
                  <div className="text-gray-300 text-2xl pt-5">→</div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
