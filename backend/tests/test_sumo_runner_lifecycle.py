
"""SumoRunner 进程清理测试：验证 TraCI 连接及 SUMO 子进程的安全回收。"""
from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

from app.simulation import sumo_runner as runner_module
from app.simulation.sumo_runner import SumoRunner


class FakeProcess:
    pid = 43210

    def __init__(self, terminate_timeouts=0, kill_failures=0):
        self.returncode = None
        self.terminated = False
        self.killed = False
        self.terminate_timeouts = terminate_timeouts
        self.kill_failures = kill_failures
        self.terminate_calls = 0
        self.kill_calls = 0
        self.wait_calls = 0

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        self.wait_calls += 1
        if self.returncode is None:
            raise runner_module.subprocess.TimeoutExpired(
                cmd="sumo",
                timeout=timeout,
            )
        return self.returncode

    def terminate(self):
        self.terminate_calls += 1
        self.terminated = True
        if self.terminate_calls <= self.terminate_timeouts:
            return
        self.returncode = 1

    def kill(self):
        self.kill_calls += 1
        if self.kill_calls <= self.kill_failures:
            raise OSError("模拟 SUMO kill 失败")
        self.killed = True
        self.returncode = -9


class FakeSocket:
    def __init__(self, close_failures=0):
        self.closed = False
        self.close_failures = close_failures
        self.close_calls = 0

    def close(self):
        self.close_calls += 1
        if self.close_failures > 0:
            self.close_failures -= 1
            raise OSError("模拟 Socket 关闭失败")
        self.closed = True


class FakeConnection:
    def __init__(
        self,
        process,
        close_error=None,
        handshake_error=None,
        socket_close_failures=0,
    ):
        self._process = process
        self._socket = FakeSocket(socket_close_failures)
        self.close_error = close_error
        self.handshake_error = handshake_error
        self.close_wait = None

    def getVersion(self):
        if self.handshake_error:
            raise self.handshake_error
        return (20, "SUMO 1.28.0")

    def close(self, wait=True):
        self.close_wait = wait
        if self.close_error:
            raise self.close_error
        self._socket.closed = True


class FailOnceDict(dict):
    """指定键第一次删除时失败，后续允许正常删除。"""

    def __init__(self, *args, fail_key):
        super().__init__(*args)
        self.fail_key = fail_key
        self.failed = False

    def __delitem__(self, key):
        if key == self.fail_key and not self.failed:
            self.failed = True
            raise RuntimeError("模拟 TraCI 连接池注销失败")
        super().__delitem__(key)


class FakeTraCI:
    def __init__(
        self,
        process,
        close_error=None,
        handshake_error=None,
        socket_close_failures=0,
    ):
        self.process = process
        self.close_error = close_error
        self.handshake_error = handshake_error
        self.started = False
        self.socket_close_failures = socket_close_failures
        self.connection = SimpleNamespace(_connections={})
        self.active_connection = None
        self.junction = SimpleNamespace(
            getPosition=lambda _tls: (200.0, 200.0)
        )
        self.simulation = SimpleNamespace(getTime=lambda: 0.0)

    def connect(self, _port, host="localhost", label=None, proc=None):
        if label in self.connection._connections:
            raise RuntimeError(
                f"Connection '{label}' is already active"
            )

        self.started = proc is not None
        conn = FakeConnection(
            proc if proc is not None else self.process,
            close_error=self.close_error,
            handshake_error=self.handshake_error,
            socket_close_failures=self.socket_close_failures,
        )
        conn._label = label
        self.connection._connections[label] = conn
        return conn

    def switch(self, label):
        self.active_connection = self.connection._connections[label]
        self.connection._connections[""] = self.active_connection


def settings(tmp_path):
    return SimpleNamespace(
        sumo_home=str(tmp_path),
        sumo_config="fake.sumocfg",
        sim_step_length=0.5,
        simulation_step_delay=0.0,
        tls_id="intersection_0",
    )


def patch_runner_environment(monkeypatch, process):
    """统一配置模拟 TraCI、SUMO 可执行文件和 Popen。"""
    monkeypatch.setattr(
        runner_module.os.path,
        "exists",
        lambda _path: True,
    )
    monkeypatch.setattr(
        runner_module.subprocess,
        "Popen",
        lambda _cmd: process,
    )


def test_stop_waits_for_sumo_process_exit(monkeypatch, tmp_path):
    process = FakeProcess()
    api = FakeTraCI(process)
    monkeypatch.setattr(runner_module, "traci", api)
    patch_runner_environment(monkeypatch, process)

    runner = SumoRunner(settings(tmp_path))
    runner.start()

    assert runner.connected is True
    assert runner.process_alive is True
    assert runner.cleanup_pending is True

    runner.stop()

    connection = api.active_connection
    assert connection is not None
    assert connection.close_wait is False
    assert connection._socket is None
    assert api.connection._connections == {}

    assert runner._connection is None
    assert runner._process is None
    assert runner.connected is False
    assert runner.process_alive is False
    assert runner.process_id is None
    assert runner.cleanup_pending is False


def test_close_failure_forces_process_termination(
    monkeypatch,
    tmp_path,
):
    process = FakeProcess()
    api = FakeTraCI(
        process,
        close_error=RuntimeError("socket close failed"),
    )
    monkeypatch.setattr(runner_module, "traci", api)
    patch_runner_environment(monkeypatch, process)

    runner = SumoRunner(settings(tmp_path))
    runner.start()
    connection = api.active_connection

    runner.stop()

    assert connection is not None
    assert connection.close_wait is False
    assert connection._socket is None
    assert api.connection._connections == {}
    assert process.terminated is True
    assert runner._connection is None
    assert runner.connected is False
    assert runner.process_alive is False
    assert runner.cleanup_pending is False


def test_terminate_timeout_falls_back_to_kill(
    monkeypatch,
    tmp_path,
):
    process = FakeProcess(terminate_timeouts=1)
    api = FakeTraCI(process)
    monkeypatch.setattr(runner_module, "traci", api)
    patch_runner_environment(monkeypatch, process)

    runner = SumoRunner(settings(tmp_path))
    runner.start()
    runner.stop()

    assert process.terminate_calls == 1
    assert process.kill_calls == 1
    assert process.killed is True
    assert runner._process is None
    assert runner._connection is None
    assert runner.connected is False
    assert runner.process_alive is False
    assert runner.cleanup_pending is False
    assert api.connection._connections == {}


def test_stop_retries_process_cleanup_after_kill_failure(
    monkeypatch,
    tmp_path,
):
    process = FakeProcess(
        terminate_timeouts=1,
        kill_failures=1,
    )
    api = FakeTraCI(process)
    monkeypatch.setattr(runner_module, "traci", api)
    patch_runner_environment(monkeypatch, process)

    runner = SumoRunner(settings(tmp_path))
    runner.start()
    connection = api.active_connection

    with pytest.raises(RuntimeError, match="SUMO 子进程仍在运行"):
        runner.stop()

    assert process.terminate_calls == 1
    assert process.kill_calls == 1
    assert runner._connection is None
    assert runner._process is process
    assert connection._socket is None
    assert api.connection._connections == {}
    assert runner.connected is False
    assert runner.process_alive is True
    assert runner.cleanup_pending is True

    runner.stop()

    assert process.terminate_calls == 2
    assert process.kill_calls == 1
    assert runner._connection is None
    assert runner._process is None
    assert runner.connected is False
    assert runner.process_alive is False
    assert runner.cleanup_pending is False
    assert api.connection._connections == {}


def test_runner_reports_unexpected_process_exit(
    monkeypatch,
    tmp_path,
):
    process = FakeProcess()
    api = FakeTraCI(process)
    monkeypatch.setattr(runner_module, "traci", api)
    patch_runner_environment(monkeypatch, process)

    runner = SumoRunner(settings(tmp_path))
    runner.start()
    process.returncode = 17

    assert runner.connected is False
    assert runner.running is False
    assert runner.process_alive is False
    assert runner.cleanup_pending is True

    runner.stop()

    assert runner.cleanup_pending is False
    assert runner._connection is None
    assert runner._process is None


@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("RUN_SUMO_INTEGRATION") != "1",
    reason="设置 RUN_SUMO_INTEGRATION=1 后执行真实 SUMO 生命周期测试",
)
def test_real_sumo_start_step_stop(tmp_path):
    from app.core.config import get_settings

    runner = SumoRunner(get_settings())
    runner.start()
    pid = runner.process_id

    assert runner.connected is True
    assert runner.process_alive is True

    runner.step()
    runner.stop()

    assert runner.connected is False
    assert runner.process_alive is False
    assert runner.cleanup_pending is False
    assert pid is not None


def test_traci_handshake_failure_still_reaps_spawned_process(
    monkeypatch,
    tmp_path,
):
    process = FakeProcess()

    class FailedHandshake(FakeTraCI):
        def __init__(self, process):
            super().__init__(
                process,
                handshake_error=RuntimeError(
                    "TraCI handshake failed"
                ),
            )

    api = FailedHandshake(process)
    monkeypatch.setattr(runner_module, "traci", api)
    patch_runner_environment(monkeypatch, process)

    runner = SumoRunner(settings(tmp_path))

    with pytest.raises(RuntimeError, match="TraCI handshake failed"):
        runner.start()

    assert process.terminated is True
    assert runner._connection is None
    assert runner._process is None
    assert runner.connected is False
    assert runner.process_alive is False
    assert runner.cleanup_pending is False
    assert api.connection._connections == {}


def test_stop_retries_socket_cleanup_after_process_exit(
    monkeypatch,
    tmp_path,
):
    process = FakeProcess()
    api = FakeTraCI(process, socket_close_failures=1)
    monkeypatch.setattr(runner_module, "traci", api)
    patch_runner_environment(monkeypatch, process)

    runner = SumoRunner(settings(tmp_path))
    runner.start()
    connection = api.active_connection

    with pytest.raises(
        RuntimeError,
        match="TraCI 连接清理未完成",
    ):
        runner.stop()

    assert process.poll() is not None
    assert runner._process is None
    assert runner._connection is connection
    assert connection._socket is not None
    assert runner.connected is False
    assert runner.process_alive is False
    assert runner.cleanup_pending is True

    runner.stop()

    assert connection._socket is None
    assert runner._connection is None
    assert runner._process is None
    assert api.connection._connections == {}
    assert runner.connected is False
    assert runner.process_alive is False
    assert runner.cleanup_pending is False


def test_stop_retries_connection_pool_cleanup_after_process_exit(
    monkeypatch,
    tmp_path,
):
    process = FakeProcess()
    api = FakeTraCI(process)
    monkeypatch.setattr(runner_module, "traci", api)
    patch_runner_environment(monkeypatch, process)

    runner = SumoRunner(settings(tmp_path))
    runner.start()
    connection = api.active_connection

    api.connection._connections = FailOnceDict(
        api.connection._connections,
        fail_key="default",
    )

    with pytest.raises(
        RuntimeError,
        match="TraCI 连接清理未完成",
    ):
        runner.stop()

    assert process.poll() is not None
    assert runner._process is None
    assert runner._connection is connection
    assert connection._socket is None
    assert api.connection._connections.get("default") is connection
    assert runner.connected is False
    assert runner.process_alive is False
    assert runner.cleanup_pending is True

    runner.stop()

    assert runner._connection is None
    assert runner._process is None
    assert api.connection._connections == {}
    assert runner.connected is False
    assert runner.process_alive is False
    assert runner.cleanup_pending is False


def test_start_rejected_when_previous_connection_cleanup_is_pending(
    monkeypatch,
    tmp_path,
):
    process = FakeProcess()
    next_process = FakeProcess()
    processes = iter([process, next_process])

    api = FakeTraCI(process, socket_close_failures=1)

    monkeypatch.setattr(runner_module, "traci", api)
    monkeypatch.setattr(
        runner_module.os.path,
        "exists",
        lambda _path: True,
    )
    monkeypatch.setattr(
        runner_module.subprocess,
        "Popen",
        lambda _cmd: next(processes),
    )

    runner = SumoRunner(settings(tmp_path))
    runner.start()

    # 故障只注入第一次连接，后续重新启动不再注入故障。
    api.socket_close_failures = 0

    # 第一次 stop：Socket 清理失败，进程退出但连接引用保留。
    with pytest.raises(
        RuntimeError,
        match="TraCI 连接清理未完成",
    ):
        runner.stop()

    assert runner.cleanup_pending is True

    # 旧连接尚未清理时，禁止启动新仿真。
    with pytest.raises(RuntimeError, match="previous resources"):
        runner.start()

    # 清理旧连接后，允许重新启动。
    runner.stop()
    assert runner.cleanup_pending is False

    runner.start()

    assert runner.connected is True
    assert runner.process_alive is True
    assert runner.cleanup_pending is True
    assert runner.process_id == next_process.pid

    runner.stop()

    assert runner.cleanup_pending is False
    assert runner.connected is False
    assert runner.process_alive is False


def test_cleanup_does_not_remove_unrelated_traci_connections(
    monkeypatch,
    tmp_path,
):
    process = FakeProcess()
    api = FakeTraCI(process)
    monkeypatch.setattr(runner_module, "traci", api)
    patch_runner_environment(monkeypatch, process)

    runner = SumoRunner(settings(tmp_path))
    runner.start()

    unrelated_connection = object()
    api.connection._connections["unrelated"] = unrelated_connection

    runner.stop()

    assert api.connection._connections == {
        "unrelated": unrelated_connection,
    }
