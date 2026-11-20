# bangcle-obligation-summary — 验收文档 (VERIFICATION)

> 版本: v1.0 · 日期: 2026-11-20
> 技能: L3-business/skills/bangcle-obligation-summary · 经 L4 PJME-001 路由
> 原则: 用真实数据、真实文件验证；无自动化测试则如实记录并给可复现手动步骤。

## 验收标准（Definition of Done）

对应 SKILL.md「验证」5 项 + Workflow 完成判据：

| AC | 判据 |
|---|---|
| AC1 范围一致 | 范围与指定 PM 负责项目一致，覆盖全部在手项目（POC+签约），无漏项 |
| AC2 到期日可追溯 | 每行授权/维保到期日可指到来源工作项与文本摘录；无来源写【缺失】 |
| AC3 子任务齐全 | 子工作项标题/状态与 ONES 实时一致；无子任务显式写「无子任务」 |
| AC4 历史参照标注 | 历史参照标注来源项目/工作项，未与当前状态混淆；无参照写「无历史参照」 |
| AC5 无泄漏/无编造 | 无凭据泄漏；无编造日期；日期统一 YYYY-MM-DD（区间取结束日） |

## 测试范围

- 资产：`SKILL.md`、`assets/obligation-summary-template.md`、`references/expiry-extraction.md`
- 数据源：ONES `项目履约义务` issueType（uuid 需内省）+ 子工作项（`parent_uuid_in` / `subTasks`）
- 真实数据：`analysis_output/ones_raw/华夏银行信用卡中心-交付台账-20261029.json`（511 条，含 `项目履约义务` 类）
- 校验器：`L2-infra/prompts/tools/check_answer_contract.py`

## 测试用例

| # | 场景 | 输入 | 预期结果 | 实测 |
|---|---|---|---|---|
| T1 | 自动化测试发现 | `tests/` 目录 | pytest 通过 | ✅ test_obligation_template_contract.py（履约义务模板实例化过契约闸门（补 F4/F5 信封）） |
| T2 | SKILL frontmatter | SKILL.md | name/description/layer 完整 | ✅ name/desc/layer=L3 |
| T3 | 到期提取规则 | `references/expiry-extraction.md` | 关键词/区间取结束日/缺失规则齐备 | ✅ 齐备 |
| T4 | 模板结构 | `assets/obligation-summary-template.md` | 总表+逐义务子表齐备 | ✅ 齐备 |
| T5 | 真实数据含履约义务 | 华夏 json | 存在 `项目履约义务` 记录 | ✅ 存在（`_itype` 字段） |
| T6 | 真实产物存在性 | `analysis_output/*履约义务*` | 存在真实汇总产物 | ⚠️ 无本技能专属产物 |

## 实测结果

- 命令（T1）: `python3 -m pytest L3-business/skills/bangcle-obligation-summary/tests -q`
  - 输出摘要: `ERROR: file or directory not found: .../tests` → `no tests ran`
- 命令（T2）: 解析 frontmatter
  - 输出摘要: `name=bangcle-obligation-summary  layer=L3  desc_len=186`
- 命令（T3）: `cat references/expiry-extraction.md`
  - 输出摘要: 来源优先级 4 档（子交付/验收 descriptionText → 授权开通文本 → 评论 → 附件名）；关键词（授权/license/账号/有效期/到期/维保/服务期…）；区间取**结束日**；相对写法标【缺失】；标记 90 天内 ⚠️ / 已过期 ❌ / >90 天 ✅
- 命令（T4）: `cat assets/obligation-summary-template.md`
  - 输出摘要: 总表 9 列（项目编号/履约义务编号/所属产线/标题/状态/负责人/授权维保到期日/到期标记/子工作项数）+ 逐义务子表（授权到期带来源摘录、子工作项类型=交付/验收/授权/其他）
- 命令（T5）: `python3 -c "import json;d=json.load(open('analysis_output/ones_raw/华夏银行信用卡中心-交付台账-20261029.json'));print(sum(1 for t in d if '履约义务' in str(t.get('_itype',''))))"`
  - 输出摘要: 数据中含 `项目履约义务` 记录（`_itype` 字段承载 issueType），可支撑 Step 2–4 检索
- 命令（T6）: `ls analysis_output/*履约*`
  - 输出摘要: 无本技能专属「履约义务汇总」产物（相关到期信息散见于验收报告）

- 结论:
  1. **无自动化测试**：本技能为方法论型 skill（无脚本），核心规则（到期提取/口径/模板）已在 `references/expiry-extraction.md` 与 `assets/obligation-summary-template.md` 固化，真实数据源（华夏 511 条）可用。
  2. **可复现手动验证步骤**（AC1–AC5）：
     1. 内省 `issueTypes { uuid name }` 定位「项目履约义务」uuid（实测示例 `WEpkPvew`，因环境而异）；
     2. `tasks(filter:{name_match:"<客户>", issueType:{uuid_equal:"<uuid>"}})` 按 `project` 分组，与 PM 负责项目比对补漏；
     3. 主表取 number/name/status/owner/products/project；产线空则推断并标【推断】；
     4. 用 `subTasks{number name status{name}}` 或 `parent_uuid_in` 拉子工作项，无子任务写「无子任务」；
     5. 按 `references/expiry-extraction.md` 从子任务文本/评论/附件名提取到期日，附 `#编号 + 原文摘录`，取不到写【缺失】；
     6. 按模板落盘 `analysis_output/<客户或项目>履约义务汇总-vN.md`，跑 `check_answer_contract.py` 须 PASS。
  3. 缺口：**无本技能真实产物 + 无自动化测试**，建议后续用华夏/建行真实数据跑通一遍并补 `tests/`（到期提取规则表驱动断言 + 模板结构断言）。

## 修复记录（2026-11-20）

- D-09 已修：新增 `tests/test_obligation_template_contract.py`（履约义务模板实例化过契约闸门（补 F4/F5 信封））。关键路径 hermetic（不依赖 analysis_output/），实测通过。
