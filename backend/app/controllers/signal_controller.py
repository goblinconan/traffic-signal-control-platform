"""信号状态机：纯逻辑，不依赖 SUMO，便于单元测试。
输入：TimingConfig、仿真当前时间、手动切换目标相位。
输出：当前相位、剩余时间、灯色、倒计时可见性、下一相位。
依赖：models/signal.py。
调用方：services/signal_service.py。
"""
from __future__ import annotations

from dataclasses import dataclass

from app.models.signal import LightState, PhaseId, TimingConfig, DirectionState

# 定义 8 个相位的固定循环顺序
_PHASE_ORDER = [
    PhaseId.NS_STRAIGHT,
    PhaseId.NS_STRAIGHT_YELLOW,
    PhaseId.NS_LEFT,
    PhaseId.NS_LEFT_YELLOW,
    PhaseId.EW_STRAIGHT,
    PhaseId.EW_STRAIGHT_YELLOW,
    PhaseId.EW_LEFT,
    PhaseId.EW_LEFT_YELLOW,
]

class SignalController:
    def __init__(self, timing: TimingConfig, start_phase: PhaseId = PhaseId.NS_STRAIGHT,
                 start_time: float = 0.0) -> None:
        self._timing = timing
        self._phase = start_phase
        self._started_at = start_time
        self._duration = self._get_duration(start_phase)

    @property
    def phase_id(self) -> PhaseId:
        return self._phase

    @property
    def timing(self) -> TimingConfig:
        return self._timing

    def _get_duration(self, phase: PhaseId) -> float:
        if phase == PhaseId.NS_STRAIGHT: return self._timing.ns_straight_green
        if phase == PhaseId.NS_LEFT: return self._timing.ns_left_green
        if phase == PhaseId.EW_STRAIGHT: return self._timing.ew_straight_green
        if phase == PhaseId.EW_LEFT: return self._timing.ew_left_green
        return self._timing.yellow # 黄灯时长

    def remaining(self, sim_time: float) -> float:
        return max(0.0, self._started_at + self._duration - sim_time)

    def next_phase(self) -> PhaseId:
        idx = _PHASE_ORDER.index(self._phase)
        return _PHASE_ORDER[(idx + 1) % len(_PHASE_ORDER)]

    def apply_timing(self, new_timing: TimingConfig) -> None:
        self._timing = new_timing

    def advance_if_needed(self, sim_time: float) -> bool:
        if sim_time + 1e-9 < self._started_at + self._duration:
            return False
        
        # 切换到下一个相位
        self._phase = self.next_phase()
        self._started_at = sim_time
        self._duration = self._get_duration(self._phase)
        return True

    def manual_switch(self, target: PhaseId, sim_time: float) -> tuple[bool, str]:
        if target == self._phase:
            return True, "already_in_phase"
        if target != self.next_phase():
            return False, f"illegal_transition:{self._phase.value}->{target.value}"
        self._phase = target
        self._started_at = sim_time
        self._duration = self._get_duration(self._phase)
        return True, "ok"

    # 核心：生成给前端的 4 个方向灯色及倒计时
    def get_direction_states(self, sim_time: float) -> tuple[DirectionState, DirectionState, DirectionState, DirectionState]:
        phase = self._phase
        rem = self.remaining(sim_time)
        t = self._timing
        
        ns_straight_g = (phase == PhaseId.NS_STRAIGHT)
        ns_straight_y = (phase == PhaseId.NS_STRAIGHT_YELLOW)
        ns_left_g = (phase == PhaseId.NS_LEFT)
        ns_left_y = (phase == PhaseId.NS_LEFT_YELLOW)

        ew_straight_g = (phase == PhaseId.EW_STRAIGHT)
        ew_straight_y = (phase == PhaseId.EW_STRAIGHT_YELLOW)
        ew_left_g = (phase == PhaseId.EW_LEFT)
        ew_left_y = (phase == PhaseId.EW_LEFT_YELLOW)

        # 计算红灯剩余时间：从当前相位一直累加到该方向下一次绿灯亮起
        def calc_red_time(target_phase: PhaseId) -> float:
            if self._phase == target_phase:
                return 0.0
            idx_curr = _PHASE_ORDER.index(self._phase)
            idx_target = _PHASE_ORDER.index(target_phase)
            total = rem
            curr = idx_curr
            while True:
                curr = (curr + 1) % len(_PHASE_ORDER)
                p = _PHASE_ORDER[curr]
                if p == target_phase:
                    break
                if p in (PhaseId.NS_STRAIGHT_YELLOW, PhaseId.NS_LEFT_YELLOW, PhaseId.EW_STRAIGHT_YELLOW, PhaseId.EW_LEFT_YELLOW):
                    total += t.yellow
                elif p == PhaseId.NS_STRAIGHT: total += t.ns_straight_green
                elif p == PhaseId.NS_LEFT: total += t.ns_left_green
                elif p == PhaseId.EW_STRAIGHT: total += t.ew_straight_green
                elif p == PhaseId.EW_LEFT: total += t.ew_left_green
            return total

        def calc(is_active: bool, is_yellow: bool, red_time: float) -> DirectionState:
            if is_active:
                return DirectionState(
                    state=LightState.YELLOW if is_yellow else LightState.GREEN,
                    remaining=round(rem, 2),
                    countdown_visible=True if is_yellow else (rem <= 8.0)
                )
            return DirectionState(
                state=LightState.RED, 
                remaining=round(red_time, 2), 
                countdown_visible=(red_time <= 10.0)
            )

        ns_s = calc(ns_straight_g or ns_straight_y, ns_straight_y, calc_red_time(PhaseId.NS_STRAIGHT))
        ns_l = calc(ns_left_g or ns_left_y, ns_left_y, calc_red_time(PhaseId.NS_LEFT))
        ew_s = calc(ew_straight_g or ew_straight_y, ew_straight_y, calc_red_time(PhaseId.EW_STRAIGHT))
        ew_l = calc(ew_left_g or ew_left_y, ew_left_y, calc_red_time(PhaseId.EW_LEFT))

        return ns_s, ns_l, ew_s, ew_l