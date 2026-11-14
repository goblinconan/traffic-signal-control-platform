"""仿真 REST API 并发启动测试。"""

from __future__ import annotations

import asyncio
import threading

import httpx
from fastapi import FastAPI

from app.api.routes import simulation
from app.simulation.lifecycle import SimulationLifecycle


class FakeRunner:
    def __init__(self) -> None:
        self.connected = False
        self.process_alive = False
        self.step_index = 0
        self.simulation_time_value = 0.0
        self.start_calls = 0
        self.stop_calls = 0

        self.start_entered = threading.Event()
        self.release_start = threading.Event()

    @property
    def cleanup_pending(self) -> bool:
        return False

    def simulation_time(self) -> float:
        return self.simulation_time_value

    def start(self) -> None:
        self.start_calls += 1
        self.start_entered.set()

        if not self.release_start.wait(timeout=5):
            raise TimeoutError("测试未及时释放 Runner.start")

        self.connected = True
        self.process_alive = True

    def stop(self) -> None:
        self.stop_calls += 1
        self.connected = False
        self.process_alive = False


class FakeSignalService:
    def __init__(self) -> None:
        self.started_calls = 0

    def on_started(self) -> None:
        self.started_calls += 1

    def step(self) -> None:
        pass


def test_concurrent_http_start_only_starts_runner_once() -> None:
    async def run_test() -> None:
        runner = FakeRunner()
        signal_service = FakeSignalService()
        lifecycle = SimulationLifecycle(runner, signal_service)

        app = FastAPI()
        app.include_router(simulation.router, prefix="/api")
        app.state.lifecycle = lifecycle

        transport = httpx.ASGITransport(app=app)

        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            first_request = asyncio.create_task(
                client.post("/api/simulation/start")
            )

            entered = await asyncio.to_thread(
                runner.start_entered.wait,
                3,
            )
            assert entered, "第一个 HTTP 请求没有进入 Runner.start"

            second_request = asyncio.create_task(
                client.post("/api/simulation/start")
            )

            # 确保第二个请求有机会进入 ASGI 请求处理流程。
            await asyncio.sleep(0.05)

            runner.release_start.set()

            first_response, second_response = await asyncio.gather(
                first_request,
                second_request,
            )

        assert first_response.status_code == 200
        assert first_response.json()["lifecycle_status"] == "RUNNING"

        assert second_response.status_code == 409

        assert runner.start_calls == 1
        assert signal_service.started_calls == 1
        assert lifecycle.status.value == "RUNNING"

    asyncio.run(run_test())