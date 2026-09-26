n# BDMS v2.1 项目管理（Project Management）详细设计

| 项 | 值 |
|---|---|
| 版本 | v2.1 |
| 层级 | L4 BDMS 模块详细设计 |
| 继承 | L3 Project Management（核心域） |
| 状态 | 设计中 |
| 模块编码 | project_management |
| 对应 L3 域 | Project Management（核心域） |
| 横切依赖 | Base Engine / Service / Importer / Exporter 框架，合同管理模块，售后管理模块 |

---

## 1 模块概述

### 1.1 业务域

项目管理模块是 BDMS 的**核心域**，覆盖项目全生命周期管理：

```
立项 → 启动 → 规划 → 执行 → 交付 → 验收 → 结项 → 售后移交
```

覆盖 16 个标准阶段（参考 PMBOK + 安全服务行业适配），内聚 **6 个子引擎**：

| 子引擎 | 职责 | 对应数据表前缀 |
|---|---|---|
| `ProjectEngine` | 项目核心（主引擎） | `pm_` |
| `DeliveryReportEngine` | 交付报告管理 | `pm_`（关联） |
| `RevenueEngine` | 收入确认与开票 | `ct_`（财务域） |
| `CostEngine` | 成本核算（工时/设备/差旅） | `ct_`（财务域） |
| `RiskEngine` | 风险与处置 | `rk_` |
| `ChangeManagementEngine` | 变更管理与发布控制 | `ch_` |

### 1.2 "大模块"设计原则

项目管理是 BDMS 中最大的模块，采用 **"一个大模块 + 6 个子引擎 + 1 个跨引擎服务"** 架构：

- **统一入口**：`bdms project` 命令族 + `ProjectManagementService` 统一编排
- **子引擎独立**：每个子引擎可单独调用、单独测试、单独演进
- **跨引擎服务**：`ProjectFinancialService` 横向聚合收入+成本数据，提供利润视图
- **数据隔离**：不同子引擎的数据表前缀不同（pm_ / ct_ / rk_ / ch_）
- **事务边界清晰**：子引擎之间通过 Service 层交互，不直接跨引擎调用

### 1.3 横切关系

| 横切关注点 | 处理方式 |
|---|---|
| 权限 | 项目经理 / 项目成员 / 部门经理 / 财务 / 高管 五级 |
| 项目权限 | 项目级角色（项目经理 + 项目成员） |
| 审计 | 项目状态变更写入审计日志 |
| 通知 | 里程碑提醒 / 风险告警 / 交付报告提交 自动通知 |
| 导出 | 项目总览 / 成本明细 / 风险清单 / 交付报告 |

---

## 2 架构图

### 2.1 模块结构

```
┌─────────────────────────────────────────────────────────┐
│            Project Management Module (project_management)   │
├─────────────────────────────────────────────────────────┤
│                                                     │
│  ┌───────────────────────────────────────────────┐      │
│  │   ProjectManagementService (编排层)    │      │
│  │  (统一入口 / 事务编排 / 权限校验)       │      │
│  └──────┬────────┬────────┬────────┬─────┘      │
│         │        │        │        │                │
│  ┌──────▼──┐ ┌───▼─────┐ ┌▼──────┐ ┌▼─────┐ ┌▼──────┐│
│  │Project │ │Delivery│ │Revenue│ │Cost│ │Risk    ││
│  │Engine  │ │Report  │ │Engine │ │Eng.│ │Engine  ││
│  │(核心)  │ │Engine  │ │(收入) │ │(成本)│ │(风险)││
│  └─────────┬───┘ └───┬─────┘ └──┬───┘ └─┬──┘ └──┬───┘│
│          │         │          │        │       │      │
│  ┌───────▼─────────▼──────────▼────────▼───────▼──┐│
│  │          数据层 (pm_ / ct_ / rk_ 表)                 ││
│  └───────────────────────────────────────────────┘│
│                                                     │
└───────────────────────────────────────────────────────
```

### 2.2 子引擎职责边界

| 子引擎 | 核心职责 | 不负责的 | 不负责 |
|---|---|---|---|
| **ProjectEngine** | 项目主数据、状态机、阶段管理 | 项目立项/结项 | 成本计算 | 财务计算 |
| **DeliveryReportEngine** | 交付报告提交/审核/归档 | 报告生命周期 | 收入确认 | 账单生成 |
| **RevenueEngine** | 收入确认、开票、到账登记 | 收入计算 | 成本计算 | 支付处理 |
| **CostEngine** | 工时/设备/差旅成本归集 | 成本核算 | 项目审批 | 预算编制 |
| **RiskEngine** | 风险识别/评估/处置/关闭 | 风险管理 | 自动处置执行 | 人员管理 |

---

## 3 接口契约

### 3.1 ProjectEngine（核心引擎）

```python
from typing import Optional, List, Dict, Tuple
from decimal import Decimal
from datetime import datetime, date
from enum import Enum


class ProjectState(str, Enum):
    INITIATING = "initiating"       # 立项中
    PLANNING = "planning"           # 规划中
    EXECUTING = "executing"       # 执行中
    DELIVERING = "delivering"     # 交付中
    ACCEPTING = "accepting"       # 验收中
    CLOSING = "closing"           # 结项中
    CLOSED = "closed"             # 已结项
    CANCELLED = "cancelled"       # 已取消


class ProjectEngine(BaseEngine):
    """项目核心引擎：项目主数据 + 状态机 + 阶段管理。"""

    def init_project(
        self,
        name: str,
        project_type: str,
        customer: str,
        contract_id: str = None,
        pm_id: str = None,
        start_date: date = None,
        end_date: date = None,
        budget: Decimal = None,
    ) -> str:
        """
        创建项目（立项）。状态: initiating

        Returns:
            project_id
        """
        ...

    def update_scope(
        self,
        project_id: str,
        **kwargs,
    ) -> None:
        """更新项目范围/基本信息。
        仅 initiating / planning 状态可自由修改；
        executing 及之后需走变更流程。
        """
        ...

    def close_project(
        self,
        project_id: str,
        close_type: str = "normal",
        close_date: date = None,
        summary: str = "",
    ) -> None:
        """
        结项：accepting → closing → closed。
        前置条件：交付完成 + 验收通过 + 成本结清 + 风险关闭 + 归档完成
        """
        ...

    def get_status(self, project_id: str) -> Dict:
        """获取项目当前状态 + 阶段进度 + 关键指标。"""
        ...

    def list_projects(
        self,
        state: ProjectState = None,
        project_type: str = None,
        customer: str = None,
        pm_id: str = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[Dict], int]:
        """项目列表查询。"""
        ...
```

### 3.2 ProjectManagementService（编排服务层）

```python
class ProjectManagementService(BaseService):
    """
    项目管理服务层：统一编排 5 个子引擎。

    负责：
    - 跨子引擎事务编排
    - 项目级权限校验
    - 项目生命周期状态推进
    - 子引擎之间的数据同步
    """

    # ----- 项目生命周期 -----

    def create_project(self, **kwargs) -> str:
        """创建项目（调用 ProjectEngine.init_project）"""
        ...

    def start_project(self, project_id: str, operator: str) -> None:
        """
        启动项目：initiating → planning → executing
        校验：合同已签署 + 团队已组建 + 计划已制定
        """
        ...

    def update_project(self, project_id: str, **kwargs) -> None:
        """更新项目信息"""
        ...

    def submit_delivery_report(self, project_id: str, report_data: Dict) -> str:
        """
        提交交付报告（调用 DeliveryReportEngine + 推进状态）
        """
        ...

    def accept_project(self, project_id: str, acceptance_data: Dict) -> None:
        """
        项目验收：delivering → accepting
        触发：收入确认 + 成本结算 + 风险关闭检查
        """
        ...

    def close_project(self, project_id: str, **kwargs) -> None:
        """
        结项：accepting → closed
        编排：检查所有子引擎就绪 → 移交售后 → 归档
        """
        ...

    def cancel_project(self, project_id: str, reason: str) -> None:
        """取消项目（任意状态 → cancelled，需权限）"""
        ...

    # ----- 查询 -----

    def get_project_detail(self, project_id: str) -> Dict:
        """
        获取项目完整详情：
        基本信息 + 交付报告列表 + 收入/成本概览 + 风险清单 + 团队成员
        """
        ...

    def list_projects(self, **filters) -> Tuple[List[Dict], int]:
        """项目列表（含汇总指标）"""
        ...

    def get_project_dashboard(self, project_id: str) -> Dict:
        """项目仪表盘：进度 / 成本 / 收入 / 风险 概览"""
        ...
```

### 3.3 CostEngine + CostService

```python
class CostEngine(BaseEngine):
    """
    成本引擎：工时 + 设备使用费 + 差旅费用归集。
    独立引擎，可单独调用。
    """

    # ----- 工时成本 -----

    def submit_timesheet(
        self,
        project_id: str,
        person_id: str,
        work_date: date,
        hours: float,
        work_type: str,
        description: str = "",
    ) -> str:
        """
        提交工时记录。

        工时单价从人员成本 = hours × 人员单价 ×
        人员单价从 ct_staff_rate 表
        """
        ...

    def approve_timesheet(
        self,
        timesheet_id: str,
        approver: str,
        approved: bool,
        comment: str = "",
    ) -> None:
        """审批工时记录。"""
        ...

    # ----- 设备使用成本 -----

    def get_device_usage(
        self,
        project_id: str,
        period_start: date = None,
        period_end: date = None,
    ) -> List[Dict]:
        """查询设备使用记录及费用。"""
        ...

    # ----- 差旅成本 -----

    def sync_travel_cost(
        self,
        project_id: str,
        travel_records: List[Dict],
    ) -> int:
        """
        同步差旅费用（从差旅系统导入）。
        返回同步的记录数。
        """
        ...

    # ----- 成本汇总 -----

    def get_cost_summary(
        self,
        project_id: str,
        period_start: date = None,
        period_end: date = None,
    ) -> Dict:
        """
        成本汇总：
        {
            "total": Decimal,
            "labor_cost": Decimal,
            "device_cost": Decimal,
            "travel_cost": Decimal,
            "other_cost": Decimal,
            "by_person": [{...}],
            "by_month": [{...}]
        }
        """
        ...


class CostService(BaseService):
    """成本管理服务层：成本引擎的事务编排 + 权限校验。"""

    def submit_timesheet(self, **kwargs) -> str: ...
    def approve_timesheet(self, **kwargs) -> None: ...
    def get_cost_summary(self, project_id: str, **kwargs) -> Dict: ...
    def import_timesheet_batch(self, file_path: str) -> int:
        """批量导入工时（Excel）。"""
        ...


class CostImporter(BaseImporter):
    """成本数据导入器：工时批量导入 / 差旅费用导入。"""
    def import_from_file(self, file_path: str, **kwargs) -> List[Dict]: ...


class CostExporter(BaseExporter):
    """成本导出器：成本明细 / 成本汇总 / 工时报表。"""
    def export_cost_detail(self, project_id: str, **kwargs) -> bytes: ...
    def export_cost_summary(self, project_id: str, **kwargs) -> bytes: ...
    def export_timesheet_report(self, **filters) -> bytes: ...
```

### 3.4 RiskEngine + RiskService

```python
class RiskEngine(BaseEngine):
    """
    风险引擎：风险识别 → 评估 → 处置 → 关闭。
    独立引擎，可单独调用。
    """

    def report_risk(
        self,
        project_id: str,
        title: str,
        description: str,
        risk_type: str,
        probability: str,      # high / medium / low
        impact: str,           # high / medium / low
        reporter: str,
    ) -> str:
        """
        上报风险。
        风险等级 = probability × impact（自动计算）
        """
        ...

    def review_risk(
        self,
        risk_id: str,
        reviewer: str,
        action: str,           # accept / mitigate / transfer / avoid
        action_plan: str = "",
        owner: str = None,
        due_date: date = None,
    ) -> None:
        """
        风险评审：确定处置策略。
        状态: open → assessing → 处置中
        """
        ...

    def get_risk_summary(self, project_id: str) -> Dict:
        """
        风险汇总：
        {
            "total": int,
            "open": int,
            "mitigating": int,
            "closed": int,
            "by_level": {"critical": N, "high": N, ...},
            "by_type": {...}
        }
        """
        ...

    def escalate(self, risk_id: str, escalate_to: str, reason: str) -> None:
        """
        风险升级：上报给更高级别处理。
        """
        ...


class RiskService(BaseService):
    """风险处置服务层：风险引擎的事务编排 + 通知。"""

    def report_risk(self, **kwargs) -> str: ...
    def review_risk(self, **kwargs) -> None: ...
    def close_risk(self, risk_id: str, closer: str, close_reason: str) -> None: ...
    def get_risk_summary(self, project_id: str) -> Dict: ...


class RiskExporter(BaseExporter):
    """风险导出器：风险清单 / 风险汇总报表。"""
    def export_risk_register(self, project_id: str = None, **filters) -> bytes: ...
    def export_risk_summary(self, project_id: str) -> bytes: ...
```

---

### 3.6 ChangeManagementEngine（变更管理引擎）

```python
class ChangeManagementEngine:
    """
    变更管理引擎：横向管理项目全生命周期的变更。
    
    职责：
    - 变更请求 CRUD（范围/进度/预算/资源）
    - 影响分析（对交付/成本/收入/风险的影响）
    - 变更审批流（分级审批）
    - 变更日志（关联到项目的每次状态变更）
    """

    def submit_change_request(
        self,
        project_id: str,
        change_type: str,           # scope / schedule / budget / resource
        title: str,
        description: str,
        reason: str,
        proposed_changes: Dict,
        submitted_by: str,
    ) -> str:
        """
        提交变更请求。
        Returns: change_request_id
        """
        ...

    def assess_impact(
        self,
        change_request_id: str,
        assessor: str,
    ) -> Dict:
        """
        影响分析：评估变更对交付/成本/收入/风险的影响。
        返回：{
            "delivery_impact": {"delayed_days": 5, "affected_milestones": [...]},
            "cost_impact": {"delta_amount": -30000, "reason": "减少现场工时"},
            "revenue_impact": {"delta_amount": 0, "reason": "不影响收入确认"},
            "risk_impact": {"new_risks": [...], "increased_risks": [...]},
        }
        """
        ...

    def approve_change(
        self,
        change_request_id: str,
        approver: str,
        decision: str,              # approved / rejected / deferred
        comment: str = "",
    ) -> None:
        """审批变更请求。approved 后自动执行变更。"""
        ...

    def execute_change(
        self,
        change_request_id: str,
        executor: str,
    ) -> None:
        """
        执行已批准的变更。
        根据 change_type 调用对应子引擎的更新方法。
        """
        ...

    def get_change_log(
        self,
        project_id: str,
        change_type: str = None,
    ) -> List[Dict]:
        """获取项目的变更日志。"""
        ...

    def get_change_statistics(
        self,
        project_id: str,
    ) -> Dict:
        """
        变更统计：
        {
            "total_changes": int,
            "by_type": {"scope": N, "schedule": N, ...},
            "by_status": {"pending": N, "approved": N, "rejected": N},
            "avg_approval_hours": float,
        }
        """
        ...
```

### 3.7 ProjectFinancialService（跨引擎财务视图服务）

```python
class ProjectFinancialService:
    """
    跨引擎财务视图服务：聚合 RevenueEngine + CostEngine 数据，提供利润视图。
    
    职责：
    - 利润计算（收入 - 成本）
    - 利润趋势（按月）
    - 利润预警（毛利率 < 阈值时告警）
    - 项目财务健康度评分
    
    注意：不持有独立数据源，所有数据来自 RevenueEngine 和 CostEngine。
    """

    def __init__(
        self,
        revenue_service: 'RevenueService',
        cost_service: 'CostService',
    ):
        self.revenue = revenue_service
        self.cost = cost_service

    def get_profit_summary(
        self,
        project_id: str,
        period_start: date = None,
        period_end: date = None,
    ) -> Dict:
        """
        利润汇总：
        {
            "total_revenue": Decimal,
            "total_cost": Decimal,
            "gross_profit": Decimal,
            "gross_margin": float,       # 毛利率 (%)
            "by_month": [
                {"month": "2026-10", "revenue": ..., "cost": ..., "profit": ..., "margin": ...},
                ...
            ]
        }
        """
        revenue_data = self.revenue.get_revenue_summary(project_id, period_start, period_end)
        cost_data = self.cost.get_cost_summary(project_id, period_start, period_end)
        return self._calc_profit(revenue_data, cost_data)

    def get_profit_trend(
        self,
        project_id: str,
        range_months: int = 12,
    ) -> List[Dict]:
        """利润趋势（多月份时间序列）。"""
        ...

    def check_profit_alert(
        self,
        project_id: str,
        threshold_pct: float = 15.0,
    ) -> Optional[Dict]:
        """
        利润预警：毛利率低于阈值时返回告警信息。
        """
        ...

    def get_financial_health_score(
        self,
        project_id: str,
    ) -> Dict:
        """
        项目财务健康度评分（0-100）。
        综合：利润率 + 成本偏差 + 收入确认率 + 变更频率
        """
        ...
```

---


## 4 数据模型

引用《BDMS v2.1 数据模型详细设计》§7、§9、§10。

### 4.1 项目核心（5 张 pm_ 表）

| 表名 | 中文名 | 说明 |
|---|---|---|
| `pm_projects` | 项目主表 | 项目基本信息、状态、阶段 |
| `pm_phases` | 项目阶段表 | 16 个标准阶段实例 |
| `pm_team_members` | 项目团队表 | 项目成员及角色 |
| `pm_milestones` | 里程碑表 | 项目里程碑计划与完成情况 |
| `pm_delivery_reports` | 交付报告表 | 交付报告提交/审核记录 |

### 4.2 财务域（4 张 ct_ 表）

| 表名 | 中文名 | 说明 |
|---|---|---|
| `ct_timesheets` | 工时记录表 | 人员工时填报与审批 |
| `ct_staff_rates` | 人员单价表 | 不同角色/级别对应的工时单价 |
| `ct_device_usage` | 设备使用表 | 设备使用记录与费用 |
| `ct_travel_costs` | 差旅费用表 | 差旅费用明细 |

### 4.3 风险域（3 张 rk_ 表）

| 表名 | 中文名 | 说明 |
|---|---|---|
| `rk_risks` | 风险主表 | 风险基本信息与状态 |
| `rk_risk_history` | 风险历史表 | 风险状态变更记录 |
| `rk_risk_actions` | 风险处置表 | 风险处置措施与进展 |

### 4.4 跨模块关联

```
cr_contracts (合同)
    │ 1:N
    ▼
pm_projects (项目)
    ├── 1:N → pm_phases (阶段)
    ├── 1:N → pm_team_members (团队)
    ├── 1:N → pm_milestones (里程碑)
    ├── 1:N → pm_delivery_reports (交付报告)
    ├── 1:N → ct_timesheets (工时)
    ├── 1:N → ct_device_usage (设备)
    ├── 1:N → ct_travel_costs (差旅)
    └── 1:N → rk_risks (风险)
```

---

## 5 子引擎独立调用设计

每个子引擎支持**两种调用方式**：

1. **通过 ProjectManagementService 统一调用（推荐，事务完整）
2. **直接调用子引擎 Service（独立使用，灵活）

### 5.1 Python API 独立调用

```python
# 直接调用成本引擎（不需要项目上下文也能独立使用
from bdms.project_management.cost_engine import CostEngine
from bdms.project_management.cost_service import CostService

# 独立使用：直接查成本
cost_service = CostService()
summary = cost_service.get_cost_summary(project_id="PROJ-001")

# 独立使用：上报风险
from bdms.project_management.risk_service import RiskService
risk_service = RiskService()
risk_id = risk_service.report_risk(
    project_id="PROJ-001",
    title="客户需求频繁变更",
    description="客户每周都有新需求",
    risk_type="scope",
    probability="high",
    impact="medium",
    reporter="zhangsan",
)
```

### 5.2 CLI 独立命令

每个子引擎都有自己的 CLI 命令子集（详见第 7 节），支持：
- 不经过项目主流程，直接操作子引擎数据
- 用于数据导入 / 报表生成 / 批量处理
- 支持脚本化与自动化集成

---

## 6 核心数据流

### 6.1 项目立项 → 执行 → 交付 → 验收 → 结项

```python
# 伪代码：项目全生命周期
def project_full_lifecycle():
    # ===== 阶段 1：立项
    project_id = project_service.create_project(
        name="XX 客户等保测评项目",
        project_type="等保测评",
        customer="XX 公司",
        contract_id="CR-2026-001",
        pm_id="zhangsan",
        start_date=date(2026, 10, 1),
        end_date=date(2026, 12, 31),
        budget=Decimal("500000"),
    )
    # state: initiating

    # ===== 阶段 2：规划（启动项目）
    project_service.start_project(project_id, operator="pm_director")
    # state: planning → executing

    # ===== 阶段 3：执行中
    # 3.1 团队成员提交工时
    cost_service.submit_timesheet(
        project_id=project_id,
        person_id="lisi",
        work_date=date(2026, 10, 5),
        hours=8.0,
        work_type="现场测评",
    )

    # 3.2 设备使用登记
    cost_engine.record_device_usage(
        project_id=project_id,
        device_id="scanner-01",
        usage_hours=4.0,
    )

    # 3.3 差旅费用同步
    cost_engine.sync_travel_cost(project_id, travel_records=[...])

    # 3.4 风险上报
    risk_service.report_risk(
        project_id=project_id,
        title="测评工具授权到期",
        description="授权还有 30 天到期，影响交付",
        risk_type="resource",
        probability="medium",
        impact="high",
        reporter="lisi",
    )

    # 3.5 风险评审与处置
    risk_service.review_risk(
        risk_id=risk_id,
        reviewer="zhangsan",
        action="mitigate",
        action_plan="申请续期采购",
        owner="wangwu",
        due_date=date(2026, 10, 20),
    )

    # ===== 阶段 4：交付
    report_id = project_service.submit_delivery_report(
        project_id=project_id,
        report_data={
            "report_type": "阶段交付",
            "title": "第一阶段测评报告",
            "content": "...",
            "attachments": [...],
        },
    )
    # state: delivering

    # ===== 阶段 5：验收
    project_service.accept_project(
        project_id=project_id,
        acceptance_data={
            "acceptance_date": date(2026, 12, 25),
            "acceptance_report": "...",
        },
    )
    # 自动触发：
    # - 收入确认（RevenueEngine）
    # - 成本结算
    # - 风险关闭检查
    # state: accepting

    # ===== 阶段 6：结项
    project_service.close_project(
        project_id=project_id,
        close_type="normal",
        summary="项目按期交付，客户满意度良好",
    )
    # 自动触发：
    # - 移交售后（AfterSalesService.transfer_to_after_sales）
    # - 合同归档
    # - 项目文档归档
    # state: closed
```

---

## 7 CLI 命令设计

### 7.1 项目主命令

```bash
bdms project <subcommand> [options]

# 项目生命周期
bdms project create --name "..." --type "等保测评" --customer "..." --pm "..." --budget 500000
bdms project update <project_id> --field value...
bdms project start <project_id>              # 启动项目
bdms project accept <project_id> --date 2026-12-25 --report "..."
bdms project close <project_id> --type normal --summary "..."
bdms project cancel <project_id> --reason "客户终止合作"

# 查询
bdms project list [--state executing] [--type "..."] [--pm "..."] [--page 1]
bdms project show <project_id>
bdms project dashboard <project_id>

# 阶段与里程碑
bdms project phases <project_id> list
bdms project phases <project_id> update <phase_id> --status completed
bdms project milestones <project_id> list
bdms project milestones <project_id> add --name "初测完成" --date 2026-11-01
```

### 7.2 交付报告命令

```bash
# 交付报告
bdms project delivery <project_id> list
bdms project delivery <project_id> submit --title "..." --type phase --content-file report.md
bdms project delivery <report_id> review --approve --comment "同意"
bdms project delivery <report_id> revise --comment "需补充..."
bdms project delivery <report_id> show
```

### 7.3 成本管理命令

```bash
# 工时
bdms project cost timesheet submit --project <id --person ...
bdms project cost timesheet approve <timesheet_id> --approver "..."
bdms project cost timesheet list [--project <id>] [--person <id>]
bdms project cost timesheet import <file.xlsx>        # 批量导入

# 设备
bdms project cost device list <project_id>
bdms project cost device add <project_id> --device scanner-01 --hours 4

# 差旅
bdms project cost travel sync <project_id> <file.xlsx>
bdms project cost travel list <project_id>

# 成本汇总
bdms project cost summary <project_id> [--period 2026-10]
bdms project cost export <project_id> --format xlsx --type detail
```

### 7.4 风险管理命令

```bash
# 风险
bdms project risk report --project <id> --title "..." --type scope --probability high --impact medium
bdms project risk list [--project <id>] [--status open]
bdms project risk show <risk_id>
bdms project risk review <risk_id> --action mitigate --plan "..." --owner "..." --due 2026-10-20
bdms project risk close <risk_id> --reason "已解决"
bdms project risk escalate <risk_id> --to "..." --reason "超出项目组无法解决"
bdms project risk summary <project_id>
bdms project risk export <project_id> --format xlsx
```

---

## 8 实现路径

### 第 1 步：核心引擎 + 数据模型（1 天）

- [ ] 创建 `project_management/` 模块目录
- [ ] 定义 pm_ 5 张表 + ct_ 4 张表 + rk_ 3 张表的 SQLAlchemy 模型
- [ ] 实现 ProjectEngine（核心状态机 + CRUD）
- [ ] 实现 DeliveryReportEngine
- [ ] 单元测试：项目状态机 + 阶段管理

### 第 2 步：成本 + 风险子引擎（1.5 天）

- [ ] 实现 CostEngine（工时/设备/差旅/汇总）
- [ ] 实现 CostService + CostImporter + CostExporter
- [ ] 实现 RiskEngine（上报/评审/升级/汇总）
- [ ] 实现 RiskService + RiskExporter
- [ ] 实现 RevenueEngine（收入确认/开票/到账）
- [ ] 单元测试：各子引擎独立功能

### 第 3 步：服务编排 + 集成（1 天）

- [ ] 实现 ProjectManagementService（统一编排）
- [ ] 跨子引擎事务一致性保证（结项检查逻辑
- [ ] 项目仪表盘（Dashboard
- [ ] 与合同管理模块集成（合同→项目关联
- [ ] 与售后管理模块集成（结项→售后移交）
- [ ] 集成测试：项目全生命周期

### 第 4 步：CLI + 收尾（0.5 天）

- [ ] 实现 `bdms project` CLI 命令族（约 40 个子命令）
- [ ] 完善审计日志
- [ ] 编写模块 README
- [ ] 端到端测试

---

## 9 预期效果 + 验收标准

### 9.1 预期效果

- 项目管理全流程线上化，项目状态透明可追踪
- 成本归集自动化率 ≥ 80%（工时/设备/差旅自动归集）
- 风险响应时效从 "事后发现提前到实时上报
- 支持同时管理 100+ 个在执行项目

### 9.2 验收标准

| 类别 | 验收项 | 通过标准 |
|---|---|---|
| 核心功能 | 项目 CRUD + 状态机 | 7 种状态转换全部正确 |
| 子引擎 | 5 个子引擎独立调用 | 每个子引擎独立单元测试全部通过 |
| 成本核算 | 工时+设备+差旅 三类成本 | 计算准确，汇总正确 |
| 风险管理 | 风险全生命周期 | 上报→评审→处置→关闭 完整链路通畅 |
| 服务编排 | 结项检查 | 未完成的子项阻止结项 |
| 跨模块集成 | 合同关联 + 售后移交 | 数据正确传递，无丢失 |
| 性能 | 项目列表 + 仪表盘 | 列表查询 < 500ms；仪表盘 < 1s |
| 幂等 | 工时重复提交 / 重复结项 | 重复操作不产生副作用 |

---

## 10 复用资产映射

| 资产 | 来源 | 复用方式 |
|---|---|---|
| BaseEngine / BaseService | BDMS Base 模块 | 5 个子引擎全部继承 |
| BaseImporter / BaseExporter | BDMS Base 模块 | 成本导入/导出，风险导出 |
| 状态机框架 | BDMS Base 模块 | 项目状态机 + 风险状态机 |
| 审计日志框架 | BDMS Base 模块 | 所有状态变更留痕 |
| 合同信息 | Contract Management 模块 | 项目立项时关联合同 |
| 售后移交 | After-sales Management 模块 | 结项时移交售后 |
| 企业微信通知 | 全局 WeCom 集成 | 里程碑提醒 / 风险告警 |
| 人员信息 | 组织架构模块 | 团队成员 + 人员单价 |

---

## 11 技术方案

### 11.1 技术选型

| 维度 | 选型 | 依据 |
| ---|---|---|
| 语言 | Python 3.10+ | 与 BDMS 全栈一致 |
| 持久化 | SQLite（通过 core.db） | 与项目/合同/成本/风险模块共享连接 |
| 子引擎架构 | 5 子引擎独立（Project/DeliveryReport/Revenue/Cost/Risk） | 大模块多子引擎，各自独立可调用 |
| 状态机 | 自实现（7+ 转换规则） | 项目状态比 BaseEngine 复杂，需独立管理 |
| 加密 | AES-256（字段级） | 预算/成本敏感数据加密存储 |
| 通知 | 企业微信 Webhook | 里程碑提醒/风险告警 |
| 定时任务 | APScheduler | 成本汇总/风险巡检/里程碑提醒 |
| Excel 导出 | openpyxl | 项目总览/成本明细/风险清单 |

### 11.2 依赖的 L2/L3/L4 资产

| 资产 | 层级 | 复用方式 |
| ---|---|---|
| BaseEngine / BaseService | L4 BDMS Base | 5 个子引擎全部继承 |
| BaseImporter / BaseExporter | L4 BDMS Base | 成本导入/导出，风险导出 |
| L2 Persistence-006 | L2 | SQLite + Repository 模式 |
| 状态机框架 | L4 BDMS Base | 项目状态机 |
| 审计日志框架 | L4 BDMS Base | 所有状态变更留痕 |
| 合同信息 | Contract Management 模块 | 项目立项时关联合同 |
| 售后移交 | After-sales Management 模块 | 结项时移交售后 |

### 11.3 与现有代码的复用/重构关系

- 现有 `modules/project_management/` 在 v1.0 中有基础骨架（ProjectEngine/ProjectManagementService），但缺少 4 个子引擎
- v2.1 保留并扩展现有骨架，新增 CostEngine/RiskEngine/RevenueEngine
- 现有 delivery_report 引擎纳入 ProjectManagementService 作为子引擎之一
- 现有 revenue 引擎纳入 ProjectManagementService 作为子引擎之一

---

## 12 非功能设计

### 12.1 性能

| 场景 | 目标 | 手段 |
| ---|---|---|
| 项目列表查询（100+ 执行中） | < 500ms | 分页 + 索引 + 状态缓存 |
| 成本汇总（月度） | < 1s | 预计算快照 + 增量更新 |
| 风险统计 | < 500ms | 实时查询 + 缓存 |
| 项目仪表盘 | < 1s | 聚合查询 + 缓存 |
| 并发项目执行 | 100+ 在执行项目 | SQLite WAL + 连接池 |

### 12.2 可靠性

- **子引擎独立**：各子引擎可单独测试/演进，单点故障不影响其他子引擎
- **事务边界清晰**：子引擎之间通过 Service 层交互，不直接跨引擎调用
- **结项检查完整性**：交付完成 + 验收通过 + 成本结清 + 风险关闭 四重检查
- **幂等保障**：工时提交/结项操作幂等，重复调用不产生副作用

### 12.3 安全

- **项目权限**：项目经理/成员/部门经理/财务/高管五级权限
- **字段级加密**：预算/成本敏感数据 AES-256 加密存储
- **审计日志**：项目状态变更 + 成本记录 + 风险操作全程留痕
- **输入校验**：外部数据通过 integration 模块标准化

### 12.4 可用性

- **子引擎降级**：某个子引擎暂时不可用时，其他子引擎仍可独立工作
- **数据备份**：项目数据随 BDMS 整体备份策略执行
- **通知降级**：企业微信不可用时降级为邮件 + 日志告警

---

## 13 风险与权衡

| 风险 | 影响 | 缓解措施 |
| ---|---|---|
| 子引擎接口变更 | 上游调用方适配成本 | 语义化版本 + 弃用周期 + 契约测试 |
| 项目状态机遗漏 | 非法状态转换 | 单元测试覆盖所有合法/非法转换 + 运行时校验 |
| 成本计算口径不一致 | 不同模块成本数据打架 | 统一 schemas 定义 + 跨模块对账脚本 |
| 工时大量提交（月>10000） | DB 写入压力 | 批量插入 + 队列缓冲 + 异步汇总 |
| 风险升级链路断裂 | 高风险无人处理 | 定时巡检 + 告警通知 + 自动升级 |
| 跨模块集成复杂 | 数据不一致 | 事件驱动 + 定时对账 + 数据一致性检查 |
| 子引擎开发进度不一 | 整体交付延迟 | 子引擎独立里程碑 + 并行开发 + 契约先行 |

---

## 14 变更历史

| 版本 | 日期 | 作者 | 变更内容 |
|---|---|---|---|
| v2.1 | 2026-09-19 | BDMS Architecture | 初始版本：项目管理模块详细设计（含 5 个子引擎） |
