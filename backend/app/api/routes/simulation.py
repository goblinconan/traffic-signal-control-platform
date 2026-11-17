"""仿真 REST 路由：启动、停止和生命周期状态查询。
输入：HTTP 请求及应用状态中的 SimulationLifecycle。
输出：生命周期快照或明确的 HTTP 错误。
依赖：simulation/lifecycle.py。
调用方：浏览器控制台及自动化测试。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.models.runtime_state import RuntimeStateMessage
from app.simulation.lifecycle import LifecycleError, SimulationLifecycle

router = APIRouter(prefix="/simulation", tags=["simulation"])


def _lifecycle(request: Request) -> SimulationLifecycle:
    return request.app.state.lifecycle


@router.get("/state", response_model=RuntimeStateMessage)
async def unified_state(request: Request) -> dict:
    """B4 统一运行状态；字段结构与 WebSocket 初始快照一致。"""
    return await request.app.state.state_service.create_message("simulation_snapshot")


@router.get("/status")
async def status(request: Request) -> dict:
    snapshot = await _lifecycle(request).refresh_health()
    return snapshot.to_dict()


@router.post("/start")
async def start(request: Request) -> dict:
    try:
        snapshot = await _lifecycle(request).start()
        return snapshot.to_dict()
    except LifecycleError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post("/stop")
async def stop(request: Request) -> dict:
    try:
        snapshot = await _lifecycle(request).stop()
        return snapshot.to_dict()
    except LifecycleError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
