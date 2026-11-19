/**
 * B5 浏览器控制台。
 * 输入：B4 WebSocket 统一运行状态及用户控制请求。
 * 输出：仿真/信号控制操作、状态展示和操作反馈。
 * 依赖：现有 B3/B4 REST API；不在浏览器实现信号状态机。
 * 调用方：App.tsx。
 */
import { useEffect, useMemo, useState, type FormEvent } from "react";
import type {
  ControlMode,
  PhaseId,
  SignalGroupState,
  SimulationState,
  TimingConfig,
} from "../../types/signal";
import { TimingPlanManager } from './TimingPlanManager';
import {
  getTimingValidationErrors,
  type TimingField,
} from "./timingValidation";

const API_BASE = import.meta.env.VITE_API_URL ?? "";

const PHASES: Array<{ id: PhaseId; label: string }> = [
  { id: "NS_LEFT", label: "南北左转" },
  { id: "NS_STRAIGHT", label: "南北直行" },
  { id: "EW_LEFT", label: "东西左转" },
  { id: "EW_STRAIGHT", label: "东西直行" },
];

const TIMING_FIELDS: Array<{
  key: TimingField;
  label: string;
  movement: string;
  light: "绿灯" | "黄灯";
}> = [
  { key: "ns_left_green", label: "南北左转绿灯", movement: "南北左转", light: "绿灯" },
  { key: "ns_left_yellow", label: "南北左转黄灯", movement: "南北左转", light: "黄灯" },
  { key: "ns_straight_green", label: "南北直行绿灯", movement: "南北直行", light: "绿灯" },
  { key: "ns_straight_yellow", label: "南北直行黄灯", movement: "南北直行", light: "黄灯" },
  { key: "ew_left_green", label: "东西左转绿灯", movement: "东西左转", light: "绿灯" },
  { key: "ew_left_yellow", label: "东西左转黄灯", movement: "东西左转", light: "黄灯" },
  { key: "ew_straight_green", label: "东西直行绿灯", movement: "东西直行", light: "绿灯" },
  { key: "ew_straight_yellow", label: "东西直行黄灯", movement: "东西直行", light: "黄灯" },
];

const GROUPS: Array<{ id: SignalGroupState["group_id"]; label: string }> = [
  { id: "NS_LEFT", label: "南北左转" },
  { id: "NS_STRAIGHT", label: "南北直行" },
  { id: "EW_LEFT", label: "东西左转" },
  { id: "EW_STRAIGHT", label: "东西直行" },
];

const PHASE_LABELS: Record<string, string> = {
  NS_LEFT: "南北左转绿灯",
  NS_LEFT_YELLOW: "南北左转黄灯",
  NS_STRAIGHT: "南北直行绿灯",
  NS_STRAIGHT_YELLOW: "南北直行黄灯",
  EW_LEFT: "东西左转绿灯",
  EW_LEFT_YELLOW: "东西左转黄灯",
  EW_STRAIGHT: "东西直行绿灯",
  EW_STRAIGHT_YELLOW: "东西直行黄灯",
  ALL_RED: "全红安全保持",
};

const SIMULATION_LABELS: Record<string, string> = {
  STOPPED: "已停止",
  STARTING: "启动中",
  RUNNING: "运行中",
  STOPPING: "停止中",
  FAILED: "异常（FAILED）",
};

const CONTROL_LABELS: Record<string, string> = {
  ENABLED: "已启用",
  DISABLING: "安全停用过渡中",
  DISABLED: "已停用（全红）",
};

const MODE_LABELS: Record<ControlMode, string> = {
  AUTO: "自动模式",
  MANUAL: "手动模式",
};

function initialTiming(): TimingConfig {
  return {
    ns_left_green: 20,
    ns_left_yellow: 3,
    ns_straight_green: 40,
    ns_straight_yellow: 3,
    ew_left_green: 20,
    ew_left_yellow: 3,
    ew_straight_green: 40,
    ew_straight_yellow: 3,
  };
}

function formatError(payload: unknown, fallback: string): string {
  if (payload && typeof payload === "object") {
    const body = payload as { detail?: unknown; message?: unknown };
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail)) {
      return body.detail
        .map((item) => {
          if (!item || typeof item !== "object") return String(item);
          const issue = item as { loc?: unknown[]; msg?: string };
          const location = Array.isArray(issue.loc) ? issue.loc.join(" → ") : "";
          return `${location ? `${location}：` : ""}${issue.msg ?? "参数不合法"}`;
        })
        .join("；");
    }
    if (typeof body.message === "string") return body.message;
  }
  return fallback;
}

async function sendRequest<T>(path: string, method: string, body?: unknown): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const raw = await response.text();
  let payload: unknown = null;
  if (raw) {
    try {
      payload = JSON.parse(raw);
    } catch {
      payload = raw;
    }
  }
  if (!response.ok) {
    throw new Error(formatError(payload, `请求失败：HTTP ${response.status}`));
  }
  return payload as T;
}

function groupColor(state?: string): string {
  if (state === "G") return "green";
  if (state === "y") return "yellow";
  return "red";
}

function lightLabel(state?: string): string {
  if (state === "G") return "绿灯";
  if (state === "y") return "黄灯";
  if (state === "r") return "红灯";
  return "未知";
}

export function ControlPanel({
  data,
  connected,
}: {
  data: SimulationState | null;
  connected: boolean;
}) {
  const signal = data?.signal_control;
  const tlsId = signal?.tls_id ?? "intersection_0";
  const simulationStatus = data?.simulation_status ?? "STOPPED";
  const controlStatus = signal?.control_status ?? "DISABLED";
  const mode = signal?.control_mode ?? "AUTO";
  const isRunning = simulationStatus === "RUNNING";
  const controlEnabled = controlStatus === "ENABLED";
  const isBusyState = simulationStatus === "STARTING" || simulationStatus === "STOPPING";

  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<{ kind: "success" | "error" | "info"; text: string } | null>(null);
  const [draft, setDraft] = useState<TimingConfig>(initialTiming);
  const [selectedPhase, setSelectedPhase] = useState<PhaseId>("NS_LEFT");

  const timing = data?.timing;
  const timingErrors = useMemo(() => getTimingValidationErrors(draft), [draft]);
  const timingReady = !!timing;

  useEffect(() => {
    if (!timing) return;
    // 若有待生效方案，编辑区以 pending 为起点，避免用户误把 active 当成待生效值。
    setDraft(timing.pending ?? timing.active);
  }, [timing?.timing_version, timing?.pending_timing_version]);

  async function runAction<T>(
    key: string,
    successText: string,
    action: () => Promise<T>,
    successDetail?: (result: T) => string,
  ) {
    if (busy) return;
    setBusy(key);
    setNotice({ kind: "info", text: "正在向后端提交请求…" });
    try {
      const result = await action();
      const detail = successDetail ? successDetail(result) : successText;
      setNotice({ kind: "success", text: detail || successText });
    } catch (error) {
      setNotice({
        kind: "error",
        text: error instanceof Error ? error.message : "操作失败，未能取得后端错误详情",
      });
    } finally {
      setBusy(null);
    }
  }

  const runPath = (key: string, path: string, method: string, body?: unknown, success?: string) =>
    runAction(key, success ?? "请求已被后端接受。", () => sendRequest(path, method, body));

  const canOperateSignal = isRunning && controlEnabled && !isBusyState && !busy;
  const canSwitchMode = isRunning && controlStatus !== "DISABLING" && !isBusyState && !busy;
  const canToggleControl = isRunning && controlStatus !== "DISABLING" && !isBusyState && !busy;
  const canSubmitManual = canOperateSignal && mode === "MANUAL";
  const canSubmitTiming = canOperateSignal && timingReady && timingErrors.length === 0;

  function submitTiming(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmitTiming) return;
    void runAction(
      "timing",
      "配时方案已提交。",
      () => sendRequest<{
        accepted: boolean;
        status: string;
        effective: string;
        timing_version: number;
        pending_timing_version: number | null;
      }>(`/api/signals/${encodeURIComponent(tlsId)}/timing`, "PUT", draft),
      (result) => `配时请求：${result.status}；生效边界：${result.effective}；active v${result.timing_version}；pending ${result.pending_timing_version ? `v${result.pending_timing_version}` : "无"}`,
    );
  }

  const active = timing?.active;
  const pending = timing?.pending;
  const computed = timing?.computed;
  const currentPhase = signal?.phase_id ?? "—";
  const nextPhase = signal?.next_phase;
  const currentGroup = (id: SignalGroupState["group_id"]) => signal?.groups.find((item) => item.group_id === id);

  return (
    <section className="control-layout">
      <div className="panel control-panel">
        <div className="panel-heading">
          <div>
            <div className="eyebrow">SIMULATION LIFECYCLE</div>
            <h2>仿真控制</h2>
          </div>
          <span className={`status-badge status-${simulationStatus.toLowerCase()}`}>
            {SIMULATION_LABELS[simulationStatus] ?? simulationStatus}
          </span>
        </div>
        <div className="status-grid">
          <div className="metric-card">
            <span>SUMO 连接</span>
            <strong className={data?.sumo_connected ? "text-green" : "text-muted"}>
              {data?.sumo_connected ? "已连接" : "未连接"}
            </strong>
          </div>
          <div className="metric-card">
            <span>SUMO 进程</span>
            <strong>{data?.process_alive ? "运行中" : "未运行"}</strong>
          </div>
        </div>
        <div className="button-row">
          <button
            className="button button-primary"
            disabled={!data || !!busy || isBusyState || simulationStatus !== "STOPPED"}
            onClick={() => void runPath("start", "/api/simulation/start", "POST", undefined, "仿真启动请求已完成。")}
          >
            {busy === "start" ? "启动中…" : "启动仿真"}
          </button>
          <button
            className="button button-danger"
            disabled={!!busy || isBusyState || (simulationStatus === "STOPPED" && !data?.process_alive)}
            onClick={() => void runPath("stop", "/api/simulation/stop", "POST", undefined, "仿真停止/资源清理请求已完成。")}
          >
            {busy === "stop" ? "停止中…" : simulationStatus === "FAILED" ? "清理异常仿真" : "停止仿真"}
          </button>
        </div>
        {data?.last_error && <div className="error-detail"><strong>后端错误：</strong>{data.last_error}</div>}
        <p className="helper-text">异常状态下不能直接重新启动；请先执行清理，再根据后端状态重试。</p>
      </div>

      <div className="panel control-panel">
        <div className="panel-heading">
          <div>
            <div className="eyebrow">SIGNAL CONTROL DOMAIN</div>
            <h2>信号控制</h2>
          </div>
          <span className={`status-badge ${controlEnabled ? "status-running" : controlStatus === "DISABLING" ? "status-transition" : "status-stopped"}`}>
            {CONTROL_LABELS[controlStatus] ?? controlStatus}
          </span>
        </div>
        <div className="control-summary">
          <div><span>当前模式</span><strong>{MODE_LABELS[mode]}</strong></div>
          <div><span>控制状态</span><strong>{CONTROL_LABELS[controlStatus] ?? controlStatus}</strong></div>
        </div>
        <div className="button-row">
          <button
            className={`button ${controlEnabled ? "button-danger" : "button-primary"}`}
            disabled={!canToggleControl}
            onClick={() => void runPath(
              "enabled",
              `/api/signals/${encodeURIComponent(tlsId)}/control/enabled`,
              "PUT",
              { enabled: !controlEnabled },
              controlEnabled ? "停用请求已接受；等待后端完成绿灯、完整黄灯及全红安全过渡。" : "启用请求已接受。",
            )}
          >
            {controlEnabled ? "请求安全停用" : "启用信号控制"}
          </button>
        </div>
        <div className="segmented-control" role="group" aria-label="控制模式">
          {(["AUTO", "MANUAL"] as ControlMode[]).map((item) => (
            <button
              key={item}
              className={mode === item ? "segment is-active" : "segment"}
              disabled={!canSwitchMode || mode === item}
              onClick={() => void runPath(
                "mode",
                `/api/signals/${encodeURIComponent(tlsId)}/control/mode`,
                "PUT",
                { mode: item },
                `模式切换请求已接受：${MODE_LABELS[item]}。切换过程以服务端安全过渡状态为准。`,
              )}
            >
              {MODE_LABELS[item]}
            </button>
          ))}
        </div>
        <p className="helper-text">模式切换可能需要先完成当前绿灯和完整黄灯，再进入全红安全边界；请以实时状态为准。</p>
      </div>

      <div className="panel phase-panel">
        <div className="panel-heading">
          <div>
            <div className="eyebrow">PHASE MONITOR</div>
            <h2>相位与信号组状态</h2>
          </div>
          <span className="phase-chip">{PHASE_LABELS[currentPhase] ?? currentPhase}</span>
        </div>
        <div className="phase-overview">
          <div><span>当前阶段</span><strong>{PHASE_LABELS[currentPhase] ?? currentPhase}</strong></div>
          <div><span>阶段剩余</span><strong>{signal?.countdown_visible ? `${Math.ceil(signal.remaining)} s` : "—"}</strong></div>
          <div><span>下一阶段/目标</span><strong>{nextPhase ? PHASE_LABELS[nextPhase] ?? nextPhase : signal?.pending_manual_phase ? PHASE_LABELS[signal.pending_manual_phase] : "等待请求"}</strong></div>
        </div>
        <div className="signal-groups">
          {GROUPS.map((item) => {
            const group = currentGroup(item.id);
            return (
              <div className="signal-group-card" key={item.id}>
                <div className="signal-group-title">{item.label}</div>
                <div className={`signal-lamp lamp-${groupColor(group?.state)}`} />
                <strong>{lightLabel(group?.state)}</strong>
                <span>{group?.countdown_visible ? `${Math.ceil(group.remaining)} 秒` : "不显示倒计时"}</span>
              </div>
            );
          })}
        </div>
        <div className="right-turn-row">
          <strong>右转独立让行状态</strong>
          {signal?.right_turns.map((turn) => (
            <span key={turn.approach} className={`right-turn-tag ${turn.signal_state === "g" ? "yield-open" : "yield-stop"}`}>
              {({ N: "北", S: "南", E: "东", W: "西" } as const)[turn.approach]}向：{turn.signal_state === "g" ? "让行通行" : "红灯"}
            </span>
          )) ?? <span className="muted">等待状态</span>}
        </div>
      </div>

      <div className="panel phase-panel">
        <div className="panel-heading">
          <div>
            <div className="eyebrow">MANUAL PHASE REQUEST</div>
            <h2>人工阶段操作</h2>
          </div>
          <span className="subtle-tag">仅请求四类绿灯业务阶段</span>
        </div>
        <p className="helper-text">仅当仿真 RUNNING、控制 ENABLED 且处于 MANUAL 时开放。后端负责黄灯、ALL_RED 和至少一个仿真 step 的安全过渡。</p>
        <div className="manual-phase-grid">
          {PHASES.map((phase) => (
            <button
              key={phase.id}
              className={selectedPhase === phase.id ? "phase-choice is-selected" : "phase-choice"}
              disabled={!canSubmitManual || busy === "phase"}
              onClick={() => setSelectedPhase(phase.id)}
            >
              {phase.label}
            </button>
          ))}
        </div>
        <button
          className="button button-primary manual-submit"
          disabled={!canSubmitManual || busy === "phase"}
          onClick={() => void runAction(
            "phase",
            "人工阶段请求已提交。",
            () => sendRequest<{ accepted: boolean; status: string; reason: string }>(
              `/api/signals/${encodeURIComponent(tlsId)}/phases/switch`,
              "POST",
              { target_phase: selectedPhase },
            ),
            (result) => result.accepted
              ? `后端已接受：${result.status} · ${result.reason}`
              : `后端未接受：${result.reason}`,
          )}
        >
          {busy === "phase" ? "提交中…" : `提交：${PHASES.find((phase) => phase.id === selectedPhase)?.label ?? "目标阶段"}`}
        </button>
      </div>

      <div className="panel timing-panel">
        <div className="panel-heading">
          <div>
            <div className="eyebrow">TIMING MANAGEMENT</div>
            <h2>信号配时管理</h2>
          </div>
          <span className="version-chip">Active v{timing?.timing_version ?? "—"}</span>
        </div>
        <div className="timing-version-grid">
          <div>
            <span>当前生效方案</span>
            <strong>{timing?.active_source.name ?? "—"}</strong>
          </div>
          <div>
            <span>当前生效版本</span>
            <strong>v{timing?.timing_version ?? "—"}</strong>
          </div>
          <div>
            <span>待生效方案</span>
            <strong>{timing?.pending_source?.name ?? "无"}</strong>
          </div>
          <div>
            <span>待生效版本</span>
            <strong>
              {timing?.pending_timing_version
                ? `v${timing.pending_timing_version}`
                : "无"}
            </strong>
          </div>
          <div>
            <span>周期总长</span>
            <strong>
              {computed ? `${computed.cycle_length.toFixed(1)} s` : "—"}
            </strong>
          </div>
        </div>
        {pending && <div className="pending-banner">存在待生效方案。当前编辑区以待生效方案为初始值；重新提交当前 active 方案可按后端规则撤销 pending。</div>}
        <div className="timing-current-grid">
          {TIMING_FIELDS.map((field) => (
            <div key={field.key}>
              <span>{field.label}</span>
              <strong>{active ? `${active[field.key]} s` : "—"}</strong>
            </div>
          ))}
        </div>
        <form onSubmit={submitTiming}>
          <div className="form-heading"><h3>编辑配时方案</h3><span>单位：秒</span></div>
          <div className="timing-input-grid">
            {TIMING_FIELDS.map((field) => (
              <label className="timing-field" key={field.key}>
                <span>{field.label}</span>
                <div className="number-input-wrap">
                  <input
                    type="number"
                    min={field.light === "绿灯" ? "8.01" : "0.01"}
                    step="0.01"
                    value={draft[field.key]}
                    disabled={!canOperateSignal || !timingReady}
                    onChange={(event) => setDraft((current) => ({ ...current, [field.key]: Number(event.target.value) }))}
                  />
                  <em>s</em>
                </div>
              </label>
            ))}
          </div>
          <div className="red-duration-grid">
            {computed && (
              <>
                <span>当前计算红灯</span>
                <strong>南北左转 {computed.ns_left_red.toFixed(1)}s</strong>
                <strong>南北直行 {computed.ns_straight_red.toFixed(1)}s</strong>
                <strong>东西左转 {computed.ew_left_red.toFixed(1)}s</strong>
                <strong>东西直行 {computed.ew_straight_red.toFixed(1)}s</strong>
              </>
            )}
          </div>
          {timingErrors.length > 0 && (
            <ul className="validation-errors">
              {timingErrors.map((error) => <li key={error}>{error}</li>)}
            </ul>
          )}
          <div className="button-row timing-actions">
            <button className="button button-primary" type="submit" disabled={!canSubmitTiming || busy === "timing"}>
              {busy === "timing" ? "提交中…" : "提交配时方案"}
            </button>
          </div>
        </form>
        <p className="helper-text">绿灯必须大于 8 秒、黄灯必须大于 0 秒；四类计算红灯均必须大于 10 秒。AUTO 在完整周期边界生效，MANUAL 按安全全红边界生效。配时仅在控制 ENABLED 且仿真 RUNNING 时可提交。</p>
      </div>

      <TimingPlanManager
        tlsId={tlsId}
        mode={mode}
        draft={draft}
        canOperateSignal={canOperateSignal}
        onDraftChange={setDraft}
      />

      <div className="panel feedback-panel">
        <div className="panel-heading">
          <div>
            <div className="eyebrow">OPERATION FEEDBACK</div>
            <h2>操作反馈</h2>
          </div>
          <span className="subtle-tag">服务端权威结果</span>
        </div>
        {notice ? (
          <div className={`notice notice-${notice.kind}`} role="status" aria-live="polite">{notice.text}</div>
        ) : (
          <p className="muted">尚无操作。控制请求成功或失败后，后端响应原因会显示在这里。</p>
        )}
        <div className="feedback-footnote">
          {connected ? "实时状态连接正常。" : "WebSocket 当前断开；控制请求仍由 REST 后端处理，状态显示可能暂时滞后。"}
          {busy ? ` 当前操作：${busy}` : ""}
        </div>
      </div>
    </section>
  );
}
