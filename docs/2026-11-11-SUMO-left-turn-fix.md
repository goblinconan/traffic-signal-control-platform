# 2026-11-11 SUMO 左转车流与信号灯问题修复记录

> 历史记录说明：本文保留 2026-11-11 当时的阶段排列、20 位状态字符串和 linkIndex 证据。该日测试阶段排列为“南北直行、南北左转、东西直行、东西左转”，与 2026-11-13 确认的当前目标顺序不同。当前实现统一采用“南北左转、南北直行、东西左转、东西直行”；不得把本文历史阶段索引直接复制到当前 SUMO 网络。

## 一、问题现象

项目：`D:\Projects\traffic-signal-control-platform`

SUMO
仿真车辆可以正常行驶，但南北方向车辆此前始终表现为直行，没有观察到左转。本次排查确认了车辆流量、路网连接、信号灯相位和实际仿真结果。

## 二、排查与修复过程

### 1. 确认左转路线和路网连接存在

`simulation/routes/intersection.rou.xml` 已定义：

  车流 ID   起点         终点           发车车道   发车间隔
  --------- ------------ ------------ ---------- ----------
  `N_E`     `north_in`   `east_out`            3      15 秒
  `S_W`     `south_in`   `west_out`            3      15 秒

`simulation/network/intersection.net.xml` 中也存在对应连接： -
`north_in` 的 3、4 号车道连接到 `east_out`。 - `south_in` 的 3、4
号车道连接到 `west_out`。

### 2. 修正信号灯相位

原始 `intersection.tll.xml` 的状态字符串与受控连接 `linkIndex`
对应关系不匹配。采用保护左转方案后，8
个相位调整如下，持续时间保持原设定：

    相位   持续时间 状态
  ------ ---------- ------------------------
       0      40 秒 `GGGrrrrrrrGGGrrrrrrr`
       1       3 秒 `GyyrrrrrrrGyyrrrrrrr`
       2      20 秒 `rrrGGrrrrrrrrGGrrrrr`
       3       3 秒 `rrryyrrrrrrrryyrrrrr`
       4      40 秒 `rrrrrGGGrrrrrrrGGGrr`
       5       3 秒 `rrrrrGyyrrrrrrrGyyrr`
       6      20 秒 `rrrrrrrrGGrrrrrrrrGG`
       7       3 秒 `rrrrrrrryyrrrrrrrryy`

每个状态字符串长度均为 20。phase 2/3 对应南北左转绿/黄灯，phase 6/7
对应东西左转绿/黄灯。

### 3. 更新 SUMO 实际加载的路网

`simulation/config/intersection.sumocfg` 引用：

``` xml
<net-file value="../network/intersection.net.xml"/>
```

因此，单独修改 `.tll.xml` 不会自动更新 SUMO 实际加载的 `.net.xml`。

重新生成前备份了原路网：

``` powershell
Copy-Item .\simulation\network\intersection.net.xml .\simulation\network\intersection.net.xml.bak
```

沿用项目原始 netconvert 流程重新生成：

``` powershell
netconvert -n .\simulation\network\intersection.nod.xml -e .\simulation\network\intersection.edg.xml -x .\simulation\network\intersection.con.xml -i .\simulation\network\intersection.tll.xml -o .\simulation\network\intersection.net.xml
```

生成成功，并验证 `.net.xml` 已包含新的 8 个相位及正确的 20
位状态字符串。

### 4. 修复车辆 flow 排序

独立运行 SUMO 时，出现 `Route file should be sorted by departure time`
警告，SUMO 忽略了 `N_E`、`S_W` 等流量。

原因是 `simulation/routes/intersection.rou.xml` 中的 `<flow>` 没有按
`begin` 递增排列。保持所有车辆参数不变，只调整为以下顺序：

    顺序 车流 ID     begin
  ------ --------- -------
       1 `N_S`           0
       2 `N_E`           1
       3 `S_N`           2
       4 `N_W`           2
       5 `S_W`           3
       6 `E_W`           4
       7 `S_E`           4
       8 `E_S`           5
       9 `W_E`           6
      10 `E_N`           6
      11 `W_N`           7
      12 `W_S`           8

使用 Python 校验 `begin` 序列已按升序排列，验证通过。再次运行 SUMO
后，flow 排序警告消失。

## 三、120 秒诊断仿真结果

运行命令：

``` powershell
sumo -c .\simulation\config\intersection.sumocfg --end 120 --vehroute-output .\left-turn-check-3.rou.xml --no-step-log true
```

从 `left-turn-check-3.rou.xml` 统计： - 总生成车辆：46 辆。 -
南北向左转车辆：8 辆。 - `N_E`：4 辆，路线 `north_in east_out`。 -
`S_W`：4 辆，路线 `south_in west_out`。

左转车辆到达记录：

  车辆        depart   arrival 路线
  --------- -------- --------- ---------------------
  `N_E.0`       1.00     63.50 `north_in east_out`
  `N_E.1`      16.00     62.50 `north_in east_out`
  `N_E.2`      31.00     65.00 `north_in east_out`
  `N_E.3`      46.00     77.00 `north_in east_out`
  `S_W.0`       3.00     62.50 `south_in west_out`
  `S_W.1`      18.00     63.00 `south_in west_out`
  `S_W.2`      33.00     64.00 `south_in west_out`
  `S_W.3`      48.00     77.50 `south_in west_out`

8 辆左转车辆均有到达时间，表明它们完成了指定路线。

## 四、验证结论

独立 SUMO headless 诊断已验证：120 秒仿真共生成 46 辆车，8 辆南北向左转车辆均有到达记录，说明这些车辆完成了指定路线。

**结论：南北向左转路线已通过独立 SUMO 诊断验证。浏览器端左转显示与放行效果仍需单独确认，不能以 headless 结果替代浏览器验收。**

排查过程中修正了 route 文件中的 flow 发车时间排序，并重新合并了信号灯相位配置。上述结果仅代表 2026-11-11 的历史测试网络与配置。

## 五、待处理事项

独立诊断仍出现两条黄灯过渡警告：

``` text
Warning: Missing yellow phase in tlLogic 'intersection_0', program '0' for tl-index 0 when switching to phase 2.
Warning: Missing yellow phase in tlLogic 'intersection_0', program '0' for tl-index 5 when switching to phase 6.
```

涉及 `tl-index 0` 和 `tl-index 5`
的黄灯过渡，尚未处理。应作为后续独立任务排查，不要破坏已经验证成功的左转相位。

## 六、关键文件

  -----------------------------------------------------------------------------------
  文件                                            用途与状态
  ----------------------------------------------- -----------------------------------
  `simulation/routes/intersection.rou.xml`        车辆流量与路线；flow 排序已修复

  `simulation/network/intersection.tll.xml`       信号灯相位定义；8 个相位已调整

  `simulation/network/intersection.net.xml`       SUMO 实际加载路网；已重新生成并验证

  `simulation/network/intersection.net.xml.bak`   重建前备份

  `simulation/config/intersection.sumocfg`        SUMO 配置

  `left-turn-check-3.rou.xml`                     120 秒诊断仿真路线输出
  -----------------------------------------------------------------------------------

------------------------------------------------------------------------

记录日期：2026-11-11\
项目：`traffic-signal-control-platform`\
状态：南北向左转路线已通过独立 SUMO 诊断验证；浏览器效果待单独确认；黄灯过渡警告待处理。

---

## 后续需求变更说明（2026-11-13）

本记录保留 2026-11-11 当时的 SUMO 路网、20 个受控连接及 8 阶段信号字符串修复证据，不应被视为车道拓扑变更后的最终配置。

2026-11-13 已确认新的第一版交通组织要求：

- 四个进口方向分别设置独立左转、直行、右转车道。
- 当前正式阶段顺序为南北左转、南北直行、东西左转、东西直行，每类业务阶段各含绿灯和黄灯。
- 南北相反方向左转同时放行；东西相反方向左转同时放行。
- 左转期间对应方向直行保持红灯。
- 右转在对应方向红灯期间允许按让行规则通行，必须减速观察，并让行行人、非机动车及其他冲突交通流。

因此，车道结构或连接关系调整后，必须重新生成并验证 `controlledLinks`、`linkIndex`、冲突矩阵及 8 个 SUMO 阶段的状态字符串。不得直接假设本记录中的 20 个 linkIndex 映射在新网络中仍然有效。
