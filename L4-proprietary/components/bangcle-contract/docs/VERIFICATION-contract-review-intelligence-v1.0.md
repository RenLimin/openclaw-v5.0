# VERIFICATION — 合同审查智能化增强 v1.0（条款拆解 · 风险点 · 历史交付盘点）

- 组件：`L4-proprietary/components/bangcle-contract`
- 日期：2026-11-24
- 结论：**PASS**（AC1–AC9 全部达成；无门禁违例）

## 验收标准与证据（对应 PRD §5 AC1–AC9）

| AC | 要求 | 证据 | 结果 |
|---|---|---|---|
| AC1 | 条款拆解接入 ReviewService，输出类别/法条/摘要/原文/问题/建议 | `contract_review/clause_extract.py`；真实样本 `tmp/oa-757/886377/contract.txt` → `categories_total=29, extracted=10, required_total=13, missing_required=4` | ✅ |
| AC2 | 风险点复用 L3 受控库，rule_id/法条可回溯 CHECK_RULES，缺失项标 `CLAUSE_MISSING` | `contract_review/risk_points.py`；实测样本产出 5 条（`medium×1, low×4`），`rule_set_version=L3-contract-management-v1.0`；测试 `test_risk_points_rule_ids_backed_by_l3_library` 断言逐条 law 一致 | ✅ |
| AC3 | 无提取器的类别不参与「缺失」判定（防漏抽误判真缺失） | `test_clause_extract_unsupported_not_counted_missing`；实测 unsupported={数量与质量,履行地点,合同转让,通知送达,合同附件,税费承担} 与 missing 交集为空 | ✅ |
| AC4 | R1b 历史交付盘点四态 fail-closed（正常/关注/异常/未收录），查无记录≠正常 | `services/oa/enhance/history_delivery.py`；`XSZS_NOT_EXIST_999999` → `未收录, matched_rows=0, missing=[bdms_unmatched…]` | ✅ |
| AC5 | R1b 去重（BDMS 按履约项多行重复同一异常） | `XSZS2609200704` 命中 16 行 → 去重后风险点 1 条；`test_history_delivery_real_contract_dedup` | ✅ |
| AC6 | P3 编号回退消误报 | `checks.extract_contract_no`；887756 类（表单空+合同名含 `20261106-01KP`）→ `('20261106-01KP','contract_name_loose')`，不再判 block | ✅ |
| AC7 | 757 备注合并 R1b 且过 ADR-035 门禁 | `remark-887770.md` / `remark-887756.md` 各 4 处时间戳标注，`check_answer_contract.py` 均 **PASS** | ✅ |
| AC8 | 新增 CLI 子命令可执行、注册表已登记 | `contractctl clauses|history-delivery --help` 正常；registry `--validate` 通过；`--coverage` 74/74=100% | ✅ |
| AC9 | 全量单元测试通过 | `pytest tests/unit/ -q` → **362 passed, 1 skipped**（新增 `test_contract_intelligence.py` 20 例） | ✅ |

## 真实单据回归（只读，未做任何 OA 写操作）

| requestid | 处理前 | 处理后 | 说明 |
|---|---|---|---|
| 887770 | 退回补充（block：合同编号缺失） | 退回补充（block 仍在，编号确实缺失；R1b=未收录显式降级） | 合同名无编号 → 正确维持 block |
| 887756 | 退回补充（block：合同编号缺失） | **退回补充（待原文）** | P3 修复生效：合同名回退命中，误报消除；仅剩 L2 三项转人工 |
| 886377 | — | 条款拆解 10/29、风险点 5 条 | 真实合同全文链路可用 |

> ⚠️ 887770 的 R1=`未知`（ONES `project_not_found`）与 R1b=`未收录` 均为数据源降级，备注已显式标注，未当作「无风险」。

## 边界与已知限制

- OA 757 链严格只读：未提交/审批/退回/转发。
- L2 三项（甲方邮箱/最终用户表/版本描述）仍需 `--contract-file` 提供原文；757 附件 REST 无权限，未提供即 `manual`。
- R1b 数据基准为 BDMS `dr_sheet_row` 202606 快照；跨期数据需更新快照后再跑。
- 条款缺失统一 `low/missing`，不阻断审批（仅提示人工复核）。

## 变更清单

新增：`contract_review/clause_extract.py`、`contract_review/risk_points.py`、`services/oa/enhance/history_delivery.py`、`tests/unit/test_contract_intelligence.py`、本 PRD 与本文档。
修改：`contract_review/{models,pipeline,report}.py`、`services/oa/enhance/{checks,runner,orchestrator,remark}.py`、`cli/contractctl.py`、`capability-registry/registry.yaml`、`skills/contract-manager-expert/SKILL.md`。
