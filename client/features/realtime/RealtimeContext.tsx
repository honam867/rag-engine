import React, { createContext, useContext, useEffect, useRef } from 'react';
import { useSupabaseSession } from '@/features/auth/hooks/useSupabaseSession';
import { useRealtimeEventHandler } from './useRealtimeEventHandler';

interface RealtimeContextType {
  isConnected: boolean;
}

const RealtimeContext = createContext<RealtimeContextType>({
  isConnected: false,
});

export const useRealtime = () => useContext(RealtimeContext);

export function RealtimeProvider({ children }: { children: React.ReactNode }) {
  const { token } = useSupabaseSession();
  const socketRef = useRef<WebSocket | null>(null);
  const [isConnected, setIsConnected] = React.useState(false);
  const { handleEvent } = useRealtimeEventHandler();
  
  // Keep a ref to the latest handleEvent callback
  // This allows us to call the latest handler (with updated params/pathname)
  // without re-running the connection effect.
  const handleEventRef = useRef(handleEvent);
  useEffect(() => {
    handleEventRef.current = handleEvent;
  }, [handleEvent]);

  useEffect(() => {
    // Only connect if we have a token
    if (!token) {
      if (socketRef.current) {
        socketRef.current.close();
        socketRef.current = null;
        setIsConnected(false);
      }
      return;
    }

    // Prevent multiple connections
    if (socketRef.current?.readyState === WebSocket.OPEN) {
      return;
    }

    const wsUrl = `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/ws?token=${token}`;
    // Replace http/https with ws/wss
    const finalUrl = wsUrl.replace(/^http/, 'ws');

    console.log('[Realtime] Connecting to:', finalUrl);
    const ws = new WebSocket(finalUrl);
    socketRef.current = ws;

    ws.onopen = () => {
      console.log('[Realtime] Connected');
      setIsConnected(true);
    };

    ws.onclose = () => {
      console.log('[Realtime] Disconnected');
      setIsConnected(false);
      socketRef.current = null;
      // Simple reconnect logic could go here (e.g. setTimeout)
    };

    ws.onerror = (error) => {
      console.error('[Realtime] Error:', error);
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        // Call the latest handler
        if (handleEventRef.current) {
            handleEventRef.current(data);
        }
      } catch (err) {
        console.error('[Realtime] Failed to parse message:', err);
      }
    };

    return () => {
      if (socketRef.current) {
        socketRef.current.close();
        socketRef.current = null;
      }
    };
    // Removed handleEvent from dependencies to prevent reconnects on route change
  }, [token]);

  return (
    <RealtimeContext.Provider value={{ isConnected }}>
      {children}
    </RealtimeContext.Provider>
  );
}
