import { useCallback, useState, useRef, DragEvent } from 'react';

interface UploadPanelProps {
  onFileUpload: (file: File) => void;
  error: string | null;
}

const ALLOWED_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.pdf', '.tiff', '.tif'];

export default function UploadPanel({ onFileUpload, error }: UploadPanelProps) {
  const [isDragging, setIsDragging] = useState(false);
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
      onFileUpload(file);
    }
  }, [onFileUpload]);

  const handleFileChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      onFileUpload(file);
    }
  }, [onFileUpload]);

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

      {/* Pipeline Overview */}
      <div className="mt-8 max-w-xl w-full">
        <div className="text-xs font-bold text-gray-500 uppercase tracking-wide text-center mb-3">
          Pipeline Overview
        </div>
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
      </div>
    </div>
  );
}
