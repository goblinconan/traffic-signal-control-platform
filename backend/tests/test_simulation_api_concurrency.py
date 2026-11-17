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

class BlockingStepSignalService(FakeSignalService):
    def __init__(self) -> None:
        self.started_calls = 0
        self.started = threading.Event()
        self.release = threading.Event()

    def step(self) -> None:
        self.started.set()
        if not self.release.wait(timeout=5):
            raise TimeoutError("测试未及时释放仿真步进")


def test_state_read_waits_for_inflight_simulation_step() -> None:
    class NonBlockingStartRunner(FakeRunner):
        def start(self) -> None:
            self.connected = True
            self.process_alive = True

        def stop(self) -> None:
            self.connected = False
            self.process_alive = False

    async def run_test() -> None:
        runner = NonBlockingStartRunner()
        signal_service = BlockingStepSignalService()
        lifecycle = SimulationLifecycle(runner, signal_service)
        await lifecycle.start()

        step_task = asyncio.create_task(lifecycle.step_once())
        entered = await asyncio.to_thread(signal_service.started.wait, 3)
        assert entered, "仿真步进未进入阻塞区间"

        read_started = asyncio.Event()
        def read_marker() -> str:
            read_started.set()
            return "consistent-state"

        read_task = asyncio.create_task(lifecycle.read_state(read_marker))
        await asyncio.sleep(0.05)
        assert not read_task.done(), "状态读取不应越过正在执行的仿真 step"

        signal_service.release.set()
        await asyncio.wait_for(step_task, timeout=3)
        result = await asyncio.wait_for(read_task, timeout=3)
        assert result == "consistent-state"
        assert read_started.is_set()
        await lifecycle.stop()

    asyncio.run(run_test())
