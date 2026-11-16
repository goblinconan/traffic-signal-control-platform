
"""信号领域模型：定义八阶段、灯色、配时及快照数据。
输入：API 请求、配置文件和控制器计算结果。
输出：经过 Pydantic 校验的信号模型。
依赖：Pydantic。
调用方：controllers、services、API routes。
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, model_validator


class PhaseId(str, Enum):
    """四类受保护业务阶段及其黄灯过渡阶段，顺序与控制器循环一致。"""

    NS_LEFT = "NS_LEFT"
    NS_LEFT_YELLOW = "NS_LEFT_YELLOW"
    NS_STRAIGHT = "NS_STRAIGHT"
    NS_STRAIGHT_YELLOW = "NS_STRAIGHT_YELLOW"
    EW_LEFT = "EW_LEFT"
    EW_LEFT_YELLOW = "EW_LEFT_YELLOW"
    EW_STRAIGHT = "EW_STRAIGHT"
    EW_STRAIGHT_YELLOW = "EW_STRAIGHT_YELLOW"
    ALL_RED = "ALL_RED"


class ControlMode(str, Enum):
    AUTO = "AUTO"
    MANUAL = "MANUAL"


class ControlStatus(str, Enum):
    ENABLED = "ENABLED"
    DISABLING = "DISABLING"
    DISABLED = "DISABLED"


class LightState(str, Enum):
    GREEN = "G"
    YELLOW = "y"
    RED = "r"


class TimingConfig(BaseModel):
    ns_straight_green: float = Field(default=40, gt=8)
    ns_left_green: float = Field(default=20, gt=8)
    ew_straight_green: float = Field(default=40, gt=8)
    ew_left_green: float = Field(default=20, gt=8)
    yellow: float = Field(default=3, gt=0)

    @property
    def ns_left_red(self) -> float:
        return (
            self.ns_straight_green
            + self.ew_left_green
            + self.ew_straight_green
            + self.yellow * 3
        )

    @property
    def ns_straight_red(self) -> float:
        return (
            self.ns_left_green
            + self.ew_left_green
            + self.ew_straight_green
            + self.yellow * 3
        )

    @property
    def ew_left_red(self) -> float:
        return (
            self.ew_straight_green
            + self.ns_left_green
            + self.ns_straight_green
            + self.yellow * 3
        )

    @property
    def ew_straight_red(self) -> float:
        return (
            self.ew_left_green
            + self.ns_left_green
            + self.ns_straight_green
            + self.yellow * 3
        )

    @model_validator(mode="after")
    def check_red(self) -> TimingConfig:
        red_durations = {
            "南北左转": self.ns_left_red,
            "南北直行": self.ns_straight_red,
            "东西左转": self.ew_left_red,
            "东西直行": self.ew_straight_red,
        }
        for name, duration in red_durations.items():
            if duration <= 10:
                raise ValueError(f"{name}红灯总时长必须 >10s")
        return self


class DirectionState(BaseModel):
    state: LightState
    remaining: float
    countdown_visible: bool


class SignalSnapshot(BaseModel):
    tls_id: str
    phase_id: PhaseId
    control_mode: ControlMode = ControlMode.AUTO
    control_status: ControlStatus = ControlStatus.ENABLED
    ns_straight: DirectionState
    ns_left: DirectionState
    ew_straight: DirectionState
    ew_left: DirectionState
    timing: TimingConfig
