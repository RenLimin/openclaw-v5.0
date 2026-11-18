# DESIGN-OUTLINE — OA 销售合同审查增强 v1.0（待评审）

> 元信息：本文档由 Jerry 于 2026-11-18 生成；应答契约版本 ADR-035 P1 v1.2 / P2 contract-answer-spec；归属 Bangcle 合同管理域（L4 CME-001）；数据基准 2026-11-18。
>
> 上游：`PRD-oa-contract-review-enhance-v1.0.md`。本文件只定**整体架构 + 模块划分 + 复用边界**，接口契约见后续 DESIGN-DETAIL。

## 0. 溯源链

```
上游 PRD：docs/architecture/PRD-oa-contract-review-enhance-v1.0.md
  → 输入：886377 审查实测证据（履约义务异常 / 超概算 4,000）
  → 结论：§2 代码盘点 / §3 目标架构 / §5 设计决策
实测证据：OA 单据 886377、概算卡片 9955（只读）；BDMS 交付月报 202606
  → 查询：oa_workflow_ones.py --capture 886377 / Playwright cube card 9955 / sqlite3 mode=ro
  → 结论：§2.1 复用清单 / §2.2 缺口 / §5.3 概算读取
```

## 1. 需求复述（一句话）

给 OA 757「销售合同审核流程」的**只读审查**增加两项核查：① 客户维度履约义务状态（异常判定）；② 概算明细/单价一致性（本单 ≤ 概算）。**不做任何 OA 写操作**。

## 2. 真实代码盘点（实证）

### 2.1 已具备、可直接复用

| 能力 | 资产 | 复用方式 |
|---|---|---|
| OA 单据捕获 | `ones-browser-export/scripts/oa_workflow_ones.py --capture <rid>` | **直接复用**（757 实测通过：886377/885969） |
| OA 会话 | `~/.openclaw/data/clm-oa-recon/state.json` + `services/oa/browser_fallback.refresh_oa_session()` | **直接复用**（本次已用） |
| OA 单据读取 | `bangcle-contract/services/oa`（`CubeClient`/`ApprovalLogReader`/`cube_provider`） | 复用 `ApprovalLogReader`（与 workflowid 解耦） |
| 合同正文审查 | `contractctl review`（22 条规则） | **不动**，增量叠加 |
| BDMS 库读取 | `bdms.db`（`dr_sheet_row` 交付月报 / `md_reference` 状态字典） | 新增只读查询模块 |
| 确收库读取 | `revenue.db`（`budget_exec` / `plan_draft`） | 新增只读查询模块（补充口径） |

### 2.2 缺口（本设计要补）

| 缺口 | 说明 |
|---|---|
| R1 查询 | 无「按客户/最终用户查履约义务 + 状态汇总」的现成脚本（`bdms/cli` 无此子命令） |
| R2 查询 | 无「按概算 billid 读概算卡片明细并逐项比对」的现成脚本 |
| 编排 | 无把 R1/R2 嵌入审查报告的编排 |

## 3. 目标架构（增量，不动既有）

```
contractctl review（既有 22 条）
        │
        ▼
oa-contract-review-enhance/            ← 新增（只读增强层）
  ├─ obligation_check.py    R1：客户履约义务核查
  │    数据源：bdms.db.dr_sheet_row（+ revenue.db 补充）
  │    入口：--customer/--end-user/--product-codes
  ├─ estimate_check.py      R2：概算一致性核查
  │    数据源：OA cube card（Playwright + storage_state，只读）
  │    入口：--estimate-billid + 本单分项 JSON
  └─ runner.py              编排：读取单据 → 调 R1/R2 → 合并进审查报告
```

**落点**：`L4-proprietary/components/bangcle-contract/scripts/`（与 `reconcile_oa.py` 同目录）或新建 `services/oa/enhance/`；详细归属在 DESIGN-DETAIL 定。

## 4. 模块划分

| 模块 | 职责 | 契约要点（概要） |
|---|---|---|
| `obligation_check` | 客户 → 履约义务清单 + 异常判定 | 输入：客户名/最终用户名/产品编码集；输出：`{records:[], anomalies:[], data_basis:"202606", missing:[]}` |
| `estimate_check` | 概算卡片 → 逐项比对 | 输入：概算 billid + 本单分项；输出：`{rows:[{code, estimate, actual, diff, verdict}], total, verdict}` |
| `runner` | 编排 + 报告合并 | 复用 `oa_workflow_ones.py --capture`，只读；失败降级不中断 |

## 5. 关键设计决策（建议）

1. **数据源优先级**：R1 以 `bdms.db.dr_sheet_row`（交付月报，含状态列）为主，`revenue.db`（含 plan_done/forecast_category）为辅；两库口径冲突时显式标注，不擅自合并。
2. **状态判定表**：异常 = {2,3,5,6,8}（应交未交/交付异常/应验未验/验收异常/应结未结）；正常 = {1,4,7,9}。字典取自 `md_reference.obligation_status`/`item_stat_status`，**硬编码需与字典一致**。
3. **概算读取**：复用 `oa_workflow_ones.py` 的 Playwright + storage_state 模式（本次实测 9955 可读）；优先解析 `layoutBase`/`mainFields` XHR 的结构化数据，body 文本作兜底。
4. **匹配键**：R2 按**产品服务编码**匹配（比按名称稳定）；编码缺失时降级按名称并标注。
5. **只读红线**：新模块**只读**，禁止任何 OA/BDMS 写操作；BDMS 用 `mode=ro`。
6. **无权限降级**：「概算流程」单据（requestid 885969）当前无权限 → R2 只读卡片，显式 `skipped: no_permission` 留证。

## 6. Phase 拆分（建议）

| Phase | 内容 | 产出 |
|---|---|---|
| P1 | `obligation_check` + 单测（真实 886377 数据跑通） | 可复现报告 |
| P2 | `estimate_check` + 单测（真实 9955 跑通） | 可复现比对表 |
| P3 | `runner` 编排 + 嵌入 `contractctl review` 报告 | 端到端 |
| P4 | 验收（A1~A5）+ 文档固化 | 验收回执 |

## 7. 红线

- ❌ 不做 OA 写操作（本工作流只提供审批建议）。
- ❌ 不伪造数据：无记录/无权限一律显式 skip。
- ❌ 不重造 OA/ONES 自动化（复用 `oa_workflow_ones.py`）。
- ✅ 提交一律隔离临时 index（`GIT_INDEX_FILE`）。

## 7b. 质量信号

- ⚠️ 数据源（BDMS 交付月报）为 **202606 月度快照**，非实时，可能过期；R1 结论须标注数据基准月。
- 本设计基于 **886377 在审单据**实测，字段随后续退回可能变化。
- 「概算流程」单据（requestid 885969）当前账号无权限 → R2 只读卡片，显式 skip 留证。

## 8. 待 Rex 拍板

1. **落点**：新建 `services/oa/enhance/` vs `scripts/` 平铺？
2. **触发方式**：作为 `contractctl review` 子步骤自动跑，还是独立 CLI（`contractctl oa-enhance`）按需跑？
3. **是否纳入 CME 路由**（`contract-manager-expert` SKILL.md）作为固定审查项？

【已验证 2026-11-18｜OA 单据 886377 + 概算卡片 9955 只读 + BDMS 202606 快照】架构决策依据。
