import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { FileUpload } from '../components/FileUpload';
import { useUploadDocument } from '../hooks/useUploadDocument';

export function Upload() {
  const navigate = useNavigate();
  const { uploadDocument, isUploading, error } = useUploadDocument();
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [confidenceThreshold, setConfidenceThreshold] = useState(90);

  const handleFileSelect = (file: File) => {
    setSelectedFile(file);
  };

  const handleUpload = async () => {
    if (!selectedFile) return;

    const result = await uploadDocument(selectedFile, confidenceThreshold);
    if (result?.job_id) {
      navigate(`/processing?jobId=${result.job_id}`);
    }
  };

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Upload Document</h1>
        <p className="mt-1 text-gray-500">
          Upload a clinical document (PDF or image) to process through the NLP pipeline.
        </p>
      </div>

      <div className="card">
        <FileUpload onFileSelect={handleFileSelect} disabled={isUploading} />

        <div className="mt-6">
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Confidence Threshold for Tier 2 Routing
          </label>
          <div className="flex items-center space-x-4">
            <input
              type="range"
              min="50"
              max="100"
              value={confidenceThreshold}
              onChange={(e) => setConfidenceThreshold(Number(e.target.value))}
              className="flex-1"
              disabled={isUploading}
            />
            <span className="w-16 text-center font-medium">{confidenceThreshold}%</span>
          </div>
          <p className="mt-1 text-xs text-gray-500">
            Documents with Textract confidence below this threshold will be routed to Tier 2 refinement.
          </p>
        </div>

        {error && (
          <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
            {error}
          </div>
        )}

        <div className="mt-6">
          <button
            onClick={handleUpload}
            disabled={!selectedFile || isUploading}
            className="btn-primary w-full flex items-center justify-center"
          >
            {isUploading ? (
              <>
                <svg
                  className="animate-spin -ml-1 mr-3 h-5 w-5 text-white"
                  fill="none"
                  viewBox="0 0 24 24"
                >
                  <circle
                    className="opacity-25"
                    cx="12"
                    cy="12"
                    r="10"
                    stroke="currentColor"
                    strokeWidth="4"
                  />
                  <path
                    className="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                  />
                </svg>
                Uploading...
              </>
            ) : (
              'Process Document'
            )}
          </button>
        </div>
      </div>

      <div className="card bg-blue-50 border-blue-200">
        <h3 className="font-semibold text-blue-900 mb-2">Processing Pipeline</h3>
        <ol className="text-sm text-blue-800 space-y-1">
          <li>1. <strong>Tier 0:</strong> Image preprocessing (OpenCV)</li>
          <li>2. <strong>Tier 1:</strong> Text extraction (AWS Textract)</li>
          <li>3. <strong>Tier 2:</strong> Structure refinement (LayoutLMv3) - if confidence low</li>
          <li>4. <strong>Tier 3:</strong> Vision-LLM correction (Claude) - for critical terms</li>
          <li>5. <strong>Track A:</strong> SNOMED CT mapping (AWS Comprehend Medical)</li>
          <li>6. <strong>Track B:</strong> Clinical summarization (AWS Bedrock)</li>
        </ol>
      </div>
    </div>
  );
}
