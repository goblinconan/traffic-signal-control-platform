# B4 / B5 需求与 B3 代码基线核对报告

- 核对日期：2026-11-17
- 核对基线：`B3-complete`，提交 `b493da1df6e06a41674b0dd9a376a19fc7dff5f2`
- 代码包：B4 review package 内层 `traffic-signal-control-platform-B4-baseline.zip`
- 目的：确定 B4 的实现边界，并为 B5 浏览器控制台准备准确需求基线。

## 1. 基线完整性

上传的外层 ZIP 包含 `B4-baseline-info.txt` 和 B3 基线 ZIP；内层 ZIP 可正常读取，共 106 个条目。`B4-baseline-info.txt` 中 `f084...` 是附注标签对象哈希；用户本机 `git rev-parse "B3-complete^{}"` 返回 `b493da1...`，与当前 HEAD 及已推送正式提交一致。

ZIP 仅导出 Git 已跟踪文件；未跟踪交付包、备份和 temp 资料不属于代码基线，不纳入 B4 修改。

## 2. B4 需求来源与边界

正式阶段来源：`docs/02-architecture.md` 第 22 节将 B4 定义为“定义 REST/WS 统一状态模型”；`docs/01-requirements.md` 第 6.4 节、第 5.2 节和第 13 节要求后端权威状态、WebSocket 实时同步、仿真/控制/模式解耦；`docs/04-api-design.md` 第 7 节定义首次完整快照、动态更新、静态网络分离、重连快照及 sequence/tick 防过期。

B4 必须交付：

1. 一套前后端可共享的字段契约和版本号。
2. REST 完整运行状态快照，与 WS snapshot/update 复用相同动态字段。
3. 生命周期、信号控制、四类信号组、右转策略、配时 active/pending/version、车辆快照。
4. 首次连接/重连完整快照；动态消息单调 sequence；前端丢弃重复/过期消息。
5. 静态路网与高频动态状态分离，并以 network_version 绑定。
6. 运行中状态采样与 TraCI step/control 串行化。
7. 生命周期停止/失败变化也能通知浏览器，不能保留过期 RUNNING。
8. 兼容现有 B1–B3 API 和信号安全规则。

B4 不实现控制台操作 UI，不改变 B3 控制器。

## 3. B3 基线现状与差距

| 领域 | B3 基线现状 | B4 处理 |
|---|---|---|
| REST 状态 | 仿真、信号、控制、配时分散接口；无统一快照 | 新增 `/api/simulation/state` |
| WS 首条消息 | 使用 `simulation_update`，带网络几何 | 明确 `simulation_snapshot` |
| WS 动态消息 | 后台 `_payload` 不带序号 | 统一结构并带 sequence |
| 重连 | 连接时重新发送初始 payload，但无快照语义和版本同步 | 每次重连首条完整 snapshot |
| 过期消息 | 无 sequence 防护 | 后端递增、前端拒绝倒退/重复 |
| 静态路网 | 首条 WS 带 geometry，动态消息不带 | 独立 network REST 资源和 SHA256 版本 |
| 状态字段 | 缺 lifecycle 详情、pending 配时、group 列表等 | 统一 Pydantic 模型 |
| TraCI 一致性 | lifecycle 已串行化 step/control；快照组合读取未走 lifecycle 锁 | 新增 read_state 受同一操作锁保护 |
| 停止/失败广播 | 仅 RUNNING 时广播，停止后可能残留旧 UI 状态 | 生命周期状态变化时发送 update |
| 前端 | 只解析旧 `signal` 结构，未校验序号 | 使用统一 `signal_control` 和 sequence guard |

## 4. B5 需求范围

正式需求来源：`docs/01-requirements.md` 第 14 节及第 16.2 节；架构实施顺序见 `docs/02-architecture.md` 第 22 节。B5 是浏览器信号控制操作台，至少包括：

- 仿真启动、停止及 STOPPED/STARTING/RUNNING/STOPPING/FAILED 状态、SUMO 连接和错误反馈。
- 信号控制 ENABLED/DISABLING/DISABLED 展示与启停。
- AUTO/MANUAL 模式展示与切换。
- 当前阶段、下一阶段、四类信号组灯色和剩余时间展示。
- MANUAL 合法阶段选择、提交、接受/拒绝原因及安全过渡状态展示。
- 四类绿灯/黄灯配时编辑、提交、active/pending 版本和生效时机展示。
- 所有操作经过既有 REST API，由后端实施状态和安全校验；前端不直接写 SUMO 灯色。

B3 已有控制 REST API，B4 提供统一状态协议；B5 主要新增前端控制面板、表单校验、操作反馈和端到端测试，不应复制信号控制状态机到浏览器。

## 5. B5 与三维 A1–A5 的范围区别

当前正式架构把 B5 定义为浏览器控制面板；A1–A5 是另行编号的静态路网几何、Three.js 场景、道路/车道/车辆/信号灯渲染、双视图接入及性能一致性验收。虽然需求文档第 15 节将二维/三维可视化列为总体需求，但架构实施阶段明确把 A1–A5 与 B4/B5 分列。故本次不把三维开发擅自塞进 B5；如项目最终交付必须同时包含三维，应在 B5 控制台完成后继续执行 A1–A5。

## 6. 非 B4/B5 当前遗留范围

- PostgreSQL 配时方案持久化、控制操作审计表和权限认证：B3 ADR-015 明确未包含，B4/B5 也未定义为必做项，需另行立项/确认。
- Docker 内 SUMO/TraCI 部署：现有文档仍标记待验证。
- 右转与行人/非机动车及其他冲突流的真实动态安全验证：仍是总体验收项，不可由静态 `g` 或 B4 数据结构代替。
- 对向左转同时放行的真实冲突矩阵：需独立交通仿真验证。

## 7. B4 交付文件范围

B4 修改/新增文件清单由 `B4-DELIVERY-README.md` 和 `B4-file-manifest.sha256` 精确列出。B4 不应覆盖整个项目目录；仅备份并替换清单内文件。
