# Session Recovery — 会话恢复机制

> 解决"主会话 LLM 报错/reset 后，上下文全丢、无法自恢复"的问题。

## 三大支柱

| 组件 | 职责 | 文件 |
|---|---|---|
| **current-task.md** | 断点记忆 — 当前在做什么、做到哪了 | `memory/current-task.md` |
| **fail-retry cron** | 失败自动重试 — 检测到主会话挂了自动唤醒 | `L2-infra/components/session-recovery/scripts/check_and_retry.py` |
| **task-card 规范** | 长任务持久化 — subagent 任务卡，崩了能续 | `L2-infra/components/session-isolation/scripts/cli.py` + 规范文档 |

## 触发场景

- LLM 请求超时 / 连接重置 / 429 限流 → 运行中断
- 会话被 reset（`The agent run failed before producing a reply`）
- Gateway 重启导致运行中断
- subagent 长任务中途挂掉

## 恢复流程

```
检测到失败
    ↓
读取 memory/current-task.md
    ↓
失败次数 < 2？ → 是 → 自动重入（sessions_send 唤醒主会话）
    ↓ 否
超过阈值 → 标记为 blocked，等人工介入
```
