
import os
import sys
import types
import pytest
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


def _advance_service(service, count):
    for _ in range(count):
        service.step()


def test_disable_waits_for_current_green_and_full_yellow_then_all_red_including_right_turns():
    from app.models.signal import ControlStatus

    service, runner = make_service()
    service.on_started()

    state = service.request_control_enabled(False)
    assert state["control_status"] == "DISABLING"
    assert service.controller.phase_id == PhaseId.NS_LEFT

    # 20s 绿灯结束后必须先进入完整 3s 黄灯。
    _advance_service(service, 40)
    assert service.controller.phase_id == PhaseId.NS_LEFT_YELLOW
    assert service.control_status == ControlStatus.DISABLING

    _advance_service(service, 6)
    assert service.controller.phase_id == PhaseId.ALL_RED
    assert service.control_status == ControlStatus.DISABLED
    assert runner.states[-1] == "r" * 20
    assert service.snapshot().control_status == ControlStatus.DISABLED


def test_auto_to_manual_waits_for_yellow_then_holds_all_red_until_request():
    from app.models.signal import ControlMode

    service, runner = make_service()
    service.on_started()
    _advance_service(service, 40)  # arrive at NS_LEFT_YELLOW

    result = service.request_control_mode(ControlMode.MANUAL)
    assert result["control_mode"] == "AUTO"
    assert result["pending_mode"] == "MANUAL"

    _advance_service(service, 6)
    assert service.control_mode == ControlMode.MANUAL
    assert service.controller.phase_id == PhaseId.ALL_RED
    assert runner.states[-1] == "r" * 20

    # MANUAL 空闲时不会自动推进。
    _advance_service(service, 20)
    assert service.controller.phase_id == PhaseId.ALL_RED
    assert runner.states[-1] == "r" * 20


def test_manual_request_starts_from_all_red_and_next_request_uses_safe_transition():
    from app.models.signal import ControlMode

    service, runner = make_service()
    service.on_started()
    _advance_service(service, 40)
    service.request_control_mode(ControlMode.MANUAL)
    _advance_service(service, 6)

    ok, reason = service.manual_switch(PhaseId.EW_LEFT)
    assert ok is True
    assert reason == "started_from_all_red"
    assert service.controller.phase_id == PhaseId.EW_LEFT

    ok, reason = service.manual_switch(PhaseId.NS_STRAIGHT)
    assert ok is True
    assert reason == "accepted_after_safe_all_red"

    _advance_service(service, 40)  # EW_LEFT green ends -> yellow
    assert service.controller.phase_id == PhaseId.EW_LEFT_YELLOW
    _advance_service(service, 6)   # yellow completes -> all red -> target starts
    assert service.controller.phase_id == PhaseId.NS_STRAIGHT
    assert runner.states[-1] == "gGGrrgrrrrgGGrrgrrrr"


def test_reenable_auto_from_disabled_restarts_cycle_but_manual_stays_all_red():
    from app.models.signal import ControlMode

    service, runner = make_service()
    service.on_started()
    service.request_control_enabled(False)
    _advance_service(service, 46)
    assert service.control_status.value == "DISABLED"

    service.request_control_mode(ControlMode.MANUAL)
    service.request_control_enabled(True)
    assert service.controller.phase_id == PhaseId.ALL_RED
    assert runner.states[-1] == "r" * 20

    service.request_control_mode(ControlMode.AUTO)
    assert service.controller.phase_id == PhaseId.NS_LEFT
    assert runner.states[-1] == "grrGGgrrrrgrrGGgrrrr"


def test_new_simulation_resets_control_domain_to_auto_enabled():
    from app.models.signal import ControlMode, ControlStatus

    service, runner = make_service()
    service.on_started()
    service.request_control_enabled(False)
    _advance_service(service, 46)
    assert service.control_status == ControlStatus.DISABLED
    service.request_control_mode(ControlMode.MANUAL)

    runner.time = 0.0
    service.on_started()
    assert service.control_status == ControlStatus.ENABLED
    assert service.control_mode == ControlMode.AUTO
    assert service.controller.phase_id == PhaseId.NS_LEFT
    assert runner.states[-1] == "grrGGgrrrrgrrGGgrrrr"


def test_disabled_rejects_timing_and_manual_phase_commands():
    from app.models.signal import ControlMode

    service, _ = make_service()
    service.on_started()
    service.request_control_enabled(False)
    _advance_service(service, 46)

    ok, reason = service.manual_switch(PhaseId.NS_STRAIGHT)
    assert ok is False
    assert reason == "control_disabled"
    try:
        service.submit_timing(TimingConfig())
    except ValueError as exc:
        assert "未启用" in str(exc)
    else:
        raise AssertionError("DISABLED 必须拒绝配时控制")


def test_auto_mode_switch_from_manual_active_phase_waits_for_all_red():
    from app.models.signal import ControlMode

    service, runner = make_service()
    service.on_started()
    _advance_service(service, 40)
    service.request_control_mode(ControlMode.MANUAL)
    _advance_service(service, 6)
    service.manual_switch(PhaseId.EW_LEFT)

    result = service.request_control_mode(ControlMode.AUTO)
    assert result["control_mode"] == "MANUAL"
    assert result["pending_mode"] == "AUTO"

    _advance_service(service, 40)
    assert service.controller.phase_id == PhaseId.EW_LEFT_YELLOW
    _advance_service(service, 6)
    assert service.control_mode == ControlMode.AUTO
    assert service.controller.phase_id == PhaseId.NS_LEFT
    assert runner.states[-1] == "grrGGgrrrrgrrGGgrrrr"


def test_switching_to_auto_clears_unexecuted_manual_target():
    from app.models.signal import ControlMode

    service, _ = make_service()
    service.on_started()
    _advance_service(service, 40)
    service.request_control_mode(ControlMode.MANUAL)
    _advance_service(service, 6)
    service.manual_switch(PhaseId.EW_LEFT)
    service.manual_switch(PhaseId.NS_STRAIGHT)
    assert service._pending_manual_phase == PhaseId.NS_STRAIGHT

    service.request_control_mode(ControlMode.AUTO)
    assert service._pending_manual_phase is None
    assert service._pending_mode == ControlMode.AUTO

@pytest.mark.parametrize(
    "target",
    [
        PhaseId.NS_LEFT_YELLOW,
        PhaseId.NS_STRAIGHT_YELLOW,
        PhaseId.EW_LEFT_YELLOW,
        PhaseId.EW_STRAIGHT_YELLOW,
        PhaseId.ALL_RED,
        "INVALID_PHASE",
    ],
)
def test_manual_switch_rejects_non_protected_green_phase(target):
    from app.models.signal import ControlMode

    service, runner = make_service()
    service.on_started()

    service.request_control_mode(ControlMode.MANUAL)
    _advance_service(service, 46)

    assert service.controller.phase_id == PhaseId.ALL_RED

    previous_state = runner.states[-1]

    ok, reason = service.manual_switch(target)

    assert ok is False
    assert reason == "target_must_be_protected_green_phase"
    assert service.controller.phase_id == PhaseId.ALL_RED
    assert service._pending_manual_phase is None
    assert runner.states[-1] == previous_state
