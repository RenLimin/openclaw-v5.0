# 长任务执行规范：Subagent + 持久化任务卡

> 适用场景：预计 > 5 步 exec / 大量文件读写 / 批量操作 / KB 文档生成
> 目的：主会话不崩，崩了能续，进度可查

---

## 为什么要这么做

主会话跑长任务的两个致命问题：

1. **上下文膨胀 → auto-compaction → 执行中被打断** → 状态不一致
2. **LLM 报错 / 连接重置 → 运行中断** → 进度全丢，得从头来

Subagent + 持久化任务卡解决这两个问题：
- 主会话只做调度，上下文不膨胀
- 任务进度持久化到磁盘，崩了从断点续
- 失败可重试，不用从头再来

---

## 三件套关系图

```
主会话 (agent:main:main)
    │
    ├─ current-task.md      ← 当前进行中的任务（全局唯一）
    │                         用途：主会话崩了 → heartbeat 捞起 → 读文件续跑
    │
    └─ 调用 subagent
         │
         ├─ 任务卡 (task-YYYYMMDD-slug/)   ← session-isolation 组件管理
         │    ├─ TASK.yml                   元数据 + 目标 + 状态
         │    ├─ events.jsonl               事件日志
         │    └─ state/                     状态快照
         │
         └─ subagent 会话 (独立上下文)
              崩了 → 主会话检测到 → 重新 spawn → 从任务卡恢复
```

---

## 主会话操作规范

### 1. 开始长任务前：写 current-task.md

```bash
python3 L2-infra/components/session-recovery/scripts/task_tracker.py start \
  --task-id "task-20260909-cissp-l3" \
  --name "CISSP 学习系统 L3 模块" \
  --description "重写 CISSP 学习系统 L3 核心领域模型 + 测试" \
  --phase "设计" \
  --steps '["需求分析","模型设计","代码实现","测试验证","归档交付"]'
```

**原则：重要任务一定先登记再开工。** 写 current-task.md 的成本 < 3 秒，但崩了之后能省你几十分钟。

### 2. 进度推进：定期 update

每完成一个阶段/大步骤后更新一次（不是每步 exec 都更）：

```bash
python3 L2-infra/components/session-recovery/scripts/task_tracker.py update \
  --phase "实现中" --step-index 2 \
  --progress "完成 5 个聚合根模型定义 + BaseRepository 适配"
```

### 3. 启动 subagent：同时创建任务卡

用 `subagent_spawn_with_card.py` 统一入口（见下），它会：
- 写 current-task.md（主会话视角）
- 用 task-init 创建任务卡（subagent 视角）
- spawn subagent
- 返回 session key

### 4. 完成后：complete 归档

```bash
python3 L2-infra/components/session-recovery/scripts/task_tracker.py complete \
  --result "5 个聚合根 + SM-2 算法 + 114 测试全通过"
```

---

## Subagent 任务卡（session-isolation）

subagent 收到任务后，自己的进度写在任务卡里：

```
tasks/in-progress/task-20260909-cissp-l3/
├── TASK.yml              # 元数据 + 目标 + 当前状态
├── events.jsonl          # 事件日志（每步 append）
├── state/
│   └── latest.json       # 最新状态快照
└── output/               # 产出物
    ├── summary.md
    └── ...
```

**事件类型**：
- `task.started` — 任务启动
- `goal.updated` — 目标状态变更
- `milestone.reached` — 里程碑达成
- `checkpoint.saved` — 检查点（可从此恢复）
- `task.completed` — 完成
- `task.failed` — 失败（含原因）

---

## 失败恢复流程

### 场景 A：主会话崩了，subagent 还在跑

1. heartbeat / 下次唤醒 → 主会话恢复
2. 读 current-task.md → 知道有未完成任务
3. 查对应 subagent 会话状态
   - 还在跑 → 等待 / 订阅结果
   - 已完成 → 收集结果、归档
   - 已失败 → 走场景 B

### 场景 B：subagent 崩了

1. 主会话检测到 subagent 状态 = failed
2. 读任务卡的 checkpoint 状态
3. 评估是否可续：
   - 有 checkpoint + 失败原因是瞬态（timeout/连接重置）→ 重新 spawn，从 checkpoint 续
   - 失败原因是代码错误 / 逻辑问题 → 修复后重跑
4. current-task.md failure_count +1
5. 超过 2 次 → 停止自动重试，等人介入

### 场景 C：主会话和 subagent 都崩了

1. heartbeat 唤醒主会话
2. 读 current-task.md → 找到任务
3. 查 subagent 任务卡 → 找到断点
4. 从断点恢复（同场景 B）

---

## Helper 脚本

### subagent_spawn_with_card.py

统一入口：创建任务卡 + 启动 subagent + 写入 current-task.md。

```bash
python3 L2-infra/components/session-recovery/scripts/subagent_spawn_with_card.py \
  --task-id "task-20260909-cissp-l3" \
  --name "CISSP 学习系统 L3 重写" \
  --description "重写 CISSP 学习系统 L3 核心领域模型" \
  --task-desc "完整的任务描述，传给 subagent" \
  --steps '["设计","实现","测试"]' \
  --component "cissp-learning" \
  --visible
```

输出：`{"session_key": "...", "task_id": "...", "status": "started"}`

---

## 防死循环规则

| 规则 | 阈值 | 说明 |
|---|---|---|
| 同一任务自动重试 | ≤ 2 次 | 超过则标记 blocked，等人工 |
| 重试最小间隔 | 5 分钟 | 防止瞬间反复重试 |
| subagent 单次运行 | 有 timeout | runTimeoutSeconds，防止挂死 |
| 失败原因相同 + 连续 2 次 | 停止重试 | 同样的错误不会因为重试而变好 |

---

## 相关文件

- current-task 管理器：`L2-infra/components/session-recovery/scripts/task_tracker.py`
- 失败检测与重试：`L2-infra/components/session-recovery/scripts/check_and_retry.py`
- 任务卡底层：`L2-infra/components/session-isolation/scripts/cli.py`
- 状态还原器：`L2-infra/components/session-isolation/scripts/state_reducer.py`
