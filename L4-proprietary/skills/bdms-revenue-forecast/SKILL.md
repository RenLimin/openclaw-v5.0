---
name: bdms-revenue-forecast
description: "BDMS 确收预算预测（Revenue Forecast）— 基于已提供财报（上一账期收入预算执行对比表）实时/动态确认收入预估的 L4 统一入口。财报上传解析、col3 交付预计完成时间混合值分类（10 类）、双口径预估（锁定 1.38 亿 / 动态 1.71 亿黄金基准）、按月分布、计划 vs 预估差异、风险/排除/跨年清单、Excel 导出。Part B（ONES 实时动态）仅占位 not_configured。当用户提出确收预算预测、收入预估、确收缺口分析、确收风险清单等需求时使用。合同管理、产品咨询、项目交付管理不属于本入口。"
metadata:
  openclaw:
    emoji: "💰"
    os: ["darwin", "linux"]
    requires:
      components: ["bdms (L4)"]
    layer: L4
    component_id: RF-001
---

# BDMS 确收预算预测（Revenue Forecast）

> L4 专有业务层，BDMS 组件 `src/bdms/modules/revenue_forecast/`。
> v1.0：**Part A（财报静态口径）完整建设 + Part B（ONES 实时动态）仅占位**。

## When to Use

- 用户需要「今年预计确认多少收入 / 缺口多少 / 风险在哪」
- 用户上传新一期财报（`2026年计划确收&实际确收对比表*.xlsx`），需要解析 + 预估
- 用户需要锁定 / 动态 / 实际 / 差异 四套数字、按月分布、明细下钻、风险清单、Excel 导出
- 用户询问确收口径（新签/递延、时点法/时段法、col3 状态映射）

## 边界外（不属于本入口）

| 需求 | 去向 | 层 |
|---|---|---|
| 合同审查 / 风险扫描 / 销售合同审批 | `contract-manager-expert`（CME-001） | L4 |
| 产品咨询 / SKU / 价格 | `product-manager-expert`（PME-001） | L4 |
| 项目交付管理 / 台账 / 履约 | `bangcle-project-manager-expert`（PJME-001） | L4 |
| PPT 生成 | `bangcle-ppt`（CPT-012） | L4 |

## 核心口径（红线）

1. **双路径结构**：Part A = 已提供财报（上一账期，报告自带交付预计完成时间 col3，**不依赖 ONES**）；Part B = ONES 动态数据（v1.0 仅占位 `NotConfiguredProvider`，恒 `not_configured`，fetch fail-closed 抛 `NotImplementedError`，不伪装有数据）。
2. **金额权威**：唯一权威金额为财报已切分列——底稿 col42（2026 及以后计划确收 ≈2.23 亿）、预算执行表 col10/col27 及逐月 col15–26；**禁用 col39–col41 推算**。
3. **col3 混合值 10 类映射**：2026 年内日期→DUE_2026 按日归月；2027+→跨年清单；`无需填写，100%确收`/`已提交资料`→IN_PIPELINE 独立桶；`调整`→按调整口径；`异常项目`/`合同终止`→排除入风险清单；`未立项`/`未预计`/`金额为0`→风险/零额清单；空/不可解析→MISSING_DATE（fail-closed）。
4. **优先级互斥**：同值含多关键词时按优先级落类（如「已提交资料…异常」→ IN_PIPELINE 第 3 类）。
5. **双口径**：锁定（仅 DUE_2026，1.38 亿）= 逐月和；动态（DUE+PIPE，1.71 亿）= DUE .869 + PIPE .841；gap = 动态 − 锁定 = +.33 亿；实际 1–9 月 = .94 亿。
6. **恒等式**：col27=Σ15–26、col40=col41+col42 不符进校验报告，不静默不崩溃；动态 = DUE + PIPE 恒成立。
7. **导出金额单位元**，表头复用 BaseExporter 惯例；幂等：同输入连跑 3 次逐字段相等。

## 黄金基准（锚点，单位亿元）

| 指标 | 值 |
|---|---|
| 预算执行表有效行 | 10,472 |
| 底稿行 | 38,052 |
| 锁定 2026 / 新签 / 递延 | 1.38 / .67 / .72 |
| 实际 1–9 / 新签 / 递延 | .94 / .44 / .51 |
| 动态 2026 / 新签 / 递延 | 1.71 / .851 / .860 |
| 动态 = DUE + PIPE | .869 + .841 |
| col10 / 2027+ | 2.23 / .84 |
| gap 动态−锁定 | +.33 |

## Quick Start

```bash
cd /Users/bangcle/.openclaw/workspace/L4-proprietary/components/bdms
PYTHONPATH=src python3 -m pytest tests/test_forecast_core.py \
  tests/test_forecast_repository.py tests/test_forecast_api.py \
  tests/test_forecast_export.py -q        # 69 passed

# 真实财报端到端（黄金基准核对）
PYTHONPATH=src python3 - <<'PY'
from bdms.modules.revenue_forecast.report_parser import parse_report
from bdms.modules.revenue_forecast.engine import forecast
rep = parse_report("/Users/bangcle/Bangcle Workspace/01. Management/2026/2026团队报告/202609/2026年计划确收&实际确收对比表202601-09-1017-差异分析.xlsx", forecast_year=2026)
res = forecast(rep.rows, period="202609", forecast_year=2026)
print(res.locked_total, res.dynamic_total, res.actual_ytd_total, res.gap_dynamic_minus_locked, res.dynamic_pipeline)
PY
```

## 组件结构

| 文件 | 职责 |
|---|---|
| `report_parser.py` | 财报解析：底稿 38,052 行 + 预算执行表关联 + 恒等式校验（issues 不阻断） |
| `classifier.py` | col3 混合值 10 类分类（优先级互斥、年份边界、fail-closed） |
| `engine.py` | 双口径预估（locked/dynamic/actual/gap + 逐月 + pipeline 桶） |
| `repository.py` | forecast 四表（period/line/monthly/totals），账期切换 is_current 唯一，幂等重算 |
| `service.py` | 上传异步 job（进度 25→55→75→95→100）+ 读模型，任何异常 job=failed，current 不被半成品切换 |
| `exporter.py` | 导出 5 sheets（汇总/锁定逐月/动态逐月/履约明细/风险与排除） |
| `providers/` | Part B 插槽：`ForecastProvider` 抽象 + `NotConfiguredProvider` 占位 |

## 关键路径

- 财报原始输入：`/Users/bangcle/Bangcle Workspace/01. Management/2026/2026团队报告/<账期>/2026年计划确收&实际确收对比表*.xlsx`
- 中间产物：`analysis_output/ones_raw/`
- 导出：`output/收入预估_<账期>.xlsx`
- 测试：`tests/test_forecast_*.py`（64 项 + export 3 + e2e 1 slow）
- 文档：`PRD/OUTLINE/DETAIL/IMPLEMENTATION-PLAN/OPERATIONS/VERIFICATION-REVENUE-FORECAST-v1.0.md`

## 验收

- 同一财报连解析 3 次稳定（幂等）；
- 异常/终止/未立项/跨年/缺值 100% 进对应清单，不静默丢弃；
- 解析失败明确报错并保留上次结果；长耗时解析有进度条；
- Part B 占位可见且行为明确（not_configured）；
- 不新增第三方依赖（标准库 + 既有 openpyxl）；新增测试数 ≥ 新增判定分支数。
