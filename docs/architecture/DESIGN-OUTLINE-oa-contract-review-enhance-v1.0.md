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

给 OA 757「销售合同审核流程」的**只读审查**增加两项核查：① 客户维度履约义务状态（**以 ONES 实时为准**）；② 概算明细/单价一致性（**允许超概算，仅提醒**）。**不做任何 OA 写操作**。

## 2. 真实代码盘点（实证）

### 2.1 已具备、可直接复用

| 能力 | 资产 | 复用方式 |
|---|---|---|
| OA 单据捕获 | `ones-browser-export/scripts/oa_workflow_ones.py --capture <rid>` | **直接复用**（757 实测通过：886377/885969） |
| OA 会话 | `~/.openclaw/data/clm-oa-recon/state.json` + `services/oa/browser_fallback.refresh_oa_session()` | **直接复用**（本次已用） |
| OA 单据读取 | `bangcle-contract/services/oa`（`CubeClient`/`ApprovalLogReader`/`cube_provider`） | 复用 `ApprovalLogReader`（与 workflowid 解耦） |
| 合同正文审查 | `contractctl review`（22 条规则） | **不动**，增量叠加 |
| **ONES 实时查询** | `ones-browser-export/scripts/oa_workflow_ones.py --code <SSXM>`（GraphQL） | **直接复用**（实测 3440/3068/0328） |
| BDMS 库读取 | `bdms.db`（`dr_sheet_row` 交付月报 / `md_reference` 状态字典） | 仅用于**定位项目编码/合同编号**（月度快照） |
| 确收库读取 | `revenue.db`（`budget_exec` / `plan_draft`） | 新增只读查询模块（补充口径） |

### 2.2 缺口（本设计要补）

| 缺口 | 说明 |
|---|---|
| R1 查询 | `oa_workflow_ones.py --code` 可查单项目履约义务，但无「按客户/最终用户跨项目汇总 + 判定」的编排 |
| R2 查询 | 无「按概算 billid 读概算卡片明细并逐项比对」的现成脚本 |
| 编排 | 无把 R1/R2 嵌入审查报告的编排 |

## 3. 目标架构（增量，不动既有）

```
contractctl review（既有 22 条）
        │
        ▼
oa-contract-review-enhance/            ← 新增（只读增强层）
  ├─ obligation_check.py    R1：客户履约义务核查
  │    数据源：ONES 实时（GraphQL，主）+ BDMS 交付月报（项目编码线索）
  │    入口：--customer/--end-user/--product-codes（+ 可选 --project-codes）
  ├─ estimate_check.py      R2：概算一致性核查
  │    数据源：OA cube card（Playwright + storage_state，只读）
  │    入口：--estimate-billid + 本单分项 JSON
  └─ runner.py              编排：读取单据 → 调 R1/R2 → 合并进审查报告
```

**落点**：`L4-proprietary/components/bangcle-contract/scripts/`（与 `reconcile_oa.py` 同目录）或新建 `services/oa/enhance/`；详细归属在 DESIGN-DETAIL 定。

## 4. 模块划分

| 模块 | 职责 | 契约要点（概要） |
|---|---|---|
| `obligation_check` | 客户 → 履约义务清单 + 判定 | 输入：客户名/最终用户名/产品编码集；输出：`{records:[{code,status,owner,task_no}], verdict:"正常|提示|异常", queried_at, missing:[]}`（**状态取 ONES 实时**） |
| `estimate_check` | 概算卡片 → 逐项比对 | 输入：概算 billid + 本单分项；输出：`{rows:[{code, estimate, actual, diff, verdict}], total, verdict}` |
| `runner` | 编排 + 报告合并 | 复用 `oa_workflow_ones.py --capture`，只读；失败降级不中断 |

## 5. 关键设计决策（建议）

1. **数据源优先级**：R1 以 **ONES 实时**为准（`oa_workflow_ones.py --code` GraphQL，任务 `status.name`）；BDMS `dr_sheet_row` 仅用于**定位项目编码/合同编号**，其「履约项统计状态」聚合列与 ONES 实时存在口径差，**不作状态结论来源**；`revenue.db` 仅补充。
2. **状态判定表（基于 ONES 实时任务状态）**：正常 = `已完成` / `交付邮件已归档` / `客户确认版验收单` / `验收文件已归档`；提示 = `实施未开始` / `义务已拆分`（项目整体未完成）；异常 = `应交未交` / `交付异常` / `应验未验` / `验收异常` / `应结未结`。状态枚举取自 ONES issueType「项目履约义务」的 status 字典。
3. **概算读取**：复用 `oa_workflow_ones.py` 的 Playwright + storage_state 模式（本次实测 9955 可读）；优先解析 `layoutBase`/`mainFields` XHR 的结构化数据，body 文本作兜底。
4. **匹配键**：R2 按**产品服务编码**匹配（比按名称稳定）；编码缺失时降级按名称并标注。
5. **只读红线**：新模块**只读**，禁止任何 OA/BDMS 写操作；BDMS 用 `mode=ro`。
6. **无权限降级**：「概算流程」单据（requestid 885969）当前无权限 → R2 只读卡片，显式 `skipped: no_permission` 留证。

## 6. Phase 拆分（建议）

| Phase | 内容 | 产出 |
|---|---|---|
| P1 | `obligation_check` + 单测（真实 886377 数据跑通） | 可复现报告 |
| P2 | `estimate_check` + 单测（真实 9955 跑通） | 可复现比对表 |
| P3 | `runner` 编排 + `contractctl oa-enhance` 子命令（CME 路由触发） | 端到端 |
| P4 | 验收（A1~A5）+ 文档固化 | 验收回执 |

## 7. 红线

- ❌ 不做 OA 写操作（本工作流只提供审批建议）。
- ❌ 不伪造数据：无记录/无权限一律显式 skip。
- ❌ 不重造 OA/ONES 自动化（复用 `oa_workflow_ones.py`）。
- ✅ 提交一律隔离临时 index（`GIT_INDEX_FILE`）。

## 7b. 质量信号

- ⚠️ 数据源 BDMS 交付月报为 **202606 月度快照**，非实时，**可能过期**；仅作项目编码线索，
  R1 状态结论以 ONES 实时 + 查询时间戳为准。
- 本设计基于 **886377 在审单据**实测，字段随后续退回可能变化。
- 「概算流程」单据（requestid 885969）当前账号无权限 → R2 只读卡片，显式 skip 留证。

## 8. Rex 拍板（2026-11-18）

1. **落点**：**L4**（Bangcle 专有业务资产）。具体目录 `L4-proprietary/components/bangcle-contract/services/oa/enhance/`
   —— 与既有 `services/oa`（`CubeClient`/`ApprovalLogReader`/`browser_fallback`/OA 会话）同域，最大化复用。
2. **触发方式**：**涉及 Bangcle OA 合同审批流程时触发**，输出**审批建议**（CME 路由调用
   `contractctl oa-enhance --requestid`，与「读单据 / 审批链 / 22 条规则」同链路）；
   独立 CLI 便于按需单跑。⚠️ **不嵌入 `review --oa-billid`**（那是 billid 合同卡片语义，与 757 requestid 不同）。
3. **CME 路由**：757 已在 `contract-manager-expert` 路由表内（§一 第 31 行，只读）。
   **已拍板纳入**（Rex 2026-11-18）：R1/R2 作为该行**固定核查项**，已落地到
   `L4-proprietary/skills/contract-manager-expert/SKILL.md`（§一第 31 行 + §典型串联编排，见 §8b）。

### 8b. CME 路由说明（供 Rex 确认）

**CME = `contract-manager-expert`（component_id `CME-001`，L4 层）**，是 Bangcle「合同管理相关」需求的
**统一入口 skill**。核心机制是 §一「合同管理统一入口路由表（强制）」：

| 用途 | 说明 |
|---|---|
| 意图识别 | 任何 Bangcle 合同管理相关需求，先查路由表定位归属 |
| 核心直处理 | 命中审查/风险/标的参照/OA 拉取/757 流程 → 本技能直接产出结论 |
| 跨资产路由 | 命中审批框架/通用逻辑/Office 流程 → 路由 `contract-approval`(L3)/`contract-management`(L3)/`office-contract`(L4) |
| 边界外分流 | 产品/PPT/项目/收入 → 按 §边界外 提示转对应能力，不越界代办 |

**757 现状**：路由表第 31 行已登记「OA 销售合同审核流程（requestid 单据/审批链/AI 小助手意见，**只读**）」，
但**未含** R1（履约义务核查）/ R2（概算一致性）。

**已落地改法**（一行增强，不新增行；2026-11-18 Rex 同意）：
- 第 31 行「说明」列补：`固定核查：履约义务（ONES 实时）+ 概算一致性（允许超，仅提醒）`
- §典型串联编排表补一行：`OA 销售合同审批（757）审查 → 读单据 → 履约义务(ONES实时) + 概算一致性 → 输出审批建议（只读，写操作人工闸）`

**收益**：CME 作为合同域统一入口，用户在 OA 合同审批场景提需求即自动带上两项核查，无需记忆新命令。
**风险**：无（纯文档增强，不改 CME 代码与其既有边界）。

**执行状态（2026-11-18）**：已改 `L4-proprietary/skills/contract-manager-expert/SKILL.md`
§一 第 31 行说明列 + §典型串联编排新增 757 审批行；CME 代码与边界未动。

【已验证 2026-11-18｜OA 单据 886377 + 概算卡片 9955 只读 + ONES 实时 GraphQL（3440/3068/0328）】架构决策依据。
