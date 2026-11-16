
/** 前后端共享的信号状态、配时和 SUMO 几何数据类型。 */
export type PhaseId =
  | "NS_LEFT"
  | "NS_LEFT_YELLOW"
  | "NS_STRAIGHT"
  | "NS_STRAIGHT_YELLOW"
  | "EW_LEFT"
  | "EW_LEFT_YELLOW"
  | "EW_STRAIGHT"
  | "EW_STRAIGHT_YELLOW"
  | "ALL_RED";

export type ControlMode = "AUTO" | "MANUAL";

export type ControlStatus = "ENABLED" | "DISABLING" | "DISABLED";

export interface SignalControlState {
  tls_id: string;
  control_status: ControlStatus;
  control_mode: ControlMode;
  phase_id: PhaseId;
  pending_mode: ControlMode | null;
  pending_manual_phase: PhaseId | null;
}

export type LightState = "G" | "y" | "r";

export interface TimingConfig {
  ns_straight_green: number;
  ns_left_green: number;
  ew_straight_green: number;
  ew_left_green: number;
  yellow: number;
}

export interface DirectionState {
  state: LightState;
  remaining: number;
  countdown_visible: boolean;
}

export interface SignalSnapshot {
  tls_id: string;
  phase_id: PhaseId;
  control_mode: ControlMode;
  control_status: ControlStatus;
  ns_straight: DirectionState;
  ns_left: DirectionState;
  ew_straight: DirectionState;
  ew_left: DirectionState;
  timing: TimingConfig;
}

/** SUMO 车辆实时快照，尺寸单位为米。 */
export interface VehicleSnapshot {
  id: string;
  x: number;
  y: number;
  angle: number;
  speed: number;
  length: number;
  width: number;
}

export interface NetworkPoint {
  x: number;
  y: number;
}

export interface NetworkLane {
  id: string;
  index: number;
  width: number;
  speed: number;
  shape: NetworkPoint[];
}

export interface NetworkEdge {
  id: string;
  from: string;
  to: string;
  function: string;
  lanes: NetworkLane[];
}

export interface NetworkJunction {
  id: string;
  type: string;
  x: number;
  y: number;
  shape: NetworkPoint[];
}

export interface InternalLane {
  id: string;
  width: number;
  shape: NetworkPoint[];
}

export interface NetworkGeometry {
  junctions: NetworkJunction[];
  edges: NetworkEdge[];
  internal_lanes: InternalLane[];
  bounds: {
    conv_boundary: string;
    orig_boundary: string;
  };
}

export interface SimulationUpdate {
  type: "simulation_update";
  simulation_time: number;
  simulation_status: string;
  signal: SignalSnapshot;
  vehicles: VehicleSnapshot[];
  network?: NetworkGeometry;
}
