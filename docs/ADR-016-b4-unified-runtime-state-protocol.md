# ADR-016：B4 REST / WebSocket 统一运行状态协议

- 状态：B4 实施决策
- 适用阶段：B4
- 基线：B3-complete (`b493da1`)

## 背景

B3 基线中 WebSocket 首次连接发送 `simulation_update` 并附带网络几何，后台更新只广播 `_payload()`；消息没有 sequence，缺少生命周期完整字段、pending 配时和统一的信号组列表。前端仅保留 network 并直接覆盖状态，无法识别过期消息。REST 状态分散在多个接口，没有完整统一快照。

## 决策

1. 新增 `RuntimeStateService`，作为 REST 和 WebSocket 的唯一运行态消息构造入口。
2. 新增 `GET /api/simulation/state`，返回 `simulation_snapshot`。
3. WebSocket 首条消息固定为 `simulation_snapshot`，后续为 `simulation_update`；两者字段一致。
4. 新增 `GET /api/intersections/{intersection_id}/network`，静态路网独立传输；`network_version` 使用 net.xml 内容 SHA256。
5. 每个消息分配进程内单调递增 sequence；允许跳号，客户端只接受严格大于当前值的消息。
6. 通过 `SimulationLifecycle.read_state()` 与 step/control 共用操作锁，组合读取生命周期、信号、配时和车辆快照。
7. 生命周期离开 RUNNING 时也发布一次状态更新；客户端断线不影响控制循环。
8. 保留既有 B1–B3 REST 接口和安全策略，不改变八阶段顺序、ALL_RED step hold、配时安全边界或右转控制策略。

## 后果

REST/WS 有一个可验证的协议契约；前端可通过 sequence 防止旧消息覆盖新状态，并通过 network_version 缓存静态路网。代价是新增统一模型和状态读取锁；序号只在单个后端进程生命周期内有意义，不是持久化事件 ID。

## 验收

由 `docs/12-b4-unified-runtime-state.md` 定义，必须通过 pytest、前端构建、REST/WS 重连及真实 SUMO 本机验收。
