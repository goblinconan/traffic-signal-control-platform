# B3：配时管理与手动阶段安全应用 — 交付与验收指南

> 基线：B2 `85fe65e` / `B2-complete`
> B3 交付包状态：代码已实现，沙盒自动化测试 85 passed、2 skipped
> 用户本机状态：待部署、待真实 SUMO/API 验收
> 范围：四类独立绿/黄灯配时、配时版本、AUTO/MANUAL 安全生效、手动阶段安全切换
> 不包含：B4 REST/WS 统一状态模型、B5 浏览器控制台、数据库持久化、右转动态让行安全验收

## 1. B3 交付内容

### 1.1 配时模型

每个受保护业务流具有独立绿灯和黄灯参数：

| 业务流 | 绿灯字段 | 黄灯字段 | 默认值 |
|---|---|---|---:|
| 南北左转 | `ns_left_green` | `ns_left_yellow` | 20 / 3 秒 |
| 南北直行 | `ns_straight_green` | `ns_straight_yellow` | 40 / 3 秒 |
| 东西左转 | `ew_left_green` | `ew_left_yellow` | 20 / 3 秒 |
| 东西直行 | `ew_straight_green` | `ew_straight_yellow` | 40 / 3 秒 |

校验规则：

- 每类绿灯必须 > 8 秒。
- 每类黄灯必须 > 0 秒。
- 每类受保护信号组计算红灯必须 > 10 秒。
- 一个周期为八个绿/黄灯阶段持续时间之和；红灯为该信号组之外其他三个业务流绿/黄灯时间之和。
- API 必须一次提交全部八个字段；未知字段、缺字段和非法数值返回 422。
- 不接受旧版共享 `yellow` 字段。

### 1.2 配时安全生效

- AUTO：配时请求先成为 pending，在完整周期边界整体提升为 active。
- MANUAL + ALL_RED：可立即应用。
- MANUAL + 业务阶段：在当前绿灯及完整黄灯完成、进入 ALL_RED 后应用。
- 新方案不会截断当前阶段；active/pending 版本由后端返回。
- 同一时刻最多一个 pending；新的提交替换旧 pending。提交与 active 相同的方案可撤销 pending。
- 当前版本只在后端进程内管理，进程重启后恢复 Settings 默认值；不属于持久化配置。

### 1.3 手动阶段安全应用

合法目标只允许：

- `NS_LEFT`
- `NS_STRAIGHT`
- `EW_LEFT`
- `EW_STRAIGHT`

从 ALL_RED 请求目标时立即启动；从活动业务阶段切换时：

1. 完成当前绿灯原定时长。
2. 完整执行当前黄灯。
3. 后端向 SUMO 实际下发 20 个 controlled links 全红。
4. 全红至少保持一个仿真 step。
5. 再启动目标绿灯阶段。

当前已经运行的目标阶段请求返回 `status=unchanged`。黄灯阶段、ALL_RED 和任意非法字符串均不得成为人工目标。

## 2. 交付文件清单

B3 更新脚本按清单逐文件备份、复制和 SHA256 校验。主要文件：

### 后端代码

- `backend/app/core/config.py`
- `backend/app/models/signal.py`
- `backend/app/controllers/signal_controller.py`
- `backend/app/services/timing_service.py`
- `backend/app/services/signal_service.py`
- `backend/app/api/routes/signal.py`

### 测试

- `backend/tests/test_signal_controller.py`
- `backend/tests/test_signal_service.py`
- `backend/tests/test_signal_control_api.py`
- `backend/tests/test_b3_sumo_integration.py`

### 前端共享类型

- `frontend/src/types/signal.ts`

### 文档

- `docs/00-project-overview.md`
- `docs/01-requirements.md`
- `docs/02-architecture.md`
- `docs/04-api-design.md`
- `docs/06-test-plan.md`
- `docs/07-development-log.md`
- `docs/08-deployment.md`
- `docs/09-b1-simulation-lifecycle.md`
- `docs/11-b3-timing-and-manual-control.md`
- `docs/ADR-015-b3-timing-and-manual-phase-application.md`

## 3. 部署前准备

在 Windows PowerShell 中执行：

```powershell
Set-Location D:\Projects\traffic-signal-control-platform
git status --short
git log -1 --oneline --decorate
```

确认当前代码基线为 B2 `85fe65e`。如果工作区有未提交工作，先自行确认并备份；不要用 `git reset`、`git clean` 或全量覆盖。

将交付 ZIP 解压到项目根目录，确保出现：

```text
B3-apply-delivery.ps1
B3-delivery\backend\...
B3-delivery\frontend\...
B3-delivery\docs\...
```

先运行只读预检：

```powershell
.\B3-apply-delivery.ps1
```

预检通过后再正式更新：

```powershell
.\B3-apply-delivery.ps1 -Apply
```

脚本会将更新前文件备份到 `temp\backup-B3-before-时间戳`，逐文件复制并验证 SHA256。若脚本失败，停止后续测试，保留完整输出。

## 4. 后端静态检查和自动化测试

```powershell
Set-Location D:\Projects\traffic-signal-control-platform
.\.venv\Scripts\python.exe -m compileall -q backend\app backend\tests
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest -q backend\tests
```

交付包沙盒基准：

```text
85 passed, 2 skipped
```

2 项 skipped 均为需要真实 SUMO 环境的集成测试：B1 SUMO 生命周期测试和 B3 手动全红保持测试。用户本机执行结果必须独立记录，不能把沙盒结果当作 Windows 本机验收结果。

## 5. 前端生产构建

```powershell
Set-Location D:\Projects\traffic-signal-control-platform\frontend
npm run build
```

B3 只更新共享 `TimingConfig` 类型，不增加控制面板 UI。此构建用于确认 TypeScript 类型变更没有破坏现有前端。

## 6. 本机真实 SUMO 与 API 验收

### 6.1 启动后端

确认 SUMO 1.28.0、`SUMO_HOME` 和项目 `.venv` 正常。

```powershell
Set-Location D:\Projects\traffic-signal-control-platform\backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

另开 PowerShell：

```powershell
$base = "http://127.0.0.1:8000/api"
$tls = "intersection_0"
Invoke-RestMethod "$base/simulation/status"
Invoke-RestMethod -Method Post "$base/simulation/start"
Invoke-RestMethod "$base/signals/$tls/timing"
```

预期默认配时：

- `ns_left_green=20`，`ns_left_yellow=3`
- `ns_straight_green=40`，`ns_straight_yellow=3`
- `ew_left_green=20`，`ew_left_yellow=3`
- `ew_straight_green=40`，`ew_straight_yellow=3`
- 周期 132 秒；NS/EW 直行红灯各 89 秒；NS/EW 左转红灯各 109 秒。

### 6.2 验证完整八字段配时 API

```powershell
$timing = @{
  ns_left_green = 22
  ns_left_yellow = 4
  ns_straight_green = 42
  ns_straight_yellow = 2
  ew_left_green = 23
  ew_left_yellow = 5
  ew_straight_green = 43
  ew_straight_yellow = 3
} | ConvertTo-Json

Invoke-RestMethod -Method Put `
  "$base/signals/$tls/timing" `
  -ContentType "application/json" `
  -Body $timing

Invoke-RestMethod "$base/signals/$tls/timing"
```

AUTO 模式预期：

- 返回 `accepted=true`、`status=queued`、`effective=next_cycle_boundary`。
- `pending` 包含八个新字段，`pending_timing_version` 为下一版本。
- `active` 保持原值，直到完整八阶段周期边界。
- 生效后 `pending=null`，`timing_version` 增加，`active` 更新为新方案。

验证缺字段、旧字段和非法值被拒绝：

```powershell
$bad = @{
  ns_left_green = 22
  ns_left_yellow = 0
  ns_straight_green = 42
  ns_straight_yellow = 2
  ew_left_green = 23
  ew_left_yellow = 5
  ew_straight_green = 43
  ew_straight_yellow = 3
} | ConvertTo-Json

try {
  Invoke-RestMethod -Method Put "$base/signals/$tls/timing" `
    -ContentType "application/json" -Body $bad
} catch {
  $_.Exception.Response.StatusCode.value__
}
```

预期 HTTP 422；active/pending 不应被非法请求改变。可再提交缺少一个字段的 JSON，预期同样 422。

### 6.3 验证 MANUAL 模式和手动阶段

先读取控制状态：

```powershell
Invoke-RestMethod "$base/signals/$tls/control"
```

切换 MANUAL：

```powershell
Invoke-RestMethod -Method Put `
  "$base/signals/$tls/control/mode" `
  -ContentType "application/json" `
  -Body '{"mode":"MANUAL"}'
```

若当前处于业务阶段，响应先显示 `pending_mode=MANUAL`。等待当前绿灯及完整黄灯结束，然后查询：

```powershell
Invoke-RestMethod "$base/signals/$tls/control"
Invoke-RestMethod "$base/signals/$tls/state"
```

预期 `control_mode=MANUAL`、`phase_id=ALL_RED`；无人工请求时持续全红。

从 ALL_RED 启动 EW_LEFT：

```powershell
Invoke-RestMethod -Method Post `
  "$base/signals/$tls/phases/switch" `
  -ContentType "application/json" `
  -Body '{"target_phase":"EW_LEFT"}'
```

预期返回 `accepted=true`、`status=started`、`reason=started_from_all_red`。

再请求 NS_STRAIGHT：

```powershell
Invoke-RestMethod -Method Post `
  "$base/signals/$tls/phases/switch" `
  -ContentType "application/json" `
  -Body '{"target_phase":"NS_STRAIGHT"}'
```

预期返回 `accepted=true`、`status=queued`。随后验证：

1. EW_LEFT 完整执行绿灯。
2. EW_LEFT_YELLOW 完整执行配置黄灯。
3. 查询过程中观察到 `phase_id=ALL_RED`。
4. 全红时 SUMO 的 20 个 controlled links 均为 `r`。
5. 至少一个仿真 step 后才进入 NS_STRAIGHT。

无效目标测试：

```powershell
try {
  Invoke-RestMethod -Method Post `
    "$base/signals/$tls/phases/switch" `
    -ContentType "application/json" `
    -Body '{"target_phase":"NS_LEFT_YELLOW"}'
} catch {
  $_.Exception.Response.StatusCode.value__
}
```

预期 HTTP 409；非法请求不得改变阶段或 SUMO 灯色。

### 6.4 恢复 AUTO 并停止

```powershell
Invoke-RestMethod -Method Put `
  "$base/signals/$tls/control/mode" `
  -ContentType "application/json" `
  -Body '{"mode":"AUTO"}'

Invoke-RestMethod -Method Post "$base/simulation/stop"
```

预期从安全全红边界恢复 AUTO；停止仿真后生命周期回到 STOPPED，SUMO 进程退出。

## 7.1 真实 SUMO 专项集成测试

```powershell
Set-Location D:\Projects\traffic-signal-control-platform\backend
$env:RUN_SUMO_INTEGRATION = "1"
..\.venv\Scripts\python.exe -m pytest tests\test_b3_sumo_integration.py -m integration -v
Remove-Item Env:RUN_SUMO_INTEGRATION
```

该测试读取 SUMO 实际 TLS state，验证 20 个 controlled links 在 MANUAL 阶段切换时真实保持全红一个仿真 step。它不替代用户本机的完整 HTTP 手工验收。

## 7. B3 验收记录需要保存

- `compileall` 输出。
- `pip check` 输出。
- `pytest -q` 完整结果。
- `npm run build` 输出。
- GET timing 默认配置和红灯计算结果。
- PUT timing queued 及 pending→active 版本变化结果。
- 缺字段、非法黄灯、旧 `yellow` 字段的 HTTP 422 结果。
- AUTO→MANUAL 的 pending 过渡和全红状态。
- MANUAL 从全红启动阶段及活动阶段切换的 API 响应。
- 活动阶段→完整黄灯→真实 ALL_RED→目标阶段的状态记录。
- 仿真停止及 SUMO 进程清理结果。

## 8. B3 完成边界与后续阶段

只有用户本机更新后自动化测试、真实 SUMO/API 验收和前端构建通过，才能将 B3 标记为完成。

B3 不包含：
- PostgreSQL `timing_plan` 持久化和 `signal_operation_log` 审计表。
- B4 REST/WS 统一状态模型。
- B5 浏览器信号控制台 UI。
- 右转车辆与行人/非机动车的动态让行安全验收。
- 生产部署和 Docker 内 SUMO/TraCI 最终拓扑验收。

B3 验收通过后，下一阶段按架构文档进入 B4：定义 REST API / WebSocket 统一状态模型、完整快照、动态更新、sequence/tick、防过期覆盖和重连恢复。
