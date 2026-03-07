import { useEffect, useRef, useCallback } from 'react';
import { useAppStore } from '../store';
import type { StatusResponse, WSMessage } from '../api/types';

export function useWebSocket() {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);
  const isConnectingRef = useRef(false);
  const { setWSConnected, setStatus, addWSMessage } = useAppStore();

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
      };

      ws.onmessage = (event) => {
        try {
          const message: WSMessage = JSON.parse(event.data);
          console.log('[WebSocket] Message:', message);
          addWSMessage(message);

          if (message.type === 'status_update' && message.data) {
            console.log('[WebSocket] Status update:', message.data);
            const statusData = message.data as StatusResponse;
            setStatus(statusData);
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
  }, [setWSConnected, setStatus, addWSMessage]);

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
