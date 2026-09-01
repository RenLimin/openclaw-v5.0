# L2 错误自动处理组件 — 设计

> **状态**: ✅ 已上线 (2026-09-01) — cron 已重建（错误扫描每 2h + provider 探测每小时）
> **ADR**: [ADR-202608-014](../../../knowledge-base/by-category/project-experience/adr/ADR-202608-014-error-auto-handling.md)
> **层级**: L2 基础设施层
> **创建**: 2026-08-24

## 1. 问题定义

Agent 运行过程中会产生各类错误和警告:**没有自动处理机制**会导致:

| 错误类型 | 示例 | 当前行为 | 期望行为 |
|---|---|---|---|
| **模型调用超时** | provider 网络抖动 | 会话中断,需人工介入 | 自动重试 → 降级模型 → 通知 |
| **compaction 失败** | 压缩模型不可用 | 上下文溢出 → 会话卡死 | 切换压缩模型 → 预警 |
| **cron 任务失败** | 模型 API 报错 | 仅记录,无告警 | 分级告警 → 自动重试 |
| **记忆检索降级** | embedding provider 挂 | 静默降级为 keyword | 自动检测 → 尝试恢复 → 告警 |
| **工具执行失败** | 命令返回非零 | 错误注入上下文,可能中断 | 判断可重试性 → 重试或优雅降级 |
| **上下文溢出** | 接近 ctx 上限 | 等 compaction 触发 | 主动分流 → 子代理 → 落盘 |

**核心问题**: 错误处理散落在各 EXP 卡片中,没有统一的检测→分级→自愈闭环。

## 2. 设计原则

1. **检测先于处理**: 先发现错误,再决定如何处理
2. **分级响应**: 不同 severity 用不同策略(Sev4 仅记录 → Sev1 立即通知)
3. **自愈优先**: 能自动恢复的不通知人类
4. **优雅降级**: 自愈失败时降级而非中断
5. **通知兜底**: 无法自愈时通知 Rex,附带诊断信息

## 3. 错误检测→分级→自愈闭环

```
检测(Detect) → 分级(Classify) → 自愈(Heal) → 通知(Notify)
     ↑              │                │              │
     │              ▼                ▼              ▼
     │         Sev1-4           成功/失败      仅 Sev1-2
     │                           │              │
     └───────────────────────────┴──────────────┘
                    持续监控
```

### 3.1 检测层

| 检测手段 | 覆盖错误 | 实现 |
|---|---|---|
| **cron 健康监控** | cron 任务失败 | cron 内置 failureAlert |
| **记忆检索探针** | embedding 降级 | 已有 memory_search_monitor.py |
| **上下文水位监控** | 上下文溢出 | 已有溢出防护状态机 |
| **会话错误扫描** | 模型调用失败/工具失败 | 新增 cron 定期扫描 |
| **provider 健康检查** | API 不可用/超时 | 新增 cron 定期探测 |

### 3.2 分级层(对齐 ADR-011 Error Contract)

| severity | 含义 | 自愈策略 | 通知 |
|---|---|---|---|
| `Sev1` 致命 | 系统不可用 | 立即自愈 + 失败则通知 | 立即通知 Rex |
| `Sev2` 严重 | 核心功能受损 | 自动自愈 | 下次 heartbeat 汇总 |
| `Sev3` 警告 | 功能降级但可用 | 尝试自愈 | 每日观测摘要汇总 |
| `Sev4` 信息 | 预期内异常 | 记录 | 仅日志 |

### 3.3 自愈层

| 错误 | 自愈动作 | 失败后 |
|---|---|---|
| 模型调用超时 | 重试 1 次 → 切换 fallback 模型 | 通知 Rex |
| compaction 失败 | 切换压缩模型 → 收紧上下文 | 通知 Rex |
| 记忆检索降级 | 尝试重建索引(`memory index --force`) | 通知 Rex |
| 工具执行失败 | 判断 retryable → 重试或跳过 | 记录 |
| 上下文溢出 | 分流到子代理 → 落盘 checkpoint | 通知 Rex |
| cron 任务失败 | 自动重试(最多 2 次) | 通知 Rex |

### 3.4 通知层

| 通道 | 触发条件 | 内容 |
|---|---|---|
| **WeCom**(未来) | Sev1-2 自愈失败 | 错误摘要 + 诊断 + 建议操作 |
| **每日观测摘要** | Sev3-4 汇总 | 当日错误统计 |
| **即时通知** | Sev1 | 立即推送 |

## 4. 实现方案

### 4.1 新增 cron 任务:会话错误扫描

```json5
{
  name: "会话错误自动处理",
  schedule: { kind: "cron", expr: "0 */2 * * *", tz: "Asia/Shanghai" },
  payload: {
    kind: "agentTurn",
    message: "执行会话错误扫描和自动处理:\n1. 检查最近 2h 的 cron runs 是否有失败\n2. 检查主会话上下文水位\n3. 检查记忆检索健康状态\n4. 对可自愈的错误执行自愈\n5. 汇总报告",
  },
  sessionTarget: "isolated",
  deleteAfterRun: true,
}
```

### 4.2 新增 cron 任务:provider 健康探测

```json5
{
  name: "provider 健康探测",
  schedule: { kind: "cron", expr: "0 */1 * * *", tz: "Asia/Shanghai" },
  payload: {
    kind: "agentTurn",
    message: "执行 provider 健康探测:\n1. 对每个配置的模型发送轻量请求\n2. 记录响应时间和成功率\n3. 标记不健康的 provider\n4. 如有 provider 连续 3 次失败,通知 Rex",
  },
  sessionTarget: "isolated",
  deleteAfterRun: true,
}
```

### 4.3 为现有 cron 任务配置 failureAlert

| 任务 | failureAlert |
|---|---|
| 记忆检索健康监控 | ✅ after: 2, mode: announce |
| 每日观测摘要 | ✅ after: 2, mode: announce |

### 4.4 错误处理脚本(可选增强)

`scripts/observability/error_handler.py`:
- 扫描会话错误日志
- 按 Error Contract 分级
- 执行预定义的自愈规则
- 产出结构化报告

## 5. 验证标准

- 错误检测覆盖率: ≥ 5 种错误类型
- 自愈成功率: Sev3-4 ≥ 80% 自动恢复
- 通知延迟: Sev1 ≤ 5min, Sev2 ≤ 30min
- 误报率: < 5%(不应通知的错误被通知)

## 6. 风险

| 风险 | 防范 |
|---|---|
| 自愈引入新问题 | 自愈前先 dry-run 评估 |
| 通知风暴 | 同类错误合并通知,cooldown 5min |
| 误判正常为错误 | 分级阈值保守,宁可漏报不误报 |
| 自愈循环 | 重试上限 2 次,超过则人工介入 |
