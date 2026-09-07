# L2 上下文管理 — 设计文档

> 版本：v2.0
> 创建日期：2026-09-01
> 最近修订：2026-09-07
> 状态：✅ 已上线
> 层级：L2 基础设施层

---

## 一、概述

### 1.1 定位

自动管理 AI Agent 的上下文溢出问题，确保长会话的稳定性。覆盖主会话、subagent、过期会话全场景。

### 1.2 核心目标

1. **自动压缩**：上下文接近阈值时自动触发 compaction
2. **溢出防护**：多层防线防止上下文溢出导致会话崩溃
3. **透明恢复**：压缩后自动恢复，用户无感知
4. **全场景覆盖**：主会话 + subagent + 过期会话生命周期治理

---

## 二、架构设计

### 2.1 防护体系（两层压缩 + 生命周期治理）

> **注意**：原设计为"三层防线"，第 3 层 session pruning 因运行时 provider 白名单限制不生效，已由「会话生命周期管理」cron 替代。

| 层级 | 机制 | 作用域 | 触发条件 |
|---|---|---|---|
| **第 1 层** | Auto-compaction（safeguard 模式） | 主会话内 | 上下文达到 WARN 阈值 |
| **第 2 层** | Mid-turn precheck | 主会话内 | 中途检查，中止并交给 recovery |
| **治理层** | 会话生命周期管理 cron | 跨会话 | 每日 02:00 清理过期会话 + deleteAfterRun |
| **保护规范** | Subagent 上下文保护 | subagent | 分段执行 + runTimeoutSeconds + 输出精简 |

#### keepRecentTokens 说明
`keepRecentTokens: 30000` 是 compaction 的内置参数（压缩时保留最近 N token），不是独立防线，而是 safeguard 模式的一部分。

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
    "maxActiveTranscriptBytes": "400kb",
    "midTurnPrecheck": { "enabled": true },
    "model": "coding-plan/deepseek-v4-flash",
    "memoryFlush": {
      "model": "coding-plan/doubao-seed-2-1-turbo"
    }
  }
}
```

---

## 三、compaction 模型委托

### 3.1 原则
- compaction 模型应与主模型**同一 provider**（网络命运共同体，主模型能连上压缩模型也能连上）
- memoryFlush 模型使用主模型（doubao-seed），与 compaction 模型形成交叉兜底

### 3.2 当前配置
| 用途 | 模型 | Provider | 说明 |
|---|---|---|---|
| Compaction 主模型 | `coding-plan/deepseek-v4-flash` | coding-plan | 大 ctx，适合摘要任务 |
| Memory Flush 模型 | `coding-plan/doubao-seed-2-1-turbo` | coding-plan | 同 provider，稳定可靠 |

### 3.3 Fallback 降级方案
OpenClaw 原生不支持 compaction fallbacks（schema 中 `compaction.model` 为单值字符串）。降级方案：

1. **同 provider 保障**：compaction 模型与主模型同属 `coding-plan` provider，网络/鉴权命运一致
2. **memoryFlush 交叉兜底**：memoryFlush 使用不同模型（doubao-seed），即使 compaction 模型故障，memory flush 仍可执行
3. **手动降级**：监控到 compaction 失败时，通过 `openclaw config set` 切换到备用模型
4. **主模型兜底**：极端情况下 unset compaction.model，回退到使用主模型自身压缩

---

## 四、Subagent 上下文保护

### 4.1 规范（AGENTS.md 固化）
1. **长任务必须分段**：每段 < 50% ctx window
2. **`sessions_spawn` 必须加 `runTimeoutSeconds`**：防止子任务卡死累积
3. **子任务输出必须精简**：结果回传主会话不超过 2000 token

### 4.2 辅助脚本
- 路径：`L2-infra/components/context-management/subagent_ctx_guard.py`
- 功能：根据任务描述和预估步数，生成分段策略和 token 预算
- 用法：`python3 subagent_ctx_guard.py <task_desc> <estimated_steps>`

---

## 五、会话生命周期治理

### 5.1 替代 session pruning
原 `session.maintenance.pruneAfter` 因运行时 provider 白名单限制不生效，已由 cron 替代。

### 5.2 Cron 任务
- **名称**：会话生命周期管理
- **ID**：`2f7846b7-f4da-4d3e-b3bf-e7036bb80e4a`
- **调度**：`cron 0 2 * * * @ Asia/Shanghai`
- **状态**：运行中（2026-09-07 实查 status: ok）
- **策略**：分级清理 + deleteAfterRun + 过期会话回收

---

## 六、验证方式

- 主会话：长会话（>100 轮）自动触发压缩
- 压缩后：关键上下文不丢失
- 生命周期：过期会话 48h 内被清理
- Subagent：长任务分段执行，不出现上下文溢出
- Compaction：模型故障时能降级到同 provider 备用模型

---

## 七、变更历史

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-08-21 | v0.1 | 初始化：两层防线 + 溢出防护状态机 |
| 2026-08-24 | v0.2 | 升级：mid-turn precheck + 模型水位校准 |
| 2026-09-01 | v1.0 | 正式发布：补充 DESIGN.md |
| 2026-09-07 | v2.0 | 补齐覆盖缺口：生命周期治理替代 session pruning + subagent 保护 + compaction fallback 方案 |
