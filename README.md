# Traffic Signal Control Platform

单路口交通信号控制仿真平台：SUMO + FastAPI + TraCI + React + TypeScript + Vite。

## 阶段状态

- B0–B3：已完成既定实现；真实交通冲突与右转让行仍有专项验收项。
- B4：已发布 `B4-complete`，commit `f2052b539ce9c50782a25b50471c4725874d8b8e`。
- B5：本交付增加浏览器控制台代码；须在 Windows + SUMO 环境构建、部署并完成真实联调后才能标记完成。
- A1–A5：待实施；现状与估算见 `docs/15-a1-a5-assessment.md`。

## 部署 B5

1. 将交付 ZIP 解压到任意临时目录。
2. 在项目根目录运行解压目录中的 `B5-apply-delivery.ps1`（默认目标为 `D:\Projects\traffic-signal-control-platform`）。
3. 按 `docs/14-b5-browser-control-console.md` 执行后端测试、前端构建、服务启动和浏览器验收。

## 本机开发运行

后端：

```powershell
Set-Location D:\Projects\traffic-signal-control-platform\backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

前端（另开终端）：

```powershell
Set-Location D:\Projects\traffic-signal-control-platform\frontend
npm ci
npm run dev
```

浏览器：`http://127.0.0.1:5173/`。API 文档：`http://127.0.0.1:8000/docs`。

只读 API 冒烟测试：

```powershell
Set-Location D:\Projects\traffic-signal-control-platform
powershell -ExecutionPolicy Bypass -File .\scripts\Test-B5-Api.ps1
```

## 安全边界

浏览器只调用现有 REST 业务接口，不直接写入 SUMO 灯色。仿真生命周期、控制启停、AUTO/MANUAL、黄灯过渡、ALL_RED、人工阶段和配时生效边界均由后端权威控制。
