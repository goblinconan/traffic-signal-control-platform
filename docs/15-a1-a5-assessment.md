# A1–A5 三维场景工作评估

- 评估基线：B4-complete `f2052b539ce9c50782a25b50471c4725874d8b8e` + 本次 B5 前端控制台交付候选。
- 评估依据：`docs/01-requirements.md` 第 15、16.3 节；`docs/02-architecture.md` 第 17–23、26 节；当前 `network_geometry.py`、B4 网络 REST 模型、二维 `IntersectionView.tsx`。
- 评估性质：代码现状为源码核查结论；工期为工程估算，不是已经发生的开发工时或验收结果。

## 1. 总体结论

A1–A5 应在 B5 浏览器控制台完成部署验收后继续实施。当前 B4 已有静态网络 API、`network_version` SHA256 和二维 SVG 网络绘制基础，但尚不能视为 A1 完成，更没有 Three.js 三维场景或双视图切换。

推荐顺序保持架构文档规定的 A1 → A2 → A3 → A4 → A5。A1 的数据契约未完成前不应开始大量 A3 模型绘制；A2 可做技术验证，但不宜将临时坐标/信号灯硬编码固化成正式场景。

## 2. 当前代码证据与差距

### 2.1 已具备的基础

- `GET /api/intersections/{intersection_id}/network` 返回静态网络资源。
- `network_version` 是 SUMO `net.xml` 内容 SHA256。
- 当前 geometry 包含 junctions（id/type/x/y/shape）、外部 edges、lane（id/index/width/speed/shape）、internal_lanes 和 conv/orig boundary。
- B4 WebSocket 动态快照/更新携带 `network_version`、车辆 x/y/angle/speed/length/width、信号组灯色、剩余时间和仿真时间。
- `useSimulationSocket` 只建立一条 WebSocket，按 network_version 加载静态网络；二维组件消费同一状态。
- 当前 net.xml 含 48 条 connection，其中 20 条带 `tl=intersection_0` 和 `linkIndex`；这些信息目前没有进入 `NetworkGeometry` 返回结构。

### 2.2 A1 尚缺内容

当前 `load_network_geometry()` 没有输出：

- connection / fromLane / toLane / via / dir / tl / linkIndex。
- 车道转向类别与业务信号组的显式映射。
- 停止线几何或可计算停止线的稳定依据。
- 信号灯组空间位置及 SUMO linkIndex 到四类业务组的映射。
- 明确的坐标转换元数据（原点、单位、轴方向、比例、旋转/平移规则）。
- 面向多个 intersection/junction 的正式关联规则。

当前 `IntersectionView.tsx` 仍将世界坐标范围硬编码为 0–400，SVG 高度方向翻转；四组灯的位置使用固定 SVG transform。这些规则适用于当前二维画面，不足以作为三维场景的通用坐标合同。

当前 SUMO `net.xml` 的 location 示例为 `netOffset="200.00,200.00"`、`convBoundary="0,0,400,400"`、`origBoundary="-200,-200,200,200"`。实际数据解析应以每次加载的网络文件为准，不要在 Three.js 中再次硬编码减 200。

## 3. 分阶段工作

### A1：静态路网几何与坐标转换

**目标**：形成二维/三维共用、版本化、无需前端猜测的网络数据合同。

主要工作：

1. 扩展网络模型和解析器，保留当前 junction/edge/lane/internal lane 字段并增加 connection 信息。
2. 明确 `netOffset`、convBoundary、origBoundary、坐标单位和轴方向；提供统一转换规则，或明确统一使用 SUMO converted coordinates。
3. 解析 lane 转向类型、进口方向、独立左转/直行/右转车道。
4. 建立 TLS controlled connection 的 linkIndex 与 from/to/via lane 映射，并与后端 SignalService 实际映射交叉核对。
5. 生成可重复计算的停止线/信号灯组锚点，避免前端固定像素位置。
6. 更新网络 API schema、版本计算和几何测试；验证 net.xml 更新时 network_version 改变，旧缓存被替换。

**验收**：数据中所有受控连接均可追溯到 lane 与 linkIndex；四类业务信号组映射无歧义；坐标转换往返/边界测试通过；二维现有视图不回归。

**估算**：2–4 人日。若实际路网存在复杂连接/信号组歧义，另计交通工程核对时间。

### A2：Three.js 场景与相机

**目标**：建立稳定的三维渲染容器和相机交互，不先追求精细模型。

主要工作：

1. 在 frontend 增加 `three`、`@react-three/fiber`、`@react-three/drei` 依赖并更新 lockfile。
2. 建立 `TrafficScene3D`、场景根节点、坐标转换层、灯光和渲染器生命周期。
3. 提供俯视/斜视预设、旋转、缩放、平移；限制相机范围避免丢失路口。
4. 处理窗口 resize、组件卸载、WebGL context 和 GPU 资源释放。
5. 用静态几何测试场景先验证坐标、比例、深度和相机。

**验收**：在目标浏览器稳定加载；俯视与斜视可切换；鼠标/触控交互正常；重复挂载卸载无持续 GPU 资源增长。

**估算**：2–3 人日（含依赖集成与相机交互）。

### A3：道路、车道、停止线、车辆和信号灯渲染

**目标**：基于 A1 网络合同绘制可读且位置正确的三维路口。

主要工作：

1. 按 lane shape/width 构造道路和车道表面；区分外部道路、内部连接和路口区域。
2. 绘制车道分隔线、停止线、必要的路缘/路口边界。
3. 按车辆 x/y/angle/length/width 构造低多边形车辆；车辆朝向需统一 SUMO 角度约定。
4. 按业务映射放置四类信号灯组，按 B4 groups 灯色更新；右转状态继续标识为 PERMISSIVE_YIELD，不渲染成具有优先权的普通绿灯。
5. 对车辆对象采用实例化或对象池，避免每个 WebSocket tick 大量创建销毁 Mesh。

**验收**：道路/车道形状和宽度与 SUMO 一致；车辆中心、朝向和尺寸与二维/后端一致；灯色及倒计时与后端一致；停止线和灯组位置不依赖屏幕像素常量。

**估算**：4–7 人日，取决于车道边界/停止线几何方案与性能优化程度。

### A4：动态状态接入与二维/三维切换

**目标**：两个渲染器使用同一份 B4 状态和同一条 WebSocket。

主要工作：

1. 将现有 `useSimulationSocket` 提升为页面唯一状态源；不在 `TrafficScene3D` 内另建 WebSocket。
2. 新建 `IntersectionViewport` / `ViewModeSwitch`，管理 2D/3D renderer。
3. 切换视图只卸载/挂载渲染器，不改变 SimulationLifecycle、信号控制域或 sequence。
4. network_version 变化时替换静态网络；动态数据使用相同 sequence/tick。
5. 对 WebSocket 重连、旧消息丢弃、网络数据加载失败和版本不匹配提供可见反馈。

**验收**：来回切换二维/三维不重启仿真、不重置相位、不建立第二条 WS；同一 sequence 下两种视图显示相同仿真时间、车辆和信号灯状态。

**估算**：1–3 人日。

### A5：性能、一致性和稳定性验收

**目标**：确保三维不是只在静态截图中正确，而是在持续仿真和重连下可靠。

主要工作：

1. 选定车辆规模与目标帧率，采集 FPS、帧时间、内存和 GPU 资源指标。
2. 验证 2D/3D 切换、重复挂载、窗口 resize、WebSocket 断线重连。
3. 对 network_version 更新、sequence 倒退/重复、车辆增删和信号状态切换做一致性测试。
4. 长时间运行观察内存增长、对象泄漏、WebGL context 丢失和 UI 卡顿。
5. 形成性能基准、浏览器/设备矩阵和回归测试报告。

**验收**：项目需先确认目标设备和车辆规模，再设定帧率/延迟阈值；不能在没有设备基准时虚构固定 FPS 通过线。

**估算**：2–4 人日，另需按性能测试发现的问题预留修复时间。

## 4. 总体工期与风险

| 阶段 | 估算人日 | 主要依赖 | 风险 |
|---|---:|---|---|
| A1 | 2–4 | B4 network API、SUMO net.xml、controlled-links | 连接/信号映射和坐标合同不完整 |
| A2 | 2–3 | 前端依赖和构建环境 | WebGL 浏览器兼容、依赖版本 |
| A3 | 4–7 | A1、A2 | 几何精度、信号灯锚点、车辆渲染性能 |
| A4 | 1–3 | B4 WS、A1–A3 | 重复订阅、视图切换状态重置 |
| A5 | 2–4 | A1–A4、目标设备 | 性能门槛尚未定义、长时资源泄漏 |
| **合计** | **11–21** | — | 不含重大路网重建或交通冲突方案整改 |

以上为单名熟悉当前代码的开发者估算，不包含用户验收等待时间、真实交通工程审核、路网重建和重大性能返工。建议按 A1、A2、A3、A4、A5 分阶段交付，不建议把所有工作一次性合并成一个大改动。

## 5. 实施前置决策

开始 A1 前需明确：

- `intersection_id` 与 SUMO `tls_id` 是否继续共用 `intersection_0`，还是在 schema 中显式分开。
- 前端三维坐标使用 SUMO converted coordinates（当前 0–400）还是还原 origBoundary；推荐统一使用 converted coordinates，保留转换元数据用于标注/导出。
- 信号灯锚点是以受控连接停止线为基础自动计算，还是由 SUMO 附加设施/配置文件提供；必须能追溯 linkIndex 和业务组。
- 车辆规模、目标浏览器、目标设备和性能门槛。
- 是否需要真实地理坐标/GPS；当前 B4 x/y 是 SUMO 平面仿真坐标，不是卫星 GPS 经纬度。

## 6. 推荐路线

1. 完成 B5 控制台真实 SUMO 验收并固定 B5 基线。
2. A1 完成网络数据合同和坐标验证。
3. A2 建立独立三维场景基础。
4. A3 完成几何与动态对象渲染。
5. A4 统一状态源并接入双视图。
6. A5 完成性能、一致性、稳定性和最终交付验收。
