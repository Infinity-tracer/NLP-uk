import { CheckCircle, Circle, Loader2, XCircle, AlertTriangle } from 'lucide-react';
import type { TierStatus, ProcessingStatus as Status } from '../types/api';

interface ProcessingStatusProps {
  currentTier?: string;
  progress: number;
  tiers: TierStatus[];
  status: Status;
  error?: string;
}

const tierLabels: Record<string, string> = {
  tier0: 'Preprocessing',
  tier1: 'Text Extraction (Textract)',
  tier2: 'Structure Refinement (LayoutLMv3)',
  tier3: 'Vision-LLM Correction',
  track_a: 'SNOMED Mapping',
  track_b: 'Clinical Summarization',
};

const allTiers = ['tier0', 'tier1', 'tier2', 'tier3', 'track_a', 'track_b'];

export function ProcessingStatus({ currentTier, progress, tiers, status, error }: ProcessingStatusProps) {
  const getTierStatus = (tier: string): 'pending' | 'processing' | 'completed' | 'failed' | 'review' => {
    const tierData = tiers.find((t) => t.tier === tier);
    if (tierData) {
      if (tierData.status === 'completed' || tierData.status === 'success') return 'completed';
      // review_required is a valid completion state, not a failure
      if (tierData.status === 'review_required' || tierData.status === 'review') return 'review';
      if (tierData.status === 'failed') return 'failed';
    }
    if (currentTier === tier) return 'processing';
    return 'pending';
  };

  const getStatusIcon = (tierStatus: string) => {
    switch (tierStatus) {
      case 'completed':
        return <CheckCircle className="h-5 w-5 text-green-500" />;
      case 'review':
        return <AlertTriangle className="h-5 w-5 text-yellow-500" />;
      case 'processing':
        return <Loader2 className="h-5 w-5 text-blue-500 animate-spin" />;
      case 'failed':
        return <XCircle className="h-5 w-5 text-red-500" />;
      default:
        return <Circle className="h-5 w-5 text-gray-300" />;
    }
  };

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold">Processing Status</h3>
        <span
          className={`px-3 py-1 rounded-full text-sm font-medium ${
            status === 'completed'
              ? 'bg-green-100 text-green-800'
              : status === 'failed'
              ? 'bg-red-100 text-red-800'
              : 'bg-blue-100 text-blue-800'
          }`}
        >
          {status}
        </span>
      </div>

      <div className="mb-6">
        <div className="flex justify-between text-sm text-gray-600 mb-1">
          <span>Progress</span>
          <span>{progress}%</span>
        </div>
        <div className="w-full bg-gray-200 rounded-full h-2">
          <div
            className="bg-blue-600 h-2 rounded-full transition-all duration-500"
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>

      {error && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
          {error}
        </div>
      )}

      <div className="space-y-3">
        {allTiers.map((tier) => {
          const tierStatus = getTierStatus(tier);
          const tierData = tiers.find((t) => t.tier === tier);

          return (
            <div
              key={tier}
              className={`flex items-center justify-between p-3 rounded-lg transition-colors ${
                tierStatus === 'processing'
                  ? 'bg-blue-50'
                  : tierStatus === 'completed'
                  ? 'bg-green-50'
                  : tierStatus === 'review'
                  ? 'bg-yellow-50'
                  : tierStatus === 'failed'
                  ? 'bg-red-50'
                  : 'bg-gray-50'
              }`}
            >
              <div className="flex items-center">
                {getStatusIcon(tierStatus)}
                <span className="ml-3 font-medium text-gray-900">{tierLabels[tier]}</span>
              </div>
              {tierData?.duration_ms && (
                <span className="text-sm text-gray-500">{(tierData.duration_ms / 1000).toFixed(1)}s</span>
              )}
              {tierData?.confidence && (
                <span className="text-sm text-gray-500">{tierData.confidence.toFixed(1)}% confidence</span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
