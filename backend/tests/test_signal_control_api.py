from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes.signal import router
from app.models.signal import ControlMode
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
