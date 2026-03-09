import type {
  BotInfo,
  ChatRequest,
  ChatResponse,
  ChannelStatus,
  ConfigSection,
  MCPStatus,
  SessionInfo,
  SessionDetail,
  StatusResponse,
  SkillInfo,
  ToolCallLog,
  StreamChunk,
  BatchDeleteResponse,
  ActivityItem,
  ChannelRefreshResult,
  MCPTestResult,
} from './types';

const API_BASE = '/api';

function botQuery(botId?: string | null): string {
  return botId ? `?bot_id=${encodeURIComponent(botId)}` : '';
}

function appendBotQuery(url: string, botId?: string | null): string {
  if (!botId) return url;
  const sep = url.includes('?') ? '&' : '?';
  return `${url}${sep}bot_id=${encodeURIComponent(botId)}`;
}

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

// ====================
// Bot Management API
// ====================

export async function listBots(): Promise<BotInfo[]> {
  return fetchJson<BotInfo[]>(`${API_BASE}/bots`);
}

export async function getBot(botId: string): Promise<BotInfo> {
  return fetchJson<BotInfo>(`${API_BASE}/bots/${encodeURIComponent(botId)}`);
}

export async function createBot(name: string, sourceConfig?: Record<string, unknown>): Promise<BotInfo> {
  return fetchJson<BotInfo>(`${API_BASE}/bots`, {
    method: 'POST',
    body: JSON.stringify({ name, source_config: sourceConfig }),
  });
}

export async function deleteBot(botId: string): Promise<{ status: string }> {
  return fetchJson(`${API_BASE}/bots/${encodeURIComponent(botId)}`, {
    method: 'DELETE',
  });
}

export async function setDefaultBot(botId: string): Promise<{ status: string }> {
  return fetchJson(`${API_BASE}/bots/default`, {
    method: 'PUT',
    body: JSON.stringify({ bot_id: botId }),
  });
}

// ====================
// Status API
// ====================

export async function getStatus(botId?: string | null): Promise<StatusResponse> {
  return fetchJson<StatusResponse>(`${API_BASE}/status${botQuery(botId)}`);
}

export async function getChannels(botId?: string | null): Promise<ChannelStatus[]> {
  return fetchJson<ChannelStatus[]>(`${API_BASE}/channels${botQuery(botId)}`);
}

export async function getMCPServers(botId?: string | null): Promise<MCPStatus[]> {
  return fetchJson<MCPStatus[]>(`${API_BASE}/mcp${botQuery(botId)}`);
}

// ====================
// Sessions API
// ====================

export async function listSessions(botId?: string | null): Promise<SessionInfo[]> {
  return fetchJson<SessionInfo[]>(`${API_BASE}/sessions${botQuery(botId)}`);
}

export async function getSession(key: string, botId?: string | null): Promise<{
  key: string;
  title?: string;
  messages: unknown[];
  message_count: number;
}> {
  return fetchJson(appendBotQuery(`${API_BASE}/sessions/${encodeURIComponent(key)}`, botId));
}

export async function createSession(key?: string, botId?: string | null): Promise<SessionInfo> {
  return fetchJson<SessionInfo>(`${API_BASE}/sessions${botQuery(botId)}`, {
    method: 'POST',
    body: JSON.stringify({ key }),
  });
}

export async function deleteSession(key: string, botId?: string | null): Promise<{ status: string }> {
  return fetchJson(appendBotQuery(`${API_BASE}/sessions/${encodeURIComponent(key)}`, botId), {
    method: 'DELETE',
  });
}

// ====================
// Chat API
// ====================

export async function sendChatMessage(request: ChatRequest): Promise<ChatResponse> {
  return fetchJson<ChatResponse>(`${API_BASE}/chat`, {
    method: 'POST',
    body: JSON.stringify(request),
  });
}

// ====================
// Tools API
// ====================

export async function getToolLogs(
  limit = 50,
  toolName?: string,
  botId?: string | null
): Promise<ToolCallLog[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (toolName) params.append('tool_name', toolName);
  if (botId) params.append('bot_id', botId);
  return fetchJson<ToolCallLog[]>(`${API_BASE}/tools/log?${params}`);
}

// ====================
// Config API
// ====================

export async function getConfig(botId?: string | null): Promise<ConfigSection> {
  return fetchJson<ConfigSection>(`${API_BASE}/config${botQuery(botId)}`);
}

// ====================
// Skills API
// ====================

export async function listSkills(botId?: string | null): Promise<SkillInfo[]> {
  return fetchJson<SkillInfo[]>(`${API_BASE}/skills${botQuery(botId)}`);
}

export async function updateSkillsConfig(
  data: Record<string, { enabled?: boolean }>,
  botId?: string | null
): Promise<ConfigSection> {
  return updateConfig('skills', data, botId);
}

export async function getSkillContent(
  name: string,
  botId?: string | null
): Promise<{ name: string; content: string }> {
  return fetchJson(
    appendBotQuery(`${API_BASE}/skills/${encodeURIComponent(name)}/content`, botId)
  );
}

export async function updateSkillContent(
  name: string,
  content: string,
  botId?: string | null
): Promise<{ status: string; name: string }> {
  return fetchJson(
    appendBotQuery(`${API_BASE}/skills/${encodeURIComponent(name)}/content`, botId),
    {
      method: 'PUT',
      body: JSON.stringify({ content }),
    }
  );
}

export async function createSkill(
  data: { name: string; description: string; content?: string },
  botId?: string | null
): Promise<{ status: string; name: string }> {
  return fetchJson(`${API_BASE}/skills${botQuery(botId)}`, {
    method: 'POST',
    body: JSON.stringify({
      name: data.name,
      description: data.description,
      content: data.content || '',
    }),
  });
}

export async function deleteSkill(
  name: string,
  botId?: string | null
): Promise<{ status: string; name: string }> {
  return fetchJson(
    appendBotQuery(`${API_BASE}/skills/${encodeURIComponent(name)}`, botId),
    {
      method: 'DELETE',
    }
  );
}

export async function updateConfig(
  section: string,
  data: Record<string, unknown>,
  botId?: string | null
): Promise<ConfigSection> {
  return fetchJson<ConfigSection>(`${API_BASE}/config${botQuery(botId)}`, {
    method: 'PUT',
    body: JSON.stringify({ section, data }),
  });
}

export async function getConfigSchema(botId?: string | null): Promise<unknown> {
  return fetchJson(`${API_BASE}/config/schema${botQuery(botId)}`);
}

export async function validateConfig(
  data: Record<string, unknown>,
  botId?: string | null
): Promise<{ valid: boolean; errors: string[] }> {
  return fetchJson(`${API_BASE}/config/validate${botQuery(botId)}`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

// ====================
// Environment Variables API
// ====================

export async function getEnv(botId?: string | null): Promise<{ vars: Record<string, string> }> {
  return fetchJson<{ vars: Record<string, string> }>(`${API_BASE}/env${botQuery(botId)}`);
}

export async function updateEnv(
  vars: Record<string, string>,
  botId?: string | null
): Promise<{ status: string; vars?: Record<string, string> }> {
  return fetchJson(`${API_BASE}/env${botQuery(botId)}`, {
    method: 'PUT',
    body: JSON.stringify({ vars }),
  });
}

// ====================
// Control API
// ====================

export async function stopCurrentTask(botId?: string | null): Promise<{ status: string }> {
  return fetchJson(`${API_BASE}/control/stop${botQuery(botId)}`, { method: 'POST' });
}

export async function restartBot(botId?: string | null): Promise<{ status: string }> {
  return fetchJson(`${API_BASE}/control/restart${botQuery(botId)}`, { method: 'POST' });
}

// ====================
// Health Check
// ====================

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
  keys: string[],
  botId?: string | null
): Promise<BatchDeleteResponse> {
  return fetchJson<BatchDeleteResponse>(`${API_BASE}/sessions/batch${botQuery(botId)}`, {
    method: 'DELETE',
    body: JSON.stringify({ keys }),
  });
}

// ====================
// Activity Feed
// ====================

export async function getRecentActivity(limit = 20, botId?: string | null): Promise<ActivityItem[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (botId) params.append('bot_id', botId);
  return fetchJson<ActivityItem[]>(`${API_BASE}/activity?${params}`);
}

// ====================
// Channel Operations
// ====================

export async function refreshChannel(
  name: string,
  botId?: string | null
): Promise<ChannelRefreshResult> {
  return fetchJson<ChannelRefreshResult>(appendBotQuery(`${API_BASE}/channels/${name}/refresh`, botId), {
    method: 'POST',
  });
}

export async function refreshAllChannels(botId?: string | null): Promise<ChannelRefreshResult[]> {
  return fetchJson<ChannelRefreshResult[]>(`${API_BASE}/channels/refresh${botQuery(botId)}`, {
    method: 'POST',
  });
}

// ====================
// MCP Operations
// ====================

export async function testMCPConnection(name: string, botId?: string | null): Promise<MCPTestResult> {
  return fetchJson<MCPTestResult>(appendBotQuery(`${API_BASE}/mcp/${name}/test`, botId), {
    method: 'POST',
  });
}

export async function refreshMCPServer(name: string, botId?: string | null): Promise<MCPTestResult> {
  return fetchJson<MCPTestResult>(appendBotQuery(`${API_BASE}/mcp/${name}/refresh`, botId), {
    method: 'POST',
  });
}

// ====================
// Session Detail
// ====================

export async function getSessionDetail(key: string, botId?: string | null): Promise<SessionDetail> {
  return fetchJson<SessionDetail>(
    appendBotQuery(`${API_BASE}/sessions/${encodeURIComponent(key)}?detail=true`, botId)
  );
}
