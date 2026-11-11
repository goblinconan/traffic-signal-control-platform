# API 接口设计

> 版本：V1.0　Base URL：`/api`

## 1. 通用约定

- 所有请求/响应使用 JSON。
- 时间单位：秒（float）。
- 错误响应：`{"detail": "..."}`，HTTP 400/409/503。
- 信号灯 `state` 使用 SUMO 字符：`G`=绿、`y`=黄、`r`=红、`u`=黄闪（第一版不使用 `u`）。

## 2. 接口

### GET /api/health

响应：`{"status":"ok","sumo_connected":bool}`

### GET /api/simulation/status

响应：

```json
{
  "status": "stopped | starting | running | error",
  "simulation_time": 0.0,
  "sumo_connected": false
}
```

### POST /api/simulation/start

请求体：`{}`  
响应：`{"status":"running"}`  
说明：启动 SUMO，初始化信号控制器。重复启动返回 409。

### POST /api/simulation/stop

响应：`{"status":"stopped"}`

### GET /api/signals/{tls_id}/state

响应：

```json
{
  "tls_id": "intersection_0",
  "phase_id": "NS_GREEN",
  "direction": "NS",
  "state": "G",
  "remaining": 24.0,
  "countdown_visible": false,
  "next_phase": "NS_YELLOW",
  "timing": {
    "ns_green": 30,
    "ns_yellow": 3,
    "ew_green": 30,
    "ew_yellow": 3,
    "ns_red": 33,
    "ew_red": 33
  }
}
```

### GET /api/signals/{tls_id}/timing

响应：当前生效配时 + 待生效配时（如果有）。

### PUT /api/signals/{tls_id}/timing

请求体：

```json
{ "ns_green": 40, "ns_yellow": 3, "ew_green": 35, "ew_yellow": 3 }
```

响应：`{"accepted":true,"effective":"next_cycle","pending_timing":{...}}`  
说明：校验不通过返回 400；当前阶段不截断，新配时从下一次进入对应阶段时生效。

### POST /api/signals/{tls_id}/phases/switch

请求体：`{"target_phase":"EW_GREEN"}`  
响应：`{"accepted":true,"reason":"transition_via_yellow"}`  
说明：不允许从 `NS_GREEN` 直接跳 `EW_GREEN`，必须先经过 `NS_YELLOW`；违规返回 409。

### WS /ws/simulation

客户端连接后，服务端推送统一结构：

```json
{
  "type": "simulation_update",
  "simulation_time": 42.0,
  "simulation_status": "running",
  "signal": {
    "tls_id": "intersection_0",
    "phase_id": "NS_GREEN",
    "direction": "NS",
    "state": "G",
    "remaining": 7.0,
    "countdown_visible": true,
    "next_phase": "NS_YELLOW"
  },
  "vehicles": [
    { "id": "v0", "x": 120.5, "y": 80.2, "angle": 90.0, "speed": 8.3 }
  ]
}
```

## 3. 倒计时规则在后端的体现

- 红灯：`remaining > 10` → `countdown_visible=false`；`<=10` → `true`，前端显示 `int(ceil(remaining))`。
- 绿灯：`remaining > 8` → `false`；`<=8` → `true`。
- 黄灯：始终 `true`。

后端只给出 `remaining` 和 `countdown_visible`，前端不自行判断阈值。
