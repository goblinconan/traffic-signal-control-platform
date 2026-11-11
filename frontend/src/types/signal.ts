
export type PhaseId =
  | "NS_STRAIGHT" | "NS_STRAIGHT_YELLOW"
  | "NS_LEFT" | "NS_LEFT_YELLOW"
  | "EW_STRAIGHT" | "EW_STRAIGHT_YELLOW"
  | "EW_LEFT" | "EW_LEFT_YELLOW";

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

/** SUMO 路网中的一个几何坐标点。 */
export interface NetworkPoint {
  x: number;
  y: number;
}

/** SUMO 路网中的车道。 */
export interface NetworkLane {
  id: string;
  index: number;
  width: number;
  speed: number;
  shape: NetworkPoint[];
}

/** SUMO 路网中的外部道路。 */
export interface NetworkEdge {
  id: string;
  from: string;
  to: string;
  function: string;
  lanes: NetworkLane[];
}

/** SUMO 路口节点。 */
export interface NetworkJunction {
  id: string;
  type: string;
  x: number;
  y: number;
  shape: NetworkPoint[];
}

/** SUMO 路口内部连接车道。 */
export interface InternalLane {
  id: string;
  width: number;
  shape: NetworkPoint[];
}

/** SUMO 静态路网几何。 */
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
  /** 首次 WebSocket 消息包含，后续动态消息不重复发送。 */
  network?: NetworkGeometry;
}
