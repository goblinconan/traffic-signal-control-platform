
"""信号状态机：独立计算四类受保护阶段、黄灯和倒计时。
输入：TimingConfig、仿真时间及可选手动切换目标。
输出：当前阶段、剩余时间、灯色和倒计时可见性。
依赖：models/signal.py。
调用方：services/signal_service.py。
"""
from __future__ import annotations

from app.models.signal import DirectionState, LightState, PhaseId, TimingConfig


_PHASE_ORDER: tuple[PhaseId, ...] = (
    PhaseId.NS_LEFT,
    PhaseId.NS_LEFT_YELLOW,
    PhaseId.NS_STRAIGHT,
    PhaseId.NS_STRAIGHT_YELLOW,
    PhaseId.EW_LEFT,
    PhaseId.EW_LEFT_YELLOW,
    PhaseId.EW_STRAIGHT,
    PhaseId.EW_STRAIGHT_YELLOW,
)

_YELLOW_PHASES = {
    PhaseId.NS_LEFT_YELLOW,
    PhaseId.NS_STRAIGHT_YELLOW,
    PhaseId.EW_LEFT_YELLOW,
    PhaseId.EW_STRAIGHT_YELLOW,
}

_GREEN_MOVEMENTS = {
    PhaseId.NS_LEFT: "ns_left",
    PhaseId.NS_STRAIGHT: "ns_straight",
    PhaseId.EW_LEFT: "ew_left",
    PhaseId.EW_STRAIGHT: "ew_straight",
}


class SignalController:
    def __init__(
        self,
        timing: TimingConfig,
        start_phase: PhaseId = PhaseId.NS_LEFT,
        start_time: float = 0.0,
    ) -> None:
        self._timing = timing
        self._phase = start_phase
        self._started_at = start_time
        self._duration = self._get_duration(start_phase)
        self._all_red_requested = False

    @property
    def phase_id(self) -> PhaseId:
        return self._phase

    @property
    def timing(self) -> TimingConfig:
        return self._timing

    @property
    def started_at(self) -> float:
        return self._started_at

    @property
    def is_all_red(self) -> bool:
        return self._phase == PhaseId.ALL_RED

    def _get_duration(self, phase: PhaseId) -> float:
        if phase == PhaseId.ALL_RED:
            return 0.0
        green_durations = {
            PhaseId.NS_LEFT: self._timing.ns_left_green,
            PhaseId.NS_STRAIGHT: self._timing.ns_straight_green,
            PhaseId.EW_LEFT: self._timing.ew_left_green,
            PhaseId.EW_STRAIGHT: self._timing.ew_straight_green,
        }
        return green_durations.get(phase, self._timing.yellow)

    def remaining(self, sim_time: float) -> float:
        return max(0.0, self._started_at + self._duration - sim_time)

    def next_phase(self) -> PhaseId:
        if self._phase == PhaseId.ALL_RED:
            return PhaseId.NS_LEFT
        index = _PHASE_ORDER.index(self._phase)
        return _PHASE_ORDER[(index + 1) % len(_PHASE_ORDER)]

    def apply_timing(self, new_timing: TimingConfig) -> None:
        """仅在完整周期边界调用，保持当前阶段起始时间不变。"""
        self._timing = new_timing
        self._duration = self._get_duration(self._phase)

    def request_all_red(self) -> None:
        """请求在当前绿灯及其完整黄灯结束后进入全红。"""
        self._all_red_requested = True

    def resume_auto(self, sim_time: float) -> None:
        """从全红安全状态恢复自动循环。"""
        self._all_red_requested = False
        self._phase = PhaseId.NS_LEFT
        self._started_at = sim_time
        self._duration = self._get_duration(self._phase)

    def start_phase(self, phase: PhaseId, sim_time: float) -> None:
        """从全红状态启动一个受保护绿灯业务阶段。"""
        if not isinstance(phase, PhaseId) or phase not in _GREEN_MOVEMENTS:
            phase_name = getattr(phase, "value", phase)
            raise ValueError(f"目标必须是受保护绿灯业务阶段: {phase_name}")

        self._all_red_requested = False
        self._phase = phase
        self._started_at = sim_time
        self._duration = self._get_duration(phase)

    def hold_all_red(self, sim_time: float) -> None:
        self._all_red_requested = True
        self._phase = PhaseId.ALL_RED
        self._started_at = sim_time
        self._duration = 0.0

    def advance_if_needed(self, sim_time: float) -> bool:
        if self._phase == PhaseId.ALL_RED:
            return False
        if sim_time + 1e-9 < self._started_at + self._duration:
            return False

        if self._all_red_requested:
            if self._phase in _YELLOW_PHASES:
                self.hold_all_red(sim_time)
            else:
                self._phase = self.next_phase()
                self._started_at = sim_time
                self._duration = self._get_duration(self._phase)
            return True

        self._phase = self.next_phase()
        self._started_at = sim_time
        self._duration = self._get_duration(self._phase)
        return True

    def manual_switch(self, target: PhaseId, sim_time: float) -> tuple[bool, str]:
        """仅允许从 ALL_RED 启动业务绿灯，禁止低层接口截断当前阶段。"""
        if target == self._phase:
            return True, "already_in_phase"
        if self._phase != PhaseId.ALL_RED:
            return False, "safe_all_red_required"
        if target not in _GREEN_MOVEMENTS:
            return False, f"invalid_manual_target:{target.value}"
        self.start_phase(target, sim_time)
        return True, "started_from_all_red"

    def get_direction_states(
        self, sim_time: float
    ) -> tuple[DirectionState, DirectionState, DirectionState, DirectionState]:
        phase = self._phase
        remaining = self.remaining(sim_time)
        if phase == PhaseId.ALL_RED:
            red = DirectionState(
                state=LightState.RED, remaining=0.0, countdown_visible=False
            )
            return red.model_copy(), red.model_copy(), red.model_copy(), red.model_copy()
        timing = self._timing

        active_movement = _GREEN_MOVEMENTS.get(phase)
        yellow_movement = None
        if phase in _YELLOW_PHASES:
            yellow_movement = phase.value.removesuffix("_YELLOW").lower()
            # Enum 命名与快照字段均采用 ns_left/ns_straight/ew_left/ew_straight。
            yellow_movement = {
                "ns_left": "ns_left",
                "ns_straight": "ns_straight",
                "ew_left": "ew_left",
                "ew_straight": "ew_straight",
            }[yellow_movement]

        def duration_for(candidate: PhaseId) -> float:
            return self._get_duration(candidate)

        def red_remaining(target_green: PhaseId) -> float:
            if active_movement == _GREEN_MOVEMENTS[target_green]:
                return 0.0
            if yellow_movement == _GREEN_MOVEMENTS[target_green]:
                return 0.0

            total = remaining
            index = _PHASE_ORDER.index(phase)
            for offset in range(1, len(_PHASE_ORDER) + 1):
                candidate = _PHASE_ORDER[(index + offset) % len(_PHASE_ORDER)]
                if candidate == target_green:
                    break
                total += duration_for(candidate)
            return total

        def make_state(movement: str, target_green: PhaseId) -> DirectionState:
            if active_movement == movement:
                return DirectionState(
                    state=LightState.GREEN,
                    remaining=round(remaining, 2),
                    countdown_visible=remaining <= 8.0,
                )
            if yellow_movement == movement:
                return DirectionState(
                    state=LightState.YELLOW,
                    remaining=round(remaining, 2),
                    countdown_visible=True,
                )
            red_time = red_remaining(target_green)
            return DirectionState(
                state=LightState.RED,
                remaining=round(red_time, 2),
                countdown_visible=red_time <= 10.0,
            )

        return (
            make_state("ns_straight", PhaseId.NS_STRAIGHT),
            make_state("ns_left", PhaseId.NS_LEFT),
            make_state("ew_straight", PhaseId.EW_STRAIGHT),
            make_state("ew_left", PhaseId.EW_LEFT),
        )
