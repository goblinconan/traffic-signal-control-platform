"""B5.1 MANUAL 配时方案库 API。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from app.models.signal import ControlMode, ControlStatus, TimingConfig
from app.services.timing_plan_store import TimingPlanStoreError
from app.simulation.lifecycle import LifecycleError

router = APIRouter(prefix="/signals", tags=["timing-plans"])


class SaveTimingPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=60)
    # TimingConfig 自身含完整字段、绿/黄灯和四类红灯时长校验。
    config: TimingConfig


def _services(request: Request, tls_id: str):
    svc = request.app.state.signal_service
    if tls_id != svc.settings.tls_id:
        raise HTTPException(404, "unknown tls_id")
    return svc, request.app.state.timing_plan_store, request.app.state.lifecycle


def _require_manual_enabled(svc) -> None:
    if svc.control_mode != ControlMode.MANUAL:
        raise ValueError("配时方案库仅允许在 MANUAL 模式下操作")
    if svc.control_status != ControlStatus.ENABLED:
        raise ValueError("信号控制未启用，拒绝配时方案操作")


def _require_running(lifecycle) -> None:
    if lifecycle.status.value != "RUNNING":
        raise LifecycleError("只有仿真 RUNNING 时才能操作配时方案库", 409)


def _translate(exc: Exception):
    if isinstance(exc, HTTPException):
        raise exc
    if isinstance(exc, LifecycleError):
        raise HTTPException(exc.status_code, str(exc)) from exc
    if isinstance(exc, (ValueError, KeyError)):
        raise HTTPException(409, str(exc)) from exc
    if isinstance(exc, TimingPlanStoreError):
        raise HTTPException(500, str(exc)) from exc
    raise exc


async def _run_locked_read(lifecycle, action):
    """借用 lifecycle 的同一把锁，避免与仿真 step/控制模式切换并发。"""
    try:
        return await lifecycle.read_state(action)
    except Exception as exc:
        _translate(exc)


async def list_timing_plans(tls_id: str, request: Request) -> dict:
    svc, store, lifecycle = _services(request, tls_id)

    def action():
        _require_running(lifecycle)
        _require_manual_enabled(svc)
        return store.snapshot(tls_id)

    return await _run_locked_read(lifecycle, action)


async def save_timing_plan(tls_id: str, body: SaveTimingPlanRequest, request: Request) -> dict:
    svc, store, lifecycle = _services(request, tls_id)

    def action():
        _require_running(lifecycle)
        _require_manual_enabled(svc)
        return {"plan": store.save(tls_id, body.name, body.config)}

    return await _run_locked_read(lifecycle, action)


async def delete_timing_plan(tls_id: str, plan_id: str, request: Request) -> dict:
    svc, store, lifecycle = _services(request, tls_id)

    def action():
        _require_running(lifecycle)
        _require_manual_enabled(svc)
        store.delete(tls_id, plan_id)
        return {"deleted": True, "plan_id": plan_id}

    return await _run_locked_read(lifecycle, action)


async def apply_timing_plan(tls_id: str, plan_id: str, request: Request) -> dict:
    svc, store, lifecycle = _services(request, tls_id)

    def action():
        _require_manual_enabled(svc)
        # 在 lifecycle 锁内读取，避免与删除/其他控制操作产生竞态。
        plan, config = store.get_plan(tls_id, plan_id)
        return svc.submit_timing(
            config,
            source={
                "kind": "saved_plan",
                "name": plan["name"],
                "plan_id": plan["plan_id"],
            },
        )

    try:
        return await lifecycle.run_control_action(action)
    except Exception as exc:
        _translate(exc)


async def restore_default_timing(tls_id: str, request: Request) -> dict:
    svc, store, lifecycle = _services(request, tls_id)

    def action():
        _require_manual_enabled(svc)
        default = TimingConfig.model_validate(store.snapshot(tls_id)["default_timing"])
        return svc.submit_timing(default)

    try:
        return await lifecycle.run_control_action(action)
    except Exception as exc:
        _translate(exc)


router.add_api_route("/{tls_id}/timing-plans", list_timing_plans, methods=["GET"])
router.add_api_route("/{tls_id}/timing-plans", save_timing_plan, methods=["POST"])
router.add_api_route("/{tls_id}/timing-plans/{plan_id}", delete_timing_plan, methods=["DELETE"])
router.add_api_route("/{tls_id}/timing-plans/{plan_id}/apply", apply_timing_plan, methods=["POST"])
router.add_api_route("/{tls_id}/timing-plans/restore-default", restore_default_timing, methods=["POST"])
