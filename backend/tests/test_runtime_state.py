"""B4 REST/WS 统一运行状态模型测试。"""
from __future__ import annotations

import asyncio
from pathlib import Path

from app.core.config import Settings
from app.models.signal import PhaseId
from app.services.signal_service import SignalService
from app.services.state_service import RuntimeStateService
from app.simulation.lifecycle import LifecycleSnapshot, SimulationStatus
from app.simulation.sumo_runner import VehicleSnapshot


ROOT = Path(__file__).resolve().parents[2]


class FakeRunner:
    def __init__(self):
        self.time = 12.5
        self.connected = True
        self.process_alive = True
        self.step_index = 25

    def simulation_time(self):
        return self.time

    def vehicles(self):
        return [VehicleSnapshot("veh-1", 10, 20, 90, 5, 4.5, 1.8)] if self.connected else []


class FakeLifecycle:
    def __init__(self, runner):
        self.runner = runner
        self.status = SimulationStatus.RUNNING

    def snapshot(self):
        return LifecycleSnapshot(
            status=self.status,
            simulation_time=self.runner.time,
            sumo_connected=self.runner.connected,
            last_error=None,
            step_index=self.runner.step_index,
            process_alive=self.runner.process_alive,
        )

    async def read_state(self, function):
        return function()


def make_service(tmp_path=None):
    runner = FakeRunner()
    settings = Settings(
        sumo_config=str(ROOT / "simulation" / "config" / "intersection.sumocfg"),
        tls_id="intersection_0",
    )
    signal_service = SignalService.create(settings, runner)
    lifecycle = FakeLifecycle(runner)
    state_service = RuntimeStateService(lifecycle, signal_service, runner, settings)
    return state_service, signal_service, runner, lifecycle


def test_unified_snapshot_contains_lifecycle_signal_timing_vehicle_and_network():
    service, _, _, _ = make_service()
    message = asyncio.run(service.create_message("simulation_snapshot"))

    assert message["schema_version"] == "1.0"
    assert message["type"] == "simulation_snapshot"
    assert message["sequence"] == 1
    assert message["simulation_status"] == "RUNNING"
    assert message["simulation_time"] == 12.5
    assert message["step_index"] == 25
    assert message["signal_control"]["phase_id"] == "NS_LEFT"
    assert message["signal_control"]["phase_index"] == 0
    assert message["signal_control"]["control_mode"] == "AUTO"
    assert [item["group_id"] for item in message["signal_control"]["groups"]] == [
        "NS_LEFT", "NS_STRAIGHT", "EW_LEFT", "EW_STRAIGHT"
    ]
    assert len(message["signal_control"]["right_turns"]) == 4
    assert message["signal_control"]["right_turns"][0]["state"] == "PERMISSIVE_YIELD"
    assert message["timing"]["timing_version"] == 1
    assert message["timing"]["pending"] is None
    assert message["vehicles"][0]["id"] == "veh-1"
    assert len(message["network_version"]) == 64


def test_sequence_is_monotonic_across_snapshots_and_updates():
    service, _, _, _ = make_service()
    first = asyncio.run(service.create_message("simulation_snapshot"))
    second = asyncio.run(service.create_message("simulation_update"))
    third = asyncio.run(service.create_message("simulation_update"))
    assert [first["sequence"], second["sequence"], third["sequence"]] == [1, 2, 3]
    assert second["type"] == "simulation_update"


def test_all_red_snapshot_has_no_sumo_phase_index_and_right_turns_are_red():
    service, signal_service, _, _ = make_service()
    signal_service.controller.hold_all_red(12.5)
    message = asyncio.run(service.create_message())
    assert message["signal_control"]["phase_id"] == PhaseId.ALL_RED.value
    assert message["signal_control"]["phase_index"] is None
    assert all(x["signal_state"] == "r" for x in message["signal_control"]["right_turns"])
    assert all(x["state"] == "r" for x in message["signal_control"]["groups"])


def test_stopped_snapshot_has_empty_vehicle_list():
    service, _, runner, lifecycle = make_service()
    runner.connected = False
    runner.process_alive = False
    lifecycle.status = SimulationStatus.STOPPED
    message = asyncio.run(service.create_message())
    assert message["simulation_status"] == "STOPPED"
    assert message["sumo_connected"] is False
    assert message["vehicles"] == []


def test_all_red_pending_manual_phase_is_reported_as_next_phase():
    service, signal_service, _, _ = make_service()
    signal_service.controller.hold_all_red(12.5)
    signal_service._pending_manual_phase = PhaseId.EW_LEFT
    message = asyncio.run(service.create_message())
    assert message["signal_control"]["next_phase"] == "EW_LEFT"


def test_right_turn_signal_state_comes_from_actual_sumo_tls_string():
    service, signal_service, runner, _ = make_service()
    signal_service._links = [[(f"{direction}_0", "out_0", "via")] for direction in ("north", "south", "east", "west")]
    runner.get_tls_state = lambda tls_id: "grgr"
    message = asyncio.run(service.create_message())
    states = {item["approach"]: item["signal_state"] for item in message["signal_control"]["right_turns"]}
    assert states == {"N": "g", "S": "r", "E": "g", "W": "r"}
