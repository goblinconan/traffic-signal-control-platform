"""FastAPI lifespan 关闭时的仿真资源清理测试。"""

from __future__ import annotations

import asyncio
import threading

from fastapi import FastAPI

from app import main


class FakeSettings:
    app_name = "Lifecycle Test"
    tls_id = "intersection_0"
    sumo_config = str(
        __import__("pathlib").Path(__file__).resolve().parents[2]
        / "simulation" / "config" / "intersection.sumocfg"
    )


class FakeRunner:
    def __init__(self, settings) -> None:
        self.settings = settings
        self.connected = False
        self.process_alive = False
        self.step_index = 0
        self.simulation_time_value = 0.0
        self.start_calls = 0
        self.stop_calls = 0

    @property
    def cleanup_pending(self) -> bool:
        return False

    def simulation_time(self) -> float:
        return self.simulation_time_value

    def start(self) -> None:
        self.start_calls += 1
        self.connected = True
        self.process_alive = True

    def stop(self) -> None:
        self.stop_calls += 1
        self.connected = False
        self.process_alive = False


class FakeSignalService:
    @staticmethod
    def configured_timing(settings):
        from app.models.signal import TimingConfig

        return TimingConfig(
            ns_left_green=20.0,
            ns_left_yellow=3.0,
            ns_straight_green=40.0,
            ns_straight_yellow=3.0,
            ew_left_green=20.0,
            ew_left_yellow=3.0,
            ew_straight_green=40.0,
            ew_straight_yellow=3.0,
        )

    def __init__(self, runner: FakeRunner) -> None:
        self.runner = runner
        self.step_started = threading.Event()
        self.release_step = threading.Event()
        self.step_calls = 0

    @classmethod
    def create(cls, settings, runner, initial_timing=None):
        return cls(runner)

    def on_started(self) -> None:
        pass

    def step(self) -> None:
        self.step_calls += 1
        self.step_started.set()

        if not self.release_step.wait(timeout=5):
            raise TimeoutError("测试未及时释放正在执行的仿真步进")


def test_lifespan_waits_for_inflight_step_before_runner_cleanup(
    monkeypatch,
) -> None:
    async def run_test() -> None:
        monkeypatch.setattr(
            main,
            "get_settings",
            lambda: FakeSettings(),
        )
        monkeypatch.setattr(
            main,
            "SumoRunner",
            FakeRunner,
        )
        monkeypatch.setattr(
            main,
            "SignalService",
            FakeSignalService,
        )

        app = FastAPI()

        lifespan_context = main.lifespan(app)
        await lifespan_context.__aenter__()

        runner = app.state.runner
        signal_service = app.state.signal_service
        lifecycle = app.state.lifecycle

        # 启动仿真，使后台循环进入 SignalService.step。
        await lifecycle.start()

        step_entered = await asyncio.to_thread(
            signal_service.step_started.wait,
            3,
        )
        assert step_entered, "后台循环没有进入仿真步进"

        assert runner.connected is True
        assert runner.process_alive is True
        assert runner.stop_calls == 0

        # 开始退出 lifespan。此时 step 仍被阻塞。
        shutdown_task = asyncio.create_task(
            lifespan_context.__aexit__(None, None, None)
        )

        await asyncio.sleep(0.1)

        # 关键断言：步进未完成之前，不能提前停止 Runner。
        assert not shutdown_task.done()
        assert runner.stop_calls == 0
        assert runner.connected is True

        # 释放正在执行的步进，允许后台循环退出。
        signal_service.release_step.set()

        await asyncio.wait_for(
            shutdown_task,
            timeout=3,
        )

        assert signal_service.step_calls >= 1
        assert runner.stop_calls == 1
        assert runner.connected is False
        assert runner.process_alive is False
        assert lifecycle.status.value == "STOPPED"

    asyncio.run(run_test())