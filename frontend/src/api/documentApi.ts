import axios from 'axios';
import type { ProcessResult } from './types';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '',
  timeout: 120000,
});

export async function processDocument(file: File): Promise<ProcessResult> {
  const formData = new FormData();
  formData.append('file', file);

  const response = await api.post<ProcessResult>('/api/process', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  });

  return response.data;
}

export async function getResult(docId: string): Promise<ProcessResult> {
  const response = await api.get<ProcessResult>(`/api/result/${docId}`);
  return response.data;
}

export interface RunSummary {
  doc_id: string;
  filename: string;
  processed_at: string;
  letter_type: string;
  unified_confidence: number;
  pages_processed: number;
  status: string;
}

export async function listRuns(): Promise<{ runs: RunSummary[]; total: number }> {
  const response = await api.get<{ runs: RunSummary[]; total: number }>('/api/runs');
  return response.data;
}

export async function deleteRun(docId: string): Promise<void> {
  await api.delete(`/api/runs/${docId}`);
}

export function getPageImageUrl(docId: string, filename: string): string {
  const baseUrl = import.meta.env.VITE_API_BASE_URL || '';
  return `${baseUrl}/pages/${docId}/${filename}`;
}
