import { useCallback, useState, useRef, DragEvent } from 'react';
import type { PipelineMode } from '../api/documentApi';

interface UploadPanelProps {
  onFileUpload: (file: File, mode: PipelineMode) => void;
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
      onFileUpload(file, 'llm');
    }
  }, [onFileUpload]);

  const handleFileChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      onFileUpload(file, 'llm');
    }
  }, [onFileUpload]);

  const handleClick = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  return (
    <div className="flex-1 flex flex-col items-center justify-center p-8 animate-fade-in">
      {/* Upload Card - MediLab Style */}
      <div
        className={`bg-white rounded-lg p-12 max-w-xl w-full text-center cursor-pointer transition-all duration-300 ${
          isDragging
            ? 'border-2 border-[#1977cc] bg-[#1977cc]/5 shadow-medilab-lg'
            : 'border-2 border-dashed border-gray-300 hover:border-[#1977cc] hover:shadow-medilab'
        }`}
        onDragOver={handleDragOver}
        onDragEnter={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={handleClick}
      >
        <div className="w-20 h-20 mx-auto mb-5 bg-[#1977cc]/10 rounded-full flex items-center justify-center">
          <span className="text-4xl">📋</span>
        </div>
        <h2 className="text-2xl font-semibold text-[#2c4964] mb-3 font-heading">Upload Clinical Document</h2>
        <p className="text-[#444444] text-sm mb-6 leading-relaxed">
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
        <p className="text-xs text-gray-400 mt-4">
          Supported: JPEG, PNG, PDF, TIFF
        </p>
      </div>

      {/* Error Message - MediLab Style */}
      {error && (
        <div className="mt-4 p-4 bg-[#df1529]/5 border border-[#df1529]/20 rounded-lg text-[#df1529] text-sm max-w-xl w-full">
          <span className="font-semibold">Error:</span> {error}
        </div>
      )}

      {/* Pipeline Overview - MediLab Style */}
      <div className="mt-8 max-w-xl w-full">
        <div className="text-xs font-bold text-[#2c4964] uppercase tracking-wider text-center mb-4 font-heading">
          AI-Powered Extraction Pipeline
        </div>
        <div className="flex justify-center items-center gap-0 bg-white rounded-lg p-4 shadow-medilab">
          {[
            { icon: '📄', tier: 'Upload', label: 'PDF/Image' },
            { icon: '🔍', tier: 'OCR', label: 'Textract' },
            { icon: '🤖', tier: 'Claude AI', label: 'Extract' },
            { icon: '✅', tier: 'Result', label: 'Structured', isGreen: true },
          ].map((step, i, arr) => (
            <div key={step.tier} className="flex items-center">
              <div className="text-center px-5">
                <div className="w-12 h-12 mx-auto mb-2 bg-gray-50 rounded-full flex items-center justify-center">
                  <span className="text-2xl">{step.icon}</span>
                </div>
                <div className={`text-xs font-semibold ${step.isGreen ? 'text-[#059652]' : 'text-[#1977cc]'}`}>
                  {step.tier}
                </div>
                <div className="text-xs text-[#444444]">{step.label}</div>
              </div>
              {i < arr.length - 1 && (
                <div className="text-[#1977cc] text-xl">→</div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
