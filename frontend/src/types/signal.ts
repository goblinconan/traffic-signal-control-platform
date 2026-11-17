/** B4 REST / WebSocket 统一状态协议及静态 SUMO 路网类型。 */
export type PhaseId =
  | "NS_LEFT" | "NS_LEFT_YELLOW"
  | "NS_STRAIGHT" | "NS_STRAIGHT_YELLOW"
  | "EW_LEFT" | "EW_LEFT_YELLOW"
  | "EW_STRAIGHT" | "EW_STRAIGHT_YELLOW"
  | "ALL_RED";

export type ControlMode = "AUTO" | "MANUAL";
export type ControlStatus = "ENABLED" | "DISABLING" | "DISABLED";
export type SimulationStatus = "STOPPED" | "STARTING" | "RUNNING" | "STOPPING" | "FAILED";
export type LightState = "G" | "y" | "r";

export interface TimingConfig {
  ns_left_green: number; ns_left_yellow: number;
  ns_straight_green: number; ns_straight_yellow: number;
  ew_left_green: number; ew_left_yellow: number;
  ew_straight_green: number; ew_straight_yellow: number;
}

export interface DirectionState {
  state: LightState; remaining: number; countdown_visible: boolean;
}
export interface SignalGroupState extends DirectionState {
  group_id: "NS_LEFT" | "NS_STRAIGHT" | "EW_LEFT" | "EW_STRAIGHT";
}
export interface RightTurnState {
  approach: "N" | "S" | "E" | "W";
  state: "PERMISSIVE_YIELD";
  signal_state: "g" | "r";
}
export interface SignalControlState {
  tls_id: string; control_status: ControlStatus; enabled: boolean;
  control_mode: ControlMode; phase_id: PhaseId; phase_index: number | null;
  remaining: number; countdown_visible: boolean; next_phase: PhaseId | null;
  pending_mode: ControlMode | null; pending_manual_phase: PhaseId | null;
  groups: SignalGroupState[]; right_turns: RightTurnState[];
}
export interface TimingState {
  active: TimingConfig; pending: TimingConfig | null;
  timing_version: number; pending_timing_version: number | null;
  computed: { cycle_length: number; ns_left_red: number; ns_straight_red: number; ew_left_red: number; ew_straight_red: number };
}
export interface VehicleSnapshot {
  id: string; x: number; y: number; angle: number; speed: number; length: number; width: number;
}
export interface NetworkPoint { x: number; y: number; }
export interface NetworkLane { id: string; index: number; width: number; speed: number; shape: NetworkPoint[]; }
export interface NetworkEdge { id: string; from: string; to: string; function: string; lanes: NetworkLane[]; }
export interface NetworkJunction { id: string; type: string; x: number; y: number; shape: NetworkPoint[]; }
export interface InternalLane { id: string; width: number; shape: NetworkPoint[]; }
export interface NetworkGeometry {
  network_version: string; junctions: NetworkJunction[]; edges: NetworkEdge[];
  internal_lanes: InternalLane[]; bounds: { conv_boundary: string; orig_boundary: string };
}
export interface NetworkResource { intersection_id: string; network_version: string; geometry: NetworkGeometry; }
export interface SimulationState {
  schema_version: "1.0"; type: "simulation_snapshot" | "simulation_update";
  sequence: number; simulation_time: number; simulation_status: SimulationStatus;
  sumo_connected: boolean; step_index: number; process_alive: boolean; last_error: string | null;
  signal_control: SignalControlState; timing: TimingState; vehicles: VehicleSnapshot[];
  network_version: string; network?: NetworkGeometry;
}
/** 兼容路口 SVG 组件的 B4 统一消息类型别名。 */
export type SimulationUpdate = SimulationState;
