# DESIGN-DETAIL — OA 项目实施管理批注建议资产 v1.0（待评审）

> 元信息：Jerry 2026-11-19；L4 CME-001；上游 `PRD-oa-project-management-asset-v1.0.md` /
> `DESIGN-OUTLINE-oa-project-management-asset-v1.0.md`。
> 字段表来源：OA `loadForm.tableInfo.*.fieldinfomap`（权威标签，非推断）。
> 只读：OA / ONES 全链无写调用。

## 1. 落点

```
services/oa/enhance/pm/
├── __init__.py
├── fields.py        # 三流程字段映射（本文件 §3 表）
├── order.py         # xhrs.json/body.txt → ProjectOrder
├── license_period.py# 授权期限提取（修复 D1；纯函数）
├── ones_refs.py     # ONES 参考项目查询 + 状态推断
├── approval_notes.py# 757 异常备注（仅 916；复用 approval_log）
├── risk.py          # 多项目隔离 / 归档 / 追认 / 增购（纯函数）
└── render.py        # 三段式批注（纯函数）
```

改动既有：`oa_workflow_ones.py::license_period` 同步修复（P1，独立上线）。

## 2. 统一模型

```python
@dataclass
class OrderItem:
    keyid: str
    line_category: str      # 产品服务类别（field29773/29770/29767）
    line_type: str          # 类别（29774/29771/29768）
    product_name: str       # 29951/29953/29954
    product_code: str       # 13675/13255/13136
    qty: str
    unit: str               # 13657(标准服务范围)/26903/26932
    amount: str             # 13667 / — / —
    std_price: str          # 26783 / — / —
    discount: str           # 26780 / — / —
    sow: str                # 26781/26905/26934 标准实施内容
    custom: str             # 13666/26904/26933 是否定制

@dataclass
class ProjectOrder:
    request_id: str
    workflow_id: str                 # 916/815/820
    title: str
    applicant: str; dept: str
    final_user: str                  # 29612/29609/29608
    customer: str                    # 13668/12978/13062
    contract_no: str                 # 13652（916）
    contract_name: str               # 13643（916）
    approval_flow_rid: str           # 13682（916 独有；其余 ""）
    project_code: str                # 29561/29560/29562
    estimate_name: str               # 31030/26674/—
    pm_field: str                    # 13673/13220/13102
    service_start: str; service_end: str
    items: List[OrderItem]
    amount: str                      # 13648（916）
    urgency: str
    field_semantics: Dict[str,str]
```

## 3. 字段映射（权威标签，`tableInfo.fieldinfomap`）

| 语义 | 916 | 815 | 820 |
|---|---|---|---|
| 标题 | -1 | -1 | -1 |
| 申请人 | 13637 | 12968 | 13057 |
| 申请时间 | 13638 | 12971 | 13060 |
| 所属部门 | 13639 | 12969 | 13058 |
| 紧急程度 | 29631 | 29630 | 29629 |
| 项目编号 | 29561 | 29560 | 29562 |
| 客户名称 | 13668（浏览框） | 12978 | 13062 |
| 最终客户名称 | 29612（浏览） | 29609 | 29608 |
| 最终客户名称（文本） | 13678 | 32754 | 32752 |
| 合同名称 | 13643 | — | — |
| 合同编号 | 13652 | — | — |
| 合同审批流程→ | **13682** | **无** | **无** |
| 项目经理 | 13673 | 13220 | 13102 |
| 项目管理部区域经理 | — | 13219 | 13101 |
| 销售概算 | 31030 | 26674 | — |
| 服务开始/结束 | 20270/20271 | — | — |
| 签约金额 | 13648 | — | — |
| 预计签约金额 | — | — | 13086 |
| 预计合同签约日期 | — | 12977 | 13085 |
| 明细表 | detail_1 | detail_1 | detail_1 |
| 明细·产品服务类别 | 29773 | 29770 | 29767 |
| 明细·类别 | 29774 | 29771 | 29768 |
| 明细·名称 | 29951 | 29953 | 29954 |
| 明细·编码 | 13675 | 13255 | 13136 |
| 明细·数量 | 13665 | 12984 | 13098 |
| 明细·单位 | 13657 | 26903 | 26932 |
| 明细·金额 | 13667 | — | — |
| 明细·标准价 | 26783 | — | — |
| 明细·折扣率 | 26780 | — | — |
| 明细·标准实施内容 | 26781 | 26905 | 26934 |
| 明细·是否定制 | 13666 | 26904 | 26933 |

**取值规则**：浏览框/选择型优先 `specialobj[0].name`，否则 `value`（复用 `oa_form._value` 同款语义，复制实现，避免跨包依赖）。
**明细多表**：按 `tableInfo` 的 `detail_1` 取（三流程均只有 detail_1 有效；`detail_2/3` 为空白模板）。

## 4. 授权期限提取（D1 修复，`license_period.py`）

```python
_NUM = r"(\d{4})\s*(?:年|[-./])\s*(\d{1,2})\s*(?:月|[-./])\s*(\d{1,2})\s*(?:日|号)?"
_RANGE = re.compile(_NUM + r"\s*(?:至|到|~|—|–|-)\s*" + _NUM)

def extract_license_period(tasks) -> Optional[tuple[str, str, str]]:
    """从【云端】license/授权/续期任务 descriptionText 取授权区间。
    返回 (start, end, 证据任务号)；多任务取结束日最晚者；无则 None。
    """
```

- 覆盖：`2026年8月11日`、`2026年11月18号`、`2026-08-11`、`2026.8.11`。
- 分隔符：`至 / 到 / ~ / — / – / -`。
- 输出规范化 `YYYY-MM-DD`；证据 = 任务号。
- **D1 回归**：SSXM-2026-0810-2066 → `2026-08-14 ~ 2027-08-14`（#385446 最晚）；
  SSXM-2026-0624-1641 → `2026-11-18 ~ 2026-11-30`（#399765）。

## 5. ONES 参考项目（`ones_refs.py`）

```python
def find_reference_projects(final_user, customer, product_codes, project_code="") -> list[RefProject]
@dataclass
class RefProject:
    code: str; name: str; project_status: str
    status_label: str           # 已交付已验收/可结项/已交付未验收/已交付未关联签约合同/进行中/待实施
    status_basis: str           # 推断依据（ob 状态集 + 项目状态）
    license_period: str         # 授权至（或【缺失】）
    license_task: str
    obligation_states: list[str]
    matched_products: list[str] # 与本单产品编码/名称命中
```

匹配顺序：
1. 若 OA 有 `project_code`（SSXM-*）→ 直查；
2. 否则 `projects(filter:{name_match: final_user})` 精确包含 → 候选（标注「候选，需人工确认本期」）；
3. 若 `final_user` 无命中 → 用 `customer` 再试；无 → `missing` 记录，不伪造。

### 5.1 状态推断规则表（D4）

| 条件 | status_label |
|---|---|
| 项目状态=验收完成 或 ob 含`验收文件已归档` | 已交付已验收 |
| 项目名含「提前实施」且 ob 含`交付邮件已归档` | 已交付未关联签约合同 |
| 项目状态=已完成 且 ob 含`交付邮件已归档` | 可结项 |
| ob 含`验收文件交接中` 或 `交付邮件已归档` | 已交付未验收 |
| ob 含`实施未开始` | 待实施 |
| 其余 | 进行中（依据：项目状态 X） |

输出必须带 `status_basis`；无法推断标 `【待人工确认】`。

## 6. 757 异常备注（`approval_notes.py`，仅 916）

```python
def collect_approval_notes(approval_rid: str, reader: ApprovalLogReader) -> ApprovalNotes
@dataclass
class ApprovalNotes:
    request_id: str; workflow_id: str
    ai_summary: str        # AI小助手「销售合同审核意见」正文（去标签）
    risk_levels: list[str] # 【重点复核】/【需补充】/【可接受】…
    abnomal_opinions: list[str]  # 任立民/评审小组等人工异常意见
    verdict_hint: str      # 总体建议
    degraded: Optional[str] # 无权限/无数据时填原因
```

- 复用 `approval_log.ApprovalLogReader.read_approval_chain(rid)`；
- `ApprovalLogUnavailable` / `ReqNoRight` → `degraded="无权限，需人工查看"`，**不阻断**；
- 提取：`AI小助手` 批注正文 + 所有 `operationname∈{退回,批注}` 且意见非「无异议/同意」的记录；
- 风险等级 = 正文中 `【…】` 标记集合。

## 7. 风险判定（`risk.py`，纯函数）

```python
def assess(order: ProjectOrder, refs: list[RefProject], notes: ApprovalNotes|None) -> list[Risk]
@dataclass
class Risk: code: str; text: str; level: str   # level: 必注/提示
```

| code | 触发 | 文本模板 |
|---|---|---|
| `multi_project_same_product` | 同最终用户+同产品/服务存在 ≥2 项目 | 不允许同最终用户同产品/服务存在多个未关联签约合同的{流程}项目；请责任销售明确本申请与已有项目的区别（如增购等） |
| `archive_date` | 815/916 有合同归档时间字段且为空 | 立项前，请与营销侧明确合同预计归档日期 |
| `retroactive` | 815 且「本项目目前状态」=已中标/已交付 | 是否追认提前实施交付内容 |
| `approval_risk` | notes 含【重点复核】/【需补充】 | 合同审批流程存在异常备注：{等级} {摘要} |
| `approval_no_permission` | notes.degraded | 合同审批流程无权限读取，需人工查看（链接见单据） |
| `pm_unassigned` | order.pm_field 为空 | 待分配项目经理 |

## 8. 渲染（`render.py`，纯函数）

```python
def render_remark(order, refs, risks, pm, *, date_text="") -> str
```

输出（与 Rex 批注同构）：

```
请<pm>负责，参考{项目类型}：
[单行] <编号>（<状态>，授权/维保至<YY.MM>）。
[列表]  1. <编号>（<状态>，<授权说明>）。
        2. <编号>（<状态>）。
注：<risk.text；多条换行；无则省略>
```

- 日期格式：`end` 为 `2027-08-14` → `27.08`；若同年截止跨年（如 26.11.30）保留 `YY.MM.DD`。
- 无参考项目 → 首段写「ONES 未匹配到{最终用户}相关项目，请人工确认本期项目编号」。
- `pm` 为空 → 首段「请<待分配>安排项目经理，参考：…」。
- 纯函数：不触网、不读时钟（`date_text` 注入）。

## 9. 错误与降级模型

| 场景 | 行为 |
|---|---|
| raw 缺失 / 结构异常 | `PmAssetError`（fail-closed，不伪造） |
| 757 无权限 | `degraded` 标注，整体继续 |
| ONES 查不到项目 | `missing` + 输出「请人工确认」，不阻断 |
| 授权期限无证据 | 【缺失】，不用服务期替代 |
| 字段无标签 | `field_semantics` 记录 field id，标 inferred |

## 10. 测试方案

| 用例 | 输入 | 期望 |
|---|---|---|
| T1 | 中文日期（2026年8月11日 至 2027年8月11日） | `2026-08-11 ~ 2027-08-11` |
| T2 | `2026年11月18号至2026年11月30号` | 正确 |
| T3 | ISO `2026-08-11 ~ 2027-08-11` | 回归不破 |
| T4 | 886453 参考项目 5 个 | 5/5 提取授权期限 |
| T5 | 886404 双参考 + 多项目 | 输出 `multi_project_same_product` |
| T6 | 885637（无权限） | `degraded`，不抛错 |
| T7 | 886362/886368/886314 回放 | 三段式同构 Rex 批注 |
| T8 | 886453 全链 | 输出含 757 链接 rid + 风险 |

单测离线（纯函数 + 夹具）；E2E 只读 OA/ONES 真实 HTTP。

## 11. CLI

```
contractctl oa-project-mgmt --requestid <rid> [--pm <名>] [--raw-dir <dir>] [--out <md>]
contractctl oa-project-mgmt --discover
```
