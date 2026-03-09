import { useEffect, useRef, useCallback } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useAppStore } from '../store';
import type { StatusResponse, SessionInfo, WSMessage } from '../api/types';

export function useWebSocket() {
  const queryClient = useQueryClient();
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);
  const isConnectingRef = useRef(false);
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
    const wsUrl = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/api/ws`;

    console.log('[WebSocket] Connecting to:', wsUrl);

    try {
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

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

          if (message.type === 'status_update' && message.data) {
            const statusData = message.data as StatusResponse & { bot_id?: string };
            const targetBotId = statusData.bot_id ?? activeBotId;
            queryClient.setQueryData(['status', targetBotId], statusData);
            queryClient.invalidateQueries({ queryKey: ['usage-history', targetBotId] });
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
