# bangcle-project-retrospective — 验收文档 (VERIFICATION)

> 版本: v1.0 · 日期: 2026-11-20
> 技能: L3-business/skills/bangcle-project-retrospective · 经 L4 PJME-001 路由
> 原则: 用真实数据、真实文件验证；无自动化测试则如实记录并给可复现手动步骤。

## 验收标准（Definition of Done）

对应 SKILL.md「验证」5 项 + Workflow 完成判据：

| AC | 判据 |
|---|---|
| AC1 层级明确 | 复盘层级（单项目/项目集）明确，范围与 `bangcle-project-summary` 台账一致 |
| AC2 证据 | 每个结论有证据或标【缺失】；客户原声不得直接当结论 |
| AC3 产品/管理分离 | 产品问题（vs 标准基线）与管理问题（vs PMBOK）分开陈述 |
| AC4 建议可执行 | 每条建议含**责任方 + 动作**，落到后续交付方案或项目计划的具体改动与可检查项 |
| AC5 Program 量化 | Program 触发信号有量化依据（同客户 12 月内 ≥2 同类 POC / 长期 0 签约 / 重复履约） |
| AC6 必算 6 指标 | 证据化作业必算：POC 占比 / 计划日期完整率 / 在途无计划率 / 占位 owner 率 / 无合同归属率 / 脏数据 |

## 测试范围

- 资产：`SKILL.md`、`references/pmbok-checklist.md`、`references/program-playbook.md`、`references/retro-evidence-playbook.md`
- 依赖：`bangcle-project-summary` 台账 + `product-kb` 标准基线
- 真实产物：`analysis_output/山东城商行联盟项目与合同汇总分析报告.md`（2026-11-02）、`analysis_output/山东城商行联盟-合同条款级交付物清单.md`
- 校验器：`L2-infra/prompts/tools/check_answer_contract.py`

## 测试用例

| # | 场景 | 输入 | 预期结果 | 实测 |
|---|---|---|---|---|
| T1 | 自动化测试发现 | `tests/` 目录 | pytest 通过 | ✅ test_report_skeleton_contract.py（报告骨架实例化过契约闸门 + 6 指标/三档证据铁律不回归） |
| T2 | SKILL frontmatter | SKILL.md | name/description/layer 完整 | ✅ name/desc/layer=L3 |
| T3 | 参考文档齐备 | 3 个 references | PMBOK/Program/证据化手册齐备 | ✅ 齐备 |
| T4 | 6 指标手册 | `retro-evidence-playbook.md` | 6 指标算法+实测齐备 | ✅ 齐备 |
| T5 | 真实产物契约校验 | 山盟分析报告 | check_answer_contract PASS | ✅ PASS |
| T6 | 真实产物存在性 | 山盟两份产物 | 存在 | ✅ 存在 |

## 实测结果

- 命令（T1）: `python3 -m pytest L3-business/skills/bangcle-project-retrospective/tests -q`
  - 输出摘要: `ERROR: file or directory not found: .../tests` → `no tests ran`
- 命令（T2）: 解析 frontmatter
  - 输出摘要: `name=bangcle-project-retrospective  layer=L3  desc_len=169`
- 命令（T3）: `find L3-business/skills/bangcle-project-retrospective -type f`
  - 输出摘要: `SKILL.md` + `references/pmbok-checklist.md` + `references/program-playbook.md` + `references/retro-evidence-playbook.md`
- 命令（T4）: `head -60 references/retro-evidence-playbook.md`
  - 输出摘要: 三档证据铁律；取数清单 4 面（合同/项目/义务/现场）；**必算 6 指标**（山盟实测：POC 占比 31/43=72%、计划完整率 73/388=19%、在途无计划率 110/113=97%、占位 owner 率 63/113=56%、无合同归属率 120/388=31%、脏数据 3 条）；双轴结构（产品轴/管理轴）；改进项分短/中/长期
- 命令（T5）: `python3 L2-infra/prompts/tools/check_answer_contract.py analysis_output/山东城商行联盟项目与合同汇总分析报告.md`
  - 输出摘要: `类型: 报告(report)` · `时间戳标注: 11 处` · `⚠️ 数据已 81 天前（2026-08-31|OA导出CSV），注意时效` · **结果: PASS**
- 命令（T6）: `ls -la analysis_output/山东城商行联盟*`
  - 输出摘要: `山东城商行联盟项目与合同汇总分析报告.md 17,228B`（2026-11-02 12:30）、`山东城商行联盟-合同条款级交付物清单.md 32,345B`（2026-11-02 12:29）

- 结论:
  1. **真实产物达成契约闸门**：山盟项目集分析报告过 `check_answer_contract.py`（PASS，11 处时间戳），且内容即本技能双轴（产品轴/管理轴）+ Program 治理 + 证据化作业的实战沉淀。
  2. **无自动化测试**：本技能为方法论型 skill（无脚本），回归依赖真实台账 + Product KB。可复现手动验证步骤：
     1. 先跑/复用 `bangcle-project-summary` 台账，确认复盘层级与范围；
     2. 按 `retro-evidence-playbook.md` 取数清单落盘 4 面原始文件；
     3. 算 6 指标（注意排除 `planEndDate=1970` 零值脏数据）；
     4. 产品轴逐维度对标 `product-kb`，管理轴按 `pmbok-checklist.md` 逐域 `Issue→Root cause→Impact→Recommendation→Owner`；
     5. 收敛两张改进清单（交付方案/项目计划），每条带责任方 + 验收点；
     6. 落盘 `analysis_output/<客户或项目>项目复盘报告-vN.md`，跑 `check_answer_contract.py` 须 PASS。
  3. 缺口：**无 `tests/` 自动化测试**；建议补 6 指标算法的表驱动单测（可复用山盟实测值作黄金基准）。

## 修复记录（2026-11-20）

- D-09 已修：新增 `tests/test_report_skeleton_contract.py`（报告骨架实例化过契约闸门 + 6 指标/三档证据铁律不回归）。关键路径 hermetic（不依赖 analysis_output/），实测通过。
