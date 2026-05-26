import { useState } from 'react';
import { FileUpload } from '../components/FileUpload';
import { api, endpoints } from '../api/client';
import { Loader2, CheckCircle, XCircle } from 'lucide-react';

type TierOption = 'tier0' | 'tier1' | 'tier2' | 'track_a' | 'track_b';

const tierInfo: Record<TierOption, { name: string; description: string; endpoint: string }> = {
  tier0: {
    name: 'Tier 0 - Preprocessing',
    description: 'Image preprocessing with OpenCV (adaptive thresholding, morphological operations, deskewing)',
    endpoint: endpoints.tier0.preprocess,
  },
  tier1: {
    name: 'Tier 1 - Text Extraction',
    description: 'AWS Textract OCR extraction with medical queries',
    endpoint: endpoints.tier1.extract,
  },
  tier2: {
    name: 'Tier 2 - Structure Refinement',
    description: 'LayoutLMv3 multimodal refinement for low-confidence documents',
    endpoint: endpoints.tier2.refine,
  },
  track_a: {
    name: 'Track A - SNOMED Mapping',
    description: 'AWS Comprehend Medical entity extraction and SNOMED CT mapping',
    endpoint: endpoints.trackA.snomedMapFile,
  },
  track_b: {
    name: 'Track B - Summarization',
    description: 'Clinical summarization with AWS Bedrock (Claude)',
    endpoint: endpoints.trackB.summarize,
  },
};

export function TierTest() {
  const [selectedTier, setSelectedTier] = useState<TierOption>('tier0');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  const handleFileSelect = (file: File) => {
    setSelectedFile(file);
    setResult(null);
    setError(null);
  };

  const handleTest = async () => {
    if (!selectedFile) return;

    setIsProcessing(true);
    setResult(null);
    setError(null);

    try {
      const formData = new FormData();
      formData.append('file', selectedFile);

      const response = await api.post(tierInfo[selectedTier].endpoint, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });

      setResult(response.data);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Test failed');
    } finally {
      setIsProcessing(false);
    }
  };

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Tier Test</h1>
        <p className="mt-1 text-gray-500">Test individual pipeline tiers in isolation.</p>
      </div>

      <div className="card">
        <h3 className="font-semibold mb-4">Select Tier</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {(Object.keys(tierInfo) as TierOption[]).map((tier) => (
            <button
              key={tier}
              onClick={() => {
                setSelectedTier(tier);
                setResult(null);
                setError(null);
              }}
              className={`p-4 rounded-lg border-2 text-left transition-colors ${
                selectedTier === tier
                  ? 'border-blue-500 bg-blue-50'
                  : 'border-gray-200 hover:border-gray-300'
              }`}
            >
              <p className="font-medium text-gray-900">{tierInfo[tier].name}</p>
              <p className="text-xs text-gray-500 mt-1">{tierInfo[tier].description}</p>
            </button>
          ))}
        </div>
      </div>

      <div className="card">
        <h3 className="font-semibold mb-4">Upload Test File</h3>
        <FileUpload onFileSelect={handleFileSelect} disabled={isProcessing} />

        <div className="mt-6">
          <button
            onClick={handleTest}
            disabled={!selectedFile || isProcessing}
            className="btn-primary w-full flex items-center justify-center"
          >
            {isProcessing ? (
              <>
                <Loader2 className="h-5 w-5 mr-2 animate-spin" />
                Processing...
              </>
            ) : (
              `Test ${tierInfo[selectedTier].name}`
            )}
          </button>
        </div>
      </div>

      {error && (
        <div className="card border-red-200 bg-red-50">
          <div className="flex items-start">
            <XCircle className="h-5 w-5 text-red-500 mt-0.5" />
            <div className="ml-3">
              <h3 className="font-semibold text-red-800">Error</h3>
              <p className="text-sm text-red-700 mt-1">{error}</p>
            </div>
          </div>
        </div>
      )}

      {result && (
        <div className="card border-green-200 bg-green-50">
          <div className="flex items-start mb-4">
            <CheckCircle className="h-5 w-5 text-green-500 mt-0.5" />
            <div className="ml-3">
              <h3 className="font-semibold text-green-800">Success</h3>
              <p className="text-sm text-green-700">Processing completed in {result.processing_time_ms}ms</p>
            </div>
          </div>

          <div className="bg-white rounded-lg p-4 overflow-x-auto">
            <pre className="text-sm text-gray-800">{JSON.stringify(result, null, 2)}</pre>
          </div>
        </div>
      )}
    </div>
  );
}
