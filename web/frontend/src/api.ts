/**
 * API client with ETag-based conditional responses and cursor-based log pagination.
 * No WebSocket — uses HTTP polling for all real-time data.
 */

const API_URL = process.env.REACT_APP_API_URL || `${window.location.protocol}//${window.location.hostname}:8420`;

/** In-memory ETag cache: endpoint path -> last ETag value */
const etagCache = new Map<string, string>();

/**
 * Fetch JSON with optional ETag support.
 * Returns null on 304 Not Modified (signals "no change" to caller).
 */
async function fetchJSON<T>(path: string, options?: RequestInit & { useETag?: boolean }): Promise<T | null> {
  const { useETag, ...fetchOptions } = options || {};
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };

  // Send If-None-Match header if we have a cached ETag
  if (useETag) {
    const cachedETag = etagCache.get(path);
    if (cachedETag) {
      headers['If-None-Match'] = cachedETag;
    }
  }

  const res = await fetch(`${API_URL}${path}`, {
    headers,
    ...fetchOptions,
  });

  // 304 Not Modified — data hasn't changed
  if (res.status === 304) {
    return null;
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || `HTTP ${res.status}`);
  }

  // Cache ETag from response
  if (useETag) {
    const etag = res.headers.get('etag');
    if (etag) {
      etagCache.set(path, etag);
    }
  }

  return res.json();
}

/**
 * Fetch JSON without ETag support (for non-conditional requests).
 * Always returns data, never null.
 */
async function fetchJSONStrict<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || `HTTP ${res.status}`);
  }
  return res.json();
}

export interface LogResponse {
  logs: Array<{ type: string; text?: string; name?: string; args?: string; iteration?: number; phase?: string }>;
  cursor: number;
  status: string;
}

export const api = {
  // Non-conditional endpoints (called once, not polled)
  listPipelines: () => fetchJSONStrict<{ pipelines: any[] }>('/api/pipelines'),
  getPipeline: (name: string) => fetchJSONStrict<any>(`/api/pipelines/${name}`),
  runPipeline: (name: string, input: Record<string, any>) =>
    fetchJSONStrict<{ run_id: string }>(`/api/pipelines/${name}/run`, { method: 'POST', body: JSON.stringify({ input }) }),

  // ETag-enabled endpoints (for polling — return null on 304 meaning "no change")
  listRuns: () => fetchJSON<{ runs: any[] }>('/api/runs', { useETag: true }),
  getRun: (runId: string) => fetchJSON<any>(`/api/runs/${runId}`, { useETag: true }),
  // Non-ETag variants for one-shot fetches (always return fresh data, never 304)
  listRunsDirect: () => fetchJSONStrict<{ runs: any[] }>('/api/runs'),
  getRunDirect: (runId: string) => fetchJSONStrict<any>(`/api/runs/${runId}`),

  // Cursor-based log pagination
  getTaskLogs: (runId: string, taskName: string, after: number = 0) =>
    fetchJSONStrict<LogResponse>(`/api/runs/${runId}/tasks/${taskName}/logs?after=${after}`),

  // Action endpoints (POST/PATCH, not polled)
  pauseRun: (runId: string) => fetchJSONStrict<any>(`/api/runs/${runId}/pause`, { method: 'POST' }),
  resumeRun: (runId: string) => fetchJSONStrict<any>(`/api/runs/${runId}/resume`, { method: 'POST' }),
  updateTask: (runId: string, taskName: string, updates: Record<string, any>) =>
    fetchJSONStrict<any>(`/api/runs/${runId}/tasks/${taskName}`, { method: 'PATCH', body: JSON.stringify(updates) }),
  reloadConfig: () => fetchJSONStrict<any>('/api/reload', { method: 'POST' }),
};
