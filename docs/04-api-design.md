# API 接口设计

> 文档版本：V2.1（目标契约）
> Base URL：`/api`
> 对应需求：`docs/01-requirements.md`
>
> 本文件定义目标接口契约。写入本文不代表接口已在代码中实现；实现状态以代码审查和接口测试为准。

## 1. 通用约定

- 请求和响应使用 JSON。
- 时间单位为秒；阶段计时以 SUMO simulation time 为准。
- 错误响应统一使用 `{"detail":"..."}`，按错误类型返回 400/409/422/503。
- 状态枚举使用大写英文值。
- 控制命令必须由后端校验仿真状态、控制启停状态、控制模式和阶段安全约束。
- 前端不直接发送 SUMO 状态字符串，也不直接访问 TraCI。
- 四类受保护信号组：`NS_STRAIGHT`、`NS_LEFT`、`EW_STRAIGHT`、`EW_LEFT`。
- 四个右转业务组：`N_RIGHT`、`S_RIGHT`、`E_RIGHT`、`W_RIGHT`，采用 `PERMISSIVE_YIELD` 让行控制，不属于四类保护式绿灯配时。

SUMO 信号字符约定：

| 字符 | 含义                         |
| ---- | ---------------------------- |
| `G`  | 优先绿灯                     |
| `g`  | 允许通行但必须让行的次要绿灯 |
| `y`  | 黄灯                         |
| `r`  | 红灯                         |

当前 SUMO TLS 程序将四个右转连接（linkIndex 0、5、10、15）在全部八个阶段设置为小写 `g`。API 中的 `PERMISSIVE_YIELD` 表示右转采用独立让行控制，不代表受保护绿灯或无条件通行。该静态控制状态不代表车辆已经完成安全让行。

具体 `linkIndex` 与业务信号组的映射必须由 `getControlledLinks()` 生成；不得假设每个业务组只对应一个字符。

## 1.1 业务阶段与 SUMO 阶段顺序

四类受保护业务阶段必须统一按以下顺序编号：

1. 南北左转：`NS_LEFT_GREEN` / `NS_LEFT_YELLOW`，SUMO index 0 / 1。
2. 南北直行：`NS_STRAIGHT_GREEN` / `NS_STRAIGHT_YELLOW`，SUMO index 2 / 3。
3. 东西左转：`EW_LEFT_GREEN` / `EW_LEFT_YELLOW`，SUMO index 4 / 5。
4. 东西直行：`EW_STRAIGHT_GREEN` / `EW_STRAIGHT_YELLOW`，SUMO index 6 / 7。

循环顺序为 `0→1→2→3→4→5→6→7→0`。每类业务阶段的绿灯后必须执行对应黄灯；不得把旧测试网络的阶段顺序当作当前目标顺序。

## 2. 仿真生命周期

### GET `/api/simulation/status`

目标响应：

```json
{
  "status": "running",
  "lifecycle_status": "RUNNING",
  "simulation_time": 42.0,
  "sumo_connected": true,
  "step_index": 84,
  "process_alive": true,
  "last_error": null
}
```

状态：`STOPPED`、`STARTING`、`RUNNING`、`STOPPING`、`FAILED`。`status` 为兼容字段，使用小写值；`lifecycle_status` 为规范状态字段。`FAILED` 表示启动、步进、连接或清理失败。`step_index` 是当前运行内成功执行的 TraCI 步数；`process_alive` 表示 Runner 持有的 SUMO 子进程句柄是否仍报告存活。`FAILED` 后应先调用 stop 完成清理，再重新 start。

### POST `/api/simulation/start`

启动 SUMO 并初始化本次运行的信号控制器。重复启动返回 409。

### POST `/api/simulation/stop`

停止仿真并完成资源清理。后端使用 TraCI `close(wait=True)` 等待 SUMO 退出；若优雅关闭失败则尝试终止子进程，并核验进程句柄退出。停止仿真不等同于停用信号控制；停止后不允许发送阶段控制命令。

## 3. 信号状态查询

### GET `/api/signals/{tls_id}/state`

目标响应：

```json
{
  "tls_id": "intersection_0",
  "phase_id": "NS_LEFT",
  "phase_index": 0,
  "remaining": 20.0,
  "countdown_visible": false,
  "next_phase": "NS_LEFT_YELLOW",
  "timing_version": 1,
  "groups": [
    {
      "group_id": "NS_LEFT",
      "state": "G",
      "remaining": 20.0,
      "countdown_visible": false
    },
    {
      "group_id": "NS_STRAIGHT",
      "state": "r",
      "remaining": 23.0,
      "countdown_visible": false
    },
    {
      "group_id": "EW_LEFT",
      "state": "r",
      "remaining": 66.0,
      "countdown_visible": false
    },
    {
      "group_id": "EW_STRAIGHT",
      "state": "r",
      "remaining": 89.0,
      "countdown_visible": false
    }
  ],
  "right_turns": [
    { "approach": "N", "state": "PERMISSIVE_YIELD" },
    { "approach": "S", "state": "PERMISSIVE_YIELD" },
    { "approach": "E", "state": "PERMISSIVE_YIELD" },
    { "approach": "W", "state": "PERMISSIVE_YIELD" }
  ]
}
```

说明：

- `phase_id` 表示当前业务绿/黄灯阶段。
- `phase_index` 表示 SUMO 信号程序中的阶段索引 0–7。
- `groups` 中四类受保护信号组的灯色由实际 controlled-links 映射生成。
- `right_turns` 描述各进口右转的让行控制状态，不代表其拥有优先通行权。
- 若右转当前因冲突而停车等待，建议另提供 `yielding` 或车辆级运行状态，不要仅凭静态灯色推断其已经安全通过。

## 4. 信号控制启停与模式

### GET `/api/signals/{tls_id}/control`

```json
{
  "tls_id": "intersection_0",
  "control_status": "ENABLED",
  "control_mode": "AUTO",
  "phase_id": "NS_LEFT",
  "pending_mode": null,
  "pending_manual_phase": null
}
```

### PUT `/api/signals/{tls_id}/control/enabled`

请求：

```json
{ "enabled": false }
```

用于启用/停用信号控制。响应 `control_status` 为 `ENABLED`、`DISABLING` 或 `DISABLED`。停用请求立即锁定新的控制命令；服务在当前绿灯和完整黄灯结束后将全部 controlled links（含右转）置红，再报告 `DISABLED`。SUMO 保持运行。仅在仿真 `RUNNING` 时接受控制操作，否则返回 HTTP 409。

### PUT `/api/signals/{tls_id}/control/mode`

请求：

```json
{ "mode": "MANUAL" }
```

允许值：`AUTO`、`MANUAL`。AUTO→MANUAL 必须完成当前绿灯及完整黄灯后进入全红，再确认模式切换；MANUAL 无请求时持续全红。MANUAL→AUTO 从全红安全状态恢复自动循环。切换不得截断正在执行的绿灯或黄灯。控制状态为 DISABLING 时返回 HTTP 409。

控制状态与信号快照字段：`control_mode`、`control_status`。`phase_id` 除八个业务绿/黄灯阶段外，另允许 `ALL_RED`，该状态不是周期配时阶段，不计入原八阶段周期。

以上控制接口已在 B2 后端实现；接口契约与自动化测试以当前代码和 `docs/10-b2-control-mode-and-acceptance.md` 为准。

## 5. 配时查询与修改

### GET `/api/signals/{tls_id}/timing`

返回当前生效配时、待生效配时、当前版本、待生效版本及按完整周期计算的红灯时长。

响应示例：

```json
{
  "active": {
    "ns_left_green": 20,
    "ns_left_yellow": 3,
    "ns_straight_green": 40,
    "ns_straight_yellow": 3,
    "ew_left_green": 20,
    "ew_left_yellow": 3,
    "ew_straight_green": 40,
    "ew_straight_yellow": 3
  },
  "pending": null,
  "timing_version": 1,
  "pending_timing_version": null,
  "computed": {
    "cycle_length": 132,
    "ns_left_red": 109,
    "ns_straight_red": 89,
    "ew_left_red": 109,
    "ew_straight_red": 89
  }
}
```

### PUT `/api/signals/{tls_id}/timing`

请求：

```json
{
  "ns_left_green": 20,
  "ns_left_yellow": 4,
  "ns_straight_green": 40,
  "ns_straight_yellow": 3,
  "ew_left_green": 22,
  "ew_left_yellow": 3,
  "ew_straight_green": 40,
  "ew_straight_yellow": 3
}
```

AUTO 模式下，响应为 `status=queued`、`effective=next_cycle_boundary`；新配时在 EW_STRAIGHT_YELLOW 完成并开始下一轮 NS_LEFT 时整体生效。

MANUAL 模式下：
- 当前处于业务绿灯/黄灯时，响应 `effective=next_manual_all_red`，在当前绿灯及完整黄灯结束、全红安全边界到达时应用。
- 已经处于 ALL_RED 时，可立即应用，响应 `effective=immediate_all_red`。
- 当前阶段不会被缩短或重置。

响应示例：

```json
{
  "accepted": true,
  "status": "queued",
  "effective": "next_cycle_boundary",
  "active": {},
  "pending": {},
  "timing_version": 1,
  "pending_timing_version": 2,
  "computed": {}
}
```

校验约束：

- 四类绿灯持续时间分别必须大于 8 秒。
- 四类黄灯持续时间分别必须大于 0 秒，默认各 3 秒。
- 四类受保护信号组的红灯总时长必须分别大于 10 秒。
- 请求必须提供全部八个绿/黄灯时长字段；未知字段拒绝，不接受旧版单一 `yellow` 字段。
- 红灯时长按完整 8 阶段周期计算；如经安全验证增加全红清空阶段，必须计入周期计算。
- 当前阶段不得被截断；新方案必须在安全边界整体生效。
- 校验失败返回 422，且不得改变当前生效或待生效方案。
- 同一路口最多保留一个待生效方案；新的有效请求替换旧 pending，提交当前 active 方案可撤销 pending。

> 当前 B3 配时版本由后端进程内管理；服务进程重启后恢复配置默认值。PostgreSQL `timing_plan` 持久化与 `signal_operation_log` 审计表尚未实现，不在 B3 本次代码交付范围，后续数据库持久化阶段另行实施。

## 6. 手动阶段请求

### POST `/api/signals/{tls_id}/phases/switch`

请求：

```json
{ "target_phase": "EW_STRAIGHT" }
```

响应示例：

```json
{
  "accepted": true,
  "status": "queued",
  "reason": "accepted_after_safe_all_red"
}
```

规则：

- 仅当仿真 `RUNNING`、信号控制 `ENABLED`、模式 `MANUAL` 时接受。
- 目标阶段必须属于该信号机允许的业务阶段。
- 不允许跳过或缩短当前黄灯阶段。
- 不允许直接下发任意 SUMO 灯色字符串。
- 从 ALL_RED 发起请求时可立即启动目标绿灯，响应 `status=started`。
- 从正在运行的业务阶段发起请求时，后端先完成当前绿灯和完整黄灯，再向 SUMO 实际下发全红；全红至少保持一个仿真 step 后，才启动目标绿灯，响应 `status=queued`。
- 请求当前已运行的目标阶段时返回 `status=unchanged`，不触发无意义切换。
- 完整安全过渡由后端状态机决定。
- MANUAL 模式无新请求时持续保持全红，按 `ADR-014` 执行。

## 7. WebSocket

### WS `/ws/simulation`

连接后先发送完整快照，随后发送动态更新。建议结构：

```json
{
  "type": "simulation_snapshot",
  "sequence": 1,
  "simulation_time": 42.0,
  "simulation_status": "RUNNING",
  "sumo_connected": true,
  "signal_control": {
    "enabled": true,
    "mode": "AUTO",
    "phase_id": "NS_LEFT",
    "phase_index": 0,
    "remaining": 20.0,
    "countdown_visible": false,
    "groups": [],
    "right_turns": []
  },
  "vehicles": [],
  "network_version": "network-v1"
}
```

- 动态消息可使用 `type=simulation_update`，携带状态变化和车辆数据。
- 静态路网几何通过独立接口或首次网络资源加载，不应每帧重复推送。
- 重连后必须重新取得完整快照。
- 使用 `sequence` 或仿真 tick 丢弃过期消息。

## 8. 静态路网数据

### GET `/api/intersections/{intersection_id}/network`

返回道路、车道、内部连接、几何 shape、车道宽度、停止线、信号灯/信号组空间位置、车道转向类型、右转让行连接和坐标转换元数据。

最终字段以实际 SUMO 网络解析结果为准。二维和三维视图必须使用同一份网络数据。

## 9. 倒计时规则

- 四类受保护信号组红灯最后 10 秒显示倒计时。
- 四类受保护信号组绿灯最后 8 秒显示倒计时。
- 黄灯全程显示倒计时。
- 后端提供剩余时间和 `countdown_visible`；前端只负责显示。
- 各信号组红灯剩余时间必须按真实 8 阶段周期计算，不能沿用旧双相位公式。
- 右转采用让行通行，不按普通受控红灯倒计时处理。
