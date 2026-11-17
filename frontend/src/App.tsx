import { IntersectionView } from "./components/intersection/IntersectionView";
import { useSimulationSocket } from "./hooks/useWebSocket";

export default function App() {
  const { data, connected } = useSimulationSocket();
  const signal = data?.signal_control;
  const group = (id: string) => signal?.groups.find((item) => item.group_id === id);
  const formatState = (name: string, state?: { state: string; remaining: number }) => {
    if (!state) return `${name}: -`;
    const colorMap: Record<string, string> = { G: "#4caf50", y: "#ffeb3b", r: "#f44336" };
    return <span style={{ marginRight: 16 }}>{name}: <span style={{ color: colorMap[state.state], fontWeight: "bold" }}>{state.state}</span> ({Math.ceil(state.remaining)}s)</span>;
  };

  return (
    <div style={{ padding: 16, fontFamily: "system-ui" }}>
      <h2>新开路 × 华龙道 — 单路口信控仿真</h2>
      <p>WebSocket: {connected ? "已连接" : "未连接"} | 仿真: {data?.simulation_status ?? "-"} | 仿真时间: {data?.simulation_time.toFixed(1) ?? "-"}s | 当前相位: {signal?.phase_id ?? "-"} | sequence: {data?.sequence ?? "-"}</p>
      <p>信号控制: {signal?.control_status ?? "-"} / {signal?.control_mode ?? "-"} | 配时版本: {data?.timing.timing_version ?? "-"}{data?.timing.pending_timing_version ? `（待生效 ${data.timing.pending_timing_version}）` : ""}</p>
      <div style={{ marginBottom: 12, background: "#eee", padding: 10, borderRadius: 8 }}>
        <div>{formatState("南北直行", group("NS_STRAIGHT"))}{formatState("南北左转", group("NS_LEFT"))}</div>
        <div style={{ marginTop: 8 }}>{formatState("东西直行", group("EW_STRAIGHT"))}{formatState("东西左转", group("EW_LEFT"))}</div>
      </div>
      <IntersectionView data={data} />
    </div>
  );
}
