# L2 会话隔离与共享 — 设计文档

> **状态**: 📐 设计态 (2026-09-02)
> **ADR**: [ADR-202609-024](../../../knowledge-base/by-category/project-experience/adr/ADR-202609-024-session-isolation-sharing.md) (proposed)
> **层级**: L2 基础设施层
> **创建**: 2026-09-02
> **版本**: v1.0

---

## 1. 问题定义

Agent 运行时存在多种会话:主会话、子代理会话、cron 运行会话、探测会话。当前:

| 问题 | 现状 | 后果 |
|---|---|---|
| **会话间无隔离** | 子代理共享父会话上下文(部分场景),cron 与业务会话混跑 | 上下文污染,任务状态互相干扰 |
| **会话间无共享** | 任务进度靠 transcript 传递,reset 后丢失 | 长任务不可持续,跨会话协作靠人肉 |
| **任务上下文易失** | `/reset` / compaction 后任务上下文丢失 | 会话重置后无法恢复任务现场 |
| **无故障隔离** | 子代理失败可能影响父会话 | 单个任务失败拖累整体 |

**核心目标**: 提供**跨会话的隔离与共享机制**,让任务状态可持久、可恢复、可协作,同时保证会话间互不污染。

---

## 2. 设计原则

1. **运行时无关 (ADR-012)**: L2 只依赖 L1 抽象契约,不绑定 OpenClaw 具体 API
2. **默认隔离,显式共享**: 会话间默认互不可见,通过显式 API 共享
3. **零耦合优先**: 共享状态用纯文件/数据结构,机制本身不依赖 LLM 驱动
4. **与现有组件正交**:
   - 会话生命周期管理(ADR-013): 管**清理**(删除/归档过期会话)
   - 上下文管理(ADR-018): 管**溢出**(compaction token 水位)
   - 错误自动处理(ADR-014): 管**故障**(检测→分级→自愈)
   - **本组件管「隔离与共享」**(跨会话状态协作) — 四者互不重叠

---

## 3. 架构分层

### 3.1 总体分层

```
┌──────────────────────────────────────────────────────┐
│  L4 业务层（零耦合）                                  │
│  任务卡 / 项目上下文 / 协作工作流                     │
├──────────────────────────────────────────────────────┤
│  L3 协议层（零耦合）                                  │
│  Task Protocol · State Protocol · Event Protocol     │
│  （纯文件 / 纯数据结构，不依赖任何 AI 框架）            │
├──────────────────────────────────────────────────────┤
│  L2 服务层（运行时无关）                              │
│  会话隔离共享服务：只依赖 L1 抽象接口                  │
│  （唯一业务逻辑层，未来换框架无需改动）                 │
├──────────────────────────────────────────────────────┤
│  L1 适配层（绑定运行时）                              │
│  adapters/openclaw/：实现 L1 抽象接口                 │
│  （OpenClaw 特有 hooks/API 全部在此层）                │
└──────────────────────────────────────────────────────┘
```

### 3.2 与 L1 抽象契约的映射

本组件通过 L1 最小能力契约访问运行时,不直接调用 OpenClaw API:

| 本组件需求 | L1 抽象接口 | OpenClaw 实现位置 |
|---|---|---|
| 会话创建/隔离 | `session_create(scope)` | `adapters/openclaw/adapter.py` |
| 会话状态查询 | `context_status()` | 运行时上下文系统 |
| 记忆读写 | `memory_read/write/search` | 运行时记忆系统 |
| 会话间发送 | `session_send(target, msg)` | `adapters/openclaw/adapter.py` |
| 会话历史读取 | `session_history(key)` | `adapters/openclaw/adapter.py` |

> **约束**: 所有 OpenClaw 特有 hooks (`before_prompt_build` / `agent_end` / `before_reset`) **只允许出现在 adapters/openclaw/ 中**,L2 服务层不可见。

---

## 4. L3 协议层设计（零耦合核心）

### 4.1 Task Protocol（任务协议）

纯 YAML/Markdown 结构,任何能读文件的系统(AI/脚本/CI/人)都能用:

```yaml
# tasks/<task_id>/TASK.yml
id: task-20260902-001
name: BDMS L4 交付月报修复
status: in-progress        # pending | in-progress | blocked | done | cancelled
priority: high
created_at: 2026-09-02T20:00:00+08:00
updated_at: 2026-09-02T21:30:00+08:00
owner: main-agent
scope:
  project: bdms-l4
  component: delivery-report
  version: v1.0

goals:
  - id: g1
    description: 修复签约/POC 行数日期过滤
    status: done
  - id: g2
    description: 修复列名对齐
    status: done
  - id: g3
    description: 完整生成验证所有 Sheet 匹配
    status: in-progress

blockers: []

context:
  - path: docs/architecture/06-l4-bdms.md
  - path: tasks/task-20260902-001/CONTEXT.md
  - path: tasks/task-20260902-001/ARTIFACTS.md

artifacts:
  - name: 修复后的 delivery_report.py
    path: scripts/l4/delivery_center/delivery_report.py
    status: done
```

### 4.2 State Protocol（共享状态协议）

跨会话共享状态,通过命名空间显式控制可见范围:

```
state/
  projects/
    bdms-l4/
      state.json          # 项目级共享状态
      progress.json
  global/
    knowledge-index.json  # 全局知识索引
  users/
    rex/
      preferences.json    # 用户级
```

**Scoping 规则**（借鉴 Mem0 四维模型）:

| scope | 可见范围 | 写入权限 |
|---|---|---|
| `session:<id>` | 仅当前会话 | 当前会话 |
| `task:<id>` | 所有参与该任务的会话 | 任务参与者(需 reducer 合并) |
| `project:<id>` | 同一项目所有会话 | 项目内(需 reducer 合并) |
| `user:<id>` | 该用户所有会话 | 该用户会话 |
| `global` | 所有会话 | 仅系统级 |

**并行写入策略**（借鉴 LangGraph reducer）:
- 每个状态字段定义 reducer: `append` / `merge` / `last-write-wins` / `conflict-detect`
- 写入前读 → reducer 合并 → 写入,避免 race condition
- 不是锁,是确定性合并规则

### 4.3 Event Protocol（事件协议）

任务状态变化的审计日志,纯 append-only:

```jsonl
# tasks/<task_id>/events.jsonl
{"ts": "2026-09-02T20:00:00+08:00", "type": "task.created", "task_id": "...", "by": "rex"}
{"ts": "2026-09-02T20:15:00+08:00", "type": "goal.completed", "goal_id": "g1", "by": "session-xxx"}
{"ts": "2026-09-02T21:00:00+08:00", "type": "subtask.spawned", "subtask_id": "sub-001", "by": "session-xxx"}
{"ts": "2026-09-02T21:05:00+08:00", "type": "subtask.completed", "subtask_id": "sub-001", "result": "..."}
```

---

## 5. 与现有组件的边界（防冲突）

| 组件 | 职责 | 本组件边界 |
|---|---|---|
| **会话生命周期管理** (ADR-013) | 清理过期会话 | 本组件**不**做清理;任务卡目录**不在**其清理范围内(需在 cleanup 时排除 `tasks/`) |
| **上下文管理** (ADR-018) | compaction 溢出防护 | 本组件**不**碰 token 水位;状态注入走独立共享 API,不占用 prompt 预算 |
| **错误自动处理** (ADR-014) | 检测→分级→自愈 | 本组件**不**做自愈;子代理 supervisor 留待 ADR-014(范围不膨胀) |
| **记忆语义检索** (ADR-009) | embedding 检索 | 本组件状态存文件/SQLite,与记忆检索组件**不同存储** |

---

## 6. 建设阶段

### P0: 手动版（当前阶段）

- [x] 组件目录创建
- [x] 本 DESIGN.md
- [ ] ADR 编写
- [ ] `tasks/` 目录 + TASK.yml 模板
- [ ] 迁移当前 BDMS 任务做验证

### P1: 半自动（脚本驱动）

- [ ] `scripts/session_isolation/` 工具集
  - [ ] `task_init.py` — 创建任务卡
  - [ ] `state_reducer.py` — 共享状态合并
  - [ ] `event_logger.py` — 事件追加
- [ ] 适配层扩展 `adapters/openclaw/` (L1 接口)
- [ ] 手动触发 hook 同步

### P2: 全自动（plugin 驱动）

- [ ] OpenClaw plugin 化（适配层内）
- [ ] 完整 reducer + 子代理 supervisor
- [ ] 跨框架可移植验证

---

## 7. 验证标准

1. **隔离**: 子代理会话独立上下文,不污染父会话
2. **共享**: 跨会话通过 State Protocol 显式读写,reducer 正确处理并行写入
3. **恢复**: `/reset` 后新会话通过 TASK.yml + events 恢复任务现场
4. **零耦合**: L2 服务层零 OpenClaw 特有概念(对齐 ADR-012 验证标准)
5. **防冲突**: 不影响会话生命周期清理 / 上下文管理 / 错误处理

---

## 8. 风险与防范

| 风险 | 防范 |
|---|---|
| 任务卡被 cleanup 误删 | session-lifecycle 清理时排除 `tasks/` |
| 状态文件膨胀 | 事件日志按任务归档,长任务定期压缩 |
| 并行写入冲突 | reducer 确定性合并,非锁 |
| 与上下文管理抢 prompt 预算 | 状态注入走独立 API,不占上下文 |
| 范围膨胀(加入 supervisor) | P0-P2 各阶段明确边界,supervisor 归 ADR-014 |

---

## 9. 变更历史

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-09-02 | v1.0 | 创建:会话隔离与共享组件设计 |

