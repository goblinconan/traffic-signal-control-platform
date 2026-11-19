"""B5.1 持久化默认配时与 MANUAL 命名方案库（单进程文件存储）。"""
from __future__ import annotations

import json
import os
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.models.signal import TimingConfig


class TimingPlanStoreError(RuntimeError):
    pass


class TimingPlanStore:
    """JSON 原子写入；适用于当前单实例/单 worker 部署。"""

    def __init__(self, path: Path | None = None) -> None:
        backend_root = Path(__file__).resolve().parents[2]
        self.path = path or backend_root / "data" / "timing_plans.json"
        self._lock = threading.RLock()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _read(self) -> dict[str, Any]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise TimingPlanStoreError(f"配时方案文件不可读取或 JSON 损坏：{exc}") from exc
        if not isinstance(data, dict) or type(data.get("schema_version")) is not int or data.get("schema_version") != 1:
            raise TimingPlanStoreError("配时方案文件版本不兼容，拒绝自动覆盖")
        tls_id = data.get("tls_id")
        if not isinstance(tls_id, str) or not tls_id.strip():
            raise TimingPlanStoreError("配时方案文件缺少有效 tls_id")
        default_timing = data.get("default_timing")
        plans = data.get("plans")
        if not isinstance(default_timing, dict) or not isinstance(plans, list):
            raise TimingPlanStoreError("配时方案文件结构不完整")
        self._validate_timestamp(data.get("default_created_at"), "default_created_at")
        try:
            TimingConfig.model_validate(default_timing)
        except Exception as exc:
            raise TimingPlanStoreError(f"服务器默认配时无效：{exc}") from exc

        seen_ids: set[str] = set()
        seen_names: set[str] = set()
        required = {"plan_id", "name", "config", "created_at", "updated_at"}
        for index, plan in enumerate(plans):
            if not isinstance(plan, dict) or set(plan) != required:
                raise TimingPlanStoreError(f"第 {index + 1} 个方案记录结构不完整")
            plan_id = plan.get("plan_id")
            name = plan.get("name")
            if not isinstance(plan_id, str):
                raise TimingPlanStoreError(f"第 {index + 1} 个方案缺少有效 plan_id")
            try:
                uuid.UUID(plan_id)
            except (ValueError, AttributeError) as exc:
                raise TimingPlanStoreError(f"第 {index + 1} 个方案 plan_id 无效") from exc
            if plan_id in seen_ids:
                raise TimingPlanStoreError("方案库包含重复 plan_id")
            seen_ids.add(plan_id)
            if not isinstance(name, str) or not name.strip() or len(name) > 60 or name != " ".join(name.split()):
                raise TimingPlanStoreError(f"第 {index + 1} 个方案名称无效")
            folded = name.casefold()
            if folded in seen_names:
                raise TimingPlanStoreError("方案库包含重复方案名称")
            seen_names.add(folded)
            if not isinstance(plan.get("config"), dict):
                raise TimingPlanStoreError(f"第 {index + 1} 个方案缺少配时配置")
            try:
                TimingConfig.model_validate(plan["config"])
            except Exception as exc:
                raise TimingPlanStoreError(f"第 {index + 1} 个方案配时无效：{exc}") from exc
            self._validate_timestamp(plan.get("created_at"), f"plans[{index}].created_at")
            self._validate_timestamp(plan.get("updated_at"), f"plans[{index}].updated_at")
        return data

    @staticmethod
    def _validate_timestamp(value: Any, field_name: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise TimingPlanStoreError(f"配时方案文件字段 {field_name} 缺少时间戳")
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise TimingPlanStoreError(f"配时方案文件字段 {field_name} 时间戳无效") from exc

    def _write(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=self.path.name + ".", suffix=".tmp", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
                json.dump(data, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_name, self.path)
        except Exception:
            try:
                os.unlink(temp_name)
            except OSError:
                pass
            raise

    def initialize(self, tls_id: str, initial: TimingConfig) -> TimingConfig:
        """首次启动冻结服务器默认值；后续启动始终读取冻结值。"""
        with self._lock:
            try:
                data = self._read()
            except FileNotFoundError:
                data = {
                    "schema_version": 1,
                    "tls_id": tls_id,
                    "default_timing": initial.model_dump(mode="json"),
                    "default_created_at": self._now(),
                    "plans": [],
                }
                self._write(data)
                return initial
            if data["tls_id"] != tls_id:
                raise TimingPlanStoreError(
                    f"方案文件属于 tls_id={data['tls_id']}，当前为 {tls_id}；拒绝混用"
                )
            try:
                return TimingConfig.model_validate(data["default_timing"])
            except Exception as exc:
                raise TimingPlanStoreError(f"服务器默认配时无效：{exc}") from exc

    def snapshot(self, tls_id: str) -> dict[str, Any]:
        with self._lock:
            data = self._read()
            self._check_tls(data, tls_id)
            return {
                "default_timing": data["default_timing"],
                "default_created_at": data["default_created_at"],
                "plans": data["plans"],
            }

    @staticmethod
    def _check_tls(data: dict[str, Any], tls_id: str) -> None:
        if data["tls_id"] != tls_id:
            raise TimingPlanStoreError("tls_id 不匹配")

    def save(self, tls_id: str, name: str, config: TimingConfig) -> dict[str, Any]:
        clean_name = " ".join(name.split())
        if not clean_name or len(clean_name) > 60:
            raise ValueError("方案名称必须为 1–60 个字符")
        with self._lock:
            data = self._read()
            self._check_tls(data, tls_id)
            if any(p["name"].casefold() == clean_name.casefold() for p in data["plans"]):
                raise ValueError("已存在同名方案，请更换名称")
            plan = {
                "plan_id": str(uuid.uuid4()),
                "name": clean_name,
                "config": config.model_dump(mode="json"),
                "created_at": self._now(),
                "updated_at": self._now(),
            }
            data["plans"].append(plan)
            self._write(data)
            return plan

    def delete(self, tls_id: str, plan_id: str) -> None:
        with self._lock:
            data = self._read()
            self._check_tls(data, tls_id)
            original = len(data["plans"])
            data["plans"] = [p for p in data["plans"] if p.get("plan_id") != plan_id]
            if len(data["plans"]) == original:
                raise KeyError("未找到指定配时方案")
            self._write(data)

    def get_plan(self, tls_id: str, plan_id: str) -> tuple[dict[str, Any], TimingConfig]:
        with self._lock:
            data = self._read()
            self._check_tls(data, tls_id)
            for plan in data["plans"]:
                if plan.get("plan_id") == plan_id:
                    try:
                        return plan, TimingConfig.model_validate(plan["config"])
                    except Exception as exc:
                        raise TimingPlanStoreError(f"方案配置无效：{exc}") from exc
        raise KeyError("未找到指定配时方案")
