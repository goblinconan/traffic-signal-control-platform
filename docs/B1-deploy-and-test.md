# B1 部署与验收操作指南

本文件是当前 B1 唯一有效的本机部署指南。B1设计与验收基线见 `09-b1-simulation-lifecycle.md`。

## 1. 替换文件

从项目根目录解压本次交付包，按包内目录覆盖同名文件。新增文件包括：

- `backend/tests/test_sumo_runner_lifecycle.py`
- `backend/tests/test_simulation_api.py`
- `backend/pytest.ini`

替换文件包括：

- `backend/app/simulation/sumo_runner.py`
- `backend/app/simulation/lifecycle.py`
- `backend/app/api/routes/simulation.py`
- `backend/app/main.py`
- `backend/tests/test_simulation_lifecycle.py`
- `docs/00-project-overview.md`
- `docs/04-api-design.md`
- `docs/06-test-plan.md`
- `docs/07-development-log.md`
- `docs/09-b1-simulation-lifecycle.md`
- `docs/B1-deploy-and-test.md`

本包不修改 SUMO 网络、路线、信号服务、控制器、前端、数据库或依赖版本。

## 2. 备份

替换前在项目根目录执行：

```powershell
$backup = ".\temp\backup-B1-before-2026-11-14-review"
New-Item -ItemType Directory -Force $backup | Out-Null
$files = @(
  "backend\app\simulation\sumo_runner.py",
  "backend\app\simulation\lifecycle.py",
  "backend\app\api\routes\simulation.py",
  "backend\app\main.py",
  "backend\tests\test_simulation_lifecycle.py",
  "docs\00-project-overview.md",
  "docs\04-api-design.md",
  "docs\06-test-plan.md",
  "docs\07-development-log.md",
  "docs\09-b1-simulation-lifecycle.md",
  "docs\B1-deploy-and-test.md"
)
foreach ($file in $files) {
  if (Test-Path $file) {
    $target = Join-Path $backup $file
    New-Item -ItemType Directory -Force (Split-Path $target -Parent) | Out-Null
    Copy-Item $file $target -Force
  }
}
```

## 3. 自动化测试

```powershell
Set-Location D:\Projects\traffic-signal-control-platform\backend
..\.venv\Scripts\python.exe -m pytest -q
```

预期：所有默认测试通过；真实 SUMO 集成测试显示 skipped。若失败，保存完整输出，不要继续真实进程测试。

## 4. 真实 SUMO 集成测试

确保 `SUMO_HOME`、SUMO 1.28.0、`sumo.exe` 和 `intersection.sumocfg` 可用：

```powershell
$env:RUN_SUMO_INTEGRATION = "1"
..\.venv\Scripts\python.exe -m pytest tests\test_sumo_runner_lifecycle.py -m integration -v
Remove-Item Env:RUN_SUMO_INTEGRATION
```

预期：真实 SUMO 启动、至少推进一步、关闭后进程句柄确认退出。

## 5. REST验收

启动后端：

```powershell
Set-Location D:\Projects\traffic-signal-control-platform\backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

另开 PowerShell：

```powershell
$base = "http://127.0.0.1:8000/api/simulation"
Invoke-RestMethod "$base/status"
Invoke-RestMethod -Method Post "$base/start"
Invoke-RestMethod -Method Post "$base/start" -ErrorAction Continue
Start-Sleep -Seconds 2
Invoke-RestMethod "$base/status"
Invoke-RestMethod -Method Post "$base/stop"
Invoke-RestMethod -Method Post "$base/stop"
```

核对：初始 STOPPED；start 后 RUNNING、`sumo_connected=true`、`process_alive=true`；重复 start HTTP 409；仿真时间/step_index 递增；stop 后 STOPPED 且两个进程/连接标志均为 false；重复 stop 幂等。

## 6. 10次启停与进程检查

先运行一次 start/stop 验证通过，再执行：

```powershell
$base = "http://127.0.0.1:8000/api/simulation"
1..10 | ForEach-Object {
  Write-Host "Cycle $_"
  Invoke-RestMethod -Method Post "$base/start" | Out-Null
  Start-Sleep -Milliseconds 500
  Invoke-RestMethod -Method Post "$base/stop" | Out-Null
}
Get-Process sumo -ErrorAction SilentlyContinue | Select-Object Id, ProcessName
```

若 SUMO 可执行文件显示为 `sumo.exe`，PowerShell 的进程名通常为 `sumo`。停止后不应残留本次启动的进程。

## 7. 外部强制退出测试

1. 正常 POST start。
2. 通过任务管理器结束对应 `sumo.exe` 进程。
3. 请求 `/api/simulation/status` 或 `/api/health`，等待后台循环检测。
4. 预期 `lifecycle_status=FAILED`，`last_error` 有诊断信息，`process_alive=false`。
5. POST stop 清理到 STOPPED，再确认可以重新 start。

## 8. FastAPI关闭测试

1. POST start。
2. 保持仿真运行，确认时间递增。
3. 使用 Ctrl+C 正常关闭 uvicorn。
4. 确认日志无 TraCI 并发关闭异常，任务管理器中对应 `sumo.exe` 退出。

## 9. 当前边界

本指南中的预期结果不是预先通过的验收证据。只有用户实际运行并提供输出后，才能将对应项目标记为通过。Docker 中 SUMO 的部署不属于本阶段范围。
