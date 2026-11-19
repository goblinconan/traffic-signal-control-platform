"""B4 统一运行状态组装与序列号管理。
输入：SimulationLifecycle、SignalService、SumoRunner 和 SUMO 路网配置。
输出：REST/WS 共用的完整运行状态消息。
依赖：运行状态 Pydantic 模型、network_geometry。
调用方：simulation API、WebSocket 与后台广播循环。
"""
from __future__ import annotations

import threading
from dataclasses import asdict
from typing import Any, Literal

from app.models.runtime_state import RuntimeStateMessage
from app.models.signal import PhaseId
from app.simulation.network_geometry import resolve_network_file, get_network_version

_PHASE_INDEX = {
    PhaseId.NS_LEFT: 0,
    PhaseId.NS_LEFT_YELLOW: 1,
    PhaseId.NS_STRAIGHT: 2,
    PhaseId.NS_STRAIGHT_YELLOW: 3,
    PhaseId.EW_LEFT: 4,
    PhaseId.EW_LEFT_YELLOW: 5,
    PhaseId.EW_STRAIGHT: 6,
    PhaseId.EW_STRAIGHT_YELLOW: 7,
}
_GROUP_FIELDS = (
    ("NS_LEFT", "ns_left"),
    ("NS_STRAIGHT", "ns_straight"),
    ("EW_LEFT", "ew_left"),
    ("EW_STRAIGHT", "ew_straight"),
)


class RuntimeStateService:
    """单进程单调递增序列号；REST 读取与 WS 推送共享同一消息构造器。"""

    def __init__(self, lifecycle: Any, signal_service: Any, runner: Any, settings: Any) -> None:
        self._lifecycle = lifecycle
        self._signal_service = signal_service
        self._runner = runner
        self._settings = settings
        self.intersection_id = settings.tls_id
        self._sequence = 0
        self._sequence_lock = threading.Lock()
        self._network_file = resolve_network_file(settings.sumo_config)
        self._network_version = get_network_version(self._network_file)

    def _refresh_network_version(self) -> str:
        # net.xml 通常只有几十 KB；每次按内容计算，避免同尺寸/保留时间戳替换导致版本漏检。
        self._network_version = get_network_version(self._network_file)
        return self._network_version

    def network_resource(self) -> dict[str, Any]:
        from app.simulation.network_geometry import load_network_geometry

        self._refresh_network_version()
        geometry = load_network_geometry(self._network_file)
        return {
            "intersection_id": self.intersection_id,
            "network_version": self._network_version,
            "geometry": geometry,
        }

    def _build(self, message_type: Literal["simulation_snapshot", "simulation_update"]) -> dict[str, Any]:
        lifecycle = self._lifecycle.snapshot()
        sim_time = lifecycle.simulation_time
        signal = self._signal_service.snapshot(sim_time)
        control = self._signal_service.control_state()
        controller = self._signal_service.controller
        phase = signal.phase_id
        remaining = controller.remaining(sim_time)
        phase_remaining = max(0.0, float(remaining))
        if phase == PhaseId.ALL_RED:
            phase_countdown = False
        elif phase in {PhaseId.NS_LEFT_YELLOW, PhaseId.NS_STRAIGHT_YELLOW, PhaseId.EW_LEFT_YELLOW, PhaseId.EW_STRAIGHT_YELLOW}:
            phase_countdown = True
        else:
            phase_countdown = phase_remaining <= 8.0

        groups = []
        for group_id, field_name in _GROUP_FIELDS:
            item = getattr(signal, field_name)
            groups.append({
                "group_id": group_id,
                "state": item.state.value,
                "remaining": item.remaining,
                "countdown_visible": item.countdown_visible,
            })

        right_turn_lights = self._signal_service.right_turn_signal_states()
        right_turns = [
            {"approach": approach, "state": "PERMISSIVE_YIELD", "signal_state": right_turn_lights[approach]}
            for approach in ("N", "S", "E", "W")
        ]
        timing = self._signal_service.timing_snapshot()
        vehicles = [asdict(vehicle) for vehicle in self._runner.vehicles()]
        pending_manual_phase = control["pending_manual_phase"]
        next_phase = (
            pending_manual_phase
            if phase == PhaseId.ALL_RED and pending_manual_phase is not None
            else (None if phase == PhaseId.ALL_RED else controller.next_phase())
        )
        with self._sequence_lock:
            self._sequence += 1
            sequence = self._sequence

        network_version = self._refresh_network_version()
        payload = {
            "schema_version": "1.0",
            "type": message_type,
            "sequence": sequence,
            "simulation_time": sim_time,
            "simulation_status": lifecycle.status,
            "sumo_connected": lifecycle.sumo_connected,
            "step_index": lifecycle.step_index,
            "process_alive": lifecycle.process_alive,
            "last_error": lifecycle.last_error,
            "signal_control": {
                "tls_id": signal.tls_id,
                "control_status": signal.control_status,
                "enabled": signal.control_status.value == "ENABLED",
                "control_mode": signal.control_mode,
                "phase_id": phase,
                "phase_index": _PHASE_INDEX.get(phase),
                "remaining": round(phase_remaining, 2),
                "countdown_visible": phase_countdown,
                "next_phase": next_phase,
                "pending_mode": control["pending_mode"],
                "pending_manual_phase": control["pending_manual_phase"],
                "groups": groups,
                "right_turns": right_turns,
            },
            "timing": timing,
            "vehicles": vehicles,
            "network_version": network_version,
        }
        return RuntimeStateMessage.model_validate(payload).model_dump(mode="json")

    async def create_message(
        self, message_type: Literal["simulation_snapshot", "simulation_update"] = "simulation_snapshot"
    ) -> dict[str, Any]:
        return await self._lifecycle.read_state(lambda: self._build(message_type))
