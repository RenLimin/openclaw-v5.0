---
name: bangcle-project-summary
description: "Bangcle 项目信息汇总：业务目标是汇总项目交付实施情况，从 ONES 等系统汇总客户名下全部项目/产品/工作项/交付物/责任人，输出结构化交付台账（Excel/Markdown）。当用户要求整理、汇总、导出某客户或项目的实施交付记录、交付历史、交付现状时使用。"
user-invocable: true
metadata:
  openclaw:
    layer: L3
    domain: project-management
---

# Bangcle 项目信息汇总技能

> **业务目标**：**汇总项目交付实施情况**——把分散在 ONES 的客户/项目/工作项/交付物汇总成**一份可信、可导出、可审计**的交付台账，回答"项目实际交付得怎么样：交了什么、谁交的、什么状态"。
>
> 本技能产出的台账是其他三个技能共同的事实基线：履约义务汇总（参考历史交付）、项目复盘、客户画像都在它之上展开。

> **统一入口**：本技能是 L4 层 **Bangcle 项目管理专家**（`bangcle-project-manager-expert`，PJME-001）路由的专项能力之一；Bangcle 项目管理相关需求从该入口统一识别、路由与协调。

## When to Use

- 用户要求整理/汇总/导出某客户或某项目的**交付实施情况**、交付历史、交付现状
- 需要按客户视角看清"涉及哪些产品、哪些项目、各工作项状态与责任人、已交付哪些交付物"
- 需要为履约对照、项目复盘、客户画像提供可信的数据底座
- 需要把交付记录导出为 Excel 并打开

## Hard Rules

1. **证据分级**，禁止编造：每条数据标注【已验证】（ONES 实时字段）/【推断】（时间戳/工时）/【缺失】（系统无记录）。
2. **客户级全景优先**：先枚举客户名下全部项目，再下钻工作项，避免漏项。
3. **owner 占位要还原真实执行人**：owner 为"管理员/空"时，用工时审批、评论反推实际执行人，无法确定则标【缺失】。
4. **交付日期无实际字段时**标注"~"并说明推断依据，不得当成事实。
5. **只做事实汇总，不下管理结论**：差异分析、改进建议归 `bangcle-project-retrospective`，客户侧需求归纳归 `bangcle-customer-profile`。
6. 凭据/账号/密码绝不写入产出（脱敏）。

## Workflow（按序执行）

### Step 1 — 锁定客户与项目全景
- 数据源 ONES（参考 `../ones-browser-export/SKILL.md`）；GraphQL 端点与鉴权见 `references/ones-query.md`。
- 用客户名 `name_match` 拉全部任务，按 `project` 分组，得出"客户 → N 个项目 → 各项目工作项数"。
- **完成判据**：输出项目清单（项目编号/立项时间/产品线/标准产品），并确认无非 POC 项目遗漏。

### Step 2 — 拉取工作项完整字段
- 每个工作项取：number / name / status / owner / issueType / products / descriptionText / createTime / planStartDate / planEndDate / attachmentCount / discussionCount / parent。
- 评论与附件单独拉取（commonComments / attachments）。
- **完成判据**：字段缺失率已知，附件/评论数量与字段计数一致。

### Step 3 — 构建统一交付台账
- 按 `assets/delivery-ledger-template.md` 的列组织，已完成/在途/未开始用**状态列**区分。
- 已完成交付按交付日期正序；在途与未开始排在后或标注，不混入历史。
- **完成判据**：每个工作项恰出现一次，状态与 ONES 一致。

### Step 4 — 导出与交付
- 导出 Excel（pandas + openpyxl）到 `analysis_output/`，文件名含客户与主题；按需 `open` 打开。
- 同时保留 Markdown 版与原始 JSON（`analysis_output/ones_raw/`）。
- **完成判据**：Excel 可打开、行数=工作项数、无凭据泄漏。

## 标准列（台账 Schema）

序号 / 项目编号 / 交付日期 / 工作项编号 / 工作项名称 / 状态 / 产品名称 / 产品版本 / 开发工程Tag / 实施类型 / 责任人 / 交付内容明细 / 文档附件

## 相关技能

- 数据获取：`ones-browser-export`
- 标准产品基线：`product-kb`
- 履约义务汇总（以本台账为历史参照）：`bangcle-obligation-summary`
- 进一步分析复盘：`bangcle-project-retrospective`
- 客户环境与需求画像：`bangcle-customer-profile`

## 验证

- [ ] 项目数/工作项数与 GraphQL 分组结果一致
- [ ] 每条非空数据可追溯到字段或明确标注推断
- [ ] 台账只陈述交付事实，未越界下管理/画像结论
- [ ] Excel 行数正确、可打开、无敏感凭据

## 应答规范（ADR-035 强制引用）

> 本技能输出口径必须遵循以下应答契约（ADR-035 P1/P2 纵切层）：
>
> 1. **P1 通用应答契约**（数据源优先级与时效、证据三档【已验证】/【推断】/【缺失】、降级显式声明、落盘与副作用、客户实体归一、风险定级通用规则）：
>    `/Users/bangcle/.openclaw/workspace/L2-infra/prompts/answer-spec-base.md`
> 2. **P2 域应答契约**（固定输出维度 + 域风险定级矩阵）：
>    `/Users/bangcle/.openclaw/workspace/L3-business/prompts/project-answer-spec.md`
>
> 契约优先于本 SKILL 内任何自定义口径；两者冲突时以契约为准，并提请维护对应 spec。
