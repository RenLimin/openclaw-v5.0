# L2 会话生命周期管理组件 — 设计

> **状态**: 阶段 1 已实现(pruneAfter=48h) + 阶段 2 建设中(自动 cleanup + deleteAfterRun)
> **ADR**: [ADR-202608-013](../../../knowledge-base/by-category/project-experience/adr/ADR-202608-013-session-lifecycle-management.md)
> **层级**: L2 基础设施层
> **创建**: 2026-08-24

## 1. 问题定义

Agent 运行时会持续产生会话(主会话、子代理会话、cron 运行会话、探测会话)。**没有生命周期管理**会导致:

| 问题 | 后果 | 已发生 |
|---|---|---|
| 会话无限增长 | SQLite 膨胀,查询变慢 | ✅ 08-23 清理前 19 个会话 |
| cron run 残留 | 每次 cron 运行产生一个会话,日积月累 | ✅ 当前 4 个 cron run 会话 |
| subagent 残留 | 完成的子代理会话不会自动消失 | ✅ 当前 2 个旧 subagent 会话 |
| 孤立 transcript | 会话记录文件与 SQLite 索引不一致 | ⚠️ 潜在风险 |

**核心问题**: `pruneAfter=48h` 是被动清理(等会话"过期"才删),没有主动清理机制。且 `pruneAfter` 不清理被 cron 历史引用的 cron run 会话。

## 2. 设计原则

1. **自动无需人工**: 清理全自动,不依赖 Rex 手动触发
2. **分级清理**: 不同会话类型用不同策略(cron run / subagent / probe / 主会话)
3. **安全优先**: 主会话和活跃会话绝对不受影响
4. **可观测**: 每次清理产出报告,可追溯

## 3. 清理策略

### 3.1 会话分级

| 会话类型 | 识别方式 | 清理策略 | 保留条件 |
|---|---|---|---|
| **主会话** | `agent:<id>:main` | ❌ 永不清理 | — |
| **活跃子代理** | `agent:<id>:subagent:*` + 最近活跃 | ❌ 保留 | 24h 内有活动 |
| **已完成子代理** | `agent:<id>:subagent:*` + 已完成 + 7d 前 | ✅ 清理 | 完成超 7d |
| **cron run** | `agent:<id>:cron:*:run:*` | ✅ 清理 | 完成后立即(deleteAfterRun) |
| **探测会话** | `agent:<id>:explicit:probe-*` | ✅ 清理 | 完成后 24h |
| **cron 主会话** | `agent:<id>:cron:<jobId>` | ⚠️ 保留最新 2 | 超 2 个的历史版本 |
| **孤立记录** | SQLite 有记录但 transcript 缺失 | ✅ 清理 | 立即 |

### 3.2 清理触发方式

| 触发 | 频率 | 手段 |
|---|---|---|
| **cron 自动清理** | 每日 02:00 CST | `openclaw sessions cleanup --enforce` |
| **cron run 即时清理** | 每次 cron 完成后 | `deleteAfterRun: true` |
| **pruneAfter 被动清理** | 持续 | `session.maintenance.pruneAfter=48h`(已有) |

### 3.3 保护机制

- `--active-key agent:main:main`: 主会话永不清理
- 清理前 `--dry-run` 预览(首次部署时验证)
- 清理报告写入日志

## 4. 实现方案

### 4.1 新增 cron 任务:每日会话清理

```json5
{
  name: "会话生命周期管理",
  schedule: { kind: "cron", expr: "0 2 * * *", tz: "Asia/Shanghai" },
  payload: {
    kind: "agentTurn",
    message: "执行每日会话清理:\n1. 运行 `openclaw sessions cleanup --enforce --active-key agent:main:main`\n2. 统计清理前后会话数\n3. 报告清理结果",
  },
  sessionTarget: "isolated",
  deleteAfterRun: true,
  model: "coding-plan/ark-code-latest",
  fallbacks: ["coding-plan/deepseek-v4-flash"],
}
```

### 4.2 为现有 cron 任务启用 deleteAfterRun

| 任务 | 当前 deleteAfterRun | 目标 |
|---|---|---|
| 记忆检索健康监控 | ❌ | ✅ true |
| 每日观测摘要 | ❌ | ✅ true |
| Memory Dreaming | ❌ | ✅ true |

### 4.3 清理脚本(可选增强)

如果官方 cleanup 命令不够,自建 `scripts/session_cleanup.py`:
- 按分级策略精确清理
- 产出结构化报告
- 支持 `--dry-run` 模式

## 5. 验证标准

- 每日 02:00 自动执行清理
- 主会话永不受影响
- cron run 会话完成后立即删除
- 已完成 7d+ 的子代理会话自动清理
- 清理报告可追溯

## 6. 风险

| 风险 | 防范 |
|---|---|
| 误删活跃会话 | `--active-key` 保护 + 分级策略 |
| 清理失败 | cron 任务有 fallback 模型 |
| 清理过于激进 | 首次部署用 `--dry-run` 验证 |
