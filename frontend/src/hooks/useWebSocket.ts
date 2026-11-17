/** B4 WebSocket Hook：完整快照、序列号防旧消息覆盖、断线重连和静态路网版本加载。 */
import { useEffect, useRef, useState } from "react";
import type { NetworkResource, SimulationState } from "../types/signal";

const WS_URL = import.meta.env.VITE_WS_URL ?? `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}/ws/simulation`;
const API_BASE = import.meta.env.VITE_API_URL ?? "";

function isSimulationStateMessage(value: unknown): value is SimulationState {
  if (!value || typeof value !== "object") return false;
  const message = value as Partial<SimulationState>;
  return (
    message.schema_version === "1.0" &&
    (message.type === "simulation_snapshot" || message.type === "simulation_update") &&
    Number.isInteger(message.sequence) &&
    typeof message.simulation_time === "number" &&
    typeof message.network_version === "string" &&
    Array.isArray(message.vehicles) &&
    !!message.signal_control && Array.isArray(message.signal_control.groups) &&
    !!message.timing && typeof message.simulation_status === "string"
  );
}

export function useSimulationSocket() {
  const [data, setData] = useState<SimulationState | null>(null);
  const [connected, setConnected] = useState(false);
  const [network, setNetwork] = useState<NetworkResource | null>(null);
  const retry = useRef(0);
  const lastSequence = useRef(0);
  const hasSnapshot = useRef(false);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let closed = false;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;

    const connect = () => {
      if (closed) return;
      ws = new WebSocket(WS_URL);
      ws.onopen = () => {
        retry.current = 0;
        lastSequence.current = 0;
        hasSnapshot.current = false;
        setConnected(true);
      };
      ws.onmessage = (ev) => {
        try {
          const parsed: unknown = JSON.parse(ev.data);
          if (!isSimulationStateMessage(parsed)) return;
          const incoming = parsed;
          if (incoming.sequence <= lastSequence.current) return;
          if (incoming.type === "simulation_snapshot") hasSnapshot.current = true;
          if (incoming.type === "simulation_update" && !hasSnapshot.current) return;
          lastSequence.current = incoming.sequence;
          setData(incoming);
        } catch {
          // 忽略无法解析或不符合协议的消息。
        }
      };
      ws.onerror = () => ws?.close();
      ws.onclose = () => {
        setConnected(false);
        if (!closed) retryTimer = setTimeout(connect, Math.min(5000, 500 * 2 ** retry.current++));
      };
    };

    // 新 Hook 生命周期开始时必须重新从服务端快照同步序列基线。
    connect();
    return () => {
      closed = true;
      if (retryTimer) clearTimeout(retryTimer);
      ws?.close();
    };
  }, []);

  useEffect(() => {
    const version = data?.network_version;
    if (!version) return;
    let cancelled = false;
    const loadNetwork = async () => {
      try {
        const response = await fetch(`${API_BASE}/api/intersections/${encodeURIComponent(data.signal_control.tls_id)}/network`);
        if (!response.ok) throw new Error(`network HTTP ${response.status}`);
        const resource = (await response.json()) as NetworkResource;
        if (!cancelled && resource.network_version === version) setNetwork(resource);
      } catch {
        // 网络资源失败不丢弃动态状态；后续新版本消息或页面重连可再次触发加载。
      }
    };
    if (network?.network_version !== version) void loadNetwork();
    return () => { cancelled = true; };
  }, [data?.network_version, data?.signal_control.tls_id, data?.type, network?.network_version]);

  const combined = data ? { ...data, network: network?.network_version === data.network_version ? network.geometry : undefined } : null;
  return { data: combined, connected };
}
