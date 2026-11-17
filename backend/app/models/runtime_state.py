"""B4 统一运行状态协议模型。
输入：仿真生命周期、信号控制器、配时服务及 SUMO 车辆快照。
输出：REST 与 WebSocket 共用的 Pydantic 状态契约。
依赖：Pydantic 与信号领域枚举。
调用方：state_service、REST routes、WebSocket。
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.signal import ControlMode, ControlStatus, PhaseId, TimingConfig
from app.simulation.lifecycle import SimulationStatus


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SignalGroupState(StrictModel):
    group_id: Literal["NS_LEFT", "NS_STRAIGHT", "EW_LEFT", "EW_STRAIGHT"]
    state: Literal["G", "y", "r"]
    remaining: float = Field(ge=0)
    countdown_visible: bool


class RightTurnState(StrictModel):
    approach: Literal["N", "S", "E", "W"]
    state: Literal["PERMISSIVE_YIELD"]
    signal_state: Literal["g", "r"]


class VehicleState(StrictModel):
    id: str
    x: float
    y: float
    angle: float
    speed: float = Field(ge=0)
    length: float = Field(gt=0)
    width: float = Field(gt=0)


class ComputedTiming(StrictModel):
    cycle_length: float
    ns_left_red: float
    ns_straight_red: float
    ew_left_red: float
    ew_straight_red: float


class TimingState(StrictModel):
    active: TimingConfig
    pending: TimingConfig | None
    timing_version: int = Field(ge=1)
    pending_timing_version: int | None
    computed: ComputedTiming


class SignalControlState(StrictModel):
    tls_id: str
    control_status: ControlStatus
    enabled: bool
    control_mode: ControlMode
    phase_id: PhaseId
    phase_index: int | None = Field(ge=0, le=7)
    remaining: float = Field(ge=0)
    countdown_visible: bool
    next_phase: PhaseId | None
    pending_mode: ControlMode | None
    pending_manual_phase: PhaseId | None
    groups: list[SignalGroupState]
    right_turns: list[RightTurnState]


class RuntimeStateMessage(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    type: Literal["simulation_snapshot", "simulation_update"]
    sequence: int = Field(ge=1)
    simulation_time: float = Field(ge=0)
    simulation_status: SimulationStatus
    sumo_connected: bool
    step_index: int = Field(ge=0)
    process_alive: bool
    last_error: str | None
    signal_control: SignalControlState
    timing: TimingState
    vehicles: list[VehicleState]
    network_version: str


class NetworkResource(StrictModel):
    intersection_id: str
    network_version: str
    geometry: dict
