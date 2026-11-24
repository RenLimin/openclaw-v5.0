# DESIGN-DETAIL — OA 项目实施管理批注建议资产 v1.3（916 专项整改）

> 元信息：Jerry 2026-11-24；上游 `PRD-oa-project-management-asset-v1.0.md` §0.2d（v1.3 口径）。
> **适用范围：仅 `wf_916` 销售合同下单**；815/820 维持 v1.2 实现不变。
> 只读：OA / ONES 全链无写调用。

## 1. 背景与实测依据

Rex 2026-11-24 手工处理完现有 4 单 916 后给出 4 条整改（见 PRD §0.2d C8–C11）。

| 事实 | 证据 |
|---|---|
| 项目名不含客户名 → 旧路径漏配 | 887726（最终用户=黄河财产保险）：`projects(name_match:"黄河财产保险")`=**0**；但义务检索得 SSXM-2026-1102-2963（义务名含「黄河财产保险」，项目名为「中科信控…POC」） |
| 同一客户项目分散在多个项目 | 887728（武汉丰泰）：义务分布在 2087/2173/2227/2462 四个项目，另有本客户 POC 3074 |
| ONES 有组织架构接口 | `users(filter:{name_match}) { name departments{name} }` → 35 个部门；张燕兰/徐亚东/冯刚=南区客户服务部；程涛=大客户服务部；潘天功/刘朋雨/申朋朋=交付技术部 |
| 履约义务「项目状态」=结项标记 | `_Gvi8gt9w{value}` = `已归档` → 已结项（沿用 v1.1 C2） |

## 2. 落点与改动面

```
services/oa/enhance/
├── ones_client.py   # +departments_of()  +search_obligations()（复用权威脚本 gql，不重写自动化）
├── pm/ones_refs.py  # +RefProject.match_level/closed  +find_reference_projects_v13()
├── pm/render.py     # _pm_lead 增 C11 分支（916：ONES 组织架构 → 冯刚/PM 本人）
├── pm/risk.py       # 916 不出 multi_project_same_product（该校准自 815）
└── cli/contractctl.py # cmd_oa_project_mgmt：916 走 v13 链 + 组织架构查部门
```

**不新建组件**；全部为既有 PM 资产的增量口径（沿用 registry 条目 `bangcle-contract`）。

## 3. v1.3 算法（916）

### 3.1 检索（C8）

```
probes = _search_tokens(final_user, customer)      # 复用 v1.2 C7 长词优先序列
for key in probes:
    obs = ones_client.search_obligations(key)      # tasks(filter:{name_match}) 跨项目
    for ob in obs where issueType==项目履约义务:
        项目名含任一 probe 或 义务名含任一 probe → 候选项目（去重 by SSXM 编号）
另：OA project_code 作为 direct 候选（同池）
```

每个候选项目经 `_build()` 拉全量任务 → 状态推断 / 授权期限 / PM（复用 v1.2）。

### 3.2 匹配层级（C9）

| 层级 | 条件 | 标注 |
|---|---|---|
| `product` | 本单产品编码/名称/类别命中该项目履约义务名（`_matched`） | 主参考 |
| `customer_only` | 仅客户/最终用户名一致，无产品命中 | 备注**「同客户项目」** |

### 3.3 排序（C10，**不截断**）

```
(匹配层级 product<customer_only) → (未结项<已结项) → 类型(签约<提前实施<POC)
→ 状态rank → 命中产品数降序 → 编号
```

「同期新建排除」「同类型取 1」在 v1.3 降级为排序键（列全部相关项，人工取舍）。

### 3.4 指派（C11）

```
primary_pm = refs[0].pm（缺失则 OA PM 字段，再缺 → 冯刚）
depts = ones_client.departments_of(primary_pm)      # ONES 配置中心-组织架构
if "南区客户服务部" in depts → 请冯刚安排项目经理
else                         → 请<primary_pm>负责
若 depts 为空（ONES 未收录）→ 按非南区处理并在报告标注「待人工确认」（不伪造部门）

**PM 取值口径（沿用 v1.2 C4，不改）**：参考项目 PM = `ones_client.project_pm(uuid)`
（履约义务任务优先，取 `assign`/`owner` 出现次数最多者，并列取字典序）。
实测 2087 存在多负责人（assign：潘天功×4、胡李鑫×3、李韶倬×1…），按此口径取潘天功。
该口径已由 Rex v1.2 校准（2874→徐亚东、2863→潘天功、0613→张燕兰、0844→刘瑞营 4/4 命中），
v1.3 不得另立口径，否则破坏回归。
```

### 3.5 渲染差异

- 混合类型 → 列表式（复用 v1.2 能力）；各项仍带 `，项目经理：X`（v1.2 C4）。
- `customer_only` 项在 Markdown 依据表加「同客户项目」标注（批注正文保持简洁，不塞噪声）。
- 风险注沿用 v1.2（757 / 归档日期）；**去掉 916 的多项目隔离注**。

## 4. 验收标准

| AC | 标准 |
|---|---|
| AC-1 | 887726 回放：引 SSXM-2026-1102-2963（黄河财险，旧路径为 0 匹配） |
| AC-2 | 887728 回放：聚合 ≥4 个项目（2087/2173/2227/2462 + 3074），均标 PM 胡李鑫 |
| AC-3 | 887726 首段=「请冯刚安排项目经理」（张燕兰∈南区客户服务部） |
| AC-4 | 887728 首段=「请潘天功负责」（refs[0]=2087，PM 取 v1.2 `project_pm` 口径=潘天功，"
│      │ 属交付技术部 → 非南区）。⚠️ PM 口径说明：`project_pm` 按 assign/owner 出现次数最多者取
│      │ （2087 实测 assign 计数：潘天功×4 > 胡李鑫×3）；沿用 v1.2 C4 已校准口径，不改。 |
| AC-5 | 815/820 回归：v1.2 输出不变（测试全绿） |
| AC-6 | 916 输出无 multi_project_same_product 注 |

## 5. 数据来源

- ONES：`oa_workflow_ones.py` GraphQL（`TEAM=RZxvwUZ8`、履约义务 `WEpkPvew`、部门 `departments`）
- 口径：PRD §0.2d C8–C11（Rex 2026-11-24）


---

## 8. v1.4 追加（Rex 2026-11-24 二次拍板：PM 取值错误修正）

### 8.1 问题

v1.3 输出的 887728 首段「请潘天功负责」被判错误。Rex 两条：
1. 部分人员（如潘天功）不属于项目经理团队；
2. 取值应为**履约义务或项目的负责人**，而非售后负责人或其他字段。

### 8.2 取证（ONES 页面 + GraphQL，2026-11-24）

项目 `SSXM-2026-0811-2087`（uuid `SwRBxYudLxEAjzi9`）页面实证：

```
项目信息
客户名称        武汉丰泰科技有限责任公司
项目负责人      李韶倬        ← GraphQL project.assign
责任销售(OA)    付自旭
```

同项目 13 条任务（10 条履约义务）：
- `项目.assign` = 李韶倬（页面「项目负责人」）
- `义务.owner` 计数：胡李鑫×9、管理员×1（ONES 未收录其部门）
- `义务.assign` 计数：潘天功×4、胡李鑫×2、李韶倬×1、魏晓欣×1、张志超×1、董见周×1（**子任务执行人**）

⇒ 旧 `project_pm`（assign/owner 计数最多者）= 潘天功 ❌；正确 = 李韶倬（项目负责人）。

### 8.3 口径落地

| 层 | 实现 |
|---|---|
| 取值 | `ones_client.project_pm_owner(uuid)`：① `project.assign`（项目负责人）→ ② 为空回退 `project_pm` |
| 团队校验 | `ones_refs.check_pm_team()`：`PM_TEAM_DEPARTMENTS = {大客户服务部, 南区客户服务部, 北区客户服务部, 项目管理部}`；写 `pm_in_team` / `pm_depts` / `pm_team_note` |
| 渲染 | `_pm_lead` 916 分支加 `pm_in_team` 门槛：非 PM 团队 / 部门未收录 → 回退冯刚 + 留证 |
| 链路 | `_build(pm_source="project")` 仅 v13（916）调用；`find_reference_projects`（815/820）默认 `"obligation"`，零影响 |

### 8.4 回归边界

- 历史 4 条 916 已交付报告的 PM 与新口径一致（2521→胡李鑫、3611→徐亚东、3115→徐亚东、0831→王文博，均为 `project.assign`）。
- 815/820 报告逐字一致（v1.2 未动）。
- 唯一行为差异：815 的 3114（旧=潘天功 / 新口径=张燕兰）——因 Rex 明确仅改 916，**不处理**，保持 v1.2。

---

## 9. v1.5：参考项目召回与取舍校准（Rex 2026-11-24，三条流程统一）

### 9.1 触发

Rex 人工办结全部 18 单后，指令「对比我的备注和你的备注，进一步优化」。以 `chains.json`（OA 审批链原文）为准逐单比对，暴露四类系统性偏差：

| 类 | 现象 | 例 |
|---|---|---|
| A | 三字短词探针张冠李戴 | 887594「北京东」→北京东大正保；887597「上海新」→上海新晨 |
| B | 取旧不取新 | 887618/887610 选中项目早于 Rex 实引 |
| C | 未区分签约客户/代理商与最终用户 | 887728 把代理商项目当最终用户项目 |
| D | 列数/新鲜度不符习惯 | Rex 常列 1–3 个且优先最近 |

### 9.2 实现（services/oa/enhance/pm/ones_refs.py）

| 改动 | 位置 | 说明 |
|---|---|---|
| `_search_tokens_long()` | 新增 | 仅返回长度 ≥4 检索词；`_collect_candidates` 双路（义务名+项目名）共用 |
| `_collect_candidates(probes, final_user, customer, project_code)` | 重构 | 义务路跨项目聚合 + 项目名路，命中校验「项目名或义务名含检索词」 |
| `RefProject.product_info` | 新增字段 | `_build` 采集「产品信息」任务名并纳入 `_matched()` |
| `RefProject.customer_mismatch` | 新增字段 | 仅标注，不参与裁决 |
| `_customer_consistent()` / `_mark_customer_mismatch()` | 新增 | 去公司后缀核心名 + ≥4 字公共子串 + 项目名含长词（三选一） |
| `_has_delivery_evidence()` | **已删除** | 曾用于「同期项保留例外」，实测有害（§9.4） |
| `_select(max_per_type=2)` | 参数化 | 每类型上限由 1 提到 2 |
| `_select` 排序 | 修改 | 类型偏好 → **新鲜度** → 状态 rank → 命中数（类型内新鲜度优先） |
| `_select` 同期排除 | 修改 | 恢复**严格**按编号日期（≥ 申请日即剔除） |
| `find_reference_projects_v13` C10 | 修改 | 「未结项优先」由硬剔除降为排序键，全量列出不截断 |
| `find_reference_projects_v13` 排序 | 修改 | 匹配层级 → 未结项 → **新鲜度** → 类型 → 状态 → 命中数 |

### 9.3 PM 口径全流统一

`find_reference_projects`（815/820）的 `_build` 调用改传 `pm_source="project"`，与 v13 一致；`check_pm_team()` 对两条链路都执行。

### 9.4 两次回滚（审计留证）

1. **同期项「交付结论例外」**：曾让 `_select`/v13 对「编号日期 ≥ 申请日但有交付结论」的项目放行，意图救 887717 的 2905；实测反而把 887636 的 3178、887597 的 3180、887610 的 3184、887594 的 3188 等**本单同期新建项**放回 → 回滚为严格按日期。
2. **客户归属剔除**：曾 `_drop_customer_mismatch()` 硬剔不符项，实测删掉 Rex 实引的 1766/3952（五菱经华为云/软通动力交付）→ 改为仅标注。

### 9.5 回归边界

- v1.2/v1.3 的输出形态（字段、列、降级块）不变；仅**选取/排序**口径变化。
- 全量单测：**363 passed, 1 skipped**（含 v1.5 新例：客户不一致标注、产品信息匹配源、每类型上限、同期严格排除）。
