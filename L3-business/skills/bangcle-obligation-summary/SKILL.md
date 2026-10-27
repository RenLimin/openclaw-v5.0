---
name: bangcle-obligation-summary
description: "Bangcle 项目履约义务汇总：按最终用户名称/客户名称检索全部项目履约义务工作项，罗列所属产线、标题、状态，下钻子交付/子验收任务并展示其标题与状态，从子任务文本明细或授权开通工作项中提取授权/维保到期日期。当用户要求汇总某客户的履约义务、授权/维保到期时间、履约子任务清单时使用。"
user-invocable: true
metadata:
  openclaw:
    layer: L3
    domain: project-management
---

# Bangcle 项目履约义务汇总技能

> 目标：以**客户（最终用户）为视角**，把分散在多个项目的"项目履约义务"工作项及其子工作项汇总成一张表，回答三类问题：
> 1. 该客户名下有哪些履约义务？属于哪条产线、什么标题、什么状态？
> 2. 每项履约义务的**授权/维保到期日期**是什么？（从子交付/子验收任务文本明细，或授权开通工作项提取）
> 3. 每项履约义务下有哪些子工作项？标题和状态分别是什么？

## When to Use

- 用户要求按客户/最终用户汇总履约义务、合同义务、维保/授权到期情况
- 需要看"某客户名下所有项目履约义务及其子任务状态"
- 需要提取授权到期日期、维保到期日期做续费/续签提醒

## 前置与数据源

- ONES 数据获取与鉴权：见 `../bangcle-project-summary/references/ones-query.md`
- 履约义务 issue type：`项目履约义务`（uuid 因环境而异，先内省 `issueTypes { uuid name }` 确认；实测示例 `WEpkPvew`）
- 本技能输出可进一步交给 `bangcle-project-retrospective` / `bangcle-customer-profile` 做深度分析

## Hard Rules

1. **只汇总履约义务类型工作项**，不混入客户定制需求/任务/实施登记等其他类型（除非用户明确要求全量）。
2. **到期日期必须来自文本证据**：从子交付/子验收任务的 `descriptionText`、评论、附件名中提取；提取不到的标【缺失】，**禁止编造**。
3. **日期格式统一为 YYYY-MM-DD**；文本中仅有期限区间（如"2026-07-02 ~ 2026-08-02"）时取**到期日**（区间结束日）。
4. **产线判定**：优先用履约义务 `products` 字段（如"产研-应用安全监测"）；为空时按标题关键词推断并标【推断】。
5. 凭据/账号/密码/license 内容不写入产出，可写授权文件名。

## Workflow（按序执行）

### Step 1 — 确认履约义务 issue type UUID
- 内省 `issueTypes`，找到名称=`项目履约义务` 的 uuid。
- **完成判据**：拿到准确 type uuid，避免类型过滤失效。

### Step 2 — 按客户检索全部履约义务
- `tasks(filter: {name_match: "<客户名>", issueType: {uuid_equal: "<履约义务uuid>"}})`；客户名=最终用户名称/客户名称（含简称与别名时多次匹配后合并去重）。
- 同时按 `project` 分组，确认覆盖该客户全部项目（POC 与签约）。
- **完成判据**：履约义务清单无漏项；若存在"无名称匹配但属于该客户项目"的履约义务，用 `project_in` 补检。

### Step 3 — 罗列产线/标题/状态
- 每条履约义务取：number / name / status{name,category} / owner / products / project / createTime。
- 产线取 products 名称；空则推断并标【推断】。
- **完成判据**：主表列齐：客户 / 项目编号 / 履约义务编号 / 所属产线 / 标题 / 状态 / 负责人。

### Step 4 — 下钻子工作项（标题+状态）
- 用 `tasks(filter: {parent_uuid_in: [<履约义务uuid...>]})` 或对每个履约义务取 `subTasks { number name status { name } }` 拉子任务。
- 子工作项分类：交付任务 / 验收任务 / 授权开通 / 其他，依据标题与 issueType 归类。
- **完成判据**：每个履约义务下子工作项标题、状态齐全；无子任务时明确写"无子任务"而非留空。

### Step 5 — 提取授权/维保到期日期
- 遍历子任务（优先：授权开通、交付、验收类）的 `descriptionText` + 评论 + 附件名。
- 按 `references/expiry-extraction.md` 的规则与关键词提取到期日。
- 授权类工作项（如"授权新建/license/账号开通"）：到期日=授权有效期结束日。
- 维保类工作项（如"维保服务"）：到期日=维保周期结束日。
- **完成判据**：每项履约义务的授权/维保到期日期有来源标注（工作项编号+文本摘录），或显式【缺失】。

### Step 6 — 汇总输出
- 按 `assets/obligation-summary-template.md` 组织：客户级总表 + 逐履约义务子表。
- 到期日期近 90 天内的标 ⚠️ 提醒；已过期的标 ❌。
- 落盘 `analysis_output/<客户>履约义务汇总-vN.md`，可导出 Excel。
- **完成判据**：表格可直接用于续费/续签决策，每行可溯源。

## 相关技能

- 数据获取与鉴权：`bangcle-project-summary`（references/ones-query.md）
- 交付台账：`bangcle-project-summary`
- 深度复盘：`bangcle-project-retrospective`
- 客户画像：`bangcle-customer-profile`
- 标准产品基线：`product-kb`

## 验证

- [ ] 履约义务清单覆盖该客户全部项目（POC+签约）
- [ ] 每行到期日期可指到来源工作项与文本摘录
- [ ] 子工作项标题/状态与 ONES 实时一致
- [ ] 无凭据泄漏；无编造日期
