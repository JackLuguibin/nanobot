import type {
  ChatRequest,
  ChatResponse,
  ChannelStatus,
  ConfigSection,
  MCPStatus,
  SessionInfo,
  SessionDetail,
  StatusResponse,
  ToolCallLog,
  StreamChunk,
  BatchDeleteResponse,
  ActivityItem,
  ChannelRefreshResult,
  MCPTestResult,
} from './types';

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
    throw new Error(`API Error: ${response.status} ${response.statusText}`);
  }

  return response.json();
}

// Status API
export async function getStatus(): Promise<StatusResponse> {
  return fetchJson<StatusResponse>(`${API_BASE}/status`);
}

export async function getChannels(): Promise<ChannelStatus[]> {
  return fetchJson<ChannelStatus[]>(`${API_BASE}/channels`);
}

export async function getMCPServers(): Promise<MCPStatus[]> {
  return fetchJson<MCPStatus[]>(`${API_BASE}/mcp`);
}

// Sessions API
export async function listSessions(): Promise<SessionInfo[]> {
  return fetchJson<SessionInfo[]>(`${API_BASE}/sessions`);
}

export async function getSession(key: string): Promise<{
  key: string;
  title?: string;
  messages: unknown[];
  message_count: number;
}> {
  return fetchJson(`${API_BASE}/sessions/${encodeURIComponent(key)}`);
}

export async function createSession(key?: string): Promise<SessionInfo> {
  return fetchJson<SessionInfo>(`${API_BASE}/sessions`, {
    method: 'POST',
    body: JSON.stringify({ key }),
  });
}

export async function deleteSession(key: string): Promise<{ status: string }> {
  return fetchJson(`${API_BASE}/sessions/${encodeURIComponent(key)}`, {
    method: 'DELETE',
  });
}

// Chat API
export async function sendChatMessage(request: ChatRequest): Promise<ChatResponse> {
  return fetchJson<ChatResponse>(`${API_BASE}/chat`, {
    method: 'POST',
    body: JSON.stringify(request),
  });
}

// Tools API
export async function getToolLogs(
  limit = 50,
  toolName?: string
): Promise<ToolCallLog[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (toolName) params.append('tool_name', toolName);
  return fetchJson<ToolCallLog[]>(`${API_BASE}/tools/log?${params}`);
}

// Config API
export async function getConfig(): Promise<ConfigSection> {
  return fetchJson<ConfigSection>(`${API_BASE}/config`);
}

export async function updateConfig(
  section: string,
  data: Record<string, unknown>
): Promise<ConfigSection> {
  return fetchJson<ConfigSection>(`${API_BASE}/config`, {
    method: 'PUT',
    body: JSON.stringify({ section, data }),
  });
}

export async function getConfigSchema(): Promise<unknown> {
  return fetchJson(`${API_BASE}/config/schema`);
}

export async function validateConfig(
  data: Record<string, unknown>
): Promise<{ valid: boolean; errors: string[] }> {
  return fetchJson(`${API_BASE}/config/validate`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

// Control API
export async function stopCurrentTask(): Promise<{ status: string }> {
  return fetchJson(`${API_BASE}/control/stop`, { method: 'POST' });
}

export async function restartBot(): Promise<{ status: string }> {
  return fetchJson(`${API_BASE}/control/restart`, { method: 'POST' });
}

// Health Check
export async function healthCheck(): Promise<{ status: string; version: string }> {
  return fetchJson(`${API_BASE}/health`);
}

// ====================
// Streaming Chat API
// ====================

type StreamCallback = (chunk: StreamChunk) => void;

export function createChatStream(
  request: ChatRequest,
  onChunk: StreamCallback,
  onError?: (error: Error) => void
): () => void {
  const controller = new AbortController();
  let buffer = '';

  fetch(`${API_BASE}/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...request, stream: true }),
    signal: controller.signal,
  })
    .then(async (response) => {
      if (!response.ok) {
        throw new Error(`API Error: ${response.status} ${response.statusText}`);
      }

      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error('Response body is null');
      }

      const decoder = new TextDecoder();

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6)) as StreamChunk;
              onChunk(data);
            } catch {
              // Skip invalid JSON
            }
          }
        }
      }
    })
    .catch((error) => {
      if (error.name !== 'AbortError' && onError) {
        onError(error);
      }
    });

  return () => controller.abort();
}

// ====================
// Batch Operations
// ====================

export async function deleteSessionsBatch(
  keys: string[]
): Promise<BatchDeleteResponse> {
  return fetchJson<BatchDeleteResponse>(`${API_BASE}/sessions/batch`, {
    method: 'DELETE',
    body: JSON.stringify({ keys }),
  });
}

// ====================
// Activity Feed
// ====================

export async function getRecentActivity(limit = 20): Promise<ActivityItem[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  return fetchJson<ActivityItem[]>(`${API_BASE}/activity?${params}`);
}

// ====================
// Channel Operations
// ====================

export async function refreshChannel(
  name: string
): Promise<ChannelRefreshResult> {
  return fetchJson<ChannelRefreshResult>(`${API_BASE}/channels/${name}/refresh`, {
    method: 'POST',
  });
}

export async function refreshAllChannels(): Promise<ChannelRefreshResult[]> {
  return fetchJson<ChannelRefreshResult[]>(`${API_BASE}/channels/refresh`, {
    method: 'POST',
  });
}

// ====================
// MCP Operations
// ====================

export async function testMCPConnection(name: string): Promise<MCPTestResult> {
  return fetchJson<MCPTestResult>(`${API_BASE}/mcp/${name}/test`, {
    method: 'POST',
  });
}

export async function refreshMCPServer(name: string): Promise<MCPTestResult> {
  return fetchJson<MCPTestResult>(`${API_BASE}/mcp/${name}/refresh`, {
    method: 'POST',
  });
}

// ====================
// Session Detail
// ====================

export async function getSessionDetail(key: string): Promise<SessionDetail> {
  return fetchJson<SessionDetail>(
    `${API_BASE}/sessions/${encodeURIComponent(key)}?detail=true`
  );
}
