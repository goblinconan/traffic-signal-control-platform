"""仿真 REST API 契约测试。"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes.simulation import router
from app.simulation.lifecycle import SimulationLifecycle


class FakeRunner:
    def __init__(self):
        self.connected = False
        self.running = False
        self.step_index = 0
        self.process_alive = False
        self.time = 0.0

    def start(self):
        self.connected = self.running = self.process_alive = True

    def stop(self):
        self.connected = self.running = self.process_alive = False

    def simulation_time(self):
        return self.time


class FakeService:
    def on_started(self):
        pass

    def step(self):
        pass


def client_with_lifecycle():
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.state.lifecycle = SimulationLifecycle(FakeRunner(), FakeService())
    return TestClient(app)


def test_status_start_conflict_and_idempotent_stop():
    with client_with_lifecycle() as client:
        initial = client.get("/api/simulation/status")
        assert initial.status_code == 200
        assert initial.json()["lifecycle_status"] == "STOPPED"

        started = client.post("/api/simulation/start")
        assert started.status_code == 200
        assert started.json()["lifecycle_status"] == "RUNNING"
        assert started.json()["sumo_connected"] is True

        duplicate = client.post("/api/simulation/start")
        assert duplicate.status_code == 409

        stopped = client.post("/api/simulation/stop")
        assert stopped.status_code == 200
        assert stopped.json()["lifecycle_status"] == "STOPPED"
        assert stopped.json()["sumo_connected"] is False

        repeated = client.post("/api/simulation/stop")
        assert repeated.status_code == 200
        assert repeated.json()["lifecycle_status"] == "STOPPED"
