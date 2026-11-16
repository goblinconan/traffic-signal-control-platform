# ADR-015：B3 配时版本与 MANUAL 阶段安全应用

- 状态：已接受（B3 实施决策）
- 决策日期：2026-11-16
- 适用阶段：B3
- 关联文档：`docs/01-requirements.md`、`docs/02-architecture.md`、`docs/04-api-design.md`

## 背景

B2 已提供 AUTO/MANUAL、控制启停和手动阶段请求的基础安全控制。审查 B2 代码发现：

1. `TimingConfig` 仍使用一个共享 `yellow` 字段，与需求中的四类独立黄灯不一致。
2. 配时 pending 只在 AUTO 完整周期边界提升；MANUAL 不自动轮转，因此 pending 可能永远不生效。
3. MANUAL 切换目标时，原实现会在同一次 `SignalService.step()` 中进入 ALL_RED 后立即启动目标阶段，最终只下发目标绿灯，SUMO 没有实际观察到 ALL_RED。

## 决策 A：八字段配时模型

四类受保护信号组各自配置绿灯和黄灯：

- `ns_left_green` / `ns_left_yellow`
- `ns_straight_green` / `ns_straight_yellow`
- `ew_left_green` / `ew_left_yellow`
- `ew_straight_green` / `ew_straight_yellow`

约束：绿灯 > 8 秒、黄灯 > 0 秒、四类红灯总时长分别 > 10 秒。周期和红灯时长由完整八阶段顺序计算，不接受客户端提交红灯时长。

PUT timing 必须完整提交八个字段；缺字段、未知字段和非法值返回 422，不能改变 active/pending 方案。

## 决策 B：待生效方案和版本

- 后端运行时保留一个 active 和至多一个 pending 配时方案。
- 每次不同于 active 的有效提交分配 `pending_timing_version = timing_version + 1`；新 pending 替换旧 pending。
- 再次提交当前 active 配时用于撤销 pending。
- AUTO：只在完整八阶段周期边界（EW_STRAIGHT_YELLOW 完成并进入下一轮 NS_LEFT）整体提升 pending。
- MANUAL：如果当前处于 ALL_RED，立即应用；如果当前正在执行业务阶段，在当前绿灯和完整黄灯完成并进入 ALL_RED 后应用。
- 应用新方案不重置当前阶段的已开始时间；只有安全边界之后新启动的阶段使用新时长。

## 决策 C：MANUAL 全红必须真实保持

- 从当前业务阶段切换到另一业务阶段时，当前绿灯完成原定时长，随后完整执行当前黄灯。
- 到达 ALL_RED 后立即向 SUMO 下发全红状态。
- ALL_RED 至少保持一个完整仿真 step。
- 下一次仿真 step 才能启动 pending 目标阶段。
- 请求当前已经运行的目标阶段时作为 no-op 成功，不触发全红切换。
- 非法目标、非 MANUAL、控制未启用或仿真未运行均拒绝。

## 决策 D：B3 范围边界

本次 B3 实现配时校验、active/pending 版本、API 契约和手动阶段安全应用。当前配时状态只存在于后端进程内，FastAPI 进程重启后从 Settings 默认值重新初始化。

PostgreSQL `timing_plan` 持久化、`signal_operation_log` 审计表、用户权限认证和浏览器控制台 UI 不在本次 B3 交付范围。它们不得被描述为已完成；B4 处理 REST/WS 统一状态模型，B5 处理浏览器操作台，数据库持久化需单独规划和验收。

## 验收

- 单元/接口测试验证八字段、红灯计算、版本提升、AUTO/MANUAL 安全边界和 ALL_RED step 保持。
- 用户 Windows/SUMO 1.28.0 环境仍须执行 B3 部署指南中的真实 SUMO/API 验收；沙盒 pytest 不替代本机验收。
