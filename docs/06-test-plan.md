# 测试计划

## 1. 分层

| 层       | 工具                                                 | 范围                                                |
| -------- | ---------------------------------------------------- | --------------------------------------------------- |
| 单元测试 | pytest                                               | `TimingService`、`SignalStateMachine`、倒计时可见性 |
| 接口测试 | FastAPI TestClient + dependency_overrides mock TraCI | 启动/停止/查状态/改配时                             |
| 集成测试 | 真实 SUMO headless                                   | 状态机与 SUMO 信号字符串一致                        |
| 前端     | Vitest + Testing Library                             | 倒计时显示、WebSocket 消息渲染                      |

## 2. 必须覆盖的用例

1. 南北绿灯 30、南北黄灯 3、东西绿灯 30、东西黄灯 3 → 南北红灯 33、东西红灯 33，均 >10。
2. 绿灯剩余 9→8→7 时 `countdown_visible` 从 false 变 true。
3. 红灯剩余 11→10→9 时 `countdown_visible` 从 false 变 true。
4. 黄灯全程 `countdown_visible=true`。
5. 手动从 `NS_GREEN` 切 `EW_GREEN` → 409。
6. 修改配时把南北绿灯改成 5 → 400。
7. 修改配时使东西红灯 = 10 → 400（因为要求 >10）。
8. 运行中修改配时，当前阶段 `remaining` 不被截断，新值在下一周期对应阶段生效。
9. WebSocket 重连后收到完整状态快照，不是增量。

## 3. 集成测试命令

```bash
cd backend
pytest tests/ -v --cov=app
```

真实 SUMO 集成测试标记 `@pytest.mark.integration`，默认跳过，用 `pytest -m integration` 单独运行。
