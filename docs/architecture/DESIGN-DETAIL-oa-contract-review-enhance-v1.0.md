# DESIGN-DETAIL — OA 销售合同审查增强 v1.0（待评审）

> 元信息：本文档由 Jerry 于 2026-11-18 生成；应答契约版本 ADR-035 P1 v1.2 / P2 contract-answer-spec；归属 Bangcle 合同管理域（L4 CME-001）；数据基准 2026-11-18。
>
> 上游：`PRD-oa-contract-review-enhance-v1.0.md`、`DESIGN-OUTLINE-oa-contract-review-enhance-v1.0.md`。
> 本文件定**接口契约 + 数据模型 + 技术方案**；Rex 拍板项见 OUTLINE §8。

## 0. 溯源链

```
PRD（R1 履约义务 / R2 概算一致性）
  → OUTLINE（目标架构 + 落点 L4 + 模块划分）
  → 本文件（接口契约 + 数据模型 + 技术方案）
证据：OA 单据 886377 原始 XHR（tmp/oa-pif/raw/886377/xhrs.json）
      + 概算卡片 9955 原始 XHR（tmp/oa-757/9955/xhrs.json）
      + ONES GraphQL 实测（SSXM-2025-1111-3440 / -1015-3068 / -0203-0328）
```

## 1. 目标与范围

给 OA 757「销售合同审核流程」的**只读审查**增加两项核查，输出**审批建议**：

| 编号 | 核查 | 主数据源 | 判定 |
|---|---|---|---|
| R1 | 客户/最终用户**履约义务**状态 | **ONES 实时**（GraphQL） | 正常 / 提示 / 异常 |
| R2 | **概算一致性**（明细/单价） | OA Cube 卡片（只读） | 一致 / 超概算（**提醒级**）/ 缺项 |

**不做**：任何 OA/ONES/BDMS 写操作；不重造 OA 自动化。

## 2. 落点与目录

**落点**：`L4-proprietary/components/bangcle-contract/services/oa/enhance/`（L4 专有资产，与 `services/oa` 同域）。

```
services/oa/enhance/
  ├─ __init__.py
  ├─ oa_form.py        OA 单据解析：requestid → 主字段 + 分项明细 + 概算 billid
  ├─ ones_obigation.py R1：ONES 实时履约义务核查（复用 oa_workflow_ones 的 GraphQL）
  ├─ estimate.py       R2：概算卡片读取 + 逐项比对（复用 CubeClient/storage_state）
  ├─ verdict.py        判定与渲染：结构化结果 → Markdown 片段
  └─ runner.py         编排：读单据 → R1 → R2 → 合并片段
scripts/
  └─ oa_enhance.py     CLI 入口（薄封装 runner；供 contractctl 子命令调用）
```

**复用边界**（不新写）：
- `services/oa/cube.py`（`CubeClient` / `_lenient_json_loads` / `ContractData`）
- `services/oa/browser_fallback.py`（`refresh_oa_session` / `heal_session`）
- `services/oa/helpers.py`（`extract_main_fields` / `extract_attachment_refs`）
- `ones-browser-export/scripts/oa_workflow_ones.py`（`project_by_code` / `project_tasks` / `gql` / `capture`）

## 3. 数据模型

### 3.1 本单分项（OA 单据 → R2 输入）

来源：OA `detailData` 响应的 `detail_1.rowDatas.row_*`（实测 886377 = 3 行）。

```python
@dataclass
class OrderItem:
    keyid: str            # row keyid（32118/32119/32120）
    product_code: str     # field10644 产品服务编码（SP-AAP-7.0-SAPLV-PLUS …）
    product_name: str     # field29757 产品名称
    amount: Decimal       # field10451 本单金额（20000.00 / 24000.00）
    std_price: Decimal    # field26701 标准价（130000.00）
    discount: Decimal     # field26698 折扣（15.38 / 18.46）
    qty: Decimal          # field10655 数量（1）
    estimate_billid: str  # field32828 概算卡片 billid（9955）
```

### 3.2 概算分项（Cube 卡片 → R2 比对）

来源：Cube `getDetailFields` 响应 `datas[]`（实测 9955 = 3 行，与本单 3 行一一对应）。

```python
@dataclass
class EstimateItem:
    dtl_id: str           # dtl_id（28316/28317/…）
    product_code: str     # field26645 产品服务编码
    product_name: str     # field29781 产品名称
    est_amount: Decimal   # field26658 预计签约价格（20000.00）
    std_price: Decimal    # field26656 标准价（130000.00）
    discount: Decimal     # field26628 折扣（15.38）
    qty: Decimal          # field26655 数量（100.00）
```

> **字段语义确认**：9955 实测 3 行 `field26658` 均 = 20000.00，与「概算预签约价」语义一致；
> 标签缺失时按 `layoutBase.fieldname`（`yjqyjgy` 等）映射兜底，并在输出标注 `field_semantics: inferred`。

### 3.3 履约义务（ONES → R1 输出）

```python
@dataclass
class ObligationRecord:
    project_code: str     # SSXM-2025-1111-3440
    project_name: str
    project_status: str   # ONES 项目状态（进行中/已完成）
    task_number: str      # 337026
    task_name: str        # license 授权 / 子验收 / 交付 …
    status: str           # ★实时状态（已完成/交付邮件已归档/客户确认版验收单/实施未开始…）
    owner: str
```

### 3.4 顶层结果

```python
@dataclass
class EnhanceResult:
    request_id: str
    r1: R1Result   # {records, verdict, queried_at, projects, missing, notes}
    r2: R2Result   # {rows:[{code, name, est, actual, diff, verdict}], total, verdict, billid}
    generated_at: str
```

## 4. 接口契约

### 4.1 R1 `ones_obigation.py`

```python
def check_obligations(
    *, end_user: str, customer: str = "",
    product_codes: Sequence[str] = (),
    project_codes: Sequence[str] = (),      # 已知时直查；否则由 end_user 经 BDMS 线索定位
    raw_dir: Path | None = None,
) -> R1Result: ...
```

**流程**：
1. `project_codes` 为空 → 用 BDMS `dr_sheet_row`（202606，`mode=ro`）按最终用户/客户名定位 `SSXM-*` 项目编码（**仅定位，不取状态**）。
2. 对每个 `SSXM`：`oa_workflow_ones.project_by_code()` → `project_tasks()` → 过滤 `issueType.name == "项目履约义务"`。
3. 汇总实时 `status.name` + 项目状态；按 §4.3 判定。
4. `queried_at` 记录查询时刻；无权限/无记录 → `missing` 显式留证，不伪造。

**判定**：
| 实时状态 | 判定 |
|---|---|
| `已完成` / `交付邮件已归档` / `客户确认版验收单` / `验收文件已归档` | 正常 |
| `实施未开始` / `义务已拆分`（项目整体未完成） | 提示 |
| `应交未交` / `交付异常` / `应验未验` / `验收异常` / `应结未结` | 异常 |

### 4.2 R2 `estimate.py`

```python
def check_estimate(
    *, billid: str, items: Sequence[OrderItem],
    storage_state: Path | None = None,
) -> R2Result: ...
```

**流程**：
1. 复用 `CubeClient`（`storage_state`）读卡片；优先解析 `getDetailFields` 结构化数据。
2. 按 `product_code` 与 `OrderItem` 逐项匹配（缺失降级按名称并标注）。
3. 计算 `diff = actual - est`。
4. **口径（Rex 拍板）**：`diff > 0` → **超概算，仅提醒**（verdict=`over_budget_warn`），**不构成退回项**；
   `diff ≤ 0` → 一致；编码无匹配 → 缺项（`missing`）。

### 4.3 判定聚合（runner）

```python
def run(request_id: str, out_dir: Path, *, storage_state=None) -> EnhanceResult:
    # 1) oa_form.parse(request_id) → 主字段 + items + estimate_billid
    # 2) ones_obigation.check_obligations(end_user=..., items=items)
    # 3) estimate.check_estimate(billid=estimate_billid, items=items)
    # 4) verdict.render_r1/r2 → Markdown 片段
```

## 5. CLI 集成

**新增子命令** `contractctl oa-enhance`（独立按需跑）+ **嵌入** `contractctl review --oa-billid` 报告尾部（涉 OA 合同审批时自动触发）：

```bash
# 独立
python3 cli/contractctl.py --out-dir <dir> oa-enhance --requestid 886377
# 嵌入（review 报告追加「增强核查」章节）
python3 cli/contractctl.py --out-dir <dir> review --oa-billid <billid>
```

**报告结构**（`report.py` 增量，不改既有 22 条）：

```
## 增强核查（履约义务 / 概算一致性）
### R1 履约义务（ONES 实时）  【已验证 2026-11-18｜ONES GraphQL】
### R2 概算一致性             【已验证 2026-11-18｜OA 卡片 9955 只读】
```

## 6. 错误处理与降级

| 场景 | 处理 |
|---|---|
| OA 会话失效 | `browser_fallback.refresh_oa_session(timeout=90)` 自愈；失败 → `missing: session_expired` |
| 卡片无权限（如 885969） | 显式 `skipped: no_permission`，不伪造 |
| ONES 查不到项目 | `missing: project_not_found`（不阻断 R2） |
| BDMS 定位失败 | 允许 `--project-codes` 手工兜底；否则 R1 `missing` |
| 字段标签缺失 | 按 `fieldname` 映射 + 输出标注 `inferred` |
| 任一步失败 | 该步降级，不中断整体；报告标注降级项 |

## 7. 测试方案

| 用例 | 输入 | 期望 |
|---|---|---|
| TC-R1-01 | 真实 886377（end_user=海通恒信） | 3440 续购正常；3068 提示；无异常 |
| TC-R1-02 | 不存在的 end_user | `missing`，不崩 |
| TC-R2-01 | 真实 9955 + 886377 分项 | AndroidSDK diff=+4000 → `over_budget_warn` |
| TC-R2-02 | 无权限 billid | `skipped: no_permission` |
| TC-E2E-01 | `oa-enhance --requestid 886377` | 端到端出报告，门禁 PASS |
| 黄金基准 | 真实数据回归 | 输出可复现，字段/判定稳定 |

**禁止 mock**；无权限/无记录一律 skip 留证。

## 8. 验收标准（对应 PRD A1~A5）

| 编号 | 判据 |
|---|---|
| A1 | R1 对 886377 输出 3440 正常 / 3068 提示；**ONES 实时**可复现 |
| A2 | R2 对 886377 输出 AndroidSDK +4000 → `over_budget_warn`（提醒级，不退回） |
| A3 | 无权限单据显式 skip；不伪造 |
| A4 | 报告含 `## 增强核查` 章节 + 溯源/时间戳，门禁 PASS |
| A5 | 提交隔离 index；无 OA 写操作 |

## 9. Phase 拆分

| Phase | 内容 | 产出 |
|---|---|---|
| P1 | `oa_form.py` + `ones_obigation.py`（TC-R1-01/02） | R1 可复现 |
| P2 | `estimate.py`（TC-R2-01/02） | R2 可复现 |
| P3 | `verdict.py` + `runner.py` + CLI（TC-E2E-01） | 端到端 |
| P4 | 验收 A1~A5 + 文档固化 | 验收回执 |

## 10. 红线

- ❌ 不做 OA/ONES/BDMS 写操作；写操作一律人工闸。
- ❌ 不伪造：无记录/无权限显式 skip 留证。
- ❌ 不重造 OA/ONES 自动化（复用 `oa_workflow_ones.py` / `CubeClient`）。
- ✅ 提交一律隔离临时 index（`GIT_INDEX_FILE`）。
- ✅ 报告遵循 ADR-035 应答契约（含溯源链 + 时间戳 + 降级标注）。

## 质量信号

- ⚠️ 数据源 BDMS 交付月报为 **202606 月度快照**，非实时，**可能过期**；仅用于 R1 项目编码定位。
- ⚠️ ONES 状态为**查询时点**实时值，须带 `queried_at`；报告非实时快照。
- ⚠️ 概算卡片 9955 为**只读**读取，字段标签经实测值推断（`field26658` 等），缺失处标注 `inferred`。

【已验证 2026-11-18｜OA 单据 886377 原始 XHR + 概算卡片 9955 原始 XHR + ONES 实时 GraphQL】技术方案依据。
