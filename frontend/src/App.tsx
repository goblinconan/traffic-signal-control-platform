import { IntersectionView } from "./components/intersection/IntersectionView";
import { ControlPanel } from "./components/control/ControlPanel";
import { useSimulationSocket } from "./hooks/useWebSocket";
import "./components/control/control.css";

export default function App() {
  const { data, connected } = useSimulationSocket();

  return (
    <main className="app-shell">
      <header className="app-header">
        <div>
          <div className="eyebrow">TRAFFIC SIGNAL CONTROL PLATFORM · B5</div>
          <h1>新开路 × 华龙道交通信号控制平台</h1>
          <p className="header-subtitle">浏览器信号控制操作台 · SUMO 实时仿真</p>
        </div>
        <div className={`connection-pill ${connected ? "is-connected" : "is-disconnected"}`}>
          <span className="connection-dot" />
          WebSocket {connected ? "已连接" : "未连接"}
        </div>
      </header>

      <ControlPanel data={data} connected={connected} />

      <section className="panel intersection-panel">
        <div className="panel-heading">
          <div>
            <div className="eyebrow">LIVE INTERSECTION</div>
            <h2>路口实时二维视图</h2>
          </div>
          <div className="live-meta">
            <span>仿真时间 <strong>{data ? `${data.simulation_time.toFixed(1)} s` : "—"}</strong></span>
            <span>步骤 <strong>{data?.step_index ?? "—"}</strong></span>
            <span>消息序号 <strong>{data?.sequence ?? "—"}</strong></span>
          </div>
        </div>
        <div className="intersection-canvas">
          <IntersectionView data={data} />
        </div>
        <p className="view-footnote">当前阶段保留 B4 已验收的二维 SVG 视图；三维视图属于后续 A1–A5，不包含在 B5 交付范围内。</p>
      </section>

      <footer className="app-footer">
        B5 浏览器控制台 · 状态以 FastAPI / SUMO 后端为准 · 前端不直接写入 SUMO 信号灯色
      </footer>
    </main>
  );
}
