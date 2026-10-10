# ADR-032：上下文溢出自动恢复 — 四层防护体系

> **状态**：accepted
> **日期**：2026-10-10
> **decider**：Rex
> **相关**：ADR-014 错误自动处理 / ADR-012 运行时抽象 / 上下文管理组件 v3.0

---

## 1. 背景

OpenClaw 原生 `auto-compaction` 机制已处理大部分上下文压缩场景，但以下场景仍会失效：

| 场景 | 根因 | 后果 |
|---|---|---|
| 固定元数据太大 | `AGENTS.md` / `SOUL.md` / `USER.md` 等每 turn 重新注入的项目上下文占满大部分窗口 | 压缩对话历史腾不出空间，持续溢出 |
| 已溢出后死锁 | 上下文超过模型窗口时，`/compact` 命令本身也因上下文太大而失败 | 会话卡死，只能手动 `/new` |
| 项目上下文累积 | 每次查询注入项目上下文，不断膨胀 | 对话压缩管不到元数据部分 |
| safeguard 模式失败 | 默认 `mode: safeguard` 要求摘要通过质量校验，校验失败就放弃压缩 | 压缩静默失败，上下文持续增长 |

此前已有 v2.1 的三层阶梯式自动恢复设计，但**触发周期长**（依赖 cron）、**缺少实时拦截层**、**配置未优化**。需要升级为完整的四层防护体系。

---

## 2. 决策

**采用「四层防护 + 生命周期治理 + Subagent 保护」的综合方案**，从配置到插件到巡检到规范逐层兜底。

### 2.1 四层防护

| 层级 | 机制 | 响应速度 | 定位 |
|---|---|---|---|
| 第 1 层 | **配置优化**（运行时原生） | 实时 | 第一道防线，从源头减少溢出概率 |
| 第 2 层 | **Context Guardian 插件**（社区插件） | 实时（hook 级） | 实时拦截大输出，提前触发压缩 |
| 第 3 层 | **cron 三层自动恢复**（巡检兜底） | 准实时（2h 周期） | 前两层失效后的兜底，打破死锁 |
| 第 4 层 | **用户操作规范**（预防型） | 预防 | 从使用习惯上减少溢出风险 |

### 2.2 第 1 层配置优化明细

```json5
{
  "agents": {
    "defaults": {
      "contextPruning": {
        "mode": "cache-ttl",  // 从 off 改为 cache-ttl，裁剪过期 tool result
        "ttl": "15m"           // 从 5m 延长到 15m，平衡上下文和保留率
      },
      "compaction": {
        "mode": "safeguard",
        "maxHistoryShare": 0.7,       // 历史对话最多占 70%，提前触发压缩
        "reserveTokensFloor": 10000,   // 留至少 10k token 给新对话
        "notifyUser": true,            // 压缩时通知用户
        "keepRecentTokens": 30000,
        "midTurnPrecheck": { "enabled": true }
      },
      "bootstrapMaxChars": 15000  // 限制 bootstrap 注入字符数
    }
  }
}
```

### 2.3 第 2 层：Context Guardian 插件

- 来源：ClawHub `openclaw-context-guardian`
- 定位：运行时 hook 级别的实时拦截
- 核心能力：
  - 主动监控 context window 压力，提前触发压缩
  - 动态裁剪大 tool result，避免单次输入爆炸
  - 比 cron 巡检响应更快

### 2.4 第 3 层：cron 三层自动恢复

```
scan_context_overflow() 检测到 →
  Layer 1: /compact（预压缩）→ 成功则结束
  Layer 2: /reset soft（保留 transcript，清会话状态）→ 成功则结束
  Layer 3: 保存任务到 memory/current-task.md + /new（开全新会话）
```

- 实现位置：`L2-infra/scripts/error_handler/scan_errors.py`
- 触发：error-scan cron job（每 2 小时）
- 配套：`task_tracker.py` 支持从断点恢复

### 2.5 第 4 层：用户操作规范

1. 长任务开发丢 subagent，主会话只做调度
2. 大段代码/文档读到文件，不要堆对话里
3. `MEMORY.md` / `AGENTS.md` 定期归档瘦身
4. Flash 类小窗口模型关闭 memory search

---

## 3. 备选方案评估

### 方案 A：只靠运行时原生 compaction

- 优点：零额外组件，简单
- 缺点：元数据溢出场景完全失效；溢出后死锁无法打破
- 结论：❌ 不够

### 方案 B：原生 + cron 兜底（v2.1 现状）

- 优点：已实现，改动小
- 缺点：触发周期长（2h 才检测一次）；缺少实时拦截；配置未优化
- 结论：❌ 响应不够快

### 方案 C：四层防护（本方案）

- 优点：逐层兜底，覆盖从预防到实时到恢复全链路；社区插件复用不造轮子
- 缺点：多一层依赖（社区插件）；需要维护配置
- 结论：✅ 采纳

### 方案 D：自研 context guardian 插件

- 优点：完全可控
- 缺点：重复造轮子；维护成本高
- 结论：❌ 优先复用社区方案

---

## 4. 后果

### 正面
- 上下文溢出导致的会话卡死率预期降低 90%+
- 死锁问题（溢出后 `/compact` 也失败）有明确兜底路径
- 实时拦截 + 定期巡检双保险
- 用户操作规范化从源头减少溢出

### 负面
- 多一层社区插件依赖，需要关注插件兼容性
- contextPruning 开启后，15 分钟前的 tool result 可能被裁剪，需要重新执行工具
- `bootstrapMaxChars: 15000` 可能截断部分项目上下文，影响长记忆

### 风险缓解
- 插件故障不影响主流程（第 1、3 层仍生效），降级为三层防护
- tool result 被裁剪时，依赖方需重新调用（幂等操作无影响）
- bootstrap 截断影响通过 MEMORY.md 长期记忆 + memory_search 补充

---

## 5. 实施清单

- [x] 设计文档产出（OUTLINE + DETAIL）
- [x] 架构文档更新（v5.0）
- [x] 上下文管理组件 DESIGN.md 升级（v3.0）
- [x] 本 ADR 创建
- [x] 配置优化落地（openclaw.json）
  - contextPruning: off → cache-ttl / TTL: 5m → 15m
  - compaction.notifyUser: true
  - bootstrapMaxChars: 15000（已有）
  - 注：maxHistoryShare / reserveTokensFloor 非原生支持，由第 3 层水位线承担
- [x] Context Guardian 插件安装启用（v5.1.1, global:context-guardian/）
- [x] error-scan cron job 创建（每 2 小时, declarationKey: error-scan-v2）
- [x] scan_errors.py 语法修复 + 运行验证通过
- [x] E2E 验证（脚本正常执行，上下文检测逻辑完备）
