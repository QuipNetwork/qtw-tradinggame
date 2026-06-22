// Real backend implementation of the MVP API contract.
// Enabled through api/index.ts when VITE_API_BASE is set.

import type {
  AgentConfig,
  AgentUpdate,
  LeaderboardEntry,
  OptimizePatch,
  QpuBudgetStatus,
  RoutingResult,
  RoutingStats,
  SubmitAgentResponse,
  SubscribeOptions,
  TvEvent,
  ValuationHistoryPoint,
} from './types';
import { ReconnectingSocket } from './socket';

const API_BASE = (import.meta.env.VITE_API_BASE ?? '').replace(/\/+$/, '');

class BackendApiError extends Error {
  status: number;
  retryAfterSeconds?: number;
  qpuBudget?: QpuBudgetStatus;

  constructor(
    status: number,
    message: string,
    retryAfterSeconds?: number,
    qpuBudget?: QpuBudgetStatus,
  ) {
    super(message);
    this.name = 'BackendApiError';
    this.status = status;
    this.retryAfterSeconds = retryAfterSeconds;
    this.qpuBudget = qpuBudget;
  }
}

function url(path: string): string {
  if (!API_BASE) {
    throw new Error('VITE_API_BASE is required for the real API adapter');
  }
  return `${API_BASE}${path}`;
}

function websocketUrl(path: string): string {
  const explicit = (import.meta.env.VITE_WS_BASE ?? '').replace(/\/+$/, '');
  const base = explicit || API_BASE;
  if (!base) {
    throw new Error('VITE_API_BASE or VITE_WS_BASE is required for WebSocket subscriptions');
  }
  const parsed = new URL(base);
  parsed.protocol = parsed.protocol === 'https:' ? 'wss:' : 'ws:';
  parsed.pathname = `${parsed.pathname.replace(/\/+$/, '')}${path}`;
  parsed.search = '';
  parsed.hash = '';
  return parsed.toString();
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url(path), {
    ...init,
    headers: {
      ...(init?.body ? { 'content-type': 'application/json' } : {}),
      ...init?.headers,
    },
  });

  if (!response.ok) {
    let message = response.statusText;
    let retryAfterSeconds: number | undefined;
    let qpuBudget: QpuBudgetStatus | undefined;
    try {
      const body = await response.json();
      const detail = body.detail ?? body;
      if (typeof detail === 'string') {
        message = detail;
      } else {
        message = typeof detail.message === 'string'
          ? detail.message
          : JSON.stringify(detail);
        retryAfterSeconds = typeof detail.retryAfterSeconds === 'number'
          ? detail.retryAfterSeconds
          : undefined;
        qpuBudget = detail.qpuBudget;
      }
    } catch {
      // Keep the HTTP status text when the response is not JSON.
    }
    throw new BackendApiError(response.status, message, retryAfterSeconds, qpuBudget);
  }

  return response.json() as Promise<T>;
}

export async function submitAgent(config: AgentConfig): Promise<SubmitAgentResponse> {
  return request<SubmitAgentResponse>('/agents', {
    method: 'POST',
    body: JSON.stringify(config),
  });
}

export async function getAgent(agentId: string): Promise<AgentConfig | null> {
  try {
    return await request<AgentConfig>(`/agents/${encodeURIComponent(agentId)}`);
  } catch (error) {
    if (error instanceof BackendApiError && error.status === 404) {
      return null;
    }
    throw error;
  }
}

export async function updateAgent(
  agentId: string,
  patch: Partial<AgentConfig>,
): Promise<AgentConfig> {
  const current = await getAgent(agentId);
  if (!current) {
    throw new Error(`Agent not found: ${agentId}`);
  }
  return { ...current, ...patch };
}

export async function requestOptimization(
  agentId: string,
  patch: OptimizePatch = {},
): Promise<RoutingResult> {
  return request<RoutingResult>(`/agents/${encodeURIComponent(agentId)}/optimize`, {
    method: 'POST',
    body: JSON.stringify(patch),
  });
}

export async function getLeaderboard(): Promise<LeaderboardEntry[]> {
  return request<LeaderboardEntry[]>('/leaderboard');
}

export async function getRoutingStats(): Promise<RoutingStats> {
  return request<RoutingStats>('/routing-stats');
}

export async function getValuationHistory(
  agentId: string,
  limit = 60,
): Promise<ValuationHistoryPoint[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  return request<ValuationHistoryPoint[]>(
    `/agents/${encodeURIComponent(agentId)}/valuation-history?${params.toString()}`,
  );
}

export function subscribeAgent(
  agentId: string,
  callback: (update: AgentUpdate) => void,
  options: SubscribeOptions = {},
): () => void {
  const socket = new ReconnectingSocket<AgentUpdate>(
    websocketUrl(`/agents/${encodeURIComponent(agentId)}`),
    { onMessage: callback, onStatus: options.onStatus },
  );
  return () => socket.close();
}

export function subscribeTvEvents(
  callback: (event: TvEvent) => void,
  options: SubscribeOptions = {},
): () => void {
  const socket = new ReconnectingSocket<TvEvent>(
    websocketUrl('/tv/events'),
    { onMessage: callback, onStatus: options.onStatus },
  );
  return () => socket.close();
}
