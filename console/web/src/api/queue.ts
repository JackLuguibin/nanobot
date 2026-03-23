import type { QueueStatus } from './types_queue';

const API_BASE = '/api';

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  const body = await response.json();
  if (body && typeof body === 'object' && 'code' in body && body.code === 0 && 'data' in body) {
    return body.data as T;
  }
  return body as T;
}

export async function fetchQueueStatus(botId?: string): Promise<QueueStatus[]> {
  const params = botId ? `?bot_id=${encodeURIComponent(botId)}` : '';
  return fetchJson<QueueStatus[]>(`${API_BASE}/queue/status${params}`);
}

export async function fetchQueueStatusSingle(botId: string): Promise<QueueStatus> {
  return fetchJson<QueueStatus>(`${API_BASE}/queue/status?bot_id=${encodeURIComponent(botId)}`);
}
