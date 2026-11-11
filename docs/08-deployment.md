# 部署手册

## 1. 开发环境（Windows 本机先跑通）

### 1.1 SUMO

1. 安装 SUMO 1.28.0，安装路径：`C:\Program Files (x86)\SUMO`。
2. 设置系统变量 `SUMO_HOME=C:\Program Files (x86)\SUMO`，Path 加入 `%SUMO_HOME%\bin`。
3. 验证：

````powershell
sumo --version
# 预期输出类似：Eclipse SUMO sumo 1.28.0
python -c "import os,sys; sys.path.append(os.path.join(os.environ['SUMO_HOME'],'tools')); import traci; print('traci ok')"

### 1.2 后端

```powershell
cd D:\Projects\traffic-signal-control-platform
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
````

### 1.3 前端

```bash
cd frontend
npm install
npm run dev
```

## 2. Docker Compose

```bash
docker compose build
docker compose up -d
docker compose logs -f backend
```

当前 compose 中 `simulation` 服务先不启用，后端以“本机 SUMO + 容器后端”的混合方式运行。**不要假设 Windows 宿主机的 SUMO 能直接在 Linux 容器里被 import**。等验证完成后再决定：

- 方案 A：SUMO 装进 backend 镜像，headless 运行；
- 方案 B：独立 simulation 容器，TraCI 走 TCP。

## 3. 停止

```bash
docker compose down
```

## 4. 环境变量

见根目录 `.env.example`。
