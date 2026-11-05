# Palantir Oncology 调研与系统优化评估（v1.1）

> 调研人：Jerry 🦞 · 日期：2026-10-31 · 版本 v1.1
> v1.1 变更：应 Rex 反馈，新增第 0 章「作为 AI 概念的 Palantir Oncology」——按业界/媒体（含豆包归纳）的概念框架组织，与"官方产品考证"并列。
> 范围：Palantir 在肿瘤/医疗领域的能力（Foundry / AIP / Ontology），评估对当前四层系统尤其 L3/L4 业务资产建设的优化空间。
> 调研覆盖：官方文档、AI 学术界（Nature 系综述）、社区评价、开源替代——四路齐备。

---

## 0. 作为 AI 概念的「Palantir Oncology」

> 术语定位：**Palantir 官方并无名为「Oncology」的独立产品页**；它是业界/媒体对 **Palantir Foundry + AIP 平台能力落地于肿瘤诊疗与科研**的概括性叫法。下文按这一概念的通行框架组织，并标注事实来源。

### 0.1 是什么（一句话定义）

以 **Ontology（本体/语义层）为核心**，把肿瘤诊疗与科研中分散的多模态数据——电子病历、影像、病理切片、基因组学、临床试验、用药与随访——统一成**可被人和 AI Agent 直接调用的"业务对象 + 动作"**，从而支撑从数据整合、队列/试验匹配到辅助决策的端到端运营。

> 与"传统肿瘤 AI"的本质区别：传统模式多为**单点模型**（一个模型做影像判读或预后预测，输出一个分数）；Palantir 范式是**运营层**——模型只是其中一个"动词"，平台负责把数据、规则、多个模型/Agent、写回动作和审计串成闭环。

### 0.2 概念分层（通行的四层结构）

| 层 | 内容 | 对应 Palantir 组件 |
|---|---|---|
| **① 数据层** | EHR、影像、病理、组学、试验、随访等多源异构接入，不搬运、不复制既有 source of truth | Foundry 数据接入 / Pipeline Builder |
| **② 本体层（核心）** | Objects（患者/病灶/样本/试验/药物）+ Links（关系）+ Actions（带规则的动词）+ 安全策略 | **Ontology** |
| **③ Agent 层** | LLM Agent 在本体约束下完成检索、推理、队列创建、风险预测、流程触发 | **AIP**（AIP Logic / Agent Studio） |
| **④ 决策/运营层** | 辅助 MDT 多学科会诊、试验匹配、路径排班，动作写回源系统并全程审计 | Workshop / Quiver / OSDK 应用 |

### 0.3 Agent 扮演的典型角色

- **信息整合**：跨系统秒级聚合患者全景，替代人工逐系统翻查；
- **队列/试验匹配**：基于本体 + 规则做入组筛选（学术界前瞻研究显示筛选时间可降约 4 倍，详见第 1.3 节）；
- **决策辅助**：MDT 会诊中提供证据与方案建议（人在回路，不自动执行）；
- **流程触发**：排班、通知、状态推进等动作，经审批后写回 OA/EHR。

### 0.4 合规底座（肿瘤/医药刚需）

GxP qualification package、**21 CFR Part 11**、细粒度对象级访问控制、透明数据血缘（provenance）、全动作审计——这些是医药客户敢把临床/试验数据放上来的前提。

### 0.5 证据与边界（不替概念吹牛皮）

- 平台与机制为 **Palantir 官方事实**（见第 1 章来源）；
- "Palantir Oncology"作为整齐的概念词条，属**业界归纳**，非官方产品名；
- 疗效/运营数字**多由院方或 Palantir 自报**，独立验证有限；
- 闭源、SaaS、美系主权、锁定与伦理争议真实存在（见第 2 章）——**学范式，不引进产品**。

---

## 1. Palantir 架构拆解（三平台）

| 平台 | 定位 | 类比 |
|---|---|---|
| **Foundry** | 数据运营核心：数据接入、管道、转换、血缘、治理 | 数据中台 + 应用工厂 |
| **AIP** (Artificial Intelligence Platform) | 生成式 AI / Agent 平台，LLM 绑定受治理的 Ontology | 我们的 model-scheduling + Agent |
| **Apollo** | 持续交付 / 部署（300+ 微服务，可到边缘/主权环境） | CI/CD + 运维网格 |

### 1.1 皇冠：Ontology（本体）

官方定义：Ontology 把企业的**数据、逻辑、动作、安全策略**整合为人和 AI Agent 都能直接使用的统一表示。三个要素：

- **Objects（名词）**：客户、订单、患者、设备……由底层多模态存储支撑，不是新建一套数据，而是"逻辑映射"（no duplication / 不破坏既有 source of truth）。
- **Links（关系）**：对象之间的连接（≈ 知识图谱的边）。
- **Actions（动词）**：在对象上可执行的、**带业务规则和审计**的写回操作（如取消订单、调整排班、运行仿真）。

> 精髓一句话（来自开源参考实现 gura105/operational-ontology）：
> **"语义层让你读懂业务；运营本体让你运营业务。"**
> （A semantic layer lets you read your business. An operational ontology lets you run it.）

关键设计：**业务规则活在模型里，而不是靠 prompt 约束**。Agent 试图取消已发货订单，会和人一样收到 `SHIPPED_ORDER_CANNOT_BE_CANCELLED`。这正是企业级 Agent 与"套壳聊天"的分水岭。

### 1.2 肿瘤场景的标准落地链路

```
影像/病理/ECG/EHR/试验数据
   → 集中接入（100GB+，多源异构）
   → 自动 ETL + 标准化到共同数据模型
   → Ontology 建模（患者-队列-样本-试验-病灶…）
   → 应用：队列创建、路径监控、风险预测、动态排班
   → 动作写回 + 全程血缘/审计
```

合规资产：GxP qualification package、21 CFR Part 11、细粒度访问控制、透明数据血缘（provenance）以支持跨试验数据复用。

---

## 2. 社区视角：批评与真实短板（避免只看官方）

| 维度 | 具体问题 | 来源 |
|---|---|---|
| **厂商锁定** | 数据以专有形态存在，导出 CSV/JSON 后"无任何等价系统可直接用"；迁移"漫长且昂贵" | HASH 博客、r/dataengineering |
| **成本** | "很强大但相当贵"，NHS FDP 合同约 £330M | Reddit、FT |
| **工程质量** | 实际使用者抱怨 bug 数量与类型，与高价不匹配 | r/datascience |
| **数据/伦理争议** | NHS 一线员工因 Palantir 的国防/政治背景拒绝使用；NYC 医院因"数据抓取"担忧终止合同；英国政客警告"危险的锁定" | Medact 2026、aicerts 2026-04 |
| **证据强度** | 医院成效**几乎全部由院方或 Palantir 自报**，缺独立验证 | pal4c.com（Palantir 实施商） |

**对我们的启示**：Palantir 模式的价值是真的，但**闭源 + SaaS + 美国主权云**这三点，对一家中国企业（尤其涉及内部业务数据）基本不可接受。学范式，不引进产品。

---

## 3. 开源/自建替代（三路之开源）

| 项目 | 形态 | License | 可借鉴点 |
|---|---|---|---|
| **gura105/operational-ontology** | 极简 TS 参考实现：objects/links/actions + 自动生成 MCP 工具（`search_order`/`cancel_order`/`read_audit_log`） | MIT | **最值得精读**，把 Ontology 模式压到最小可读，含 MCP 接入 |
| **Marsovius** | 完整 Foundry 开源替代（本体/数字孪生/审计预测），欧洲主权导向 | Apache-2.0 | 概念对照与产品形态参考 |
| **Helix Foundry (HelixDB)** | 连接 DB/API/文件服务成"公司本体"，AI 答案由**实际执行 SQL** 支撑 | 开源 | DuckDB + 图 + S3 的轻量栈 |
| **openfoundry (aisoftware)** | 云原生运营数据平台单体仓（数据集/本体/应用/AI/治理/可观测） | 开源 | 模块切分参考 |
| **Przyval/openfoundry** | Foundry 本地模拟器（Foundry 兼容 API + 内存存储） | 开源 | API 契约对照 |

社区高赞提醒（LinkedIn 评论）：
> **"Foundry 真正的护城河不是数据模型，而是 Ontology 层 + 多年在脏乱的企业遗留系统集成上的积累。复刻 UI 和管道构建器的开源项目，一旦要连 40 个没有标准 API 的老系统就会撞墙。"**

这句话对我们直接成立：**业务资产建设的硬骨头是"接入和语义对齐"，不是建一个问答界面。**

---

## 4. 与当前系统的对照评估

### 4.1 现状（已具备的底子）

| 我们已有的 | 对应 Palantir 概念 |
|---|---|
| L2 `ai-knowledge-base`：entity / entity_attr / collection / kb_relation | Objects + Links（读模型）✅ |
| GraphRAG：关系存储、子图扩展、LLM 自动抽取实体关系 | 图谱/关系层 ✅ |
| 混合检索（确定性→FTS→向量）+ 强制来源引用 | 读侧 + 血缘/引用 ✅ |
| ABAC 文档级权限、检索时过滤 | 安全策略（部分）✅ |
| model-scheduling + MCP 工具描述符 | AIP + Agent 接入 ✅ |
| L4 `product-kb`（8 产品线/193 产品/385 SKU/944 文档/6195 切片）、`bangcle-contract` | 业务实例 ✅ |

### 4.2 核心差距：我们只有"读模型"，缺"运营本体"的"动词"

这是本次调研最重要的发现。我们的知识库能**回答**问题（read），但 Palantir Ontology 的另一半是**带规则、可审计、能写回源系统的 Action（run）**：

| 差距 | Palantir 做法 | 我们现状 |
|---|---|---|
| **Action 抽象** | 对象上定义动作，动作=业务规则+权限+审计+写回 | ❌ 无统一抽象，写操作散落在各脚本/skill |
| **规则即模型** | 业务规则在本体层，Agent 与人走同一校验 | ⚠️ 部分靠 prompt / 各组件 if-else |
| **活体连接器** | 双向连接 ERP/CRM/OA，不搬运、不复制 | ⚠️ 目前以导入为主（文档/Excel），缺实时双向 connector |
| **数字孪生 / 写操作审计** | 每次动作尝试都审计，可仿真 | ❌ 审计日志标记为"待扩展" |
| **运营动作编排** | Action 串联规则+ML+LLM 形成工作流 | ⚠️ DAG 编排器在建，未与本体 Action 绑定 |

---

## 5. 对业务资产（L3/L4）建设的具体优化建议

按"价值/成本"排序，全部可在**不引入 Palantir、坚持开源/自建**前提下落地。

### 🟢 P0 —— 把"运营本体 Action"纳入 L2 抽象（最高杠杆）

在 `ai-knowledge-base` 增加 **Action 层**，与现有 entity/relation 对称：

```
object   (名词)  —— 已有 entity
link     (关系)  —— 已有 kb_relation
action   (动词)  —— 【新增】
```

Action 数据模型建议：
- `action(id, object_type, name, rule_spec, permission, writeback_target)`
- `action_log(id, action_id, caller, input, result: ALLOWED|REJECTED, reason, ts)` —— 每次尝试必留痕（含被拒）
- 规则与调用者身份解耦：**Agent 和人走同一条校验路径**（直接对标 `SHIPPED_ORDER_CANNOT_BE_CANCELLED`）。

参考实现精读 `gura105/operational-ontology`（MIT，TS；我们用 Python 移植概念）。

### 🟢 P1 —— L4 业务实例先行验证"动词"

选两个已有 L4 场景端到端验证 Action 写回：

| 实例 | 可落地的 Action（举例） |
|---|---|
| `bangcle-contract` | `submit_approval` / `escalate` / `reject` / `link_product` —— 复用 L3 `contract-management` 状态机，动作受状态机约束，写回泛微 OA |
| `product-kb` | `update_sku_status` / `merge_duplicate_product` / `bind_contract_line` —— 写回前走规则+审计 |

这正好把 L3 合同状态机（纯逻辑核心）变成**可被 Agent 安全调用的"动词集合"**，而不是让 LLM 直接碰 OA。

### 🟡 P2 —— 双向连接器（Connector）替代单向导入

针对最痛的源系统（泛微 OA、企业微信、产品库）做**双向 connector**：读侧保持"不复制、映射 source of truth"，写侧只允许通过 Action。这是真正的脏活，也是护城河——比再加一个问答界面值钱得多。

### 🟡 P3 —— 审计日志 / 血缘 / 合规补齐

能力矩阵中已标"待扩展"的三项（审计日志、PII 脱敏、版本治理）借 Action 落地一起补：`action_log` 天然是审计与合规底座。

### 🔵 P4（可选，远期）

若业务规模上量，参考 Marsovius / openfoundry 的模块切分评估是否演进到 PostgreSQL + Qdrant，以及"数字孪生/仿真"能力。**不建议现阶段引入。**

---

## 6. 明确不建议做的事

- ❌ **不采购 / 不上 Palantir**：闭源、SaaS、美系主权、£330M 级成本、厂商锁定、医疗数据伦理争议——对我们场景不可接受。
- ❌ **不为了"对标"而照搬 300+ 微服务的重架构**：我们的规模用不到，迭代演进原则不变。
- ❌ **不把精力放在复刻 UI / dashboard**：护城河在 Ontology + 遗留系统集成，不在界面。

---

## 7. 建议的下一步（待 Rex 拍板）

1. 是否启动 **L2 `ai-knowledge-base` 的 Action 层设计**？按铁律先走：`DESIGN-OUTLINE-action-layer-v1.0` → 评审通过 → 详细设计。
2. 首个验证实例定为 `bangcle-contract`（复用现有状态机，闭环最短）还是 `product-kb`？
3. 是否需要我把 `gura105/operational-ontology` 精读后产出一份"概念到 Python 的移植对照"作为设计输入？

---

## 附：主要信息来源

- Palantir 官方架构：palantir.com/docs/foundry/architecture-center/platforms、/overview
- NHS 癌症路径 28%：blog.palantir.com (2023-01-13)
- 医疗落地与短板：pal4c.com/palantir-healthcare（2026-10-08）
- 锁定/成本批评：hash.ai/blog/the-problem-with-palantir；r/datascience、r/dataengineering
- NHS 伦理争议：medact.org (2026)；aicerts.ai (2026-04)
- 开源：github.com/gura105/operational-ontology；marsovius.com；Helix Foundry；github.com/aisoftware/openfoundry
