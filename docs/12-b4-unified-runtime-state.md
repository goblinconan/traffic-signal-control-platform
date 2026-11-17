# B4：REST / WebSocket 统一运行状态模型

- 阶段：B4
- 基线：`B3-complete` / `b493da1df6e06a41674b0dd9a376a19fc7dff5f2`
- 协议版本：`1.0`
- 状态：实现候选，须按本文件完成本机验收后方可标记完成

## 1. 目标与边界

B4 将仿真生命周期、信号控制、配时和车辆数据整合为一个后端权威运行状态模型，REST 查询和 WebSocket 消息复用同一字段结构。B4 不实现 B5 控制面板，不改变 B3 信号状态机、安全边界、配时版本或 SUMO 灯色映射。

## 2. 状态来源

- 生命周期：`SimulationLifecycle`，提供 STOPPED/STARTING/RUNNING/STOPPING/FAILED、仿真时间、TraCI 步数、连接/进程状态和错误。
- 信号控制：`SignalService` / `SignalController`，提供控制启停、AUTO/MANUAL、当前/下一阶段、剩余时间和四类信号组灯色。
- 配时：`TimingService`，提供 active/pending、版本及周期/红灯计算。
- 车辆：`SumoRunner.vehicles()`，提供 SUMO 位置、角度、速度、长宽。
- 静态路网：`network_geometry`，独立 REST 资源，以 net.xml SHA256 作为 `network_version`。

所有运行态读取通过生命周期操作锁串行化，避免 REST/WS 采样与 TraCI step 或控制操作竞争。

## 3. REST 契约

### GET `/api/simulation/state`

返回完整 `simulation_snapshot`，结构与 WebSocket 首条消息一致。每次服务端生成消息时分配单调递增 `sequence`。

### GET `/api/intersections/{intersection_id}/network`

返回 `{intersection_id, network_version, geometry}`。`geometry` 包含路口、道路、车道、内部车道及坐标边界。若 net.xml 内容变化，SHA256 版本随之变化。

既有 `/api/simulation/status`、`/api/signals/{tls_id}/state`、`control`、`timing` 和阶段控制 API 保持兼容；B4 不移除旧接口。

## 4. 统一状态字段

| 字段 | 说明 |
|---|---|
| `schema_version` | 固定 `1.0` |
| `type` | `simulation_snapshot` 或 `simulation_update` |
| `sequence` | 本进程消息序号，严格递增；允许因 REST 查询或多客户端快照出现序号间隔 |
| `simulation_time` | SUMO 仿真时间，秒 |
| `simulation_status` | STOPPED/STARTING/RUNNING/STOPPING/FAILED |
| `sumo_connected` / `process_alive` | TraCI 连接和 SUMO 子进程状态 |
| `step_index` | 当前运行成功完成的 TraCI 步数 |
| `last_error` | 最近生命周期错误；无错误为 null |
| `signal_control` | 信号机、控制启停/模式、阶段、倒计时、信号组及右转策略 |
| `timing` | active/pending、版本和计算周期 |
| `vehicles` | 当前车辆实时快照 |
| `network_version` | 对应静态网络资源的内容版本 |

`signal_control.enabled` 仅在 `control_status=ENABLED` 时为 true；`DISABLING` 与 `DISABLED` 必须明确区分。`phase_index` 对八个 SUMO 阶段为 0–7；`ALL_RED` 为 null。四个右转组的 `state=PERMISSIVE_YIELD` 表示规则类别，`signal_state` 由后端根据 SUMO 实际 TLS 状态字符串和 controlled-links 映射读取，正常放行策略通常为小写 `g`，ALL_RED 时为 `r`。它不表示车辆已完成让行。

## 5. WebSocket 契约

地址：`WS /ws/simulation`。

1. 每次连接/重连，服务端先发送一条完整 `simulation_snapshot`。
2. 后续发送 `simulation_update`，动态字段结构与快照一致。
3. 不在动态消息重复发送静态路网几何；客户端按 `network_version` 请求网络 REST 资源并缓存。
4. 生命周期从 RUNNING 转为 STOPPED/FAILED 等状态时，也必须发送状态更新，避免浏览器保留旧的 RUNNING 状态。
5. `sequence` 在同一后端进程内单调递增；客户端只接受大于已应用序号的消息。重连后先用新快照重置同步基线。序号不要求连续。
6. 浏览器断开不得影响仿真和信号控制。

## 6. 一致性规则

- 后端是状态唯一权威来源；前端不得自建相位计时器或推导相位切换。
- `simulation_time`、车辆位置、灯色和阶段来自同一受生命周期锁保护的采样。
- REST 快照和 WS 消息调用同一 `RuntimeStateService` 及 Pydantic 契约。
- 状态读取不直接操作 TraCI；所有 Runner 查询由其内部锁保护，并在生命周期操作锁内完成组合采样。
- 静态网络版本与网络资源必须匹配；动态消息只携带版本号。

## 7. B4 验收标准

- [ ] `GET /api/simulation/state` 返回 schema_version=1.0 的完整快照。
- [ ] REST 与 WebSocket 使用相同字段结构及相同状态语义。
- [ ] 首次连接和每次重连均先收到完整 snapshot。
- [ ] 后续 update 的 sequence 严格大于之前消息；前端拒绝重复/倒退序号。
- [ ] WebSocket 不重复传输静态网络几何；network_version 可取得对应网络资源。
- [ ] 仿真启动、运行、停止及 FAILED 状态能推送给已连接客户端。
- [ ] 四类受保护组灯色/倒计时、右转让行策略、AUTO/MANUAL、ENABLED/DISABLING/DISABLED、配时 active/pending/version 正确。
- [ ] 车辆数据与仿真时间一致，停止时车辆数组为空。
- [ ] 并发 REST 状态读取、WebSocket 广播与仿真 step 不造成 TraCI 竞争。
- [ ] B3 原有 pytest、真实 SUMO 专项和前端 build 回归通过。
- [ ] `test_b4_sumo_state_integration.py` 在用户本机真实 SUMO 1.28.0 环境通过。

## 8. 明确不在 B4 范围

- B5 浏览器控制面板操作 UI。
- PostgreSQL 配时持久化、控制审计日志及用户认证。
- 三维场景 A1–A5。
- 右转冲突行为的交通工程安全认证。

这些边界不代表项目总需求被取消；需按项目阶段安排另行实施和验收。
