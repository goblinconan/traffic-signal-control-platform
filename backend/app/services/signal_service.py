
"""信号服务：协调八阶段状态机、SUMO 受控连接和配时生效。
输入：Settings、SUMO Runner、配时配置和仿真时间。
输出：SUMO 信号字符串及 SignalSnapshot。
依赖：SignalController、TimingService、SumoRunner。
调用方：API routes、WebSocket 和后台仿真循环。
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
    _links: list[list[tuple[str, str, str]]] = field(default_factory=list)
    _state_string: str = ""

    @classmethod
    def create(cls, settings: Settings, runner: SumoRunner) -> "SignalService":
        timing = TimingService(
            TimingConfig(
                ns_straight_green=settings.ns_straight_green,
                ns_left_green=settings.ns_left_green,
                ew_straight_green=settings.ew_straight_green,
                ew_left_green=settings.ew_left_green,
                yellow=settings.yellow,
            )
        )
        controller = SignalController(timing.active)
        return cls(settings, runner, timing, controller)

    def on_started(self) -> None:
        self._links = self.runner.controlled_links(self.settings.tls_id)
        if not self._links:
            raise RuntimeError("SUMO 未返回任何 traffic-light controlled link")
        log.info(
            "controlled link groups: %d; connections: %d",
            len(self._links),
            sum(len(group) for group in self._links),
        )
        self._state_string = ""
        self._sync_sumo()

    @staticmethod
    def _movement_for_link(
        from_lane: str, to_lane: str, via_lane: str
    ) -> tuple[str, str]:
        """依据实际进口车道 ID 判断轴向和车道功能；未知映射拒绝启动。"""
        lane_parts = from_lane.rsplit("_", 1)
        if len(lane_parts) != 2 or not lane_parts[1].isdigit():
            raise ValueError(f"无法解析 SUMO fromLane: {from_lane}")

        edge_id, lane_index_text = lane_parts
        lane_index = int(lane_index_text)
        if edge_id.startswith(("north", "south")):
            axis = "NS"
        elif edge_id.startswith(("east", "west")):
            axis = "EW"
        else:
            raise ValueError(f"无法识别进口方向: {from_lane}")

        lane_movement = {
            0: "right",
            1: "straight",
            2: "straight",
            3: "left",
            4: "left",
        }.get(lane_index)
        if lane_movement is None:
            raise ValueError(
                f"未配置车道功能: fromLane={from_lane}, toLane={to_lane}, via={via_lane}"
            )
        return axis, lane_movement

    def _state_for_movement(self, axis: str, movement: str) -> str:
        phase = self.controller.phase_id
        if movement == "right":
            # 当前 SUMO 冲突矩阵中右转连接无冲突，使用让行绿灯。
            # 小写 g 不代表受保护通行，后续仍需验证车辆轨迹和让行行为。
            return "g"

        phase_mapping = {
            PhaseId.NS_LEFT: ("NS", "left", "G"),
            PhaseId.NS_LEFT_YELLOW: ("NS", "left", "y"),
            PhaseId.NS_STRAIGHT: ("NS", "straight", "G"),
            PhaseId.NS_STRAIGHT_YELLOW: ("NS", "straight", "y"),
            PhaseId.EW_LEFT: ("EW", "left", "G"),
            PhaseId.EW_LEFT_YELLOW: ("EW", "left", "y"),
            PhaseId.EW_STRAIGHT: ("EW", "straight", "G"),
            PhaseId.EW_STRAIGHT_YELLOW: ("EW", "straight", "y"),
        }
        active_axis, active_movement, state = phase_mapping[phase]
        return state if (axis, movement) == (active_axis, active_movement) else "r"

    def _build_state_string(self) -> str:
        if not self._links:
            raise RuntimeError("SUMO controlled links 尚未初始化")

        chars: list[str] = []
        for link_index, group in enumerate(self._links):
            if not group:
                chars.append("r")
                continue

            movement_states: set[str] = set()
            for from_lane, to_lane, via_lane in group:
                axis, movement = self._movement_for_link(
                    from_lane, to_lane, via_lane
                )
                movement_states.add(self._state_for_movement(axis, movement))

            # 一个 linkIndex 若包含不同灯色需求，不能任意选择其中一个。
            if len(movement_states) != 1:
                raise RuntimeError(
                    f"SUMO linkIndex={link_index} 包含冲突灯色需求: "
                    f"{sorted(movement_states)}"
                )
            chars.append(movement_states.pop())

        state = "".join(chars)
        if len(state) != len(self._links):
            raise RuntimeError(
                f"SUMO 信号字符串长度错误: {len(state)} != {len(self._links)}"
            )
        return state

    def _sync_sumo(self) -> None:
        new_state = self._build_state_string()
        if new_state != self._state_string:
            self.runner.set_tls_state(self.settings.tls_id, new_state)
            self._state_string = new_state
            log.info("SUMO TLS state updated: phase=%s state=%s",
                     self.controller.phase_id.value, new_state)

    def step(self) -> SignalSnapshot:
        sim_time = self.runner.step()
        previous_phase = self.controller.phase_id
        switched = self.controller.advance_if_needed(sim_time)

        # 只有完整八阶段周期结束、重新进入 NS_LEFT 绿灯时才提升待生效配时。
        if switched and previous_phase == PhaseId.EW_STRAIGHT_YELLOW \
                and self.controller.phase_id == PhaseId.NS_LEFT:
            promoted = self.timing.promote_pending_if_any()
            if promoted is not None:
                self.controller.apply_timing(promoted)
                log.info("timing promoted at cycle boundary: %s", promoted)

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
