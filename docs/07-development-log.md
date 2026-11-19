

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



# 开发日志


## 2026-11-11


### 🎯 今日目标

1. 将单路口仿真从“双向 2 车道”升级为“双向 10 车道（单向 5 车道）”。
2. 实现当时的四相位信控（直行 + 左转）；当时测试中右转车辆在红灯期间持续通行。
   - 历史说明：该右转行为仅为 2026-11-11 当时的仿真观察，不代表安全让行；已被 2026-11-13 确认的“独立右转车道 + 红灯期间让行通行”规则取代，不再作为当前目标规则。
3. 解决车辆位置映射漂移、左转车流不生成、红绿灯串相位等核心 Bug。




### ✅ 完成的工作与关键修复


1. **SUMO 路网与车流升级**
   - 将 `intersection.edg.xml` 升级为单向 5 车道（左转2、直行2、右转1），并加宽了车道（width=16.0）。
   - 重新编写了 `intersection.rou.xml`，引入了密集的直行、左转、右转车流。
   - **修复了车流丢失问题**：发现 SUMO 要求 `<flow>` 必须按 `begin` 时间递增排序，否则会静默忽略未排序的车流（导致左转车完全不生成）。已重新排序并通过 `vehroute-output` 独立验证。


2. **信号灯状态机与相位修复**
   - 将信号机升级为当时测试用的 8 个相位（南北直行绿/黄、南北左转绿/黄、东西直行绿/黄、东西左转绿/黄）。该排列是 2026-11-11 历史测试配置，不是 2026-11-13 确认的当前目标顺序。
   - 更新了 `intersection.tll.xml`，将状态字符串扩展为 20 位，并与 `netconvert` 重新合并。
   - 修复了红灯剩余时间计算逻辑，确保前端在红灯最后 10 秒、绿灯最后 8 秒精准展示倒计时。
   - 修复了异步死锁：将 `runner.start/stop` 放入 `asyncio.to_thread` 线程池，解决 FastAPI 卡死问题。


3. **坐标系统与前端可视化**
   - **解决坐标漂移**：`netconvert` 默认开启归一化会平移路网。通过 `--offset.disable-normalization true` 强制固定中心点在 (0,0)，并通过后端 `traci.junction.getPosition` 动态下发相对坐标。
   - **前端车道渲染**：将 SVG 马路总宽拓宽至 120px，绘制了完美的双向双黄线和 10 车道虚线。
   - **信号灯 UI 重构**：将信号灯组按“南北向（左上）”、“东西向（右下）”分块并排布局，标明“直行”与“左转”，彻底解决了版面错位。




### 🐛 踩坑与诊断记录

- **左转车流消失之谜**：不仅是因为 `rou.xml` 顺序没排好，而且单独修改 `.tll.xml` 不会自动生效到 `.net.xml`，必须手动执行 `netconvert` 重新合并。
- **车辆飞出屏幕**：因为 `netconvert` 平移了坐标，前端不知道中心点在哪，导致 `v.x * SCALE` 计算到了屏幕外。通过后端动态减去 `junction` 坐标完美解决。




### 🔍 验证结果

- [x] 双向 10 车道（单向 5 车道）渲染正常，车辆各归其道。
- [x] 120秒独立诊断测试：生成 46 辆车，其中 8 辆左转车全部成功到达终点（通过 `left-turn-check-3.rou.xml` 验证）。
- [ ] 浏览器端南北左转放行效果：待单独确认；独立 SUMO headless 诊断结果不能替代浏览器验收。
- [!] 旧测试网络中曾观察到右转车辆红灯期间持续通行；这是 2026-11-11 的历史行为记录，不代表符合 2026-11-13 确认的右转让行需求，也不作为当前验收通过项。
- [x] 倒计时数字、红绿灯并排 UI 布局在当时测试环境中的显示效果符合预期。




### ⏭️ 待处理事项 (遗留问题)

1. **黄灯过渡警告**：独立诊断日志出现两条 `Missing yellow phase in tlLogic 'intersection_0' ... for tl-index 0 and 5` 警告。由于涉及 `tl-index 0` 和 `tl-index 5`，需作为独立任务排查，**切勿破坏已经验证成功的左转相位**。
2. **配时修改联调**：验证前端修改各相位时长后，后端的 `TimingService` 是否能平滑在下一周期生效。
3. **Docker SUMO 化**：规划如何将 SUMO 放进 Docker 容器。
4. **OSM 真实路网替换**：将当前手工最小路网替换为真实的新开路与华龙道路口数据。




### 📦 Git 提交建议

```bash
git add simulation/ backend/ frontend/ docs/
git commit -m "feat(sim): 升级双向10车道及四相位信控，修复左转车流及坐标漂移Bug"
```



### 第一步：检查并确保有 `.gitignore` 文件

先看一眼有没有忽略配置，没有的话一定要先生成，否则代码仓库会变得巨大。

powershell

# 如果你之前没建过 .gitignore，执行这句创建它（如果已经存在会提示覆盖，选不覆盖）

if (!(Test-Path .gitignore)) { "node_modules/`n.venv/`n__pycache__/`ndist/`n.pytest_cache/`n*.pyc`n.env" | Out-File -FilePath .gitignore -Encoding utf8 }

### 第二步：查看当前修改状态

看看今天到底改了哪些文件，确认没有遗漏或误改：

powershell

git status

*(你会看到很多文件变成了红色，表示已修改但未暂存)*

### 第三步：将所有修改添加到暂存区

注意：因为有了 `.gitignore`，Git 会自动跳过那些大文件。

powershell

git add .

### 第四步：提交代码（记录里程碑）

使用我们之前拟定的标准规范提交信息：

powershell

git commit -m "feat(sim): 升级双向10车道及四相位信控，修复左转车流及坐标漂移Bug"

---

### （可选）第五步：推送到 GitHub

如果你已经在 GitHub 上建好了仓库，并且之前关联过远程地址（`origin`），直接推送即可：

powershell

git push origin main

*(如果你用的是 `master` 分支，就把 `main` 换成 `master`)*

> **如果你还没关联远程仓库**，需要先在 GitHub 新建一个空仓库，然后执行：
> `git remote add origin <你的GitHub仓库地址>`
> `git push -u origin main`



### 日常 Git 标准 5 步法

**前提**：在执行前，请确保终端（PowerShell）位于项目根目录 `D:\Projects\traffic-signal-control-platform`。

#### 1️⃣ 查看状态（先看一眼改了什么）

powershell

git status

*目的：确认你改了哪些文件，避免把临时文件或无关代码误提交。*

#### 2️⃣ 添加到暂存区（准备提交）

powershell

git add .

*目的：把当前目录下所有修改过的文件放入“购物车”。*

#### 3️⃣ 提交并写清楚说明（建立快照）

powershell

git commit -m "fix(traci): 修复车辆坐标漂移问题"

*目的：把代码保存为一个历史版本。**提交信息绝对不能只写 `update` 或 `修改`**，必须带上前缀，具体规范见后文。*

#### 4️⃣ 拉取远程代码（防止冲突）

powershell

git pull origin main

*目的：如果你的 GitHub 仓库有其他改动，或者你换电脑写了代码，这步能确保你先同步最新代码。*(单人开发报错可忽略)*

#### 5️⃣ 推送到 GitHub 云端

powershell

git push origin main

*目的：把本地的提交上传到 GitHub。如果没网，这步可以明天再做，本地提交不会丢。*

---

### 💡 懒人一键快捷版（如果你确定没冲突）

当你完全确认代码没问题，且不需要拉取远程代码时，可以合并成一条命令执行：

powershell

git add . ; git commit -m "feat: 你的提交说明" ; git push origin main

---

### 📝 提交信息（Commit Message）怎么写才专业？

按照你最初定的规范，每次提交的说明必须带上**类型前缀**。以后直接套用下面这些模板：

- **新增功能**：`feat(模块): 增加了配时修改接口`
  *(例如：`feat(frontend): 增加红绿灯倒计时显示`)*

- **修 Bug**：`fix(模块): 修复了什么错误`
  *(例如：`fix(sumo): 修复左转车流不生成的flow排序问题`)*

- **改文档**：`docs: 更新了今天的开发日志和README`

- **重构代码**：`refactor(模块): 重构了什么代码`（不改变功能的优化）

- **工程配置/依赖**：`chore: 更新了requirements.txt或Docker配置`

---

### 🚫 日常避坑指南（非常重要）

1. **千万别把 `.venv` 或 `node_modules` 提交上去**：
     只要你在根目录执行了 `git add .`，Git 会自动读取 `.gitignore` 文件，把这些几万兆的垃圾文件忽略。所以**千万不要删掉 `.gitignore` 文件**。

2. **`git push` 失败报错**：
     如果提示 `Updates were rejected`，说明 GitHub 上的代码比你本地新（比如你在网页上直接改了 README）。先执行 `git pull origin main --rebase`，解决冲突后再 `git push`。

3. **提交频率**：
     **每完成一个能跑通的小功能，就立刻 commit 一次**。千万别积累了一周再提交，一旦代码崩了，你连回滚的后悔药都没有。

**把你的开发日志 `07-development-log.md` 当作 Commit 的副产品**：每次提交前，顺手在日志里加两行今天干了啥，然后连着代码一起 `add` 进去，你的开发轨迹就完美闭环了。



## 模板

## YYYY-MM-DD

- 做了什么：
- 怎么验证的：
- 遗留问题：
- 对应 Git commit：


## 2026-11-12

### 文档阶段 1：需求与架构统一

- 检查 `docs.zip` 中现有项目文档。
- 确认早期文档仍包含双相位、简化配时字段等过时描述。
- 按当前已记录的八阶段 SUMO 基线补充需求、架构、API、仿真及测试设计。
- 明确浏览器控制优先于三维建模；保留二维视图并新增三维视图切换目标。
- 将仿真运行状态、信号控制启停状态、AUTO/MANUAL 模式分离。
- 将控制停用后的灯色策略、MANUAL 无新请求时的行为列为待确认安全决策。
- 本次为文档规划更新，不代表新增 API、前端组件或控制逻辑已经实现，也未修改业务代码。

### 验证与遗留

- 待对更新后的 Markdown、Mermaid 和 API 字段一致性进行复核。
- 待确认 ADR-001 中两项人工控制安全策略后，才能进入相关代码实现。

## 2026-11-13

### 今日工作：统一保护式左转与右转让行需求

- 明确第一版采用四类受保护业务通行阶段：南北左转、南北直行、东西左转、东西直行；每类绿灯后执行对应黄灯，共 8 个 SUMO 绿/黄灯阶段。
- 确认南北两个相反方向左转同时放行、东西两个相反方向左转同时放行；左转期间对应方向直行保持红灯。
- 确认四个进口方向均设置独立右转车道；对应方向红灯期间允许右转，但必须减速观察，并让行行人、非机动车及其他冲突交通流。
- 对齐 AUTO/MANUAL 控制、控制启用/停用状态、二维/三维双视图的既有 V2 目标。
- 修订项目概述、需求、架构、数据库、API、SUMO 仿真和测试文档；新增保护式左转与右转让行决策记录。
- 修正部署文档中的 PowerShell 代码块闭合错误。

### 验证与遗留事项

- 本次为文档修订，没有修改 Python/TypeScript 源码、数据库迁移、SUMO 网络或 Docker 配置。
- 右转独立车道、右转红灯让行、行人/非机动车冲突及对向左转同时放行，仍须在目标 SUMO 网络中通过 controlled-links、冲突矩阵和真实车辆仿真验证。
- `Missing yellow phase` 警告仍按既有测试计划跟踪。
- （历史记录，已于 2026-11-15 由 ADR-014 决策并实现）信号控制 DISABLED 后的灯色处置、MANUAL 模式无新请求时的行为此前待确认。
- 当前 40 秒直行绿、20 秒左转绿、3 秒黄灯仅作为既有 SUMO 测试基线，不代表最终交通配时已经验收。


### 当前阶段顺序基准（2026-11-13）

后续实现、测试、API 示例及 SUMO 程序统一采用以下顺序：

1. `NS_LEFT_GREEN` / `NS_LEFT_YELLOW`（南北左转，index 0/1）。
2. `NS_STRAIGHT_GREEN` / `NS_STRAIGHT_YELLOW`（南北直行，index 2/3）。
3. `EW_LEFT_GREEN` / `EW_LEFT_YELLOW`（东西左转，index 4/5）。
4. `EW_STRAIGHT_GREEN` / `EW_STRAIGHT_YELLOW`（东西直行，index 6/7）。

历史开发记录中的阶段顺序、状态字符串和 linkIndex 仅用于还原当时环境，不得直接作为当前网络配置或验收依据。


## 2026-11-14

### B1：仿真生命周期管理（交付待验收）

- 审查 `code审查v2(1).zip` 中现有 SumoRunner、仿真 REST 路由、FastAPI 后台循环及项目文档。
- 识别 start/stop/step 并发协调、异常状态表达、后台步进失败后的清理和应用关闭收尾等缺口。
- 新增 `SimulationLifecycle`，统一串行化启动、停止和仿真步进。
- 增加 STOPPED、STARTING、RUNNING、STOPPING、FAILED 生命周期状态。
- 保留 `/api/simulation/status` 的小写 `status` 字段，增加 `lifecycle_status` 和 `last_error`。
- 增加 FakeRunner 单元测试，覆盖启动/停止、重复操作、启动失败、步进失败及非运行状态步进。
- 本次代码与文档交付尚未在用户本机替换或执行测试，不得记为B1验收通过。

### 遗留

- 用户本机 pytest 与真实 SUMO API 启停测试待执行。
- SUMO进程被外部强制终止后的检测与残留进程专项测试待补充。
- `Missing green phase ... tl-index 0` 警告继续单独跟踪。
- 右转冲突安全验证按既定要求暂缓。


## 2026-11-14 — B1 生命周期管理整体复审

### 审核结论

- 收到完整后端代码、测试、项目文档及 SUMO 配置/网络/路线文件。
- 原有自动化测试：16 passed；该结果仅代表原测试集通过，不代表 B1 完整验收。
- 发现应用关闭取消后台 task 可能与 `asyncio.to_thread` 工作线程竞态；Runner 原实现吞掉 `traci.close(False)` 异常且没有进程退出确认；缺少并发、REST 和真实进程测试。
- B1 修订包增加取消安全的线程等待、关闭事件、五态生命周期、TraCI wait=True、进程句柄核验及失败时的进程终止回退。

### 当前验证状态

代码包的自动化测试结果和真实 SUMO 验收结果以本次 B1 专项验收报告为准。未在用户 Windows/SUMO 环境完成的项目均保持“待本机验证”，不得标记为已通过。


## 2026-11-15 — B2 控制域实现与自动化验证（本机 SUMO 待验收）

### 安全决策

- 用户确认策略 A：DISABLED 请求立即锁定新控制命令；当前绿灯完成后执行完整黄灯，再将所有 SUMO controlled links（包括右转 linkIndex 0、5、10、15）置为红灯；SUMO 继续运行。
- 用户确认策略 B：AUTO→MANUAL 在当前绿灯及完整黄灯结束后进入全红；MANUAL 无新请求时持续全红；人工业务阶段请求须从全红启动或经完整黄灯和全红过渡。
- 新增 `docs/ADR-014-control-mode-and-disable-policy.md`，不与既有 ADR-001 至 ADR-013 编号冲突。

### 本轮代码修改

- 补齐用户提供的 `backend/app/core/logging.py` 与 `backend/app/simulation/network_geometry.py`。
- `PhaseId` 增加控制保持态 `ALL_RED`；该状态不计入原八个周期阶段。
- `SignalService` 增加独立 `ControlMode`、`ControlStatus`、待完成模式切换和人工阶段请求；停用和 AUTO/MANUAL 切换采用安全过渡。
- 全红状态将 20 个 controlled links 全部设置为 `r`，覆盖原四个小写 `g` 右转连接。
- 新仿真启动重置为 ENABLED/AUTO。
- 新增 GET/PUT 控制状态 API；通过 `SimulationLifecycle` 操作锁串行化控制命令与 TraCI 步进。
- 更新前端信号类型、API/架构/仿真/需求/测试文档。

### 当前自动化验证

在独立审查副本 `B2-review/` 的 `backend` 目录执行：

```powershell
python -m compileall -q app tests
python -m pytest -q
```

当前最终结果：`49 passed, 1 skipped`。跳过项为显式要求设置 `RUN_SUMO_INTEGRATION=1` 的真实 SUMO 集成测试；这不是本机 SUMO 验收通过的证据。

### 尚未完成

- 尚未在用户 Windows 项目目录替换文件。
- 尚未执行用户本机真实 SUMO 进程启停、控制模式切换及全红灯色检查。
- B2 阶段状态保持“代码及自动化测试完成，本机真实 SUMO 验收待执行”。


## 2026-11-16 — B2 正式完成与 B3 配时/手动阶段交付

### B2 Git 里程碑

- 正式提交：`85fe65e Complete B2 signal control modes and safety`。
- 创建并推送标签：`B2-complete`。
- `origin/main` 指向 `85fe65e`；B2 代码和验收文档已同步 GitHub。
- 本机正式更新后回归、真实 SUMO/HTTP 控制验收及前端生产构建已按 `10-b2-control-mode-and-acceptance.md` 记录完成。

### B3 本轮实现

- 将配时模型从单一共享 `yellow` 字段调整为四类受保护业务流独立绿灯/黄灯共八个字段。
- 周期长度和四类红灯时长按完整八阶段计算；API 要求一次提交完整八字段，拒绝未知字段及非法参数。
- 配时方案增加 active/pending 版本号；AUTO 在完整周期边界应用，MANUAL 在安全全红边界应用。
- 修复 MANUAL 阶段切换在同一状态更新中进入并立即离开 ALL_RED 的问题：ALL_RED 先实际下发到 SUMO，并保持至少一个仿真 step，再启动目标阶段。
- 手动请求当前已运行阶段时作为无操作成功返回，避免无意义的全红切换。
- 更新前后端配时共享类型、API 文档、架构、需求、测试计划和新增 ADR-015/B3 验收文档。

### 沙盒验证与本机待验收

- 交付包后端测试：85 passed，2 skipped。
- skipped 项为真实 SUMO 集成测试，沙盒没有执行 Windows SUMO 实际运行验收。
- Windows 本机正式更新、依赖检查、完整 pytest、真实 SUMO 配时/手动阶段测试和前端生产构建仍需按 B3 部署指南执行。
- 当前配时 active/pending 版本仍在后端进程内管理；PostgreSQL `timing_plan` 持久化及 `signal_operation_log` 审计表尚未实现，明确留作后续数据库实施范围。


## 2026-11-17：B4 统一运行状态协议实现候选

- 基线：B3-complete，提交 `b493da1df6e06a41674b0dd9a376a19fc7dff5f2`。
- 新增 REST/WS 共用的 RuntimeStateService 和 Pydantic 协议模型。
- 新增统一运行状态查询及静态路网版本接口。
- WebSocket 首次连接发送完整 snapshot，动态更新携带单调 sequence。
- 前端 Hook 增加 sequence 防旧消息覆盖和 network_version 静态路网加载。
- 当前记录为实现候选；测试与用户本机 SUMO 验收结果由交付验收记录补充，不预先标记 B4 完成。


## 2026-11-18 B5 浏览器控制台交付候选

### 完成的代码工作（待用户本机验收）

1. 基于 B4-complete `f2052b539ce9c50782a25b50471c4725874d8b8e`，新增浏览器信号控制操作台。
2. 保留 B4 WebSocket Hook、统一状态类型和二维 SVG 路口视图；前端通过既有 REST API 调用仿真、控制启停、模式、人工阶段和配时操作。
3. 新增配时前端预校验：绿灯 >8 秒、黄灯 >0 秒、计算红灯 >10 秒；后端校验仍是最终权威。
4. 增加服务端操作反馈、FAILED 清理入口、DISABLING 安全过渡状态展示、active/pending 配时版本展示。
5. 增加 B5 部署说明、只读 API 冒烟脚本及 A1–A5 工作评估。

### 当前验证状态

- 代码生成和静态源码核对已完成。
- 本交付环境未包含前端 `node_modules`，且 npm 离线缓存缺少 lockfile 所需包；因此尚未在此环境运行 `npm run build`。
- B5 交付尚未在用户 Windows + SUMO 环境部署；真实 SUMO / 浏览器端到端验收待用户执行。
- 不得将本节代码交付候选标记为 B5 已验收完成。

### 下一步

按 `docs/14-b5-browser-control-console.md` 执行部署、pytest、npm build、只读 API 冒烟检查和浏览器真实 SUMO 验收；根据结果修复后再发布 B5-complete。
