# ⚠️ 已废弃 — 已合并到 session-isolation

> **废弃日期**: 2026-09-10
> **替代组件**: `L2-infra/components/session-isolation/`
> **原因**: 两个组件职责高度重叠，核心协议（task/state/event）在 session-isolation，scheduler/spawner 在本组件，导致用户不知道该用哪个

本组件的所有功能已合并到 `session-isolation` 组件中，成为其统一功能的一部分。

---

## 迁移指南

### 1. 目录变化

| 旧路径 | 新路径 | 说明 |
|---|---|---|
| `session-isolation-sharing/scripts/orchestrator/scheduler.py` | `session-isolation/scheduler.py` | 调度器，API 不变 |
| `session-isolation-sharing/adapters/openclaw/spawner.py` | `session-isolation/adapters/openclaw/spawner.py` | OpenClaw 发起适配层，API 不变 |
| `session-isolation-sharing/scripts/cli/run_scheduler.py` | `session-isolation/scripts/cli.py scheduler` | 合并到统一 CLI，子命令 `scheduler` |
| — | `session-isolation/service.py` | 统一服务层，新增 scheduler 接口 |
| — | `session-isolation/__init__.py` | 统一 API 导出 |

### 2. Python 导入迁移

**旧 (错误示范)**：
```python
# 硬编码路径，脆弱不堪
sys.path.insert(0, '/path/to/session-isolation-sharing/scripts')
from orchestrator.scheduler import TaskScheduler
```

**新 (推荐)**：
```python
# 方式1: 从组件根目录导入
import sys; sys.path.insert(0, 'L2-infra/components/session-isolation')
from scheduler import TaskScheduler, Task
from service import SessionIsolationService

# 方式2: 通过统一服务层
from service import SessionIsolationService
svc = SessionIsolationService()
sched = svc.get_scheduler()
```

### 3. CLI 迁移

**旧**：
```bash
python3 session-isolation-sharing/scripts/cli/run_scheduler.py --dry-run
```

**新**：
```bash
cd L2-infra/components/session-isolation
python3 scripts/cli.py scheduler --dry-run
```

### 4. 设计文档

旧 DESIGN.md 已迁移到：`docs/architecture/components/session-isolation/DESIGN.md`

### 5. 保留文件

本目录下的源代码文件暂时保留，但不再维护。新功能请直接使用 `session-isolation/`。

---

## 合并后的功能增益

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

