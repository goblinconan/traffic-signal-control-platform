
"""WebSocket 推送：初始发送静态路网，持续发送信号 + 车辆快照。
输入：已连接客户端。
输出：simulation_update JSON。
依赖：SignalService、SumoRunner、network_geometry。
调用方：前端 hooks/useWebSocket.ts。
"""
from __future__ import annotations

import asyncio
import logging
from functools import lru_cache
from pathlib import Path

from fastapi import WebSocket, WebSocketDisconnect

from app.simulation.network_geometry import load_network_geometry

log = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
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


@lru_cache(maxsize=4)
def _load_network_geometry(net_file: str) -> dict:
    """缓存静态路网，避免重复解析 XML。"""
    return load_network_geometry(net_file)


def _get_network_geometry(settings) -> dict:
    """根据 SUMO 配置文件定位 net.xml。"""
    sumo_config = Path(settings.sumo_config).resolve()

    if not sumo_config.is_file():
        raise FileNotFoundError(f"SUMO 配置文件不存在: {sumo_config}")

    import xml.etree.ElementTree as ET

    root = ET.parse(sumo_config).getroot()
    net_element = root.find("./input/net-file")

    if net_element is None:
        raise ValueError("SUMO 配置文件缺少 input/net-file")

    net_value = net_element.get("value")

    if not net_value:
        raise ValueError("SUMO 配置文件的 net-file 缺少 value")

    net_path = Path(net_value)

    if not net_path.is_absolute():
        net_path = (sumo_config.parent / net_path).resolve()

    return _load_network_geometry(str(net_path))


async def websocket_endpoint(ws: WebSocket, app) -> None:
    await manager.connect(ws)
    svc = app.state.signal_service
    runner = app.state.runner

    try:
        # 连接时发送一次完整快照，包含静态路网几何。
        payload = _payload(svc, runner)
        payload["network"] = await asyncio.to_thread(
            _get_network_geometry,
            app.state.settings,
        )
        await ws.send_json(payload)

        while True:
            # 动态仿真数据由 main.py 后台循环广播。
            await asyncio.sleep(3600)

    except WebSocketDisconnect:
        manager.disconnect(ws)
    except Exception:
        log.exception("websocket error")
        manager.disconnect(ws)


def _payload(svc, runner) -> dict:
    snap = svc.snapshot()

    return {
        "type": "simulation_update",
        "simulation_time": runner.simulation_time(),
        "simulation_status": "running" if runner.running else "stopped",
        "signal": snap.model_dump(),
        "vehicles": [v.__dict__ for v in runner.vehicles()],
    }
