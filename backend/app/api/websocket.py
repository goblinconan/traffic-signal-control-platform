"""B4 WebSocket：连接时完整快照，运行期间发送统一动态更新。
输入：WebSocket 客户端及应用状态服务。
输出：simulation_snapshot / simulation_update 消息。
依赖：RuntimeStateService、FastAPI WebSocket。
调用方：main.py 与前端 hooks/useWebSocket.ts。
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import WebSocket, WebSocketDisconnect

log = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._clients.add(ws)

    def register(self, ws: WebSocket) -> None:
        self._clients.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self._clients.discard(ws)

    async def broadcast(self, payload: dict) -> None:
        dead: list[WebSocket] = []
        for ws in list(self._clients):
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = ConnectionManager()


async def websocket_endpoint(ws: WebSocket, app) -> None:
    try:
        await ws.accept()
        # 先发送完整快照，再注册到广播集合，保证任何 update 都不会抢在 snapshot 前面。
        payload = await app.state.state_service.create_message("simulation_snapshot")
        await ws.send_json(payload)
        manager.register(ws)
        while True:
            await asyncio.sleep(3600)
    except WebSocketDisconnect:
        manager.disconnect(ws)
    except Exception:
        log.exception("websocket error")
        manager.disconnect(ws)
