# L2 运营本体（Operational Ontology）整体架构设计大纲 v1.0

> L2 Infrastructure Component · ai-knowledge-base · 阶段 4（Gen3）
> 组件编码：INFRA-KB-002
> 版本：v1.0 · 状态：**待 Rex 评审**
> 日期：2026-10-31 · 作者：Jerry 🦞
> 依据：ADR-007/008/009（`docs/architecture/00-system-architecture.md`）
> 方法论：`docs/research/ANALYSIS-ontology-methodology-v1.0.md`；写治理：`docs/research/ANALYSIS-agent-write-governance-v1.0.md`
> 前置文档：本组件 `DESIGN-OUTLINE-v1.0.md`（Gen1/Gen2，只读知识库）

---

## 1. 背景与目标

### 1.1 背景

现有 ai-knowledge-base 完成 Gen1（RAG 事实接地）与 Gen2（GraphRAG 关系接地），本质是**开放世界气质的只读模型**：能回答"是什么"，不能在受规则约束下"决策并写回"。

阶段 4 将其升级为 **Gen3 运营本体（神经符号运营层）**：给概率 LLM 配确定性符号骨架，使 Agent 能安全地对真实业务系统做写操作。

### 1.2 目标（本期范围）

在不破坏既有只读能力的前提下，新增四类通用原语：
1. **权威身份层（Identity）**：稳定主键 + 跨源身份解析 + system-of-record + 封闭世界边界（ADR-008）。
2. **动力学层（Kinetic）**：`action` / `function` 原语，与现有 object/link 对称（ADR-007）。
3. **决策对象（Decision Record）**：每次动作沉淀结构化决策记录（谁/何时/为何/变更集/依据）。
4. **Proposal Gate（写治理）**：两阶段提交，LLM 仅提议、确定性层校验、review/commit 写回（ADR-009）。

### 1.3 非目标（本期不做）

- 不做 Palantir 式 300+ 微服务、不做持久沙箱/仿真（流程场景价值低）。
- 不做跨库分布式 ACID；多源写回先用 Saga 补偿（详设阶段定）。
- 不绑定任何 Agent 框架；不实现具体业务规则（业务规则属 L3，本期只定调用契约）。

---

## 2. 设计原则

1. **语义配动力学**：object/link（读懂世界）必须配 action/function（改变世界），二者同一本体、同一权限模型。
2. **封闭世界（CWA，运营域）**：边界内"无权威记录=不存在"，支撑确定性事务与状态迁移；文档/切片等**语料域仍保持开放世界**，两域分离。
3. **规则即模型，不进 prompt**：业务规则封装为 function，LLM 调用而非推理；人与 Agent 走同一 commit 路径。
4. **LLM 只提议、永不直接写**：所有写经 Proposal Gate；不存在任何 Agent 直达源系统的通道。
5. **增量向后兼容**：新表/新字段走 migration；现有只读 API 与数据不受影响。
6. **L2 无业务**：L2 只提供原语与契约；具体对象类型、动作、规则由 L3/L4 注入。

---

## 3. 整体架构

### 3.1 在现有分层中的位置

```
接入层  REST │ MCP Server（query_*/compute_*/propose_* 三分类）│ CLI │ SDK
服务层  知识库管理 │ 检索(Gen1/2) │ ★本体运营服务 OntologyService(Gen3)
                              ├─ IdentityService（权威身份/解析）
                              ├─ ActionRegistry（动作/函数注册与发现）
                              ├─ ProposalService（提议→校验→提交）
                              └─ DecisionService（决策记录/回放）
知识组织层（现有）实体/文档/图谱/版本/权限  ＋  ★运营对象/关系/动作（同一本体）
风险防护层（现有）输入/检索/输出/审计       ＋  ★输出侧符号校验（Output Guard）
存储层  SQLite/PG │ 向量 │ FTS  ＋  ★identity / action_type / function_def / proposal / decision_record 表
```

### 3.2 核心写流程（Proposal Gate 时序）

```
Agent / 人
   │ ① propose_action(action_type, object_refs, params, rationale)
   ▼
ProposalService：生成 proposal(status=pending)，对目标对象打快照(snapshot)
   │ ② 调用绑定的 Function（规则在 L3，纯确定性；不经过 LLM）
   ▼
Output Guard：前置条件/权限(ABAC)/状态机/参数约束 校验
   ├─ 不通过 → proposal=rejected(+reason)，记 decision_record，结束
   └─ 通过   → proposal=validated（仍未写）
   │ ③ review（自动策略 或 人工 HITL）
   ▼
commit：在单事务内 应用变更集 → 写回源系统(Connector) → 生成 decision_record
   │      任一步失败 → Saga 补偿回滚 + 告警，proposal=failed
   ▼
proposal=committed（不可变，可回放）
```

关键不变量：**validated ≠ committed**；未经 commit，本体与源系统零变更。

---

## 4. 模块划分

| 模块 | 代码路径（计划） | 职责 | 状态 |
|---|---|---|---|
| 身份层 | `ai_kb/ontology/identity.py` | 主键策略、身份解析、SoR 声明、别名归并仲裁 | 🆕 |
| 运营对象 | `ai_kb/ontology/objects.py` | 在 entity 之上区分"运营对象"与语料实体，封闭世界边界 | 🆕 |
| 动作注册 | `ai_kb/ontology/actions.py` | action_type/function_def 注册、参数 schema、前置条件、变更集定义 | 🆕 |
| 提议闸门 | `ai_kb/ontology/proposal.py` | 两阶段提交、快照、commit/拒绝/补偿、幂等 | 🆕 |
| 决策记录 | `ai_kb/ontology/decision.py` | 结构化决策对象、回放、依据留痕 | 🆕 |
| 输出侧校验 | `ai_kb/guardrails/output_guard.py` | 调用 Function 做符号校验，与现有输出防护衔接 | 🆕 |
| 连接器抽象 | `ai_kb/ontology/connectors/base.py` | 写回源系统的统一接口 + Saga 补偿钩子（L4 提供实现） | 🆕（仅抽象） |
| MCP 暴露 | `mcp/server.py` 扩展 | 仅注册 query_/compute_/propose_ 工具，按身份授权 | 扩展 |
| 数据模型 | `ai_kb/db.py` | 新增 5 表 + migration | 扩展 |

依赖方向：接入层 → OntologyService →（actions/functions）→ db；Function 的**实现**由上层（L3）注入，L2 只持有注册表与调用契约，禁止反向依赖。

---

## 5. 数据模型契约（新增表，概要）

> 均 `CREATE TABLE IF NOT EXISTS` + migration 版本号；SQLite 先行，方言沿用 `dialects/`。

**5.1 权威身份 `ont_identity`**
- `id, domain_id, object_type, canonical_key(稳定主键,UNIQUE), system_of_record, display_name, status, merged_into(可空,归并指针), created_at, updated_at`
- 关联多源标识 `ont_identity_alias(id, identity_id, source_system, source_key, confidence, created_at)`。
- 约束：canonical_key 一经 commit 不可变；同一 (source_system, source_key) 唯一；归并走 `merged_into`，不物理删除。

**5.2 动作类型 `ont_action_type`**
- `id, domain_id, name(如 submit_contract), object_type, params_schema(JSON), precondition(JSON, 引用 function), required_approval(none|auto|human), writeback_target, version, status`。

**5.3 函数定义 `ont_function_def`**
- `id, domain_id, name, kind(rule|state_machine|risk|compute), handler_ref(上层注入的可调用标识), io_schema(JSON), deterministic(bool=1), version`。
- 约定：可被写流程调用的校验 function 必须 `deterministic=1`、无外部副作用。

**5.4 提议 `ont_proposal`**
- `id, domain_id, action_type_id, caller_id, caller_kind(human|agent), params(JSON), target_snapshot(JSON), status(pending|validated|rejected|committed|failed), validation_result(JSON), review_by, review_at, idempotency_key(UNIQUE), created_at, committed_at`。

**5.5 决策记录 `ont_decision_record`**
- `id, proposal_id(可空), domain_id, action_type, object_refs(JSON), actor_id, actor_kind, rationale, change_set(JSON), evidence(JSON,依据/命中规则), result(allowed|rejected|compensated), ts`。
- 与现有 `kb_audit_log` 关系：audit_log 记"发生了操作"（运维视角）；decision_record 记"做了什么决策及依据"（业务/学习视角），一一关联。

与现有表衔接：运营对象复用 `entity.id`，通过 `ont_identity.canonical_key` 建立权威身份；关系复用 `kb_relation`；语料（doc_asset/doc_chunk）保持开放世界，不进封闭世界约束。

---

## 6. 接口契约（概要，详设细化）

- `propose_action(domain, action_name, object_refs, params, *, caller, rationale, idempotency_key) -> proposal_id`
  - 只创建 pending proposal + 快照，**不产生任何写**。
- `validate(proposal_id) -> {ok, violations[]}`：调用绑定 deterministic function。
- `review(proposal_id, decision, reviewer) / commit(proposal_id) -> decision_record`：commit 单事务 + 写回 + 补偿。
- `register_action_type / register_function`：上层装配期调用；Agent 运行期不可注册（结构变更与数据变更通道分离）。
- MCP 工具三分类（强制）：`query_*`（读，ABAC 读时过滤）、`compute_*`（调用 deterministic function，只产出建议）、`propose_*`（只生成 proposal）。**禁止暴露 execute_*/write_*。**

---

## 7. 关键设计取舍

| 议题 | 决策 | 理由 |
|---|---|---|
| CWA 范围 | 仅运营对象封闭；语料域开放 | 合同/产品需确定性，文档问答需容忍不完整 |
| 事务 | 单库本地事务；跨源 Saga 补偿 | 单机起步，不引入分布式事务复杂度 |
| 身份归并 | 软归并(merged_into)+审计，不删数据 | 可回溯、可纠错，符合 append-only |
| 规则位置 | L3 实现、L2 注册调用 | 保 L2 无业务、可复用 |
| Agent 权限 | 结构与数据两通道分离；运行期只读+提议 | 对标 Palantir MCP/OMCP 硬约束 |
| 人审粒度 | action_type 上声明 none/auto/human | 风险分级，避免一刀切卡流程 |

---

## 8. Phase 拆分（建设计划，详 IMPLEMENTATION-PLAN）

- **P1 身份层**：ont_identity(+alias)、SoR 声明、归并；在 product-kb 做只读联调（不写业务）。
- **P2 Kinetic + 注册**：action_type/function_def 表与注册中心、参数/前置条件校验框架。
- **P3 Proposal Gate**：proposal/decision_record、快照、commit/拒绝、幂等、output_guard；MCP 三分类。
- **P4 连接器与补偿**：connector 抽象 + Saga 钩子（实现留给 L4 首个实例）。
- 每阶段独立可测、向后兼容；黄金基准与 E2E 在 VERIFICATION 文档定。

> 落地顺序遵循架构总纲：本 L2 原语完成并评审后，才进入 L3 规则 Function 化与 L4 bangcle-contract 实例验证。

---

## 9. 风险与开放问题（评审重点）

1. 运营对象与现有 `entity` 的边界判定规则（哪些 type 进封闭世界）需在详设给可操作判据。
2. canonical_key 生成策略（自然键 vs 代理键）直接决定是否重蹈"本体重建"，需结合 product-kb 193 产品/385 SKU 实测。
3. Function handler 的注入与安全沙箱（上层代码如何被 L2 安全调用）需详设定边界。
4. Saga 补偿在 OA 不支持反向操作时的降级策略（人工对账工单）。
