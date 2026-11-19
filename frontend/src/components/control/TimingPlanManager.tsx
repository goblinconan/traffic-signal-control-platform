import { useCallback, useEffect, useState } from "react";
import type { ControlMode, TimingConfig } from "../../types/signal";

type Plan = {
  plan_id: string;
  name: string;
  config: TimingConfig;
  created_at: string;
};
type Props = {
  tlsId: string;
  mode: ControlMode;
  draft: TimingConfig;
  canOperateSignal: boolean;
  onDraftChange: (config: TimingConfig) => void;
};

const API_BASE = import.meta.env.VITE_API_URL ?? "";

async function request<T>(path: string, method = "GET", body?: unknown): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = payload?.detail;
    throw new Error(typeof detail === "string" ? detail : `请求失败：HTTP ${response.status}`);
  }
  return payload as T;
}

export function TimingPlanManager({ tlsId, mode, draft, canOperateSignal, onDraftChange }: Props) {
  const [plans, setPlans] = useState<Plan[]>([]);
  const [defaultTiming, setDefaultTiming] = useState<TimingConfig | null>(null);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  const base = `/api/signals/${encodeURIComponent(tlsId)}/timing-plans`;

  const refresh = useCallback(async () => {
    if (mode !== "MANUAL") return;
    const result = await request<{ plans: Plan[]; default_timing: TimingConfig }>(base);
    setPlans(result.plans);
    setDefaultTiming(result.default_timing);
  }, [base, mode]);

  useEffect(() => {
    let alive = true;
    if (mode === "MANUAL") {
      request<{ plans: Plan[]; default_timing: TimingConfig }>(base)
        .then((result) => {
          if (!alive) return;
          setPlans(result.plans);
          setDefaultTiming(result.default_timing);
        })
        .catch((error) => alive && setMessage(error instanceof Error ? error.message : "加载方案失败"));
    }
    return () => { alive = false; };
  }, [base, mode]);

  async function run(action: () => Promise<void>, refreshAfter = true) {
    if (busy) return;
    setBusy(true);
    setMessage("");
    let actionSucceeded = false;
    try {
      await action();
      actionSucceeded = true;
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "操作失败");
      return;
    } finally {
      if (!actionSucceeded) setBusy(false);
    }

    try {
      if (refreshAfter) await refresh();
    } catch (error) {
      const detail = error instanceof Error ? error.message : "未知错误";
      setMessage((current) => `${current || "操作已成功。"} 但刷新方案列表失败：${detail}`);
    } finally {
      setBusy(false);
    }
  }

  if (mode !== "MANUAL") {
    return <section className="panel timing-plan-panel">
      <h3>手动配时方案库</h3>
      <p className="helper-text">方案库仅在 MANUAL 模式下管理。AUTO 与 MANUAL 共用当前 Active Timing，切换模式不会重置配时。</p>
    </section>;
  }

  return <section className="panel timing-plan-panel">
    <div className="panel-heading">
      <div><div className="eyebrow">MANUAL TIMING LIBRARY</div><h3>手动配时方案库</h3></div>
      <span className="phase-chip">{plans.length} 个方案</span>
    </div>
    <p className="helper-text">保存/删除只改变方案库，不修改 Active/Pending。应用或恢复默认均提交到后端安全配时流程。方案库读取、保存和删除要求仿真 RUNNING 且信号控制 ENABLED。</p>
    <div className="button-row">
      <input aria-label="方案名称" value={name} maxLength={60} placeholder="输入方案名称" onChange={(e) => setName(e.target.value)} />
      <button className="button button-primary" disabled={!canOperateSignal || !!busy || !name.trim()}
        onClick={() => void run(async () => {
          await request(`${base}`, "POST", { name, config: draft });
          setName("");
          setMessage("方案已保存；当前 Active Timing 未改变。");
        })}>保存当前草稿</button>
    </div>
    <div className="timing-plan-list">
      {plans.map((plan) => <div className="timing-plan-row" key={plan.plan_id}>
        <div><strong>{plan.name}</strong><small>{new Date(plan.created_at).toLocaleString()}</small></div>
        <button className="button button-secondary" disabled={!!busy}
          onClick={() => { onDraftChange(plan.config); }}>载入编辑区</button>
        <button className="button button-primary" disabled={!canOperateSignal || !!busy}
          onClick={() => void run(async () => {
            await request(`${base}/${encodeURIComponent(plan.plan_id)}/apply`, "POST");
            setMessage("方案已提交；请查看 Active/Pending 版本及安全边界状态。");
          })}>应用方案</button>
        <button className="button button-danger" disabled={!canOperateSignal || !!busy}
          onClick={() => {
            if (!window.confirm(`确定删除方案“${plan.name}”？`)) return;
            void run(async () => { await request(`${base}/${encodeURIComponent(plan.plan_id)}`, "DELETE"); });
          }}>删除</button>
      </div>)}
      {plans.length === 0 && <p className="helper-text">尚未保存手动配时方案。</p>}
    </div>
    <div className="button-row">
      <button className="button button-secondary" disabled={!canOperateSignal || !!busy || !defaultTiming}
        onClick={() => void run(async () => {
          await request(`${base}/restore-default`, "POST");
          setMessage("服务器默认配时已提交；将按 MANUAL 安全边界生效。");
        })}>恢复服务器默认配时</button>
      <button className="button button-secondary" disabled={!!busy} onClick={() => void run(refresh, false)}>刷新方案库</button>
    </div>
    {message && <p className="helper-text" role="status">{message}</p>}
  </section>;
}
