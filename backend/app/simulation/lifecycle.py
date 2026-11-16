
"""仿真生命周期协调器：串行化启动、停止、步进及应用关闭。

输入：SumoRunner、SignalService。
输出：生命周期状态快照及可诊断的失败原因。
依赖：asyncio、simulation/sumo_runner.py、services/signal_service.py。
调用方：simulation API、main.py 应用后台循环。
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Coroutine

log = logging.getLogger(__name__)


class SimulationStatus(str, Enum):
    STOPPED = "STOPPED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    STOPPING = "STOPPING"
    FAILED = "FAILED"


class LifecycleError(RuntimeError):
    def __init__(self, message: str, status_code: int = 409) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class LifecycleSnapshot:
    status: SimulationStatus
    simulation_time: float
    sumo_connected: bool
    last_error: str | None
    step_index: int = 0
    process_alive: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value.lower(),
            "lifecycle_status": self.status.value,
            "simulation_time": self.simulation_time,
            "sumo_connected": self.sumo_connected,
            "step_index": self.step_index,
            "process_alive": self.process_alive,
            "last_error": self.last_error,
        }


async def _wait_task_safely(task: asyncio.Task[Any]) -> Any:
    """等待任务真正结束；重复收到取消也不提前放弃底层任务。

    如果调用方被取消，会先等待目标任务完成，再传播取消。
    """
    cancellation_received = False

    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            cancellation_received = True

    if cancellation_received:
        raise asyncio.CancelledError

    return task.result()


async def _run_blocking_safely(function: Callable[[], Any]) -> Any:
    """在线程中执行同步操作，取消时等待线程真正结束。"""
    task = asyncio.create_task(asyncio.to_thread(function))
    return await _wait_task_safely(task)


class SimulationLifecycle:
    """统一协调 SUMO 进程生命周期和 TraCI 步进。"""

    def __init__(self, runner: Any, signal_service: Any) -> None:
        self._runner = runner
        self._signal_service = signal_service
        self._operation_lock = asyncio.Lock()
        self._status = SimulationStatus.STOPPED
        self._last_error: str | None = None
        self._closing = False

    @property
    def status(self) -> SimulationStatus:
        return self._status

    def _runner_connected(self) -> bool:
        return bool(self._runner.connected)

    def _runner_process_alive(self) -> bool:
        return bool(
            getattr(
                self._runner,
                "process_alive",
                self._runner_connected(),
            )
        )

    def _runner_cleanup_pending(self) -> bool:
        return bool(getattr(self._runner, "cleanup_pending", False))

    def _runner_has_resources(self) -> bool:
        return (
            self._runner_connected()
            or self._runner_process_alive()
            or self._runner_cleanup_pending()
        )

    def snapshot(self) -> LifecycleSnapshot:
        try:
            simulation_time = float(self._runner.simulation_time())
        except Exception:
            simulation_time = 0.0

        try:
            connected = self._runner_connected()
        except Exception:
            connected = False

        try:
            process_alive = self._runner_process_alive()
        except Exception:
            process_alive = False

        try:
            step_index = int(getattr(self._runner, "step_index", 0))
        except Exception:
            step_index = 0

        return LifecycleSnapshot(
            status=self._status,
            simulation_time=simulation_time,
            sumo_connected=connected,
            last_error=self._last_error,
            step_index=step_index,
            process_alive=process_alive,
        )

    async def refresh_health(self) -> LifecycleSnapshot:
        async with self._operation_lock:
            if self._status == SimulationStatus.RUNNING:
                try:
                    if not self._runner_connected():
                        raise RuntimeError(
                            "SUMO 进程已退出或 TraCI 连接已断开"
                        )

                    # 真实发起一次 TraCI 查询，识别连接失效。
                    self._runner.simulation_time()

                except Exception as exc:
                    self._status = SimulationStatus.FAILED
                    self._last_error = (
                        f"{type(exc).__name__}: {exc}"
                    )

                    cleanup_error = await self._cleanup_runner()

                    if cleanup_error:
                        self._last_error += (
                            f"；清理失败：{cleanup_error}"
                        )

            return self.snapshot()

    async def start(self) -> LifecycleSnapshot:
        async with self._operation_lock:
            if self._closing:
                raise LifecycleError(
                    "应用正在关闭，拒绝启动仿真",
                    503,
                )

            if self._status in (
                SimulationStatus.STARTING,
                SimulationStatus.RUNNING,
                SimulationStatus.STOPPING,
            ):
                raise LifecycleError(
                    "仿真已经启动、正在启动或正在停止",
                    409,
                )

            if self._status == SimulationStatus.FAILED:
                raise LifecycleError(
                    "仿真处于 FAILED 状态，请先调用 stop 完成清理",
                    409,
                )

            # STOPPED 但仍持有资源时，也禁止直接启动。
            if self._runner_has_resources():
                raise LifecycleError(
                    "SUMO Runner 仍有资源等待清理，请先调用 stop",
                    409,
                )

            self._status = SimulationStatus.STARTING
            self._last_error = None

            try:
                await _run_blocking_safely(self._runner.start)
                await _run_blocking_safely(
                    self._signal_service.on_started
                )

                if not self._runner_connected():
                    raise RuntimeError(
                        "SUMO 启动后连接立即断开"
                    )

                self._status = SimulationStatus.RUNNING
                log.info("simulation lifecycle entered RUNNING")
                return self.snapshot()

            except asyncio.CancelledError:
                log.warning(
                    "simulation start was cancelled; cleaning up SUMO"
                )

                cleanup_error = await self._cleanup_runner()

                if cleanup_error:
                    self._status = SimulationStatus.FAILED
                    self._last_error = (
                        "启动请求被取消；清理失败："
                        + cleanup_error
                    )
                else:
                    self._status = SimulationStatus.STOPPED
                    self._last_error = (
                        "启动请求被取消，SUMO 已完成清理"
                    )

                raise

            except Exception as exc:
                log.exception("simulation start failed")

                cleanup_error = await self._cleanup_runner()

                self._status = SimulationStatus.FAILED
                self._last_error = (
                    f"{type(exc).__name__}: {exc}"
                )

                if cleanup_error:
                    self._last_error += (
                        f"；清理失败：{cleanup_error}"
                    )

                raise LifecycleError(
                    f"SUMO 启动失败：{exc}",
                    503,
                ) from exc

    async def stop(self) -> LifecycleSnapshot:
        async with self._operation_lock:
            if (
                self._status == SimulationStatus.STOPPED
                and not self._runner_has_resources()
            ):
                return self.snapshot()

            self._status = SimulationStatus.STOPPING

            try:
                await _run_blocking_safely(self._runner.stop)

                if self._runner_has_resources():
                    raise RuntimeError(
                        "Runner.stop 返回后仍检测到 SUMO 资源"
                    )

            except asyncio.CancelledError:
                log.warning(
                    "simulation stop was cancelled; checking cleanup"
                )

                try:
                    resources_remain = self._runner_has_resources()
                except Exception:
                    resources_remain = True

                if resources_remain:
                    self._status = SimulationStatus.FAILED
                    self._last_error = (
                        "停止请求被取消，SUMO 仍有资源未清理"
                    )
                else:
                    self._status = SimulationStatus.STOPPED
                    self._last_error = None

                raise

            except Exception as exc:
                log.exception("simulation stop failed")

                self._status = SimulationStatus.FAILED
                self._last_error = (
                    f"{type(exc).__name__}: {exc}"
                )

                raise LifecycleError(
                    f"仿真停止失败：{exc}",
                    503,
                ) from exc

            self._status = SimulationStatus.STOPPED
            self._last_error = None

            log.info("simulation lifecycle entered STOPPED")
            return self.snapshot()

    async def run_control_action(self, function: Callable[[], Any]) -> Any:
        """在生命周期锁内执行信号控制操作，避免与 TraCI 步进并发。"""
        async with self._operation_lock:
            if self._closing:
                raise LifecycleError("应用正在关闭，拒绝信号控制操作", 503)
            if self._status != SimulationStatus.RUNNING:
                raise LifecycleError("只有仿真 RUNNING 时才能操作信号控制", 409)
            try:
                return await _run_blocking_safely(function)
            except LifecycleError:
                raise
            except Exception as exc:
                raise LifecycleError(f"信号控制操作失败：{exc}", 409) from exc

    async def step_once(self) -> None:
        async with self._operation_lock:
            if (
                self._closing
                or self._status != SimulationStatus.RUNNING
            ):
                return

            try:
                await _run_blocking_safely(
                    self._signal_service.step
                )

                if not self._runner_connected():
                    raise RuntimeError(
                        "SUMO 进程在仿真步进期间退出"
                    )

            except asyncio.CancelledError:
                log.warning(
                    "simulation step was cancelled; cleaning up SUMO"
                )

                cleanup_error = await self._cleanup_runner()

                self._status = (
                    SimulationStatus.FAILED
                    if cleanup_error
                    else SimulationStatus.STOPPED
                )

                self._last_error = (
                    "仿真步进任务被取消"
                    + (
                        f"；清理失败：{cleanup_error}"
                        if cleanup_error
                        else ""
                    )
                )

                raise

            except Exception as exc:
                log.exception(
                    "simulation step failed; marking lifecycle FAILED"
                )

                self._status = SimulationStatus.FAILED
                self._last_error = (
                    f"{type(exc).__name__}: {exc}"
                )

                cleanup_error = await self._cleanup_runner()

                if cleanup_error:
                    self._last_error += (
                        f"；清理失败：{cleanup_error}"
                    )

    async def _cleanup_runner(self) -> str | None:
        try:
            await _run_blocking_safely(self._runner.stop)

            if self._runner_connected():
                return "Runner.stop 后仍检测到 TraCI 连接"

            if self._runner_process_alive():
                return "Runner.stop 后 SUMO 进程仍在运行"

            if self._runner_cleanup_pending():
                return "SUMO Runner 仍有资源等待清理"

            return None

        except asyncio.CancelledError:
            # 取消时不能把尚未确认完成的清理报告为成功。
            log.warning("SUMO cleanup task was cancelled")
            raise

        except Exception as exc:
            log.exception("SUMO cleanup failed")
            return f"{type(exc).__name__}: {exc}"

    async def shutdown(self) -> None:
        """禁止新操作，等待已有操作结束，再确保 SUMO 清理完成。"""
        self._closing = True

        shutdown_task = asyncio.create_task(self.stop())

        # 应用关闭任务即使收到取消，也先等待 stop 完成。
        await _wait_task_safely(shutdown_task)
