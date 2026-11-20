# bangcle-project-manager-expert — 验收文档 (VERIFICATION)
> 版本: v1.0 · 日期: 2026-11-20

> 范围说明：本 skill 是**纯路由/协调入口**（PJME-001），自身无脚本、无测试；
> 其职责是「识别项目管理意图 → 路由到对应技能/组件」。验收以**路由表正确性 +
> 路由目标可达性**为准，分析能力由被路由技能各自验收。

## 验收标准（Definition of Done）

| # | 标准 | 判据 |
|---|---|---|
| 1 | 项目管理需求按 §一 路由表唯一定位 | 7 个路由条目均可解析到存在的 SKILL.md/组件 |
| 2 | 非项目管理需求按 §边界外 正确分流 | 5 个边界外条目均指向存在的资产 |
| 3 | 典型串联编排顺序明确 | 4 条编排链顺序与 SKILL.md 一致 |
| 4 | 路由目标资产真实存在 | 逐个 `SKILL.md` 存在性校验通过 |
| 5 | 交付闸门工具可用 | `L2-infra/prompts/tools/check_answer_contract.py` 存在且可执行 |

## 测试范围

- skill 自身：仅 `SKILL.md`（6.7KB），无 `scripts/`、无 `tests/`。
- 路由目标：`L3-business/skills/{bangcle-project-summary,bangcle-obligation-summary,bangcle-project-retrospective,bangcle-customer-profile}`、`L4-proprietary/components/delivery-center`、`L4-proprietary/skills/{ones-browser-export,product-manager-expert,contract-manager-expert,bangcle-ppt,bdms-revenue-forecast}`。

## 测试用例

| # | 场景 | 输入 | 预期结果 | 实测 |
|---|---|---|---|---|
| 1 | 路由目标存在性 | 9 个被引用资产逐个查 `SKILL.md` | 全部存在 | ✅ 9/9 OK |
| 2 | 契约工具存在性 | 查 `check_answer_contract.py` | 存在 | ✅ OK |
| 3 | 路由表自洽 | 比对 SKILL.md §一 表条目 | 7 条路由 + 5 条边界外 + 4 条编排 | ✅ 与文档一致 |
| 4 | 自动化测试 | `pytest tests` | — | ⛔ 无 `tests/` 目录：**无自动化测试** |

## 实测结果

- 命令: `for p in L3-business/skills/... ; do [ -f "$p/SKILL.md" ] && echo OK || echo MISS; done`
- 输出摘要: 9 个路由/边界资产全部 `OK`（project-summary / obligation-summary / project-retrospective / customer-profile / product-manager-expert / contract-manager-expert / bangcle-ppt / bdms-revenue-forecast / ones-browser-export）；`L2-infra/prompts/tools/check_answer_contract.py` 亦 `OK`。
- 结论: **通过（静态路由验证）**。路由表与边界外条目均指向真实存在的资产，交付闸门工具就位。

## 可复现手动验证步骤（无自动化测试）

1. 复述需求并按 §一 路由表判定唯一去向；
2. 检查 `bangcle-project-summary` 台账时效（ONES 实时变化，过期先重跑台账）；
3. 多意图按 §典型串联编排 顺序执行，进度分步可见；
4. 最终汇报区分事实/推断/缺失，列明落盘文件；
5. 报告落盘后跑 `python3 L2-infra/prompts/tools/check_answer_contract.py <报告路径>`，exit=0 才算完成。

## 遗留与后续

- 建议把「路由表条目 ↔ 资产存在性」做成 pre-commit 静态门禁，避免路由目标改名/迁移后静默失效。
- 该入口无独立测试是设计使然（自身无逻辑）；若后续加入编排代码，须同步补 `tests/`。
