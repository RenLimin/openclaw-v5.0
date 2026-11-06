# DESIGN-OUTLINE — L4 bangcle-contract × 运营本体桥（Contract Ontology Bridge）v1.0

> L4 · bangcle-contract · 依据：RESEARCH-palantir-oncology-v1.1 §5 P0/P1 + DESIGN-DETAIL-operational-ontology-v1.0（已通过）+ DESIGN-DETAIL-contract-management-v1.0 §7（已通过）
> 版本 v1.0 · 状态：**已验收 P1–P3**（Rex 2026-11-06 授权收口；实现 `a1efeb4`，黄金 7 基准 + L4 194/L3 115 回归绿）· **P4 泛微真写回不在本立项范围**，另立项（见 `docs/research/PROPOSAL-palantir-p4-oa-writeback-v1.0.md`） · 2026-11-03 · Jerry 🦞
> 关联提交：L2 运营本体 P1–P4（`ae3a1b9`，114 tests 绿）；L3 contract-management P1/P2（42 tests 绿）

---

## 1. 背景与目标

调研结论（RESEARCH-palantir-oncology §4.2）：我们已有"读模型"（entity/relation/kb_relation/GraphRAG），缺 Palantir 范式的另一半——**带规则、可审计、能写回的 Action（动词）**。L2 运营本体 P1–P4 已把"动词引擎"修好并通过验收（`ont_identity` / `ont_action_type` / `ont_proposal` / `ont_decision_record` / Saga 连接器，REST+MCP 已接）。

但全 workspace **没有一个真实装配过的 ai_kb DB**；L4 `bangcle-contract` 从未走 Proposal Gate（只在解析器层 import `ai_kb.parsers`）。**范式尚未真实落地过一次。**

本立项目标：让 `bangcle-contract` 成为**第一个真实运营的"动词引擎"实例**——合同作为运营对象，submit/approve/reject 经 Proposal Gate 安全执行，写回真实生效并全程审计。**闭环最短、复用现成 L3 零件。**

## 2. 现状盘点（契约对齐后的基线与缺口）

| 层 | 已有 | 缺口 |
|---|---|---|
| L2 | `ProposalService.propose/validate/review/commit` 全状态机 + CWA + AssemblyGate + NullConnector + 审计/决策双写 | —（已验收） |
| L3 | 9 个 deterministic handler + 3 action type 注册脚本（submit=auto/approve=human/reject=human），集成测试 28 绿 | —（已就绪，无需改） |
| L4 | 一次性审查管线（reviews/review_item/audit_log 表 + pipeline） | **无 contract 运营对象表**；**无 Proposal Gate 接入**；**无装配脚本**；**无写回连接器** |

**关键契约约束（来自 L2 源码，非猜测）：**
- CWA：`propose_action(object_refs=[...])` 的对象**必须已登记** `ont_identity`（domain + object_type + canonical_key），否则直接拒绝 → 合同必须先登记才能运营。
- commit 的 change_set 只写 `ont_identity.metadata.applied_changes`（纯增量、可追溯），**不写任何 L4 自己的表** → 要让"动词真实生效"，必须提供 `ContractWritebackConnector` 把状态变更写回 L4 contract 表。
- `required_approval=human` 的 action 只能由 `reviewer_kind='human'` 审，agent 越权直接 `PermissionError`（L2 内置，我们只需在黄金基准中验证）。

## 3. 方案设计（分层）

```
┌─ L4 bangcle-contract（新增 ontology_bridge 模块）──────────────┐
│  contract 表（运营对象：contract_no/title/amount/status/审批流）│
│  ContractRegistry：登记合同 → ont_identity(object_type=contract)│
│  ContractOntologyBridge：propose→validate→review→commit 编排   │
│  ContractWritebackConnector：commit 时把 status 写回 contract 表│
│  cli/contractctl.py 扩展：ontology submit/approve/reject/status │
└──────────────────────────────┬─────────────────────────────────┘
                               │ 调用（L4 → L2 单向依赖）
┌─ L2 ai-knowledge-base（已有，不改）───────────────────────────┐
│  ProposalService / ActionRegistry / AssemblyGate / 审计/决策    │
│  ont_identity / ont_proposal / ont_decision_record / Saga      │
└──────────────────────────────▲─────────────────────────────────┘
                               │ 绑定（已有）
┌─ L3 contract-management（已有，不改）─────────────────────────┐
│  core/ontology_adapter.py 9 handler（状态机规则）              │
│  scripts/register_ontology_functions.py（3 action type）       │
└────────────────────────────────────────────────────────────────┘
```

**数据流（一条合同审批的完整旅程）：**
1. `ContractRegistry.register(contract_no, title, amount)` → 建 L4 contract 行 + 登记 L2 `ont_identity`（object_type=`contract`，canonical_key=规范化 contract_no）
2. `bridge.submit(cid, operator)` → `propose_action('submit_contract')` → `validate()`（调 L3 `validate_submit_state`，检查 draft→review1 合法性）→ `review(auto)` → `commit()` → Connector 写回 `contract.status=draft→review1`
3. `bridge.approve(cid, human_reviewer)` → propose `approve_contract` → validate（L3 状态机 + 审批层级）→ **human review** → commit → 写回 status 推进
4. 任何越权/非法转移/未登记对象 → L2 拒绝并留痕，L4 侧只透传异常

## 4. 关键设计决策（含备选，供评审）

### D1 合同运营对象表落点
- **A（推荐）**：L4 repository 新增 `contract` 表为 source of truth；L2 `ont_identity` 为运营索引/快照。合同生命周期（状态）以 L4 表为准，L2 只记录对象存在 + 变更快照 + 决策。
- B：直接只用 L2 `ont_identity.metadata` 存全部合同字段 → L4 失去自有查询/报表能力，且 L2 是平台层不该存业务全量。
- **选 A**：符合"L2 平台化、L4 业务实例化"分层铁律。

### D2 写回连接器
- **A（推荐）**：`ContractWritebackConnector`（本地真实写回：commit 事务内把 status/审批字段写入 L4 contract 表；compensate=写回 before 状态，本地表可逆 → Saga 可完整演示）。
- B：沿用 NullConnector → "动词落地"无法被断言，演示价值为零。
- **选 A**。真写回 + 可补偿，正是 Palantir"动作写回+审计"范式的核心验证。

### D3 review 管线与运营对象的桥接
- **A（推荐）**：起步**不耦合**。review 管线（一次性分析）与 contract 对象（可运营生命周期）独立；可选提供 `review → contract` 一键登记桥（报告通过后提炼 contract 对象）作为 P3 附加项。
- B：强耦合（每次 review 自动建合同）→ 引入"未审批就建对象"的噪声，且超出本立项最小闭环。
- **选 A**，一键登记桥列为可选加分项。

### D4 canonical_key 规范化
- 对齐 product-kb 身份层经验：NFKC 全角转半角 + 去空白/标点 + 小写；**保留编号语义**（合同号如 `HT-2026-001` 去空白后原样）。键一经生成不可变。

## 5. 范围与边界（红线）

- ✅ 只做：contract 运营对象表、登记、bridge 编排、真写回 connector、CLI、黄金 E2E。
- ❌ 不改 L2 ai-knowledge-base 源码/测试（只调用）。
- ❌ 不改 L3 contract-management 源码（复用注册脚本与 handler；如发现脚本缺陷走 L3 变更流程）。
- ❌ 不做泛微 OA 真写回（属 P2 连接器立项；本立项用本地表写回演示 Saga，接口按 `WritebackConnector` 契约预留）。
- ❌ 不物理删除/不可逆操作；所有变更走 Proposal Gate + 审计。
- ❌ 不新增第三方依赖、凭据、网络调用（stdlib + sqlite + 既有库）。

## 6. Phase 建议（每 Phase 三道门：自测 → VERIFICATION → Rex 验收）

| Phase | 内容 | 预估 |
|---|---|---|
| **P1 对象与装配** | contract 表 DDL + ContractRegistry（登记+canonical_key+CWA 拒绝未登记）+ 真实装配脚本（跑 L3 注册 + 建域 + 登记示例合同）；真实 ai_kb DB 首次落地 | 1 人日 |
| **P2 编排与写回** | ContractOntologyBridge（propose/validate/review/commit 封装 + 状态机流转断言）+ ContractWritebackConnector（真写回+补偿）+ 单元/集成测试 | 1.5 人日 |
| **P3 CLI 与黄金 E2E** | contractctl ontology 子命令 + 5 组黄金基准（提交闭环/越权拒绝/非法转移/幂等重放/补偿回滚）+ REST/MCP 冒烟 + VERIFICATION + OPERATIONS 更新 | 1 人日 |
| **合计** | | **3.5 人日**（缓冲 +20% ≈ 4.2 封顶） |

## 7. 验收标准（黄金基准草案）

1. **提交闭环**：`submit(HT-2026-001)` → pending → validated → auto approve → committed → `contract.status=draft→review1`（L4 表 + L2 决策记录双写，evidence 完整）。
2. **越权拒绝**：agent 以 `reviewer_kind='agent'` 审 `approve_contract`（human）→ `PermissionError`，审计留痕。
3. **非法转移**：未 submit 直接 propose `approve_contract` → L3 `validate_approve_state` 拒绝（状态机约束），proposal 留违规痕不 committed。
4. **幂等重放**：同 `idempotency_key` 重复 submit → 返回既有 proposal，无二次副作用。
5. **补偿回滚**：写回第二步注入失败 → 事务 ROLLBACK + 状态 failed + 人工对账工单记录，无静默。

## 8. 交付物清单

- 代码：`contract_review/ontology_bridge/`（registry.py / bridge.py / connector.py）、`repository/db.py`（contract 表 migration）、`scripts/register_contract_ontology.py`、`cli/contractctl.py` 扩展
- 测试：单元/集成/E2E + 5 组黄金基准
- 文档：VERIFICATION（每 Phase）+ OPERATIONS 更新 + 本立项的 DETAIL/PLAN

## 9. 待 Rex 拍板

1. 方案总体（§3）与三个关键决策 D1–D4 是否通过；
2. Phase 划分（§6）是否认可；
3. 验收标准（§7）是否补充。
