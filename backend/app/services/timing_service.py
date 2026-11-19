
"""配时校验、版本管理与待生效方案。
输入：TimingConfig、当前生效配时及方案来源。
输出：当前/待生效配时、版本和方案来源。
依赖：models/signal.py。
调用方：SignalService、API routes。
"""
from __future__ import annotations

from app.models.signal import TimingConfig


class TimingError(ValueError):
    pass


DEFAULT_TIMING_SOURCE = {
    "kind": "default",
    "name": "服务器默认配时",
    "plan_id": None,
}

CUSTOM_TIMING_SOURCE = {
    "kind": "custom",
    "name": "自定义配时",
    "plan_id": None,
}


class TimingService:
    def __init__(self, initial: TimingConfig) -> None:
        self._active = initial
        self._pending: TimingConfig | None = None
        self._version = 1
        self._pending_version: int | None = None

        # 方案来源与配时状态同步管理。
        self._active_source = dict(DEFAULT_TIMING_SOURCE)
        self._pending_source: dict | None = None

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

    @property
    def active_source(self) -> dict:
        return dict(self._active_source)

    @property
    def pending_source(self) -> dict | None:
        return (
            dict(self._pending_source)
            if self._pending_source is not None
            else None
        )

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

    def submit(
        self,
        candidate: TimingConfig,
        source: dict | None = None,
    ) -> TimingConfig | None:
        """登记待生效方案；提交当前 active 可撤销尚未生效的 pending。

        source 是本次提交配时的来源信息。
        只有来源明确传入时，才允许在配时数值不变的情况下更新
        Active 来源；不传 source 的旧调用保持原有来源。
        """
        self.validate(candidate)

        if candidate == self._active:
            self._pending = None
            self._pending_version = None
            self._pending_source = None

            if source is not None:
                self._active_source = dict(source)

            return None

        self._pending = candidate
        self._pending_version = self._version + 1
        self._pending_source = (
            dict(source)
            if source is not None
            else dict(CUSTOM_TIMING_SOURCE)
        )
        return candidate

    def promote_pending_if_any(self) -> TimingConfig | None:
        """只允许由 SignalService 在安全边界调用。"""
        if self._pending is None:
            return None

        self._active = self._pending
        self._version = self._pending_version or (self._version + 1)

        if self._pending_source is not None:
            self._active_source = dict(self._pending_source)

        self._pending = None
        self._pending_version = None
        self._pending_source = None

        return self._active

    def snapshot(self) -> dict:
        return {
            "active": self._active.model_dump(),
            "pending": self._pending.model_dump() if self._pending else None,
            "timing_version": self._version,
            "pending_timing_version": self._pending_version,
            "active_source": dict(self._active_source),
            "pending_source": (
                dict(self._pending_source)
                if self._pending_source is not None
                else None
            ),
            "computed": {
                "cycle_length": self._active.cycle_length,
                "ns_left_red": self._active.ns_left_red,
                "ns_straight_red": self._active.ns_straight_red,
                "ew_left_red": self._active.ew_left_red,
                "ew_straight_red": self._active.ew_straight_red,
            },
        }
