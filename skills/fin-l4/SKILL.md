---
name: fin-l4
description: "家庭及个人理财管理系统 FIN-L4：记账、预算、贷款、保险、投资、报表、导出。数据全本地 SQLite，Web UI + CLI + OpenClaw 三通道。"
user-invocable: true
---

# FIN-L4 家庭及个人理财管理系统

> L4 专有业务层，继承 L3 通用理财引擎（FIN-001~006）。
> 数据全本地（SQLite），不连银行/券商，手动录入 + CSV 导入。

## 依赖组件

- **L3 通用引擎**：`fin001_account` ~ `fin006_advisor`（纯计算，零副作用）
- **L2 持久化**：SQLite + Repository 模式
- **L2 Office 文档生成**：`openpyxl`（Excel）+ `python-docx`（Word）

## When to Use

- 用户需要记账（复式记账、试算平衡、对账）
- 用户需要管理预算（月度预算、执行追踪、超支预警）
- 用户需要管理贷款（创建、还款计划、提前还款、结清）
- 用户需要管理保险（保单、现金价值、退保、保障缺口）
- 用户需要管理投资（组合、买卖、盈亏、资产配置、再平衡）
- 用户需要生成报表（资产负债表、收支汇总、现金流）
- 用户需要导出报表（Excel / Word）
- 用户需要理财建议（健康诊断、债务优化、资产配置）
- 用户需要同步利率（LPR、央行利率）
- 用户需要导入 CSV 银行流水

## Quick Start

```bash
# 启动 Web UI（端口 8500）
cd /Users/bangcle/.openclaw/workspace/finance-engine
PYTHONPATH=. python3 fin_l4/run_web.py

# CLI 使用
PYTHONPATH=. python3 -m fin_l4.cli --help
PYTHONPATH=. python3 -m fin_l4.cli family create --name "Rex 家庭"
PYTHONPATH=. python3 -m fin_l4.cli account list
PYTHONPATH=. python3 -m fin_l4.cli report balance-sheet
PYTHONPATH=. python3 -m fin_l4.cli export balance-sheet --output report.xlsx
```

## Architecture

```
交互层:   Web UI (FastAPI :8500) + CLI (finctl) + OpenClaw (本 skill)
服务层:   Account / Transaction / Budget / Loan / Insurance / Portfolio / Report / Advise / Export / Import / CategoryEngine
数据层:   SQLite (fin4_ 前缀) + 14 张表 + Repository 模式
外部:     DataSource (利率/行情/汇率) + LinkManager (系统链接)
安全:     AES-256-GCM 加密 + 审计日志 + 加密备份
```

## API 端点

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | / | 仪表盘 |
| GET | /budget | 预算管理页 |
| GET | /import | CSV 导入页 |
| GET | /loans | 贷款列表 |
| GET | /loans/{id} | 贷款详情 |
| POST | /loans/{id}/prepay | 提前还款 |
| POST | /loans/{id}/close | 结清贷款 |
| GET | /insurance | 保险列表 |
| GET | /insurance/{id} | 保单详情 |
| POST | /insurance/{id}/surrender | 退保 |
| GET | /insurance/coverage-gap | 保障缺口分析 |
| GET | /portfolio | 投资列表 |
| GET | /portfolio/{id} | 组合详情 |
| GET | /api/v1/accounts | 账户列表 |
| GET | /api/v1/accounts/trial-balance | 试算平衡 |
| POST | /api/v1/transactions | 记账 |
| GET | /api/v1/budgets | 预算列表 |
| POST | /api/v1/budgets | 设置预算 |
| GET | /api/v1/budgets/status | 预算执行状态 |
| GET | /api/v1/loans/{id} | 贷款详情+还款计划 |
| POST | /api/v1/loans/{id}/prepay | 提前还款 |
| GET | /api/v1/insurance/{id} | 保单详情 |
| GET | /api/v1/insurance/coverage-gap | 保障缺口 |
| GET | /api/v1/portfolios/{id} | 组合详情 |
| GET | /api/v1/reports/balance-sheet | 资产负债表 |
| GET | /api/v1/reports/income | 收支汇总 |
| GET | /api/v1/reports/cashflow | 月度现金流 |
| GET | /api/v1/export/balance-sheet | 导出 Excel |
| GET | /api/v1/export/transactions | 导出 Excel |
| GET | /api/v1/export/report | 导出 Word |

## CLI 命令组

| 命令 | 说明 |
|---|---|
| family create/list | 家庭管理 |
| account create/list/balance/trial-balance | 账户管理 |
| txn add/list | 记账 |
| budget set/status | 预算管理 |
| loan create/list/schedule/summary | 贷款管理 |
| insurance create/list | 保险管理 |
| portfolio create/list/buy/performance | 投资管理 |
| report balance-sheet/income/cashflow | 报表 |
| rate sync/latest | 利率管理 |
| export balance-sheet/transactions/report | 导出 |
| advise health | 理财建议 |

## 关键约束

1. **数据全本地**：SQLite (`~/.fin-l4/fin_l4.db`)，不上云
2. **不连银行/券商**：手动录入 + CSV 导入
3. **复式记账**：每笔交易必须有借方+贷方，试算平衡必须通过
4. **Decimal 精度**：所有金额用 Decimal，ROUND_HALF_UP，保留 2 位
5. **表前缀**：`fin4_`（L4）/ `fin_`（L3）
6. **零副作用**：L3 引擎不写数据库、不发网络请求（利率除外）

## 测试

```bash
cd /Users/bangcle/.openclaw/workspace/finance-engine
PYTHONPATH=. python3 -m pytest tests/test_fin_l4_db.py tests/test_fin_l4_services.py tests/test_fin_l4_e2e.py tests/test_fin_l4_m2.py tests/test_fin_l4_m3.py -v
```

## 文件结构

```
finance-engine/
├── fin001_account/ ~ fin006_advisor/    # L3 通用引擎
├── fin_l4/                               # L4 管理系统
│   ├── cli.py                            # CLI 入口
│   ├── run_web.py                        # Web 启动
│   ├── db/__init__.py                    # 迁移 + 14 表
│   ├── db/repositories.py                # 12+ Repository
│   ├── services/                         # 10 个服务
│   │   ├── account_svc.py
│   │   ├── txn_svc.py
│   │   ├── budget_svc.py
│   │   ├── category_engine.py
│   │   ├── import_svc.py
│   │   ├── loan_svc.py
│   │   ├── insurance_svc.py
│   │   ├── portfolio_svc.py
│   │   ├── report_svc.py
│   │   ├── advise_svc.py
│   │   ├── rate_svc.py
│   │   └── export_svc.py
│   ├── web/                              # Web UI
│   │   ├── main.py                       # FastAPI 路由
│   │   ├── api.py                        # REST API
│   │   └── templates/                    # Jinja2 模板
│   ├── external/                         # 外部数据源
│   ├── integration/                      # 系统链接
│   └── security/                         # 安全模块
└── tests/                                # 77 个测试
```

## 里程碑状态

| 里程碑 | 状态 | 内容 |
|---|---|---|
| M1 | ✅ | 骨架 + 数据层 + 8 服务 + Web UI + CLI |
| M2 | ✅ | 智能分类 + 预算管理 + CSV 导入 |
| M3 | ✅ | 贷款/保险/投资深度功能 |
| M4 | ✅ | Excel/Word 导出 + CLI 完整 + Skill |
| M5 | 🔄 | 全量测试 + UI 优化 |
