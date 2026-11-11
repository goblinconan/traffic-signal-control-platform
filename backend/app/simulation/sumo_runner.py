"""SUMO 运行器：启动/停止/单步仿真，封装 TraCI 连接。
输入：Settings。
输出：仿真时间、车辆快照、信号灯受控连接映射。
依赖：traci、core/config.py。
调用方：services/signal_service.py。
"""
from __future__ import annotations

import logging
import os
import sys
import threading
import time
from dataclasses import dataclass, field

from app.core.config import Settings

log = logging.getLogger(__name__)

if "SUMO_HOME" in os.environ:
    sys.path.append(os.path.join(os.environ["SUMO_HOME"], "tools"))

import traci  # type: ignore  # noqa: E402


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
    _cx: float = 200.0  # 路网中心 X
    _cy: float = 200.0  # 路网中心 Y

    def start(self) -> None:
        with self._lock:
            if self._running:
                raise RuntimeError("simulation already running")
            sumo_home = self.settings.sumo_home or os.environ["SUMO_HOME"]
            sumo_binary = os.path.join(sumo_home, "bin", "sumo.exe")
            if not os.path.exists(sumo_binary):
                sumo_binary = "sumo"
                
            cmd = [
                sumo_binary,
                "-c", self.settings.sumo_config,
                "--step-length", str(self.settings.sim_step_length),
                "--no-step-log", "true",
                "--no-warnings", "true",
                "--duration-log.disable", "true",
            ]
            traci.start(cmd)
            self._running = True
            self._connected = True
            self._paused = False
            self._step_index = 0
            
            # 读取真实路口的中心坐标（解决坐标偏移）
            self._cx, self._cy = traci.junction.getPosition(self.settings.tls_id)
            log.info("SUMO started: %s", " ".join(cmd))

    def stop(self) -> None:
        self._running = False
        self._connected = False
        try:
            traci.close(False)
        except Exception as e:
            log.warning("traci.close failed: %s", e)

    def pause(self) -> None:
        self._paused = True

    def resume(self) -> None:
        self._paused = False

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def running(self) -> bool:
        return self._running

    def simulation_time(self) -> float:
        if not self._connected:
            return 0.0
        return float(traci.simulation.getTime())

    def step(self) -> float:
        with self._lock:
            if not self._running or not self._connected:
                return 0.0
            if self._paused:
                return self.simulation_time()
            traci.simulationStep()
            self._step_index += 1
            if self.settings.simulation_step_delay > 0:
                time.sleep(self.settings.simulation_step_delay)
            return self.simulation_time()

    def vehicles(self) -> list[VehicleSnapshot]:
        if not self._connected:
            return []
        result: list[VehicleSnapshot] = []
        for vid in traci.vehicle.getIDList():
            x, y = traci.vehicle.getPosition(vid)
            result.append(VehicleSnapshot(
                id=vid,
                x=float(x),
                y=float(y),
                angle=float(traci.vehicle.getAngle(vid)),
                speed=float(traci.vehicle.getSpeed(vid)),
                length=float(traci.vehicle.getLength(vid)),
                width=float(traci.vehicle.getWidth(vid)),
            ))
        return result

    def controlled_links(self, tls_id: str) -> list[tuple[str, str, str]]:
        raw = traci.trafficlight.getControlledLinks(tls_id)
        links: list[tuple[str, str, str]] = []
        for item in raw:
            if not item:
                continue
            from_lane, to_lane, _via = item[0]
            # 用 from_lane 判断方向（北和南是 NS，东和西是 EW）
            links.append((from_lane, to_lane, "NS" if _lane_is_ns(from_lane) else "EW"))
        return links

    def set_tls_state(self, tls_id: str, state: str) -> None:
        if not self._connected:
            return
        traci.trafficlight.setRedYellowGreenState(tls_id, state)
        log.debug("set tls %s state=%s", tls_id, state)


def _lane_is_ns(lane_id: str) -> bool:
    """判断车道方向：北和南为 NS，东和西为 EW。"""
    return lane_id.startswith(("north", "south"))