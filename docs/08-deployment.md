# 部署手册

> 本文记录当前开发环境准备方式。Docker 中 SUMO/TraCI 的最终部署拓扑仍待最小原型验证；本文中的命令必须在对应文件路径确认后再作为正式启动命令。

## 1. 开发环境（Windows 本机先跑通）

### 1.1 SUMO

1. 安装 SUMO 1.28.0，安装路径：`C:\Program Files (x86)\SUMO`。
2. 设置系统变量 `SUMO_HOME=C:\Program Files (x86)\SUMO`，Path 加入 `%SUMO_HOME%\bin`。
3. 验证：

```powershell
sumo --version
# 预期输出类似：Eclipse SUMO sumo 1.28.0
python -c "import os,sys; sys.path.append(os.path.join(os.environ['SUMO_HOME'],'tools')); import traci; print('traci ok')"
```

### 1.2 后端

以下命令示例假设后端依赖清单位于 `backend` 目录；执行前应核对项目实际文件路径：

```powershell
cd D:\Projects\traffic-signal-control-platform\backend
python -m venv ..\.venv
..\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 1.3 前端

```powershell
cd D:\Projects\traffic-signal-control-platform\frontend
npm install
npm run dev
```

## 2. Docker Compose

Docker Compose 当前用于验证平台服务容器化；SUMO/TraCI 是否在容器内运行尚未完成原型验证。不要把 `docker compose up -d` 的成功等同于 SUMO 仿真链路已经启动。

```powershell
cd D:\Projects\traffic-signal-control-platform
docker compose build
docker compose up -d
docker compose logs -f backend
```

当前 compose 中 `simulation` 服务先不启用，后端与本机 SUMO 的混合运行方式仍需验证。**不要假设 Windows 宿主机的 SUMO 能直接在 Linux 容器里被 import。**

待验证方案：

- 方案 A：SUMO 安装进 backend 镜像并以 headless 方式运行。
- 方案 B：使用独立 simulation 容器，通过 TCP 建立 TraCI 连接。

最终方案以可重复运行的最小原型和 Docker 集成测试为准。

## 3. 停止

```powershell
cd D:\Projects\traffic-signal-control-platform
docker compose down
```

## 4. 环境变量

见根目录 `.env.example`。不得将真实密钥或本机敏感配置提交到 Git。

## 5. 部署验收边界

- 本机 SUMO + FastAPI 的开发运行方式与 Docker 最终部署方式应分别记录和验收。
- 若采用独立 simulation 容器，必须验证 TraCI TCP 连接、启动/停止、异常退出清理及网络可达性。
- 若将 SUMO 安装进 backend 镜像，必须验证镜像内 SUMO 版本、Python `traci`/`sumolib` 导入和 headless 仿真。
- 任何部署方式均须验证后端信号状态机、8 个目标阶段、WebSocket 状态推送和车辆数据链路；容器启动成功不等于业务验收通过。
- 当前阶段顺序以南北左转、南北直行、东西左转、东西直行为准；部署配置不得继续沿用历史测试网络阶段顺序。



## 6. B3 配时与手动阶段功能部署

B3 代码包使用 `B3-apply-delivery.ps1` 进行逐文件更新。必须先在项目根目录运行默认预检，再使用 `-Apply` 正式更新；脚本会在 `temp` 下创建更新前备份并逐文件验证 SHA256。不要把 `B3-delivery` 暂存目录提交到 Git。

更新后：

```powershell
Set-Location D:\Projects\traffic-signal-control-platform\backend
..\.venv\Scripts\python.exe -m compileall -q app tests
..\.venv\Scripts\python.exe -m pip check
..\.venv\Scripts\python.exe -m pytest -q
```

启动真实 SUMO/HTTP 验收时，必须使用项目原有 Windows SUMO 1.28.0 环境；B3 的配时 API 和手动阶段 API 只能在仿真 RUNNING 时调用。详细请求、预期响应和安全检查见 `docs/11-b3-timing-and-manual-control.md`。

B3 当前不引入数据库表迁移，active/pending 配时在进程内管理。重启 FastAPI 后会从 `Settings` 默认值重新初始化；PostgreSQL 配时持久化和操作审计不属于本次 B3 交付。B4 的 REST/WS 统一状态模型及 B5 浏览器操作台仍是后续阶段。
