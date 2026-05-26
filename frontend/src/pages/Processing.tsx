import { useSearchParams, Link } from 'react-router-dom';
import { ArrowRight, FileText, RefreshCw } from 'lucide-react';
import { ProcessingStatus } from '../components/ProcessingStatus';
import { useJobStatus } from '../hooks/useJobStatus';

export function Processing() {
  const [searchParams] = useSearchParams();
  const jobId = searchParams.get('jobId');
  const { status, result, isPolling, error } = useJobStatus(jobId);

  if (!jobId) {
    return (
      <div className="text-center py-12">
        <FileText className="h-16 w-16 text-gray-300 mx-auto mb-4" />
        <h2 className="text-xl font-semibold text-gray-700 mb-2">No Job Selected</h2>
        <p className="text-gray-500 mb-4">Upload a document to start processing.</p>
        <Link to="/upload" className="btn-primary">
          Upload Document
        </Link>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Processing</h1>
          <p className="text-sm text-gray-500 mt-1">Job ID: {jobId}</p>
        </div>
        {isPolling && (
          <div className="flex items-center text-blue-600">
            <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
            <span className="text-sm">Polling for updates...</span>
          </div>
        )}
      </div>

      {status && (
        <ProcessingStatus
          currentTier={status.current_tier}
          progress={status.progress_percent}
          tiers={status.tiers}
          status={status.status}
          error={status.error || error || undefined}
        />
      )}

      {result && status?.status === 'completed' && (
        <div className="space-y-6">
          {result.track_a && (
            <div className="card">
              <h3 className="text-lg font-semibold mb-4">SNOMED Codes (Track A)</h3>
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Code</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Description</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Source</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Score</th>
                    </tr>
                  </thead>
                  <tbody className="bg-white divide-y divide-gray-200">
                    {result.track_a.snomed_codes.slice(0, 10).map((code, idx) => (
                      <tr key={idx}>
                        <td className="px-4 py-3 text-sm font-mono text-blue-600">{code.code}</td>
                        <td className="px-4 py-3 text-sm text-gray-900">{code.description}</td>
                        <td className="px-4 py-3 text-sm text-gray-500">{code.source_text}</td>
                        <td className="px-4 py-3 text-sm text-gray-500">{(code.score * 100).toFixed(1)}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {result.track_b && (
            <div className="card">
              <h3 className="text-lg font-semibold mb-4">Clinical Summary (Track B)</h3>
              <div className="prose prose-sm max-w-none">
                <div className="bg-gray-50 p-4 rounded-lg whitespace-pre-wrap text-gray-700">
                  {result.track_b.summary}
                </div>
              </div>
              {result.track_b.key_findings && result.track_b.key_findings.length > 0 && (
                <div className="mt-4">
                  <h4 className="font-medium text-gray-900 mb-2">Key Findings</h4>
                  <ul className="list-disc list-inside text-sm text-gray-600 space-y-1">
                    {result.track_b.key_findings.map((finding, idx) => (
                      <li key={idx}>{finding}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}

          <div className="card">
            <h3 className="text-lg font-semibold mb-4">Processing Summary</h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="text-center p-4 bg-gray-50 rounded-lg">
                <p className="text-2xl font-bold text-blue-600">
                  {result.tier1?.pages_processed || 0}
                </p>
                <p className="text-sm text-gray-500">Pages Processed</p>
              </div>
              <div className="text-center p-4 bg-gray-50 rounded-lg">
                <p className="text-2xl font-bold text-green-600">
                  {result.track_a?.snomed_codes?.length || 0}
                </p>
                <p className="text-sm text-gray-500">SNOMED Codes</p>
              </div>
              <div className="text-center p-4 bg-gray-50 rounded-lg">
                <p className="text-2xl font-bold text-purple-600">
                  {result.track_a?.entities?.length || 0}
                </p>
                <p className="text-sm text-gray-500">Medical Entities</p>
              </div>
              <div className="text-center p-4 bg-gray-50 rounded-lg">
                <p className="text-2xl font-bold text-gray-700">
                  {(result.total_processing_time_ms / 1000).toFixed(1)}s
                </p>
                <p className="text-sm text-gray-500">Total Time</p>
              </div>
            </div>
          </div>
        </div>
      )}

      <div className="flex justify-between">
        <Link to="/upload" className="btn-secondary">
          Upload Another
        </Link>
        {result && (
          <Link to={`/review?jobId=${jobId}`} className="btn-primary flex items-center">
            View Full Results
            <ArrowRight className="h-4 w-4 ml-2" />
          </Link>
        )}
      </div>
    </div>
  );
}
