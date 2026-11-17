# traffic-signal-control-platform

单路口交通信号控制仿真平台：SUMO + FastAPI + React + PostgreSQL。

## 当前阶段

- B0：八阶段信号映射及 SUMO 安全基线。
- B1：仿真生命周期管理。
- B2：AUTO/MANUAL 与信号控制启停安全。
- B3：独立绿/黄灯配时、版本管理和人工阶段安全切换；已完成本机验收，标签 `B3-complete`。
- B4：REST / WebSocket 统一运行状态协议；实现候选，待本机验收，见 `docs/12-b4-unified-runtime-state.md`。
- B5：浏览器信号控制面板，见 `docs/01-requirements.md` 第 14 节。

## 本机启动

### 后端

```powershell
Set-Location D:\Projects\traffic-signal-control-platform\backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

API 文档：`http://127.0.0.1:8000/docs`。

### 前端

```powershell
Set-Location D:\Projects\traffic-signal-control-platform\frontend
npm install
npm run dev
```

默认 Vite 地址：`http://127.0.0.1:5173`。开发代理将 `/api` 和 `/ws` 转发至本机后端。

## B4 新增接口

- `GET /api/simulation/state`：REST 完整运行状态快照。
- `WS /ws/simulation`：首条消息为 `simulation_snapshot`，后续为 `simulation_update`。
- `GET /api/intersections/{intersection_id}/network`：静态路网及 SHA256 版本。

## Docker

Docker Compose 仍是部署目标；当前 B4 交付验收以用户 Windows + SUMO 1.28.0 本机环境为准。Docker 内 SUMO/TraCI 部署仍需单独验证。
