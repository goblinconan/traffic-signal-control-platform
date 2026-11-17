"""FastAPI 入口：装配 Runner、SignalService、REST、WebSocket 和可安全关闭的仿真循环。
输入：HTTP/WS 请求、环境变量。
输出：运行中的 ASGI 应用。
依赖：services/signal_service.py、simulation/sumo_runner.py、simulation/lifecycle.py。
调用方：uvicorn。
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import intersection, signal, simulation
from app.api.websocket import manager, websocket_endpoint
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.services.signal_service import SignalService
from app.services.state_service import RuntimeStateService
from app.simulation.lifecycle import SimulationLifecycle
from app.simulation.sumo_runner import SumoRunner

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

    runner = SumoRunner(settings=settings)
    svc = SignalService.create(settings, runner)
    app.state.settings = settings
    app.state.runner = runner
    app.state.signal_service = svc
    lifecycle = SimulationLifecycle(runner, svc)
    app.state.lifecycle = lifecycle
    app.state.state_service = RuntimeStateService(lifecycle, svc, runner, settings)

    stop_event = asyncio.Event()
    task = asyncio.create_task(_loop(app, stop_event), name="simulation-loop")
    try:
        yield
    finally:
        # 不取消正在 await asyncio.to_thread 的循环任务；先发出退出信号，
        # 让当前 step 自然完成，再由 lifecycle.shutdown 串行关闭 TraCI/SUMO。
        stop_event.set()
        try:
            await task
        except asyncio.CancelledError:
            log.warning("simulation loop was externally cancelled")
        except Exception:
            log.exception("simulation loop terminated unexpectedly")
        finally:
            await lifecycle.shutdown()


async def _loop(app: FastAPI, stop_event: asyncio.Event | None = None) -> None:
    """只在 RUNNING 时步进；关闭事件不会取消正在执行的 TraCI 工作线程。"""
    runner: SumoRunner = app.state.runner
    lifecycle: SimulationLifecycle = app.state.lifecycle
    svc: SignalService = app.state.signal_service
    last_broadcast_status: str | None = None
    while stop_event is None or not stop_event.is_set():
        await lifecycle.step_once()
        current_status = lifecycle.status.value
        should_publish = bool(manager._clients) and (
            current_status == "RUNNING" or current_status != last_broadcast_status
        )
        if should_publish:
            try:
                payload = await app.state.state_service.create_message("simulation_update")
                await manager.broadcast(payload)
                last_broadcast_status = current_status
            except Exception:
                log.exception("simulation broadcast failed")

        if stop_event is None:
            await asyncio.sleep(0.05)
        else:
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=0.05)
            except asyncio.TimeoutError:
                pass


def create_app() -> FastAPI:
    setup_logging()
    app = FastAPI(title=get_settings().app_name, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(signal.router, prefix="/api")
    app.include_router(simulation.router, prefix="/api")
    app.include_router(intersection.router, prefix="/api")

    @app.get("/api/health")
    async def health() -> dict:
        lifecycle: SimulationLifecycle = app.state.lifecycle
        snapshot = await lifecycle.refresh_health()
        return {
            "status": "ok",
            "sumo_connected": snapshot.sumo_connected,
            "simulation_status": snapshot.status.value,
            "process_alive": snapshot.process_alive,
        }

    @app.websocket("/ws/simulation")
    async def ws(websocket: WebSocket) -> None:
        await websocket_endpoint(websocket, app)

    return app


app = create_app()
