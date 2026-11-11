/** WebSocket Hook：连接 /ws/simulation，断线后指数退避重连。 */
import { useEffect, useRef, useState } from "react";
import type { SimulationUpdate } from "../types/signal";

const WS_URL = import.meta.env.VITE_WS_URL ?? "ws://127.0.0.1:8000/ws/simulation";

export function useSimulationSocket() {
  const [data, setData] = useState<SimulationUpdate | null>(null);
  const [connected, setConnected] = useState(false);
  const retry = useRef(0);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let closed = false;

    const connect = () => {
      ws = new WebSocket(WS_URL);
      ws.onopen = () => { retry.current = 0; setConnected(true); };
      ws.onmessage = (ev) => {
        try {
          const incoming = JSON.parse(ev.data) as SimulationUpdate;

          setData((previous) => ({
            ...incoming,
            network: incoming.network ?? previous?.network,
          }));
        } catch {
          // 忽略无效消息
        }
      };
      ws.onclose = () => {
        setConnected(false);
        if (!closed) setTimeout(connect, Math.min(5000, 500 * 2 ** retry.current++));
      };
    };

    connect();
    return () => { closed = true; ws?.close(); };
  }, []);

  return { data, connected };
}