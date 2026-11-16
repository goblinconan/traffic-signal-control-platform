# ADR-014：信号控制模式切换与停用安全策略

- 状态：已接受
- 决策日期：2026-11-15
- 决策参与：用户确认
- 适用阶段：B2
- 关联需求：`docs/01-requirements.md` 第 13 节

## 背景

系统必须将 SUMO 仿真生命周期、信号控制启停和 AUTO/MANUAL 控制模式分开管理。原有八阶段状态机只包含四类受保护业务阶段的绿灯和黄灯，未定义控制停用后的保持状态，也未定义 MANUAL 无新请求时的行为。

控制模式切换和控制停用不得截断正在执行的绿灯或黄灯；同时不能让 SUMO 的实际灯色与后端状态不一致。

## 决策 A：DISABLED 安全处置

用户批准以下策略：

1. 收到 DISABLED 请求后，立即拒绝新的手动阶段和配时控制命令。
2. 当前绿灯必须完成其原定时长。
3. 当前业务阶段随后执行完整黄灯，不得跳过或缩短。
4. 黄灯结束后，所有 SUMO controlled links 全部设置为红灯 `r`。
5. 全红必须覆盖全部 linkIndex，包括原本在八个正常业务阶段使用小写 `g` 的右转 linkIndex 0、5、10、15。
6. 完成全红后控制状态变为 `DISABLED`；SUMO 仿真仍保持 `RUNNING`，但信号控制状态机不再推进。
7. 如果请求到达时已经处于全红，则可以立即完成停用。

## 决策 B：MANUAL 空闲与切换行为

用户批准以下策略：

1. AUTO 切换到 MANUAL 时，不立即中断当前业务阶段。
2. 当前绿灯完成原定时长后，执行完整黄灯。
3. 黄灯结束后进入 `ALL_RED`，再将控制模式正式切换为 MANUAL。
4. MANUAL 没有新的合法人工阶段请求时，持续保持全红，不自动推进八阶段循环。
5. 合法人工阶段请求只能指定四类受保护绿灯业务阶段，不允许直接提交任意 SUMO 状态字符串。
6. MANUAL 下从全红启动目标阶段；从一个正在运行的业务阶段切换到另一个业务阶段时，必须先完成当前绿灯和完整黄灯，再经过全红后启动目标阶段。
7. MANUAL 切回 AUTO 时，如果当前已处于全红，可从确定的 `NS_LEFT` 业务阶段恢复自动循环；如果仍在业务阶段，则先安全过渡到全红，再恢复 AUTO。

## 状态模型

### 仿真生命周期

由 `SimulationLifecycle` 管理：`STOPPED`、`STARTING`、`RUNNING`、`STOPPING`、`FAILED`。

### 控制模式

由 `SignalService` 管理：`AUTO`、`MANUAL`。

### 控制启停

由 `SignalService` 管理：

- `ENABLED`：允许按当前模式控制。
- `DISABLING`：已锁定新控制命令，正在完成当前绿灯/黄灯安全过渡。
- `DISABLED`：已全红，信号控制停止推进，SUMO 继续运行。

`DISABLING` 是过渡态，不是第三种用户操作模式。

### 全红状态

`PhaseId.ALL_RED` 是控制保持状态，不属于原八个绿/黄灯周期阶段，不计入正常配时周期，也不改变原八阶段顺序。

## 重新启用与仿真重启

- DISABLED → ENABLED 且模式为 AUTO：从 `NS_LEFT` 重新启动自动循环。
- DISABLED → ENABLED 且模式为 MANUAL：继续保持全红，等待人工阶段请求。
- 每次启动新 SUMO 仿真时，控制域重置为 `ENABLED/AUTO`，阶段状态重置到本次运行的 `NS_LEFT` 初始状态。

## 并发与执行约束

- 控制命令必须通过 `SimulationLifecycle` 的操作锁执行，与后台 TraCI 步进串行化。
- 仿真不是 `RUNNING` 时，控制 API 返回 HTTP 409。
- 控制处于 `DISABLING` 时，拒绝新的模式切换和启用请求，直到当前安全过渡结束。
- 全红灯色字符串长度必须与 `getControlledLinks()` 返回的 controlled link 数量完全一致。

## 后果

优点：控制停用和 MANUAL 空闲状态都有确定、可验证的安全灯色；不会因切换操作截断黄灯；右转让行绿灯在全红保持态被明确覆盖。

代价：MANUAL 空闲期间路口所有方向均停止放行；本策略只定义信号控制软件行为，不能替代真实路口交通工程审查、冲突矩阵验证或监管审批。

## 验收证据

### 自动化测试

在独立 Python 3.14 虚拟环境中，根据 B2 的 `backend/requirements.txt` 安装依赖后执行完整测试：

- 依赖安装成功。
- `pip check`：`No broken requirements found.`
- `pytest -q`：`77 passed, 1 skipped`。
- 唯一跳过项为需要设置 `RUN_SUMO_INTEGRATION=1` 的真实 SUMO 生命周期集成测试；该测试已单独执行并通过。

### 真实 SUMO / TraCI 验证

用户 Windows 环境已使用 Eclipse SUMO 1.28.0 完成以下验证：

1. SUMO 真实进程启动、TraCI 连接、单步推进及停止清理。
2. AUTO 八个绿灯/黄灯阶段按预期顺序推进。
3. AUTO 切换 MANUAL：当前绿灯和完整黄灯结束后进入全红，继续推进仿真仍保持全红。
4. MANUAL 从全红成功启动 `EW_LEFT`，SUMO 实际灯色与预期一致。
5. DISABLED：完成当前绿灯及完整黄灯后，20 个 controlled links 全部变为红灯，SUMO 继续运行。
6. DISABLED 重新启用 AUTO：从 `NS_LEFT` 恢复自动周期。
7. DISABLED 重新启用 MANUAL：保持全红并等待人工请求。
8. 全红实际 TLS state 为 `rrrrrrrrrrrrrrrrrrrr`，长度为 20；右转 linkIndex 0、5、10、15 均为 `r`。

以上记录证明所列控制场景已在当前用户 Windows/SUMO 环境完成验证，不代表已完成浏览器 UI、生产部署或其他操作系统环境的验收。

### 验收边界

- B2 后端自动化测试及上述真实 SUMO 控制场景已有验证证据。
- 原始 B2 交付包缺少 `simulation/routes/intersection.rou.xml`；审查时已从原项目复制到暂存目录，并通过 SHA256 一致性检查。
- 尚未覆盖用户原项目工作目录，正式替换前仍须完成交付文件清单核对及备份确认。
- 本策略只定义信号控制软件行为，不能替代真实路口交通工程审查、冲突矩阵验证或监管审批。
