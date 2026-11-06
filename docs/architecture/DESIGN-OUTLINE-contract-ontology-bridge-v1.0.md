# DESIGN-OUTLINE — Contract Ontology Bridge v1.0（重做版 · 待评审）

> 状态：**待 Rex 评审**。通过后才进 DESIGN-DETAIL。
>
> 📌 **关系指针（2026-11-06 追加，不改写历史正文）**：本文档属 **11-04 旧路线——只读/持久化桥**（P1 字段映射只读适配 + P2 本地持久化/状态机接线，代码 `ontology/mapper.py`、`services/oa/cube_provider.py`，实现 `f0a7b57`/`33a5a2a`）。它与 **11-05 Palantir 范式动词桥**（L4 `contract_review/ontology_bridge/`，合同登记为 L2 运营对象 + Proposal Gate + Saga 真写回，实现 `a1efeb4`，设计见 `L4-proprietary/components/bangcle-contract/docs/DESIGN-OUTLINE-contract-ontology-bridge-v1.0.md`）是**两条并存路线**：旧桥解决“读得准/对得齐”，动词桥解决“可审计地写回”。两者代码均在、用途不同；P1–P3 已由 Rex 2026-11-06 验收。
> 重做原因：压缩摘要继承的 OUTLINE / 提交 `d6470ec` / 锚点（`ProposalService`、`SagaStep`、`ACTION_TYPES`、`register_action_type` 等）在当前仓库**全部查无实证**（全分支/refs/reflog/文件系统）。本版仅基于**亲眼通读的真实代码**重立。
> 日期：2026-11-04 · Jerry 🦞

---

## 1. 需求复述

在 **L3 通用合同管理（纯逻辑）** 与 **L4 梆梆合同（泛微集成 + 持久化 + 编排）** 之间建一座"本体桥"：把 L3 的合同/审批/风险**领域模型与状态**，与泛微侧真实数据/流程**对齐并可双向同步**，同时守住分层与"高影响动作由人决策"红线。

---

## 2. 真实代码盘点（实证，非继承）

### L3 `contract-management`（纯逻辑，785 行，零副作用）
| 模块 | 真实能力 |
|---|---|
| `models.py` | `Contract` / `ApprovalConfig` / `ApprovalRecord` / `AuditLogEntry` / `RiskFinding` / `RiskReport`；8 态 `CONTRACT_STATUSES` + `VALID_TRANSITIONS` |
| `state_machine.py` | 金额分级审批（1~4 级），`next_approval_status()` 纯函数 + `ApprovalStateMachine` 只**算**下一状态、产出记录，**不落库** |
| `risk_engine.py` | 民法典 22 规则 `scan_text()`，纯函数 |
| `amount_utils.py` | `amount_to_chinese()` |
| `oa/base.py` | `OaProvider` ABC：4 方法（`get_contract_attachment` / `query_process` / `push_result` / `register_callback`），**零实现** |

依赖方向 L4→L3；L3 仅 stdlib。

### L4 `bangcle-contract`（只交付"合同审查"单链路）
```
OA拉取 → 数字化 → L3风险扫描 → product-kb比对 → Markdown/Excel报告 → SQLite审查三表
```
- `services/oa/`：`cube.py`(`CubeClient`) + `browser_fallback.py` + `entry.py`，**全部为入站拉取**。
- `contract_review/`：ingest/digitize/risk/kb_match/parser/report 编排。
- `repository/db.py`：仅 `reviews` / `kb_matches` / `audit_logs`（审查域三表，审计 append-only）。

---

## 3. 三条真实鸿沟（Bridge 要补的）

| # | 鸿沟 | 证据 |
|---|---|---|
| **G1** | `CubeClient` **只拉不写、未实现** L3 `OaProvider` | `grep push_result/OaProvider` 源码 0 命中；`cube.py` 无任何 POST/同意/驳回 |
| **G2** | L4 **只接了 L3 的 `risk_engine`**，状态机 / models / `OaProvider` 全未接 | 全 L4 仅 `contract_review/risk.py:39` 一处 import L3 |
| **G3** | 持久化**无合同/审批实例表**，无法承载状态机生命周期 | `db.py` schema 仅审查三表 |

**文档与代码脱节**：L4 `docs/DESIGN-OUTLINE-v1.0.md` 规划了 `MockOaProvider`/`DingTalkOaProvider`、`contract_service`、`oa_callback`、双向同步——**这些代码一个都不存在**；真实 OA 侧是泛微建模引擎 Cube，不是文档写的钉钉。

**关键可行性约束**：当前 Cube 属泛微**建模引擎**（合同卡片 `main_fields/attachments`），**不承载审批节点状态**；审批流是泛微另一套 workflow API，**仓库内无该客户端、无真实快照**。故"审批状态映射"在 P1 阶段**无可靠数据源**，不得凭空造映射。

---

## 4. 目标架构（增量，不动既有）

在 L4 **新增**桥接层，复用而非改写：

```
┌─────────────── L4 bangcle-contract（新增 bridge/）───────────────┐
│  ontology/mapper.py   合同字段  泛微卡片  ↔ L3 Contract（纯映射）  │
│  ontology/state_map.py 状态字典 + 置信度 + 数据源标记（默认unknown）│
│  services/oa/cube_provider.py  CubeClient 适配 OaProvider（只读先行）│
│  repository/  +contracts/+approval_instances（增量幂等迁移）        │
│  services/contract_service.py  读→映射→调L3状态机→(人工确认)→落库  │
└──────────────────────────────┬──────────────────────────────────┘
                               │ 只调用，不修改
              ┌────────────────▼───────────────┐
              │ L3 contract-management（纯逻辑） │
              └─────────────────────────────────┘
```

**映射分层原则**：
- 字段映射（卡片↔Contract）= 确定性纯函数，可单测、可黄金基准。
- 状态映射 = 输出 `(l3_status, confidence, source)`；**数据源不可得时一律 `unknown` + 低置信度**，绝不猜成具体审批态。
- LLM（若用）只可**提议**映射，业务规则走 deterministic 函数；`validated ≠ committed`。

---

## 5. Phase 拆分（建议）

| Phase | 范围 | 出口标准 | 写回? |
|---|---|---|---|
| **P1 只读桥** | G2 字段映射 + Cube→Contract；`CubeOaProvider` 实现 `get_contract_attachment`/`query_process`（后者暂返 unknown） | 真实卡片快照→L3 Contract 黄金比对；OaProvider 抽象测试全过 | ❌ |
| **P2 持久化 + 状态机接线** | G3 增量建 `contracts`/`approval_instances` 表；`contract_service` 调 L3 状态机推进本地态 | 状态机全路径在真实 SQLite 上跑通；迁移幂等 ×3；审计 append-only | 仅本地 |
| **P3 待数据源确认** | 仅当拿到泛微 **workflow 审批流**真实 API + 快照后，做审批节点→L3 状态映射与 `push_result` | 需先补可行性调研 + Rex 单独拍板 | 人工确认后 |
| **P4（可选）回调/真写回** | `register_callback` / OA 回写，事件驱动双向同步 | 默认关闭；同意/驳回**必须人决策**，系统只提交人已批准的动作 | 受控 |

> P1/P2 无外部副作用，可连续做；**P3 卡在"workflow 数据源"**，在 Rex 提供入口或允许侦察前不启动。

---

## 6. 红线

- 不改 L3 `contract-management`、L2 `ai-knowledge-base` 的源码/测试；只调用。
- 不做泛微真写回、不物理删除；`push_result` 在 P4 前不落真实动作。
- 无 workflow 数据源时，审批状态映射只许输出 `unknown`，禁止伪造节点/状态。
- 不新增第三方依赖/凭据；migration 增量幂等；state 文件权限 600、入 `~/.openclaw/state`。
- 测试用真实执行（含真实 HTTP 当涉及网络安全），不污染真实 state/log/DB。

---

## 7. 待 Rex 拍板

1. 本 OUTLINE 范围与 Phase 切分（P1/P2/P3/P4）是否认可？
2. P3 的泛微 **workflow 审批流入口**：你提供 API/凭据，还是授权先做只读侦察？在此之前 P3/P4 冻结。
3. 是否同意"P1 只做只读字段映射 + 状态默认 unknown"的保守起点？
