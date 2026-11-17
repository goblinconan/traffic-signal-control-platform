# 测试计划

> 版本：V2.1
> 对应需求：`docs/01-requirements.md`
> 对应仿真设计：`docs/05-simulation-design.md`

## 1. 测试分层

| 层级       | 工具                            | 范围                                                   |
| ---------- | ------------------------------- | ------------------------------------------------------ |
| 单元测试   | pytest                          | 配时计算、`SignalStateMachine`、倒计时可见性、冲突校验 |
| 接口测试   | FastAPI TestClient + mock TraCI | 仿真启停、状态查询、模式/控制启停、手动阶段、配时      |
| 集成测试   | 真实 SUMO headless              | controlled links、8 个 SUMO 阶段、车辆停车/让行        |
| 前端测试   | Vitest + Testing Library        | 倒计时、控制台、WebSocket、二维/三维切换               |
| 端到端测试 | 浏览器 + 真实 SUMO              | 信号、车辆、右转让行和实时展示闭环                     |

## 2. 配时与倒计时测试

当前 SUMO 测试基线：

- 南北直行绿/黄：40s / 3s。
- 南北左转绿/黄：20s / 3s。
- 东西直行绿/黄：40s / 3s。
- 东西左转绿/黄：20s / 3s。

不设置额外全红阶段时，周期为 132 秒；南北/东西直行红灯各 89 秒，南北/东西左转红灯各 109 秒，均大于 10 秒。该组数据用于配时计算测试，不代表最终交通配时。

必须覆盖：

1. 四类绿灯分别为 8 秒或更短时，配置拒绝。
2. 四类黄灯分别为 0 秒或负值时，配置拒绝。
3. 任一计算红灯总时长为 10 秒或更短时，配置拒绝。
4. 绿灯剩余时间 9→8→7 秒时，`countdown_visible` 从 false 变为 true。
5. 红灯剩余时间 11→10→9 秒时，`countdown_visible` 从 false 变为 true。
6. 黄灯全程 `countdown_visible=true`，且倒计时不跳过 3、2、1。
7. 配时修改不缩短当前阶段剩余时间。
8. 待生效方案在规定安全周期边界整体生效，同一周期不得混用版本。
9. 若后续增加全红清空阶段，周期长度和四类红灯计算测试必须同步更新。
10. 旧双相位红灯公式不得再被调用。

## 3. 八个 SUMO 阶段与冲突测试

### 3.1 阶段顺序

1. 按 `0→1→2→3→4→5→6→7→0` 顺序推进。
2. 阶段 0/1 对应 `NS_LEFT_GREEN` / `NS_LEFT_YELLOW`。
3. 阶段 2/3 对应 `NS_STRAIGHT_GREEN` / `NS_STRAIGHT_YELLOW`。
4. 阶段 4/5 对应 `EW_LEFT_GREEN` / `EW_LEFT_YELLOW`。
5. 阶段 6/7 对应 `EW_STRAIGHT_GREEN` / `EW_STRAIGHT_YELLOW`。
6. 每个黄灯阶段必须完整执行配置时长。
7. 手动请求不能跳过或缩短黄灯阶段。

### 3.2 保护式左转

1. 南北左转绿灯期间，南北直行连接必须为红灯。
2. 东西左转绿灯期间，东西直行连接必须为红灯。
3. 南北两个相反方向左转同时放行，且目标网络冲突矩阵确认无冲突。
4. 东西两个相反方向左转同时放行，且目标网络冲突矩阵确认无冲突。
5. 不同受保护阶段之间不得出现冲突性优先放行。
6. 逐个验证 `linkIndex` 的业务转向、信号组和实际 SUMO 灯色；字符串长度匹配不能代替语义验证。

## 4. 车道与右转让行测试

1. 四个进口方向均具有独立左转、直行、右转车道。
2. 任何进口车道不得同时承载左转与直行、左转与右转或直行与右转业务。
3. 四个右转连接（linkIndex 0、5、10、15）在全部八个 SUMO 阶段均应设置为小写 `g`。
4. 右转连接不得被误设为大写 `G`，不得获得受保护绿灯或无条件优先通行权。
5. 右转车辆在任意信号阶段接近冲突区域时均应减速观察。
6. 行人处于右转冲突区域时，右转车辆必须停车等待。
7. 非机动车处于右转冲突区域时，右转车辆必须停车等待。
8. 其他冲突车辆具有优先权时，右转车辆停车或减速让行。
9. 冲突解除后，右转车辆能够继续通行。
10. 必须分别验证右转信号静态配置和车辆动态让行行为，不能只检查配置文件或 TLS 灯色。
11. 右转车道、转向连接和让行行为必须通过真实 SUMO 车辆仿真验证，并保留测试日志及车辆轨迹证据。

## 5. AUTO/MANUAL 与控制启停测试

1. AUTO 模式按仿真时间自动推进 8 个 SUMO 阶段。
2. MANUAL 模式只接受合法业务阶段请求。
3. 手动请求必须通过后端校验和安全过渡。
4. 仿真 STOPPED 时拒绝手动阶段请求。
5. 控制 DISABLED 时拒绝新的手动阶段及配时控制请求。
6. AUTO/MANUAL 切换不能截断当前黄灯。
7. 禁用和重新启用控制后，后端与 SUMO 状态重新核对。
8. 连续/并发 start、stop、mode、manual 请求不会造成状态损坏。
9. AUTO→MANUAL 必须等待当前绿灯和完整黄灯结束后进入 ALL_RED；无请求时持续全红。
10. DISABLED 必须在当前绿灯和完整黄灯结束后将全部 20 个 controlled links（包括 4 个右转 linkIndex）置为 `r`，且 SUMO 继续 RUNNING。
11. DISABLED 时手动阶段与配时请求返回拒绝；重新启用 AUTO 恢复 NS_LEFT，重新启用 MANUAL 保持全红。
12. 每次新仿真启动重置为 ENABLED/AUTO，避免上一轮运行状态污染。

## 6. B3 配时与手动阶段安全应用专项

- `test_signal_controller.py`：四类独立黄灯时长、红灯周期计算、黄灯边界与倒计时。
- `test_signal_service.py`：AUTO 完整周期应用 pending；MANUAL 全红时立即应用；MANUAL 活动阶段修改配时后只在全红边界应用；手动阶段切换实际向 SUMO 下发全红并至少保持一个 step。
- `test_signal_control_api.py`：完整八字段配时请求、缺字段/未知字段/非法时长拒绝、配时查询与版本、手动请求 accepted/status/reason。
- 手动阶段 API 只能在仿真 RUNNING、控制 ENABLED、模式 MANUAL 时接受合法目标；不得接受黄灯阶段、ALL_RED 或任意字符串。
- API 失败不得改变 active/pending 配时、当前阶段或 SUMO 灯色。
- 本阶段配时版本仅由进程内服务管理；数据库持久化和操作审计表不在 B3 代码包验收范围，必须单独标记为后续工作。

## 7. B2 控制域专项测试

- `test_signal_controller.py`：ALL_RED 终态保持及显式恢复。
- `test_signal_service.py`：停用安全过渡、右转全红、AUTO→MANUAL、MANUAL 空闲全红、手动请求经全红过渡、重新启用和新仿真状态重置。
- `test_signal_control_api.py`：控制状态查询、启停与模式接口。
- `test_network_geometry.py`：SUMO net.xml 几何解析及缺失文件处理。

## 8. WebSocket 与前端测试

1. 首次连接收到完整状态快照。
2. 重连收到最新完整快照。
3. sequence/tick 过期消息不会覆盖新状态。
4. 动态消息不重复传输完整网络几何。
5. 仿真状态、控制模式、控制启停状态、四类信号组灯色及右转让行状态同步更新。
6. 浏览器不自行计算信号阶段切换和权威倒计时。
7. 二维原有展示回归通过。
8. 三维道路、车道、停止线几何与 SUMO 网络匹配。
9. 同一仿真 tick 下二维和三维车辆位置、灯色和阶段一致。
10. 切换视图不重启仿真、不改变控制模式。

## 9. 已知问题回归

- `Missing yellow phase` 警告必须定位到具体 `linkIndex` 和 from/to connection。
- 验证不存在绿灯直接转红灯、黄灯被跳过或黄灯持续时间错误。
- 重新生成网络后，必须重新核验全部 controlled links 和信号状态字符串。
- 保留已验证左转路线，避免车道结构修改导致左转车流消失。

## 10. 测试命令与证据

单元及接口测试：

```powershell
cd backend
pytest tests/ -v --cov=app
```

真实 SUMO 集成测试使用 `@pytest.mark.integration` 标记；默认可跳过，执行：

```powershell
pytest -m integration -v
```

每项标记为通过时，至少保留一种可复核证据：pytest 输出、API 请求/响应、SUMO 日志、浏览器录屏/截图或明确的人工验收记录。仅有代码存在或静态配置存在不视为验收通过。

## 11. B1仿真生命周期管理专项

B1自动化测试文件：

- `backend/tests/test_simulation_lifecycle.py`：状态转换、重复操作、启动/步进/停止异常、并发启动、关闭等待正在执行的 step。
- `backend/tests/test_sumo_runner_lifecycle.py`：TraCI优雅关闭等待、关闭异常后的进程终止、外部进程退出识别；真实SUMO集成测试默认跳过。
- `backend/tests/test_simulation_api.py`：status/start/stop、409重复启动和幂等停止。
- `backend/tests/test_main_lifespan.py`：FastAPI lifespan 等待后台 step 完成后再停止 Runner。

验收要求：

1. STOPPED → STARTING → RUNNING → STOPPING → STOPPED 成功。
2. RUNNING重复start返回HTTP 409；STOPPED重复stop幂等。
3. 启动、步进、停止异常进入FAILED并保留错误。
4. 应用关闭先停止后台循环接收新步进，等待当前TraCI工作线程完成，再执行统一shutdown。
5. 优雅关闭使用 `traci.close(wait=True)`；若关闭失败，尝试terminate/kill，并确认子进程退出。
6. 外部结束SUMO后，status/health检查或下一次step能将生命周期更新为FAILED。
7. 默认pytest全部通过；设置 `RUN_SUMO_INTEGRATION=1` 后执行真实SUMO启停集成测试。

FakeRunner和模拟Popen测试不替代用户本机的真实SUMO进程验收；本机还必须执行10次REST启停循环及外部强制终止测试。


## 12. B4 REST / WebSocket 统一状态协议专项

自动化测试新增：

- `backend/tests/test_runtime_state.py`：统一快照字段、序号、阶段映射、控制状态、配时版本、车辆和 network_version。
- `backend/tests/test_websocket.py`：首次连接发送 simulation_snapshot、断开清理及重连快照语义。
- `backend/tests/test_b4_sumo_state_integration.py`：真实 SUMO 运行时统一快照、实际 TLS、controlled-links 和网络版本。
- `backend/tests/test_runtime_state_api.py`：REST `/api/simulation/state` 与静态网络资源接口。

本机验收还应验证：

1. WebSocket 连接时先收到 `simulation_snapshot`，随后收到 `simulation_update`。
2. 连续消息 sequence 严格递增；客户端重复/倒序消息不覆盖最新状态。
3. 浏览器断开后重新连接，首条消息仍是完整快照。
4. 停止仿真后，客户端收到 STOPPED 更新且车辆数组为空。
5. 修改 net.xml 内容后 network_version 改变；动态 WS 消息不携带 geometry。
6. REST 快照与同一仿真时刻的 WS 消息在 lifecycle/control/timing/groups 字段语义一致。
7. B3 原有安全控制测试和真实 SUMO 专项回归通过。
