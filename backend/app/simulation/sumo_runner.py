
"""SUMO 运行器：集中管理 TraCI 连接、子进程和所有连接访问。
输入：Settings、SUMO 配置及控制指令。
输出：仿真时间、车辆快照、受控连接及可核验的进程状态。
依赖：traci、core/config.py、threading、subprocess。
调用方：SignalService、SimulationLifecycle。
"""
from __future__ import annotations

import importlib
import logging
import os
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from app.core.config import Settings

log = logging.getLogger(__name__)

if "SUMO_HOME" in os.environ:
    tools_path = os.path.join(os.environ["SUMO_HOME"], "tools")
    if tools_path not in sys.path:
        sys.path.append(tools_path)

try:
    import traci  # type: ignore  # noqa: E402
except ImportError:  # 允许不安装 SUMO 的环境运行纯单元测试
    traci = None  # type: ignore[assignment]


@dataclass
class VehicleSnapshot:
    id: str
    x: float
    y: float
    angle: float
    speed: float
    length: float
    width: float


@dataclass
class SumoRunner:
    settings: Settings
    _lock: threading.RLock = field(default_factory=threading.RLock)
    _running: bool = False
    _connected: bool = False
    _paused: bool = False
    _step_index: int = 0
    _cx: float = 200.0
    _cy: float = 200.0
    _connection: Any | None = field(default=None, init=False, repr=False)
    _process: Any | None = field(default=None, init=False, repr=False)
    _connection_close_attempted: bool = field(
        default=False,
        init=False,
        repr=False,
    )

    def _require_traci(self) -> Any:
        global traci

        if traci is None:
            sumo_home = self.settings.sumo_home or os.environ.get("SUMO_HOME")

            if sumo_home:
                tools_path = os.path.join(sumo_home, "tools")
                if tools_path not in sys.path:
                    sys.path.insert(0, tools_path)

            try:
                traci = importlib.import_module("traci")
            except ImportError as exc:
                raise RuntimeError(
                    "未找到 TraCI。请检查 Settings.sumo_home / SUMO_HOME，"
                    "并确认对应 SUMO tools 目录中存在 traci 包。"
                ) from exc

        return traci

    def _process_alive_locked(self) -> bool:
        if self._process is None:
            return self._connected

        return self._process.poll() is None

    def _refresh_process_state_locked(self) -> None:
        if self._process is not None and self._process.poll() is not None:
            self._connected = False
            self._running = False
            self._paused = False

    def _terminate_process_locked(self) -> None:
        """尽可能回收当前 Runner 创建的 SUMO 子进程。"""
        process = self._process

        if process is None or process.poll() is not None:
            return

        try:
            process.terminate()
            process.wait(timeout=5)
            return
        except Exception as terminate_error:
            # terminate 或 wait 失败时，只要进程仍存活，就升级为 kill。
            if process.poll() is None:
                log.warning(
                    "SUMO terminate/wait failed; trying kill: %s",
                    terminate_error,
                )

                try:
                    process.kill()
                    process.wait(timeout=5)
                except Exception as kill_error:
                    raise RuntimeError(
                        "SUMO 进程 terminate 和 kill 均未能完成"
                    ) from kill_error

    def _close_locked(self) -> None:
        """清理当前 Runner 持有的 TraCI 连接和 SUMO 进程。

        连接清理失败时保留连接引用，允许后续 stop() 重试。
        不删除不属于当前 Runner 的 TraCI 全局连接。
        """
        connection = self._connection
        close_error: Exception | None = None
        connection_clean = connection is None

        if connection is not None:
            api = None

            # 获取 TraCI 模块失败时，仍继续尝试关闭 Socket 和 SUMO 进程。
            try:
                api = self._require_traci()
            except Exception as exc:
                close_error = exc
                log.exception("Unable to load TraCI during connection cleanup")

            # 1. TraCI close 只尝试一次，避免重复执行不安全的关闭流程。
            if not self._connection_close_attempted:
                self._connection_close_attempted = True

                try:
                    connection.close(wait=False)
                except Exception as exc:
                    if close_error is None:
                        close_error = exc

                    log.exception(
                        "TraCI graceful close failed; "
                        "trying socket and connection-pool cleanup"
                    )

            # 2. 独立关闭 Socket，失败时保留引用供下一次 stop() 重试。
            try:
                connection_socket = getattr(connection, "_socket", None)

                if connection_socket is not None:
                    connection_socket.close()
                    connection._socket = None

            except Exception as exc:
                if close_error is None:
                    close_error = exc

                log.exception("TraCI socket cleanup failed")

            # 3. 只注销当前 Runner 所拥有的连接。
            pool_clean = False

            if api is not None:
                try:
                    pool = api.connection._connections

                    if pool.get("") is connection:
                        del pool[""]

                    if pool.get("default") is connection:
                        del pool["default"]

                    pool_clean = (
                        pool.get("") is not connection
                        and pool.get("default") is not connection
                    )

                except Exception as exc:
                    if close_error is None:
                        close_error = exc

                    log.exception("TraCI connection-pool cleanup failed")

            socket_clean = getattr(connection, "_socket", None) is None
            connection_clean = socket_clean and pool_clean

            # 只有 Socket 和连接池都清理成功，才能释放连接引用。
            if connection_clean:
                self._connection = None
                self._connection_close_attempted = False

        # 4. 无论 TraCI 清理是否成功，都尝试回收 SUMO 进程。
        try:
            self._terminate_process_locked()
        except Exception as exc:
            if close_error is None:
                close_error = exc
            else:
                log.exception("SUMO process termination also failed")

        # 5. 核验 SUMO 进程是否真正退出。
        process = self._process
        process_alive = process is not None and process.poll() is None

        self._connected = False
        self._running = False
        self._paused = False

        if process_alive:
            raise RuntimeError(
                "SUMO 子进程仍在运行，清理未完成"
            ) from close_error

        # 进程已退出，可以释放进程引用。
        self._process = None

        # 6. TraCI 连接未清理干净时，不能报告停止成功。
        if not connection_clean:
            raise RuntimeError(
                "SUMO 子进程已退出，但 TraCI 连接清理未完成；"
                "请重试停止操作"
            ) from close_error

        if close_error is not None:
            log.warning(
                "TraCI close reported an error, but socket, connection pool "
                "and SUMO process cleanup completed: %s",
                close_error,
            )

    def start(self) -> None:
        with self._lock:
            self._refresh_process_state_locked()

            # 即使进程已经退出，只要旧资源尚未完全清理，就禁止重新启动。
            if (
                self._running
                or self._connected
                or self._process_alive_locked()
                or self._connection is not None
                or self._process is not None
            ):
                raise RuntimeError(
                    "SUMO simulation is running or previous resources "
                    "are still awaiting cleanup; call stop() first"
                )

            api = self._require_traci()
            sumo_home = self.settings.sumo_home or os.environ.get("SUMO_HOME")

            if not sumo_home:
                raise RuntimeError("SUMO_HOME 未配置")

            sumo_binary = os.path.join(sumo_home, "bin", "sumo.exe")

            if not os.path.exists(sumo_binary):
                sumo_binary = "sumo"

            log.info(
                "SUMO startup config diagnostic: settings_id=%s config=%r exists=%s",
                id(self.settings),
                self.settings.sumo_config,
                os.path.isfile(self.settings.sumo_config),
            )

            cmd = [
                sumo_binary,
                "-c",
                self.settings.sumo_config,
                "--step-length",
                str(self.settings.sim_step_length),
                "--no-step-log",
                "true",
                "--duration-log.disable",
                "true",
            ]

            try:
                # 先申请临时端口，再由 TraCI 建立连接。
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as port_socket:
                    port_socket.bind(("127.0.0.1", 0))
                    port = int(port_socket.getsockname()[1])

                self._process = subprocess.Popen(
                    cmd + ["--remote-port", str(port)]
                )

                # 先保存连接对象，再执行握手。
                # 即使 getVersion() 失败，也可以清理本次创建的连接。
                self._connection = api.connect(
                    port,
                    host="127.0.0.1",
                    label="default",
                    proc=self._process,
                )
                self._connection_close_attempted = False

                api.switch("default")
                self._connection.getVersion()

                self._connected = True
                self._running = True
                self._paused = False
                self._step_index = 0

                self._cx, self._cy = api.junction.getPosition(
                    self.settings.tls_id
                )

                log.info(
                    "SUMO started: pid=%s command=%s",
                    self._process.pid,
                    " ".join(cmd),
                )

            except Exception:
                try:
                    self._close_locked()
                except Exception:
                    log.exception(
                        "SUMO cleanup after startup failure failed"
                    )

                raise

    def stop(self) -> None:
        with self._lock:
            self._refresh_process_state_locked()

            if (
                self._connection is None
                and not self._connected
                and self._process is None
            ):
                self._running = False
                self._paused = False
                self._connection_close_attempted = False
                return

            self._close_locked()

    @property
    def process_id(self) -> int | None:
        with self._lock:
            return getattr(self._process, "pid", None)

    @property
    def process_alive(self) -> bool:
        with self._lock:
            self._refresh_process_state_locked()
            return self._process_alive_locked()

    @property
    def cleanup_pending(self) -> bool:
        """是否仍持有需要清理的 TraCI 连接或 SUMO 进程引用。"""
        with self._lock:
            return (
                self._connection is not None
                or self._process is not None
            )

    @property
    def connected(self) -> bool:
        with self._lock:
            self._refresh_process_state_locked()
            return self._connected

    @property
    def running(self) -> bool:
        with self._lock:
            self._refresh_process_state_locked()
            return self._running

    @property
    def step_index(self) -> int:
        with self._lock:
            return self._step_index

    def pause(self) -> None:
        with self._lock:
            self._paused = True

    def resume(self) -> None:
        with self._lock:
            self._paused = False

    def simulation_time(self) -> float:
        with self._lock:
            self._refresh_process_state_locked()

            if not self._connected:
                return 0.0

            return float(self._require_traci().simulation.getTime())

    def step(self) -> float:
        with self._lock:
            self._refresh_process_state_locked()

            if not self._running:
                return 0.0

            if not self._connected:
                raise RuntimeError(
                    "SUMO 子进程已退出，无法继续推进仿真"
                )

            api = self._require_traci()

            if self._paused:
                return float(api.simulation.getTime())

            api.simulationStep()
            self._step_index += 1

            if self.settings.simulation_step_delay > 0:
                time.sleep(self.settings.simulation_step_delay)

            return float(api.simulation.getTime())

    def vehicles(self) -> list[VehicleSnapshot]:
        with self._lock:
            if not self._connected:
                return []

            api = self._require_traci()
            result: list[VehicleSnapshot] = []

            for vehicle_id in api.vehicle.getIDList():
                x, y = api.vehicle.getPosition(vehicle_id)

                result.append(
                    VehicleSnapshot(
                        id=vehicle_id,
                        x=float(x),
                        y=float(y),
                        angle=float(api.vehicle.getAngle(vehicle_id)),
                        speed=float(api.vehicle.getSpeed(vehicle_id)),
                        length=float(api.vehicle.getLength(vehicle_id)),
                        width=float(api.vehicle.getWidth(vehicle_id)),
                    )
                )

            return result

    def controlled_links(
        self,
        tls_id: str,
    ) -> list[list[tuple[str, str, str]]]:
        """返回每个 SUMO linkIndex 对应的全部连接，不丢弃同组连接。"""
        with self._lock:
            raw = self._require_traci().trafficlight.getControlledLinks(
                tls_id
            )

            return [
                [
                    (str(from_lane), str(to_lane), str(via_lane))
                    for from_lane, to_lane, via_lane in group
                ]
                for group in raw
            ]

    def set_tls_state(self, tls_id: str, state: str) -> None:
        with self._lock:
            if not self._connected:
                raise RuntimeError(
                    "SUMO 未连接，拒绝设置 traffic-light state"
                )

            api = self._require_traci()
            expected_length = len(
                api.trafficlight.getControlledLinks(tls_id)
            )

            if len(state) != expected_length:
                raise ValueError(
                    f"traffic-light state 长度 {len(state)} "
                    f"与 controlled link 数 {expected_length} 不一致"
                )

            api.trafficlight.setRedYellowGreenState(tls_id, state)
            log.debug("set tls %s state=%s", tls_id, state)

    def get_tls_state(self, tls_id: str) -> str:
        """读取 SUMO 当前实际 TLS 状态，供运行诊断和集成验收使用。"""
        with self._lock:
            if not self._connected:
                raise RuntimeError("SUMO 未连接，无法读取 traffic-light state")
            return str(
                self._require_traci().trafficlight.getRedYellowGreenState(tls_id)
            )
