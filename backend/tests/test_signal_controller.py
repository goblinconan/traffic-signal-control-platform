
from app.controllers.signal_controller import SignalController
from app.models.signal import LightState, PhaseId, TimingConfig


def make_controller() -> SignalController:
    timing = TimingConfig(
        ns_straight_green=40,
        ns_left_green=20,
        ew_straight_green=40,
        ew_left_green=20,
        yellow=3,
    )
    return SignalController(timing, start_time=0.0)


def test_phase_sequence_matches_approved_business_order():
    controller = make_controller()
    assert controller.phase_id == PhaseId.NS_LEFT

    transitions = [
        (20.0, PhaseId.NS_LEFT_YELLOW),
        (23.0, PhaseId.NS_STRAIGHT),
        (63.0, PhaseId.NS_STRAIGHT_YELLOW),
        (66.0, PhaseId.EW_LEFT),
        (86.0, PhaseId.EW_LEFT_YELLOW),
        (89.0, PhaseId.EW_STRAIGHT),
        (129.0, PhaseId.EW_STRAIGHT_YELLOW),
        (132.0, PhaseId.NS_LEFT),
    ]
    for simulation_time, expected_phase in transitions:
        assert controller.advance_if_needed(simulation_time) is True
        assert controller.phase_id == expected_phase


def test_initial_signal_states_and_red_countdowns():
    controller = make_controller()
    ns_straight, ns_left, ew_straight, ew_left = (
        controller.get_direction_states(0.0)
    )

    assert ns_left.state == LightState.GREEN
    assert ns_left.remaining == 20.0
    assert ns_straight.state == LightState.RED
    assert ns_straight.remaining == 23.0
    assert ew_left.state == LightState.RED
    assert ew_left.remaining == 66.0
    assert ew_straight.state == LightState.RED
    assert ew_straight.remaining == 89.0


def test_yellow_phase_keeps_only_its_own_movement_yellow():
    controller = make_controller()
    controller.advance_if_needed(20.0)

    ns_straight, ns_left, ew_straight, ew_left = (
        controller.get_direction_states(21.0)
    )
    assert ns_left.state == LightState.YELLOW
    assert ns_left.remaining == 2.0
    assert ns_straight.state == LightState.RED
    assert ns_straight.remaining == 2.0
    assert ew_left.state == LightState.RED
    assert ew_straight.state == LightState.RED


def test_timing_red_durations_are_movement_specific():
    timing = make_controller().timing
    assert timing.ns_left_red == 109.0
    assert timing.ns_straight_red == 89.0
    assert timing.ew_left_red == 109.0
    assert timing.ew_straight_red == 89.0


def test_timing_update_changes_current_duration_without_resetting_start():
    controller = make_controller()
    new_timing = TimingConfig(
        ns_straight_green=45,
        ns_left_green=25,
        ew_straight_green=42,
        ew_left_green=22,
        yellow=3,
    )
    controller.apply_timing(new_timing)

    assert controller.started_at == 0.0
    assert controller.remaining(0.0) == 25.0
