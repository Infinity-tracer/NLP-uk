import { useState } from 'react';
import { api, endpoints } from '../api/client';
import type { PipelineJobResponse } from '../types/api';

export function useUploadDocument() {
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const uploadDocument = async (file: File, confidenceThreshold = 90): Promise<PipelineJobResponse | null> => {
    setIsUploading(true);
    setError(null);

    try {
      const formData = new FormData();
      formData.append('file', file);

      const response = await api.post<PipelineJobResponse>(
        `${endpoints.pipeline.processDocument}?confidence_threshold=${confidenceThreshold}`,
        formData,
        {
          headers: {
            'Content-Type': 'multipart/form-data',
          },
        }
      );

      return response.data;
    } catch (err: any) {
      const message = err.response?.data?.detail || err.message || 'Upload failed';
      setError(message);
      return null;
    } finally {
      setIsUploading(false);
    }
  };

  return { uploadDocument, isUploading, error };
}
