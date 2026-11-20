# bangcle-customer-profile — 验收文档 (VERIFICATION)

> 版本: v1.0 · 日期: 2026-11-20
> 技能: L3-business/skills/bangcle-customer-profile · 经 L4 PJME-001 路由
> 原则: 用真实数据、真实文件验证；无自动化测试则如实记录并给可复现手动步骤。

## 验收标准（Definition of Done）

对应 SKILL.md「验证」5 项 + Workflow 完成判据：

| AC | 判据 |
|---|---|
| AC1 五维覆盖 | 客户环境 / 客户要求 / 定制要求 / 安全等级 / 安全需求全部覆盖，无内容显式标【缺失】 |
| AC2 可追溯 | 每条画像可指到来源工作项；客户要求与我方推断分开标注 |
| AC3 安全等级依据 | 安全等级结论附依据行（行业/监管/合同/客户明示），无依据标【缺失】 |
| AC4 边界 | 聚焦客户侧事实，未混入我方产品差异/管理结论（归 retrospective） |
| AC5 无泄漏 | 无凭据/网络敏感细节（可定位内部地址+凭证）写入画像 |
| AC6 落盘+闸门 | 落盘 `analysis_output/<客户>客户画像-vN.md`；`check_answer_contract.py` exit=0 |

## 测试范围

- 资产：`SKILL.md`、`assets/customer-profile-template.md`
- 数据源：ONES（工作项描述/评论/附件）+ Product KB 白皮书（经 `../bangcle-project-summary/references/ones-query.md` 取数）
- 校验器：`L2-infra/prompts/tools/check_answer_contract.py`（P1/P2 应答契约，fail-closed）
- 目录清单：`find L3-business/skills/bangcle-customer-profile -type f`

## 测试用例

| # | 场景 | 输入 | 预期结果 | 实测 |
|---|---|---|---|---|
| T1 | 自动化测试发现 | `tests/` 目录 | pytest 通过 | ❌ 无 `tests/` 目录（无自动化测试） |
| T2 | SKILL frontmatter | SKILL.md | name/description/layer 完整 | ✅ name/desc/layer=L3 |
| T3 | 模板结构 | `assets/customer-profile-template.md` | 五维度章节齐备 | ✅ 五维齐备 |
| T4 | 真实产物存在性 | `analysis_output/*客户画像*` | 存在真实画像产物 | ⚠️ 无客户画像类产物（仅台账/报告） |
| T5 | 取数参考可用 | `../bangcle-project-summary/references/ones-query.md` | 端点/鉴权/语法可读 | ✅ 存在且完整 |

## 实测结果

- 命令（T1）: `python3 -m pytest L3-business/skills/bangcle-customer-profile/tests -q`
  - 输出摘要: `ERROR: file or directory not found: .../tests` → `no tests ran`
- 命令（T2）: 解析 SKILL.md frontmatter
  - 输出摘要: `name=bangcle-customer-profile  layer=L3  desc_len=153`
- 命令（T3）: `cat assets/customer-profile-template.md`
  - 输出摘要: 含 `## 0. 基础信息`、`## 1. 客户环境`（云/机房·容器·OS·CPU·中间件·数据库·主机·网络·入场 9 行）、`## 2. 客户要求`、`## 3. 定制要求`（客户明确/我方建议·标准差异·可收费）、`## 4. 安全等级`（依据行）、`## 5. 安全需求`
- 命令（T4）: `ls analysis_output/*画像* analysis_output/*环境*`
  - 输出摘要: 无匹配（该技能尚无真实落盘产物）
- 命令（T5）: `ls L3-business/skills/bangcle-project-summary/references/ones-query.md`
  - 输出摘要: 文件存在，含 GraphQL 端点/鉴权/`name_match`/`issueType` 内省/时间戳说明

- 结论:
  1. **无自动化测试**：本技能为「方法论型」skill（无脚本，仅 SKILL.md + 模板 + 取数参考），测试以**模板结构完备性 + 取数参考可用性 + 真实产物**为准；目前 T4 无真实客户画像产物。
  2. **可复现手动验证步骤**（AC1–AC6）：
     1. 用 `../bangcle-project-summary/references/ones-query.md` 的 `name_match` 拉取目标客户工作项（描述/评论/附件）；
     2. 按 `assets/customer-profile-template.md` 逐维归并，每条标注 `【已验证 日期|来源】/【推断】/【缺失】`；
     3. 安全等级给出依据行，无依据写【缺失】；
     4. 删除凭据/可定位内部地址+凭证；
     5. 落盘 `analysis_output/<客户>客户画像-vN.md`；
     6. 运行 `python3 ../../../L2-infra/prompts/tools/check_answer_contract.py <画像路径>`，须 PASS（exit=0）。
  3. 缺口：**无真实产物样本 + 无自动化测试**，建议后续在跑通一个真实客户画像后补 `tests/`（模板结构断言 + 契约校验断言）。
