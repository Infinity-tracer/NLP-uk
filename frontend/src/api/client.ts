import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

export const endpoints = {
  health: '/api/v1/health',
  tier0: {
    preprocess: '/api/v1/tier0/preprocess',
    preprocessBatch: '/api/v1/tier0/preprocess-batch',
  },
  tier1: {
    extract: '/api/v1/tier1/extract',
    results: '/api/v1/tier1/results',
  },
  tier2: {
    refine: '/api/v1/tier2/refine',
    refineBatch: '/api/v1/tier2/refine-batch',
  },
  tier3: {
    correct: '/api/v1/tier3/correct',
  },
  trackA: {
    snomedMap: '/api/v1/track-a/snomed-map',
    snomedMapFile: '/api/v1/track-a/snomed-map-file',
  },
  trackB: {
    summarize: '/api/v1/track-b/summarize',
  },
  pipeline: {
    processDocument: '/api/v1/pipeline/process-document',
    status: (jobId: string) => `/api/v1/pipeline/status/${jobId}`,
    result: (jobId: string) => `/api/v1/pipeline/result/${jobId}`,
    jobs: '/api/v1/pipeline/jobs',
  },
  admin: {
    jobs: '/api/v1/admin/jobs',
    outputs: '/api/v1/admin/outputs',
    stats: '/api/v1/admin/stats',
  },
};
