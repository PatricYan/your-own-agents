const BASE = process.env.REACT_APP_API_URL || 'http://localhost:8420';

async function fetchJSON<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || `HTTP ${res.status}`);
  }
  return res.json();
}

export const api = {
  listAgents: () => fetchJSON<{ agents: { name: string; pipeline: string }[] }>('/api/pipelines'),

  getPipeline: (name: string) =>
    fetchJSON<any>(`/api/pipelines/${name}`),

  runPipeline: (name: string, input: Record<string, any>) =>
    fetchJSON<{ run_id: string }>(`/api/pipelines/${name}/run`, {
      method: 'POST',
      body: JSON.stringify({ input }),
    }),

  listRuns: () => fetchJSON<{ runs: any[] }>('/api/runs'),

  getRun: (runId: string) => fetchJSON<any>(`/api/runs/${runId}`),

  pauseRun: (runId: string) =>
    fetchJSON<any>(`/api/runs/${runId}/pause`, { method: 'POST' }),

  resumeRun: (runId: string) =>
    fetchJSON<any>(`/api/runs/${runId}/resume`, { method: 'POST' }),

  updateTask: (runId: string, taskName: string, updates: Record<string, any>) =>
    fetchJSON<any>(`/api/runs/${runId}/tasks/${taskName}`, {
      method: 'PATCH',
      body: JSON.stringify(updates),
    }),

  listModels: () => fetchJSON<{ models: any[] }>('/api/models'),
};

export function connectWS(onMessage: (event: any) => void): WebSocket {
  const wsUrl = BASE.replace(/^http/, 'ws') + '/ws';
  const ws = new WebSocket(wsUrl);
  ws.onmessage = (e) => {
    try {
      onMessage(JSON.parse(e.data));
    } catch {}
  };
  ws.onclose = () => {
    // Auto-reconnect after 2 seconds
    setTimeout(() => connectWS(onMessage), 2000);
  };
  return ws;
}
