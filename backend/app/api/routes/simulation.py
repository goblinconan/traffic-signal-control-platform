"""仿真 REST 路由：启动、停止、状态。
输入：HTTP 请求。
输出：JSON。
依赖：SumoRunner、SignalService。
调用方：前端 api/simulation.ts。
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/simulation", tags=["simulation"])


def _runner(request: Request):
    return request.app.state.runner


def _svc(request: Request):
    return request.app.state.signal_service


@router.get("/status")
async def status(request: Request) -> dict:
    runner = _runner(request)
    return {
        "status": "running" if runner.running else "stopped",
        "simulation_time": runner.simulation_time(),
        "sumo_connected": runner.connected,
    }


@router.post("/start")
async def start(request: Request) -> dict:
    runner = _runner(request)
    if runner.running:
        raise HTTPException(409, "already running")
    try:
        # 将阻塞的 SUMO 启动放入线程池执行
        await asyncio.to_thread(runner.start)
        await asyncio.to_thread(_svc(request).on_started)
    except Exception as exc:
        raise HTTPException(503, f"sumo start failed: {exc}") from exc
    return {"status": "running"}


@router.post("/stop")
async def stop(request: Request) -> dict:
    runner = _runner(request)
    runner._running = False
    runner._connected = False
    # 用后台线程去关闭 TraCI，防止阻塞主线程
    import threading
    threading.Thread(target=runner.stop, daemon=True).start()
    return {"status": "stopped"}