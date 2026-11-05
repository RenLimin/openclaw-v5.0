# Palantir Oncology 调研与系统优化评估

> 调研人：Jerry 🦞 · 日期：2026-10-31 · 版本 v1.0
> 范围：Palantir 在肿瘤/医疗领域的能力（Foundry / AIP / Ontology），评估对当前四层系统尤其 L3/L4 业务资产建设的优化空间。
> 调研覆盖：官方文档、社区评价（Reddit/Medact/HASH）、开源替代（GitHub）——三路齐备。

---

## 0. 关键事实澄清（先纠正一个前提）

**不存在名为「Palantir Oncology」的独立产品。** Palantir 没有单一的"肿瘤产品"，它在肿瘤领域的价值是**通用平台（Foundry + AIP）在癌症场景的落地**：

- **肿瘤诊疗路径优化**：NHS England 癌症路径（cancer pathway）试点，公开报道**等待时间降低 28%**（2023-01 Palantir 官方博客）。
- **肿瘤科研数据整合**：某全球 Top5 药企将 Foundry 实例归类为 **GxP qualified**；某政府机构整合了约 **100 项肿瘤免疫疗法临床试验、25,000+ 患者**，做跨试验安全性/疗效 meta 分析。
- **医院运营层**：患者分流、床位、出院、排班、收入周期（Tampa General、Nebraska Medicine、Cleveland Clinic、HCA、NHS FDP）。

**核心结论先行**：Palantir 解决的不是"治癌"，而是**把分散在 EHR/影像/病理/试验系统里的数据，统一成可被人和 AI 调用的"业务对象 + 动作"，从而压缩流程等待**。这个模式与我们 L4 业务资产建设高度同构——值得借鉴的是它的 **Ontology（本体）范式**，不是买它的产品。

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
