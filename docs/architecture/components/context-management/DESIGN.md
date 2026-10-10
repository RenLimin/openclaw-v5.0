# L2 上下文管理 — 设计文档

> 版本：v3.0
> 创建日期：2026-09-01
> 最近修订：2026-10-10
> 状态：✅ 已上线（四层防护体系）
> 层级：L2 基础设施层
> ADR：ADR-032 上下文溢出自动恢复四层防护

---

## 一、概述

### 1.1 定位

自动管理 AI Agent 的上下文溢出问题，确保长会话的稳定性。覆盖主会话、subagent、过期会话全场景。

### 1.2 核心目标

1. **自动压缩**：上下文接近阈值时自动触发 compaction
2. **溢出防护**：多层防线防止上下文溢出导致会话崩溃
3. **透明恢复**：压缩/恢复后自动继续，用户最小感知
4. **全场景覆盖**：主会话 + subagent + 过期会话生命周期治理
5. **死锁打破**：解决上下文已溢出时 `/compact` 自身也失败的死锁问题

---

## 二、架构设计

### 2.1 防护体系（四层防护 + 生命周期治理 + Subagent 保护）

> **演进历史**：
> - v1.x：两层防线（auto-compaction + mid-turn precheck）
> - v2.x：三层阶梯式自动恢复（/compact → /reset → /new）
> - v3.x：四层防护体系（配置优化 + 插件实时拦截 + cron 兜底 + 用户规范）

| 层级 | 机制 | 作用域 | 触发条件 | 响应速度 |
|---|---|---|---|---|
| **第 1 层：配置优化** | Auto-compaction safeguard + contextPruning cache-ttl + midTurnPrecheck + notifyUser | 运行时原生 | 上下文达到阈值 | 实时（运行时内置） |
| **第 2 层：实时拦截** | Context Guardian 插件 — 主动监控 + 大 tool result 裁剪 + 提前压缩 | 运行时插件 | token 压力 / 大输出 | 实时（插件 hook） |
| **第 3 层：cron 巡检兜底** | 三层自动恢复：`/compact` → `/reset soft` → `/new` + 任务持久化 | 外部巡检 | 每 2h 扫描检测 | 准实时（2h 周期） |
| **第 4 层：治理规范** | 长任务 subagent 化 + 大内容落盘 + MEMORY/AGENTS 瘦身 | 开发规范 | 人为遵守 | 预防型 |
| **治理层** | 会话生命周期管理 cron | 跨会话 | 每日 02:00 | 天级 |

#### 第 1 层关键配置项

```json5
{
  "compaction": {
    "mode": "safeguard",
    "notifyUser": true,           // 压缩时通知用户
    "keepRecentTokens": 30000,
    "maxActiveTranscriptBytes": "6mb",
    "midTurnPrecheck": { "enabled": true },
    "model": "longcat/LongCat-2.0",
    "qualityGuard": { "maxRetries": 3 },
    "memoryFlush": {
      "model": "longcat/LongCat-2.0",
      "softThresholdTokens": 8000,
      "forceFlushTranscriptBytes": "200kb"
    }
  },
  "contextPruning": {
    "mode": "cache-ttl",          // 从 off 改为 cache-ttl，裁剪过期 tool result
    "ttl": "15m"                   // 从 5m 延长到 15m
  },
  "bootstrapMaxChars": 15000      // 限制 bootstrap 注入字符数，防止小窗口模型溢出
}
```

> **说明**：社区方案中常见的 `maxHistoryShare` 和 `reserveTokensFloor` 在 OpenClaw 2026.9.8 原生 schema 中不支持。实际阈值控制由第 3 层（L2 巡检脚本）的 80%/95% 水位线承担。

#### 第 2 层：Context Guardian 插件

- 来源：ClawHub `openclaw-context-guardian`
- 能力：
  - 主动监控 context window 压力，提前触发压缩
  - 动态裁剪大 tool result，避免单次输入爆炸
  - 实时拦截（hook 到 tool output），比 cron 响应快
- 定位：第 1 层（运行时原生）和第 3 层（cron 兜底）之间的补充

#### 第 3 层：cron 三层自动恢复（解决死锁问题）

> **解决的核心问题**：上下文已溢出时，连 `/compact` 命令本身都跑不起来（死锁）。

```
检测到 context_overflow →
  Layer 1: /compact（预压缩）→ 成功则结束
  Layer 2: /reset soft（保留 transcript，清会话状态）→ 成功则结束
  Layer 3: 保存任务到 memory/current-task.md + /new（开全新会话）
```

- 实现位置：`L2-infra/scripts/error_handler/scan_errors.py` → `scan_context_overflow()` + `auto_fix()`
- 触发频率：每 2 小时（error-scan cron job）
- 任务恢复：`task_tracker.py` 读取 `memory/current-task.md` 断点续跑

#### 第 4 层：用户操作规范（预防型）

| 规范 | 说明 |
|---|---|
| 长任务丢 subagent | 主会话只做调度，不堆大段代码/文档 |
| 大内容落盘 | 代码/文档读到文件，不要全量贴对话 |
| MEMORY/AGENTS 定期归档 | 项目上下文膨胀是溢出主因，定期瘦身 |
| Flash 模型关闭 memory search | 小窗口模型减少额外注入 |

### 2.2 溢出防护状态机

```
NORMAL → WARN(80%) → ERROR(95%) → RECOVERED
   ↓        ↓            ↓
   正常   /compact   /reset → /new
```

| 状态 | 阈值 | 动作 |
|---|---|---|
| NORMAL | < 80% | 正常运行 |
| WARN | ≥ 80% | 自动 `/compact` 预压缩 |
| ERROR | ≥ 95% | `/reset soft`，失败则 `/new` + 任务持久化 |
| RECOVERED | 回到安全水位 | 恢复正常 |

### 2.3 各模型水位阈值

| 模型 | contextWindow | WARN (80%) | ERROR (95%) |
|---|---|---|---|
| ark-code-latest | 224k | 179k | 213k |
| deepseek-v4-flash | 1024k | 819k | 972k |
| longcat/LongCat-2.0 | 1049k | 839k | 996k |

---

## 三、compaction 模型委托

### 3.1 原则
- compaction 模型应与主模型**同一 provider**（网络命运共同体，主模型能连上压缩模型也能连上）
- memoryFlush 模型使用同 provider 不同模型，与 compaction 模型形成交叉兜底

### 3.2 当前配置
| 用途 | 模型 | Provider | 说明 |
|---|---|---|---|
| Compaction 主模型 | `longcat/LongCat-2.0` | longcat | 大 ctx（1049k），适合摘要任务 |
| Memory Flush 模型 | `longcat/LongCat-2.0` | longcat | 同 provider，稳定可靠 |

### 3.3 Fallback 降级方案
OpenClaw 原生不支持 compaction fallbacks（schema 中 `compaction.model` 为单值字符串）。降级方案：

1. **同 provider 保障**：compaction 模型与主模型同属一个 provider，网络/鉴权命运一致
2. **memoryFlush 交叉兜底**：memoryFlush 使用独立模型，即使 compaction 模型故障，memory flush 仍可执行
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
- 三层恢复：模拟 95%+ 水位，验证 /compact → /reset → /new 逐级触发
- Context Guardian 插件：验证大 tool result 被自动裁剪

---

## 七、变更历史

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-08-21 | v0.1 | 初始化：两层防线 + 溢出防护状态机 |
| 2026-08-24 | v0.2 | 升级：mid-turn precheck + 模型水位校准 |
| 2026-09-01 | v1.0 | 正式发布：补充 DESIGN.md |
| 2026-09-07 | v2.0 | 补齐覆盖缺口：生命周期治理替代 session pruning + subagent 保护 + compaction fallback 方案 |
| 2026-10-07 | v2.1 | 新增第三层阶梯式自动恢复：解决保留元数据过多导致的自动压缩失效问题，按 `/compact` → `/reset` → `/new` 顺序尝试恢复 |
| 2026-10-10 | v3.0 | **四层防护体系升级**：配置优化（contextPruning cache-ttl + notifyUser + bootstrapMaxChars）+ Context Guardian 插件 + cron 三层兜底 + 用户规范；状态机简化为 WARN/ERROR 两级；统一阈值为 80%/95% |
