# Session Recovery — 会话断点恢复组件

> L2 基础设施层 · 会话失败自动恢复 + 长任务断点续跑
>
> **2026-09-11**：基于实际代码重写，对齐 task_tracker + check_and_retry 双脚本架构。

## 1. 定位

| 维度 | 值 |
|---|---|
| 层级 | L2 基础设施层 |
| 组件类 | 会话恢复 |
| 状态 | ✅ 已建设 (2026-09-09) |
| 关联规范 | `LONG-TASK-SPEC.md`（长任务执行规范）、AGENTS.md §会话恢复自检 |

## 2. 设计约束

1. **崩溃是常态**：LLM 超时、连接重置、Gateway 重启、auto-compaction 打断都应被恢复。
2. **状态外化**：任务进度必须持久化到磁盘（`memory/current-task.md`），不能只存在会话上下文中。
3. **有限重试**：自动重试上限 2 次，超过即停止，避免死循环。
4. **最小侵入**：恢复机制不耦合业务逻辑，只负责"检测 → 唤醒 → 提示从断点继续"。
5. **幂等归档**：任务完成后归档到 `memory/task-history/`，current-task.md 删除，可重复 start。

## 3. 架构

```
┌─────────────────────────────────────────────────────────┐
│                   主会话 (agent:main:main)                │
│                                                         │
│  ┌─────────────────┐     ┌──────────────────────────┐   │
│  │  task_tracker.py │     │  memory/current-task.md  │   │
│  │  (CRUD 管理器)   │◄───►│  (断点记忆文件)           │   │
│  └─────────────────┘     └──────────────────────────┘   │
│           │                            ▲                │
│           │ start/update/complete      │ 读写            │
│           ▼                            │                │
│  ┌─────────────────────────────────────────────────┐    │
│  │  memory/task-history/                           │    │
│  │  (归档目录: {timestamp}_{task_id}.md)            │    │
│  └─────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────┘
                          │
                          │ cron 每 10 分钟
                          ▼
┌─────────────────────────────────────────────────────────┐
│  check_and_retry.py                                     │
│  ┌──────────────┐  ┌───────────────┐  ┌──────────────┐  │
│  │ 读 current-  │  │ 检测主会话    │  │ sessions_    │  │
│  │ task.md      │──│ 是否 failed   │──│ send 唤醒    │  │
│  └──────────────┘  └───────────────┘  └──────────────┘  │
│                          │                               │
│                          ▼                               │
│  ┌──────────────────────────────────────────────────┐    │
│  │ memory/session-retry.log (操作日志)              │    │
│  └──────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────┘
                          ▲
                          │ 调用
┌─────────────────────────┴───────────────────────────────┐
│  cron_retry.sh (cron 入口脚本)                          │
│  每 10 分钟执行 check_and_retry.py --apply              │
└─────────────────────────────────────────────────────────┘
```

### 3.1 模块职责

| 模块 | 文件 | 职责 |
|---|---|---|
| 任务管理器 | `scripts/task_tracker.py` | current-task.md 的 CRUD：start / update / increment-fail / complete / current |
| 失败检测器 | `scripts/check_and_retry.py` | 检测主会话失败 + 自动唤醒重试 |
| Cron 入口 | `scripts/cron_retry.sh` | Shell 包装器，供 cron job 调用 |
| 规范文档 | `LONG-TASK-SPEC.md` | 长任务执行规范（三件套关系 + 防死循环规则） |
| 测试 | `tests/test_task_tracker.py` | task_tracker 单元测试（CRUD + frontmatter + 归档） |
| 测试 | `tests/test_check_and_retry.py` | check_and_retry 单元测试 |

## 4. 核心数据模型

### 4.1 current-task.md (frontmatter + body)

```markdown
---
task_id: task-20260909-retry
name: 会话失败自动重试
phase: 设计
step_index: 2
total_steps: 4
failure_count: 0
started_at: 2026-09-09T13:00:00
last_updated: 2026-09-09T14:30:00
---

实现主会话失败后的自动重试 + 断点恢复

### 进度记录
- [2026-09-09T13:00:00] 任务启动: 会话失败自动重试
- [2026-09-09T13:30:00] 完成 current-task 模块
- [2026-09-09T14:00:00] ⚠️ 失败 #1: LLM timeout
```

### 4.2 归档文件

归档到 `memory/task-history/{YYYYMMDD-HHMMSS}_{task_id}.md`，额外增加：

| 字段 | 说明 |
|---|---|
| `archived_at` | 归档时间 |
| `archive_reason` | `completed` / `interrupted-by-new` |
| `result` | 完成结果摘要 |

## 5. 核心 API (task_tracker.py)

```bash
# 开始新任务
python3 task_tracker.py start \
  --task-id "task-20260909-retry" \
  --name "会话失败自动重试" \
  --description "实现自动重试 + 断点恢复" \
  --phase "设计" \
  --steps '["盘现状","设计","实现","测试"]'

# 更新进度
python3 task_tracker.py update \
  --phase "实现中" --step-index 2 \
  --progress "已完成 current-task 模块"

# 失败计数 +1
python3 task_tracker.py increment-fail --reason "LLM timeout"

# 完成归档
python3 task_tracker.py complete --result "三个模块全通过"

# 查看当前任务
python3 task_tracker.py current [--json]
```

### 5.1 子命令说明

| 命令 | 作用 | 关键行为 |
|---|---|---|
| `start` | 创建新任务 | 如有旧任务先归档为 `interrupted-by-new` |
| `update` | 推进进度 | 可更新 phase / step_index / 追加进度文本 |
| `increment-fail` | 失败 +1 | failure_count++，追加 ⚠️ 进度条目 |
| `complete` | 完成归档 | 写入 task-history/，删除 current-task.md |
| `current` | 读取状态 | `--json` 输出结构化数据（最近 5 条进度） |

## 6. 失败恢复流程 (check_and_retry.py)

```
cron 触发 (每 10 分钟)
    │
    ▼
读取 current-task.md
    │
    ├── 无任务 → 跳过
    │
    ▼
failure_count >= 2？
    │
    ├── 是 → 停止，等人工介入
    │
    ▼
检测主会话状态 (openclaw sessions --agent main --json)
    │
    ├── 正常 → 无需重试
    │
    ▼
距上次失败 < 5 分钟？
    │
    ├── 是 → 再等等
    │
    ▼
--apply 模式？
    │
    ├── 否 → dry-run，仅日志
    │
    ▼
increment-fail → sessions_send 唤醒主会话
    │
    ▼
写入 memory/session-retry.log
```

### 6.1 关键配置常量

| 常量 | 值 | 说明 |
|---|---|---|
| `MAX_RETRIES` | 2 | 自动重试上限 |
| `MIN_RETRY_INTERVAL_MIN` | 5 | 两次重试最小间隔（分钟） |

### 6.2 子会话处理策略

子会话失败**只做信息记录，不触发主会话重试**。子会话有自己的任务卡，归 session-isolation / taskflow 组件管理。

## 7. 与其他组件的关系

```
session-recovery (本组件)
    │
    ├── 依赖 ─── memory/current-task.md (文件系统)
    │
    ├── 依赖 ─── openclaw sessions (CLI 检测会话状态)
    │
    ├── 依赖 ─── openclaw sessions send (CLI 唤醒会话)
    │
    ├── 被调用 ─ AGENTS.md §会话恢复自检 (主会话启动时读取)
    │
    ├── 被调用 ─ AGENTS.md §异常自动处置 (LLM timeout 恢复)
    │
    └── 协作 ─── session-isolation (subagent 任务卡，独立恢复路径)
```

## 8. 防死循环规则

| 规则 | 阈值 | 实现位置 |
|---|---|---|
| 同一任务自动重试 | ≤ 2 次 | `check_and_retry.py` → `MAX_RETRIES` |
| 重试最小间隔 | 5 分钟 | `check_and_retry.py` → `MIN_RETRY_INTERVAL_MIN` |
| subagent 单次运行 | 有 timeout | `sessions_spawn(runTimeoutSeconds)` |
| 失败原因相同 + 连续 2 次 | 停止重试 | 由 MAX_RETRIES 覆盖 |

## 9. 测试覆盖

| 测试文件 | 覆盖点 |
|---|---|
| `tests/test_task_tracker.py` | CRUD 操作、frontmatter 解析、failure_count 递增、归档逻辑、JSON 输出 |
| `tests/test_check_and_retry.py` | 失败检测、重试触发、dry-run 模式、间隔检查 |

运行测试：

```bash
python3 -m pytest L2-infra/components/session-recovery/tests/ -v
```

## 10. 演进方向

| 方向 | 优先级 | 触发条件 |
|---|---|---|
| 接入 OpenClaw cron 原生调度 | 中 | 替代 cron_retry.sh 的 shell 包装 |
| 子会话自动恢复 | 低 | 需 session-isolation 组件提供 checkpoint API |
| 恢复成功率统计 | 低 | task-history 积累 > 50 条后 |
| 指数退避重试间隔 | 低 | 频繁瞬时失败场景出现 |

## 11. 变更记录

| 日期 | 变更 |
|---|---|
| 2026-09-09 | task_tracker.py + check_and_retry.py 首版，实现断点记忆 + 自动重试 |
| 2026-09-09 | 增加 cron_retry.sh 入口，接入 OpenClaw cron |
| 2026-09-09 | LONG-TASK-SPEC.md 规范文档，定义三件套关系 |
| 2026-09-11 | 基于实际代码重写 DESIGN.md |
