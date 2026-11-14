# 数据库设计

> 版本：V2.1（目标逻辑设计）  
> 对应需求：`01-requirements.md`  
> 对应架构：`02-architecture.md`
>
> 本文描述第一版目标数据模型，不代表数据库表或 Alembic 迁移已经实现。物理字段、索引和约束以实施时的迁移脚本及测试为准。

## 1. 设计原则

- 路口、道路、车道、车道连接、信号组、信号阶段和配时方案使用明确的关联关系。
- 四个进口方向分别记录独立左转、直行、右转车道。
- 右转让行规则属于车道连接/信号组控制属性，不作为第五类保护式绿灯阶段。
- 配时方案保存四类受保护信号组的绿灯和黄灯时长；红灯总时长由后端按完整周期计算。
- 配时方案区分 `active`、`pending`、`archived`；运行中修改不得截断当前阶段。
- 仿真高频车辆位置不默认全部写入数据库；优先通过运行时状态和 WebSocket 推送。
- 所有真实时间字段使用 UTC；仿真时间使用 SUMO simulation time，二者不得混用。
- 表结构通过 Alembic 管理，不手工修改数据库。

## 2. 核心表结构

### 2.1 intersection

| 字段          | 类型         | 说明            |
| ------------- | ------------ | --------------- |
| id            | BIGSERIAL PK | 路口主键        |
| name          | VARCHAR(120) | 路口名称        |
| location_name | VARCHAR(200) | 地点描述        |
| sumo_tls_id   | VARCHAR(80)  | SUMO tlLogic ID |
| created_at    | TIMESTAMPTZ  | 创建时间        |

### 2.2 road

| 字段            | 类型                 | 说明                   |
| --------------- | -------------------- | ---------------------- |
| id              | BIGSERIAL PK         | 道路主键               |
| intersection_id | FK → intersection.id | 所属路口               |
| name            | VARCHAR(120)         | 道路名称               |
| direction       | VARCHAR(8)           | `NS` / `EW` 或具体方向 |
| sumo_edge_id    | VARCHAR(120)         | SUMO edge ID           |

### 2.3 lane

| 字段               | 类型         | 说明                                             |
| ------------------ | ------------ | ------------------------------------------------ |
| id                 | BIGSERIAL PK | 车道主键                                         |
| road_id            | FK → road.id | 所属道路                                         |
| approach_direction | VARCHAR(8)   | `N` / `S` / `E` / `W`                            |
| movement_type      | VARCHAR(16)  | `LEFT` / `STRAIGHT` / `RIGHT`                    |
| sumo_lane_id       | VARCHAR(120) | SUMO lane ID                                     |
| lane_index         | INTEGER      | SUMO lane 索引，仅作来源属性，不作为转向判断依据 |
| is_dedicated       | BOOLEAN      | 是否为专用转向车道                               |

约束：每个进口方向的左转、直行和右转目标车道必须分别建模，不能将同一条车道同时标记为多个转向类型。若来源路网与目标交通组织不一致，必须先记录差异并完成路网校正。

### 2.4 lane_connection

| 字段              | 类型         | 说明                                                |
| ----------------- | ------------ | --------------------------------------------------- |
| id                | BIGSERIAL PK | 连接主键                                            |
| from_lane_id      | FK → lane.id | 进口车道                                            |
| to_lane_id        | FK → lane.id | 出口车道                                            |
| movement_type     | VARCHAR(16)  | `LEFT` / `STRAIGHT` / `RIGHT`                       |
| sumo_link_index   | INTEGER      | SUMO TLS controlled link 索引；非信号控制连接可为空 |
| control_mode      | VARCHAR(24)  | `PROTECTED` / `PERMISSIVE_YIELD` / `UNSIGNALIZED`   |
| conflict_metadata | JSONB        | 冲突关系或来源映射信息                              |

右转连接使用 `PERMISSIVE_YIELD` 或经验证的等效让行规则；不得将右转连接设置为优先通行。当前 SUMO TLS 程序将四个右转连接（linkIndex 0、5、10、15）在全部八个阶段设置为小写 `g`，表示让行绿灯。该信号配置不代表车辆已经正确执行减速、停车和让行，实际行为及冲突安全性仍须通过 controlled-links、冲突矩阵和车辆轨迹验证。

### 2.5 signal_group

| 字段            | 类型                 | 说明                             |
| --------------- | -------------------- | -------------------------------- |
| id              | BIGSERIAL PK         | 信号组主键                       |
| intersection_id | FK → intersection.id | 所属路口                         |
| group_code      | VARCHAR(32) UNIQUE   | 业务信号组编码                   |
| movement_type   | VARCHAR(16)          | `LEFT` / `STRAIGHT` / `RIGHT`    |
| direction_group | VARCHAR(8)           | `NS` / `EW` / 具体进口方向       |
| control_mode    | VARCHAR(24)          | `PROTECTED` / `PERMISSIVE_YIELD` |

四类保护式信号组编码：`NS_STRAIGHT`、`NS_LEFT`、`EW_STRAIGHT`、`EW_LEFT`。四个右转方向分别记录为 `N_RIGHT`、`S_RIGHT`、`E_RIGHT`、`W_RIGHT`，控制方式为 `PERMISSIVE_YIELD`。

### 2.6 signal_phase

| 字段                | 类型                 | 说明                  |
| ------------------- | -------------------- | --------------------- |
| id                  | BIGSERIAL PK         | 阶段主键              |
| intersection_id     | FK → intersection.id | 所属路口              |
| phase_code          | VARCHAR(40)          | 阶段编码              |
| sequence_index      | SMALLINT             | SUMO 阶段顺序索引 0–7 |
| stage_type          | VARCHAR(8)           | `GREEN` / `YELLOW`    |
| movement_group_code | VARCHAR(32)          | 对应业务信号组        |

第一版业务阶段顺序固定为：南北左转、南北直行、东西左转、东西直行；每个业务阶段包含绿灯和黄灯两个 SUMO 阶段，共 8 个阶段。对应 SUMO 阶段索引为 0/1 南北左转、2/3 南北直行、4/5 东西左转、6/7 东西直行。实际状态字符串必须依据 SUMO controlled links 生成。

### 2.7 timing_plan

| 字段               | 类型                 | 说明                              |
| ------------------ | -------------------- | --------------------------------- |
| id                 | BIGSERIAL PK         | 配时方案主键                      |
| intersection_id    | FK → intersection.id | 所属路口                          |
| ns_straight_green  | NUMERIC(5,1)         | 南北直行绿灯秒，必须 > 8          |
| ns_straight_yellow | NUMERIC(5,1)         | 南北直行黄灯秒，必须 > 0          |
| ns_left_green      | NUMERIC(5,1)         | 南北左转绿灯秒，必须 > 8          |
| ns_left_yellow     | NUMERIC(5,1)         | 南北左转黄灯秒，必须 > 0          |
| ew_straight_green  | NUMERIC(5,1)         | 东西直行绿灯秒，必须 > 8          |
| ew_straight_yellow | NUMERIC(5,1)         | 东西直行黄灯秒，必须 > 0          |
| ew_left_green      | NUMERIC(5,1)         | 东西左转绿灯秒，必须 > 8          |
| ew_left_yellow     | NUMERIC(5,1)         | 东西左转黄灯秒，必须 > 0          |
| status             | VARCHAR(16)          | `active` / `pending` / `archived` |
| effective_at       | TIMESTAMPTZ          | 待生效方案的计划生效时间          |
| version            | INTEGER              | 配时版本号                        |
| created_at         | TIMESTAMPTZ          | 创建时间                          |

红灯时长不作为用户输入字段。若不设置额外全红阶段，周期长度：

`C = (ns_straight_green + ns_straight_yellow) + (ns_left_green + ns_left_yellow) + (ew_straight_green + ew_straight_yellow) + (ew_left_green + ew_left_yellow)`

每个保护式信号组的红灯总时长等于其余三个业务阶段的绿灯与黄灯时长之和。若后续增加全红清空阶段，必须将其加入周期和红灯计算。

当前测试基线：南北/东西直行绿灯各 40 秒、南北/东西左转绿灯各 20 秒、四类黄灯各 3 秒。由此得到周期 132 秒；南北/东西直行红灯各 89 秒，南北/东西左转红灯各 109 秒。此处仅用于测试示例，不代表最终实际配时。

### 2.8 phase_group_mapping

| 字段            | 类型                 | 说明                  |
| --------------- | -------------------- | --------------------- |
| phase_id        | FK → signal_phase.id | SUMO 阶段             |
| signal_group_id | FK → signal_group.id | 业务信号组            |
| signal_state    | CHAR(1)              | `G` / `g` / `y` / `r` |

`G` 表示优先绿灯；`g` 表示允许通行但必须让行的次要绿灯；`y` 表示黄灯；`r` 表示红灯。当前 SUMO TLS 程序中，四个右转连接（linkIndex 0、5、10、15）在全部八个阶段使用小写 `g`。该配置不得解释为受保护绿灯或无条件通行。最终映射仍须结合 controlled-links、冲突矩阵和实际车辆轨迹验证；右转让行连接不得误映射为 `G`。

### 2.9 simulation_run

| 字段            | 类型                 | 说明                            |
| --------------- | -------------------- | ------------------------------- |
| id              | BIGSERIAL PK         | 仿真运行主键                    |
| intersection_id | FK → intersection.id | 所属路口                        |
| started_at      | TIMESTAMPTZ          | 开始时间                        |
| ended_at        | TIMESTAMPTZ          | 结束时间                        |
| status          | VARCHAR(16)          | `RUNNING` / `STOPPED` / `ERROR` |
| stop_reason     | TEXT                 | 停止原因                        |

### 2.10 signal_operation_log

| 字段       | 类型                   | 说明                                                                                                        |
| ---------- | ---------------------- | ----------------------------------------------------------------------------------------------------------- |
| id         | BIGSERIAL PK           | 操作记录主键                                                                                                |
| run_id     | FK → simulation_run.id | 所属仿真运行                                                                                                |
| operation  | VARCHAR(64)            | `timing_update` / `manual_switch` / `mode_change` / `control_enable` / `control_disable` / `start` / `stop` |
| payload    | JSONB                  | 请求参数及修改前后值                                                                                        |
| result     | VARCHAR(16)            | `success` / `rejected`                                                                                      |
| message    | TEXT                   | 处理结果或拒绝原因                                                                                          |
| created_at | TIMESTAMPTZ            | 操作时间                                                                                                    |

## 3. 关键约束与计算规则

- 同一路口最多只能有一条 `status='active'` 的配时方案；待生效方案最多一条，或由应用层明确管理版本队列。
- 四类绿灯分别满足 `> 8` 秒；四类黄灯分别满足 `> 0` 秒，默认 3 秒。
- 四类受保护信号组计算得到的红灯总时长必须分别 `> 10` 秒。
- 红灯时长由完整阶段序列计算，不得沿用旧版 `ns_red = ew_green + ew_yellow`、`ew_red = ns_green + ns_yellow` 双相位公式。
- 右转车道和右转连接必须独立建模；让行策略不得授予优先通行权。
- 配时方案先整体校验，再保存为待生效版本；当前阶段不截断，且同一周期不得混用版本。
- AUTO/MANUAL、信号控制启用状态、当前阶段和剩余时间属于运行态；由后端运行时状态管理，重要操作写入 `signal_operation_log`。
- 实际车道、受控连接和冲突矩阵以 SUMO 网络验证结果为准；不得将未经验证的推断当作已实现约束。

## 4. 旧字段迁移说明

旧版 `ns_green`、`ns_yellow`、`ew_green`、`ew_yellow` 仅能作为历史字段处理，不能直接套用旧双相位红灯公式。

若数据库中已存在旧配时记录，迁移时至少应：

1. 备份并盘点旧记录及其原始配时语义。
2. 旧版南北/东西绿灯可能同时包含当时允许的直行和左转交通流，不能假定与新的直行字段一一对应。
3. 根据旧 SUMO 阶段、路由和业务配置制定逐条迁移映射；无法可靠拆分的历史值应保留原始记录并标记待人工确认。
4. 为新增左转字段提供经审核的初始化值，不得静默猜测或丢弃。
5. 重新计算四类红灯时长并校验约束。
6. 通过迁移测试确认历史记录和操作日志完整。

## 5. Alembic

```powershell
cd backend
alembic revision --autogenerate -m "align_protected_turn_timing"
alembic upgrade head
```

以上命令为后续实施示例，必须在数据库模型和迁移脚本实际完成后执行。

**验证**：检查路口、道路、车道、车道连接、信号组、信号阶段、配时方案、仿真运行及操作日志等表结构；具体表名以最终 ORM 模型为准。
