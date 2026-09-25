# DESIGN-DETAIL-PROFIT-MANAGEMENT-v2.1.md

> Bangcle Delivery Management System v2.1 — 项目利润管理模块详细设计
> 版本：v2.1 Detail r2（2026-09-24）
> 层级：L4 专有业务层
> 父文档：`DESIGN-OUTLINE-v2.1.md` §3.5
> 依赖模块：`revenue`（收入数据）、`integration`（数据导入）、`project_management`（项目主数据）
> 状态：待 Rex 审核

## 目录

1. [模块概述](#1-模块概述)
2. [OS 依赖与限制](#2-os-依赖与限制)
3. [技术方案](#3-技术方案)
4. [接口设计](#4-接口设计)
5. [数据模型](#5-数据模型)
6. [成本核算规则](#6-成本核算规则)
7. [利润计算逻辑](#7-利润计算逻辑)
8. [成本异常告警规则](#8-成本异常告警规则)
9. [收入同步机制](#9-收入同步机制)
10. [利润报表设计](#10-利润报表设计)
11. [错误处理](#11-错误处理)
12. [CLI 命令](#12-cli-命令)
13. [测试策略](#13-测试策略)
附录 A：[配置项清单](#附录-a配置项清单)
附录 B：[复用资产清单与重构方案](#附录-b复用资产清单与重构方案)
[变更历史](#变更历史)

## 0. 版本记录

| 版本 | 日期 | 变更说明 |
|---|---|---|
| v2.1 Detail r1 | 2026-09-22 | 初版 |
| v2.1 Detail r2 | 2026-09-24 | Rex 审核反馈 2 条：PMP/EVM 要素补全占位 + 复用资产迁移重构方案 |

---

## 1. 模块概述

### 1.1 业务域

项目利润管理（Profit Management）是 BDMS v2.1 的财务核心模块，负责：
- **收入确认**：从确收模块自动同步项目收入数据
- **成本核算**：归集工时成本（工时×费率）、设备折旧、差旅费用
- **利润计算**：收入 - 成本 = 利润，按项目/部门/时间维度聚合
- **利润报表**：多维度报表生成与导出
- **成本异常告警**：成本超预算 10% 自动告警

### 1.2 与其他模块交互

```
┌──────────────────────────────────────────────────────────────────┐
│                    profit_management                               │
│                                                                  │
│  ┌─────────────┐    ┌─────────────┐    ┌──────────────────┐     │
│  │ ProfitEngine │    │ ProfitService│    │ ProfitImporter   │     │
│  │ (纯计算)     │    │ (事务编排)   │    │ (数据导入)       │     │
│  └──────┬──────┘    └──────┬──────┘    └────────┬─────────┘     │
│         │                  │                     │               │
│  ┌──────┴──────────────────┴─────────────────────┴──────────┐   │
│  │                    数据层 (pf_* 表)                         │   │
│  └────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
        ▲                    ▲                      ▲
        │                    │                      │
   ┌────┴────┐          ┌────┴────┐           ┌────┴────┐
   │ revenue  │          │ project │           │integrat.│
   │ 收入数据  │          │ 项目主数据│           │ 导入数据  │
   └─────────┘          └─────────┘           └─────────┘
```

**交互规则**：

| 方向 | 模块 | 数据 | 方式 |
|---|---|---|---|
| 入 | `revenue` | 项目确认收入（按期间） | DB 共享 `rr_sheet_row` + 事件通知 |
| 入 | `project_management` | 项目预算、部门信息 | DB 共享 `pm_projects` 只读 |
| 入 | `integration` | 工时/设备/差旅原始数据 | `int_staging` → `pf_*` 落地 |
| 出 | `dashboard` | 利润 KPI 数据 | DB 共享 `pf_profit_snapshot` 只读 |

**解耦原则**：模块间不直接调用 Python 函数，通过 DB 共享数据 + `outbox_events` 事件总线解耦。

### 1.3 业界最佳实践与 PMP 核心要素

#### 1.3.1 业界最佳实践参考

| 产品/方案 | 核心能力 | 借鉴点 | 本系统落地 |
|---|---|---|---|
| **SAP CO-PA** | 盈利能力分析 | 收入-成本=利润，按项目/部门/时间多维聚合 | ProfitEngine.compute_profit() |
| **Oracle P6** | 项目成本控制 | 预算 vs 实际偏差分析 + 告警 | check_budget_alert() |
| **QuickBooks** | 费用归集 | 工时×费率 + 设备折旧 + 差旅 | CostEngine 成本核算 |
| **NetSuite** | 实时利润 | 收入确认 + 成本归集 → 实时利润快照 | pf_profit_snapshot |
| **Anaplan** | 多维聚合 | 项目/部门/时间三维交叉分析 | 利润报表多维度 |
| **Tableau/Power BI** | 成本可视化 | 成本构成饼图 + 趋势折线 | dashboard 集成 |
| **Stripe Revenue** | 收入确认 | 按期间确认收入，支持递延 | revenue 模块对齐 |
| **Workday Financial** | 异常检测 | 成本超预算自动告警 + 工作流 | outbox_events 告警 |

#### 1.3.2 PMP 挣值管理（EVM）核心要素

> PMBOK 第 7 版「测量绩效域」核心工具。v2.1 实现基础三要素，其余占位。

| 要素 | 英文/公式 | 状态 | 说明 |
|---|---|---|---|
| **计划价值** | PV (Planned Value) | ✅ v2.1 | 到某时点计划完成工作的预算成本 |
| **挣值** | EV (Earned Value) | ✅ v2.1 | 到某时点实际完成工作的预算成本 |
| **实际成本** | AC (Actual Cost) | ✅ v2.1 | 到某时点实际发生的成本（cost_total） |
| **进度偏差** | SV = EV - PV | 📋 v2.2 占位 | >0 进度超前，<0 进度滞后 |
| **成本偏差** | CV = EV - AC | 📋 v2.2 占位 | >0 成本节约，<0 成本超支 |
| **进度绩效指数** | SPI = EV / PV | 📋 v2.2 占位 | <1 进度落后 |
| **成本绩效指数** | CPI = EV / AC | 📋 v2.2 占位 | <1 成本超支 |
| **完工估算** | EAC = BAC / CPI | 📋 v2.2 占位 | 按当前绩效预测总成本 |
| **完工尚需估算** | ETC = EAC - AC | 📋 v2.2 占位 | 剩余工作预测成本 |
| **完工偏差** | VAC = BAC - EAC | 📋 v2.2 占位 | 预测最终盈亏 |
| **TCPI** | (BAC-EV)/(BAC-AC) | 📋 v2.2 占位 | 完工尚需绩效指数 |

**v2.1 EVM 数据模型占位**（pf_profit_snapshot 字段已预留）
：
```sql
-- pf_profit_snapshot 表新增字段（v2.2 激活）
ALTER TABLE pf_profit_snapshot ADD COLUMN pv REAL DEFAULT 0;   -- 计划价值
ALTER TABLE pf_profit_snapshot ADD COLUMN ev REAL DEFAULT 0;   -- 挣值
-- ac = cost_total（已有）
-- sv/cv/spi/cpi/eac/etv/vac/tcpi 为计算列，不落盘，实时计算
```

#### 1.3.3 PMP 成本管理其他核心要素

| 要素 | PMBOK 知识领域 | 状态 | 说明 |
|---|---|---|---|
| **成本估算** | 规划过程组 | 📋 v2.2 占位 | 类比/参数/自下而上估算，项目立项时预估 |
| **成本预算** | 规划过程组 | ✅ v2.1 | budget 字段（pm_projects 同步） |
| **成本控制** | 监控过程组 | ✅ v2.1 | budget_usage + 告警 |
| **现金流管理** | 财务管理 | 📋 v2.2 占位 | 收付款计划 vs 实际，项目级现金流预测 |
| **间接成本分摊** | 成本管理 | 📋 v2.2 占位 | 管理成本/公共成本按比例分摊到项目 |
| **成本基准** | 成本管理 | 📋 v2.2 占位 | 批准的随时间预算（BAC 基线） |
| **应急储备** | 估算依据 | 📋 v2.2 占位 | 应对已识别风险（已知-未知） |
| **管理储备** | 估算依据 | 📋 v2.2 占位 | 应对未知风险（未知-未知） |
| **投资回报率** | 财务指标 | 📋 v2.2 占位 | ROI = 利润 / 投资额 |
| **内部收益率** | 财务指标 | 📋 远期占位 | IRR（考虑资金时间价值） |
| **回收期** | 财务指标 | 📋 远期占位 | 投资回收时间 |

**v2.2 占位表结构**（预创建，不激活）：
```sql
-- pf_cash_flow（现金流，v2.2 占位）
CREATE TABLE IF NOT EXISTS pf_cash_flow (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    period TEXT NOT NULL,
    plan_inflow REAL DEFAULT 0,        -- 计划流入（回款计划）
    actual_inflow REAL DEFAULT 0,      -- 实际流入
    plan_outflow REAL DEFAULT 0,       -- 计划流出（付款计划）
    actual_outflow REAL DEFAULT 0,     -- 实际流出
    net_cash_flow REAL DEFAULT 0,      -- 净现金流
    created_at TEXT DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (project_id) REFERENCES pm_projects(id),
    UNIQUE(project_id, period)
);

-- pf_cost_overhead（间接成本分摊，v2.2 占位）
CREATE TABLE IF NOT EXISTS pf_cost_overhead (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period TEXT NOT NULL,
    overhead_type TEXT NOT NULL,       -- management / shared / facility
    total_amount REAL NOT NULL,        -- 期间总间接成本
    allocation_rule TEXT NOT NULL,     -- revenue_ratio / headcount_ratio / custom
    allocation_basis TEXT,             -- 分摊基数 JSON
    created_at TEXT DEFAULT (datetime('now','localtime')),
    UNIQUE(period, overhead_type)
);
```

### 1.4 设计原则

| 原则 | 落地方式 |
|---|---|
| **纯计算优先** | `ProfitEngine.compute_profit()` 无 DB 写入，输入→输出纯函数 |
| **幂等可重入** | 利润快照按 `(project_id, period)` 唯一键，重复计算覆盖 |
| **成本可追溯** | 每项成本关联来源（工时记录/设备记录/差旅记录），可下钻 |
| **告警可配置** | 告警阈值（默认 10%）通过 `settings` 模块可配置 |
| **复用资产重构** | 引用已有代码（import/组合/继承），禁止复制粘贴 |

---

## 2. OS 依赖与限制

> 项目利润管理模块依赖工时数据（浏览器自动化）和差旅数据（系统导入），间接依赖 integration 模块。

| 功能 | OS 依赖 | macOS | Windows | Linux | 说明 |
|---|---|---|---|---|---|
| 工时数据导入 | 浏览器自动化 | ✅ osascript（已验证） | 🔶 Playwright（待适配） | 🔶 Playwright（待适配） | 间接依赖 integration I-03 |
| 差旅数据导入 | 系统导入（Excel/CSV） | ✅ 支持 | ✅ 支持 | ✅ 支持 | openpyxl，纯 Python |
| 成本核算 | SQLite SQL | ✅ 支持 | ✅ 支持 | ✅ 支持 | 纯 SQL，OS 无关 |
| 利润计算 | SQLite SQL | ✅ 支持 | ✅ 支持 | ✅ 支持 | 纯 SQL，OS 无关 |
| 预算告警 | SQLite + 事件 | ✅ 支持 | ✅ 支持 | ✅ 支持 | 纯 SQL，OS 无关 |
| 利润报表导出 | openpyxl | ✅ 支持 | ✅ 支持 | ✅ 支持 | 纯 Python |
| Web UI (FastAPI) | uvicorn + Jinja2 | ✅ 支持 | ✅ 支持 | ✅ 支持 | 纯 Python |
| CLI (Click) | click | ✅ 支持 | ✅ 支持 | ✅ 支持 | 纯 Python |

**间接依赖链**：
```
profit_management
├── 工时数据 → integration I-03 → 浏览器自动化
│   ├── macOS: osascript + Chrome（已验证）
│   ├── Linux: Playwright Headless（待验证）
│   └── Windows: Playwright Headless（待开发）
├── 差旅数据 → 系统导入（Excel/CSV，全平台）
├── 成本/利润/告警 → SQLite（OS 无关）
└── 报表/Web/CLI → 纯 Python（全平台）
```

## 3. 技术方案

### 2.1 架构图

```
┌─────────────────────────────────────────────────────────────┐
│                        CLI / API 层                          │
│  bdms profit summary / bdms profit report / bdms profit alert│
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────┴──────────────────────────────────┐
│                      ProfitService                           │
│  submit_timesheet / approve_timesheet / import_travel_cost   │
│  get_profit_report / list_projects_profit / check_budget     │
└──────────┬───────────────────────────────┬──────────────────┘
           │                               │
┌──────────┴──────────┐      ┌─────────────┴────────────────┐
│   ProfitEngine       │      │   ProfitImporter              │
│   compute_profit     │      │   import_travel_cost_excel    │
│   get_cost_summary   │      │   import_timesheet_csv        │
│   check_budget_alert │      │   import_device_csv           │
└──────────┬──────────┘      └─────────────┬────────────────┘
           │                               │
┌──────────┴───────────────────────────────┴────────────────┐
│                    数据访问层 (SQLite)                       │
│  pf_timesheet / pf_cost_item / pf_profit_snapshot           │
│  + 读 rr_sheet_row / pm_projects / ct_staff_rates           │
└────────────────────────────────────────────────────────────┘
```

### 2.2 文件结构

```
modules/profit_management/
├── __init__.py
├── engine.py          # ProfitEngine — 利润计算引擎（含成本归集，纯计算）
├── service.py         # ProfitService — 业务服务层（工时提交/审批 + 事务编排）
├── importer.py        # ProfitImporter — 成本数据导入（工时/设备/差旅 Excel/CSV）
├── alert.py           # BudgetAlertService — 预算告警服务
├── exporter.py        # ProfitExporter — 利润报表导出（含成本明细）
└── cli.py             # CLI 命令注册

# 迁移源（迁移重构后下线，见附录 B）
modules/project_management/cost/
└── _deprecated_compat.py  # 兼容层（DeprecationWarning + 转发，v2.2 移除）
```

### 2.3 依赖关系（迁移后）

```python
# profit_management（自包含，无跨模块 import）
from bdms.modules.base import BaseEngine, BaseService, BaseImporter, BaseExporter  # 基类继承
from bdms.core.db import get_connection, transaction                              # DB 基础设施

# 收入/项目数据通过 DB 共享（非 import，见附录 B.3）
# 事件通过 outbox_events 表（DB 共享）
```

**重构策略**（详见附录 B）：
- `project_management/cost/` 的引擎/服务/导入器/导出器**迁移重构**到本模块（逻辑内核保留，接口按新契约对齐）
- `ct_*` 表数据迁移到 `pf_*` 新表，旧表转 VIEW 兼容
- 迁移完成后 `project_management/cost/` 下线（v2.2）
- 本模块不 import revenue/project_management 任何代码，全部通过 DB 共享解耦

---

## 4. 接口设计

### 3.1 ProfitEngine

```python
class ProfitEngine(BaseEngine):
    """利润计算引擎（纯计算，无 DB 写入）。

    核心公式：profit = revenue - cost
    cost = labor_cost + device_cost + travel_cost
    """

    def compute_profit(
        self,
        project_id: int,
        period: str,              # YYYY-MM
        revenue_override: Optional[float] = None,  # 用于模拟计算
    ) -> dict:
        """计算项目在某期间的利润。

        Args:
            project_id: 项目 ID
            period: 会计期间 YYYY-MM
            revenue_override: 收入覆盖值（None 则从 revenue 模块同步）

        Returns:
            {
                "project_id": int,
                "period": str,
                "revenue": float,          # 收入（元）
                "cost": float,             # 总成本（元）
                "profit": float,           # 利润（元）
                "profit_margin": float,    # 利润率（0.0~1.0）
                "cost_breakdown": {
                    "labor_cost": float,
                    "device_cost": float,
                    "travel_cost": float,
                },
                "budget": float,           # 项目预算
                "budget_usage": float,     # 预算使用率（0.0~1.0+）
            }

        Raises:
            NotFoundError: 项目不存在
            ValueError: period 格式非法
        """

    def get_cost_summary(
        self,
        project_id: int,
        period: Optional[str] = None,    # None = 全部期间
    ) -> dict:
        """获取项目成本汇总（委托 CostEngine）。

        Returns:
            {
                "total": float,
                "labor_cost": float,
                "device_cost": float,
                "travel_cost": float,
                "total_hours": float,
                "by_person": [{"person_id": str, "hours": float, "rate": float, "cost": float}],
                "by_month": [{"month": str, "labor_cost": float, "device_cost": float, "travel_cost": float, "total": float}],
            }
        """

    def check_budget_alert(
        self,
        project_id: int,
        threshold: float = 0.10,          # 告警阈值，默认 10%
    ) -> list[dict]:
        """检查项目成本是否超预算阈值。

        Args:
            project_id: 项目 ID
            threshold: 超预算比例阈值（0.10 = 10%）

        Returns:
            [
                {
                    "alert_level": "warning" | "critical",
                    "project_id": int,
                    "project_name": str,
                    "budget": float,
                    "actual_cost": float,
                    "over_budget_pct": float,    # 超预算百分比
                    "message": str,
                }
            ]
            无异常返回空列表 []
        """

    def aggregate_by_department(
        self,
        period: str,
        dept: Optional[str] = None,
    ) -> list[dict]:
        """按部门维度聚合利润数据。

        Returns:
            [
                {
                    "dept": str,
                    "project_count": int,
                    "total_revenue": float,
                    "total_cost": float,
                    "total_profit": float,
                    "profit_margin": float,
                }
            ]
        """

    def aggregate_by_period(
        self,
        project_id: int,
        periods: list[str],                # ["2026-01", "2026-02", ...]
    ) -> list[dict]:
        """按时间维度聚合利润数据。

        Returns:
            [
                {
                    "period": str,
                    "revenue": float,
                    "cost": float,
                    "profit": float,
                    "profit_margin": float,
                }
            ]
        """
```

### 3.2 ProfitService

```python
class ProfitService(BaseService):
    """利润管理服务层（事务编排 + 权限校验）。"""

    def submit_timesheet(
        self,
        project_id: int,
        person_id: str,
        work_date: str,           # YYYY-MM-DD
        hours: float,
        work_type: str = "",
        description: str = "",
        submitter: str = "",
    ) -> dict:
        """提交工时记录。

        Returns:
            {"timesheet_id": int, "status": "pending", "message": str}

        Raises:
            ValidationError: 参数非法（hours > 24, 未来日期等）
            NotFoundError: 项目不存在
        """

    def approve_timesheet(
        self,
        timesheet_id: int,
        approver: str,
        approved: bool = True,
        comment: str = "",
    ) -> dict:
        """审批工时记录。

        Returns:
            {"timesheet_id": int, "status": "approved"|"rejected", "message": str}

        Raises:
            NotFoundError: 工时记录不存在
            StateTransitionError: 状态非 pending 不可审批
            PermissionError: 审批人无权限
        """

    def import_travel_cost(
        self,
        project_id: int,
        file_path: str,           # Excel 或 CSV 文件路径
        operator: str = "",
    ) -> dict:
        """导入差旅费用（Excel/CSV）。

        Returns:
            {
                "imported": int,        # 成功导入条数
                "failed": int,          # 失败条数
                "errors": [{"row": int, "error": str}],
                "total_amount": float,  # 导入总金额
            }

        Raises:
            ValidationError: 文件格式不支持或缺少必要列
            FileNotFoundError: 文件不存在
        """

    def get_profit_report(
        self,
        project_id: int,
        period: str,               # YYYY-MM
    ) -> dict:
        """获取项目利润报表（单项目单期间）。

        Returns:
            {
                "project": {项目基本信息},
                "period": str,
                "revenue": float,
                "cost": float,
                "profit": float,
                "profit_margin": float,
                "cost_detail": {...},       # 同 get_cost_summary
                "revenue_detail": {...},    # 收入明细
                "budget_status": "normal" | "warning" | "over_budget",
                "monthly_trend": [...],      # 近 6 个月趋势
            }
        """

    def list_projects_profit(
        self,
        period: str,
        dept: Optional[str] = None,
        status: Optional[str] = None,
        sort_by: str = "profit_margin",
        page: int = 1,
        page_size: int = 50,
    ) -> dict:
        """列出多项目利润汇总（支持筛选/排序/分页）。

        Returns:
            {
                "total": int,
                "page": int,
                "page_size": int,
                "items": [
                    {
                        "project_id": int,
                        "project_name": str,
                        "dept": str,
                        "pm": str,
                        "status": str,
                        "revenue": float,
                        "cost": float,
                        "profit": float,
                        "profit_margin": float,
                        "budget_usage": float,
                    }
                ]
            }
        """

    def sync_revenue(
        self,
        project_id: int,
        period: str,
        force: bool = False,
    ) -> dict:
        """从 revenue 模块同步收入数据。

        Args:
            project_id: 项目 ID
            period: 会计期间
            force: 强制重新同步（覆盖已有数据）

        Returns:
            {"synced": bool, "revenue": float, "source": str}

        Raises:
            NotFoundError: revenue 模块无该项目期间数据
        """
```

### 3.3 BudgetAlertService

```python
class BudgetAlertService:
    """预算告警服务。"""

    def check_all_projects(
        self,
        period: str,
        threshold: float = 0.10,
    ) -> list[dict]:
        """检查所有活跃项目的预算告警。"""

    def get_alert_history(
        self,
        project_id: Optional[int] = None,
        period: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict]:
        """查询告警历史。"""

    def resolve_alert(
        self,
        alert_id: int,
        resolver: str,
        resolution: str = "",
    ) -> dict:
        """确认/解决告警。"""
```

### 3.4 ProfitImporter

```python
class ProfitImporter(BaseImporter):
    """利润数据导入器（扩展 CostImporter 能力）。"""

    # 差旅 Excel 列映射
    TRAVEL_COLUMN_MAP = {
        "姓名": "employee_name",
        "日期": "travel_date",
        "目的地": "destination",
        "费用类型": "cost_type",
        "金额": "amount",
        "备注": "description",
    }

    def import_travel_excel(
        self,
        project_id: int,
        file_path: str,
    ) -> dict:
        """导入差旅费用 Excel。

        支持列名：姓名/日期/目的地/费用类型/金额/备注
        支持多 Sheet，自动识别"差旅" Sheet。
        """

    def import_device_csv(
        self,
        project_id: int,
        file_path: str,
    ) -> dict:
        """导入设备使用 CSV。

        CSV 格式：device_name,start_date,end_date,cost_per_day
        """
```

---

## 5. 数据模型

### 4.1 pf_timesheet（工时记录）

> **迁移说明**：本表是 `ct_timesheets` 的迁移目标（见附录 B.1）。迁移完成后 `ct_timesheets` 转为 VIEW 只读，数据存储在本表。

```sql
CREATE TABLE IF NOT EXISTS pf_timesheet (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    person_id TEXT NOT NULL,
    work_date TEXT NOT NULL,               -- YYYY-MM-DD
    hours REAL NOT NULL CHECK (hours > 0 AND hours <= 24),
    work_type TEXT,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'submitted',  -- submitted/approved/rejected
    approver TEXT,
    approved_by TEXT,
    approved_at TEXT,
    created_at TEXT DEFAULT (datetime('now','localtime')),
    updated_at TEXT DEFAULT (datetime('now','localtime')),
    deleted_at TEXT DEFAULT NULL,
    FOREIGN KEY (project_id) REFERENCES pm_projects(id)
);
CREATE INDEX IF NOT EXISTS idx_pf_ts_project ON pf_timesheet(project_id);
CREATE INDEX IF NOT EXISTS idx_pf_ts_date ON pf_timesheet(work_date);
CREATE INDEX IF NOT EXISTS idx_pf_ts_status ON pf_timesheet(status);
CREATE INDEX IF NOT EXISTS idx_pf_ts_person ON pf_timesheet(person_id);

-- 迁移后旧表兼容 VIEW（v2.2 移除）
CREATE VIEW IF NOT EXISTS ct_timesheets AS
SELECT id, project_id, person_id, work_date, hours, work_type, description,
       status, approver, approved_by, approved_at, created_at, deleted_at
FROM pf_timesheet;
```

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | INTEGER | PK AUTOINCREMENT | 工时记录 ID |
| project_id | INTEGER | FK → pm_projects(id) | 所属项目 |
| person_id | TEXT | NOT NULL | 人员标识（姓名） |
| work_date | TEXT | NOT NULL (YYYY-MM-DD) | 工作日期 |
| hours | REAL | NOT NULL, >0, ≤24 | 工时数 |
| work_type | TEXT | | 工作类型（实施/开发/差旅等） |
| description | TEXT | | 工作描述 |
| status | TEXT | DEFAULT 'submitted' | submitted/approved/rejected |
| approver | TEXT | | 审批人 |
| approved_by | TEXT | | 最终审批人 |
| approved_at | TEXT | | 审批时间 |
| created_at | TEXT | DEFAULT datetime('now','localtime') | 创建时间 |
| deleted_at | TEXT | DEFAULT NULL | 软删除标记 |

### 4.2 pf_cost_item（成本项明细）

```sql
CREATE TABLE IF NOT EXISTS pf_cost_item (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    period TEXT NOT NULL,                   -- 所属期间 YYYY-MM
    cost_type TEXT NOT NULL,                -- labor / device / travel
    source_table TEXT NOT NULL,             -- 来源表名
    source_id INTEGER NOT NULL,             -- 来源记录 ID
    amount REAL NOT NULL DEFAULT 0,         -- 成本金额（元）
    currency TEXT DEFAULT 'CNY',            -- 币种
    description TEXT,                       -- 成本说明
    allocated_at TEXT NOT NULL,             -- 归集时间
    created_at TEXT DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (project_id) REFERENCES pm_projects(id)
);
CREATE INDEX IF NOT EXISTS idx_pf_cost_project ON pf_cost_item(project_id);
CREATE INDEX IF NOT EXISTS idx_pf_cost_period ON pf_cost_item(period);
CREATE INDEX IF NOT EXISTS idx_pf_cost_type ON pf_cost_item(cost_type);
CREATE INDEX IF NOT EXISTS idx_pf_cost_source ON pf_cost_item(source_table, source_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_pf_cost_unique
    ON pf_cost_item(project_id, period, cost_type, source_table, source_id);
```

**设计说明**：
- `pf_cost_item` 是成本归集中间表，将分散在 `ct_timesheets` / `ct_device_usage` / `ct_travel_costs` 中的成本统一归集到项目维度
- `(project_id, period, cost_type, source_table, source_id)` 唯一约束保证幂等——重复归集不重复计算
- `cost_type` 枚举：`labor`（工时）、`device`（设备）、`travel`（差旅）

### 4.3 pf_profit_snapshot（利润快照）

```sql
CREATE TABLE IF NOT EXISTS pf_profit_snapshot (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    period TEXT NOT NULL,                   -- 会计期间 YYYY-MM
    -- 收入
    revenue REAL NOT NULL DEFAULT 0,        -- 确认收入（元）
    revenue_source TEXT,                    -- 收入数据来源
    revenue_synced_at TEXT,                 -- 收入同步时间
    -- 成本
    cost_labor REAL NOT NULL DEFAULT 0,     -- 工时成本
    cost_device REAL NOT NULL DEFAULT 0,    -- 设备成本
    cost_travel REAL NOT NULL DEFAULT 0,    -- 差旅成本
    cost_total REAL NOT NULL DEFAULT 0,     -- 总成本
    -- 利润
    profit REAL NOT NULL DEFAULT 0,         -- 利润 = revenue - cost_total
    profit_margin REAL DEFAULT 0,           -- 利润率 = profit / revenue
    -- 预算
    budget REAL DEFAULT 0,                  -- 项目预算
    budget_usage REAL DEFAULT 0,            -- 预算使用率 = cost_total / budget
    -- 元数据
    status TEXT DEFAULT 'draft',            -- draft / confirmed / archived
    computed_at TEXT NOT NULL,              -- 计算时间
    confirmed_by TEXT,                      -- 确认人
    confirmed_at TEXT,                      -- 确认时间
    created_at TEXT DEFAULT (datetime('now','localtime')),
    updated_at TEXT DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (project_id) REFERENCES pm_projects(id),
    UNIQUE(project_id, period)
);
CREATE INDEX IF NOT EXISTS idx_pf_snapshot_project ON pf_profit_snapshot(project_id);
CREATE INDEX IF NOT EXISTS idx_pf_snapshot_period ON pf_profit_snapshot(period);
CREATE INDEX IF NOT EXISTS idx_pf_snapshot_status ON pf_profit_snapshot(status);
```

**设计说明**：
- 利润快照是**物化视图**概念——将计算结果持久化，避免每次查询重新计算
- `(project_id, period)` 唯一约束保证幂等——同一项目同一期间只有一条快照
- `status` 状态机：`draft`（计算中）→ `confirmed`（已确认，不可修改）→ `archived`（已归档）
- 快照更新策略：每次成本变更触发重新计算（draft 状态），确认后锁定

### 4.4 pf_budget_alert（预算告警记录）

```sql
CREATE TABLE IF NOT EXISTS pf_budget_alert (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    period TEXT NOT NULL,
    alert_level TEXT NOT NULL,              -- warning / critical
    budget REAL NOT NULL,                   -- 预算金额
    actual_cost REAL NOT NULL,              -- 实际成本
    over_budget_pct REAL NOT NULL,          -- 超预算百分比
    threshold REAL NOT NULL,                -- 触发阈值
    message TEXT,                           -- 告警消息
    status TEXT DEFAULT 'open',             -- open / acknowledged / resolved
    acknowledged_by TEXT,
    acknowledged_at TEXT,
    resolved_by TEXT,
    resolved_at TEXT,
    resolution_note TEXT,
    created_at TEXT DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (project_id) REFERENCES pm_projects(id)
);
CREATE INDEX IF NOT EXISTS idx_pf_alert_project ON pf_budget_alert(project_id);
CREATE INDEX IF NOT EXISTS idx_pf_alert_status ON pf_budget_alert(status);
CREATE INDEX IF NOT EXISTS idx_pf_alert_period ON pf_budget_alert(period);
```

### 4.5 ER 关系图

```
pm_projects (1) ──── (N) pf_cost_item
pm_projects (1) ──── (N) pf_profit_snapshot
pm_projects (1) ──── (N) pf_budget_alert
pm_projects (1) ──── (N) ct_timesheets ──── VIEW ──── pf_timesheet
pm_projects (1) ──── (N) ct_device_usage
pm_projects (1) ──── (N) ct_travel_costs
ct_timesheets (N) ──── (1) ct_staff_rates
rr_sheet_row ──── 收入数据（只读）
```

---

## 6. 成本核算规则

### 5.1 工时成本

**公式**：
```
labor_cost = Σ (hours_i × rate_i)
```

其中：
- `hours_i` = 第 i 条 approved 工时记录的小时数
- `rate_i` = 该人员对应期间的工时单价（从 `ct_staff_rates` 获取）

**计算规则**：
1. 仅 `status = 'approved'` 的工时记录计入成本
2. 人员单价按 `person_name` 从 `ct_staff_rates` 获取最新生效单价
3. 找不到单价的人员，rate = 0（不计算成本，但记录 warning 日志）
4. 同一人同一天同一类型的工时，幂等合并（更新而非新增）

**示例**：
```
张三: 8h × 500元/h = 4,000元
李四: 6h × 800元/h = 4,800元
王五: 4h × 0元/h = 0元（未配置单价，warning）
─────────────────────────────────
labor_cost = 8,800元
```

### 5.2 设备折旧

**公式**：
```
device_cost = Σ total_cost
```

**计算规则**：
1. 设备成本按 `ct_device_usage.total_cost` 直接汇总
2. `total_cost` 由导入时计算：`cost_per_day × usage_days`
3. 设备成本按 `start_date` 所在月份计入对应期间
4. 设备跨月使用时，成本全部计入开始月份（简化处理，不按天分摊）

**折旧方法**：
- 默认：**直线法**（一次性计入使用期间）
- 可选：**按天分摊**（`cost_per_day × 实际使用天数`）
- 配置项：`profit.device_depreciation_method = "straight_line" | "daily"`

### 5.3 差旅费用

**导入格式**：

**Excel 格式**：
| 姓名 | 日期 | 目的地 | 费用类型 | 金额 | 备注 |
|---|---|---|---|---|---|
| 张三 | 2026-06-15 | 北京 | 机票 | 1200.00 | 往返 |
| 张三 | 2026-06-15 | 北京 | 住宿 | 800.00 | 2晚 |
| 李四 | 2026-06-16 | 上海 | 高铁 | 553.50 | 单程 |

**CSV 格式**：
```csv
employee_name,travel_date,destination,cost_type,amount,description
张三,2026-06-15,北京,机票,1200.00,往返
李四,2026-06-16,上海,高铁,553.50,单程
```

**计算规则**：
1. 差旅费用按 `travel_date` 所在月份计入对应期间
2. 费用类型（`cost_type`）仅做分类统计，不影响金额计算
3. 导入时自动去重：同一人同一日期同一金额同一类型的记录视为重复，跳过

### 5.4 成本归集流程

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│ ct_timesheets │    │ct_device_usage│    │ct_travel_costs│
│ (approved)   │    │              │    │              │
└──────┬───────┘    └──────┬───────┘    └──────┬───────┘
       │                   │                   │
       ▼                   ▼                   ▼
┌──────────────────────────────────────────────────────┐
│              pf_cost_item (成本归集)                    │
│  cost_type = labor / device / travel                  │
│  amount = 计算后金额                                   │
│  (project_id, period, cost_type, source_unique)       │
└──────────────────────┬───────────────────────────────┘
                       │
                       ▼
              pf_profit_snapshot
```

---

## 7. 利润计算逻辑

### 6.1 核心公式

```
profit = revenue - cost_total
profit_margin = profit / revenue                    (revenue > 0)
budget_usage = cost_total / budget                  (budget > 0)
cost_total = cost_labor + cost_device + cost_travel
```

### 6.2 按项目维度

```python
# 伪代码
def compute_profit(project_id, period):
    revenue = get_revenue(project_id, period)        # 从 revenue 模块
    cost = get_cost_summary(project_id, period)       # 从成本归集
    profit = revenue - cost["total"]
    margin = profit / revenue if revenue > 0 else 0

    return {
        "revenue": revenue,
        "cost": cost["total"],
        "profit": profit,
        "profit_margin": round(margin, 4),
        "cost_breakdown": {
            "labor": cost["labor_cost"],
            "device": cost["device_cost"],
            "travel": cost["travel_cost"],
        }
    }
```

### 6.3 按部门维度

```sql
-- 按部门聚合
SELECT
    p.dept,
    COUNT(DISTINCT p.id) AS project_count,
    SUM(s.revenue) AS total_revenue,
    SUM(s.cost_total) AS total_cost,
    SUM(s.profit) AS total_profit,
    CASE WHEN SUM(s.revenue) > 0
         THEN ROUND(SUM(s.profit) / SUM(s.revenue), 4)
         ELSE 0 END AS profit_margin
FROM pf_profit_snapshot s
JOIN pm_projects p ON s.project_id = p.id
WHERE s.period = ?
  AND s.status = 'confirmed'
  AND p.deleted_at IS NULL
GROUP BY p.dept
ORDER BY total_profit DESC;
```

### 6.4 按时间维度

```sql
-- 按时间聚合（趋势分析）
SELECT
    period,
    SUM(revenue) AS total_revenue,
    SUM(cost_total) AS total_cost,
    SUM(profit) AS total_profit,
    CASE WHEN SUM(revenue) > 0
         THEN ROUND(SUM(profit) / SUM(revenue), 4)
         ELSE 0 END AS profit_margin,
    COUNT(DISTINCT project_id) AS project_count
FROM pf_profit_snapshot
WHERE status = 'confirmed'
  AND period BETWEEN ? AND ?
GROUP BY period
ORDER BY period;
```

### 6.5 快照生命周期

```
[draft] ──确认──▶ [confirmed] ──归档──▶ [archived]
   │                    │
   │ 重新计算            │ 不可修改
   ▼                    ▼
 覆盖更新              只读
```

**状态转换规则**：
- `draft` → `confirmed`：人工确认或自动确认（配置项）
- `confirmed` → `archived`：期间结束后自动归档
- `confirmed` 不可回退到 `draft`（需管理员手动解锁）
- `archived` 永久只读

---

## 8. 成本异常告警规则

### 7.1 告警触发条件

| 条件 | 级别 | 阈值 | 说明 |
|---|---|---|---|
| `budget_usage ≥ 90%` | **warning** | 90% | 成本接近预算 |
| `budget_usage ≥ 100%` | **critical** | 100% | 成本已超预算 |
| `over_budget_pct ≥ 10%` | **critical** | 10% | 超预算 10%（PRD 要求） |
| `cost_total > budget × 1.2` | **critical** | 120% | 严重超预算 |

**默认阈值**：成本超预算 **10%** 触发 critical 告警（PRD 明确要求）。

### 7.2 告警级别定义

| 级别 | 标识 | 颜色 | 通知方式 | 响应时效 |
|---|---|---|---|---|
| 警告 | `warning` | 🟡 黄色 | 系统通知 + 邮件 | 24h 内确认 |
| 严重 | `critical` | 🔴 红色 | 系统通知 + 邮件 + 企微 | 4h 内响应 |

### 7.3 告警通知方式

1. **系统内通知**：写入 `pf_budget_alert` 表，驾驶舱告警面板展示
2. **邮件通知**：通过 `notification` 服务发送（TODO：对接企业邮箱）
3. **企微通知**：通过 `wecom-msg` 技能发送告警卡片给项目经理 + 财务负责人

### 7.4 告警流程

```
成本变更 ──▶ 重新计算快照 ──▶ 检查预算使用率
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
              < 90%            90%~100%         > 100%
              正常              warning          critical
              无告警          ──▶ 创建告警 ──▶ 通知 PM + 财务
                                    │
                              等待确认/解决
                                    │
                              ──▶ 解决/关闭
```

### 7.5 告警去重

- 同一项目同一期间只保留一条 active 告警
- 成本更新后重新评估：如果告警条件不再满足，自动 resolve
- 告警升级：warning 持续 48h 未确认，自动升级为 critical

---

## 9. 收入同步机制

> **收入确认准则**：收入数据遵循 ASC 606 / 企业会计准则14号确认准则（时点法/时段法判定见 REVENUE §1.7），同步的是已完成确认的收入。

### 8.1 同步时机

| 触发方式 | 时机 | 说明 |
|---|---|---|
| **手动触发** | 用户执行 `bdms profit sync` | 按需同步 |
| **事件驱动** | revenue 模块发布 `revenue.confirmed` 事件 | 自动同步 |
| **定时同步** | cron 每日 02:00 | 兜底同步 |
| **报表生成时** | 生成利润报表前 | 确保数据最新 |

### 8.2 同步流程

```
revenue 模块                    profit_management
     │                               │
     │  ① 收入确认完成               │
     │  ② 写入 rr_sheet_row          │
     │  ③ 发布 outbox_events         │
     │  (event_type=                 │
     │   "revenue.confirmed")        │
     │ ─────────────────────────────▶│
     │                               │
     │                          ④ 监听事件
     │                          ⑤ 读取 rr_sheet_row
     │                          ⑥ 按项目+期间聚合
     │                          ⑦ 写入 pf_profit_snapshot
     │                          ⑧ 触发告警检查
     │                               │
     │  ⑨ 确认同步完成               │
     │ ◀─────────────────────────────│
```

### 8.3 幂等保证

```python
def sync_revenue(project_id, period, force=False):
    """幂等同步：同一项目同一期间重复同步结果一致。"""
    # 1. 检查是否已同步且非强制模式
    existing = get_snapshot(project_id, period)
    if existing and existing.status == 'confirmed' and not force:
        return {"synced": False, "reason": "already_confirmed"}

    # 2. 从 revenue 模块读取收入
    revenue = revenue_engine.get_confirmed_revenue(project_id, period)

    # 3. UPSERT 快照（ON CONFLICT 覆盖）
    upsert_snapshot(project_id, period, {"revenue": revenue})

    # 4. 发布同步完成事件
    publish_event("profit.revenue_synced", {...})
```

**幂等键**：`(project_id, period)` — SQLite `ON CONFLICT(project_id, period) DO UPDATE`

### 8.4 收入数据来源

```sql
-- 从确收模块宽表读取项目收入
SELECT
    project_name,
    SUM(CASE
        WHEN sheet_name = '预算执行表'
        AND col_name = '实际确认收入'
        THEN value ELSE 0
    END) AS confirmed_revenue
FROM rr_sheet_row
WHERE period = ?
  AND project_name = ?
GROUP BY project_name;
```

**映射关系**：`pm_projects.project_name` ↔ `rr_sheet_row.project_name`

### 8.5 同步失败处理

| 失败场景 | 处理策略 |
|---|---|
| revenue 模块无数据 | 跳过，记录 warning，不阻塞利润计算 |
| 项目名不匹配 | 记录到 `pf_sync_error` 表，人工处理 |
| DB 写入失败 | 重试 3 次（间隔 1s/2s/4s），仍失败则记录错误 |
| 快照已 confirmed | 非强制模式跳过，强制模式需管理员审批 |

---

## 10. 利润报表设计

### 9.1 按项目维度报表

**报表名称**：项目利润明细表

| 列 | 数据来源 | 说明 |
|---|---|---|
| 项目名称 | pm_projects.project_name | |
| 部门 | pm_projects.dept | |
| 项目经理 | pm_projects.pm | |
| 会计期间 | pf_profit_snapshot.period | |
| 确认收入 | pf_profit_snapshot.revenue | 来自 revenue 模块 |
| 工时成本 | pf_profit_snapshot.cost_labor | |
| 设备成本 | pf_profit_snapshot.cost_device | |
| 差旅成本 | pf_profit_snapshot.cost_travel | |
| 总成本 | pf_profit_snapshot.cost_total | |
| 利润 | pf_profit_snapshot.profit | |
| 利润率 | pf_profit_snapshot.profit_margin | 百分比显示 |
| 预算 | pf_profit_snapshot.budget | |
| 预算使用率 | pf_profit_snapshot.budget_usage | 百分比显示 |
| 状态 | pf_profit_snapshot.status | draft/confirmed |

### 9.2 按部门维度报表

**报表名称**：部门利润汇总表

| 列 | 计算方式 | 说明 |
|---|---|---|
| 部门 | GROUP BY dept | |
| 项目数 | COUNT(DISTINCT project_id) | |
| 总收入 | SUM(revenue) | |
| 总成本 | SUM(cost_total) | |
| 总利润 | SUM(profit) | |
| 平均利润率 | SUM(profit) / SUM(revenue) | |
| 预算使用率 | SUM(cost_total) / SUM(budget) | |

### 9.3 按时间维度报表

**报表名称**：利润趋势分析表

| 列 | 计算方式 | 说明 |
|---|---|---|
| 期间 | GROUP BY period | |
| 项目数 | COUNT(DISTINCT project_id) | |
| 收入 | SUM(revenue) | |
| 成本 | SUM(cost_total) | |
| 利润 | SUM(profit) | |
| 利润率 | SUM(profit) / SUM(revenue) | |
| 环比增长 | (本期利润 - 上期利润) / 上期利润 | |

### 9.4 报表输出格式

- **CLI 表格**：终端直接展示（tabulate）
- **Excel 导出**：多 Sheet（项目明细 + 部门汇总 + 趋势分析）
- **JSON API**：供 dashboard 模块消费

---

## 11. 错误处理

### 10.1 异常体系

```python
# 继承 BDMS 统一异常体系
class ProfitError(BDMSBaseError):
    """利润模块异常基类。"""
    code = "PROFIT_ERROR"

class RevenueSyncError(ProfitError):
    """收入同步失败。"""
    code = "REVENUE_SYNC_ERROR"

class CostAllocationError(ProfitError):
    """成本归集失败。"""
    code = "COST_ALLOCATION_ERROR"

class BudgetAlertError(ProfitError):
    """预算告警异常。"""
    code = "BUDGET_ALERT_ERROR"

class SnapshotLockedError(ProfitError):
    """快照已锁定（confirmed/archived）。"""
    code = "SNAPSHOT_LOCKED"
```

### 10.2 错误处理策略

| 场景 | 异常 | 处理 |
|---|---|---|
| 项目不存在 | `NotFoundError` | 返回 404 + 明确错误信息 |
| 收入数据缺失 | `RevenueSyncError` | revenue=0，记录 warning，不阻塞 |
| 成本归集冲突 | `CostAllocationError` | 跳过重复记录，记录到错误日志 |
| 快照已确认 | `SnapshotLockedError` | 拒绝修改，提示先解锁 |
| 文件格式不支持 | `ValidationError` | 返回支持的格式列表 |
| 预算为 0 | `ZeroDivisionError` | budget_usage = 0，记录 warning |
| 收入为 0 | `ZeroDivisionError` | profit_margin = 0，记录 warning |

### 10.3 事务管理

```python
# 工时提交 + 成本归集 + 快照更新 = 原子操作
with transaction():
    ts_id = cost_engine.submit_timesheet(...)
    allocate_cost(project_id, period, "labour", "ct_timesheets", ts_id, amount)
    snapshot = profit_engine.compute_profit(project_id, period)
    persist_snapshot(snapshot)
    alerts = profit_engine.check_budget_alert(project_id)
    if alerts:
        create_alerts(alerts)
```

---

## 12. CLI 命令

### 11.1 命令清单

```bash
# 利润总览
bdms profit summary --period 2026-06                    # 全部项目利润汇总
bdms profit summary --period 2026-06 --dept 安服一部     # 按部门筛选
bdms profit summary --period 2026-06 --sort profit_margin # 排序

# 项目利润详情
bdms profit report --project 1 --period 2026-06          # 单项目利润报表
bdms profit report --project 1 --period 2026-06 --export # 导出 Excel

# 收入同步
bdms profit sync --project 1 --period 2026-06            # 同步收入数据
bdms profit sync --period 2026-06 --all                  # 同步全部项目

# 成本管理
bdms profit cost-summary --project 1                     # 成本汇总
bdms profit import-travel --project 1 --file travel.xlsx # 导入差旅
bdms profit import-device --project 1 --file device.csv  # 导入设备

# 告警
bdms profit alerts                                      # 查看活跃告警
bdms profit alerts --project 1                          # 单项目告警
bdms profit alerts --resolve 1 --resolver 张三           # 解决告警

# 趋势
bdms profit trend --project 1 --from 2026-01 --to 2026-06  # 利润趋势
```

### 11.2 输出示例

```
$ bdms profit summary --period 2026-06

项目利润汇总 — 2026-06
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
项目名称             部门       收入        成本       利润     利润率   预算使用
─────────────────────────────────────────────────────────────
梆梆安全平台V3.0    安服一部  850,000   620,000   230,000   27.1%    72.9%
移动威胁感知系统    安服二部  420,000   380,000    40,000    9.5%    90.5% ⚠️
代码加固工具定制    研发一部  180,000   210,000   -30,000  -16.7%   116.7% 🔴
─────────────────────────────────────────────────────────────
合计                         1,450,000 1,210,000   240,000   16.6%    83.4%

⚠️  1 个警告  🔴 1 个严重告警
```

---

## 13. 测试策略

### 12.1 单元测试

| 测试类 | 覆盖内容 | 用例数 |
|---|---|---|
| `TestProfitEngine` | 利润计算核心逻辑 | ≥ 8 |
| `TestCostAllocation` | 成本归集幂等性 | ≥ 5 |
| `TestBudgetAlert` | 告警触发条件 | ≥ 6 |
| `TestRevenueSync` | 收入同步幂等 | ≥ 4 |

**关键用例**：

```python
# test_profit_engine.py

def test_compute_profit_basic():
    """基本利润计算：收入 10000 - 成本 6000 = 利润 4000"""
    result = engine.compute_profit(project_id=1, period="2026-06")
    assert result["profit"] == result["revenue"] - result["cost"]
    assert result["profit_margin"] == result["profit"] / result["revenue"]

def test_compute_profit_zero_revenue():
    """收入为 0 时，利润 = -成本，利润率 = 0"""
    ...

def test_budget_alert_warning():
    """成本达预算 90% 触发 warning"""
    ...

def test_budget_alert_critical():
    """成本超预算 10% 触发 critical"""
    ...

def test_cost_allocation_idempotent():
    """同一成本项重复归集不重复计算"""
    ...

def test_revenue_sync_idempotent():
    """同一项目同一期间重复同步结果一致"""
    ...

def test_snapshot_unique_constraint():
    """同一项目同一期间只能有一条快照"""
    ...

def test_profit_margin_precision():
    """利润率精度：保留 4 位小数"""
    ...
```

### 12.2 集成测试

| 测试场景 | 验证点 |
|---|---|
| 工时提交 → 成本归集 → 快照更新 | 端到端数据流 |
| 收入同步 → 利润计算 → 告警触发 | 跨模块数据流 |
| 差旅导入 → 成本归集 → 报表生成 | 文件导入完整链路 |
| 并发工时提交 | 数据一致性 |

### 12.3 E2E 测试

```bash
# 完整流程测试
bdms profit sync --period 2026-06 --all          # 同步收入
bdms profit import-travel --project 1 --file test.xlsx  # 导入差旅
bdms profit report --project 1 --period 2026-06   # 生成报表
bdms profit alerts                               # 检查告警
```

### 12.4 黄金基准对比

| 对比项 | 基准来源 | 容差 |
|---|---|---|
| 利润计算结果 | 手工 Excel 计算 | 误差 ≤ 0.01 元 |
| 成本归集结果 | 手工汇总 | 误差 ≤ 0.01 元 |
| 告警触发 | 手工验证 | 100% 一致 |
| 报表数据 | 财务提供参考数据 | 误差 ≤ 1% |

---

## 附录 A：配置项清单

| 配置键 | 默认值 | 说明 |
|---|---|---|
| `profit.alert_threshold` | `0.10` | 预算告警阈值（10%） |
| `profit.alert_warning_pct` | `0.90` | 警告级别阈值（90%） |
| `profit.auto_confirm` | `false` | 是否自动确认快照 |
| `profit.device_depreciation_method` | `"straight_line"` | 设备折旧方法 |
| `profit.sync_retry_count` | `3` | 收入同步重试次数 |
| `profit.currency_default` | `"CNY"` | 默认币种 |
| `profit.months_trend` | `6` | 趋势分析默认月数 |

## 附录 B：复用资产清单与重构方案

> **原则**：按系统设计大纲 §3.5 模块划分重构，而非直接引用旧代码。
> 设计大纲定义：成本核算（工时×费率 + 设备折旧 + 差旅）归属 **profit_management** 职责域。
> 因此 `project_management/cost/` 的能力应**迁移重构**到本模块，旧模块同步降级为薄兼容层，最终下线。

### B.1 资产迁移重构方案

| 资产 | 现位置 | 目标位置 | 重构操作 |
|---|---|---|---|
| `CostEngine` | `project_management/cost/engine.py` | `profit_management/cost_engine.py` | **迁移重构**：按 DESIGN-DETAIL 契约重写接口，保留计算逻辑内核；旧路径保留 import 兼容层（deprecation warning） |
| `CostService` | `project_management/cost/service.py` | `profit_management/cost_service.py` | **迁移重构**：工时提交/审批迁入 ProfitService；旧路径兼容层 |
| `CostImporter` | `project_management/cost/importer.py` | `profit_management/importer.py` | **迁移重构**：作为 ProfitImporter 基础，扩展差旅 Excel 导入 |
| `CostExporter` | `project_management/cost/exporter.py` | `profit_management/exporter.py` | **迁移重构**：并入 ProfitExporter（利润报表含成本明细 Sheet） |
| `ct_timesheets` 表 | `core/schemas.py` | → `pf_timesheet`（新表） | **数据迁移**：建 pf_timesheet 新表，ct_timesheets 数据一次性迁移，旧表改 VIEW 只读 |
| `ct_device_usage` 表 | `core/schemas.py` | → `pf_device_usage`（新表） | 同上，数据迁移 + 旧表 VIEW |
| `ct_travel_costs` 表 | `core/schemas.py` | → `pf_travel_cost`（新表） | 同上 |
| `ct_staff_rates` 表 | `core/schemas.py` | → `pf_staff_rate`（新表） | 同上，人员费率表 |

### B.2 迁移重构步骤（IMPLEMENTATION-PLAN 引用）

```
Step 1：创建 pf_* 新表（DDL 见 §4），与 ct_* 并存
Step 2：数据迁移脚本（ct_* → pf_*，全量复制 + 校验）
Step 3：旧表转 VIEW（ct_timesheets AS SELECT ... FROM pf_timesheet）
Step 4：引擎/服务/导出器迁移重构（逻辑内核保留，接口按新契约对齐）
Step 5：旧路径兼容层（import warning + 转发）
Step 6：全量测试通过 → 发布
Step 7（v2.2）：移除兼容层，旧表 VIEW 删除，cost/ 目录下线
```

### B.3 迁移后依赖关系

```python
# profit_management（迁移后，无跨模块 import）
from bdms.modules.base import BaseEngine, BaseService, BaseImporter, BaseExporter  # 基类继承
from bdms.core.db import get_connection, transaction                              # DB 基础设施

# 收入数据通过 DB 共享（非 import）
revenue_data = conn.execute(
    "SELECT ... FROM rr_sheet_row WHERE period = ?", (period,)
).fetchall()

# 项目主数据通过 DB 共享（非 import）
project = conn.execute(
    "SELECT budget, dept FROM pm_projects WHERE id = ?", (project_id,)
).fetchone()

# 事件总线（DB 共享）
conn.execute(
    "INSERT INTO outbox_events (module, event_type, payload) VALUES (?, ?, ?)",
    ("profit", "budget_alert", json.dumps(alert_payload))
)
```

### B.4 重构检查清单

- [ ] pf_* 新表 DDL 与本文档 §4 逐字段一致
- [ ] 数据迁移脚本含校验（行数 + 金额汇总比对）
- [ ] 旧表 VIEW 只读，写入报错
- [ ] 兼容层 import 时输出 DeprecationWarning
- [ ] 本模块无 `from bdms.modules.project_management.cost import ...`（迁移完成后）
- [ ] 本模块无 `from bdms.modules.revenue import ...`（收入只走 DB 共享）
- [ ] 模块间交互全部通过 DB 共享 + 事件总线（无直接函数调用）
- [ ] 全量测试通过（含迁移前后数据一致性验证）

---

> 文档版本：v2.1 Detail r2 | 编制日期：2026-09-24 | 编制人：BDMS 设计组
> 审核状态：⏳ 待 Rex 审核

## 变更历史

| 版本 | 日期 | 变更 |
|---|---|---|
| v2.1 r2 | 2026-09-24 | Rex 审核反馈 2 条：<br>① 新增 PMP 挣值管理（EVM）核心要素：PV/EV/AC v2.1 实现，SV/CV/SPI/CPI/EAC/ETC/VAC/TCPI v2.2 占位；新增成本估算/现金流/间接成本分摊/ROI 等 11 项占位（含 pf_cash_flow/pf_cost_overhead 占位表）<br>② 复用资产重构：按设计大纲 §3.5 模块职责，`project_management/cost/` 迁移重构到 profit_management（ct_* 表 → pf_* 表 + 兼容 VIEW + 7 步迁移方案），模块间全部 DB 共享解耦 |
| v2.1 r1 | 2026-09-22 | 初版 |
