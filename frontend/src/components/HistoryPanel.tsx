import { useState, useEffect } from 'react';
import { listRuns, deleteRun, getResult, type RunSummary } from '../api/documentApi';
import type { ProcessResult } from '../api/types';
import { IconDocument, IconTrash, IconArrowRight, IconAlertCircle } from './icons/Icons';

interface HistoryPanelProps {
  onSelectRun: (result: ProcessResult) => void;
  onClose: () => void;
}

export default function HistoryPanel({ onSelectRun, onClose }: HistoryPanelProps) {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [loadingId, setLoadingId] = useState<string | null>(null);

  const fetchRuns = async () => {
    try {
      setLoading(true);
      const data = await listRuns();
      setRuns(data.runs);
      setError(null);
    } catch (err) {
      setError('Failed to load history');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchRuns();
  }, []);

  const handleSelect = async (docId: string) => {
    try {
      setLoadingId(docId);
      const result = await getResult(docId);
      onSelectRun(result);
    } catch (err) {
      setError('Failed to load document');
    } finally {
      setLoadingId(null);
    }
  };

  const handleDelete = async (docId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm('Delete this run? This cannot be undone.')) return;

    try {
      await deleteRun(docId);
      setRuns(runs.filter(r => r.doc_id !== docId));
    } catch (err) {
      setError('Failed to delete run');
    }
  };

  const formatDate = (dateStr: string) => {
    if (!dateStr) return 'Unknown';
    try {
      return new Date(dateStr).toLocaleString('en-GB', {
        timeZone: 'Europe/London',
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      });
    } catch {
      return dateStr;
    }
  };

  const getConfidenceBadge = (confidence: number) => {
    const percent = Math.round(confidence * 100);
    if (confidence >= 0.75) {
      return <span className="px-3 py-1 rounded-full text-xs font-medium bg-[#059652]/10 text-[#059652] border border-[#059652]/20">{percent}%</span>;
    } else if (confidence >= 0.5) {
      return <span className="px-3 py-1 rounded-full text-xs font-medium bg-[#ffc107]/10 text-[#b38600] border border-[#ffc107]/30">{percent}%</span>;
    }
    return <span className="px-3 py-1 rounded-full text-xs font-medium bg-[#df1529]/10 text-[#df1529] border border-[#df1529]/20">{percent}%</span>;
  };

  return (
    <div className="fixed inset-0 bg-black/40 backdrop-blur-sm flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-3xl max-h-[80vh] flex flex-col">
        {/* Header */}
        <div className="px-6 py-5 border-b border-gray-200 flex items-center justify-between">
          <div>
            <h2 className="text-xl font-semibold text-[#2c4964]">Processing History</h2>
            <p className="text-sm text-gray-500 mt-1">{runs.length} saved runs</p>
          </div>
          <button
            onClick={onClose}
            className="w-10 h-10 rounded-full hover:bg-gray-100 flex items-center justify-center text-gray-500 hover:text-[#2c4964] transition-all duration-300"
          >
            <span className="text-xl font-light">×</span>
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-5">
          {loading ? (
            <div className="flex items-center justify-center py-16">
              <div className="relative">
                <div className="w-12 h-12 border-4 border-[#1977cc]/20 rounded-full" />
                <div className="absolute top-0 left-0 w-12 h-12 border-4 border-transparent border-t-[#1977cc] rounded-full animate-spin" />
              </div>
            </div>
          ) : error ? (
            <div className="text-center py-16">
              <div className="w-16 h-16 mx-auto mb-4 bg-[#df1529]/10 rounded-full flex items-center justify-center text-[#df1529]">
                <IconAlertCircle size={32} />
              </div>
              <div className="text-[#df1529] font-medium">{error}</div>
            </div>
          ) : runs.length === 0 ? (
            <div className="text-center py-16">
              <div className="w-20 h-20 mx-auto mb-4 bg-[#1977cc]/10 rounded-full flex items-center justify-center text-[#1977cc]">
                <IconDocument size={40} />
              </div>
              <div className="text-[#2c4964] font-medium">No processing runs yet</div>
              <div className="text-sm text-gray-500 mt-2">Upload a document to get started</div>
            </div>
          ) : (
            <div className="space-y-3">
              {runs.map((run) => (
                <div
                  key={run.doc_id}
                  onClick={() => handleSelect(run.doc_id)}
                  className={`p-5 rounded-lg border border-gray-100 hover:border-[#1977cc]/30 hover:shadow-md cursor-pointer transition-all duration-300 ${
                    loadingId === run.doc_id ? 'opacity-50' : ''
                  }`}
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-3">
                        <div className="w-10 h-10 bg-[#1977cc]/10 rounded-full flex items-center justify-center flex-shrink-0 text-[#1977cc]">
                          <IconDocument size={18} />
                        </div>
                        <span className="font-medium text-[#2c4964] truncate">{run.filename}</span>
                        {getConfidenceBadge(run.unified_confidence)}
                      </div>
                      <div className="mt-2 text-sm text-gray-500 flex items-center gap-3 ml-13">
                        <span>{formatDate(run.processed_at)}</span>
                        <span className="text-[#1977cc]">•</span>
                        <span>{run.pages_processed} page{run.pages_processed !== 1 ? 's' : ''}</span>
                        {run.letter_type && (
                          <>
                            <span className="text-[#1977cc]">•</span>
                            <span className="truncate">{run.letter_type}</span>
                          </>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-2 ml-4">
                      {loadingId === run.doc_id ? (
                        <div className="w-8 h-8 border-2 border-[#1977cc] border-t-transparent rounded-full animate-spin" />
                      ) : (
                        <>
                          <button
                            onClick={(e) => handleDelete(run.doc_id, e)}
                            className="w-9 h-9 rounded-full hover:bg-[#df1529]/10 flex items-center justify-center text-gray-400 hover:text-[#df1529] transition-all duration-300"
                            title="Delete"
                          >
                            <IconTrash size={16} />
                          </button>
                          <span className="text-[#1977cc]">
                            <IconArrowRight size={18} />
                          </span>
                        </>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-gray-200 flex justify-end">
          <button
            onClick={onClose}
            className="btn-secondary"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
