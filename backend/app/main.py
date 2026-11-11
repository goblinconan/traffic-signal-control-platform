"""FastAPI 入口：装配 Runner、SignalService、REST、WebSocket、后台仿真循环。
输入：HTTP/WS 请求、环境变量。
输出：运行中的 ASGI 应用。
依赖：services/signal_service.py、simulation/sumo_runner.py。
调用方：uvicorn。
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import signal, simulation
from app.api.websocket import _payload, manager, websocket_endpoint
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.services.signal_service import SignalService
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
    task = asyncio.create_task(_loop(app))
    yield
    task.cancel()
    runner.stop()


async def _loop(app: FastAPI) -> None:
    runner: SumoRunner = app.state.runner
    svc: SignalService = app.state.signal_service
    while True:
        if runner.running:
            try:
                # 【关键修改】用 to_thread 把阻塞的 TraCI 调用挪出事件循环
                await asyncio.to_thread(svc.step)
                if manager._clients:
                    await manager.broadcast(_payload(svc, runner))
            except Exception:
                log.exception("simulation step failed")
        await asyncio.sleep(0.05)


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

    @app.get("/api/health")
    async def health() -> dict:
        runner: SumoRunner = app.state.runner
        return {"status": "ok", "sumo_connected": runner.connected}

    @app.websocket("/ws/simulation")
    async def ws(websocket: WebSocket) -> None:
        await websocket_endpoint(websocket, app)

    return app


app = create_app()