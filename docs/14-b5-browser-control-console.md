# B5 浏览器信号控制操作台

- 目标基线：B4-complete，`f2052b539ce9c50782a25b50471c4725874d8b8e`
- 阶段定位：B5 浏览器控制台，不包含 A1–A5 三维场景开发。
- 当前交付状态：代码包已生成；必须在用户 Windows + SUMO 环境完成构建、真实联调和验收后，才能标记 B5 完成。

## 1. 本阶段范围

依据 `docs/01-requirements.md` 第 14 节、第 16.2 节及 `docs/02-architecture.md` 第 22 节，B5 在现有 B3 控制 REST API 和 B4 统一状态协议之上增加浏览器控制界面：

1. 仿真启动、停止、生命周期状态、SUMO 连接、进程状态和后端错误反馈。
2. 信号控制 ENABLED / DISABLING / DISABLED 状态及安全启停操作。
3. AUTO / MANUAL 模式显示与切换。
4. 当前阶段、下一阶段、四类受保护信号组灯色和剩余时间显示。
5. MANUAL 模式下选择四类合法业务绿灯阶段并提交请求，显示服务端 accepted/status/reason。
6. 四类绿灯和黄灯配时的完整编辑、前端预校验、提交结果、生效版本及 active/pending 方案展示。
7. 保留 B4 二维 SVG 路口图、车辆实时位置和右转独立让行状态。

B5 不重写后端状态机，不直接操作 TraCI，不允许前端提交 SUMO 灯色字符串，不新增暂停/恢复接口，不实现三维场景。

## 2. 本次交付文件

| 文件 | 操作 | 用途 |
|---|---|---|
| `frontend/src/App.tsx` | 替换 | B5 页面布局，保留二维视图和 B4 WebSocket Hook |
| `frontend/src/components/control/ControlPanel.tsx` | 新增 | 生命周期、控制域、相位、配时和反馈面板 |
| `frontend/src/components/control/timingValidation.ts` | 新增 | 绿/黄/红时长的前端预校验 |
| `frontend/src/components/control/control.css` | 新增 | 控制台样式和响应式布局 |
| `docs/00-project-overview.md` | 更新 | 阶段进度与 B4/B5 状态 |
| `docs/07-development-log.md` | 追加 | B5 实施记录及待验收事项 |
| `docs/14-b5-browser-control-console.md` | 新增 | B5 设计、接口、部署和验收说明 |
| `docs/15-a1-a5-assessment.md` | 新增 | A1–A5 现状评估、依赖与计划 |
| `README.md` | 更新 | 本机运行和 B5 入口说明 |

后端 B3/B4 文件保持不变。前端原有 `useSimulationSocket.ts`、`types/signal.ts`、`IntersectionView.tsx` 保持不变。

## 3. REST API 对接契约

| 操作 | 方法与路径 | 请求体 | 成功反馈 |
|---|---|---|---|
| 启动仿真 | `POST /api/simulation/start` | 无 | 生命周期快照 |
| 停止/清理 | `POST /api/simulation/stop` | 无 | 生命周期快照 |
| 启停信号控制 | `PUT /api/signals/{tls_id}/control/enabled` | `{"enabled": true/false}` | 控制状态字典 |
| 控制模式 | `PUT /api/signals/{tls_id}/control/mode` | `{"mode":"AUTO"}` 或 `MANUAL` | 控制状态字典 |
| 查询配时 | `GET /api/signals/{tls_id}/timing` | 无 | active/pending/version/computed |
| 提交配时 | `PUT /api/signals/{tls_id}/timing` | 完整八字段 | accepted/status/effective 与配时快照 |
| 人工切相位 | `POST /api/signals/{tls_id}/phases/switch` | `{"target_phase":"NS_LEFT"}` 等 | accepted/status/reason |
| 运行状态 | `GET /api/simulation/state` | 无 | B4 完整快照 |
| 动态状态 | `WS /ws/simulation` | 无 | snapshot/update |

`tls_id` 由 B4 状态快照中的 `signal_control.tls_id` 获取；页面在快照尚未到达时暂用项目默认值 `intersection_0`。请求仍由后端验证实际 TLS ID。

## 4. 控制约束与界面行为

### 4.1 仿真生命周期

- 只有 STOPPED 时开放启动。
- RUNNING 时开放停止。
- STARTING / STOPPING 时禁用重复操作。
- FAILED 时显示 `last_error`，启动按钮保持禁用，提供“清理异常仿真”操作；后端要求先 stop 清理再允许重新启动。
- 文档需求曾使用 ERROR，但 B4 实际枚举是 STOPPED/STARTING/RUNNING/STOPPING/FAILED。页面保留真实值 FAILED，并以“异常（FAILED）”显示，不修改服务端协议。

### 4.2 信号控制域

- 控制状态展示 ENABLED、DISABLING、DISABLED。
- DISABLING 是真实安全过渡状态，页面不能将停用请求响应等同于已经完成停用。
- 模式切换仅在仿真 RUNNING 且不处于 DISABLING 时开放。
- 控制启停仅在仿真 RUNNING 且不处于 DISABLING 时开放。

### 4.3 人工阶段

只允许请求四个业务绿灯阶段，按项目固定顺序展示：

1. 南北左转 `NS_LEFT`
2. 南北直行 `NS_STRAIGHT`
3. 东西左转 `EW_LEFT`
4. 东西直行 `EW_STRAIGHT`

只有 RUNNING + ENABLED + MANUAL 时开放。黄灯阶段和 ALL_RED 不作为用户目标选项。后端拒绝时显示 HTTP 错误原因；接受时显示 `status` 和 `reason`。真实黄灯及 ALL_RED 过渡由后端执行。

### 4.4 配时

- 提交完整八字段，不发送局部字段。
- 绿灯必须 `> 8s`，黄灯必须 `> 0s`。
- 每类受保护信号组计算红灯必须 `> 10s`。
- 前端校验仅用于提前提示；FastAPI/Pydantic 和 TimingService 是最终权威校验。
- AUTO 模式按后端定义在完整周期边界生效；MANUAL 按安全 ALL_RED 边界生效；当前阶段不得被前端截断。
- active/pending 版本以 B4 状态快照为准。存在 pending 时，编辑区以 pending 方案为起点；恢复按钮恢复服务端 pending 或 active 方案。

## 5. 部署步骤

### 5.1 应用交付文件

在项目根目录执行交付包内的 `B5-apply-delivery.ps1`。脚本会：

- 检查 Git HEAD 必须为 B4 commit `f2052b539ce9c50782a25b50471c4725874d8b8e`。
- 检查已跟踪文件无暂存或未暂存修改。
- 在项目同级目录建立备份目录。
- 只替换本交付清单中的文件；不删除、不覆盖其他文件。
- 不执行 Git add/commit/push/tag。

### 5.2 前端构建

```powershell
Set-Location D:\Projects\traffic-signal-control-platform\frontend
npm ci
npm run build
```

预期：TypeScript 检查和 Vite production build 均成功，生成 `frontend/dist`。`dist` 是构建产物，不应加入本次 B5 源码提交。

### 5.3 启动后端

```powershell
Set-Location D:\Projects\traffic-signal-control-platform\backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

确认 `http://127.0.0.1:8000/docs` 可访问。

### 5.4 启动前端

另开 PowerShell 窗口：

```powershell
Set-Location D:\Projects\traffic-signal-control-platform\frontend
npm run dev
```

打开 `http://127.0.0.1:5173/`。开发服务器代理 `/api` 和 `/ws` 到 `127.0.0.1:8000`。

### 5.5 只读 API 冒烟检查

后端启动后，在项目根目录运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\Test-B5-Api.ps1
```

脚本只执行 GET，不启动/停止 SUMO，也不修改信号控制或配时。

## 6. 浏览器端到端验收顺序

每项均需在浏览器中实际观察，并记录截图或结果；自动化 API 测试不能替代真实 SUMO 验收。

1. **初始快照**：页面显示 WebSocket 已连接、STOPPED、SUMO 未连接；无控制按钮误开放。
2. **启动仿真**：点击启动，观察 RUNNING、SUMO 已连接、车辆移动、仿真时间和 sequence 增长。
3. **AUTO/MANUAL**：在 RUNNING 时切换 MANUAL，观察后端完成当前安全过渡并进入全红；切回 AUTO，观察后端恢复自动推进。
4. **人工阶段**：MANUAL + ENABLED 时依次请求四类合法绿灯阶段；确认服务端反馈 accepted/status/reason，实际灯色不跳过黄灯和 ALL_RED。
5. **非法操作**：AUTO 下尝试提交人工请求（按钮应禁用）；使用 API Docs 或 PowerShell 发送非法请求时，应由后端返回 409/422，页面显示错误详情。
6. **安全停用**：点击请求安全停用，观察 DISABLING，等待服务端完成完整黄灯及全红后显示 DISABLED；SUMO 仍保持 RUNNING。
7. **重新启用**：点击启用，确认控制状态回到 ENABLED，按当前模式规则恢复控制。
8. **配时前端校验**：把任一绿灯设为 8 或更低、黄灯设为 0，确认提交按钮禁用并出现错误。
9. **配时后端校验**：通过 API 发送不满足红灯 `>10s` 的完整配时，确认 HTTP 422/错误原因；不应改变 active/pending 版本。
10. **配时正常提交**：提交合法方案，确认 pending 版本/方案出现；AUTO 等待完整周期边界，MANUAL 等待安全全红边界后应用。观察 active version 更新且当前阶段未被截断。
11. **停止仿真**：点击停止，观察 STOPPING → STOPPED、SUMO 断开、进程退出、车辆停止；控制按钮回到不可用状态。
12. **重连**：刷新浏览器或断开后恢复网络，确认首条消息重新为完整 snapshot，页面状态与后端一致。

## 7. 自动化与人工测试边界

本交付在前端增加控制台与纯函数配时校验，不新增前端测试框架或第三方依赖。原因是采集基线的 package.json/package-lock.json 没有 Vitest、Jest 或 Playwright；本交付不在未验证依赖安装和锁文件变更的情况下擅自引入测试栈。

现有后端 15 个测试模块覆盖生命周期、控制 API、配时、人工阶段、统一状态、网络几何、WebSocket 和并发。部署后先执行：

```powershell
Set-Location D:\Projects\traffic-signal-control-platform\backend
..\.venv\Scripts\python.exe -m pytest -q
```

真实 SUMO 集成测试使用 `RUN_SUMO_INTEGRATION=1` 启用，在本机 SUMO 1.28.0 环境执行：

```powershell
$env:RUN_SUMO_INTEGRATION = "1"
..\.venv\Scripts\python.exe -m pytest -m integration -v
Remove-Item Env:RUN_SUMO_INTEGRATION
```

注意：`pytest.ini` 的集成标记以当前仓库配置为准；如果测试模块仍有单独 skip 条件，必须检查实际输出并记录通过/跳过数量，不能将 skip 计为 pass。

## 8. 已知范围外事项

- Docker 内 SUMO/TraCI 部署仍需专项验证。
- 配时方案数据库持久化、操作审计和用户权限认证未纳入 B5。
- 右转与行人/非机动车/其他冲突流的真实动态安全验证仍是独立总体验收项。
- A1–A5 三维与双视图工作见 `docs/15-a1-a5-assessment.md`。
