
import os
import sys
import types
import xml.etree.ElementTree as ET
from pathlib import Path

# 测试 SignalService 不启动 SUMO；仅提供 TraCI 模块导入占位。
sys.modules.setdefault("traci", types.ModuleType("traci"))

from app.core.config import Settings
from app.models.signal import PhaseId, TimingConfig
from app.services.signal_service import SignalService
from app.services.timing_service import TimingService
from app.controllers.signal_controller import SignalController


PROJECT_ROOT = Path(__file__).resolve().parents[2]
NET_FILE = PROJECT_ROOT / "simulation" / "network" / "intersection.net.xml"


class FakeRunner:
    def __init__(self):
        self.time = 0.0
        self.states = []

    def controlled_links(self, tls_id):
        root = ET.parse(NET_FILE).getroot()
        by_index = {}
        for connection in root.findall("connection"):
            if connection.get("tl") != tls_id:
                continue
            index = int(connection.get("linkIndex"))
            from_lane = (
                f'{connection.get("from")}_{connection.get("fromLane")}'
            )
            to_lane = (
                f'{connection.get("to")}_{connection.get("toLane")}'
            )
            via_lane = connection.get("via", "")
            by_index.setdefault(index, []).append(
                (from_lane, to_lane, via_lane)
            )
        return [by_index[index] for index in sorted(by_index)]

    def set_tls_state(self, tls_id, state):
        self.states.append(state)

    def step(self):
        self.time += 0.5
        return self.time

    def simulation_time(self):
        return self.time


def make_service():
    settings = Settings(
        sumo_home="C:/SUMO",
        sumo_config=str(PROJECT_ROOT / "simulation/config/intersection.sumocfg"),
        tls_id="intersection_0",
        ns_straight_green=40,
        ns_left_green=20,
        ew_straight_green=40,
        ew_left_green=20,
        yellow=3,
    )
    runner = FakeRunner()
    timing = TimingService(TimingConfig())
    controller = SignalController(timing.active)
    service = SignalService(settings, runner, timing, controller)
    return service, runner


def test_controlled_link_mapping_is_exactly_20_indices_and_right_turns_yield():
    service, runner = make_service()
    service.on_started()

    assert len(service._links) == 20
    assert len(runner.states[-1]) == 20
    # NS 左转：linkIndex 3、4、13、14 放行；四个右转使用让行绿灯。
    assert runner.states[-1] == "grrGGgrrrrgrrGGgrrrr"
    assert all(runner.states[-1][index] == "g" for index in (0, 5, 10, 15))


def test_each_protected_phase_maps_to_expected_link_indices():
    service, runner = make_service()
    service.on_started()

    expected = {
        PhaseId.NS_LEFT: (3, 4, 13, 14),
        PhaseId.NS_STRAIGHT: (1, 2, 11, 12),
        PhaseId.EW_LEFT: (8, 9, 18, 19),
        PhaseId.EW_STRAIGHT: (6, 7, 16, 17),
    }

    for phase, active_indices in expected.items():
        service.controller._phase = phase
        state = service._build_state_string()
        assert len(state) == 20
        assert {index for index, char in enumerate(state) if char == "G"} == set(active_indices)


def test_mixed_movement_group_fails_closed():
    service, _ = make_service()
    service._links = [[
        ("north_in_0", "west_out_0", ":via0"),
        ("north_in_3", "east_out_3", ":via1"),
    ]]
    try:
        service._build_state_string()
    except RuntimeError as exc:
        assert "冲突灯色需求" in str(exc)
    else:
        raise AssertionError("混合 movement 的 linkIndex 必须拒绝生成信号状态")


def test_pending_timing_is_promoted_only_at_complete_cycle_boundary():
    service, _ = make_service()
    service.on_started()
    candidate = TimingConfig(
        ns_straight_green=45,
        ns_left_green=25,
        ew_straight_green=42,
        ew_left_green=22,
        yellow=3,
    )
    service.submit_timing(candidate)

    # 运行到 NS 左转绿灯结束，仍不能提前应用新配时。
    for _ in range(40):
        service.step()
    assert service.controller.phase_id == PhaseId.NS_LEFT_YELLOW
    assert service.timing.pending == candidate
    assert service.timing.active.ns_left_green == 20

    # 从 20s 连续运行到完整周期边界 132s。
    for _ in range(224):
        service.step()
    assert service.controller.phase_id == PhaseId.NS_LEFT
    assert service.timing.pending is None
    assert service.timing.active == candidate
    assert service.controller.remaining(132.0) == 25.0
