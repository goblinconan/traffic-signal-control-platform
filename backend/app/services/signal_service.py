"""信号服务：协调状态机、SUMO 和配置，是业务层唯一入口。
输入：Settings、TimingConfig、仿真时间。
输出：SignalSnapshot、SUMO 状态字符串。
依赖：SignalController、TimingService、SumoRunner。
调用方：api/routes/signal.py、api/websocket.py、main.py 后台任务。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.controllers.signal_controller import SignalController
from app.core.config import Settings
from app.models.signal import PhaseId, SignalSnapshot, TimingConfig
from app.services.timing_service import TimingService
from app.simulation.sumo_runner import SumoRunner

log = logging.getLogger(__name__)


@dataclass
class SignalService:
    settings: Settings
    runner: SumoRunner
    timing: TimingService
    controller: SignalController
    _links: list[tuple[str, str, str]] = field(default_factory=list)
    _state_string: str = ""

    @classmethod
    def create(cls, settings: Settings, runner: SumoRunner) -> "SignalService":
        timing = TimingService(TimingConfig(
            ns_straight_green=settings.ns_straight_green,
            ns_left_green=settings.ns_left_green,
            ew_straight_green=settings.ew_straight_green,
            ew_left_green=settings.ew_left_green,
            yellow=3.0
        ))
        controller = SignalController(timing.active)
        return cls(settings=settings, runner=runner, timing=timing, controller=controller)

    def on_started(self) -> None:
        self._links = self.runner.controlled_links(self.settings.tls_id)
        log.info("controlled links: %s", self._links)
        self._sync_sumo()

    def _build_state_string(self) -> str:
        """
        根据当前相位，动态生成 SUMO 需要的 20 位信号字符串。
        规则：每个方向 5 条道，车道索引 0(右转), 1(直行), 2(直行), 3(左转), 4(左转)。
        """
        phase = self.controller.phase_id
        chars: list[str] = []

        for from_lane, to_lane, direction in self._links:
            # 从 from_lane (如 "north_in_0") 中提取车道索引
            try:
                lane_idx = int(from_lane.split("_")[-1])
            except ValueError:
                lane_idx = 0

            # 0 号车道是右转，常绿
            if lane_idx == 0:
                chars.append("G")
                continue

            # 判断车道功能
            is_straight = lane_idx in (1, 2)
            is_left = lane_idx in (3, 4)

            # 根据当前相位分配颜色
            if phase == PhaseId.NS_STRAIGHT:
                chars.append("G" if direction == "NS" and is_straight else "r")
            elif phase == PhaseId.NS_STRAIGHT_YELLOW:
                chars.append("y" if direction == "NS" and is_straight else "r")
            elif phase == PhaseId.NS_LEFT:
                chars.append("G" if direction == "NS" and is_left else "r")
            elif phase == PhaseId.NS_LEFT_YELLOW:
                chars.append("y" if direction == "NS" and is_left else "r")
            elif phase == PhaseId.EW_STRAIGHT:
                chars.append("G" if direction == "EW" and is_straight else "r")
            elif phase == PhaseId.EW_STRAIGHT_YELLOW:
                chars.append("y" if direction == "EW" and is_straight else "r")
            elif phase == PhaseId.EW_LEFT:
                chars.append("G" if direction == "EW" and is_left else "r")
            elif phase == PhaseId.EW_LEFT_YELLOW:
                chars.append("y" if direction == "EW" and is_left else "r")
            else:
                chars.append("r")

        return "".join(chars)

    def _sync_sumo(self) -> None:
        new_state = self._build_state_string()
        if new_state != self._state_string:
            self._state_string = new_state
            self.runner.set_tls_state(self.settings.tls_id, new_state)

    def step(self) -> SignalSnapshot:
        sim_time = self.runner.step()
        switched = self.controller.advance_if_needed(sim_time)
        if switched:
            promoted = self.timing.promote_pending_if_any()
            if promoted:
                self.controller.apply_timing(promoted)
                log.info("new timing promoted: %s", promoted)
        self._sync_sumo()
        return self.snapshot(sim_time)

    def snapshot(self, sim_time: float | None = None) -> SignalSnapshot:
        if sim_time is None:
            sim_time = self.runner.simulation_time()
            
        ns_s, ns_l, ew_s, ew_l = self.controller.get_direction_states(sim_time)
        
        return SignalSnapshot(
            tls_id=self.settings.tls_id,
            phase_id=self.controller.phase_id,
            ns_straight=ns_s,
            ns_left=ns_l,
            ew_straight=ew_s,
            ew_left=ew_l,
            timing=self.timing.active,
        )

    def submit_timing(self, candidate: TimingConfig) -> TimingConfig:
        return self.timing.submit(candidate)

    def manual_switch(self, target: PhaseId) -> tuple[bool, str]:
        sim_time = self.runner.simulation_time()
        ok, reason = self.controller.manual_switch(target, sim_time)
        if ok:
            self._sync_sumo()
        return ok, reason