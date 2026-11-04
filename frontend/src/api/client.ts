import type { InvestigationResponse, ScenarioSummary } from '../types/api';

const BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/+$/, '');

export class ApiError extends Error {
  constructor(public code: string, message: string, public retryable = true) {
    super(message);
    this.name = 'ApiError';
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, init);
  } catch (error) {
    if (init?.signal?.aborted) throw error;
    throw new ApiError('BACKEND_UNREACHABLE', 'Unable to reach GridProbe. Check that the backend is running, then retry.');
  }
  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    throw new ApiError('INVALID_RESPONSE', 'The backend returned an unreadable response. Please retry.');
  }
  if (!response.ok) {
    const detail = isRecord(payload) && isRecord(payload.error) ? payload.error : null;
    throw new ApiError(
      typeof detail?.code === 'string' ? detail.code : 'REQUEST_FAILED',
      typeof detail?.message === 'string' ? detail.message : 'The investigation request could not be completed.',
      typeof detail?.retryable === 'boolean' ? detail.retryable : true,
    );
  }
  return payload as T;
}

export const listScenarios = (signal?: AbortSignal) => request<ScenarioSummary[]>('/api/scenarios', { signal });
export const scenarioImageUrl = (caseId: string) => `${BASE_URL}/api/scenarios/${encodeURIComponent(caseId)}/image`;

export const investigate = (caseId: string) => request<InvestigationResponse>('/api/investigations', {
  method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ case_id: caseId }),
});

export async function checkHealth(): Promise<boolean> {
  try {
    const health = await request<{ status: string; service: string }>('/health', { signal: AbortSignal.timeout(5000) });
    return health.status === 'ok' && health.service === 'gridprobe-backend';
  } catch {
    return false;
  }
}
