// Type definitions for the API

export interface Message {
  role: 'user' | 'assistant' | 'system' | 'tool';
  content: string;
  tool_call_id?: string;
  tool_name?: string;
  timestamp?: string;
}

export interface ChatRequest {
  session_key?: string;
  message: string;
  stream?: boolean;
  bot_id?: string;
}

export interface BotInfo {
  id: string;
  name: string;
  config_path: string;
  workspace_path: string;
  created_at: string;
  updated_at: string;
  is_default: boolean;
  running: boolean;
}

export interface ChatResponse {
  session_key: string;
  message: string;
  tool_calls?: ToolCall[];
  done: boolean;
}

export interface ToolCall {
  id: string;
  name: string;
  arguments: Record<string, unknown>;
}

export interface SessionInfo {
  key: string;
  title?: string;
  message_count: number;
  last_message?: string;
  created_at?: string;
  updated_at?: string;
}

export interface ChannelStatus {
  name: string;
  enabled: boolean;
  status: 'online' | 'offline' | 'error';
  stats: Record<string, unknown>;
}

export interface MCPStatus {
  name: string;
  status: 'connected' | 'disconnected' | 'error';
  server_type: 'stdio' | 'http';
  last_connected?: string;
  error?: string;
}

export interface ToolCallLog {
  id: string;
  tool_name: string;
  arguments: Record<string, unknown>;
  result?: string;
  status: 'success' | 'error';
  duration_ms: number;
  timestamp: string;
}

export interface StatusResponse {
  running: boolean;
  uptime_seconds: number;
  model?: string;
  active_sessions: number;
  messages_today: number;
  channels: ChannelStatus[];
  mcp_servers: MCPStatus[];
}

export interface ConfigSection {
  general?: GeneralConfig;
  providers?: Record<string, ProviderConfig>;
  tools?: ToolsConfig;
  channels?: Record<string, ChannelConfig>;
  skills?: Record<string, SkillConfig>;
}

export interface GeneralConfig {
  workspace?: string;
  model?: string;
  max_iterations?: number;
  temperature?: number;
  memory_window?: number;
  reasoning_effort?: string;
}

export interface ProviderConfig {
  apiKey?: string;
  apiBase?: string;
  [key: string]: unknown;
}

export interface ToolsConfig {
  restrictToWorkspace?: boolean;
  mcpServers?: Record<string, MCPServerConfig>;
}

export interface MCPServerConfig {
  command?: string;
  args?: string[];
  url?: string;
  headers?: Record<string, string>;
  toolTimeout?: number;
}

export interface ChannelConfig {
  enabled?: boolean;
  [key: string]: unknown;
}

export interface SkillConfig {
  enabled?: boolean;
}

export interface SkillInfo {
  name: string;
  source: 'builtin' | 'workspace';
  description: string;
  enabled: boolean;
  path?: string;
  available?: boolean;
}

export type WSMessageType =
  | 'chat_token'
  | 'chat_done'
  | 'session_key'
  | 'tool_call'
  | 'tool_result'
  | 'tool_progress'
  | 'error'
  | 'status_update'
  | 'sessions_update'
  | 'bots_update';

export interface WSMessage {
  type: WSMessageType;
  data: unknown;
  session_key?: string;
}

// Streaming response types
export interface StreamChunk {
  type: WSMessageType;
  content?: string;
  session_key?: string;
  tool_call?: ToolCall;
  tool_name?: string;
  tool_result?: string;
  error?: string;
  done?: boolean;
}

// Batch operations
export interface BatchDeleteRequest {
  keys: string[];
}

export interface BatchDeleteResponse {
  deleted: string[];
  failed: { key: string; error: string }[];
}

// Activity feed
export interface ActivityItem {
  id: string;
  type: 'message' | 'tool' | 'channel' | 'session' | 'error';
  title: string;
  description?: string;
  timestamp: string;
  metadata?: Record<string, unknown>;
}

// Channel refresh result
export interface ChannelRefreshResult {
  name: string;
  success: boolean;
  message?: string;
}

// MCP test result
export interface MCPTestResult {
  name: string;
  success: boolean;
  message?: string;
  latency_ms?: number;
}

// Extended session with preview
export interface SessionDetail extends SessionInfo {
  preview_messages?: Message[];
}

// Memory
export interface MemoryResponse {
  long_term: string;
  history: string;
}

// Bot profile files (SOUL, USER, HEARTBEAT, TOOLS, AGENTS, IDENTITY)
export interface BotFilesResponse {
  soul: string;
  user: string;
  heartbeat: string;
  tools: string;
  agents: string;
  identity: string;
}
