# customer-delivery-intelligence — 验收文档 (VERIFICATION)
> 版本: v1.0 · 日期: 2026-11-20

> 范围说明：本 skill 是**工作流路由入口**（CDI-001），唯一权威为组件
> `L4-proprietary/components/customer-delivery-intelligence/runner/`。
> 验收以工作流骨架、两道人工闸、断点恢复与 fail-closed 校验为准。

## 验收标准（Definition of Done）

| # | 标准 | 判据 |
|---|---|---|
| 1 | 输入三元组必填 | customer / period / audience 缺一不可 |
| 2 | 两道人工闸强制暂停 | 不会自动跑完；approve/reject 均生效 |
| 3 | 闸2 驳回可回退 compose | revise 分支正确 |
| 4 | 断点恢复 | checkpoint 持久化，`resume` 可续跑 |
| 5 | 原始数据只来自 OA/ONES | sourceUri 覆盖率 100%，否则失败 |
| 6 | 产物完整 | 6 份 Markdown + PPTX + DOCX |
| 7 | 骨架测试全绿 | `tests/` 0 failed |

## 测试范围

组件 `L4-proprietary/components/customer-delivery-intelligence/tests/test_skeleton.py`（13 用例），
覆盖：双闸全流程、闸2 驳回回退、checkpoint 持久化与恢复等。

## 测试用例

| # | 场景 | 输入 | 预期结果 | 实测 |
|---|---|---|---|---|
| 1 | 双闸全流程 | `test_full_flow_with_two_gates` | 两闸 approve 后产出全套产物 | ✅ 含于 #5 |
| 2 | 闸2 驳回回退 | `test_gate2_revise_back_to_compose` | revise 后回到 compose，不落地产物 | ✅ 含于 #5 |
| 3 | checkpoint 恢复 | `test_checkpoint_persist_and_resume` | 持久化并可断点续跑 | ✅ 含于 #5 |
| 4 | 用例总数 | `--collect-only` | 13 | ✅ 13 tests collected |
| 5 | 全量回归 | `pytest tests -q` | 0 failed | ✅ 13 passed（27.24s） |
| 6 | 真实客户黄金基准 | 中国建设银行（14 合同 / 净额 5,621,800 元） | 数字一致 | ⛔ 需 OA/ONES 真实会话，本次未执行（环境性） |

## 实测结果

- 命令: `cd L4-proprietary/components/customer-delivery-intelligence && PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests -q -p no:cacheprovider`
- 输出摘要: `13 passed in 27.24s`（含 openpyxl/pydantic 告警，非失败）。
- 结论: **通过**。工作流骨架 13 项全绿，两道人工闸、驳回回退、断点恢复均有覆盖。

## 可复现手动验证步骤（环境性未验项）

1. 启动：`python3 -m runner.main start --customer "<客户官方全名>" --period-start YYYY-MM-DD --period-end YYYY-MM-DD --audience internal`，记下 task_id；
2. `status <task_id>` 确认停在 gate1，`decide <task_id> --gate gate1 --decision approve`；
3. 确认停在 gate2，`decide ... --gate gate2 --decision approve`；
4. 核对 `storage/artifacts/<task_id>/` = 6 份 Markdown + `*-项目交付汇报.pptx` + `*-项目交付说明.docx`；
5. external 场景额外确认脱敏闸生效。

## 遗留与后续

- 黄金基准（建行）需真实 OA/ONES 会话，建议纳入带证人的定期跑批；
- 测试仅覆盖骨架，采集器与渲染器复用既有 collector，其自身测试在对应组件内。
