
"""信号 REST 路由：状态、配时和受控阶段切换。
输入：HTTP 请求体、路径参数。
输出：经过校验的信号状态及配时响应。
依赖：SignalService、models/signal.py。
调用方：浏览器信号控制台。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.models.signal import PhaseId, SignalSnapshot, TimingConfig

router = APIRouter(prefix="/signals", tags=["signals"])


class PhaseSwitchRequest(BaseModel):
    target_phase: PhaseId


def _svc(request: Request):
    return request.app.state.signal_service


@router.get("/{tls_id}/state", response_model=SignalSnapshot)
async def get_state(tls_id: str, request: Request) -> SignalSnapshot:
    svc = _svc(request)
    if tls_id != svc.settings.tls_id:
        raise HTTPException(404, "unknown tls_id")
    return svc.snapshot()


@router.get("/{tls_id}/timing")
async def get_timing(tls_id: str, request: Request) -> dict:
    svc = _svc(request)
    if tls_id != svc.settings.tls_id:
        raise HTTPException(404, "unknown tls_id")
    timing = svc.timing.active
    return {
        "active": timing.model_dump(),
        "pending": svc.timing.pending.model_dump() if svc.timing.pending else None,
        "computed": {
            "ns_left_red": timing.ns_left_red,
            "ns_straight_red": timing.ns_straight_red,
            "ew_left_red": timing.ew_left_red,
            "ew_straight_red": timing.ew_straight_red,
        },
    }


@router.put("/{tls_id}/timing")
async def put_timing(
    tls_id: str, body: TimingConfig, request: Request
) -> dict:
    svc = _svc(request)
    if tls_id != svc.settings.tls_id:
        raise HTTPException(404, "unknown tls_id")
    try:
        pending = svc.submit_timing(body)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {
        "accepted": True,
        "effective": "next_complete_cycle",
        "pending_timing": pending.model_dump(),
    }


@router.post("/{tls_id}/phases/switch")
async def switch_phase(
    tls_id: str, body: PhaseSwitchRequest, request: Request
) -> dict:
    svc = _svc(request)
    if tls_id != svc.settings.tls_id:
        raise HTTPException(404, "unknown tls_id")
    ok, reason = svc.manual_switch(body.target_phase)
    if not ok:
        raise HTTPException(409, reason)
    return {"accepted": True, "reason": reason}
