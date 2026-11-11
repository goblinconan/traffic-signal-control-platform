"""信号 REST 路由：状态、配时、手动切换。
输入：HTTP 请求体、路径参数。
输出：Pydantic 响应。
依赖：services/signal_service.py、models/signal.py。
调用方：前端 api/signal.ts。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.models.signal import PhaseId, SignalSnapshot, TimingConfig

router = APIRouter(prefix="/signals", tags=["signals"])


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
    return {
        "active": svc.timing.active.model_dump(),
        "pending": svc.timing.pending.model_dump() if svc.timing.pending else None,
        "computed": {
            "ns_red": svc.timing.active.ns_red,
            "ew_red": svc.timing.active.ew_red,
        },
    }


@router.put("/{tls_id}/timing")
async def put_timing(tls_id: str, body: TimingConfig, request: Request) -> dict:
    svc = _svc(request)
    if tls_id != svc.settings.tls_id:
        raise HTTPException(404, "unknown tls_id")
    try:
        pending = svc.submit_timing(body)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"accepted": True, "effective": "next_cycle",
            "pending_timing": pending.model_dump()}


@router.post("/{tls_id}/phases/switch")
async def switch_phase(tls_id: str, body: dict, request: Request) -> dict:
    svc = _svc(request)
    if tls_id != svc.settings.tls_id:
        raise HTTPException(404, "unknown tls_id")
    try:
        target = PhaseId(body.get("target_phase", ""))
    except ValueError as exc:
        raise HTTPException(400, "invalid target_phase") from exc
    ok, reason = svc.manual_switch(target)
    if not ok:
        raise HTTPException(409, reason)
    return {"accepted": True, "reason": reason}