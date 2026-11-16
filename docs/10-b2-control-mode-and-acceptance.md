# B2 控制模式与信号控制启停实施及验收指南

- 阶段：B2
- 对应决策：`docs/ADR-014-control-mode-and-disable-policy.md`
- 范围：后端 AUTO/MANUAL、ENABLED/DISABLING/DISABLED、全红保持、控制 API、前端共享类型及 SUMO 网络几何解析。
- 不包含：浏览器控制台 UI（B5）、配时编辑功能扩展及完整手动阶段操作台（B3）。既有手动阶段接口仅保留后端模式/启停校验与安全过渡。

## 1. 控制状态定义

| 维度     | 状态                 | 含义                                      |
| -------- | -------------------- | ----------------------------------------- |
| 仿真     | STOPPED / RUNNING 等 | 由 SimulationLifecycle 管理               |
| 控制启停 | ENABLED              | 控制域可按模式工作                        |
| 控制启停 | DISABLING            | 新控制命令已锁定，正在完成绿灯和黄灯过渡  |
| 控制启停 | DISABLED             | 全部 controlled links 全红；SUMO 继续运行 |
| 控制模式 | AUTO                 | 后端按八个正常绿/黄灯阶段自动推进         |
| 控制模式 | MANUAL               | 空闲时持续全红，等待合法人工阶段请求      |
| 控制阶段 | ALL_RED              | 控制保持状态，不属于正常八阶段周期        |

四个受保护业务阶段的顺序固定为：

1. 南北左转（NS_LEFT）
2. 南北直行（NS_STRAIGHT）
3. 东西左转（EW_LEFT）
4. 东西直行（EW_STRAIGHT）

每个业务阶段包含绿灯和黄灯，因此正常自动周期共八个绿/黄灯阶段。全红状态不属于正常八阶段周期。

## 2. 新增/修改文件

### 后端

- `backend/app/models/signal.py`：ControlMode、ControlStatus、ALL_RED 及快照字段。
- `backend/app/controllers/signal_controller.py`：安全进入全红、全红保持和恢复自动循环。
- `backend/app/services/signal_service.py`：控制启停、模式切换、全红灯色、手动请求安全过渡及新仿真重置。
- `backend/app/simulation/lifecycle.py`：在生命周期操作锁内串行执行控制命令。
- `backend/app/simulation/network_geometry.py`：解析 SUMO net.xml 静态几何并过滤或拒绝非有限坐标。
- `backend/app/api/routes/signal.py`：控制状态查询、启停和模式接口；配时及手动请求也通过生命周期锁。
- `backend/app/core/logging.py`：统一业务日志初始化。

### 前端类型

- `frontend/src/types/signal.ts`：增加 `ControlMode`、`ControlStatus`、`SignalControlState` 和 `ALL_RED` 等共享类型。

### 测试

- `backend/tests/test_signal_control_api.py`
- `backend/tests/test_network_geometry.py`
- `backend/tests/test_signal_controller.py`
- `backend/tests/test_signal_service.py`
- `backend/tests/test_simulation_lifecycle.py`
- `backend/tests/test_sumo_runner_lifecycle.py`

## 3. API

### GET `/api/signals/{tls_id}/control`

返回示例：

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

返回 `DISABLING` 表示正在等待当前绿灯和完整黄灯结束；后续查询变为 `DISABLED` 时，SUMO 应继续运行且全部 controlled links 为红灯。

### PUT `/api/signals/{tls_id}/control/mode`

请求：

```json
{ "mode": "MANUAL" }
```

若需要安全过渡，响应仍显示原 `control_mode`，同时 `pending_mode` 显示目标模式。到达全红后，`control_mode` 更新且 `pending_mode` 清空。

控制操作要求仿真 `RUNNING`，否则返回 HTTP 409。

### POST `/api/signals/{tls_id}/phases/switch`

请求示例：

```json
{ "target_phase": "EW_LEFT" }
```

仅允许在 `ENABLED + MANUAL` 状态下启动四个受保护绿灯阶段。若当前不处于全红状态，应先完成安全过渡，再启动目标阶段。黄灯阶段和 `ALL_RED` 不允许作为人工启动目标。

### 仿真生命周期接口

- `POST /api/simulation/start`
- `POST /api/simulation/stop`
- `GET /api/simulation/status`

仿真停止后重新启动时，控制域应重新初始化为 `ENABLED + AUTO + NS_LEFT`，清除待处理模式和待处理人工阶段。

## 4. 本地自动化验证与正式更新后回归

### 4.1 正式更新前的交付准备

- 原始 B2 交付包缺少 `simulation/routes/intersection.rou.xml`。
- 审查时已从原项目复制到暂存目录，并验证 SHA256 一致。
- 正式更新采用逐文件差异清单和选择性更新方式，没有直接覆盖整个项目。
- 内容相同的文件保留，不重复覆盖。

### 4.2 正式更新结果

正式更新脚本：

`B2-apply-delivery.ps1`

原项目完整备份：

`D:\Projects\traffic-signal-control-platform-backup-20261116-085929`

正式更新结果：

| 项目                  | 结果               |
| --------------------- | ------------------ |
| 交付清单文件          | 51 个              |
| 更新文件              | 19 个              |
| 新增文件              | 6 个               |
| 保留文件              | 26 个              |
| 保留文件 SHA256       | 全部一致           |
| 更新及新增文件 SHA256 | 全部验证通过       |
| 备份目录              | 已创建             |
| 临时目录检查          | 未发现遗留临时目录 |

正式更新脚本执行成功。文件复制与 SHA256 完整性校验通过。

### 4.3 正式更新后的后端回归

在原项目正式工作目录中，使用项目虚拟环境完成回归：

- `python -m compileall -q backend\app backend\tests`：通过。
- `python -m pip check`：通过。
- `python -m pytest -q`：通过。

依赖检查结果：

```text
No broken requirements found.
```

自动化测试结果：

```text
77 passed, 1 skipped in 1.24s
```

唯一 skipped 项为需要设置 `RUN_SUMO_INTEGRATION=1` 后执行的真实 SUMO 生命周期集成测试。该测试随后已单独执行并通过，不能将 skipped 计入 77 个 passed。

### 4.4 真实 SUMO 生命周期集成测试

在项目虚拟环境中执行：

```powershell
$env:RUN_SUMO_INTEGRATION = "1"
python -m pytest tests\test_sumo_runner_lifecycle.py::test_real_sumo_start_step_stop -v
```

结果：

```text
1 passed in 0.78s
```

使用 Eclipse SUMO 1.28.0，验证 SUMO 进程启动、TraCI 连接、仿真单步推进及停止清理。

## 5. 真实 SUMO 与 HTTP 集成验收

本节记录已在用户 Windows 环境、Eclipse SUMO 1.28.0 中完成的真实验证。涉及灯色的验收以 TraCI 读取的实际 TLS state 为依据，不仅依赖后端模拟对象或 JSON 快照。

### 5.1 启动后检查初始状态

真实 SUMO 生命周期集成测试通过，验证 SUMO 进程启动、TraCI 连接、仿真单步推进及停止清理。

HTTP 启动测试返回：

- HTTP 200。
- `status=running`。
- `lifecycle_status=RUNNING`。
- `sumo_connected=true`。
- `process_alive=true`。

控制域初始状态为：

- `control_mode=AUTO`
- `control_status=ENABLED`
- `phase_id=NS_LEFT`

### 5.2 AUTO 八阶段推进

已通过真实 SUMO 验证，观察到以下顺序：

1. NS_LEFT
2. NS_LEFT_YELLOW
3. NS_STRAIGHT
4. NS_STRAIGHT_YELLOW
5. EW_LEFT
6. EW_LEFT_YELLOW
7. EW_STRAIGHT
8. EW_STRAIGHT_YELLOW

真实 SUMO 状态与后端阶段推进一致，AUTO 保持 ENABLED，仿真资源正常释放。

### 5.3 AUTO 切换到 MANUAL

已通过真实 SUMO 服务层及 HTTP 集成验证：

- 请求 MANUAL 后不立即截断当前绿灯。
- 当前绿灯完成后执行完整黄灯。
- 随后进入 ALL_RED。
- 后端控制状态变为 `MANUAL + ENABLED + ALL_RED`。
- 全部 20 个 controlled links 变为红灯。
- SUMO 继续运行，继续推进仿真仍保持全红。
- HTTP 模式切换接口返回 200，待处理模式在安全过渡完成后清空。

### 5.4 MANUAL 人工阶段启动

已通过真实 SUMO 服务层及 HTTP 集成验证：

- MANUAL 全红状态下提交 `EW_LEFT`。
- HTTP 请求：

```json
{ "target_phase": "EW_LEFT" }
```

- HTTP 返回 200：

```json
{
  "accepted": true,
  "reason": "started_from_all_red"
}
```

- 后端控制状态变为 `MANUAL + ENABLED + EW_LEFT`。
- SUMO 实际灯色与后端预期一致。
- 对应 EW_LEFT linkIndex 8、9、18、19 为绿灯。
- HTTP 停止仿真后，SUMO 连接和进程正常释放。

### 5.5 DISABLED 安全停用

已通过真实 SUMO 服务层及 HTTP 集成验证：

- 请求停用后进入 DISABLING。
- 新控制命令被锁定。
- 当前绿灯完整执行 20 秒，随后执行 3 秒黄灯。
- 黄灯结束后进入 ALL_RED，控制状态变为 DISABLED。
- 20 个 controlled links 全部为红灯。
- SUMO 继续运行，仿真时间继续推进。
- 后续查询仍保持 DISABLED 和全红状态。
- HTTP 停止仿真后，SUMO 连接和进程正常释放。

### 5.6 验证所有 SUMO controlled links 全红

真实 TraCI 读取结果：

```text
Controlled links: 20
Before: grrGGgrrrrgrrGGgrrrr
Expected: rrrrrrrrrrrrrrrrrrrr
Actual:   rrrrrrrrrrrrrrrrrrrr
```

右转 linkIndex：

```text
index 0: r
index 5: r
index 10: r
index 15: r
```

所有 20 个 controlled links 均为红灯，包括原来小写 `g` 放行的四个右转连接。

### 5.7 重新启用

已通过真实 SUMO 服务层及 HTTP 集成验证：

- DISABLED → AUTO：重新启用后恢复 `AUTO + ENABLED + NS_LEFT`，SUMO 实际灯色正确，后续观察到 NS_LEFT、NS_LEFT_YELLOW、NS_STRAIGHT。
- DISABLED → MANUAL：重新启用后保持 `MANUAL + ENABLED + ALL_RED`，全部 20 个 linkIndex 为红灯；无人工指令时持续全红，SUMO 继续运行。

### 5.8 非法人工阶段请求

已通过真实 SUMO HTTP 集成验证：

| 请求目标         | HTTP 状态码 | 结果                                   |
| ---------------- | ----------: | -------------------------------------- |
| `INVALID_PHASE`  |         422 | FastAPI 枚举校验拒绝                   |
| `NS_LEFT_YELLOW` |         409 | `target_must_be_protected_green_phase` |
| `ALL_RED`        |         409 | `target_must_be_protected_green_phase` |

所有非法请求前后，后端控制阶段保持 ALL_RED，SUMO 实际 20 个 controlled links 均保持红灯，没有因非法请求改变信号状态。

### 5.9 仿真停止与重新启动状态复位

已通过真实 SUMO HTTP 集成验证：

1. 第一次启动仿真，控制状态为 `AUTO + ENABLED + NS_LEFT`。
2. 切换 MANUAL，安全过渡到 ALL_RED。
3. 人工启动 EW_LEFT。
4. 第一次 HTTP stop 成功，SUMO 连接和进程释放。
5. 第二次 HTTP start 成功。
6. 控制状态重新初始化为 `AUTO + ENABLED + NS_LEFT`。
7. `pending_mode` 和 `pending_manual_phase` 均为 `null`。
8. SUMO 实际灯色与 NS_LEFT 初始阶段预期一致。
9. 第二次 HTTP stop 成功，资源正常清理。

这项测试验证了仿真重新启动不会继承上一次运行的 MANUAL 阶段或待处理控制命令。

## 6. 前端类型与生产构建验收

### 6.1 共享类型核对

检查文件：

`frontend/src/types/signal.ts`

确认以下类型与后端 B2 约定一致：

- `PhaseId`：四个受保护绿灯阶段、四个黄灯阶段及 ALL_RED。
- `ControlMode`：AUTO、MANUAL。
- `ControlStatus`：ENABLED、DISABLING、DISABLED。
- `SignalControlState`：当前控制状态、当前阶段及待处理字段。
- `TimingConfig`：四方向绿灯配时及黄灯配时。
- `SignalSnapshot`：信号阶段、控制模式、启停状态、方向灯色和倒计时。

`pending_manual_phase` 使用 `PhaseId | null`，类型范围比后端实际允许的人工启动目标更宽；后端服务层已限制人工启动只能使用四个受保护绿灯阶段，因此不构成当前安全性问题。

### 6.2 前端生产构建

在 `frontend` 目录执行：

```powershell
npm run build
```

实际结果：

```text
> traffic-signal-control-platform-frontend@0.1.0 build
> tsc -b && vite build

vite v6.4.6 building for production...
✓ 28 modules transformed.
dist/index.html                  0.35 kB │ gzip:  0.28 kB
dist/assets/index-DJrHw2y4.js  148.83 kB │ gzip: 48.24 kB
✓ built in 449ms.
```

TypeScript 项目检查通过，Vite 生产构建成功，生成 `frontend/dist` 产物。

## 7. B2 验收记录

| 验收项                      | 结果 | 证据                                    |
| --------------------------- | ---- | --------------------------------------- |
| 交付文件清单校验            | 通过 | 51 个文件逐项核对                       |
| 正式更新原项目文件          | 通过 | 19 更新、6 新增、26 保留                |
| SHA256 完整性验证           | 通过 | 保留文件及更新/新增文件全部校验通过     |
| 原项目备份                  | 通过 | 备份目录已创建                          |
| 后端 compileall             | 通过 | 正式更新后原项目回归                    |
| pip check                   | 通过 | No broken requirements found            |
| pytest                      | 通过 | 77 passed，1 skipped                    |
| 真实 SUMO 生命周期          | 通过 | 单独执行，1 passed                      |
| AUTO 八阶段推进             | 通过 | 真实 SUMO 阶段与灯色记录                |
| AUTO→MANUAL 安全切换        | 通过 | 完整绿灯、黄灯后全红                    |
| MANUAL 全红保持             | 通过 | 继续推进仿真仍保持全红                  |
| MANUAL 人工阶段启动         | 通过 | EW_LEFT 从全红启动                      |
| DISABLED 完整绿/黄过渡      | 通过 | 真实 SUMO 时间及状态记录                |
| 所有 20 个 linkIndex 全红   | 通过 | TraCI 实际 TLS state                    |
| 右转 link 全红              | 通过 | linkIndex 0、5、10、15 均为 r           |
| SUMO 在 DISABLED 时继续运行 | 通过 | 仿真时间继续推进，进程存活              |
| 重新启用 AUTO               | 通过 | 从 NS_LEFT 恢复自动周期                 |
| 重新启用 MANUAL             | 通过 | 保持全红，无人工指令不放行              |
| 非法人工阶段请求            | 通过 | 422/409，灯色和阶段不变                 |
| 仿真停止与重新启动复位      | 通过 | HTTP stop/start 集成测试                |
| 前端共享类型核对            | 通过 | signal.ts 与后端 B2 约定一致            |
| 前端 TypeScript 检查        | 通过 | `tsc -b`                                |
| 前端生产构建                | 通过 | Vite 28 modules transformed，build 成功 |

## 8. 交付与验收边界

本次 B2 正式更新和约定的后端、真实 SUMO、HTTP 集成及前端构建检查均已完成。

以下内容不属于本次 B2 已验证范围：

- 浏览器控制台 UI（B5）。
- 完整手动阶段操作台（B3）。
- 配时编辑功能扩展。
- 生产部署及其他操作系统环境的部署验收。

B2 的验收结论应限定在本指南列明的实现范围和已执行测试证据内，不应将 B3、B5 或生产部署功能视为本阶段已经交付。
