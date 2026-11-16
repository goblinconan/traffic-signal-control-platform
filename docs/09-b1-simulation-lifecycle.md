# B1：仿真生命周期管理 — 统一实施与验收基线

> 版本：2026-11-14（本轮整体复审）
> 状态：自动化测试及真实 SUMO 基础生命周期验证通过；剩余本机验收项待完成
> 范围：SUMO/TraCI 启动、停止、步进协调、状态查询、异常识别、应用关闭清理
> 不包含：B2 AUTO/MANUAL、信号控制启停；B3 配时和手动阶段功能；右转安全验收

## 1. B1验收目标

1. FastAPI 可启动 SUMO 并完成信号服务初始化。
2. 仿真状态准确表达 STOPPED、STARTING、RUNNING、STOPPING、FAILED。
3. 重复启动返回冲突；重复停止幂等。
4. start、stop、step 通过同一异步锁串行化。
5. 任何 `asyncio.to_thread` 工作在取消传播前都必须真正结束，不能在释放协调锁后继续访问 TraCI。
6. FastAPI lifespan 关闭时先通知后台循环退出，等待当前 step 完成，再执行统一 shutdown。
7. 优雅关闭等待 SUMO 进程退出；优雅关闭失败时执行进程终止回退，并核验子进程已退出。
8. 外部强制结束 SUMO 后，状态检查或下一次步进能够进入 FAILED 并记录原因。
9. REST API 提供可复核状态和错误信息。
10. 单元、Runner、API 和真实 SUMO 集成测试覆盖关键路径。

## 2. 状态模型与操作规则

| 状态     | 含义                         | 规则                                 |
| -------- | ---------------------------- | ------------------------------------ |
| STOPPED  | 未启动或已完成清理           | 允许 start；stop 幂等                |
| STARTING | 启动 SUMO / 初始化信号服务   | 拒绝重复 start                       |
| RUNNING  | TraCI 已连接，服务初始化完成 | 允许 step / stop                     |
| STOPPING | 正在关闭 TraCI / SUMO        | 由生命周期锁串行化                   |
| FAILED   | 启动、步进、连接或清理失败   | 保留错误；先 stop 清理，再重试 start |

状态所有权属于 `SimulationLifecycle`。`SumoRunner.connected` 和 `process_alive` 是底层事实，不代替生命周期状态。

## 3. 线程与关闭顺序

- 所有 TraCI 访问由 Runner 的 `threading.RLock` 保护。
- 生命周期的 start、stop、step、health refresh 使用同一 `asyncio.Lock`。
- 阻塞 TraCI 调用通过 `asyncio.to_thread` 执行。
- 线程调用采用 shield + 等待底层任务完成的取消处理，避免取消协程后线程继续使用连接。
- lifespan 关闭顺序固定为：设置 stop event → 等待后台循环任务结束 → `lifecycle.shutdown()` → `runner.stop()`。
- 不得通过直接 `task.cancel()` 来停止正在执行 TraCI step 的后台循环。

## 4. SUMO进程清理策略

当前项目依赖固定为 `traci==1.28.0`。Runner 使用 `subprocess.Popen` 启动 SUMO，保存子进程句柄，再通过 `api.connect()` 建立 TraCI 连接。连接对象在执行 `getVersion()` 握手前即保存到 Runner，因此即使握手失败，Runner 仍持有可回收的连接对象和进程句柄。

关闭时：

1. 调用当前连接对象的 `connection.close(wait=False)`，发起 TraCI 连接关闭，不依赖该调用等待 SUMO 子进程退出。
2. 独立关闭连接底层 Socket，并清理 TraCI 连接池中属于当前 Runner 的连接；不误删其他 Runner 的连接。
3. 尝试调用 SUMO 子进程的 `terminate()`，并通过 `wait(timeout=5)` 等待最多 5 秒。
4. 若进程仍未退出，调用 `kill()` 并再次等待最多 5 秒。
5. 只有确认进程退出、连接 Socket 和 TraCI 连接池清理完成后，才释放对应资源引用。
6. 若进程仍存活或 TraCI 资源仍未清理，保留必要的资源引用并抛出异常，生命周期不得伪装成 STOPPED。

说明：端口通过本机临时端口分配；端口释放到 SUMO 监听之间存在极短的本机端口竞争窗口，真实 Windows 环境仍需集成测试。TraCI 的 `api.connect(..., proc=...)` 调用及其参数应与项目锁定的 1.28.0 版本保持一致。

## 5. REST契约

### GET `/api/simulation/status`

```json
{
  "status": "running",
  "lifecycle_status": "RUNNING",
  "simulation_time": 12.5,
  "sumo_connected": true,
  "step_index": 25,
  "process_alive": true,
  "last_error": null
}
```

`status` 是小写兼容字段；`lifecycle_status` 是规范枚举。`step_index` 为当前运行成功执行的 TraCI 步数。`process_alive` 来自 Runner 保存的进程句柄。

### POST `/api/simulation/start`

- 正常启动：200，返回 RUNNING 快照。
- 已启动、正在启动或正在停止：409。
- SUMO 启动或信号服务初始化失败：503，生命周期进入 FAILED 并尝试清理。

### POST `/api/simulation/stop`

- 正常停止：200，返回 STOPPED。
- 已停止：200，幂等返回 STOPPED。
- 清理失败或进程仍存活：503，生命周期进入 FAILED。

## 6. 自动化测试

| 文件                                 | 覆盖范围                                                                                      |
| ------------------------------------ | --------------------------------------------------------------------------------------------- |
| `test_simulation_lifecycle.py`       | 状态转换、重复操作、异常、并发启动、shutdown 等待 step                                        |
| `test_sumo_runner_lifecycle.py`      | TraCI 连接非阻塞关闭、Socket 与连接池清理、进程终止回退、外部进程退出识别、真实 SUMO 集成测试 |
| `test_simulation_api.py`             | 状态查询、启动、409、停止及幂等停止                                                           |
| `test_main_lifespan.py`              | FastAPI lifespan 关闭流程、等待进行中的 step 完成后再清理 Runner                              |
| `test_simulation_api_concurrency.py` | 并发 HTTP 启动请求的串行化及 Runner 单次启动保护                                              |
| 既有信号测试                         | 回归八阶段顺序、映射和信号服务行为                                                            |

默认运行：

```powershell
Set-Location D:\Projects\traffic-signal-control-platform\backend
..\.venv\Scripts\python.exe -m pytest -q
```

真实 SUMO 集成测试：

```powershell
$env:RUN_SUMO_INTEGRATION = "1"
..\.venv\Scripts\python.exe -m pytest tests\test_sumo_runner_lifecycle.py -m integration -v
Remove-Item Env:RUN_SUMO_INTEGRATION
```

## 7. 用户本机验收清单

- [ ] 默认 pytest 全部通过，集成测试按预期跳过。
- [ ] 真实 SUMO 集成测试启动、step、stop 成功。
- [ ] 初始 status 为 STOPPED。
- [ ] start 后 RUNNING、sumo_connected=true、process_alive=true。
- [ ] 重复 start 返回 409。
- [ ] 仿真时间及 step_index 递增。
- [ ] stop 后 STOPPED、sumo_connected=false、process_alive=false。
- [ ] 重复 stop 仍为 STOPPED。
- [ ] 连续执行 10 次 REST start/stop，无遗留 sumo.exe。
- [ ] 运行中通过任务管理器结束 sumo.exe，状态在 health/status 或下一次 step 后进入 FAILED，并记录错误。
- [ ] 关闭 FastAPI 时，先结束后台 step，再关闭 SUMO；进程退出。
- [ ] stop 清理失败时不能返回成功 STOPPED。

每项必须保留 pytest 输出、API 响应、日志或进程检查结果。未执行项标记为待验证。

## 8. B1范围边界

B1通过只证明 SUMO 生命周期管理达到本阶段验收目标，不代表 B0 所有交通安全项目完成，也不代表 B2 控制启停/AUTO/MANUAL 已实现。右转小写 `g` 的让行安全验证仍是独立事项。
