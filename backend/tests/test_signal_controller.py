from app.controllers.signal_controller import SignalController
from app.models.signal import TimingConfig, PhaseId, LightState

def make_ctl() -> SignalController:
    t = TimingConfig(ns_straight_green=40, ns_left_green=20, ew_straight_green=40, ew_left_green=20, yellow=3)
    return SignalController(t, start_time=0.0)

def test_phase_sequence():
    ctl = make_ctl()
    assert ctl.phase_id == PhaseId.NS_STRAIGHT
    
    # 40秒后变南北直行黄灯
    ctl.advance_if_needed(40.0)
    assert ctl.phase_id == PhaseId.NS_STRAIGHT_YELLOW
    
    # 43秒后变南北左转绿灯
    ctl.advance_if_needed(43.0)
    assert ctl.phase_id == PhaseId.NS_LEFT
    
    # 63秒后变南北左转黄灯
    ctl.advance_if_needed(63.0)
    assert ctl.phase_id == PhaseId.NS_LEFT_YELLOW

def test_direction_states():
    ctl = make_ctl()
    ns_s, ns_l, ew_s, ew_l = ctl.get_direction_states(0.0)
    
    # 南北直行绿，左转红，东西全红
    assert ns_s.state == LightState.GREEN
    assert ns_l.state == LightState.RED
    assert ew_s.state == LightState.RED
    assert ew_l.state == LightState.RED