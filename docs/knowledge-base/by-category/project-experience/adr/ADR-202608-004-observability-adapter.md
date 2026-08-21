---
type: adr
id: ADR-202608-004
date: 2026-08-21
title: L2 可观测性适配组件设计决策 — 本地结构化日志优先, 渐进式演进
status: accepted
deciders: [Rex, Jerry]
layers: [L1, L2]
tags: [observability, logging, tracing, monitoring, cross-cutting]
supersedes: null
superseded_by: null
---

# [ADR-202608-004] L2 可观测性适配组件设计决策

## 1. 状态
**accepted** — 2026-08-21 Rex 确认

## 2. 背景

综合开放平台进入 L2 最小可用建设阶段。第一个组件选型为**可观测性适配**（横切关注点），因为：
- AI agent 的失败模式与传统软件不同（"礼貌地失败"），传统监控对此失明
- 后续所有 L2/L3/L4 组件都需要观测能力
- 没有可观测性，系统建设中的问题无法被及时发现和回溯

**设计文档**: [components/observability/DESIGN.md](./components/observability/DESIGN.md)

## 3. 核心决策

### 决策 1: 观测模型采用 5 层递进

| 层 | 名称 | 当前范围 |
|---|---|---|
| 1 | Logging (结构化日志) | ✅ 实施 |
| 2 | Tracing (步骤级追踪) | ✅ 实施 |
| 3 | Monitoring (指标+告警) | ⏳ 预留 |
| 4 | Evaluation (质量评估) | ⏳ 预留 |
| 5 | Governance (治理审计) | ⏳ 预留 |

**理由**：
- 80% 的价值来自 Layer 1+2（能看 + 能追溯）
- Layer 3~5 需要 Layer 1+2 的数据基础
- 渐进式避免过度工程

### 决策 2: 当前技术选型 — 本地结构化日志 (JSONL)

| 候选 | 评估 | 原因 |
|---|---|---|
| 全托管 SaaS (LangSmith/Braintrust) | ❌ | 数据外泄、成本高、违反自建目标 |
| 开源自托管 (Langfuse/Phoenix) | ⏸️ 备选 | OTEL 友好但需 Docker/K8s |
| OTEL Collector + ClickHouse | ⏸️ 长期 | 最灵活但工作量大 |
| **本地 JSONL 日志** | ✅ **采用** | 零依赖、渐进式、隐私友好 |

**理由**：
- 零依赖，不增加运维负担
- 先建立 schema，未来可无缝对接 OTEL
- 数据不出本机（隐私优先）

### 决策 3: 日志 schema 遵循 OpenTelemetry GenAI conventions

使用 `gen_ai.*` 属性命名（如 `gen_ai.tool.name`, `gen_ai.model.id`）。

**理由**：
- 业界标准，工具链兼容性好
- 未来对接 OTEL 无需改 schema
- 避免厂商锁定

### 决策 4: 隐私过滤（强制）

日志中**绝不出现**：凭据/API key/token、用户消息完整内容、工具参数敏感字段。

**理由**：
- 日志文件可能被多人查看（或未来上送后端）
- 与 SOUL.md / USER.md 中的安全边界一致

## 4. 后果

### 4.1 正面
- **低投入高回报**：Layer 1+2 覆盖 80% 观测需求
- **横切能力**：所有后续组件自动获得观测能力
- **隐私安全**：数据不出本机
- **可演进**：schema 兼容 OTEL，未来平滑升级

### 4.2 负面
- **手动分析**：阶段一没有 dashboard，需要 `jq` / Python 手动分析
- **单机限制**：不支持多机器/多团队协作观测
- **无自动告警**：阶段一~二没有实时告警

### 4.3 风险
| 风险 | 缓解 |
|---|---|
| 日志量过大撑满磁盘 | 30 天轮转策略 |
| 隐私过滤遗漏 | 自动化测试 + 定期审计 |
| schema 设计不当 | 先 MVP 验证，迭代调整 |

## 5. 实现计划

- [x] ADR-004 accepted（本文件）
- [ ] 实现最小埋点（tool_call + agent_turn + error 三类事件）
- [ ] 实现隐私过滤（redact 敏感字段）
- [ ] 验证：手动触发 agent → 检查日志输出
- [ ] 沉淀经验卡片（EXP-20260821-003）

## 6. 验证标准

1. 每次 agent turn 后，`logs/observability/` 有对应日志文件
2. 日志包含完整 trace/span 结构
3. 日志中无凭据/敏感数据（自动检查通过）
4. 日志可用 `jq` 快速查询（如 `jq 'select(.event=="tool_call")'`）

## 7. 相关决策

- **supersedes**: null
- **superseded_by**: null
- **相关 ADR**:
  - ADR-202608-001: 4 层架构（可观测性是 L2 横切组件）
- **相关文档**:
  - `docs/architecture/components/observability/DESIGN.md`（完整设计）
  - `docs/architecture/00-system-architecture.md#4-横切关注点`（架构定位）

## 8. 引用

- **Expanso**: AI Agent Observability Best Practices 2026
- **Azure**: Top 5 Agent Observability Best Practices
- **Braintrust**: Best AI Agent Observability Tools 2026
- **MLflow**: What Is Agent Observability (2026 Developer Guide)
- **OpenTelemetry**: GenAI Semantic Conventions

## 9. 变更历史

- 2026-08-21: proposed
- 2026-08-21: accepted（Rex 确认）
