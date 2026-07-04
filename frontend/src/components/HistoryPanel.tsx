import { useState, useEffect } from 'react';
import { listRuns, deleteRun, getResult, type RunSummary } from '../api/documentApi';
import type { ProcessResult } from '../api/types';

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
      return <span className="px-2 py-0.5 rounded-full text-xs bg-green-100 text-green-700">{percent}%</span>;
    } else if (confidence >= 0.5) {
      return <span className="px-2 py-0.5 rounded-full text-xs bg-yellow-100 text-yellow-700">{percent}%</span>;
    }
    return <span className="px-2 py-0.5 rounded-full text-xs bg-red-100 text-red-700">{percent}%</span>;
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-3xl max-h-[80vh] flex flex-col">
        {/* Header */}
        <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold text-gray-900">Processing History</h2>
            <p className="text-sm text-gray-500">{runs.length} saved runs</p>
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 rounded-lg hover:bg-gray-100 flex items-center justify-center text-gray-500"
          >
            ✕
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-4">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full" />
            </div>
          ) : error ? (
            <div className="text-center py-12 text-red-500">{error}</div>
          ) : runs.length === 0 ? (
            <div className="text-center py-12 text-gray-500">
              <div className="text-4xl mb-3">📭</div>
              <div>No processing runs yet</div>
              <div className="text-sm mt-1">Upload a document to get started</div>
            </div>
          ) : (
            <div className="space-y-2">
              {runs.map((run) => (
                <div
                  key={run.doc_id}
                  onClick={() => handleSelect(run.doc_id)}
                  className={`p-4 rounded-lg border border-gray-200 hover:border-blue-300 hover:bg-blue-50 cursor-pointer transition-colors ${
                    loadingId === run.doc_id ? 'opacity-50' : ''
                  }`}
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-lg">📄</span>
                        <span className="font-medium text-gray-900 truncate">{run.filename}</span>
                        {getConfidenceBadge(run.unified_confidence)}
                      </div>
                      <div className="mt-1 text-sm text-gray-500 flex items-center gap-3">
                        <span>{formatDate(run.processed_at)}</span>
                        <span>•</span>
                        <span>{run.pages_processed} page{run.pages_processed !== 1 ? 's' : ''}</span>
                        {run.letter_type && (
                          <>
                            <span>•</span>
                            <span className="truncate">{run.letter_type}</span>
                          </>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-2 ml-4">
                      {loadingId === run.doc_id ? (
                        <div className="animate-spin w-5 h-5 border-2 border-blue-500 border-t-transparent rounded-full" />
                      ) : (
                        <>
                          <button
                            onClick={(e) => handleDelete(run.doc_id, e)}
                            className="p-2 rounded-lg hover:bg-red-100 text-gray-400 hover:text-red-600 transition-colors"
                            title="Delete"
                          >
                            🗑️
                          </button>
                          <span className="text-gray-400">→</span>
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
            className="px-4 py-2 bg-gray-100 hover:bg-gray-200 rounded-lg text-gray-700 font-medium transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
