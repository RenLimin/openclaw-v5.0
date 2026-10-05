# 跨会话状态协作组件设计（已废弃）

> L2 基础设施层 · 跨会话状态协作组件
>
> **⚠️ 废弃声明**：本组件已于 2026-09-10 废弃，功能完全合并到 `session-isolation` 组件。
> 本文档保留用于历史参考。

## 1. 定位

| 维度 | 值 |
|---|---|
| 层级 | L2 基础设施层 |
| 组件类 | 跨会话状态协作 |
| 状态 | ❌ 已废弃 (2026-09-10) |
| 替代组件 | `L2-infra/components/session-isolation/` |
| ADR | ADR-012（运行时抽象）、ADR-202609-024（合并决策） |

## 2. 废弃原因

本组件与 `session-isolation` 职责高度重叠：

- 核心协议（task/state/event）在 `session-isolation`
- 调度器（scheduler）和发起器（spawner）在本组件
- 用户不知道该用哪个组件，API 入口分散

合并后统一为 `session-isolation` 一个组件，API 更简洁，维护成本更低。

## 3. 历史职责

本组件原提供以下能力（现已全部迁移到 `session-isolation`）：

1. **Task Scheduler**：多任务编排（拓扑排序、错峰发起、状态回写）
2. **OpenClaw Spawner**：基于 `sessions_spawn` 的子会话发起适配层
3. **CLI 调度入口**：`run_scheduler.py` 命令行工具

## 4. 架构（历史）

```
┌─────────────────────────────────────────────────────┐
│        scripts/cli/run_scheduler.py (CLI)            │
├─────────────────────────────────────────────────────┤
│              TaskScheduler                           │  任务编排
│        scripts/orchestrator/scheduler.py             │  (拓扑排序+错峰)
├─────────────────────────────────────────────────────┤
│          OpenClawTaskSpawner                         │  L1 适配层
│        adapters/openclaw/spawner.py                  │  (sessions_spawn)
├─────────────────────────────────────────────────────┤
│        session-isolation/scripts/utils.py            │  依赖工具层
└─────────────────────────────────────────────────────┘
```

### 4.1 模块职责（历史）

| 模块 | 文件 | 职责 | 迁移目标 |
|---|---|---|---|
| scheduler | `scripts/orchestrator/scheduler.py` | 任务编排调度器 | `session-isolation/scheduler.py` |
| spawner | `adapters/openclaw/spawner.py` | OpenClaw 子会话发起 | `session-isolation/adapters/openclaw/spawner.py` |
| cli | `scripts/cli/run_scheduler.py` | 调度器 CLI 入口 | `session-isolation/scripts/cli.py scheduler` |

## 5. 核心设计（历史）

### 5.1 Task Scheduler

与合并后 `session-isolation/scheduler.py` 逻辑一致：

1. 加载 `tasks/in-progress/` 下所有 pending 任务
2. Kahn 算法拓扑排序，输出可并行批次
3. 批次内按优先级排序（urgent > high > medium > low）
4. 错峰发起（默认间隔 10s），调用 spawn_callback
5. 发起后回写 TASK.yml 状态为 `in-progress`

### 5.2 OpenClaw Spawner

封装 `sessions_spawn` 工具：

- 从 Task 数据类组装任务描述
- 调用 `sessions_spawn(task=..., task_name=..., label=..., context="isolated", ...)`
- 返回 `result.status == "accepted"` 判定成功

### 5.3 Task 数据类

与 `session-isolation` 的 Task 完全一致，字段相同：

```python
@dataclass
class Task:
    id: str
    name: str
    status: str
    dependencies: List[str]
    priority: str
    scope: Dict[str, str]
    goals: List[Dict[str, str]]
    blockers: List[str]
    context: List[Dict[str, str]]
    artifacts: List[Dict[str, str]]
    created_at: str
    updated_at: str
    owner: str
    file_path: str
```

## 6. 迁移指南

### 6.1 目录映射

| 旧路径 | 新路径 |
|---|---|
| `session-isolation-sharing/scripts/orchestrator/scheduler.py` | `session-isolation/scheduler.py` |
| `session-isolation-sharing/adapters/openclaw/spawner.py` | `session-isolation/adapters/openclaw/spawner.py` |
| `session-isolation-sharing/scripts/cli/run_scheduler.py` | `session-isolation/scripts/cli.py scheduler` |

### 6.2 Python 导入迁移

**旧**：
```python
sys.path.insert(0, 'L2-infra/components/session-isolation-sharing/scripts')
from orchestrator.scheduler import TaskScheduler
```

**新**：
```python
sys.path.insert(0, 'L2-infra/components/session-isolation')
from scheduler import TaskScheduler, Task
from service import SessionIsolationService
```

### 6.3 CLI 迁移

**旧**：
```bash
python3 session-isolation-sharing/scripts/cli/run_scheduler.py --dry-run
```

**新**：
```bash
cd L2-infra/components/session-isolation
python3 scripts/cli.py scheduler --dry-run
```

## 7. 合并前后功能对比

| 能力 | 合并前 session-isolation | 合并前 sharing | 合并后 |
|---|---|---|---|
| Task Protocol | ✅ | ❌ | ✅ |
| State Protocol | ✅ | ❌ | ✅ |
| Event Protocol | ✅ | ❌ | ✅ |
| Task Scheduler | ❌ | ✅ | ✅ |
| OpenClaw Spawner | ❌ | ✅ | ✅ |
| 统一 CLI | ✅ (3 命令) | ✅ (单独脚本) | ✅ (7 命令) |
| Service 层 | ✅ | ❌ | ✅ (含 scheduler) |
| 测试 | 2 个 (空壳) | 0 个 | **51 个** |

## 8. 存储结构（保留文件）

```
session-isolation-sharing/
├── README.md                          # 废弃声明 + 迁移指南
├── DESIGN.md                          # 本文档
└── .deprecated/                       # 保留的源代码（不再维护）
    ├── adapters/openclaw/spawner.py
    └── scripts/
        ├── cli/run_scheduler.py
        └── orchestrator/scheduler.py
```

## 9. 设计约束（历史）

1. **运行时无关 (ADR-012)**：核心调度逻辑纯 Python，不绑定 OpenClaw API
2. **依赖 L1 适配层**：调度器只定义 spawn_callback 接口，具体发起由 L1 实现
3. **错峰发起**：批次内任务间隔可配置，避免 burst 限流
4. **状态回写**：发起后立即更新 TASK.yml，保证可恢复

## 10. 变更记录

| 日期 | 变更 |
|---|---|
| 2026-09-10 | 废弃，功能合并到 session-isolation 组件 |
| 2026-09-11 | 基于实际代码重写设计文档（标记废弃状态） |
