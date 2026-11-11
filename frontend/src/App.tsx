import { IntersectionView } from "./components/intersection/IntersectionView";
import { useSimulationSocket } from "./hooks/useWebSocket";

export default function App() {
  const { data, connected } = useSimulationSocket();
  const sig = data?.signal;

  const formatState = (name: string, s?: { state: string; remaining: number }) => {
    if (!s) return `${name}: -`;
    const colorMap: Record<string, string> = { G: "#4caf50", y: "#ffeb3b", r: "#f44336" };
    return (
      <span style={{ marginRight: 16 }}>
        {name}: <span style={{ color: colorMap[s.state], fontWeight: "bold" }}>{s.state}</span>
        ({Math.ceil(s.remaining)}s)
      </span>
    );
  };

  return (
    <div style={{ padding: 16, fontFamily: "system-ui" }}>
      <h2>新开路 × 华龙道 — 单路口信控仿真</h2>
      <p>
        WebSocket: {connected ? "已连接" : "未连接"} | 仿真时间:{" "}
        {data?.simulation_time.toFixed(1) ?? "-"}s | 当前相位:{" "}
        {sig?.phase_id ?? "-"}
      </p>
      <div style={{ marginBottom: 12, background: "#eee", padding: 10, borderRadius: 8 }}>
        <div>
          {formatState("南北直行", sig?.ns_straight)}
          {formatState("南北左转", sig?.ns_left)}
        </div>
        <div style={{ marginTop: 8 }}>
          {formatState("东西直行", sig?.ew_straight)}
          {formatState("东西左转", sig?.ew_left)}
        </div>
      </div>
      <IntersectionView data={data} />
    </div>
  );
}