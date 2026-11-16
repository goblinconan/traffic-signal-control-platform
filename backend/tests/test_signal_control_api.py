from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes.signal import router
from app.models.signal import ControlMode, TimingConfig
from app.simulation.lifecycle import LifecycleError


class FakeLifecycle:
    def __init__(self):
        self.error = None

    async def run_control_action(self, function):
        if self.error is not None:
            raise self.error
        return function()


class FakeSignalService:
    def __init__(self):
        self.settings = SimpleNamespace(tls_id="intersection_0")
        self.state = {
            "tls_id": "intersection_0",
            "control_status": "ENABLED",
            "control_mode": "AUTO",
            "phase_id": "NS_LEFT",
            "pending_mode": None,
            "pending_manual_phase": None,
        }
        self.enabled_error = None
        self.mode_error = None
        self.timing_state = {
            "active": TimingConfig().model_dump(),
            "pending": None,
            "timing_version": 1,
            "pending_timing_version": None,
            "computed": {
                "cycle_length": 132.0,
                "ns_left_red": 109.0,
                "ns_straight_red": 89.0,
                "ew_left_red": 109.0,
                "ew_straight_red": 89.0,
            },
        }

    def timing_snapshot(self):
        return self.timing_state

    def submit_timing(self, candidate):
        self.timing_state["pending"] = candidate.model_dump()
        self.timing_state["pending_timing_version"] = 2
        return {
            "accepted": True,
            "status": "queued",
            "effective": "next_cycle_boundary",
            **self.timing_state,
        }

    def manual_switch(self, target):
        return True, "accepted_after_safe_all_red"

    @property
    def timing(self):
        class TimingView:
            def __init__(self, state):
                self._state = state
                self.active = TimingConfig()

            def snapshot(self):
                return self._state

        return TimingView(self.timing_state)

    def control_state(self):
        return dict(self.state)

    def request_control_enabled(self, enabled):
        if self.enabled_error is not None:
            raise self.enabled_error

        self.state["control_status"] = (
            "DISABLED" if not enabled else "ENABLED"
        )
        return self.control_state()

    def request_control_mode(self, mode):
        if self.mode_error is not None:
            raise self.mode_error

        self.state["control_mode"] = mode.value
        return self.control_state()


def make_client():
    app = FastAPI()
    app.include_router(router, prefix="/api")

    app.state.signal_service = FakeSignalService()
    app.state.lifecycle = FakeLifecycle()

    return TestClient(app), app


def test_get_control_reports_independent_mode_and_enabled_state():
    client, _ = make_client()

    with client:
        response = client.get(
            "/api/signals/intersection_0/control"
        )

    assert response.status_code == 200
    assert response.json()["control_status"] == "ENABLED"
    assert response.json()["control_mode"] == "AUTO"


def test_put_control_enabled_and_mode_use_distinct_endpoints():
    client, _ = make_client()

    with client:
        disabled = client.put(
            "/api/signals/intersection_0/control/enabled",
            json={"enabled": False},
        )
        manual = client.put(
            "/api/signals/intersection_0/control/mode",
            json={"mode": "MANUAL"},
        )

    assert disabled.status_code == 200
    assert disabled.json()["control_status"] == "DISABLED"

    assert manual.status_code == 200
    assert manual.json()["control_mode"] == ControlMode.MANUAL.value


def test_get_control_rejects_unknown_tls_id():
    client, _ = make_client()

    with client:
        response = client.get(
            "/api/signals/unknown_tls/control"
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "unknown tls_id"


def test_put_control_enabled_rejects_unknown_tls_id():
    client, _ = make_client()

    with client:
        response = client.put(
            "/api/signals/unknown_tls/control/enabled",
            json={"enabled": False},
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "unknown tls_id"


def test_put_control_mode_rejects_invalid_mode():
    client, _ = make_client()

    with client:
        response = client.put(
            "/api/signals/intersection_0/control/mode",
            json={"mode": "INVALID"},
        )

    assert response.status_code == 422


def test_put_control_enabled_maps_lifecycle_error_status():
    client, app = make_client()
    app.state.lifecycle.error = LifecycleError(
        "simulation is not running",
        503,
    )

    with client:
        response = client.put(
            "/api/signals/intersection_0/control/enabled",
            json={"enabled": False},
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "simulation is not running"


def test_put_control_mode_maps_value_error_to_conflict():
    client, app = make_client()
    app.state.signal_service.mode_error = ValueError(
        "mode transition is invalid"
    )

    with client:
        response = client.put(
            "/api/signals/intersection_0/control/mode",
            json={"mode": "MANUAL"},
        )

    assert response.status_code == 409
    assert response.json()["detail"] == "mode transition is invalid"


def test_get_timing_returns_active_pending_and_computed_red():
    client, _ = make_client()
    with client:
        response = client.get("/api/signals/intersection_0/timing")
    assert response.status_code == 200
    body = response.json()
    assert body["timing_version"] == 1
    assert body["active"]["ns_left_yellow"] == 3
    assert body["computed"]["ns_left_red"] == 109


def test_put_timing_accepts_eight_independent_green_yellow_values():
    client, _ = make_client()
    payload = {
        "ns_left_green": 22, "ns_left_yellow": 4,
        "ns_straight_green": 42, "ns_straight_yellow": 2,
        "ew_left_green": 23, "ew_left_yellow": 5,
        "ew_straight_green": 43, "ew_straight_yellow": 3,
    }
    with client:
        response = client.put(
            "/api/signals/intersection_0/timing",
            json=payload,
        )
    assert response.status_code == 200
    assert response.json()["accepted"] is True
    assert response.json()["effective"] == "next_cycle_boundary"
    assert response.json()["pending"]["ns_left_yellow"] == 4


def test_put_timing_rejects_invalid_yellow_and_unknown_fields():
    client, _ = make_client()
    invalid_yellow = {
        "ns_left_green": 22, "ns_left_yellow": 0,
        "ns_straight_green": 42, "ns_straight_yellow": 3,
        "ew_left_green": 23, "ew_left_yellow": 3,
        "ew_straight_green": 43, "ew_straight_yellow": 3,
    }
    with client:
        invalid = client.put(
            "/api/signals/intersection_0/timing",
            json=invalid_yellow,
        )
        unknown = client.put(
            "/api/signals/intersection_0/timing",
            json={**TimingConfig().model_dump(), "yellow": 3},
        )
        incomplete = client.put(
            "/api/signals/intersection_0/timing",
            json={key: value for key, value in TimingConfig().model_dump().items()
                  if key != "ew_straight_yellow"},
        )
    assert invalid.status_code == 422
    assert unknown.status_code == 422
    assert incomplete.status_code == 422


def test_manual_phase_endpoint_returns_queued_acceptance():
    client, _ = make_client()
    with client:
        response = client.post(
            "/api/signals/intersection_0/phases/switch",
            json={"target_phase": "EW_LEFT"},
        )
    assert response.status_code == 200
    assert response.json() == {
        "accepted": True,
        "status": "queued",
        "reason": "accepted_after_safe_all_red",
    }
