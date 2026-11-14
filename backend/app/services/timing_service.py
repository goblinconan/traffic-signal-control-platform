"""配时校验与待生效管理。
输入：TimingConfig、当前生效配时。
输出：校验结果、待生效配时。
依赖：models/signal.py。
调用方：api/routes/signal.py。
"""
from __future__ import annotations

from app.models.signal import TimingConfig


class TimingError(ValueError):
    pass


class TimingService:
    def __init__(self, initial: TimingConfig) -> None:
        self._active = initial
        self._pending: TimingConfig | None = None

    @property
    def active(self) -> TimingConfig:
        return self._active

    @property
    def pending(self) -> TimingConfig | None:
        return self._pending

    def validate(self, candidate: TimingConfig) -> None:
        # Pydantic 已校验字段级和红灯级；这里预留业务级校验入口
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

    def submit(self, candidate: TimingConfig) -> TimingConfig:
        self.validate(candidate)
        self._pending = candidate
        return candidate

    def promote_pending_if_any(self) -> TimingConfig | None:
        """在新相位开始时调用；把 pending 提升为 active。"""
        if self._pending is None:
            return None
        self._active = self._pending
        self._pending = None
        return self._active
    