import { useEffect, useState } from 'react';
import { useSearchParams, Link } from 'react-router-dom';
import {
  FileText,
  CheckCircle,
  XCircle,
  AlertTriangle,
  Download,
  ChevronDown,
  ChevronRight,
  Flag,
  Send,
  ArrowLeft
} from 'lucide-react';
import { api, endpoints } from '../api/client';
import type { PipelineResultResponse } from '../types/api';

export function Review() {
  const [searchParams] = useSearchParams();
  const jobId = searchParams.get('jobId');
  const [result, setResult] = useState<PipelineResultResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedEntities, setExpandedEntities] = useState<Set<number>>(new Set());
  const [editedSummary, setEditedSummary] = useState('');

  useEffect(() => {
    if (!jobId) return;

    const fetchResult = async () => {
      try {
        const response = await api.get<PipelineResultResponse>(endpoints.pipeline.result(jobId));
        setResult(response.data);
        if (response.data.track_b?.summary) {
          setEditedSummary(response.data.track_b.summary);
        }
      } catch (err: any) {
        setError(err.response?.data?.detail || 'Failed to load results');
      } finally {
        setLoading(false);
      }
    };

    fetchResult();
  }, [jobId]);

  const toggleEntity = (idx: number) => {
    const newExpanded = new Set(expandedEntities);
    if (newExpanded.has(idx)) {
      newExpanded.delete(idx);
    } else {
      newExpanded.add(idx);
    }
    setExpandedEntities(newExpanded);
  };

  if (!jobId) {
    return (
      <div className="text-center py-12">
        <FileText className="h-16 w-16 text-gray-300 mx-auto mb-4" />
        <h2 className="text-xl font-semibold text-gray-700 mb-2">No Document Selected</h2>
        <p className="text-gray-500 mb-4">Process a document first to review results.</p>
        <Link to="/upload" className="btn-primary">Upload Document</Link>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="max-w-2xl mx-auto">
        <div className="card border-red-200 bg-red-50">
          <div className="flex items-start">
            <XCircle className="h-6 w-6 text-red-500 mt-0.5" />
            <div className="ml-3">
              <h3 className="font-semibold text-red-800">Error Loading Results</h3>
              <p className="text-red-700 mt-1">{error}</p>
            </div>
          </div>
          <Link to="/upload" className="btn-secondary mt-4 inline-block">
            <ArrowLeft className="h-4 w-4 mr-2 inline" />
            Upload New Document
          </Link>
        </div>
      </div>
    );
  }

  const snomed_codes = result?.track_a?.snomed_codes || [];
  const entities = result?.track_a?.entities || [];
  const summary = result?.track_b?.summary || '';
  const keyFindings = result?.track_b?.key_findings || [];
  const actionPlans = result?.track_b?.action_plans || {};

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <Link to={`/processing?jobId=${jobId}`} className="text-blue-600 hover:text-blue-700 text-sm flex items-center mb-2">
            <ArrowLeft className="h-4 w-4 mr-1" />
            Back to Processing
          </Link>
          <h1 className="text-2xl font-bold text-gray-900">Clinician Review</h1>
          <p className="text-sm text-gray-500">Document: {result?.document_name}</p>
        </div>
        <div className="flex items-center space-x-2">
          <span className={`px-3 py-1 rounded-full text-sm font-medium ${
            result?.status === 'completed' ? 'bg-green-100 text-green-800' : 'bg-yellow-100 text-yellow-800'
          }`}>
            {result?.status}
          </span>
        </div>
      </div>

      {/* Processing Stats */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <div className="card text-center">
          <p className="text-2xl font-bold text-blue-600">{result?.tier1?.pages_processed || 0}</p>
          <p className="text-xs text-gray-500">Pages</p>
        </div>
        <div className="card text-center">
          <p className="text-2xl font-bold text-green-600">{snomed_codes.length}</p>
          <p className="text-xs text-gray-500">SNOMED Codes</p>
        </div>
        <div className="card text-center">
          <p className="text-2xl font-bold text-purple-600">{entities.length}</p>
          <p className="text-xs text-gray-500">Entities</p>
        </div>
        <div className="card text-center">
          <p className="text-2xl font-bold text-orange-600">
            {result?.tier1?.average_confidence?.toFixed(1) || 'N/A'}%
          </p>
          <p className="text-xs text-gray-500">OCR Confidence</p>
        </div>
        <div className="card text-center">
          <p className="text-2xl font-bold text-gray-700">
            {((result?.total_processing_time_ms || 0) / 1000).toFixed(1)}s
          </p>
          <p className="text-xs text-gray-500">Total Time</p>
        </div>
      </div>

      {/* Main Content - Two Columns */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Left Column - Clinical Summary */}
        <div className="space-y-4">
          <div className="card">
            <h2 className="text-lg font-semibold mb-4 flex items-center">
              <FileText className="h-5 w-5 mr-2 text-blue-600" />
              Clinical Summary
            </h2>

            {summary ? (
              <div className="space-y-4">
                <div className="bg-blue-50 border border-blue-100 rounded-lg p-4">
                  <p className="text-gray-700 leading-relaxed whitespace-pre-wrap">{summary}</p>
                </div>
                <details className="group">
                  <summary className="cursor-pointer text-sm text-blue-600 hover:text-blue-700 flex items-center">
                    <ChevronRight className="h-4 w-4 mr-1 group-open:rotate-90 transition-transform" />
                    Edit Summary
                  </summary>
                  <div className="mt-3">
                    <textarea
                      value={editedSummary}
                      onChange={(e) => setEditedSummary(e.target.value)}
                      className="w-full h-48 p-3 border border-gray-200 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none text-sm"
                      placeholder="Edit clinical summary..."
                    />
                    <div className="mt-2 flex justify-end">
                      <button className="btn-primary text-sm">
                        Save Changes
                      </button>
                    </div>
                  </div>
                </details>
              </div>
            ) : (
              <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
                <div className="flex items-start">
                  <AlertTriangle className="h-5 w-5 text-yellow-500 mt-0.5" />
                  <div className="ml-3">
                    <p className="text-sm text-yellow-700">
                      Clinical summary not available. Track B may have failed.
                    </p>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Key Findings */}
          {keyFindings.length > 0 && (
            <div className="card">
              <h3 className="font-semibold mb-3 flex items-center">
                <span className="text-lg mr-2">🔍</span>
                Key Clinical Findings
              </h3>
              <div className="bg-green-50 rounded-lg p-4">
                <ul className="space-y-3">
                  {keyFindings.map((finding, idx) => (
                    <li key={idx} className="flex items-start">
                      <CheckCircle className="h-5 w-5 text-green-600 mt-0.5 mr-3 flex-shrink-0" />
                      <span className="text-gray-700">{finding}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          )}

          {/* Action Plans */}
          {Object.keys(actionPlans).length > 0 && (
            <div className="card">
              <h3 className="font-semibold mb-4 flex items-center">
                <span className="text-lg mr-2">📋</span>
                Action Plans
              </h3>
              <div className="space-y-4">
                {actionPlans.clinician && actionPlans.clinician.length > 0 && (
                  <div className="bg-blue-50 rounded-lg p-4 border-l-4 border-blue-500">
                    <h4 className="text-sm font-bold text-blue-800 mb-3 flex items-center">
                      <span className="mr-2">👨‍⚕️</span>
                      For Clinician
                    </h4>
                    <ul className="space-y-2">
                      {actionPlans.clinician.map((action, idx) => (
                        <li key={idx} className="flex items-start text-sm text-blue-900">
                          <span className="w-5 h-5 bg-blue-200 rounded-full flex items-center justify-center text-xs font-bold mr-2 flex-shrink-0">{idx + 1}</span>
                          <span>{action}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {actionPlans.patient && actionPlans.patient.length > 0 && (
                  <div className="bg-green-50 rounded-lg p-4 border-l-4 border-green-500">
                    <h4 className="text-sm font-bold text-green-800 mb-3 flex items-center">
                      <span className="mr-2">🧑‍🦱</span>
                      For Patient
                    </h4>
                    <ul className="space-y-2">
                      {actionPlans.patient.map((action, idx) => (
                        <li key={idx} className="flex items-start text-sm text-green-900">
                          <span className="w-5 h-5 bg-green-200 rounded-full flex items-center justify-center text-xs font-bold mr-2 flex-shrink-0">{idx + 1}</span>
                          <span>{action}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {actionPlans.pharmacist && actionPlans.pharmacist.length > 0 && (
                  <div className="bg-purple-50 rounded-lg p-4 border-l-4 border-purple-500">
                    <h4 className="text-sm font-bold text-purple-800 mb-3 flex items-center">
                      <span className="mr-2">💊</span>
                      For Pharmacist
                    </h4>
                    <ul className="space-y-2">
                      {actionPlans.pharmacist.map((action, idx) => (
                        <li key={idx} className="flex items-start text-sm text-purple-900">
                          <span className="w-5 h-5 bg-purple-200 rounded-full flex items-center justify-center text-xs font-bold mr-2 flex-shrink-0">{idx + 1}</span>
                          <span>{action}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Right Column - SNOMED Codes */}
        <div className="card">
          <h2 className="text-lg font-semibold mb-4 flex items-center">
            <span className="text-xl mr-2">🧬</span>
            SNOMED CT Mapping
            {snomed_codes.length > 0 && (
              <span className="ml-2 text-sm font-normal text-gray-500">
                ({snomed_codes.length} codes found)
              </span>
            )}
          </h2>

          {snomed_codes.length > 0 ? (
            <div className="space-y-2 max-h-[600px] overflow-y-auto pr-1">
              {snomed_codes.map((code, idx) => (
                <div
                  key={idx}
                  className={`border rounded-lg overflow-hidden ${
                    code.score >= 0.8 ? 'border-green-300 bg-green-50/30' :
                    code.score >= 0.5 ? 'border-blue-300 bg-blue-50/30' :
                    'border-gray-200'
                  }`}
                >
                  <button
                    onClick={() => toggleEntity(idx)}
                    className="w-full flex items-center justify-between p-3 hover:bg-white/50 transition-colors text-left"
                  >
                    <div className="flex items-center flex-1 min-w-0">
                      {expandedEntities.has(idx) ? (
                        <ChevronDown className="h-4 w-4 text-gray-400 mr-2 flex-shrink-0" />
                      ) : (
                        <ChevronRight className="h-4 w-4 text-gray-400 mr-2 flex-shrink-0" />
                      )}
                      <div className="min-w-0">
                        <p className="font-medium text-gray-900 truncate">{code.description || code.source_text}</p>
                        <p className="text-xs text-gray-500 font-mono">{code.code}</p>
                      </div>
                    </div>
                    <span className={`ml-2 text-xs px-2 py-1 rounded-full font-medium flex-shrink-0 ${
                      code.score >= 0.8 ? 'bg-green-100 text-green-800' :
                      code.score >= 0.5 ? 'bg-blue-100 text-blue-800' :
                      code.score >= 0.3 ? 'bg-yellow-100 text-yellow-800' :
                      'bg-gray-100 text-gray-600'
                    }`}>
                      {(code.score * 100).toFixed(0)}%
                    </span>
                  </button>

                  {expandedEntities.has(idx) && (
                    <div className="px-3 pb-3 pt-1 bg-white/80 border-t border-gray-100">
                      <div className="space-y-2 text-sm">
                        <div className="flex items-center">
                          <span className="text-gray-500 w-24">SNOMED Code:</span>
                          <span className="font-mono text-blue-600 font-medium">{code.code}</span>
                        </div>
                        <div className="flex items-center">
                          <span className="text-gray-500 w-24">Source Text:</span>
                          <span className="text-gray-700 italic">"{code.source_text}"</span>
                        </div>
                        <div className="flex items-center">
                          <span className="text-gray-500 w-24">Confidence:</span>
                          <div className="flex items-center">
                            <div className="w-24 h-2 bg-gray-200 rounded-full mr-2">
                              <div
                                className={`h-2 rounded-full ${
                                  code.score >= 0.8 ? 'bg-green-500' :
                                  code.score >= 0.5 ? 'bg-blue-500' :
                                  'bg-yellow-500'
                                }`}
                                style={{ width: `${code.score * 100}%` }}
                              />
                            </div>
                            <span className="font-medium">{(code.score * 100).toFixed(1)}%</span>
                          </div>
                        </div>
                      </div>
                      <div className="mt-3 pt-3 border-t border-gray-100">
                        <label className="text-xs text-gray-500 block mb-1">Clinician Review Status</label>
                        <select className="text-sm border border-gray-200 rounded px-3 py-1.5 w-full bg-white">
                          <option value="pending">⏳ Pending Review</option>
                          <option value="approved">✅ Approved</option>
                          <option value="incorrect">❌ Incorrect Code</option>
                          <option value="clarify">❓ Needs Clarification</option>
                        </select>
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
              <div className="flex items-start">
                <AlertTriangle className="h-5 w-5 text-yellow-500 mt-0.5" />
                <div className="ml-3">
                  <p className="text-sm text-yellow-700">
                    No high-confidence SNOMED codes found. This could mean:
                  </p>
                  <ul className="text-sm text-yellow-600 mt-2 list-disc list-inside">
                    <li>The document contains limited medical terminology</li>
                    <li>OCR quality affected entity detection</li>
                    <li>Medical entities didn't match SNOMED concepts with sufficient confidence</li>
                  </ul>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Tier Status Details */}
      <div className="card">
        <h3 className="font-semibold mb-4">Processing Details</h3>
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
          {[
            { name: 'Tier 0', data: result?.tier0, key: 'tier0' },
            { name: 'Tier 1', data: result?.tier1, key: 'tier1' },
            { name: 'Tier 2', data: result?.tier2, key: 'tier2' },
            { name: 'Tier 3', data: result?.tier3, key: 'tier3' },
            { name: 'Track A', data: result?.track_a, key: 'track_a' },
            { name: 'Track B', data: result?.track_b, key: 'track_b' },
          ].map((tier) => (
            <div
              key={tier.key}
              className={`p-3 rounded-lg text-center ${
                tier.data?.status === 'success' ? 'bg-green-50' :
                tier.data?.status === 'failed' ? 'bg-red-50' :
                tier.data ? 'bg-yellow-50' : 'bg-gray-50'
              }`}
            >
              <div className="flex items-center justify-center mb-1">
                {tier.data?.status === 'success' ? (
                  <CheckCircle className="h-5 w-5 text-green-500" />
                ) : tier.data?.status === 'failed' ? (
                  <XCircle className="h-5 w-5 text-red-500" />
                ) : tier.data ? (
                  <AlertTriangle className="h-5 w-5 text-yellow-500" />
                ) : (
                  <div className="h-5 w-5 rounded-full border-2 border-gray-300" />
                )}
              </div>
              <p className="text-xs font-medium">{tier.name}</p>
              {tier.data?.processing_time_ms && (
                <p className="text-xs text-gray-500">
                  {(tier.data.processing_time_ms / 1000).toFixed(1)}s
                </p>
              )}
              {tier.data?.duration_ms && (
                <p className="text-xs text-gray-500">
                  {(tier.data.duration_ms / 1000).toFixed(1)}s
                </p>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Action Buttons */}
      <div className="flex flex-wrap gap-3">
        <button className="btn-primary flex items-center">
          <CheckCircle className="h-4 w-4 mr-2" />
          Approve & Export to EMIS
        </button>
        <button className="btn-secondary flex items-center">
          <Flag className="h-4 w-4 mr-2" />
          Flag for Specialist Review
        </button>
        <button className="btn-secondary flex items-center">
          <Download className="h-4 w-4 mr-2" />
          Download Audit Trail
        </button>
        <Link to="/upload" className="btn-secondary flex items-center">
          <Send className="h-4 w-4 mr-2" />
          Process Another Document
        </Link>
      </div>
    </div>
  );
}
