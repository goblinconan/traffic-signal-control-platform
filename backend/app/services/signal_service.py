
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
from app.models.signal import (
    ControlMode, ControlStatus, PhaseId, SignalSnapshot, TimingConfig,
)
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
    control_mode: ControlMode = ControlMode.AUTO
    control_status: ControlStatus = ControlStatus.ENABLED
    _pending_mode: ControlMode | None = None
    _pending_manual_phase: PhaseId | None = None

    @staticmethod
    def configured_timing(settings: Settings) -> TimingConfig:
        return TimingConfig(
            ns_left_green=settings.ns_left_green,
            ns_left_yellow=settings.ns_left_yellow,
            ns_straight_green=settings.ns_straight_green,
            ns_straight_yellow=settings.ns_straight_yellow,
            ew_left_green=settings.ew_left_green,
            ew_left_yellow=settings.ew_left_yellow,
            ew_straight_green=settings.ew_straight_green,
            ew_straight_yellow=settings.ew_straight_yellow,
        )

    @classmethod
    def create(
        cls, settings: Settings, runner: SumoRunner,
        initial_timing: TimingConfig | None = None,
    ) -> "SignalService":
        timing = TimingService(
            initial_timing if initial_timing is not None
            else cls.configured_timing(settings)
        )
        controller = SignalController(timing.active)
        return cls(settings, runner, timing, controller)

    def on_started(self) -> None:
        # 每次新仿真均从确定的 AUTO/ENABLED 初始状态开始，避免跨运行污染。
        self.control_mode = ControlMode.AUTO
        self.control_status = ControlStatus.ENABLED
        self._pending_mode = None
        self._pending_manual_phase = None
        self.controller.resume_auto(self.runner.simulation_time())
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
        if phase == PhaseId.ALL_RED:
            return "r"
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
        entered_all_red = switched and self.controller.is_all_red

        # AUTO：只在完整八阶段周期边界整体应用新配时。
        cycle_boundary = (
            switched
            and previous_phase == PhaseId.EW_STRAIGHT_YELLOW
            and self.controller.phase_id == PhaseId.NS_LEFT
        )
        if cycle_boundary:
            self._promote_pending_timing()

        # MANUAL/安全模式切换：进入 ALL_RED 后先向 SUMO 实际下发全红，
        # 至少保持一个仿真 step；下一次 step 才允许启动目标阶段/完成模式切换。
        # 这避免在同一次后台循环中 ALL_RED 被瞬间覆盖，SUMO 从未实际处于全红。
        if entered_all_red:
            self._promote_pending_timing()

        if self.controller.is_all_red:
            if self.control_status == ControlStatus.DISABLING:
                self.control_status = ControlStatus.DISABLED
                self._pending_mode = None
                self._pending_manual_phase = None
                log.info("signal control entered DISABLED after safe all-red")
            elif not entered_all_red and self._pending_mode is not None:
                self.control_mode = self._pending_mode
                self._pending_mode = None
                if self.control_mode == ControlMode.AUTO and self.control_status == ControlStatus.ENABLED:
                    self.controller.resume_auto(sim_time)
                log.info("signal control mode changed to %s at all-red", self.control_mode.value)
            elif (
                not entered_all_red
                and self._pending_manual_phase is not None
                and self.control_status == ControlStatus.ENABLED
                and self.control_mode == ControlMode.MANUAL
            ):
                target = self._pending_manual_phase
                self._pending_manual_phase = None
                self.controller.start_phase(target, sim_time)
                log.info("manual phase started after all-red hold: %s", target.value)

        self._sync_sumo()
        return self.snapshot(sim_time)

    def _promote_pending_timing(self) -> bool:
        promoted = self.timing.promote_pending_if_any()
        if promoted is None:
            return False
        self.controller.apply_timing(promoted)
        log.info(
            "timing promoted at safe boundary: version=%s timing=%s",
            self.timing.version,
            promoted.model_dump(),
        )
        return True

    def snapshot(self, sim_time: float | None = None) -> SignalSnapshot:
        if sim_time is None:
            sim_time = self.runner.simulation_time()

        ns_s, ns_l, ew_s, ew_l = self.controller.get_direction_states(sim_time)
        return SignalSnapshot(
            tls_id=self.settings.tls_id,
            phase_id=self.controller.phase_id,
            control_mode=self.control_mode,
            control_status=self.control_status,
            ns_straight=ns_s,
            ns_left=ns_l,
            ew_straight=ew_s,
            ew_left=ew_l,
            timing=self.timing.active,
        )

    def timing_snapshot(self) -> dict:
        """返回包含当前生效方案来源的完整配时状态。"""
        return self.timing.snapshot()

    def submit_timing(
        self,
        candidate: TimingConfig,
        source: dict | None = None,
    ) -> dict:
        if self.control_status != ControlStatus.ENABLED:
            log.warning(
                "timing update rejected: control_status=%s candidate=%s",
                self.control_status.value,
                candidate.model_dump(),
            )
            raise ValueError("信号控制未启用，拒绝配时控制命令")

        pending = self.timing.submit(candidate, source)
        if pending is None:
            result = {
                "accepted": True,
                "status": "unchanged_or_pending_cancelled",
                "effective": "immediate",
                **self.timing.snapshot(),
            }
            log.info(
                "timing update accepted: status=%s effective=%s version=%s candidate=%s",
                result["status"], result["effective"], self.timing.version,
                candidate.model_dump(),
            )
            return result

        # MANUAL 已处于全红时不存在正在执行的阶段，可立即安全应用。
        if self.control_mode == ControlMode.MANUAL and self.controller.is_all_red:
            self._promote_pending_timing()
            result = {
                "accepted": True,
                "status": "applied",
                "effective": "immediate_all_red",
                **self.timing.snapshot(),
            }
            log.info(
                "timing update accepted: status=applied effective=immediate_all_red "
                "version=%s candidate=%s",
                self.timing.version,
                candidate.model_dump(),
            )
            return result

        effective = (
            "next_cycle_boundary"
            if self.control_mode == ControlMode.AUTO
            else "next_manual_all_red"
        )
        result = {
            "accepted": True,
            "status": "queued",
            "effective": effective,
            **self.timing.snapshot(),
        }
        log.info(
            "timing update accepted: status=queued effective=%s "
            "active_version=%s pending_version=%s candidate=%s",
            effective, self.timing.version, self.timing.pending_version,
            candidate.model_dump(),
        )
        return result

    def request_control_enabled(self, enabled: bool) -> dict:
        sim_time = self.runner.simulation_time()
        if enabled:
            if self.control_status == ControlStatus.ENABLED:
                return self.control_state()
            if self.control_status == ControlStatus.DISABLING:
                raise ValueError("控制正在执行安全停用过渡，暂不能重新启用")
            self.control_status = ControlStatus.ENABLED
            if self.control_mode == ControlMode.AUTO:
                self.controller.resume_auto(sim_time)
            self._sync_sumo()
            return self.control_state()

        if self.control_status == ControlStatus.DISABLED:
            return self.control_state()
        if self.control_status == ControlStatus.DISABLING:
            return self.control_state()

        self.control_status = ControlStatus.DISABLING
        self._pending_mode = None
        self._pending_manual_phase = None
        self.controller.request_all_red()
        # 已处于全红时可立即完成停用，不等待下一次仿真步。
        if self.controller.is_all_red:
            self.control_status = ControlStatus.DISABLED
        self._sync_sumo()
        return self.control_state()

    def request_control_mode(self, mode: ControlMode) -> dict:
        if self.control_status == ControlStatus.DISABLING:
            raise ValueError("控制正在执行安全停用过渡，暂不能切换模式")
        if mode == self.control_mode and self._pending_mode is None:
            return self.control_state()

        sim_time = self.runner.simulation_time()
        if mode != self.control_mode:
            # 操作员显式切换控制模式时，撤销尚未执行的旧模式人工目标。
            self._pending_manual_phase = None
        if mode == ControlMode.MANUAL:
            if self.controller.is_all_red:
                self.control_mode = ControlMode.MANUAL
                self._pending_mode = None
            else:
                self._pending_mode = ControlMode.MANUAL
                self.controller.request_all_red()
        else:
            if self.controller.is_all_red:
                self._pending_mode = None
                self.control_mode = ControlMode.AUTO
                if self.control_status == ControlStatus.ENABLED:
                    self.controller.resume_auto(sim_time)
            else:
                self._pending_mode = ControlMode.AUTO
                self.controller.request_all_red()
        self._sync_sumo()
        return self.control_state()

    def right_turn_signal_states(self) -> dict[str, str]:
        """按 SUMO 实际 TLS 状态及 controlled-links 映射返回四个进口右转灯色。"""
        approaches = {"north": "N", "south": "S", "east": "E", "west": "W"}
        result: dict[str, set[str]] = {key: set() for key in approaches.values()}
        if not self._links or not self.runner.connected:
            return {key: "r" for key in result}

        actual_state = self.runner.get_tls_state(self.settings.tls_id)
        if len(actual_state) != len(self._links):
            raise RuntimeError(
                f"SUMO 实际 TLS 状态长度错误: {len(actual_state)} != {len(self._links)}"
            )

        for link_index, connections in enumerate(self._links):
            for from_lane, to_lane, via_lane in connections:
                _, movement = self._movement_for_link(from_lane, to_lane, via_lane)
                if movement != "right":
                    continue
                edge_id = from_lane.rsplit("_", 1)[0]
                approach = next(
                    (value for prefix, value in approaches.items() if edge_id.startswith(prefix)),
                    None,
                )
                if approach is None:
                    raise RuntimeError(f"无法识别右转进口方向: {from_lane}")
                result[approach].add(actual_state[link_index])

        normalized: dict[str, str] = {}
        for approach, states in result.items():
            if len(states) > 1:
                raise RuntimeError(
                    f"同一进口右转连接出现不一致 SUMO 灯色: approach={approach}, states={sorted(states)}"
                )
            normalized[approach] = next(iter(states), "r")
        return normalized

    def control_state(self) -> dict:
        return {
            "tls_id": self.settings.tls_id,
            "control_status": self.control_status.value,
            "control_mode": self.control_mode.value,
            "phase_id": self.controller.phase_id.value,
            "pending_mode": self._pending_mode.value if self._pending_mode else None,
            "pending_manual_phase": self._pending_manual_phase.value if self._pending_manual_phase else None,
        }

    def manual_switch(self, target: PhaseId) -> tuple[bool, str]:
        if self.control_status != ControlStatus.ENABLED:
            log.warning("manual phase rejected: reason=control_disabled target=%s", target)
            return False, "control_disabled"
        if self.control_mode != ControlMode.MANUAL:
            log.warning("manual phase rejected: reason=manual_mode_required target=%s", target)
            return False, "manual_mode_required"
        if target not in {
            PhaseId.NS_LEFT, PhaseId.NS_STRAIGHT,
            PhaseId.EW_LEFT, PhaseId.EW_STRAIGHT,
        }:
            log.warning("manual phase rejected: reason=invalid_target target=%s", target)
            return False, "target_must_be_protected_green_phase"
        if self._pending_manual_phase is not None:
            log.warning(
                "manual phase rejected: reason=manual_transition_pending target=%s pending=%s",
                target, self._pending_manual_phase,
            )
            return False, "manual_transition_pending"
        if self.controller.phase_id == target:
            log.info("manual phase accepted as no-op: target=%s", target.value)
            return True, "already_in_phase"

        sim_time = self.runner.simulation_time()
        if self.controller.is_all_red:
            self.controller.start_phase(target, sim_time)
            self._sync_sumo()
            log.info("manual phase accepted: target=%s status=started_from_all_red", target.value)
            return True, "started_from_all_red"

        self._pending_manual_phase = target
        self.controller.request_all_red()
        self._sync_sumo()
        log.info(
            "manual phase accepted: target=%s status=queued_after_green_yellow",
            target.value,
        )
        return True, "accepted_after_safe_all_red"
