# VERIFICATION — OA 合同附件自动获取 + L2/R3 真实分析 v1.0

- 组件：`L4-proprietary/components/bangcle-contract`
- 日期：2026-11-27
- 结论：**PASS**（规则 1 降级落地；规则 2 自动取原文链路真实跑通；无降级误判）

## 背景

Rex（Limin Ren）2026-11-27 两项要求：
1. 「合同编号在合同归档时生成，OA 销售合同审核流程默认为空」→ 不得作为退回理由。
2. 「审核结果是否针对流程中合同附件原文做了拆解和分析」→ 此前未做（旧链路只认显式 `--contract-file`）。

## 验收标准与证据

| AC | 要求 | 证据 | 结果 |
|---|---|---|---|
| A1 | 合同编号缺失由 block 降为 warn，不阻断 | `checks.py::run_fixed_checks` L1-a；`remark.derive_verdict`；`test_oa_approval.py::test_l1_form_checks` | ✅ |
| A2 | 未给 `--contract-file` 时自动从 OA 表单附件下载原文 | `services/oa/enhance/attachment.py::fetch_contract_text`；编排层接入；实测 4 单全部 `with_attachment_auto=4 / attachment_failed=0` | ✅ |
| A3 | 附件 magic 校验（docx=PK / doc=OLE2 / pdf=%PDF），登录跳转 HTML 不伪造 | `download_ref`；`tests/unit/test_oa_attachment.py` 7 例 | ✅ |
| A4 | 有原文后真实执行 L2 + R3（条款/风险点），不再恒转人工 | 4 单 summary：`with_contract_text=4`；R3 clauses=8 类、overall high×3 / low×1 | ✅ |
| A5 | 旧「REST 无权限」口径修正并留审计链 | `checks.py`/`attachment.py` 头注释；`PRD…v1.0.md` P2 加修正指针；`VERIFICATION…intelligence-v1.0.md` §口径修正 | ✅ |
| A6 | 甲方官方邮箱识别修正（外部域名=pass）+ evidence 诚实化 | `checks.py::_party_a_email_windows/_external_emails`；`test_oa_approval.py` 新增 4 例；实测 888194/888171/888166 → pass | ✅ |
| A7 | L3 解析器无分组正则崩溃修复 | `L3-business/components/contract-management/contract_management/contract_parser.py`；回归 `tests/test_clause_extract_group_bug.py` 2 例 | ✅ |

## 真实单据复跑（只读，未做任何 OA 写操作）

| requestid | 附件 | 附件形态 | L2 甲方邮箱 | R3 overall | 备注结论 |
|---|---|---|---|---|---|
| 886502 | 湖北网安通采购订单.docx | PK / 25339B | manual（原文无邮箱条款） | high（风险 21：高6/中8/低7；必备缺 5） | 退回补充（待人工复核） |
| 888194 | 小米钱包合同.doc | OLE2 / 77824B | **pass**（zhangyu33@xiaomi.com） | high（高1/中1/低5） | 退回补充（待人工复核） |
| 888171 | 奔腾融媒合同.doc | OLE2 / 103936B | **pass**（8947078@qq.com） | low | 退回补充（待人工复核） |
| 888166 | 鑫欣顺发合同.doc | OLE2 / 79360B | **pass**（8947078@qq.com） | high | 退回补充（待人工复核） |

> 「待人工复核」≠「待原文」：已有原文但个别条款未检索到（当前仅「最终用户信息表」仍 manual）。合同编号缺失仅 warn，不影响结论。

## 回归

- L4 组件：`pytest tests/unit -q` → **378 passed, 3 skipped**
- L3 组件：`pytest tests/ -q` → **126 passed**
- ADR-035 应答契约门禁：4 张备注均 **PASS**
- 注册表：`--coverage` 75/75=100%，`--validate` 129 entry 路径通过，`--lifecycle` 75/75

## 变更清单

新增：`services/oa/enhance/attachment.py`、`tests/unit/test_oa_attachment.py`、本文件。
修改：`services/oa/enhance/{checks,orchestrator,remark,history_delivery}.py`、`cli/contractctl.py`、L3 `contract_parser.py`、`docs/{PRD,VERIFICATION}-contract-review-intelligence-v1.0.md`、知识库 `oa-contract-review-workflow.md`、skill 镜像 `contract-manager-expert/SKILL.md`。
