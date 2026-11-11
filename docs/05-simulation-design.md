# SUMO 仿真设计

## 1. 网络来源

优先使用 OSM 提取新开路—华龙道路口，`netconvert` 生成 net.xml。当前代码先用**手工最小十字路口**作为可验证基线，OSM 网络替换时只需改 `simulation/network/` 下的文件和后端配置，不改业务代码。

## 2. 最小网络要求

- 4 条 edge：`north_in`、`south_in`、`east_in`、`west_in`，各带反向 `out`。
- 每个进口至少 2 条车道（直行、右转），左转在后续阶段增加。
- 所有进口车道受同一个 `tlLogic` 控制。
- 信号状态字符串长度 = 受控连接数。第一版用 4 位简化字符串验证状态机，正式 OSM 网络生成后按 `getControlledLinks` 重新映射。

## 3. 信号状态字符串映射

后端不假设“一个方向一个字符”。启动后调用：

```python
links = traci.trafficlight.getControlledLinks(tls_id)
```

建立 `link_index → (from_lane, to_lane, direction)` 映射，再按方向生成状态字符串。第一版先打印映射并写入日志，供人工核实。

## 4. 车辆与跟驰

- 使用 `flow` 按固定发车率生成，不手工插车。
- 跟驰模型使用 SUMO 默认 Krauss。
- 红灯停车、绿灯通行完全交给 SUMO，后端不直接控制车辆。

## 5. 时间基准

所有倒计时和阶段切换以 `traci.simulation.getTime()` 为准。暂停通过停止调用 `simulationStep` 实现，恢复后从原剩余时间继续。

## 6. 待验证事项

- OSM 网络的实际 controlled links 数量。
- 左转是否与直行冲突、是否需要独立相位。
- Docker 中 SUMO 的启动方式（同容器 vs 独立容器）。
