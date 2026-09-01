# L2 上下文管理 — 设计文档

> 版本：v1.0
> 创建日期：2026-09-01
> 状态：✅ 已上线
> 层级：L2 基础设施层

---

## 一、概述

### 1.1 定位

自动管理 AI Agent 的上下文溢出问题，确保长会话的稳定性。

### 1.2 核心目标

1. **自动压缩**：上下文接近阈值时自动触发 compaction
2. **溢出防护**：多层防线防止上下文溢出导致会话崩溃
3. **透明恢复**：压缩后自动恢复，用户无感知

---

## 二、架构设计

### 2.1 三层防线

| 层级 | 机制 | 触发条件 |
|---|---|---|
| **第 1 层** | Auto-compaction | 上下文达到 WARN 阈值 |
| **第 2 层** | Mid-turn precheck | 中途检查，中止并交给 recovery |
| **第 3 层** | keepRecentTokens | 压缩不丢关键上下文 |

### 2.2 溢出防护状态机

```
NORMAL → WARN → DIVERT → HARD_LIMIT → RECOVERED
```

| 状态 | 说明 |
|---|---|
| NORMAL | 正常运行 |
| WARN | 上下文达到警告阈值，准备压缩 |
| DIVERT | 触发压缩，分流到新会话 |
| HARD_LIMIT | 达到硬限制，强制压缩 |
| RECOVERED | 压缩完成，恢复正常 |

### 2.3 各模型水位阈值

| 模型 | contextWindow | WARN | DIVERT | HARD_LIMIT |
|---|---|---|---|---|
| ark-code-latest | 224k | 134k | 179k | 201k |
| deepseek-v4-flash | 1024k | 614k | 819k | 921k |
| longcat/LongCat-2.0 | 1049k | 629k | 839k | 944k |

### 2.4 关键配置

```json
{
  "compaction": {
    "mode": "safeguard",
    "keepRecentTokens": 30000,
    "maxActiveTranscriptBytes": "20mb",
    "midTurnPrecheck": { "enabled": true }
  }
}
```

---

## 三、compaction 模型委托

- **原则**：compaction 模型应始终指向全局最大 ctx 模型
- **当前配置**：`agents.defaults.compaction.model = longcat/LongCat-2.0`
- **备选**：`coding-plan/deepseek-v4-flash`（1049k）

---

## 四、验证方式

- 长会话（>100 轮）自动触发压缩
- 压缩后关键上下文不丢失
- 用户无感知恢复

---

## 五、变更历史

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-08-21 | v0.1 | 初始化：两层防线 + 溢出防护状态机 |
| 2026-08-24 | v0.2 | 升级：mid-turn precheck + 模型水位校准 |
| 2026-09-01 | v1.0 | 正式发布：补充 DESIGN.md |
