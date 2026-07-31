import { useState, useEffect } from 'react';
import type { ProcessResult } from '../api/types';
import { IconDocument } from './icons/Icons';

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
    <span className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full text-sm font-medium bg-[#059652]/10 text-[#059652] border border-[#059652]/20">
      <span className="w-2 h-2 bg-[#059652] rounded-full"></span>
      High Confidence ({confPercent}%)
    </span>
  ) : result.unified_confidence >= threshold * 0.75 ? (
    <span className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full text-sm font-medium bg-[#ffc107]/10 text-[#b38600] border border-[#ffc107]/30">
      <span className="w-2 h-2 bg-[#ffc107] rounded-full"></span>
      Check Outputs ({confPercent}%)
    </span>
  ) : (
    <span className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full text-sm font-medium bg-[#df1529]/10 text-[#df1529] border border-[#df1529]/20">
      <span className="w-2 h-2 bg-[#df1529] rounded-full"></span>
      Low Confidence ({confPercent}%)
    </span>
  );

  return (
    <div className="w-full h-full bg-white flex flex-col overflow-hidden rounded-xl">
      {/* Header */}
      <div className="px-5 py-4 border-b border-gray-100">
        <div className="flex items-center gap-3 mb-3">
          <div className="w-10 h-10 bg-[#1977cc]/10 rounded-full flex items-center justify-center text-[#1977cc]">
            <IconDocument size={20} />
          </div>
          <h3 className="text-sm font-semibold text-[#2c4964] truncate flex-1">
            {result.filename}
          </h3>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-xs text-gray-500">
            {result.pages_processed} page{result.pages_processed !== 1 ? 's' : ''} processed
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
          <div className="w-full h-full overflow-auto p-6 flex items-start justify-center">
            <img
              src={fileUrl}
              alt="Document preview"
              className="max-w-full rounded-lg shadow-lg bg-white"
            />
          </div>
        ) : (
          <div className="w-full h-full flex items-center justify-center">
            <div className="text-center text-[#444444]">
              <div className="w-20 h-20 mx-auto mb-4 bg-[#1977cc]/10 rounded-full flex items-center justify-center text-[#1977cc]">
                <IconDocument size={40} />
              </div>
              <div className="text-base font-medium text-[#2c4964]">{result.filename}</div>
              <div className="text-sm text-gray-500 mt-2">
                {result.pages_processed} page{result.pages_processed !== 1 ? 's' : ''} processed
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
