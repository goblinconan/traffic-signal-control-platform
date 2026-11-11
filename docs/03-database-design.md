# 数据库设计

> 版本：V1.0　对应需求：`01-requirements.md`　对应架构：`02-architecture.md`

## 1. 设计原则

- 高频车辆轨迹不默认入库，只保存仿真运行摘要和信号控制操作记录。
- 配时方案区分“生效中”和“待生效”，修改不截断当前阶段。
- 所有时间字段使用 UTC，业务展示时由前端转换。
- 表结构通过 Alembic 管理，不手工改库。

## 2. 表结构

### 2.1 intersection

| 字段        | 类型         | 说明                  |
| ----------- | ------------ | --------------------- |
| id          | SERIAL PK    |                       |
| name        | VARCHAR(120) | 路口名称              |
| sumo_tls_id | VARCHAR(80)  | SUMO 中 tlLogic 的 id |
| created_at  | TIMESTAMPTZ  |                       |

### 2.2 timing_plan

| 字段            | 类型                 | 说明                              |
| --------------- | -------------------- | --------------------------------- |
| id              | SERIAL PK            |                                   |
| intersection_id | FK → intersection.id |                                   |
| ns_green        | NUMERIC(5,1)         | 南北绿灯秒，>8                    |
| ns_yellow       | NUMERIC(5,1)         | 南北黄灯秒，>0                    |
| ew_green        | NUMERIC(5,1)         | 东西绿灯秒，>8                    |
| ew_yellow       | NUMERIC(5,1)         | 东西黄灯秒，>0                    |
| status          | VARCHAR(16)          | `active` / `pending` / `archived` |
| effective_at    | TIMESTAMPTZ          | 待生效方案的计划生效时间          |
| created_at      | TIMESTAMPTZ          |                                   |

红灯不落库，由后端按 `ns_red = ew_green + ew_yellow`、`ew_red = ns_green + ns_yellow` 实时计算。

### 2.3 simulation_run

| 字段            | 类型        | 说明                      |
| --------------- | ----------- | ------------------------- |
| id              | SERIAL PK   |                           |
| intersection_id | FK          |                           |
| started_at      | TIMESTAMPTZ |                           |
| ended_at        | TIMESTAMPTZ |                           |
| status          | VARCHAR(16) | running / stopped / error |
| stop_reason     | TEXT        |                           |

### 2.4 signal_operation_log

| 字段       | 类型                   | 说明                                         |
| ---------- | ---------------------- | -------------------------------------------- |
| id         | SERIAL PK              |                                              |
| run_id     | FK → simulation_run.id |                                              |
| operation  | VARCHAR(64)            | timing_update / manual_switch / start / stop |
| payload    | JSONB                  | 修改前后值                                   |
| result     | VARCHAR(16)            | success / rejected                           |
| message    | TEXT                   |                                              |
| created_at | TIMESTAMPTZ            |                                              |

## 3. 关键约束

- `timing_plan` 中同一 `intersection_id` 最多一条 `status='active'`。
- 应用层校验：`ns_green > 8`、`ew_green > 8`、`ns_yellow > 0`、`ew_yellow > 0`、`(ew_green+ew_yellow) > 10`、`(ns_green+ns_yellow) > 10`。
- 不在数据库层做过强的“红灯 > 10”硬约束，避免后续全红阶段扩展时改表；校验放在 `TimingService`。

## 4. Alembic

```bash
cd backend
alembic revision --autogenerate -m "init tables"
alembic upgrade head
```

**验证**：`psql -c "\dt"` 应看到上述 4 张表。
