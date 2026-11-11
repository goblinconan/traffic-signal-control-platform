# 开发日志

## 2026-11-10

- 完成 00/01/02 文档。
- 完成 03–08 文档和 README。
- 建立后端最小可运行骨架：配置、SUMO 运行器、信号状态机、REST + WebSocket。
- 建立 simulation/network 最小十字路口占位文件。
- 建立 frontend 最小 SVG 路口 + WebSocket 状态展示。
- 建立 docker-compose.yml 和 Dockerfile（SUMO 部署方式标注待验证）。

**下一步**：在 Windows 本机用 SUMO_HOME + pip traci 跑通 `python -m app.simulation.sumo_runner --smoke`，再把网络替换为 OSM 生成结果。



# 开发日志


## 2026-11-10


### 🎯 今日目标
从零搭建 SUMO 单路口仿真路网，打通前后端通信，实现车辆生成、行驶、红绿灯控制及 WebSocket 实时渲染的完整闭环。


### ✅ 完成的工作

1. **环境与基建**
   - 确定并配置了 Python 3.14.5 虚拟环境与 SUMO 1.28.0。
   - 解决了 npm 11 的 `esbuild` postinstall 脚本未执行导致 Vite 无法启动的问题。
   - 解决了 Docker 启动时 5432 和 8000 端口冲突问题，确认当前 Docker 容器内无 SUMO，Docker 模式暂作平台外壳验证。

   
2. **SUMO 仿真路网构建**
   - 手写了十字路口最小路网（`nod`, `edg`, `con`, `tll`），并使用 `netconvert` 成功编译。
   - 编写了 `intersection.rou.xml`，去除了 `end="600"` 限制，使车辆能无限生成。
   - 发现并确认了 SUMO 的 `netconvert` 默认会平移路网坐标（中心点变成 200,200）。

   
3. **后端 FastAPI + TraCI 控制逻辑**
   - 实现了 `SumoRunner` 类，封装了 `traci.start`、`simulationStep` 和车辆位置读取。
   - 解决了 TraCI 阻塞导致的异步死锁：将 `svc.step()` 和 `runner.start/stop` 放入 `asyncio.to_thread` 线程池执行。
   - 实现了红绿灯状态机 `SignalController`：包含南北/东西绿灯、黄灯，准确计算 8 秒绿灯倒计时与 10 秒红灯倒计时。
   - 修复了信号灯下发字符串的映射 Bug，通过动态遍历 `controlled_links` 生成正确的状态字符串（如 `GGGGrrrr`），彻底解决车辆在路口中央打架/卡死的问题。

   
4. **前端 React + SVG 可视化**
   - 实现了 `IntersectionView`，绘制背景、道路、虚线和四个方向的错位停止线。
   - 解决了车辆坐标偏移：在映射时通过 `(v.x - 200)` 补偿 `netconvert` 的归一化偏移。
   - 修复了车辆朝向：将 SUMO 角度 `v.angle` 转为 SVG 的 `v.angle - 90`，让车头方向正确。
   - 将白线向外侧偏移 15px，消除了视觉上车头“越线”的错觉。




### 🐛 踩坑与关键修复记录

- **文件污染**：在 PowerShell 中用 here-string (`@' ... '@`) 写入 JSON/TSX 文件时，极容易把命令尾部写进文件。后续涉及代码文件必须用 VS Code 手动保存。
- **端口抢占**：`uvicorn` 和 `Docker` 同时监听 8000 端口时，Windows 优先将 `127.0.0.1` 路由给本机 `python.exe`，导致误以为 Docker 里的仿真跑通了。排查端口时务必用 `netstat -ano | findstr :8000` 确认 PID。
- **前端构建产物**：`tsc` 如果没配好 `noEmit`，会在 `src` 下生成 `.js` 文件，导致 Vite 解析报错，需要删除并确保 `tsconfig` 正确。




### 🔍 验证结果

- [x] `curl -X POST http://127.0.0.1:8000/api/simulation/start` 秒级返回 `{"status":"running"}`，不再卡死。
- [x] 仿真时间正常推进，车辆从四个方向持续生成。
- [x] 浏览器页面 WebSocket 状态为“已连接”，车辆实时移动，红绿灯及倒计时显示正常。
- [x] 红灯时车辆准确停在白线后排队，黄灯正常过渡。




### ⏭️ 下一步计划 (遗留问题)

1. **配时修改联调**：验证前端修改南北/东西绿灯时长后，后端的 `TimingService` 是否能平滑在下一周期生效。
2. **手动切相位**：测试违规切相位（如跳过黄灯）是否被后端 409 拦截。
3. **Docker SUMO 化**：规划如何将 SUMO 放进 Docker 容器（或使用独立容器走 TCP 远程连接）。
4. **OSM 真实路网**：将手工最小路网替换为新开路与华龙道的真实 OSM 提取路网。




### 📦 Git 提交建议

```bash
git add simulation/ backend/ frontend/ docs/
git commit -m "feat(sim): 跑通SUMO单路口信控闭环，修复异步死锁、坐标映射及相位映射Bug"
```

## 模板

## YYYY-MM-DD

- 做了什么：
- 怎么验证的：
- 遗留问题：
- 对应 Git commit：
