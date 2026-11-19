# DESIGN-OUTLINE — OA 项目实施管理批注建议资产 v1.0（待评审）

> 元信息：Jerry 2026-11-19；归属 L4 CME-001；上游 PRD：`PRD-oa-project-management-asset-v1.0.md`。
> 口径基准：KB `EXP-20261112-001`；OA 只读、ONES 只读。

## 1. 架构定位

纯增量，挂在既有 `services/oa/enhance/` 下，**不改动** `oa-approval`（757 链）。

```
L4-proprietary/components/bangcle-contract/
├── services/oa/enhance/pm/            # 新增包
│   ├── fields.py       # 三流程字段映射表（916/815/820 各自 field id）
│   ├── order.py        # 统一单模型（ProjectOrder dataclass）
│   ├── ones_refs.py    # ONES 参考项目查询 + 状态/授权期限推断
│   ├── license_period.py  # 授权期限提取（修复 D1，独立纯函数）
│   ├── approval_notes.py  # 757 异常备注提取（复用 approval_log）
│   ├── risk.py         # 多项目隔离/归档/追认/增购 判定（纯函数）
│   └── render.py       # 三段式批注渲染（纯函数）
├── cli/contractctl.py  # 新增子命令 oa-project-mgmt
└── tests/unit/test_pm_asset.py
```

`L4-proprietary/skills/ones-browser-export/scripts/oa_workflow_ones.py`
→ 只做最小修复（授权日期正则）并补 `project_status`/状态推断辅助；不动捕获/ONES 自动化主体。

## 2. 模块契约（摘要）

| 模块 | 输入 | 输出 | 网络 |
|---|---|---|---|
| `fields.py` | workflowid | 字段映射 dict | 无 |
| `order.py` | raw `xhrs.json`/`body.txt` | `ProjectOrder`（统一字段） | 无 |
| `ones_refs.py` | 最终用户/客户/产品编码 | 参考项目列表（编号/状态/授权/依据） | ONES 只读 |
| `license_period.py` | 任务描述文本 | `(起, 止, 证据号)` 或 `None` | 无 |
| `approval_notes.py` | 916 单 `field13682` → 757 rid | 异常备注 + 风险等级 或 `【无权限】` | OA 只读 |
| `risk.py` | order + 参考项目集 | 风险注文本 + 触发码 | 无 |
| `render.py` | order + refs + risks + PM | 三段式文本 | 无 |

## 3. 关键设计决策

1. **字段映射按流程分表**（D2）：916/815/820 明细字段集互不相同，禁止共用硬编码 field id。
2. **授权期限提取独立纯函数**（D1 修复）：支持 `YYYY年M月D日`、`YYYY年M月D号`、ISO、`YYYY.MM.DD`；分隔符 `至/到/-/~/—`；取**最晚结束日**（同一项目多 license 任务）。
3. **状态推断规则表**（D4）：`验收文件已归档`∈履约义务状态集 或 项目状态=验收完成 → `已交付已验收`；项目状态=已完成 且含「交付邮件已归档」→ `可结项`；含「验收文件交接中」→ `已交付未验收`；提前实施项目无签约合同 → `已交付未关联签约合同`。推断依据随输出展示，不直抄枚举。
4. **757 备注按单降级**（D3）：`approval_log.read_approval_chain` 抛 `ApprovalLogUnavailable` → 标 `【无权限/无数据，需人工查看】`，不阻断整体输出。
5. **只读铁律**：全链无 OA 写调用；与 `oa-approval` 同口径。
6. **渲染为纯函数**：无网络、无时钟依赖（日期由入参注入），保证单测可离线重放。

## 4. 数据模型（统一单）

```python
@dataclass
class ProjectOrder:
    request_id: str
    workflow_id: str          # 916/815/820
    title: str
    final_user: str           # 最终客户
    customer: str             # 客户名称（916 为签约客户）
    contract_no: str
    contract_name: str
    approval_flow_rid: str    # 916 独有（field13682）；其余为 ""
    project_code: str         # OA 项目编号（可空）
    items: List[OrderItem]    # 分项：产品线/类别/名称/编码/数量/金额/标准价/折扣/内容
    amount: Decimal
    service_start: str
    service_end: str
```

## 5. CLI

```
contractctl oa-project-mgmt --requestid <rid> [--pm <名>] [--out <md>]
contractctl oa-project-mgmt --discover            # 列当前待办（复用 oa_todo_dist）
```

输出：Markdown 建议稿（三段式正文 + 依据表 + ⚠️ 降级项）。

## 6. 分阶段（对应 IMPLEMENTATION-PLAN）

| Phase | 内容 | 出口 |
|---|---|---|
| P1 | `license_period` 修复 + 单测（D1，独立可上线） | 5/5 中文日期通过 |
| P2 | `fields`/`order` 三流程解析 | 4 单回放字段全对 |
| P3 | `ones_refs` + `risk` + `render` | 三段式输出同构 Rex 批注 |
| P4 | `approval_notes`（757 异常备注） | 无权限降级验证 |
| P5 | CLI + E2E 只读实测 | AC1~AC8 全绿 |

## 7. 边界与非目标

- 不写 OA、不代审批、不自动派 PM
- 合同原文审查仍走 `oa-approval`
- 数据源不可用标 ⚠️，无来源标【缺失】
