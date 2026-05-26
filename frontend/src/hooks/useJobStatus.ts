import { useState, useEffect, useCallback } from 'react';
import { api, endpoints } from '../api/client';
import type { PipelineStatusResponse, PipelineResultResponse } from '../types/api';

export function useJobStatus(jobId: string | null, pollInterval = 2000) {
  const [status, setStatus] = useState<PipelineStatusResponse | null>(null);
  const [result, setResult] = useState<PipelineResultResponse | null>(null);
  const [isPolling, setIsPolling] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchStatus = useCallback(async () => {
    if (!jobId) return;

    try {
      const response = await api.get<PipelineStatusResponse>(endpoints.pipeline.status(jobId));
      setStatus(response.data);

      if (response.data.status === 'completed' || response.data.status === 'failed') {
        setIsPolling(false);

        if (response.data.status === 'completed') {
          const resultResponse = await api.get<PipelineResultResponse>(endpoints.pipeline.result(jobId));
          setResult(resultResponse.data);
        }
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message);
      setIsPolling(false);
    }
  }, [jobId]);

  useEffect(() => {
    if (!jobId) {
      setStatus(null);
      setResult(null);
      setIsPolling(false);
      return;
    }

    setIsPolling(true);
    fetchStatus();

    const interval = setInterval(() => {
      if (isPolling) {
        fetchStatus();
      }
    }, pollInterval);

    return () => clearInterval(interval);
  }, [jobId, pollInterval, fetchStatus, isPolling]);

  return { status, result, isPolling, error };
}
