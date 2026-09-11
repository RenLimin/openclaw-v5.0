# 会话隔离组件设计

> L2 基础设施层 · 会话隔离组件
>
> **2026-09-11 更新**：基于实际代码重写设计文档（v2.0 — 与 session-isolation-sharing 合并后）。

## 1. 定位

| 维度 | 值 |
|---|---|
| 层级 | L2 基础设施层 |
| 组件类 | 会话隔离与编排 |
| 组件 ID | — |
| 状态 | ✅ 已实现 (v2.0, 2026-09-10) |
| ADR | ADR-012（运行时抽象）、ADR-202609-024（合并 sharing 组件） |
| 验证 | 51 个单元测试 |

## 2. 职责

会话隔离组件提供四大核心能力：

1. **Task Protocol（任务卡协议）**：YAML 格式任务卡，定义目标、依赖、优先级、作用域
2. **State Protocol（共享状态协议）**：跨会话状态共享，支持 3 种 reducer 合并策略
3. **Event Protocol（事件日志协议）**：append-only 事件流，记录任务全生命周期
4. **Task Scheduler（任务编排调度）**：拓扑排序 + 优先级 + 错峰发起 + 状态回写

## 3. 架构

```
┌─────────────────────────────────────────────────────────────┐
│                    cli.py (统一 CLI)                          │
│  task-init / state-write / state-read / state-list           │
│  event-log / event-read / scheduler                          │
├─────────────────────────────────────────────────────────────┤
│                SessionIsolationService                        │  统一服务层
├──────────┬──────────┬──────────┬───────────────────────────┤
│  Task    │  State   │  Event   │  Scheduler                │
│  Init    │  Reducer │  Logger  │  (scheduler.py)           │
│  (任务卡) │ (状态合并)│ (事件日志)│  (拓扑排序+错峰)           │
├──────────┴──────────┴──────────┴───────────────────────────┤
│                    scripts/utils.py                          │  通用工具 + 常量
├─────────────────────────────────────────────────────────────┤
│            adapters/openclaw/spawner.py                      │  L1 适配层
│            (sessions_spawn 封装)                              │
└─────────────────────────────────────────────────────────────┘
```

### 3.1 模块职责

| 模块 | 文件 | 职责 |
|---|---|---|
| service | `service.py` | 统一服务门面，整合四大协议 + 调度器 |
| scheduler | `scheduler.py` | 任务编排：拓扑排序、优先级、错峰发起 |
| task_init | `scripts/task_init.py` | 任务卡创建：目录结构 + YAML 填充 |
| state_reducer | `scripts/state_reducer.py` | 状态合并：3 种内置 reducer + 自定义注册 |
| event_logger | `scripts/event_logger.py` | 事件日志：append-only JSONL |
| spawner | `adapters/openclaw/spawner.py` | OpenClaw 子会话发起适配 |
| cli | `scripts/cli.py` | CLI 入口（7 个子命令） |
| utils | `scripts/utils.py` | 通用工具：ID 校验、路径、YAML、时间 |

### 3.2 数据模型

**Task**（任务数据类，对应 TASK.yml）：

```python
@dataclass
class Task:
    id: str                    # task-YYYYMMDD-slug
    name: str                  # 任务名称
    status: str                # pending | in-progress | done | blocked
    dependencies: List[str]    # 依赖任务 ID 列表
    priority: str              # urgent | high | medium | low
    scope: Dict[str, str]      # {project, component, version}
    goals: List[Dict]          # [{id, description, status}]
    blockers: List[str]        # 阻塞原因
    context: List[Dict]        # [{path: 上下文文件路径}]
    artifacts: List[Dict]      # 产出物
    created_at: str
    updated_at: str
    owner: str
    file_path: str             # TASK.yml 文件路径
```

## 4. 核心设计

### 4.1 Task Protocol（任务卡协议）

任务卡目录结构：

```
tasks/
└── in-progress/
    └── task-YYYYMMDD-slug/
        ├── TASK.yml          # 任务定义（YAML）
        ├── CONTEXT.md        # 现场上下文（会话重置后恢复用）
        └── events.jsonl      # 事件日志（append-only）
```

**TASK.yml 格式**：

```yaml
id: task-20260910-example
name: 示例任务
status: pending
priority: high
owner: main-agent
scope:
  project: my-project
  component: backend
  version: v1.0
goals:
  - id: g1
    description: 完成功能开发
    status: pending
dependencies: []
blockers: []
context:
  - path: docs/spec.md
artifacts: []
created_at: "2026-09-10T10:00:00+08:00"
updated_at: "2026-09-10T10:00:00+08:00"
```

**任务 ID 校验规则**：正则 `^task-\d{8}-[a-zA-Z0-9-]+$`，即 `task-YYYYMMDD-slug`。

**任务状态机**：

```
pending → in-progress → done
              ↓
           blocked → cancelled
```

### 4.2 State Protocol（共享状态协议）

状态按 scope 组织，存储为 JSON 文件：

```
state/
└── {scope}/
    └── {key}.json
```

例如 `state/project/bdms/config.json`。

**三种内置 Reducer**：

| Reducer | 行为 | 适用场景 |
|---|---|---|
| `last-write-wins` | 后写覆盖先写（默认） | 简单配置、状态标记 |
| `merge` | dict 浅合并，后写字段覆盖先写 | 配置项合并、元数据累积 |
| `append` | list 拼接（旧值非 list 时自动包装） | 日志、事件列表、产出物收集 |

支持通过 `register_reducer(name, fn)` 注册自定义 reducer。

### 4.3 Event Protocol（事件日志协议）

事件日志为 append-only 的 JSONL 文件（`events.jsonl`），每行一个 JSON 对象：

```json
{"ts": "2026-09-10T10:00:00+08:00", "type": "task.created", "by": "main-agent"}
{"ts": "2026-09-10T10:05:00+08:00", "type": "goal.updated", "goal_id": "g1", "new_status": "done"}
```

**标准事件类型**：

| 事件类型 | 触发时机 |
|---|---|
| `task.created` | 任务创建时自动记录 |
| `goal.updated` | 目标状态变更时自动记录 |
| 自定义 | 通过 `log_task_event` 手动记录 |

### 4.4 Task Scheduler（任务编排调度）

调度器核心流程：

1. **加载 pending 任务**：扫描 `tasks/in-progress/` 下所有 `status: pending` 的任务
2. **拓扑排序**：Kahn 算法，输出可并行批次
3. **优先级排序**：同批次内按 `urgent > high > medium > low` 排序
4. **错峰发起**：批次内任务间隔 `interval_sec`（默认 10s），避免 burst 限峰
5. **状态回写**：发起后立即更新 TASK.yml 的 status 为 `in-progress`

**拓扑排序示例**：

```
输入: A → B, A → C, B → D, C → D
输出: 批次1: [A] → 批次2: [B, C] → 批次3: [D]
```

**环检测**：排序后若 `len(done) != len(all_tasks)`，判定有环，返回空批次。

### 4.5 L1 适配层（Spawner）

`OpenClawTaskSpawner` 封装 OpenClaw `sessions_spawn` 工具：

- 从 Task 数据类组装任务描述（name + goals + dependencies）
- 延迟导入 `openclaw.tools.sessions_spawn`，避免非 OpenClaw 环境 import 失败
- 返回 `result.status == "accepted"` 判定为发起成功

## 5. CLI 接口

```bash
# 任务卡管理
python3 scripts/cli.py task-init \
    --task-id task-20260910-test \
    --name "测试任务" \
    --owner main-agent \
    --scope-project myproj \
    --scope-component api \
    --scope-version v1.0 \
    [--priority high] \
    [--context-paths docs/a.md docs/b.md]

# 状态管理
python3 scripts/cli.py state-write --scope project/test --key config \
    --data '{"timeout": 30}' [--reducer merge] [--root state]
python3 scripts/cli.py state-read --scope project/test --key config
python3 scripts/cli.py state-list --scope project/test

# 事件管理
python3 scripts/cli.py event-log --task-id task-20260910-test \
    --type task.started --data '{"by": "rex"}'
python3 scripts/cli.py event-read --task-id task-20260910-test [--limit N]

# 调度器
python3 scripts/cli.py scheduler [--dry-run] [--interval 10] \
    [--model <model>] [--timeout 1800]
```

## 6. Python API

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
    initial_status="pending",
)

# 2. 读写共享状态
svc.write_shared_state("project/my-project", "progress", {"done": 5, "total": 10})
data, _ = svc.read_shared_state("project/my-project", "progress")

# 3. 记录事件
svc.log_task_event("task-20260910-example", "goal.completed", {"goal_id": "g1"})

# 4. 运行调度器
stats = svc.run_scheduler(spawn_callback=my_spawn_fn, dry_run=True)
```

## 7. 存储结构

```
tasks/
├── _templates/              # 模板目录（预留）
├── in-progress/
│   └── task-YYYYMMDD-slug/
│       ├── TASK.yml          # 任务定义
│       ├── CONTEXT.md        # 现场上下文
│       └── events.jsonl      # 事件日志
├── done/                    # 已完成任务
└── archive/                 # 归档任务

state/
└── {scope}/
    └── {key}.json            # 共享状态
```

## 8. 依赖

| 依赖 | 来源 | 说明 |
|---|---|---|
| openclaw.tools.sessions_spawn | L1 适配层（可选） | 子会话发起，延迟导入 |
| utils.py | 本组件内 | ID 校验、YAML、时间等工具 |

外部依赖仅 Python 标准库 + PyYAML。

## 9. 测试

```bash
python3 -m pytest L2-infra/components/session-isolation/tests/ -v
```

51 个测试用例，覆盖：

| 测试文件 | 覆盖模块 | 用例数 |
|---|---|---|
| test_task_protocol.py | ID 校验、任务创建、目标更新 | 15 |
| test_state_protocol.py | 读写、三种 reducer、list/delete、自定义 | 14 |
| test_event_protocol.py | 追加、读取、limit、时间戳、清空 | 7 |
| test_scheduler.py | 数据类、拓扑排序、优先级、dry-run、spawn | 12 |
| test_integration.py | 完整生命周期、依赖调度、Service API | 3 |

## 10. 设计约束

1. **运行时无关 (ADR-012)**：核心逻辑纯 Python，不绑定 OpenClaw API
2. **默认隔离，显式共享**：通过 scope 控制状态可见范围
3. **零耦合优先**：协议层用纯文件/数据结构，不依赖 LLM 驱动
4. **原生优先**：并发控制、嵌套深度、限流复用运行时原生能力
5. **幂等创建**：重复创建同一 task_id 返回已存在错误，不覆盖
6. **append-only 事件**：事件日志只追加，clear 仅用于归档压缩

## 11. 演进方向

| 方向 | 优先级 | 触发条件 |
|---|---|---|
| 任务状态机增强 | 中 | 需要 blocked/cancelled 状态流转 |
| 调度器持久化 | 中 | 调度结果需要跨会话保留 |
| 状态 TTL/清理 | 低 | state 目录膨胀 |
| 事件查询增强 | 低 | 需要按类型/时间范围过滤 |

## 12. 变更记录

| 日期 | 变更 |
|---|---|
| 2026-09-10 | v2.0 — 与 session-isolation-sharing 合并，新增 scheduler/spawner，补全 51 个测试 |
| 2026-09-02 | v1.0 — 初始版本，Task/State/Event 三协议 + Service 层 |
| 2026-09-11 | 基于实际代码重写设计文档 |
