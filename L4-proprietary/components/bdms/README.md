# BDMS — Bangcle 交付管理系统

> 组件路径：`L4-proprietary/components/bdms/`
> 架构文档：`docs/architecture/00-system-architecture.md` §L4
> 文档体系：`PRD-v2.1` / `DESIGN-OUTLINE-v2.1` / 7 份 `DESIGN-DETAIL-v2.1` / `OPERATIONS-v2.1` / `VERIFICATION-v2.1`

## 模块地图

| 模块 | 目录 | 说明 |
|---|---|---|
| 交付月报 | `src/bdms/modules/delivery_report/` | 交付月报生成（核心业务） |
| 确收管理 | `src/bdms/modules/revenue/` | 确收报表（既有） |
| **确收预算预测** | `src/bdms/modules/revenue_forecast/` | **v1.0 新增**：基于上一账期财报的实时/动态确认收入预估（Part A）+ ONES 动态占位（Part B） |
| 看板 | `src/bdms/modules/dashboard/` | 概览看板 |
| 基础数据 | `src/bdms/modules/master_data/` | 主数据维护 |
| 合同管理 | `src/bdms/modules/contract_management/` | 合同台账 |
| 利润管理 | `src/bdms/modules/profit_management/` | 利润分析 |
| 项目管理 | `src/bdms/modules/project_management/` | 项目台账 |
| 集成 | `src/bdms/modules/integration/` | 外部系统对接 |
| 设置 | `src/bdms/modules/settings/` | 系统设置 |

## 确收预算预测（revenue_forecast v1.0）

基于**已提供的上一账期财报**（`2026年计划确收&实际确收对比表*.xlsx`）生成双口径预估：

- **锁定口径**：仅按交付预计完成时间（col3）落在 2026 年的到期项 → **1.38 亿**
- **动态口径**：到期 + 流程中待确收（IN_PIPELINE）→ **1.71 亿**
- 输出：锁定/动态/实际/差异四套数字 + 按月分布 + 明细下钻 + 风险/排除/跨年清单 + Excel 导出（5 sheets）
- **Part B（ONES 实时动态）v1.0 仅占位**：`NotConfiguredProvider` 恒 `not_configured`，fetch fail-closed

设计/验收文档（v1.0）：`PRD` / `DESIGN-OUTLINE` / `DESIGN-DETAIL` / `IMPLEMENTATION-PLAN` / `OPERATIONS` / `VERIFICATION`（均带 `-REVENUE-FORECAST-v1.0` 后缀）。

### 快速验证

```bash
cd L4-proprietary/components/bdms
PYTHONPATH=src python3 -m pytest tests/test_forecast_core.py \
  tests/test_forecast_repository.py tests/test_forecast_api.py \
  tests/test_forecast_export.py -q        # 69 passed
```

### 启动

```bash
python3 -m uvicorn bdms.web.main:app --host 127.0.0.1 --port 8000
# 打开 http://127.0.0.1:8000/forecast
```

## 测试

```bash
cd L4-proprietary/components/bdms
PYTHONPATH=src python3 -m pytest -q --ignore=tests/test_e2e_v21.py --ignore=tests/visual
# 全量非 e2e/visual 回归：409 passed / 16 skipped / 0 failed
```

- `pytest.ini`：`addopts = -m "not slow"`（e2e/visual 单独跑）
- E2E（需真实浏览器 + 在线服务）：`tests/test_e2e_v21.py`、`tests/visual/`
