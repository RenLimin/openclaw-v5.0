# L2 会话隔离组件 (session-isolation)

> **状态**: ✅ 已实现 (v2.0 — 2026-09-10 与 session-isolation-sharing 合并)
> **层级**: L2 基础设施层
> **设计文档**: `docs/architecture/components/session-isolation/DESIGN.md`
> **ADR**: ADR-202609-024

统一的会话隔离与编排组件，提供**任务卡协议 + 共享状态 + 事件日志 + 任务调度**四大能力。

---

## 功能概览

| 模块 | 职责 | 核心文件 |
|---|---|---|
| **Task Protocol** | 任务卡 YAML 协议（CRUD、目标、依赖） | `scripts/task_init.py` |
| **State Protocol** | 跨会话共享状态（3 种 reducer + 自定义） | `scripts/state_reducer.py` |
| **Event Protocol** | append-only 事件日志 | `scripts/event_logger.py` |
| **Task Scheduler** | 多任务编排（拓扑排序、优先级、错峰） | `scheduler.py` |
| **Spawner (OpenClaw)** | 基于 `sessions_spawn` 的子会话发起 | `adapters/openclaw/spawner.py` |
| **Service Layer** | 统一 API 入口 | `service.py` |
| **CLI** | 命令行工具 | `scripts/cli.py` |

---

## 目录结构

```
session-isolation/
├── __init__.py              # API 导出（延迟导入）
├── service.py               # 统一服务层 SessionIsolationService
├── scheduler.py             # 任务编排调度器
├── adapters/
│   └── openclaw/
│       └── spawner.py       # OpenClaw 子会话发起适配层
├── scripts/
│   ├── task_init.py         # 任务初始化
│   ├── state_reducer.py     # 共享状态 reducer
│   ├── event_logger.py      # 事件日志
│   ├── utils.py             # 通用工具 + 常量
│   └── cli.py               # CLI 入口
└── tests/                   # 测试 (51 用例)
    ├── conftest.py
    ├── test_task_protocol.py
    ├── test_state_protocol.py
    ├── test_event_protocol.py
    ├── test_scheduler.py
    └── test_integration.py
```

---

## 快速开始

### Python API

```python
from service import SessionIsolationService

svc = SessionIsolationService()

# 1. 创建任务
ok, msg = svc.create_task(
    task_id="task-20260910-example",
    name="示例任务",
    owner="main-agent",
    scope_project="my-project",
    scope_component="backend",
    scope_version="v1.0",
    goals=[{"id": "g1", "description": "完成功能", "status": "pending"}],
    priority="high",
    initial_status="pending",  # 或 in-progress
)

# 2. 读写共享状态
svc.write_shared_state("project/my-project", "progress", {"done": 5, "total": 10})
data, _ = svc.read_shared_state("project/my-project", "progress")

# 3. 记录事件
svc.log_task_event("task-20260910-example", "goal.completed", {"goal_id": "g1"})

# 4. 运行调度器（发起所有 pending 任务）
stats = svc.run_scheduler(spawn_callback=my_spawn_fn, dry_run=True)
```

### CLI

```bash
cd L2-infra/components/session-isolation

# 创建任务卡
python3 scripts/cli.py task-init \
  --task-id task-20260910-test \
  --name "测试任务" \
  --owner main-agent \
  --scope-project myproj \
  --scope-component api \
  --scope-version v1.0 \
  --priority high

# 写入共享状态
python3 scripts/cli.py state-write \
  --scope project/test --key config \
  --data '{"timeout": 30}' --reducer merge

# 读取共享状态
python3 scripts/cli.py state-read --scope project/test --key config

# 记录事件
python3 scripts/cli.py event-log \
  --task-id task-20260910-test \
  --type task.started \
  --data '{"by": "rex"}'

# 运行调度器（dry-run）
python3 scripts/cli.py scheduler --dry-run
```

---

## 核心概念

### 三种 Reducer

| Reducer | 行为 | 适用场景 |
|---|---|---|
| `last-write-wins` | 后写覆盖先写（默认） | 简单配置、状态标记 |
| `merge` | dict 浅合并，后写字段覆盖先写 | 配置项合并、元数据累积 |
| `append` | list 拼接 | 日志、事件列表、产出物收集 |

也可以通过 `register_reducer(name, fn)` 注册自定义 reducer。

### 任务状态机

```
pending → in-progress → done
              ↓
           blocked → cancelled
```

- `pending`：待调度，scheduler 会扫到并发起
- `in-progress`：已发起，正在执行
- `done`：已完成

### 调度批次

scheduler 按依赖关系做拓扑排序，输出若干批次：
- **同批内**：无依赖，可并行，按优先级排序（urgent → high → medium → low）
- **批次间**：串行，下一批依赖上一批完成

---

## 测试

```bash
cd openclaw-v5.0
python3 -m pytest L2-infra/components/session-isolation/tests/ -v
```

51 个测试用例，覆盖：
- Task Protocol（15 个）：ID 校验、创建、重复检测、字段验证、目标更新
- State Protocol（14 个）：读写、三种 reducer、list、delete、自定义 reducer
- Event Protocol（7 个）：追加、读取、limit、时间戳、数据字段、清空
- Scheduler（12 个）：数据类、拓扑排序（线性/扇入扇出/环/外部依赖）、优先级、dry-run、spawn 回调
- 集成测试（3 个）：完整生命周期、带依赖调度、Service 层全 API

---

## 设计原则

1. **运行时无关 (ADR-012)**：核心逻辑纯 Python，不绑定 OpenClaw API
2. **默认隔离，显式共享**：通过 scope 控制状态可见范围
3. **零耦合优先**：协议层用纯文件/数据结构，不依赖 LLM 驱动
4. **原生优先**：并发控制、嵌套深度、限流复用运行时原生能力，调度器只做排序和错峰

---

## 历史

- **v2.0 (2026-09-10)**：与 `session-isolation-sharing` 组件合并，统一为单一组件；新增 scheduler / spawner；补全 51 个测试；修复 task_init 字符串替换 bug
- **v1.0 (2026-09-02)**：初始版本 — Task/State/Event 三协议 + Service 层
