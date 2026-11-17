"""B4 WebSocket 首次连接快照测试。"""
from __future__ import annotations

import asyncio
from fastapi import WebSocketDisconnect

from app.api.websocket import manager, websocket_endpoint


class FakeStateService:
    async def create_message(self, message_type):
        return {"type": message_type, "schema_version": "1.0", "sequence": 1}


class FakeApp:
    class State: pass
    def __init__(self):
        self.state = self.State()
        self.state.state_service = FakeStateService()


class FakeWebSocket:
    def __init__(self): self.sent = []; self.accepted = False
    async def accept(self): self.accepted = True
    async def send_json(self, payload):
        self.sent.append(payload)
        raise WebSocketDisconnect()


def test_websocket_sends_full_snapshot_first_and_disconnects_cleanly():
    async def run():
        ws = FakeWebSocket()
        await websocket_endpoint(ws, FakeApp())
        assert ws.accepted is True
        assert ws.sent == [{"type": "simulation_snapshot", "schema_version": "1.0", "sequence": 1}]
        assert ws not in manager._clients
    asyncio.run(run())
