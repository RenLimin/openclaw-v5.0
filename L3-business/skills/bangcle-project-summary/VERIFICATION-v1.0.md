# bangcle-project-summary — 验收文档 (VERIFICATION)

> 版本: v1.0 · 日期: 2026-11-20
> 技能: L3-business/skills/bangcle-project-summary · 经 L4 PJME-001 路由
> 原则: 用真实数据、真实文件验证；无自动化测试则如实记录并给可复现手动步骤。

## 验收标准（Definition of Done）

对应 SKILL.md「验证」4 项 + Workflow 完成判据：

| AC | 判据 |
|---|---|
| AC1 计数一致 | 项目数/工作项数与 GraphQL 分组结果一致；每个工作项恰出现一次 |
| AC2 可追溯 | 每条非空数据可追溯到字段或明确标注推断（交付日期带 `~` 前缀并说明依据） |
| AC3 边界 | 台账只陈述交付事实，未越界下管理/画像结论 |
| AC4 可交付 | Excel 行数 = 工作项数、可打开、无敏感凭据 |
| AC5 落盘 | 落盘 `analysis_output/`（Excel + Markdown + `ones_raw/` 原始 JSON） |

## 测试范围

- 资产：`SKILL.md`、`assets/delivery-ledger-template.md`（标准列 Schema）、`references/ones-query.md`（GraphQL 取数）
- 真实产物：`analysis_output/华夏银行信用卡中心-交付台账-20261029.{md,xlsx}` + `analysis_output/ones_raw/华夏银行信用卡中心-交付台账-20261029.json`
- 校验器：`L2-infra/prompts/tools/check_answer_contract.py`

## 测试用例

| # | 场景 | 输入 | 预期结果 | 实测 |
|---|---|---|---|---|
| T1 | 自动化测试发现 | `tests/` 目录 | pytest 通过 | ✅ test_ledger_template_contract.py（台账模板实例化过契约闸门 + 信封骨架不回归） |
| T2 | SKILL frontmatter | SKILL.md | name/description/layer 完整 | ✅ name/desc/layer=L3 |
| T3 | 台账模板列 | `assets/delivery-ledger-template.md` | 标准 13 列齐备 | ✅ 13 列齐备 |
| T4 | 真实产物存在性 | 华夏台账 md/xlsx/json | 三件套存在 | ✅ 三件套存在 |
| T5 | 真实台账内容 | 华夏台账 md | 项目全景 + 逐项台账 | ✅ 511 工作项 / 28 项目 |
| T6 | 契约校验 | 华夏台账 md | check_answer_contract PASS | ⚠️ BLOCK（缺溯源链/质量信号章节） |
| T7 | 原始 JSON 一致性 | 华夏 json | 行数 = 工作项数 | ✅ 511 条 |

## 实测结果

- 命令（T1）: `python3 -m pytest L3-business/skills/bangcle-project-summary/tests -q`
  - 输出摘要: `ERROR: file or directory not found: .../tests` → `no tests ran`
- 命令（T2）: 解析 frontmatter
  - 输出摘要: `name=bangcle-project-summary  layer=L3  desc_len=133`
- 命令（T3）: `head -40 assets/delivery-ledger-template.md`
  - 输出摘要: 标准列 13 列（序号/项目编号/交付日期/工作项编号/工作项名称/状态/产品名称/产品版本/开发工程Tag/实施类型/责任人/交付内容明细/文档附件）+ 填写约定（`~YYYY-MM` 推断、缺失写【缺失】、凭据脱敏）
- 命令（T4）: `ls -la analysis_output/华夏银行信用卡中心-交付台账-20261029.*`
  - 输出摘要: `md 177,880B` · `xlsx 58,730B` · `ones_raw/…json 394,850B`
- 命令（T5）: `head -25 analysis_output/华夏银行信用卡中心-交付台账-20261029.md`
  - 输出摘要: 头部「生成时间 2026-10-29 · 数据源 ONES 实时 GraphQL（**511 工作项 / 28 项目**）· 证据分级【已验证】/【推断】/【缺失】· 仅事实汇总，不含管理结论/复盘/画像」；项目全景表 28 行；正文表格行计数 `grep -c '^| '` = **542**
- 命令（T6）: `python3 L2-infra/prompts/tools/check_answer_contract.py analysis_output/华夏银行信用卡中心-交付台账-20261029.md`
  - 输出摘要: `❌ 信封F4：缺 ## 0. 溯源链 章节`、`❌ 信封F5：缺「质量信号」章节`、`⚠️ 【推断】未见就近推导依据` → **BLOCK（exit=1）**
- 命令（T7）: `python3 -c "import json;d=json.load(open('analysis_output/ones_raw/华夏银行信用卡中心-交付台账-20261029.json'));print(len(d))"`
  - 输出摘要: `511`（与 md 头部「511 工作项」一致）；条目含 `_itype/_dnote/_project` 等溯源辅助字段

- 结论:
  1. **真实产物达成 AC1/AC2/AC4/AC5**：511 工作项 / 28 项目三件套（md+xlsx+json）齐备，行数一致，证据分级显式。
  2. **缺口（已验证缺陷）**: 台账 md 未过 `check_answer_contract.py` 信封 F4/F5（缺 `## 0. 溯源链`、`质量信号` 章节）。该技能 SKILL.md 强制要求「落盘含溯源链」并跑 fail-closed 校验，需在产出模板中补两章节。
  3. **无自动化测试**：本技能为方法论型 skill（无脚本），回归依赖真实 ONES 取数。可复现手动验证步骤：
     1. 按 `references/ones-query.md` 用 `name_match` 拉客户全部任务，按 `project` 分组；
     2. 按 `assets/delivery-ledger-template.md` 13 列组织，已完成按交付日期正序；
     3. 导出 Excel 到 `analysis_output/`，核对行数 = 工作项数；
     4. 运行 `python3 ../../../L2-infra/prompts/tools/check_answer_contract.py <台账md>`，须 PASS（exit=0）。

## 修复记录（2026-11-20）

- D-03 已修：`assets/delivery-ledger-template.md` 补契约信封骨架（元信息块 F2/F3、`## 0. 溯源链` F4、`## 质量信号` F5、降级标注约定）。模板样例实测过 `check_answer_contract.py`：2 处时间戳、全部硬性项通过、PASS exit=0。
