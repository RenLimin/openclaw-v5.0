# DESIGN-DETAIL — OA 销售合同审批：触发 + 编排 + 标准审批备注 v1.0（待评审）

> 元信息：本文档由 Jerry 于 2026-11-19 生成；应答契约版本 ADR-035 P1 v1.2 / P2 contract-answer-spec；归属 Bangcle 合同管理域（L4 CME-001）；数据基准 2026-11-19。
>
> 【已验证 2026-11-19｜oa_todo_dist.py 实跑 + 单据 886377 raw 只读】本设计所有结论均可复现。

## 0. 溯源链

```
数据源 A：services/oa/enhance/{runner,verdict,oa_form,estimate,ones_obigation}.py
   → 结论：§1 既有接口；§3 数据模型
数据源 B：cli/contractctl.py（cmd_oa_enhance / 子命令注册）
   → 结论：§5 CLI 集成形态
数据源 C：tmp/oa-pif/raw/886377/{xhrs.json,body.txt} + 2026-11-19 待办实跑
   → 结论：§3.1 字段映射；§6 边界
```

## 1. 目标与范围

给 757「销售合同审核流程」新增**触发 + 编排 + 标准备注**三层（纯增量）：
发现待办 → 捕获单据 → R1/R2 → 固定核查 → 标准备注。**不改动** `oa-enhance`/`review`。

## 2. 落点与目录

```
L4-proprietary/components/bangcle-contract/
├── services/oa/enhance/
│   ├── todo.py            # 新增：757 待办发现
│   ├── checks.py          # 新增：固定核查项（L1 表单 / L2 原文）
│   ├── remark.py          # 新增：标准审批备注渲染（纯函数）
│   └── orchestrator.py    # 新增：一条链编排
├── cli/contractctl.py     # 新增子命令 oa-approval
└── tests/unit/test_oa_approval.py   # 新增：真实数据测试

L4-proprietary/skills/contract-manager-expert/SKILL.md   # 触发词 + 编排
```

## 3. 数据模型

### 3.1 待办项（todo.py）

```python
@dataclass
class TodoItem:
    request_id: str
    request_name: str
    workflow_id: str
    create_date: str
    status: str
    applicant: str = ""      # 从 request_name 解析（命名=流程名-申请人-日期）
```

### 3.2 固定核查项（checks.py）

```python
@dataclass
class CheckResult:
    check_id: str      # "contract_no_missing" / "service_period" / "party_a_email" / "end_user_table" / "version_desc"
    level: str         # "block" | "warn" | "pass" | "manual"
    message: str
    evidence: str      # 就近原文/字段值
    source: str        # "form" | "contract_text" | "none"
```

判定规则：

| check_id | 层级 | 规则 | 缺失/不适用 |
|---|---|---|---|
| `contract_no_missing` | L1 | `body.txt`「合同编号！」后为空 | 判 **block** |
| `service_period` | L1 | 服务起止日期有值→pass；仅「签订之日起N年」→warn | 无日期→warn |
| `party_a_email` | L2 | 合同原文「甲方指定授权__邮箱」留空→block；有值→pass | 无原文→**manual** |
| `end_user_table` | L2 | 原文 11.6 声明附件且正文含「最终用户信息表」→pass；声明但未随附→block | 无原文→**manual** |
| `version_desc` | L2 | 分项「标准服务内容」版本 vs 原文「许可版/增强版」不一致→warn | 无原文→**manual** |

### 3.3 审批备注（remark.py）

```python
def render_remark(form, checks, r1, r2, degraded) -> str
```

输出（与 PRD §N4 一致）：
```
【审批建议】<退回补充 / 同意 / 退回补充（待原文）>
合同：<名称>（<rid>，<金额> 元，<客户>）
退回项（需关闭后重提）：
1. ...
提示项（不阻断）：
1. ...
R1 履约义务：<判定>（ONES 实时 <日期>）
R2 概算一致性：<判定>
（降级时）⚠️ 数据源…可能过期
```

结论推导：`block` 存在 → 退回补充；否则 `manual` 存在 → 退回补充（待原文）；否则 → 同意。

## 4. 接口契约

### 4.1 `todo.discover_todos(workflow_id="757") -> List[TodoItem]`

- 复用 `oa_todo_dist` 同款 Playwright（`table/datas` 全量分页 + `dataKey` 捕获）。
- 会话失效 → 抛 `OaSessionExpired`，由 orchestrator 提示 `refresh_oa_session()`。
- 0 条 → 返回 `[]`（不报错）。

### 4.2 `checks.run_fixed_checks(form, body_text, contract_text=None) -> List[CheckResult]`

- 纯函数 + 本地文件；无网络。
- `contract_text` 为 None 时 L2 三项一律 `manual`。

### 4.3 `orchestrator.run_approval(...) -> dict`

```python
{
  "todos": [TodoItem...],
  "results": [
    {"request_id", "form", "checks", "r1", "r2", "remark", "degraded": [...]}
  ],
  "summary": {"total", "block", "warn", "manual", "pass"},
  "out_dir": "..."
}
```

## 5. CLI 集成

```
contractctl oa-approval [--contract-no <编号>] [--raw-dir <dir>]
                       [--contract-file <docx/txt>] [--out-dir <dir>]
                       [--no-discover]
```

- 默认：`discover_todos("757")` → 逐张处理。
- `--contract-no`：走 `ledger.fetch_contract_by_no` 定位 billid → `oa-fetch` 取原文（可选增强）。
- 输出：`tmp/oa-approval-<rid>/remark-<rid>.md` + 汇总 stdout。
- **只读**：不调用任何 OA 写接口。

## 6. 错误处理与降级

| 场景 | 行为 |
|---|---|
| OA 会话过期 | `OaSessionExpired` → 提示 `refresh_oa_session(timeout=90)`，不静默 |
| 单据捕获失败 | 该张标 `degraded`，继续下一张 |
| R1/R2 降级 | 备注标注，不误报「同意」 |
| 合同原文未提供 | L2 三项 `manual`，结论「退回补充（待原文）」 |
| 0 条待办 | 输出「无待办」 |

## 7. 测试方案

`tests/unit/test_oa_approval.py`（真实数据，禁 mock）：

| 用例 | 数据 | 断言 |
|---|---|---|
| 待办发现 | 真实 OA（会话有效） | 返回列表（可为空），字段完整 |
| 固定核查 L1 | `tmp/oa-pif/raw/886377/body.txt` | `contract_no_missing`=block；`service_period`=warn |
| 固定核查 L2 无原文 | 同上，`contract_text=None` | 三项 `manual` |
| 固定核查 L2 有原文 | `tmp/oa-757/886377/contract.txt` | `party_a_email`=block；`end_user_table`=block |
| 备注渲染 | 合成 form/checks/r1/r2 | 格式与草案一致；block→退回补充 |
| 端到端 | 886377 全链 | 备注文件落盘，含 R1/R2 |

依赖缺失（无 raw / 会话失效）→ `pytest.skip` 留证，不伪 pass。

## 8. 验收标准（对应 PRD B1~B5）

| # | 标准 | 验证 |
|---|---|---|
| B1 | 触发词命中 CME 路由 | SKILL 路由表实读 |
| B2 | 886377 标准备注 | 端到端跑通，格式一致 |
| B3 | 无原文 L2 转人工 | 断言 `manual` |
| B4 | 降级不误报 | 注入 skip 验证 |
| B5 | 全量单测通过 | `pytest tests/unit` |

## 9. Phase 拆分

| Phase | 内容 |
|---|---|
| P1 | `todo.py` + `checks.py` + 单测 |
| P2 | `remark.py` + `orchestrator.py` + CLI + 端到端 |
| P3 | SKILL 触发词 + 文档 + 门禁回归 |

## 10. 红线

- 全程只读；OA 写操作人工闸。
- 无原文不伪造 L2 判定。
- 既有 `oa-enhance`/`review` 零破坏。
- 提交用隔离 index。

## 质量信号

- 备注结论绑定 requestid + 读取时间。
- ⚠️ OA 在审单据字段会随后续退回变化（数据源为查询时点快照，可能过期）。
- ⚠️ 合同原文为必要输入（L2 层），无原文时显式转人工。
