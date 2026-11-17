"""B4 统一运行状态 REST 接口测试。"""
from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
from fastapi import FastAPI

from app.api.routes import intersection, simulation
from app.core.config import Settings
from app.services.state_service import RuntimeStateService
from app.services.signal_service import SignalService
from app.simulation.lifecycle import LifecycleSnapshot, SimulationStatus


ROOT = Path(__file__).resolve().parents[2]


class FakeRunner:
    connected = False
    process_alive = False
    step_index = 0
    def simulation_time(self): return 0.0
    def vehicles(self): return []


class FakeLifecycle:
    def __init__(self, runner): self.runner = runner
    def snapshot(self):
        return LifecycleSnapshot(SimulationStatus.STOPPED, 0.0, False, None, 0, False)
    async def read_state(self, function): return function()


def test_unified_state_and_network_rest_endpoints():
    async def run():
        runner = FakeRunner()
        settings = Settings(sumo_config=str(ROOT / "simulation/config/intersection.sumocfg"), tls_id="intersection_0")
        svc = SignalService.create(settings, runner)
        lifecycle = FakeLifecycle(runner)
        state_service = RuntimeStateService(lifecycle, svc, runner, settings)
        app = FastAPI()
        app.include_router(simulation.router, prefix="/api")
        app.include_router(intersection.router, prefix="/api")
        app.state.state_service = state_service
        app.state.lifecycle = lifecycle
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            state = await client.get("/api/simulation/state")
            network = await client.get("/api/intersections/intersection_0/network")
            unknown = await client.get("/api/intersections/unknown/network")
        assert state.status_code == 200
        assert state.json()["type"] == "simulation_snapshot"
        assert state.json()["simulation_status"] == "STOPPED"
        assert network.status_code == 200
        assert network.json()["network_version"] == state.json()["network_version"]
        assert network.json()["geometry"]["edges"]
        assert unknown.status_code == 404
    asyncio.run(run())
