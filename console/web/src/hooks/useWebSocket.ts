import { useEffect, useRef, useCallback } from 'react';
import type { RefObject } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useAppStore } from '../store';
import type { StatusResponse, SessionInfo, WSMessage, ActivityItem } from '../api/types';
import type { QueueStatus } from '../api/types_queue';
import type { StreamChunk } from '../api/types';

// Global chat message handler registry (used by Chat.tsx for WS streaming)
type ChatMessageHandler = (chunk: StreamChunk) => void;
const _chatHandlers = new Set<ChatMessageHandler>();

export function registerChatHandler(handler: ChatMessageHandler): () => void {
  _chatHandlers.add(handler);
  return () => _chatHandlers.delete(handler);
}

function _dispatchChat(chunk: StreamChunk) {
  for (const h of _chatHandlers) {
    try { h(chunk); } catch {}
  }
}

// Expose wsRef so callers can send messages directly
let _wsRef: RefObject<WebSocket | null> | null = null;
export function getWSRef(): RefObject<WebSocket | null> | null {
  return _wsRef;
}

export function useWebSocket() {
  const queryClient = useQueryClient();
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);
  const isConnectingRef = useRef(false);
  const initialStatusReceivedRef = useRef(false);
  const { setWSConnected, setStatus, setSessions, addWSMessage } = useAppStore();

  const connect = useCallback(() => {
    // Prevent multiple concurrent connections
    if (isConnectingRef.current || (wsRef.current?.readyState === WebSocket.OPEN)) {
      console.log('[WebSocket] Already connected or connecting, skipping');
      return;
    }

    isConnectingRef.current = true;

    // Determine WebSocket URL - connect directly to backend
    // In dev: localhost:3000 -> proxy -> localhost:18791
    const wsUrl = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws`;

    console.log('[WebSocket] Connecting to:', wsUrl);

    try {
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;
      _wsRef = wsRef;

      ws.onopen = () => {
        console.log('[WebSocket] Connected!');
        isConnectingRef.current = false;
        setWSConnected(true);
        const botId = useAppStore.getState().currentBotId;
        if (botId) {
          ws.send(JSON.stringify({ type: 'subscribe', bot_id: botId }));
        }
      };

      ws.onmessage = (event) => {
        try {
          const message: WSMessage = JSON.parse(event.data);
          console.log('[WebSocket] Message:', message);
          addWSMessage(message);

          const activeBotId = useAppStore.getState().currentBotId;

          // Dispatch chat streaming messages to registered handlers
          const chatTypes = [
            'chat_token', 'chat_done', 'session_key', 'tool_call',
            'tool_result', 'tool_progress', 'subagent_start',
            'subagent_done', 'assistant_message', 'error',
          ];
          if (chatTypes.includes(message.type)) {
            _dispatchChat(message as StreamChunk);
          }

          if (message.type === 'status_update' && message.data) {
            const statusData = message.data as StatusResponse & { bot_id?: string };
            const targetBotId = statusData.bot_id ?? activeBotId;
            queryClient.setQueryData(['status', targetBotId], statusData);
            // 跳过连接时的初始 status，避免与页面加载时的 useQuery 重复请求 usage-history
            if (initialStatusReceivedRef.current) {
              queryClient.invalidateQueries({ queryKey: ['usage-history', targetBotId] });
            } else {
              initialStatusReceivedRef.current = true;
            }
            if (!statusData.bot_id || statusData.bot_id === activeBotId) {
              setStatus(statusData);
            }
          }
          if (message.type === 'sessions_update' && message.data) {
            const { sessions, bot_id } = message.data as { sessions: SessionInfo[]; bot_id?: string };
            const targetBotId = bot_id ?? activeBotId;
            queryClient.setQueryData(['sessions', targetBotId], sessions);
            queryClient.setQueryData(['sessions', 'recent', targetBotId], sessions?.slice(0, 5));
            if (!targetBotId || targetBotId === activeBotId) {
              setSessions(sessions);
            }
          }
          if (message.type === 'bots_update') {
            console.log('[WebSocket] Bots list updated, invalidating query');
            queryClient.invalidateQueries({ queryKey: ['bots'] });
          }
          if (message.type === 'queue_update' && message.data) {
            const queueData = message.data as { queues?: QueueStatus[]; bot_id?: string };
            // queues 是数组（全量），bot_id 是旧格式（单个）
            if (queueData.queues && Array.isArray(queueData.queues)) {
              // 全量更新：将每个 bot 的状态写入对应 queryKey
              for (const q of queueData.queues) {
                if (q.bot_id) {
                  queryClient.setQueryData(['queue-status', q.bot_id], q);
                }
              }
            } else if (queueData.bot_id) {
              // 旧格式：仅 invalidate，让组件重新 fetch
              queryClient.invalidateQueries({ queryKey: ['queue-status', queueData.bot_id] });
            }
          }
          if (message.type === 'activity_update' && message.entry) {
            const entry = message.entry as ActivityItem;
            // Update all active activity query caches so the Activity page
            // stays in sync with real-time events regardless of bot_id.
            const queries = queryClient.getQueriesData<ActivityItem[]>({
              queryKey: ['activity'],
              type: 'active',
            });
            for (const [queryKey, old] of queries) {
              if (!old) continue;
              if (old.some((e) => e.id === entry.id)) continue;
              queryClient.setQueryData<ActivityItem[]>(queryKey, [entry, ...old]);
            }
          }
        } catch (e) {
          console.error('[WebSocket] Parse error:', e);
        }
      };

      ws.onclose = (event) => {
        console.log('[WebSocket] Closed:', event.code, event.reason);
        isConnectingRef.current = false;
        setWSConnected(false);
        wsRef.current = null;

        // Schedule reconnect
        if (reconnectTimeoutRef.current) {
          clearTimeout(reconnectTimeoutRef.current);
        }
        reconnectTimeoutRef.current = window.setTimeout(() => {
          console.log('[WebSocket] Reconnecting...');
          connect();
        }, 3000);
      };

      ws.onerror = (error) => {
        console.error('[WebSocket] Error:', error);
        isConnectingRef.current = false;
      };
    } catch (e) {
      console.error('[WebSocket] Creation error:', e);
      isConnectingRef.current = false;

      // Schedule retry
      reconnectTimeoutRef.current = window.setTimeout(() => {
        connect();
      }, 5000);
    }
  }, [queryClient, setWSConnected, setStatus, setSessions, addWSMessage]);

  useEffect(() => {
    console.log('[WebSocket] Mounted, connecting...');
    connect();

    return () => {
      console.log('[WebSocket] Unmounting, cleaning up...');
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, []);

  return wsRef;
}
