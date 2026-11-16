"""配时校验、版本管理与待生效方案。
输入：TimingConfig、当前生效配时。
输出：当前/待生效配时及版本。
依赖：models/signal.py。
调用方：SignalService、API routes。
"""
from __future__ import annotations

from app.models.signal import TimingConfig


class TimingError(ValueError):
    pass


class TimingService:
    def __init__(self, initial: TimingConfig) -> None:
        self._active = initial
        self._pending: TimingConfig | None = None
        self._version = 1
        self._pending_version: int | None = None

    @property
    def active(self) -> TimingConfig:
        return self._active

    @property
    def pending(self) -> TimingConfig | None:
        return self._pending

    @property
    def version(self) -> int:
        return self._version

    @property
    def pending_version(self) -> int | None:
        return self._pending_version

    def validate(self, candidate: TimingConfig) -> None:
        red_durations = {
            "南北左转": candidate.ns_left_red,
            "南北直行": candidate.ns_straight_red,
            "东西左转": candidate.ew_left_red,
            "东西直行": candidate.ew_straight_red,
        }
        invalid = [
            f"{name}={duration:g}s"
            for name, duration in red_durations.items()
            if duration <= 10
        ]
        if invalid:
            raise TimingError("红灯总时长必须 >10s：" + "、".join(invalid))

    def submit(self, candidate: TimingConfig) -> TimingConfig | None:
        """登记待生效方案；提交当前 active 可撤销尚未生效的 pending。"""
        self.validate(candidate)
        if candidate == self._active:
            self._pending = None
            self._pending_version = None
            return None
        self._pending = candidate
        self._pending_version = self._version + 1
        return candidate

    def promote_pending_if_any(self) -> TimingConfig | None:
        """只允许由 SignalService 在安全边界调用。"""
        if self._pending is None:
            return None
        self._active = self._pending
        self._version = self._pending_version or (self._version + 1)
        self._pending = None
        self._pending_version = None
        return self._active

    def snapshot(self) -> dict:
        return {
            "active": self._active.model_dump(),
            "pending": self._pending.model_dump() if self._pending else None,
            "timing_version": self._version,
            "pending_timing_version": self._pending_version,
            "computed": {
                "cycle_length": self._active.cycle_length,
                "ns_left_red": self._active.ns_left_red,
                "ns_straight_red": self._active.ns_straight_red,
                "ew_left_red": self._active.ew_left_red,
                "ew_straight_red": self._active.ew_straight_red,
            },
        }
