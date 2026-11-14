"""SimulationLifecycle 单元测试：覆盖正常、重复、失败及步进异常路径。"""
from __future__ import annotations

import asyncio

import pytest

from app.simulation.lifecycle import (
    LifecycleError,
    SimulationLifecycle,
    SimulationStatus,
)


class FakeRunner:
    def __init__(self) -> None:
        self.connected = False
        self.running = False
        self.time = 0.0
        self.start_calls = 0
        self.stop_calls = 0
        self.fail_start = False

    def start(self) -> None:
        self.start_calls += 1
        if self.fail_start:
            raise RuntimeError("fake start failure")
        self.connected = True
        self.running = True

    def stop(self) -> None:
        self.stop_calls += 1
        self.connected = False
        self.running = False

    def simulation_time(self) -> float:
        return self.time


class FakeSignalService:
    def __init__(self) -> None:
        self.started_calls = 0
        self.step_calls = 0
        self.fail_step = False

    def on_started(self) -> None:
        self.started_calls += 1

    def step(self) -> None:
        self.step_calls += 1
        if self.fail_step:
            raise RuntimeError("fake step failure")


def run(coro):
    return asyncio.run(coro)


def test_start_and_stop_transition_through_expected_states():
    runner = FakeRunner()
    service = FakeSignalService()
    lifecycle = SimulationLifecycle(runner, service)

    async def scenario():
        started = await lifecycle.start()
        assert started.status == SimulationStatus.RUNNING
        assert started.sumo_connected is True
        assert service.started_calls == 1

        stopped = await lifecycle.stop()
        assert stopped.status == SimulationStatus.STOPPED
        assert stopped.sumo_connected is False

    run(scenario())


def test_repeated_start_is_rejected_and_stop_is_idempotent():
    runner = FakeRunner()
    lifecycle = SimulationLifecycle(runner, FakeSignalService())

    async def scenario():
        await lifecycle.start()
        with pytest.raises(LifecycleError) as error:
            await lifecycle.start()
        assert error.value.status_code == 409
        stopped = await lifecycle.stop()
        assert stopped.status == SimulationStatus.STOPPED
        assert (await lifecycle.stop()).status == SimulationStatus.STOPPED
        assert runner.start_calls == 1

    run(scenario())


def test_start_failure_cleans_runner_and_records_failed_state():
    runner = FakeRunner()
    runner.fail_start = True
    lifecycle = SimulationLifecycle(runner, FakeSignalService())

    async def scenario():
        with pytest.raises(LifecycleError) as error:
            await lifecycle.start()
        assert error.value.status_code == 503
        snapshot = lifecycle.snapshot()
        assert snapshot.status == SimulationStatus.FAILED
        assert "fake start failure" in (snapshot.last_error or "")
        assert runner.connected is False

    run(scenario())


def test_step_failure_marks_failed_and_cleans_runner():
    runner = FakeRunner()
    service = FakeSignalService()
    service.fail_step = True
    lifecycle = SimulationLifecycle(runner, service)

    async def scenario():
        await lifecycle.start()
        await lifecycle.step_once()
        snapshot = lifecycle.snapshot()
        assert snapshot.status == SimulationStatus.FAILED
        assert snapshot.sumo_connected is False
        assert "fake step failure" in (snapshot.last_error or "")

    run(scenario())


def test_step_is_ignored_when_not_running():
    runner = FakeRunner()
    service = FakeSignalService()
    lifecycle = SimulationLifecycle(runner, service)

    async def scenario():
        await lifecycle.step_once()
        assert service.step_calls == 0

    run(scenario())


def test_shutdown_waits_for_inflight_step_before_stopping_runner():
    import threading

    runner = FakeRunner()
    entered = threading.Event()
    release = threading.Event()

    class BlockingService(FakeSignalService):
        def step(self):
            entered.set()
            assert release.wait(timeout=3)
            self.step_calls += 1

    lifecycle = SimulationLifecycle(runner, BlockingService())

    async def scenario():
        await lifecycle.start()
        step_task = asyncio.create_task(lifecycle.step_once())
        assert await asyncio.to_thread(entered.wait, 1)
        shutdown_task = asyncio.create_task(lifecycle.shutdown())
        await asyncio.sleep(0.05)
        assert runner.stop_calls == 0
        release.set()
        await step_task
        await shutdown_task
        assert runner.stop_calls == 1
        assert lifecycle.status == SimulationStatus.STOPPED

    run(scenario())


def test_concurrent_start_requests_only_start_runner_once():
    runner = FakeRunner()
    lifecycle = SimulationLifecycle(runner, FakeSignalService())

    async def scenario():
        results = await asyncio.gather(
            lifecycle.start(), lifecycle.start(), return_exceptions=True
        )
        assert sum(not isinstance(item, Exception) for item in results) == 1
        assert sum(isinstance(item, LifecycleError) for item in results) == 1
        assert runner.start_calls == 1

    run(scenario())


def test_stop_failure_keeps_failed_state_and_error():
    class FailingStopRunner(FakeRunner):
        def stop(self):
            self.stop_calls += 1
            raise RuntimeError("fake stop failure")

    runner = FailingStopRunner()
    lifecycle = SimulationLifecycle(runner, FakeSignalService())

    async def scenario():
        await lifecycle.start()
        with pytest.raises(LifecycleError) as error:
            await lifecycle.stop()
        assert error.value.status_code == 503
        assert lifecycle.status == SimulationStatus.FAILED
        assert "fake stop failure" in (lifecycle.snapshot().last_error or "")

    run(scenario())


def test_external_sumo_exit_is_detected_by_health_refresh():
    runner = FakeRunner()
    lifecycle = SimulationLifecycle(runner, FakeSignalService())

    async def scenario():
        await lifecycle.start()
        runner.connected = False
        snapshot = await lifecycle.refresh_health()
        assert snapshot.status == SimulationStatus.FAILED
        assert "进程已退出" in (snapshot.last_error or "")
        assert runner.stop_calls == 1

    run(scenario())


def test_health_refresh_detects_broken_traci_query():
    class BrokenQueryRunner(FakeRunner):
        fail_query = False

        def simulation_time(self):
            if self.fail_query:
                raise RuntimeError("fake TraCI socket failure")
            return self.time

    runner = BrokenQueryRunner()
    lifecycle = SimulationLifecycle(runner, FakeSignalService())

    async def scenario():
        await lifecycle.start()
        runner.fail_query = True
        snapshot = await lifecycle.refresh_health()
        assert snapshot.status == SimulationStatus.FAILED
        assert "fake TraCI socket failure" in (snapshot.last_error or "")
        assert snapshot.sumo_connected is False

    run(scenario())
