import { useState, useEffect } from 'react';
import type { ProcessResult } from '../api/types';

interface DocumentViewerProps {
  result: ProcessResult;
  file: File | null;
}

export default function DocumentViewer({ result, file }: DocumentViewerProps) {
  const [fileUrl, setFileUrl] = useState<string | null>(null);
  const [fileType, setFileType] = useState<'pdf' | 'image' | null>(null);

  useEffect(() => {
    if (file) {
      const url = URL.createObjectURL(file);
      setFileUrl(url);

      const ext = file.name.split('.').pop()?.toLowerCase();
      if (ext === 'pdf') {
        setFileType('pdf');
      } else if (['jpg', 'jpeg', 'png', 'gif', 'webp', 'tiff', 'tif'].includes(ext || '')) {
        setFileType('image');
      }

      return () => {
        URL.revokeObjectURL(url);
      };
    }
  }, [file]);

  const confPercent = Math.round((result.unified_confidence || 0) * 100);
  const threshold = result.confidence_threshold || 0.75;
  const isHighConf = result.unified_confidence >= threshold;

  const statusBadge = isHighConf ? (
    <span className="inline-flex items-center gap-1 px-3 py-1 rounded-full text-sm font-medium bg-green-100 text-green-800 border border-green-200">
      ✅ High Confidence ({confPercent}%)
    </span>
  ) : result.unified_confidence >= threshold * 0.75 ? (
    <span className="inline-flex items-center gap-1 px-3 py-1 rounded-full text-sm font-medium bg-yellow-100 text-yellow-800 border border-yellow-200">
      ⚠️ Check Outputs ({confPercent}%)
    </span>
  ) : (
    <span className="inline-flex items-center gap-1 px-3 py-1 rounded-full text-sm font-medium bg-red-100 text-red-800 border border-red-200">
      ⚠️ Low Confidence ({confPercent}%)
    </span>
  );

  return (
    <div className="flex-[1.2] bg-white border-r border-gray-200 flex flex-col overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 border-b border-gray-200">
        <div className="flex items-center gap-2 mb-2">
          <span className="text-lg">📄</span>
          <h3 className="text-sm font-semibold text-gray-800 truncate flex-1">
            {result.filename}
          </h3>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-xs text-gray-500">
            {result.pages_processed} page{result.pages_processed !== 1 ? 's' : ''}
          </span>
          {statusBadge}
        </div>
      </div>

      {/* Document viewer */}
      <div className="flex-1 overflow-hidden bg-gray-100">
        {fileUrl && fileType === 'pdf' ? (
          <iframe
            src={fileUrl}
            className="w-full h-full border-0"
            title="PDF Preview"
          />
        ) : fileUrl && fileType === 'image' ? (
          <div className="w-full h-full overflow-auto p-4 flex items-start justify-center">
            <img
              src={fileUrl}
              alt="Document preview"
              className="max-w-full rounded shadow-lg bg-white"
            />
          </div>
        ) : (
          <div className="w-full h-full flex items-center justify-center">
            <div className="text-center text-gray-500">
              <div className="text-4xl mb-3">📄</div>
              <div className="text-sm font-medium">{result.filename}</div>
              <div className="text-xs text-gray-400 mt-1">
                {result.pages_processed} page{result.pages_processed !== 1 ? 's' : ''} processed
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
