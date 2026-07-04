import { useState, useEffect } from 'react';
import type { ProcessResult } from '../api/types';

interface DocumentViewerProps {
  result: ProcessResult;
  file: File | null;
}

export default function DocumentViewer({ result, file }: DocumentViewerProps) {
  const [localPreview, setLocalPreview] = useState<string | null>(null);

  useEffect(() => {
    if (!result.preview_pages?.length && file) {
      const ext = file.name.split('.').pop()?.toLowerCase();
      if (['jpg', 'jpeg', 'png'].includes(ext || '')) {
        const reader = new FileReader();
        reader.onload = (e) => {
          setLocalPreview(e.target?.result as string);
        };
        reader.readAsDataURL(file);
      }
    }
    return () => {
      setLocalPreview(null);
    };
  }, [file, result.preview_pages]);

  const pages = result.preview_pages || [];
  const confPercent = Math.round((result.unified_confidence || 0) * 100);
  const threshold = result.confidence_threshold || 0.75;
  const isHighConf = result.unified_confidence >= threshold;

  const statusBadge = isHighConf ? (
    <span className="badge badge-processed">✅ High Confidence ({confPercent}%)</span>
  ) : result.unified_confidence >= threshold * 0.75 ? (
    <span className="badge badge-review">⚠️ Check Outputs ({confPercent}%)</span>
  ) : (
    <span className="badge badge-review">⚠️ Low Confidence ({confPercent}%)</span>
  );

  return (
    <div className="flex-[1.2] bg-white border-r border-gray-200 flex flex-col overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 border-b border-gray-200 flex items-center gap-2">
        <span className="text-lg">📄</span>
        <h3 className="text-sm font-semibold text-nhs-dark">
          {result.filename}
          {result.pages_processed > 1 && ` (${result.pages_processed} pages)`}
        </h3>
        <div className="ml-auto">{statusBadge}</div>
      </div>

      {/* Page viewer */}
      <div className="flex-1 overflow-y-auto bg-gray-100 p-4">
        <div className="flex flex-col items-center gap-3">
          {pages.length > 0 ? (
            pages.map((url, i) => (
              <div key={i} className="w-full">
                <div className="text-xs text-gray-400 text-center mb-1">
                  Page {i + 1} of {pages.length}
                </div>
                <img
                  src={url}
                  alt={`Page ${i + 1}`}
                  className="w-full rounded shadow-lg bg-white"
                  onError={(e) => {
                    (e.target as HTMLImageElement).style.display = 'none';
                  }}
                />
              </div>
            ))
          ) : localPreview ? (
            <img
              src={localPreview}
              alt="Document preview"
              className="w-full rounded shadow-lg bg-white"
            />
          ) : (
            <div className="text-gray-400 text-sm">Preview not available</div>
          )}
        </div>
      </div>
    </div>
  );
}
