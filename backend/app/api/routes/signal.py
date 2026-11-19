
"""信号 REST 路由：状态、配时和受控阶段切换。
输入：HTTP 请求体、路径参数。
输出：经过校验的信号状态及配时响应。
依赖：SignalService、models/signal.py。
调用方：浏览器信号控制台。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.signal import ControlMode, PhaseId, SignalSnapshot, TimingConfig
from app.simulation.lifecycle import LifecycleError

router = APIRouter(prefix="/signals", tags=["signals"])


class PhaseSwitchRequest(BaseModel):
    target_phase: PhaseId


class TimingUpdateRequest(BaseModel):
    """PUT 配时接口要求一次提交完整的八个绿/黄灯参数。"""

    model_config = ConfigDict(extra="forbid")

    ns_left_green: float = Field(gt=8)
    ns_left_yellow: float = Field(gt=0)
    ns_straight_green: float = Field(gt=8)
    ns_straight_yellow: float = Field(gt=0)
    ew_left_green: float = Field(gt=8)
    ew_left_yellow: float = Field(gt=0)
    ew_straight_green: float = Field(gt=8)
    ew_straight_yellow: float = Field(gt=0)

    @model_validator(mode="after")
    def validate_red_durations(self):
        cycle = sum((
            self.ns_left_green, self.ns_left_yellow,
            self.ns_straight_green, self.ns_straight_yellow,
            self.ew_left_green, self.ew_left_yellow,
            self.ew_straight_green, self.ew_straight_yellow,
        ))
        red_values = (
            cycle - self.ns_left_green - self.ns_left_yellow,
            cycle - self.ns_straight_green - self.ns_straight_yellow,
            cycle - self.ew_left_green - self.ew_left_yellow,
            cycle - self.ew_straight_green - self.ew_straight_yellow,
        )
        if any(value <= 10 for value in red_values):
            raise ValueError("四类受保护信号组的红灯总时长必须分别 >10s")
        return self

    def to_timing_config(self) -> TimingConfig:
        return TimingConfig(**self.model_dump())


class ControlEnabledRequest(BaseModel):
    enabled: bool


class ControlModeRequest(BaseModel):
    mode: ControlMode


def _svc(request: Request):
    return request.app.state.signal_service


@router.get("/{tls_id}/state", response_model=SignalSnapshot)
async def get_state(tls_id: str, request: Request) -> SignalSnapshot:
    svc = _svc(request)
    if tls_id != svc.settings.tls_id:
        raise HTTPException(404, "unknown tls_id")
    return svc.snapshot()


@router.get("/{tls_id}/control")
async def get_control(tls_id: str, request: Request) -> dict:
    svc = _svc(request)
    if tls_id != svc.settings.tls_id:
        raise HTTPException(404, "unknown tls_id")
    return svc.control_state()


@router.put("/{tls_id}/control/enabled")
async def put_control_enabled(
    tls_id: str, body: ControlEnabledRequest, request: Request
) -> dict:
    svc = _svc(request)
    if tls_id != svc.settings.tls_id:
        raise HTTPException(404, "unknown tls_id")
    lifecycle = request.app.state.lifecycle
    try:
        return await lifecycle.run_control_action(
            lambda: svc.request_control_enabled(body.enabled)
        )
    except LifecycleError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.put("/{tls_id}/control/mode")
async def put_control_mode(
    tls_id: str, body: ControlModeRequest, request: Request
) -> dict:
    svc = _svc(request)
    if tls_id != svc.settings.tls_id:
        raise HTTPException(404, "unknown tls_id")
    lifecycle = request.app.state.lifecycle
    try:
        return await lifecycle.run_control_action(
            lambda: svc.request_control_mode(body.mode)
        )
    except LifecycleError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/{tls_id}/timing")
async def get_timing(tls_id: str, request: Request) -> dict:
    svc = _svc(request)
    if tls_id != svc.settings.tls_id:
        raise HTTPException(404, "unknown tls_id")
    return svc.timing_snapshot()


@router.put("/{tls_id}/timing")
async def put_timing(
    tls_id: str, body: TimingUpdateRequest, request: Request
) -> dict:
    svc = _svc(request)
    if tls_id != svc.settings.tls_id:
        raise HTTPException(404, "unknown tls_id")
    lifecycle = request.app.state.lifecycle
    try:
        return await lifecycle.run_control_action(
            lambda: svc.submit_timing(body.to_timing_config())
        )
    except LifecycleError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/{tls_id}/phases/switch")
async def switch_phase(
    tls_id: str, body: PhaseSwitchRequest, request: Request
) -> dict:
    svc = _svc(request)
    if tls_id != svc.settings.tls_id:
        raise HTTPException(404, "unknown tls_id")
    lifecycle = request.app.state.lifecycle
    try:
        ok, reason = await lifecycle.run_control_action(
            lambda: svc.manual_switch(body.target_phase)
        )
    except LifecycleError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    if not ok:
        raise HTTPException(409, reason)
    status = "started" if reason == "started_from_all_red" else (
        "unchanged" if reason == "already_in_phase" else "queued"
    )
    return {"accepted": True, "status": status, "reason": reason}
