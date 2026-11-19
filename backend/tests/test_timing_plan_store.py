import json

import pytest
from pydantic import ValidationError

from app.models.signal import TimingConfig
from app.services.timing_plan_store import TimingPlanStore, TimingPlanStoreError


def test_default_is_frozen_and_plans_are_separate(tmp_path):
    path = tmp_path / "timing_plans.json"
    store = TimingPlanStore(path)
    first = TimingConfig()
    frozen = store.initialize("tls-a", first)
    changed = TimingConfig(ew_left_green=25)
    assert store.initialize("tls-a", changed) == frozen
    plan = store.save("tls-a", "晚高峰", changed)
    assert plan["name"] == "晚高峰"
    snapshot = store.snapshot("tls-a")
    assert snapshot["default_timing"] == frozen.model_dump(mode="json")
    assert len(snapshot["plans"]) == 1


def test_duplicate_names_are_case_insensitive(tmp_path):
    store = TimingPlanStore(tmp_path / "plans.json")
    store.initialize("tls-a", TimingConfig())
    store.save("tls-a", "Peak", TimingConfig())
    with pytest.raises(ValueError):
        store.save("tls-a", " peak ", TimingConfig())


def test_tls_mismatch_fails_closed(tmp_path):
    store = TimingPlanStore(tmp_path / "plans.json")
    store.initialize("tls-a", TimingConfig())
    with pytest.raises(TimingPlanStoreError):
        store.initialize("tls-b", TimingConfig())


def test_corrupt_json_fails_closed(tmp_path):
    path = tmp_path / "plans.json"
    path.write_text("{broken", encoding="utf-8")
    with pytest.raises(TimingPlanStoreError):
        TimingPlanStore(path).initialize("tls-a", TimingConfig())


def test_store_creates_parent_directory(tmp_path):
    path = tmp_path / "nested" / "data" / "timing_plans.json"
    store = TimingPlanStore(path)
    store.initialize("tls-a", TimingConfig())
    assert path.is_file()


def test_delete_removes_only_named_plan(tmp_path):
    store = TimingPlanStore(tmp_path / "plans.json")
    store.initialize("tls-a", TimingConfig())
    first = store.save("tls-a", "A", TimingConfig())
    second = store.save("tls-a", "B", TimingConfig(ew_left_green=25))
    store.delete("tls-a", first["plan_id"])
    plans = store.snapshot("tls-a")["plans"]
    assert [item["plan_id"] for item in plans] == [second["plan_id"]]


def test_timing_config_rejects_green_at_lower_bound():
    # TimingConfig 的模型级 validator 是配时方案库与既有 PUT 配时 API 的共同校验入口。
    with pytest.raises(ValidationError):
        TimingConfig(
            ns_left_green=8,
        )


def test_malformed_plan_record_fails_closed(tmp_path):
    path = tmp_path / "plans.json"
    store = TimingPlanStore(path)
    store.initialize("tls-a", TimingConfig())
    data = json.loads(path.read_text(encoding="utf-8"))
    data["plans"].append({"plan_id": "broken"})
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(TimingPlanStoreError):
        store.snapshot("tls-a")


def test_invalid_default_timestamp_fails_closed(tmp_path):
    path = tmp_path / "plans.json"
    store = TimingPlanStore(path)
    store.initialize("tls-a", TimingConfig())
    data = json.loads(path.read_text(encoding="utf-8"))
    data["default_created_at"] = "not-a-timestamp"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(TimingPlanStoreError):
        store.snapshot("tls-a")


def test_invalid_saved_plan_config_fails_closed(tmp_path):
    path = tmp_path / "plans.json"
    store = TimingPlanStore(path)
    store.initialize("tls-a", TimingConfig())
    plan = store.save("tls-a", "晚高峰", TimingConfig())
    data = json.loads(path.read_text(encoding="utf-8"))
    data["plans"][0]["config"]["unexpected"] = 1
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(TimingPlanStoreError):
        store.get_plan("tls-a", plan["plan_id"])
