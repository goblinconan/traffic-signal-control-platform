
import type {
  DirectionState,
  NetworkPoint,
  SimulationUpdate,
} from "../../types/signal";

const VIEW = 600;
const PADDING = 24;
const WORLD_MIN = 0;
const WORLD_MAX = 400;
const WORLD_SIZE = WORLD_MAX - WORLD_MIN;
const SCALE = (VIEW - PADDING * 2) / WORLD_SIZE;

const ROAD_COLOR = "#2d2d44";
const LANE_COLOR = "#777";
const ROAD_EDGE_COLOR = "#171725";
const JUNCTION_COLOR = "#2d2d44";

function toScreen(point: NetworkPoint) {
  return {
    x: PADDING + (point.x - WORLD_MIN) * SCALE,
    y: VIEW - PADDING - (point.y - WORLD_MIN) * SCALE,
  };
}

function toPath(points: NetworkPoint[]) {
  if (points.length === 0) return "";

  return points
    .map((point, index) => {
      const p = toScreen(point);
      return `${index === 0 ? "M" : "L"} ${p.x} ${p.y}`;
    })
    .join(" ");
}

function getLaneDividerPath(
  current: NetworkPoint[],
  next: NetworkPoint[],
) {
  if (current.length !== next.length || current.length < 2) {
    return "";
  }

  const points = current.map((point, index) => ({
    x: (point.x + next[index].x) / 2,
    y: (point.y + next[index].y) / 2,
  }));

  return toPath(points);
}

function getJunctionShape(data: SimulationUpdate) {
  return data.network?.junctions.find(
    (junction) => junction.id === "intersection_0",
  )?.shape ?? [];
}

export function IntersectionView({
  data,
}: {
  data: SimulationUpdate | null;
}) {
  const signal = data?.signal_control;
  const group = (id: string) => signal?.groups.find((item) => item.group_id === id);
  const network = data?.network;

  const junctionShape = data ? getJunctionShape(data) : [];
  const junctionPath = toPath(junctionShape);

  return (
    <svg
      width="100%"
      height="100%"
      viewBox={`0 0 ${VIEW} ${VIEW}`}
      preserveAspectRatio="xMidYMid meet"
      style={{
        display: "block",
        background: "#1a1a2e",
        borderRadius: 12,
      }}
    >
      {/* 外部道路：根据 SUMO 真实车道宽度绘制 */}
      {network?.edges.flatMap((edge) =>
        edge.lanes.map((lane) => (
          <path
            key={lane.id}
            d={toPath(lane.shape)}
            fill="none"
            stroke={ROAD_COLOR}
            strokeWidth={lane.width * SCALE}
            strokeLinecap="butt"
            strokeLinejoin="round"
          />
        )),
      )}

      {/* 路口中心区域：使用 SUMO junction shape */}
      {junctionPath && (
        <path
          d={`${junctionPath} Z`}
          fill={JUNCTION_COLOR}
          stroke={ROAD_EDGE_COLOR}
          strokeWidth={1}
        />
      )}

      {/* 内部连接车道：绘制真实转弯轨迹 */}
      {network?.internal_lanes.map((lane) => (
        <path
          key={lane.id}
          d={toPath(lane.shape)}
          fill="none"
          stroke={ROAD_COLOR}
          strokeWidth={lane.width * SCALE}
          strokeLinecap="butt"
          strokeLinejoin="round"
        />
      ))}

      {/* 外部车道分隔线：绘制相邻车道中心线的中间位置 */}
      {network?.edges.flatMap((edge) =>
        edge.lanes.slice(0, -1).map((lane, index) => {
          const nextLane = edge.lanes[index + 1];
          const dividerPath = getLaneDividerPath(
            lane.shape,
            nextLane.shape,
          );

          if (!dividerPath) return null;

          return (
            <path
              key={`${lane.id}-divider`}
              d={dividerPath}
              fill="none"
              stroke={LANE_COLOR}
              strokeWidth={0.8}
              strokeDasharray="5 5"
              opacity={0.75}
            />
          );
        }),
      )}

      {/* 路口内部连接车道分隔线 */}
      {network?.internal_lanes.map((lane) => (
        <path
          key={`${lane.id}-marking`}
          d={toPath(lane.shape)}
          fill="none"
          stroke={LANE_COLOR}
          strokeWidth={0.6}
          strokeDasharray="3 5"
          opacity={0.45}
        />
      ))}

      {/* 路口轮廓 */}
      {junctionPath && (
        <path
          d={`${junctionPath} Z`}
          fill="none"
          stroke="#55556b"
          strokeWidth={1}
        />
      )}

      {/* 信号灯组：南北向 */}
      <g transform="translate(80, 80)">
        <text
          x={0}
          y={-60}
          textAnchor="middle"
          fill="#fff"
          fontSize="18"
          fontWeight="bold"
        >
          南北向
        </text>
        <SignalBox
          x={-20}
          y={-20}
          state={group("NS_STRAIGHT")}
          label="直行"
        />
        <SignalBox
          x={40}
          y={-20}
          state={group("NS_LEFT")}
          label="左转"
        />
      </g>

      {/* 信号灯组：东西向 */}
      <g transform="translate(520, 520)">
        <text
          x={0}
          y={-60}
          textAnchor="middle"
          fill="#fff"
          fontSize="18"
          fontWeight="bold"
        >
          东西向
        </text>
        <SignalBox
          x={-20}
          y={-20}
          state={group("EW_STRAIGHT")}
          label="直行"
        />
        <SignalBox
          x={40}
          y={-20}
          state={group("EW_LEFT")}
          label="左转"
        />
      </g>

      {/* 车辆：真实位置、长度、宽度和方向 */}
      {data?.vehicles.map((vehicle) => {
        // SUMO 返回的是车辆前保险杠中心，
        // 前端矩形需要使用车辆几何中心，因此沿行驶反方向退半个车身。
        const angleRad = (vehicle.angle * Math.PI) / 180;

        const centerX =
          vehicle.x - (vehicle.length / 2) * Math.sin(angleRad);

        const centerY =
          vehicle.y - (vehicle.length / 2) * Math.cos(angleRad);

        const position = toScreen({
          x: centerX,
          y: centerY,
        });

        // SUMO 角度以正北为 0°，顺时针增加。
        // SVG 矩形默认沿本地 X 轴，因此旋转角度为 angle - 90°。
        const rotation = vehicle.angle - 90;

        return (
          <g
            key={vehicle.id}
            transform={`translate(${position.x},${position.y}) rotate(${rotation})`}
          >
            <rect
              x={-(vehicle.length * SCALE) / 2}
              y={-(vehicle.width * SCALE) / 2}
              width={vehicle.length * SCALE}
              height={vehicle.width * SCALE}
              rx={1.5}
              fill="#4fc3f7"
              stroke="#d9f4ff"
              strokeWidth={0.6}
            />
          </g>
        );
      })}

      {/* 尚未收到路网数据时的提示 */}
      {!network && (
        <text
          x={VIEW / 2}
          y={VIEW / 2}
          textAnchor="middle"
          fill="#aaa"
          fontSize={15}
        >
          等待 SUMO 路网数据...
        </text>
      )}
    </svg>
  );
}

function SignalBox(props: {
  x: number;
  y: number;
  state?: DirectionState;
  label: string;
}) {
  const s = props.state;
  const countdown = s?.countdown_visible
    ? Math.ceil(s.remaining)
    : null;

  return (
    <g transform={`translate(${props.x},${props.y})`}>
      <rect
        x={-16}
        y={0}
        width={32}
        height={80}
        rx={6}
        fill="#111"
        stroke="#333"
      />

      <circle
        cx={0}
        cy={18}
        r={7}
        fill={s?.state === "r" ? "#f44336" : "#333"}
      />
      <circle
        cx={0}
        cy={40}
        r={7}
        fill={s?.state === "y" ? "#ffeb3b" : "#333"}
      />
      <circle
        cx={0}
        cy={62}
        r={7}
        fill={s?.state === "G" ? "#4caf50" : "#333"}
      />

      <text
        x={0}
        y={96}
        textAnchor="middle"
        fill="#aaa"
        fontSize={14}
        fontWeight="bold"
      >
        {props.label}
      </text>

      {countdown !== null && (
        <text
          x={0}
          y={-10}
          textAnchor="middle"
          fill="#fff"
          fontSize={18}
          fontWeight="bold"
        >
          {countdown}
        </text>
      )}
    </g>
  );
}
