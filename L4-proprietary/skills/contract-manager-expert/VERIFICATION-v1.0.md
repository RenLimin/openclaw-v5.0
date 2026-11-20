# contract-manager-expert — 验收文档 (VERIFICATION)
> 版本: v1.0 · 日期: 2026-11-20

> 范围说明：本 skill 是 **L4 合同管理统一入口**（CME-001）。合同智能审查/风险扫描/
> 标的参照为**本技能核心职责**，实现在组件 `L4-proprietary/components/bangcle-contract`；
> OA 拉取、审批框架、Office 流程为路由能力。测试取自该组件测试集。

## 验收标准（Definition of Done）

| # | 标准 | 判据 |
|---|---|---|
| 1 | 合同审查五步跑通 | ingest→digitize→risk→kb_match→report 各阶段有测试覆盖 |
| 2 | 风险 rule_id 单一来源 | rule_id 集合 100% 来自 L3 `contract-management` 的 CHECK_RULES |
| 3 | 标的满足度三态 | `satisfied / partial / unsatisfied`，停售 SKU hard-fail |
| 4 | Ontology Bridge 生命周期 | 提交闭环/越权拒绝/非法转移/幂等/Saga 补偿/CWA/CLI 冒烟 7 组通过 |
| 5 | OA 真实链路失效可 skip | E2E 环境不满足时 skip 留证，禁止伪 pass |
| 6 | 回归全绿 | 组件测试集 0 failed（含 skip） |

## 测试范围

组件 `L4-proprietary/components/bangcle-contract/tests/`，共 **365** 用例：
`unit/`（含 risk/extract/satisfaction 等）、`integration/`（含 `test_ontology_bridge.py` 7 组）、
`e2e/`（21 项，含 `test_e2e_real_files.py`）、`fixtures/`。

## 测试用例

| # | 场景 | 输入 | 预期结果 | 实测 |
|---|---|---|---|---|
| 1 | 风险规则 | `tests/unit/test_risk.py` | rule_id 来源受控、命中计数一致 | ✅ 含于 #7 |
| 2 | 标的满足度 | `tests/test_satisfaction.py` | 三态 + 停售红线 | ✅ 含于 #7 |
| 3 | 条目抽取 | `tests/test_extract_items.py` | 条款抽取正确 | ✅ 含于 #7 |
| 4 | Ontology Bridge | `tests/integration/test_ontology_bridge.py` | 7 组全绿 | ✅ 7 passed（0.79s） |
| 5 | 真实文件 E2E | `tests/e2e` | 21 项全绿 | ✅ 21 passed（5.55s） |
| 6 | 单元/集成 | `tests/integration` | 全绿 | ✅ 12 passed（0.84s） |
| 7 | 全量回归 | `pytest tests -q` | 0 failed | ✅ 364 passed, 1 skipped（34.80s） |
| 8 | OA 真实链路 | `contractctl oa-login` 等 | 会话有效期内真跑；失效 skip 留证 | ⛔ 需 OA 会话（耗 IMAP 验证码），本次未执行，属环境性未验 |

## 实测结果

- 命令: `cd L4-proprietary/components/bangcle-contract && PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests -q -p no:cacheprovider`
- 输出摘要: `364 passed, 1 skipped in 34.80s`；用例总数 `365 tests collected`。
- 命令（子集）: `pytest tests/integration/test_ontology_bridge.py -q` → `7 passed`；`pytest tests/e2e -q` → `21 passed`；`pytest tests/integration -q` → `12 passed`。
- 结论: **通过**。364 项全绿，1 项 skip（环境性），核心五步、22 条受控规则、标的参照、Ontology Bridge 均有测试覆盖。

## 可复现手动验证步骤（环境性未验项）

1. 本地合同审查：`python3 cli/contractctl.py review --file <合同.docx> --format xlsx`，确认报告含命中原文片段 + 法条依据；
2. OA 拉取：`oa-login`（耗一次 IMAP 验证码）→ `review --oa-billid <billid>`，确认会话过期时显式报错而非静默；
3. 标的参照：连真实 `product_kb.db`，确认停售 SKU 触发 hard-fail；
4. 交付闸门：报告落盘后跑 `python3 L2-infra/prompts/tools/check_answer_contract.py <报告路径>`，exit=0。

## 遗留与后续

- 1 项 skip 为环境性（OA/外部依赖），符合「失效 skip 留证」红线，非功能缺陷。
- OA 真实链路（TC-OA-01~03）需在有会话时单独回归，建议纳入带证人的定期跑批。
