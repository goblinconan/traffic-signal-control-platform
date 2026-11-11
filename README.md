# traffic-signal-control-platform

单路口交通信号控制仿真平台：SUMO + FastAPI + React + PostgreSQL。

## 当前进度

- [x] 文档 00–08
- [x] 后端信号状态机 + REST + WebSocket 骨架
- [x] 前端 SVG 路口 + 信号状态展示骨架
- [ ] OSM 实际路口网络替换
- [ ] 配时修改运行时生效验证
- [ ] Docker SUMO 部署验证

## 启动

### 1. 本机 SUMO 验证

```powershell
sumo --version
# 预期：Eclipse SUMO sumo 1.28.0
echo $env:SUMO_HOME
# 预期：C:\Program Files (x86)\SUMO
```

### 2. 后端

```powershell
cd D:\Projects\traffic-signal-control-platform
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

打开 `http://127.0.0.1:8000/docs`。

### 3. 前端

```bash
cd frontend
npm install
npm run dev
```

打开 `http://127.0.0.1:5173`。

### 4. Docker

```bash
copy .env.example .env
docker compose up -d --build
```

前端 `http://localhost:3000`，后端 `http://localhost:8000/docs`。

## 项目结构

```
backend/app/         FastAPI + 信号控制 + TraCI
frontend/src/        React + SVG 可视化
simulation/          SUMO 网络、路由、配置
database/migrations/ Alembic
docs/                需求、架构、设计、日志、部署
```

## 停止

```bash
# 本机
Ctrl+C

# Docker
docker compose down
```
