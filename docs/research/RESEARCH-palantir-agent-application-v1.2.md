# Palantir 范式如何实际应用于 AI Agent 建设（RESEARCH v1.2）

> 调研人：Jerry 🦞 · 日期：2026-11-06 · 版本 v1.2
> v1.2 定位：承接 v1.1（概念/架构拆解），**聚焦"如何实际用于 AI Agent 建设"**——官方机制、社区工程实践、开源可复用资产三路并行调研后的综合，并给出对我们 OpenClaw 四层架构的落地映射。
> 调研方法：三路 isolated 子代理并行（官方文档 / 社区实践 / GitHub+ClawHub 开源），每路产出独立报告（`/tmp/palantir-agent-lane{1,2,3}.md`），主助手交叉验证后综合。事实与观点区分标注。

---

## 0. TL;DR（一句话结论）

**Palantir 范式对 AI Agent 建设的核心贡献不是"本体建模"，而是一套可照抄的工程机制：把业务规则编译成 Agent 只能"触发、不能绕过"的受控动作（Action），动作经预检/权威分类/写回优先/全量审计后执行，Agent 永远不能直接碰库。** 这套机制在官方（AIP/Ontology MCP）、社区（LangGraph/Box/Neo4j）、开源（operational-ontology/Sixb）三路完全同构，且我们已在 P4.3 落地了它的最小雏形（proposal gate + dry-run + 补偿语义）。

---

## 1. 官方机制：Ontology 如何变成 Agent 的工具与世界模型

### 1.1 构建 Agent 的三个入口（Palantir 2026 现状）

| 入口 | 定位 | 关键点 |
|---|---|---|
| **AIP Logic** | no-code 编排 LLM-driven 函数 | 输入可以是 Ontology 对象/文本，输出可以是字符串/对象/**Ontology edits**；"**Don't let the LLM guess the rules**"——业务逻辑封装成可发布函数 |
| **AIP Chatbot Studio**（原 Agent Studio） | 构建可复用对话 Agent | 工具集：Action / Object Query / Function / Update Application Variable / Command / Request Clarification；**只读查询低风险，Action 改数据需确认步骤 + 紧作用域 + 最多测试** |
| **Pro-code Agents**（SDK 如 Claude Agent SDK / OSDK） | 代码内构建 | 类型化、可测试、完全可控；OSDK 适合"自己写代码维护"的工程团队 |

> 关键认知（官方文档 + 实施商一致）：Agent 绑定 Ontology 的方式 = **Ontology 对象/动作/函数被注册为 Agent 的工具**。Agent 的"世界模型"不是靠 prompt 描述，而是工具 schema 本身。

### 1.2 五层交互架构（官方 + 深度分析文，zerofuturetech 2026）

```
1. Ontology Schema Registry —— 对象/属性/链接/动作/函数的定义与版本
2. Tool Registry —— 暴露给 agent 的工具集 + 参数 schema + 调用方法
3. Context Builder —— 基于当前用户/页面/对象/查询确定性注入上下文（Layer 1）
4. Object Query + Function + Action —— 查询对象/封装业务逻辑/受控写入（Layer 2-4）
5. Governance —— OAuth 2.0 权限、应用限制、审计（Layer 5）
```

**Agent 能做什么/不能做什么（官方明示）：**
- ✅ 读对象、执行动作、查询数据、写 ontology 数据（经动作）
- ❌ **不能修改 Ontology 类型定义本身**
- 约束：应用限制 + OAuth 2.0 权限（Beta）

### 1.3 最小交互流（官方文档归纳）

```
User Message → Context Builder → LLM → Object Query → Function
→ LLM Response → User Confirmation → Action → Ontology Edit → Audit Log
```

一句话官方总结（YouTube 官方文档讲解, 2026-02）：**"AI reads via context. AI writes via governed actions."**（读走上下文，写走受治理的动作。）

### 1.4 Ontology MCP：把 Ontology 暴露给外部 Agent（关键机制）

- **Ontology MCP**（Developer Console 特性）：把应用的 object types / action types / query functions 自动暴露为 **MCP 工具**——外部 agent（Claude / Copilot Studio / Gemini Enterprise / 自建框架）可读对象、在 OAuth 权限下**调用已批准的 Action**，全程审计。
  - Object types → SQL 工具（只读查询）
  - **Action types → 每个动作一个 MCP 工具**（写入的唯一入口）
- **Palantir MCP**（另一套，给 builder 用）：让 Claude Code/Cursor 等编码 agent 设计/编辑 Foundry 资源。区分："**Pick by who the agent works for**"——业务 agent 用 Ontology MCP，工程 agent 用 Palantir MCP。
- **Agent 作为工具（组合）**：AIP Logic 函数/chatbot 可保存为 function 再经 MCP 暴露——**高层 agent 可以调用底层 agent**，即 agent 编排的官方机制。
- 对比 OSDK：MCP 免平台定制代码但数据离开 Foundry 交给 LLM 提供商；OSDK 代码内类型化、数据不离开。**对数据敏感企业，这是取舍点。**

### 1.5 治理与可观测（官方）

- AIP Evals：agent 发布前先建评测集（实施商惯例："**Start with one Action a person would approve, and build the eval set before the agent.**"）
- Workflow Lineage / Run History：每次 LLM 调用（请求/响应/延迟）、工具使用、所用模型、被编辑的 Ontology 对象全记录——**agent 动作审计 = 全链路可追溯**。
- AIP Evolve：多 agent 自动做候选变更并对比基线（官方示例：换模型 + 加护栏后成本降 65%）。
- 官方社区反馈也在暴露现实 bug（AIP Logic 引用已删字段等），说明**机制成熟但远非完美**。

---

## 2. 社区共识：可迁移的工程实践（跨阵营最强交集）

### 2.1 共识一："Action 网关 + 提案制"是唯一主流写路径

Palantir 派（Ken Huang 2026）与非 Palantir 派（Box+LangGraph 2025）殊途同归：

- **Agent 只产出意图与提案**（LLM extracts, the playbook decides——模型只做非结构化抽取，风险判定留在可审计的确定性代码）；
- 写操作必须经**带校验的 action/工具层**，状态变更前可插人工门（LangGraph `interrupt` + checkpointing）；
- 硬规则留在代码：`if amount > limit: block()`，不靠 prompt 约束。

### 2.2 共识二：规则即模型，而不是规则即提示词

- 社区强共识：**"LLM 必须永远无权决定自己的动作是否需要人工复核"**（Golabs 七层架构、Exemplary AI）；
- 系统提示里的"只改授权记录"**不构成访问控制边界**——必须身份层 + 确定性硬门禁；
- 主流实现：Neo4j 读/写工具物理分离（`cypher-read` 宽授权、`cypher-write` 窄权限+schema 检查+置信度阈值+人工批准）；ClickIT 四阶段（Shadow → Read-Only → Human-Gated → Scoped Autonomy）。

### 2.3 共识三：Ontology 编译成工具（不是 RAG 也不是直连库）

- TWA 项目（arXiv 2602.03439, 2026-02）：OWL T-Box **编译成带内建校验的函数 → 自动生成 MCP server**，agent **必须**经这些工具创建/修改 KG 实例，语义约束**在写入时执行**而非事后校验；
- Microsoft Fabric IQ Ontology：官方 ontology MCP server + **proposal-first** 变更模式（agent 提议、系统执行配置动作）；
- 反面：LLM 直连数据库 = prompt injection 变成 DROP TABLE（AI Data Gateway 论点），社区有真实噩梦案例。

### 2.4 最大踩坑：先建模后找用例

- 多位实践者一致（Ken Huang、Reddit 客户帖、Tellius）：**"最常见失败模式是在任何 agent 用例证明价值之前，试图把整个企业建模进 ontology"**；
- 推荐：**单一 commit surface**（如"分诊 AML 告警"）→ 最小对象图 → 1-2 个 Functions 编码逻辑 → 包成 Actions 管控写路径 → 暴露为 agent 工具 → 嵌入操作 UI；
- 6 个月后无人"拥有"的 ontology 必然烂尾（Datawalk）。

### 2.5 批评与反向观点（必须正视）

- **锁定**：Foundry ontology 无 RDF/OWL/JSON-LD 标准导出，业务逻辑/关系/安全策略/action 触发器无法干净导出，迁出估 3-6 个月；NHS £330M 合同因不拥有 IP 面临 2027 解约审查；
- **"Ontology 就是数据建模"**（VONNG 公开辩论，75% 听众支持）：Palantir 真壁垒是安全许可与国防背景而非概念；中国模仿者有 cargo cult 风险（复制烟而非引擎，重演"数据中台"周期）；
- **ROI 难证**：多数项目上线后没人持续测量（PAL4C 2026）；Microsoft 官方也主张"**start light, scale intentionally**"——不为不需要结构的负载加结构；
- **挺方平衡**（a16z "The Palantirization of Everything"）：小合同起步、价值证明后扩张、服务是采纳手段。

### 2.6 评测/可观测性现状

- 主流：LangSmith（LangChain 系）vs Langfuse（开源可自托管、框架无关）；
- agent 专属信号：Goal Completion Rate、Tool Success Rate（Sherlocks.ai 2026）；
- 经济账（Siemens 2026）：无 KG 的 agent 跨域推理多烧 10-20x tokens——**KG 不只是更聪明、更是更便宜**。

---

## 3. 开源可复用资产（含代码模式）

### 3.1 精读：gura105/operational-ontology（MIT，204★，最值得照抄）

核心仅 4 文件 1656 行（TS），objects/links/actions 全是 **plain data**（zod schema），`buildMcpServer` 枚举模型自动生成工具：

| 模型元素 | 生成的 MCP 工具 |
|---|---|
| ObjectType | `search_/get_/union/intersect/subtract/aggregate_<type>` |
| LinkType | `traverse_/pivot_<link>`（双向） |
| **Action** | **`<action>`（如 cancel_order），params 原样作 tool input schema** |
| Function | `<function>`（readingHint） |
| 固定 | `read_audit_log`（append-only 审计视图） |

**刻意缺席即设计**：无裸 SQL / 无通用 update 工具——agent 的操作空间 = 模型定义的操作空间。

**治理流水线（最值得照抄的模式）**：
```
validate params(zod) → 行级 visibility → 纯函数 preconditions（业务规则，可 reject）
→ effects 产出 Edit[] → #preflight（用提交同一份代码在回滚事务里 dry-run）
→ 权威分类（source/ontology；跨线 MIXED_AUTHORITY 拒绝）
→ writeback-first（外部系统先写成功，本地才提交；外部 guarded UPDATE 二次校验）
→ SQLite 原子提交 + append-only 审计（每次拒绝/崩溃都记录）
```
规则 ≠ 权限：precondition 决定"操作是否成立"（shipped 单不可取消 → `SHIPPED_ORDER_CANNOT_BE_CANCELLED`），权限决定"谁可以做"。
**生产判断**：未发 npm、无认证（actor 自报 fail-open）、单人——**作蓝图 ✅，直接生产 ❌**；MIT 可逐文件移植。

### 3.2 Sixb（MIT，134★，日更，已发 npm 0.2.1）——唯一产品级完整框架

connectors → ontology → actions → workflows → app 全链路；内置 agent **不经 MCP**，在沙箱内经 run-scoped domain SDK/CLI 请求动作——**权限来自 run 而非 agent 视图**（`AgentToolRuntimeFacade`）。判断：可小范围试点，0.x 有 breaking change。

### 3.3 组合式蓝图：smilebank7/OpenFoundry（Apache-2.0，代码薄但架构诚实）

唯一自研 Ontology Layer（Registry/Compiler/Query API/**Action Engine**），其余组合 Airbyte/dbt/Trino + **OPA**（策略外置，谁能调 action）+ Keycloak；Action Engine 规划 idempotency key + outbox + append-only audit + writeback adapter。**其架构图基本就是我们应该走的路。**

### 3.4 底座与组合件（生产可用级）

- **HelixDB**（6.2k★，Apache-2.0，YC 支持）：graph-vector 存储底座，自带 agent 图遍历 MCP；**无 action 门需自建**——正好用 §3.1/§3.3 的模式补上；
- **FastMCP**（py 28k★ / ts 3.3k★）：Pydantic → tool 的事实标准；
- **Cortex**（3.3k★）：OpenAPI → MCP 生成；
- **LinkML**（690★）：schema 单一来源、多格式导出（JSON-Schema/OWL/SHACL/SQL），但 MCP 集成不成熟；
- OWL/SHACL 路线（ontoloom 等）：知识表示方向，**非 operational**，我们要的是后者。

### 3.5 ClawHub 生态现状：空白 = 机会

- plugins：无 ontology/object-action 方案；
- skills "ontology" 一批（@oswalpalash/@thcjp/@onlyloveher 等）：都是**结构化记忆实体图**（Person/Project/Task...），**无 action 门/写回/权限**，不可当 Foundry 替代；
- **结论：我们自建的 action/ontology 组件在 ClawHub 生态是空白，具备沉淀回 ClawHub 的价值。**

### 3.6 License 合规速记

MIT/Apache-2.0/BSD-3 可商用闭源衍生（保留版权/NOTICE）；NOASSERTION（orionbelt、u485349、palantir-ontology-strategy 书）未获授权前不可用代码；AGPL-3.0（orodruin）有网络服务传染风险，不纳入核心依赖。

---

## 4. 对我们 OpenClaw 四层架构的映射（核心章节）

### 4.1 我们已有的（对应关系）

| 我们已有 | 对应 Palantir 概念 | 状态 |
|---|---|---|
| L2 `ai-knowledge-base` entity/relation | Objects + Links（读模型） | ✅ |
| L4 `contract_review/ontology_bridge/`（P4.3） | **Action 层雏形** | ✅ 最小可用 |
| Proposal Gate（提案 + 审批 + 决策记录） | Action 的 human-in-the-loop | ✅ 已落地 |
| Saga 写回 + 逆序补偿 + `compensated` 审计 | writeback + 补偿 | ✅ 已落地 |
| `dry_run` 预演模式（OaWritebackConnector 默认） | #preflight dry-run | ✅ 已落地 |
| MCP 工具描述符 + model-scheduling | Agent 接入 | ✅ |
| ABAC 文档级权限 + 检索过滤 | 安全策略（部分） | ⚠️ 对象级待补 |
| `reconcile.py` 四态对账 | 双写一致性检测（外部写不可补偿时的唯一守护） | ✅ 已落地 + cron |

> **关键事实：Palantir 范式的核心机制（Action 网关 + 提案 + 预检 + 写回优先 + 审计）我们已在 P4.3 用最小形态落地并验收。** 这不是"要不要建"的问题，是"如何扩展成通用 L2 抽象"的问题。

### 4.2 核心差距（按可落地性排序）

| 差距 | Palantir 做法 | 我们现状 | 复用来源 |
|---|---|---|---|
| **① Action 注册表 + 自动生成 MCP 工具** | Ontology Schema Registry → Tool Registry → 自动暴露 MCP | 手写每个 connector/CLI，工具不自动生成 | operational-ontology `buildMcpServer`（§3.1，MIT 照抄） |
| **② 规则外置（规则即模型）** | precondition 纯函数 + 权限分离（OPA） | 规则散落组件 if-else / prompt | operational-ontology preconditions + smilebank7 OPA 蓝图（§3.3） |
| **③ 身份层防越权** | OAuth 2.0 作用域、每 agent 服务主体、run-scoped 权限 | 调用者身份靠 actor 自报（P4.3 已标注 fail-open 风险） | Sixb run-scoped facade（§3.2） |
| **④ 统一 agent 动作审计** | 每次尝试（含拒绝/崩溃）append-only | `action_log` 已有雏形（L2 提案/决策记录），未覆盖所有组件动作 | operational-ontology `audit_log`（§3.1） |
| **⑤ 对象级权限** | Markings / 行级 visibility | ABAC 文档级 | operational-ontology visibility（§3.1） |
| **⑥ Agent 组合（agent-as-tool）** | AIP Logic 函数经 MCP 暴露，高层 agent 调用底层 | 无统一机制（subagent 已有雏形，未语义化） | Ontology MCP agent-as-tools（§1.4） |

### 4.3 落地建议：三条路径（对应 L2 Action 层设计）

**路径 A（推荐起点）——把 P4.3 雏形泛化为 L2 `action-registry`**
- 在 L2 `ai-knowledge-base` 增加 Action 层（`action(id, object_type, name, rule_spec, permission, writeback_target)` + `action_log` append-only），与 entity/relation 对称；
- 移植 operational-ontology 三件套（MIT）：模型驱动自动生成 MCP 工具 + preflight/权威分类/writeback-first/审计；
- 首个验证实例：`bangcle-contract` 现有 Proposal Gate + P4.3 连接器直接接入（闭环最短，风险可控）；
- 铁律不变：validated ≠ committed；外部写不可补偿；agent 永不直连业务库。

**路径 B（工程参照）——精读 Sixb 的 run-scoped 授权与沙箱**
- 引入"权限来自 run 而非 agent 视图"：每个 agent 运行实例独立身份/作用域；
- 评估是否试点 Sixb 小范围（MIT、已发 npm），或仅借鉴其 action phases/effects/writeback 分离。

**路径 C（底座选型）——HelixDB 评估**
- 若业务规模上量，评估 HelixDB（Apache-2.0）作为图+向量底座（agent 走图 MCP），action 门自建（§3.1/§3.3 模式补齐）；
- 现阶段不引入，仅保持观察。

### 4.4 明确不做的事（承接 v1.1 + 社区批评）

- ❌ 不采购/不上 Palantir（锁定、主权、成本）；
- ❌ 不做"全企业预建模"——**从单一 commit surface 起步**（社区最大踩坑的直接对冲）；
- ❌ 不照搬 300+ 微服务重架构；
- ❌ 不引入 OWL/SHACL 推理方向（我们要 operational，不要知识表示）；
- ❌ 不采用 NOASSERTION/AGPL 项目代码；
- ❌ 不把精力放复刻 UI/dashboard。

---

## 5. 建议的下一步（待 Rex 拍板）

1. 是否启动 **L2 `action-registry` 设计**（路径 A）？按铁律：`DESIGN-OUTLINE-action-layer-v1.0` → 评审 → 详设。设计输入：本报告 §3.1 代码模式 + 现有 P4.3 连接器 + OPERATIONS §4b 对账链路。
2. 首个验证实例确认：`bangcle-contract`（推荐，闭环最短）还是 `product-kb`？
3. 是否需要我把 operational-ontology 核心三件套（`core.ts`/`mcp.ts` 模式）移植成 **Python + Pydantic 概念验证**（约 300-500 行，L2 沙箱内演示，不接真实系统）作为详设的黄金基准？
4. ClawHub 沉淀：验证通过后，是否将 action-registry 组件沉淀为 ClawHub skill/plugin（当前生态空白，具备先发价值）？

---

## 6. 主要来源（三路汇总，完整清单见 lane 报告）

**官方**：palantir.com/docs/foundry/ontology-mcp/sample-architecture；pal4c.com/palantir-aip-agents；pal4c.com/palantir-ontology-mcp；zerofuturetech.substack.com/p/palantir-aip-agent-ontology-interaction；YouTube "Palantir AIP Explained"（2026-02）；community.palantir.com（AIP Logic bug / 反向追踪讨论）
**社区**：kenhuangus.substack.com（2026）；blog.box.com（contract review agent + LangGraph）；arxiv.org 2602.03439（TWA, 2026-02）；neo4j.com（GraphRAG / agent tools / MCP 四原语）；learn.microsoft.com（Fabric IQ Ontology）；spinnable.ai（12 controls, 2026）；vonng.com/en/db/ontology-again（VONNG 反方）；fgarofalo56.github.io/csa-inabox（锁定分析）；a16z.com/the-palantirization-of-everything
**开源**：github.com/gura105/operational-ontology（MIT）；github.com/sixb-ai/sixb（MIT）；github.com/objectstack-ai/objectstack（Apache-2.0）；github.com/HelixDB/helix-db（Apache-2.0）；github.com/PrefectHQ/fastmcp；smilebank7/OpenFoundry（蓝图）；Marsovius/u485349/Przyval（不可用判断）
**内部**：RESEARCH-palantir-oncology-v1.1.md；DESIGN-DETAIL-palantir-p4-reader-v1.0.md（P4.3 连接器契约）；VERIFICATION-palantir-p4-reader-v1.0.md

---

## 变更历史

- v1.2（2026-11-06）：新文档。三路并行调研综合，聚焦"如何实际应用于 AI Agent 建设"；新增 §4 对 OpenClaw 的映射（已有/差距/路径 A/B/C）与 §5 待拍板项。
- （v1.0/v1.1 为 Palantir Oncology 概念调研，见 RESEARCH-palantir-oncology-v1.1.md）
