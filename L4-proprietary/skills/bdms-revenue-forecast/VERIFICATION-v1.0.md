# bdms-revenue-forecast — 验收文档 (VERIFICATION)
> 版本: v1.0 · 日期: 2026-11-20

> 范围说明：本 skill 是 **L4 确收预算预测统一入口**（RF-001），真实实现在
> 组件 `L4-proprietary/components/bdms/src/bdms/modules/revenue_forecast/`。
> 本文件为 skill 层验收，测试取自该组件的 forecast 测试集。

## 验收标准（Definition of Done）

| # | 标准 | 判据 |
|---|---|---|
| 1 | 双路径结构：Part A 完整、Part B 仅占位 | `NotConfiguredProvider` 恒 `not_configured`，fetch fail-closed 抛 `NotImplementedError` |
| 2 | col3 混合值 10 类映射互斥、fail-closed | 10 类分类无静默丢弃，缺值落 MISSING_DATE |
| 3 | 双口径数字恒等 | 动态 = DUE + PIPE；gap = 动态 − 锁定 |
| 4 | 幂等 | 同输入连跑多次逐字段相等 |
| 5 | 导出 5 sheets、单位元 | 导出测试全绿 |
| 6 | 回归全绿 | forecast 测试集 0 failed |

## 测试范围

组件 `L4-proprietary/components/bdms/tests/` 下 forecast 相关 5 个文件：
`test_forecast_core.py` / `test_forecast_repository.py` / `test_forecast_api.py` / `test_forecast_export.py` / `test_forecast_e2e.py`。
（`test_forecast_e2e.py` 唯一用例标记 slow，默认 deselect，故 `-q` 汇总显示 1 deselected。）

## 测试用例

| # | 场景 | 输入 | 预期结果 | 实测 |
|---|---|---|---|---|
| 1 | 核心口径 | `test_forecast_core.py` | 10 类映射/双口径/恒等式断言通过 | ✅ 含于 #6 |
| 2 | 仓库幂等与账期 | `test_forecast_repository.py` | 重复重算幂等、is_current 唯一 | ✅ 含于 #6 |
| 3 | API 读模型 | `test_forecast_api.py` | 读模型/异常 job 语义正确 | ✅ 含于 #6 |
| 4 | 导出 | `test_forecast_export.py` | 5 sheets、表头与单位 | ✅ 含于 #6 |
| 5 | 端到端（slow） | `test_forecast_e2e.py` | 默认跳过 | 1 deselected |
| 6 | 合并回归 | 5 文件合并 `-q` | 0 failed | ✅ 69 passed, 1 deselected（144.13s） |
| 7 | 真实财报黄金基准 | `parse_report` + `forecast` | 锁定 1.38 / 动态 1.71 / 实际 .94 / gap +.33 / PIPE .841 | ⛔ 本次未跑：源 xlsx 路径依赖本机「Bangcle Workspace」，且组件 `revenue_analysis` 有并行会话在改，按红线避让 |

## 实测结果

- 命令: `cd L4-proprietary/components/bdms && PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m pytest tests/test_forecast_core.py tests/test_forecast_repository.py tests/test_forecast_api.py tests/test_forecast_export.py tests/test_forecast_e2e.py -q -p no:cacheprovider`
- 输出摘要: `69 passed, 1 deselected in 144.13s (0:02:24)`（退出码 0）。
- 结论: **通过**。forecast 模块 69 项测试全绿，覆盖 SKILL.md 声明的核心口径、幂等、导出与 API 语义。

## 遗留与后续

- 黄金基准用例（真实 xlsx 端到端）本次未执行，原因：源文件位于用户本机 `~/Bangcle Workspace/...`，且 `components/bdms` 存在并行会话改动（红线要求避让 `components/`）。该项应作为独立一次真实财报回归执行，不阻断本次 skill 验收。
- `test_forecast_e2e.py` 的 slow 用例建议在 CI 以 `-m slow` 单独跑，保留黄金基准证明力。
