# 可观测性适配 (L2 基础设施组件)

> 本文档是 [系统架构](../00-system-architecture.md) 的 L2 组件设计文档。
> 决策记录: [ADR-202608-004](./ADR-202608-004-observability-adapter.md)

## 1. 定位

**层级**: L2 基础设施层
**类型**: 横切关注点 (Cross-Cutting Concern)
**状态**: 设计阶段 (待 ADR-004 锁定)

可观测性适配是 L2 的**横切组件**——不构成独立层，但为 L1~L4 所有层提供观测能力。

## 2. 问题定义

### 2.1 AI agent 可观测性 ≠ 传统监控

传统 APM（Application Performance Monitoring）假设**确定性系统**：同样的输入给出同样的输出，故障表现为错误、延迟、宕机。

AI agent 不同——它**"礼貌地失败"（fail politely）**：
- 输出格式正确、运行完成、dashboard 全绿
- 但 agent 调错了工具、检索了错误的文档、推理出自信的错误答案

传统监控对此**完全失明**。

### 2.2 核心矛盾

| 维度 | 传统软件 | AI agent |
|---|---|---|
| 失败模式 | 崩溃、超时、5xx | 语义错误、工具误调、推理偏差 |
| 最小可观测单位 | 请求/响应 | **步骤 (step)** |
| 因果链 | 线性调用栈 | 多步推理、工具调用、检索、循环 |
| 健康检查 | up/down 二值 | "运行完美但做了错事" |

**结论**：AI agent 的最小可观测单位是**步骤**（model call / tool invocation / retrieval / reasoning hop），不是最终响应。

### 2.3 我们的具体需求

基于 OpenClaw + Rex 的工作模式：

1. **步骤级追踪**：每次 agent turn、tool call、model inference 都可追溯
2. **结构化日志**：agent 做了什么决策、为什么选这个工具、耗时多少
3. **成本可见**：token 用量、API 调用、外部服务计费（Tavily 搜索次数等）
4. **质量评估**：agent 输出是否正确（至少可追溯，不一定自动评估）
5. **漂移检测**：agent 行为模式是否随时间变化

## 3. 设计原则

| 原则 | 说明 |
|---|---|
| **步骤级** | 最小可观测单位是步骤，不是会话 |
| **结构化** | 日志有统一 schema，不是自由文本 |
| **异步非阻塞** | 观测不能阻塞 agent 核心功能 |
| **隐私优先** | 不记录敏感数据（凭据、PII），只记录元信息 |
| **渐进式** | 先做"能看"，再做"能评"，最后做"能警" |
| **OpenTelemetry 优先** | 遵循 GenAI semantic conventions，避免厂商锁定 |

## 4. 架构设计

### 4.1 五层观测模型

```
┌─────────────────────────────────────────────────────────────┐
│  5. Governance (治理)                                       │
│     审计日志 / 合规检查 / 数据驻留                           │
├─────────────────────────────────────────────────────────────┤
│  4. Evaluation (评估)                                       │
│     输出质量评分 / 回归检测 / A/B 对比                       │
├─────────────────────────────────────────────────────────────┤
│  3. Monitoring (监控)                                       │
│     指标聚合 / 异常检测 / 告警规则                           │
├─────────────────────────────────────────────────────────────┤
│  2. Tracing (追踪)                                          │
│     步骤级 span / 因果链 / trace replay                      │
├─────────────────────────────────────────────────────────────┤
│  1. Logging (日志)                                          │
│     结构化事件流 / 决策记录 / 工具调用记录                   │
└─────────────────────────────────────────────────────────────┘
```

**当前范围**（阶段一）：**Layer 1 (Logging) + Layer 2 (Tracing)**
**未来扩展**（阶段二~三）：Layer 3 (Monitoring) → Layer 4 (Evaluation) → Layer 5 (Governance)

### 4.2 日志设计 (Layer 1)

#### 4.2.1 日志格式

遵循 OpenTelemetry GenAI semantic conventions (`gen_ai.*`)：

```json
{
  "timestamp": "2026-08-21T14:30:00+08:00",
  "level": "info",
  "component": "agent",
  "event": "tool_call",
  "trace_id": "abc123",
  "span_id": "def456",
  "session_id": "e28ede2e-...",
  "attributes": {
    "gen_ai.tool.name": "tavily_search",
    "gen_ai.tool.args": {"query": "...", "search_depth": "advanced"},
    "gen_ai.tool.result_count": 3,
    "gen_ai.tool.duration_ms": 1813,
    "gen_ai.model.id": "coding-plan/ark-code-latest"
  }
}
```

#### 4.2.2 日志事件类型

| 事件 | 级别 | 内容 |
|---|---|---|
| `session_start` | INFO | 会话开始、模型、工具配置 |
| `agent_turn` | INFO | 每次 agent turn 的输入/输出摘要 |
| `tool_call` | INFO | 工具名、参数摘要、耗时、结果摘要 |
| `tool_error` | ERROR | 工具名、错误类型、重试次数 |
| `model_call` | DEBUG | 模型名、token 用量、延迟 |
| `memory_op` | DEBUG | memory read/write/search 操作 |
| `session_end` | INFO | 会话统计（总 turn 数、总工具调用、总耗时）|

#### 4.2.3 日志存储

| 存储位置 | 用途 | 保留 |
|---|---|---|
| `memory/YYYY-MM-DD.md` | 人类可读的每日摘要 | 永久 |
| `logs/observability/` | 结构化 JSONL 日志 | 30 天轮转 |
| `logs/observability/errors/` | 错误级别日志 | 90 天 |

**隐私过滤**：日志中**绝不出现**——
- 凭据 / API key / token
- 用户消息的完整内容（只记录长度 + hash）
- 工具参数中的敏感字段（自动 redact）

### 4.3 追踪设计 (Layer 2)

#### 4.3.1 Trace 结构

```
Trace (一次会话)
  ├── Span: session_start
  ├── Span: agent_turn_1
  │   ├── Span: model_call (prompt → reasoning)
  │   ├── Span: tool_call (tavily_search)
  │   ├── Span: tool_call (exec)
  │   └── Span: model_call (synthesize)
  ├── Span: agent_turn_2
  │   └── ...
  └── Span: session_end (statistics)
```

#### 4.3.2 与 OpenClaw 的集成点

| OpenClaw 钩子 | 用途 |
|---|---|
| `before_agent_turn` | 记录 turn 开始、提取上下文摘要 |
| `agent_end` | 记录 turn 结束、统计工具调用 |
| `before_tool_call` | 记录工具调用开始 |
| `after_tool_call` | 记录工具调用结果、耗时 |
| `session_start` | 创建 trace 根 span |
| `session_end` | 关闭 trace、输出统计 |

### 4.4 指标设计 (Layer 3 — 预留)

| 指标 | 类型 | 来源 |
|---|---|---|
| `agent.turns_total` | counter | agent turn 计数 |
| `agent.tool_calls_total` | counter | 工具调用计数（按工具名标签）|
| `agent.tool_duration_ms` | histogram | 工具调用耗时 |
| `agent.model_tokens_total` | counter | token 用量（按模型标签）|
| `agent.session_duration_ms` | histogram | 会话总耗时 |
| `agent.error_rate` | gauge | 错误率（滑动窗口）|
| `agent.cost_per_session` | gauge | 每次会话成本（估算）|

## 5. 技术选型

### 5.1 业界工具对比

| 类型 | 代表 | 适合我们? | 原因 |
|---|---|---|---|
| 全托管 SaaS | LangSmith / Braintrust / Datadog | ❌ | 数据外泄、成本高、违反"自建"目标 |
| 开源自托管 | Langfuse / Arize Phoenix | ⏸️ 备选 | OTEL 友好，但需要 Docker/K8s |
| OTEL Collector + 自建后端 | OpenTelemetry + ClickHouse | ⏸️ 长期 | 最灵活，但工作量大 |
| **本地结构化日志** | Python logging + JSONL | ✅ **当前** | 简单、零依赖、渐进式 |

### 5.2 当前决策：本地结构化日志

**理由**：
1. **零依赖**：不引入外部服务，不增加运维负担
2. **渐进式**：先建立日志 schema，未来可无缝对接 OTEL
3. **可读**：JSONL 可用 `jq` / Python 快速分析
4. **隐私**：数据不出本机

### 5.3 未来演进路径

```
阶段 1 (当前): 本地 JSONL 日志 + 手动分析
  ↓ 当日志量 > 1000 条/天
阶段 2: 本地聚合脚本 (Python) + 简单 dashboard
  ↓ 当需要跨机器/团队协作
阶段 3: OTEL Collector + 开源自托管后端 (Langfuse/Phoenix)
  ↓ 当需要企业级 SLA
阶段 4: 全托管 SaaS 或自建 OTEL + ClickHouse
```

## 6. 与其他组件的关系

```
可观测性适配 (本组件)
  ↑ 被依赖
  ├── L1 OpenClaw hooks (before_tool_call, agent_end, ...)
  ├── L2 其他组件 (每个组件都产生日志)
  ├── L3 通用业务 (业务指标)
  └── L4 专有业务 (专有指标)
  
  ↓ 依赖
  ├── L1 OpenClaw (hooks, sessions, tools)
  └── L2 持久化适配 (日志存储，如果未来需要)
```

## 7. 实施计划

### 阶段 1: 日志 schema + 最小埋点 (当前)
- [ ] ADR-004 锁定设计决策
- [ ] 定义 JSON schema (本文件 §4.2.1)
- [ ] 实现最小埋点 (tool_call + agent_turn + error)
- [ ] 实现隐私过滤 (redact 敏感字段)
- [ ] 验证：手动触发 agent → 检查日志输出

### 阶段 2: 追踪 + 统计
- [ ] 实现 trace/span 结构
- [ ] 实现 session_end 统计输出
- [ ] 实现每日摘要自动生成 (更新 memory/YYYY-MM-DD.md)

### 阶段 3: 监控 + 告警
- [ ] 实现关键指标聚合
- [ ] 实现异常检测（错误率突增、成本突增）
- [ ] 实现告警规则（如：连续 3 次 tool_error → 通知）

### 阶段 4: 评估 + 治理
- [ ] 实现输出质量评估（至少可追溯）
- [ ] 实现审计日志
- [ ] 对接 OTEL（如需）

## 8. 参考

- **Expanso**: AI Agent Observability Best Practices 2026
- **Azure AI Foundry**: Top 5 Agent Observability Best Practices
- **Braintrust**: Best AI Agent Observability Tools 2026
- **MLflow**: What Is Agent Observability (2026 Developer Guide)
- **OpenTelemetry**: GenAI Semantic Conventions (gen_ai.*)
- **Monte Carlo**: The 2026 Guide To Agent Observability Tools
