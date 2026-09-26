# BDMS v2.1 售后管理（After-sales Management）详细设计

| 项 | 值 |
|---|---|
| 版本 | v2.1 |
| 层级 | L4 BDMS 模块详细设计 |
| 继承 | L3 After-sales Management |
| 状态 | 设计中 |
| 模块编码 | after_sales |
| 对应 L3 域 | After-sales Management |
| 横切依赖 | Base Service / Exporter 框架，项目管理模块（上游），合同管理模块（关联），知识库（关联） |

---

## 1 模块概述

### 1.1 业务域

售后管理模块覆盖**售后维保与工单管理**全流程，是项目全生命周期的关键组成部分：

```
项目立项 → ... → 项目验收 → 售后移交 → 工单管理 → 售后完结 → 项目结项
                    ↑                                    ↓
                    └────────── 售后维保期 ←─────────────┘
```

**核心说明**：在 Bangcle 项目全生命周期中，**结项 = 整个项目完结（含售后服务完结）**。售后管理是项目管理的一部分，售后服务期从项目验收后开始，到售后完结后项目才正式结项。

业务场景：
- 项目验收后自动进入售后维保期
- 客户通过电话/邮件/企业微信报修 → 创建售后工单
- 按合同约定的服务等级（SLA）分派给对应工程师
- 全程追踪工单状态与 SLA 达成情况
- 所有工单关闭且维保期满后 → 售后完结 → 触发项目结项
- 关联合同管理模块，获取售后服务条款（SLA 等级、维保范围）
- 关联产品/服务知识库，辅助工单处理和故障排查

### 1.2 上游来源与下游出口

**上游**：

| 来源 | 触发方式 | 说明 |
|---|---|---|
| 项目验收 | 项目管理模块 `accept_project` 后触发 | 自动进入售后维保期，创建维保合同 |
| 合同管理 | 关联合同条款获取 SLA 等级 | 售后服务条款自动配置 |
| 知识库 | 产品/服务知识库关联 | 故障排查 FAQ 和处置方案推荐 |

**下游**：

| 出口 | 触发条件 | 说明 |
|---|---|---|
| 售后完结 | 所有工单关闭 + 维保期满 | 触发项目结项 |
| 项目结项 | 售后完结后 | 项目管理模块 `close_project` 完成最终结项 |

### 1.3 横切关系

| 横切关注点 | 处理方式 |
|---|---|
| 权限 | 客服 / 售后工程师 / 售后主管 / 管理员 |
| SLA | 按合同约定的服务等级自动计算响应/解决时限 |
| 通知 | 工单分派 / 超时 / 解决 自动通知工程师和客户联系人 |
| 统计 | SLA 达成率 / 工单量 / 平均解决时长 / 产品-版本分布 / 时间趋势 |
| 审计 | 工单状态变更全程留痕 |
| 合同关联 | 关联合同管理模块，获取售后服务条款 |
| 知识库关联 | 关联产品/服务知识库，辅助故障排查 |

### 1.4 产品/服务知识库关联

售后工单处理时，自动关联知识库中的故障排查 FAQ 和产品规格，辅助工程师快速定位问题。

| 关联方式 | 说明 |
|---|---|
| 工单创建时 | 按产品类型匹配 FAQ，推荐相关故障排查方案 |
| 工单处理时 | 搜索知识库产品规格，获取技术参数和部署要求 |
| 工单解决时 | 将解决方案沉淀为知识库条目，反哺知识库 |

### 1.5 合同管理模块关联

售后服务的 SLA 等级和维保范围由合同约定。合同管理模块提供：

| 合同字段 | 售后用途 |
|---|---|
| `service_level` | 自动设置售后工单 SLA 等级 |
| `warranty_period` | 确定维保期限 |
| `after_sales_clauses` | 获取售后服务范围和排除项 |
| `response_time` / `resolution_time` | 自定义 SLA 时限（覆盖默认等级） |

---

## 2 接口契约

### 2.1 AfterSalesService

```python
from typing import Optional, List, Dict, Tuple
from datetime import datetime, date
from enum import Enum


class TicketState(str, Enum):
    OPEN = "open"              # 已创建，待分派
    ASSIGNED = "assigned"      # 已分派给工程师
    IN_PROGRESS = "in_progress"  # 处理中
    RESOLVED = "resolved"       # 已解决
    CLOSED = "closed"           # 已关闭（客户确认）
    REOPENED = "reopened"       # 重新打开


class TicketPriority(str, Enum):
    LOW = "low"              # P4 - 一般问题
    MEDIUM = "medium"       # P3 - 较重要
    HIGH = "high"           # P2 - 重要
    CRITICAL = "critical"    # P1 - 紧急


class ServiceLevel(str, Enum):
    GOLD = "gold"        # 金牌：4h 响应，24h 解决
    SILVER = "silver"    # 银牌：8h 响应，48h 解决
    BRONZE = "bronze"    # 铜牌：24h 响应，72h 解决


class AfterSalesService(BaseService):
    """
    售后服务层：售后移交 + 工单全生命周期管理 + SLA 管理。
    """

    # ---------- 售后移交 ----------

    def transfer_to_after_sales(
        self,
        project_id: str,
        warranty_period_months: int = 12,
        service_level: ServiceLevel = ServiceLevel.SILVER,
        customer_contact: str = None,
        customer_contact_phone: str = None,
    ) -> str:
        """
        项目验收后转入售后维保。
        由 ProjectManagementService.accept_project 自动触发。

        Args:
            project_id: 项目 ID
            warranty_period_months: 质保期（月）
            service_level: 服务等级
            customer_contact: 客户联系人
            customer_contact_phone: 联系电话

        Returns:
            after_sales_contract_id
        """
        ...

    # ---------- 工单管理 ----------

    def create_ticket(
        self,
        source: str,                       # 报修来源：phone / email / wechat / project / other
        title: str,
        description: str,
        project_id: str = None,
        customer_name: str = None,
        customer_contact: str = None,
        customer_phone: str = None,
        priority: TicketPriority = TicketPriority.MEDIUM,
        service_level: ServiceLevel = None,
        created_by: str = None,
    ) -> str:
        """
        创建售后工单。

        自动计算：
        - SLA 响应时限
        - SLA 解决时限
        - 初始状态: open

        Returns:
            ticket_id
        """
        ...

    def assign_ticket(
        self,
        ticket_id: str,
        assignee: str,
        assigner: str = None,
        comment: str = "",
    ) -> None:
        """
        分派工单：open → assigned。
        通知被分派的工程师。
        """
        ...

    def start_ticket(
        self,
        ticket_id: str,
        operator: str,
    ) -> None:
        """
        开始处理：assigned → in_progress。
        记录响应时间，用于 SLA 计算。
        """
        ...

    def resolve_ticket(
        self,
        ticket_id: str,
        resolver: str,
        resolution: str,
        resolution_type: str = "fixed",    # fixed / workaround / duplicate / wont_fix
    ) -> None:
        """
        解决工单：in_progress → resolved。
        记录解决时间，用于 SLA 计算。
        通知客户确认。
        """
        ...

    def close_ticket(
        self,
        ticket_id: str,
        closer: str,
        close_note: str = "",
    ) -> None:
        """
        关闭工单：resolved → closed。
        通常由客户确认后关闭，或自动关闭（resolved 后 N 天无反馈）。
        """
        ...

    def reopen_ticket(
        self,
        ticket_id: str,
        reopener: str,
        reason: str,
    ) -> None:
        """
        重新打开工单：resolved/closed → reopened → in_progress。
        用于客户不满意或问题复现。
        """
        ...

    # ---------- 查询 ----------

    def list_tickets(
        self,
        state: TicketState = None,
        priority: TicketPriority = None,
        assignee: str = None,
        project_id: str = None,
        customer_keyword: str = None,
        date_from: date = None,
        date_to: date = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[Dict], int]:
        """工单列表查询。"""
        ...

    def get_ticket(self, ticket_id: str) -> Dict:
        """
        获取工单详情：
        基本信息 + 处理历史 + SLA 情况 + 关联项目/合同信息
        """
        ...

    def get_sla_summary(
        self,
        period_start: date = None,
        period_end: date = None,
        service_level: ServiceLevel = None,
    ) -> Dict:
        """
        SLA 统计概览：
        {
            "total_tickets": int,
            "response_sla_rate": float,       # 响应达标率 (%)
            "resolution_sla_rate": float,     # 解决达标率 (%)
            "avg_response_time_hours": float, # 平均响应时长
            "avg_resolution_time_hours": float, # 平均解决时长
            "overdue_response": int,          # 响应超时工单数
            "overdue_resolution": int,        # 解决超时工单数
            "by_service_level": {...},
            "by_priority": {...}
        }
        """
        ...

    def get_engineer_performance(
        self,
        engineer_id: str = None,
        period_start: date = None,
        period_end: date = None,
    ) -> Dict:
        """工程师绩效统计：处理工单数 / 平均解决时长 / SLA 达标率。"""
        ...

    # ---------- 售后完结 ----------

    def complete_after_sales(
        self,
        project_id: str,
        operator: str,
    ) -> None:
        """
        售后完结：所有工单关闭 + 维保期满 → 触发项目结项。
        调用 ProjectManagementService.close_project 完成最终结项。
        """
        ...
```

### 2.2 AfterSalesExporter

```python
class AfterSalesExporter(BaseExporter):
    """
    售后导出器。
    输出格式：Excel / PDF / CSV
    """

    def export_ticket_list(
        self,
        filters: Dict = None,
        format: str = "xlsx",
    ) -> bytes:
        """导出工单列表。"""
        ...

    def export_sla_summary(
        self,
        period_start: date = None,
        period_end: date = None,
        format: str = "xlsx",
    ) -> bytes:
        """导出 SLA 统计报表。"""
        ...

    def export_engineer_performance(
        self,
        period_start: date = None,
        period_end: date = None,
        format: str = "xlsx",
    ) -> bytes:
        """导出工程师绩效报表。"""
        ...

    def export_ticket_detail(self, ticket_id: str, format: str = "pdf") -> bytes:
        """导出单张工单详情（含处理历史）。"""
        ...
```

### 2.3 AfterSalesAnalyticsService

```python
class AfterSalesAnalyticsService:
    """
    售后服务分析服务：提供多维度统计分析能力。
    """
    
    def get_ticket_trend(
        self,
        product_id: str = None,
        period_start: date = None,
        period_end: date = None,
        granularity: str = "month",  # day / week / month
    ) -> List[Dict]:
        """
        工单趋势分析：
        [{"date": "2026-09-01", "created": 5, "resolved": 3, "closed": 2}, ...]
        """
        ...
    
    def get_product_version_distribution(
        self,
        period_start: date = None,
        period_end: date = None,
    ) -> List[Dict]:
        """
        产品-版本-工单分布：
        [{"product": "等保测评系统", "version": "v2.1", "ticket_count": 15, "ratio": 0.3}, ...]
        """
        ...
    
    def get_resolution_time_distribution(
        self,
        product_id: str = None,
        period_start: date = None,
        period_end: date = None,
    ) -> Dict:
        """
        解决时长分布：
        {"p50": 4.2, "p90": 18.5, "p95": 24.0, "avg": 8.5, "unit": "hours"}
        """
        ...
    
    def get_repeat_issue_analysis(
        self,
        project_id: str = None,
        threshold: int = 3,
    ) -> List[Dict]:
        """
        重复性问题识别：同一问题出现 ≥ threshold 次
        [{"issue_pattern": "数据库连接池耗尽", "count": 5, "projects": [...]}, ...]
        """
        ...
    
    def get_customer_health_score(
        self,
        customer_id: str,
    ) -> Dict:
        """
        客户健康度评分（0-100）：
        综合：工单频率 + SLA达标率 + 满意度 + 维保期限
        """
        ...
```

---

## 3 数据模型

引用《BDMS v2.1 数据模型详细设计》§8，共 3 张 `as_` 表。

### 3.1 表清单

| 表名 | 中文名 | 说明 |
|---|---|---|
| `as_tickets` | 售后工单表 | 工单基本信息与状态 |
| `as_ticket_history` | 工单历史表 | 工单状态变更 / 处理记录 / 操作日志 |
| `as_warranty_contracts` | 售后维保合同表 | 项目移交后的维保期信息 |

### 3.2 字段说明（关键字段）

**as_tickets（主表）：**

| 字段 | 类型 | 说明 | 加密/脱敏 |
|---|---|---|---|
| `ticket_id` | varchar(32) | 工单编号（主键） | - |
| `title` | varchar(255) | 工单标题 | - |
| `description` | text | 问题描述 | - |
| `state` | varchar(20) | 工单状态 | - |
| `priority` | varchar(20) | 优先级 | - |
| `service_level` | varchar(20) | 服务等级 | - |
| `source` | varchar(20) | 报修来源 | - |
| `project_id` | varchar(32) | 关联项目 ID | - |
| `customer_name` | varchar(255) | 客户名称 | AES-256 加密 |
| `customer_contact` | varchar(100) | 客户联系人 | AES-256 加密 |
| `customer_phone` | varchar(50) | 联系电话 | AES-256 加密 |
| `assignee` | varchar(100) | 指派工程师 | - |
| `product_id` | varchar(50) | 关联产品 ID | - |
| `product_version` | varchar(50) | 产品版本 | - |
| `created_at` | datetime | 创建时间 | - |
| `response_at` | datetime | 响应时间（首次处理时间） | - |
| `resolved_at` | datetime | 解决时间 | - |
| `closed_at` | datetime | 关闭时间 | - |
| `response_deadline` | datetime | SLA 响应截止时间 | - |
| `resolution_deadline` | datetime | SLA 解决截止时间 | - |
| `resolution` | text | 解决方案 | - |
| `resolution_type` | varchar(30) | 解决类型 | - |

**as_warranty_contracts（维保合同表）：**

| 字段 | 类型 | 说明 |
|---|---|---|
| `contract_id` | varchar(32) | 维保合同 ID |
| `project_id` | varchar(32) | 关联项目 ID |
| `warranty_start` | date | 维保开始日期 |
| `warranty_end` | date | 维保结束日期 |
| `service_level` | varchar(20) | 服务等级 |
| `remaining_tickets` | int | 剩余工单额度（如按次计费） |
| `status` | varchar(20) | 状态：active / expired |

### 3.3 脱敏规则

| 场景 | 字段 | 脱敏规则 |
|---|---|---|
| 列表接口（非售后角色） | `customer_name` | 首尾各 1 字，中间 `*` |
| 列表接口 | `customer_phone` | 前 3 后 4，中间 `*` |
| 导出（非管理员） | `customer_phone` | 同上 |

---

## 4 状态机

### 4.1 工单状态流转图

```
                    创建
       ┌────────────────────────┐
       │                        ▼
    ┌──────┐  分派   ┌─────────┐  开始处理  ┌─────────────┐
    │ open │ ──────► │ assigned│ ────────► │ in_progress │
    └──────┘         └─────────┘            └──────┬──────┘
       ▲                                          │
       │                                          │ 解决
       │                                          ▼
       │                                    ┌──────────┐
       │                                    │ resolved │
       │                                    └────┬─────┘
       │                                         │
       │  重新打开                               │ 关闭（客户确认）
       │                                         ▼
       │                                    ┌──────────┐
       └────────────────────────────────────│  closed  │
         （从 resolved / closed 重新打开）   └──────────┘
```

### 4.2 状态转换表

| 当前状态 | 操作 | 目标状态 | 执行角色 | 条件 |
|---|---|---|---|---|
| `open` | assign | `assigned` | 客服 / 售后主管 | 指定了 assignee |
| `open` | auto_assign | `assigned` | 系统 | 自动分派规则命中 |
| `assigned` | start | `in_progress` | 被指派工程师 | 本人操作 |
| `assigned` | reassign | `assigned` | 售后主管 | 更换工程师 |
| `in_progress` | resolve | `resolved` | 处理工程师 | 填写了 resolution |
| `in_progress` | escalate | `in_progress` | 工程师 / 主管 | 升级到高级工程师，状态不变但更换处理人 |
| `resolved` | close | `closed` | 客户 / 客服 / 系统（自动） | 客户确认或 N 天后自动关闭 |
| `resolved` | reopen | `in_progress` | 客户 / 客服 | 填写重开原因 |
| `closed` | reopen | `in_progress` | 售后主管 | 填写重开原因，需审批 |
| 任意状态 | cancel | `closed` | 售后主管 | 工单取消，需注明原因 |

---

## 5 SLA 计算规则

### 5.1 服务等级标准

| 服务等级 | 响应时限 | 解决时限 | 适用场景 |
|---|---|---|---|
| GOLD（金牌） | 4 小时 | 24 小时 | 重要客户 / 紧急系统 |
| SILVER（银牌） | 8 小时 | 48 小时 | 标准客户（默认） |
| BRONZE（铜牌） | 24 小时 | 72 小时 | 普通客户 / 非核心系统 |

### 5.2 计算公式

**响应时长**：
```
response_duration = response_at - created_at
response_sla_met = response_duration ≤ response_sla_hours
```

**解决时长**：
```
resolution_duration = resolved_at - created_at
resolution_sla_met = resolution_duration ≤ resolution_sla_hours
```

**响应 SLA 达标率**：
```
response_sla_rate = (response_sla_met_count / total_tickets_with_response) × 100%
```

**解决 SLA 达标率**：
```
resolution_sla_rate = (resolution_sla_met_count / total_resolved_tickets) × 100%
```

**超时率**：
```
response_overdue_rate = 100% - response_sla_rate
resolution_overdue_rate = 100% - resolution_sla_rate
```

### 5.3 特殊规则

1. **工作时间计算**：SLA 按**工作时间**计算（工作日 9:00-18:00），非工作时间暂停计时
2. **暂停机制**：
   - 等待客户反馈期间，SLA 计时暂停（需标记 "pending_customer" 子状态）
   - 等待第三方（如厂商支持）期间，SLA 计时暂停
3. **优先级调整**：
   - CRITICAL 优先级的工单，SLA 自动提升一级（如 SILVER → GOLD 标准）
4. **重开工单**：
   - 重开后，解决 SLA 重新计时
   - 响应 SLA 不重新计算（以首次响应为准）

### 5.4 SLA 监控触发点

| 触发点 | 动作 |
|---|---|
| 响应 SLA 剩余 50% | 提醒工程师 |
| 响应 SLA 剩余 10% | 告警 + 通知主管 |
| 响应 SLA 超时 | 升级 + 通知经理 |
| 解决 SLA 剩余 50% | 提醒工程师 |
| 解决 SLA 剩余 10% | 告警 + 通知主管 |
| 解决 SLA 超时 | 升级 + 通知经理 + 计入绩效 |

---

## 6 核心数据流

### 6.1 项目转售后 → 工单创建 → 分派 → 解决 完整流程

```python
# 伪代码：售后工单完整流程
def after_sales_full_flow():
    # ===== 阶段 1：项目验收移交售后
    # 由 ProjectManagementService.accept_project 自动触发
    after_sales_contract_id = after_sales_service.transfer_to_after_sales(
        project_id="PROJ-001",
        warranty_period_months=12,
        service_level=ServiceLevel.SILVER,
        customer_contact="李经理",
        customer_contact_phone="13800138000",
    )
    # 维保期：2026-12-25 ~ 2027-12-24

    # ===== 阶段 2：客户报修 → 创建工单
    ticket_id = after_sales_service.create_ticket(
        source="phone",
        title="系统登录失败",
        description="客户反馈今早开始无法登录管理后台，报错 500",
        project_id="PROJ-001",
        customer_name="XX 公司",
        customer_contact="李经理",
        customer_phone="13800138000",
        priority=TicketPriority.HIGH,
        created_by="kefu_001",
    )
    # 自动计算 SLA（SILVER 等级 + HIGH 优先级 → 提升为 GOLD 标准）：
    # - response_deadline = created_at + 4h
    # - resolution_deadline = created_at + 24h
    # state: open

    # ===== 阶段 3：分派工单
    after_sales_service.assign_ticket(
        ticket_id=ticket_id,
        assignee="engineer_wang",
        assigner="after_sales_lead",
        comment="高优先级，请尽快处理",
    )
    # 通知 engineer_wang
    # state: assigned

    # ===== 阶段 4：开始处理
    after_sales_service.start_ticket(
        ticket_id=ticket_id,
        operator="engineer_wang",
    )
    # 记录 response_at = 当前时间
    # state: in_progress

    # ===== 阶段 5：问题排查 & 解决
    # ... 工程师排查问题 ...
    after_sales_service.resolve_ticket(
        ticket_id=ticket_id,
        resolver="engineer_wang",
        resolution="数据库连接池耗尽，已调整配置并重启服务",
        resolution_type="fixed",
    )
    # 记录 resolved_at = 当前时间
    # 通知客户确认
    # state: resolved

    # ===== 阶段 6：客户确认关闭
    after_sales_service.close_ticket(
        ticket_id=ticket_id,
        closer="kefu_001",
        close_note="客户确认问题已解决，满意度良好",
    )
    # state: closed

    # ===== SLA 验证
    sla_summary = after_sales_service.get_sla_summary()
    # 检查该工单：
    # - 响应时长 = 30 min < 4h ✅
    # - 解决时长 = 3h < 24h ✅
    # - SLA 全部达标
```

### 6.2 售后完结 → 项目结项流程

```python
def after_sales_completion_flow():
    # 条件：所有工单关闭 + 维保期满
    after_sales_service.complete_after_sales(
        project_id="PROJ-001",
        operator="after_sales_lead",
    )
    # 触发项目结项
    # ProjectManagementService.close_project(...)
    # state: closed
```

---

## 7 CLI 命令设计

```bash
# 售后管理模块命令
bdms after-sales <subcommand> [options]
# 或简写
bdms as <subcommand> [options]

# 售后移交
bdms after-sales transfer <project_id> --warranty 12 --level silver --contact "..." --phone "..."

# 工单管理
bdms after-sales ticket create --title "..." --description "..." --source phone --priority high --project <id>
bdms after-sales ticket show <ticket_id>
bdms after-sales ticket list [--state open] [--priority high] [--assignee ...] [--project ...] [--page 1]
bdms after-sales ticket assign <ticket_id> --assignee engineer_wang [--comment "..."]
bdms after-sales ticket start <ticket_id>
bdms after-sales ticket resolve <ticket_id> --resolution "..." --type fixed
bdms after-sales ticket close <ticket_id> [--note "..."]
bdms after-sales ticket reopen <ticket_id> --reason "问题复现"
bdms after-sales ticket history <ticket_id>              # 查看工单历史

# SLA 统计
bdms after-sales sla summary [--period 2026-09] [--level gold]
bdms after-sales sla overdue [--period 2026-09]         # 查看超时工单
bdms after-sales sla engineer <engineer_id> [--period 2026-09]  # 工程师绩效

# 分析
bdms after-sales analytics trend [--period 2026-09] [--granularity month]
bdms after-sales analytics product [--period 2026-09]
bdms after-sales analytics repeat [--threshold 3]
bdms after-sales analytics customer <customer_id>

# 维保合同
bdms after-sales warranty list [--status active]
bdms after-sales warranty show <contract_id>
bdms after-sales warranty check <project_id>            # 检查项目维保状态

# 售后完结
bdms after-sales complete <project_id>                   # 售后完结 → 触发项目结项

# 导出
bdms after-sales export tickets [--filters ...] --format xlsx
bdms after-sales export sla [--period 2026-09] --format xlsx
bdms after-sales export performance [--period 2026-09] --format xlsx
bdms after-sales export ticket <ticket_id> --format pdf
```

---

## 8 实现路径

### 第 1 步：核心数据模型 + 工单管理（0.5 天）

- [ ] 创建 `after_sales/` 模块目录
- [ ] 定义 3 张 `as_` 表的 SQLAlchemy 模型
- [ ] 实现 `AfterSalesService` 工单 CRUD + 状态流转
- [ ] 实现工单状态机（7 种状态，10+ 转换）
- [ ] 单元测试：状态机转换正确性

### 第 2 步：SLA 计算 + 移交 + 导出 + CLI（0.5 天）

- [ ] 实现 SLA 计算逻辑（响应/解决时限 + 工作时间 + 暂停机制）
- [ ] 实现 `transfer_to_after_sales`（与项目管理模块集成）
- [ ] 实现 `AfterSalesExporter`（4 种导出）
- [ ] 实现 `bdms after-sales` CLI 命令（约 25 个子命令）
- [ ] 集成测试：项目移交 → 工单 → SLA 统计 全流程
- [ ] 编写模块 README

### 第 3 步：分析能力 + 合同/知识库关联（0.5 天）

- [ ] 实现 `AfterSalesAnalyticsService`（4 种分析能力）
- [ ] 关联合同管理模块获取 SLA 等级
- [ ] 关联知识库获取故障排查方案
- [ ] 实现售后完结 → 项目结项流程
- [ ] 集成测试：售后完结 → 项目结项

---

## 9 预期效果 + 验收标准

### 9.1 预期效果

- 售后工单全流程线上化，处理时效可追踪
- SLA 达标率从人工管理的 ~85% 提升到 ≥ 95%
- 平均响应时间缩短 50%
- 支持同时处理 200+ 活跃工单
- 客户满意度提升

### 9.2 验收标准

| 类别 | 验收项 | 通过标准 |
|---|---|---|
| 工单功能 | 工单 CRUD + 状态流转 | 7 种状态、10+ 转换全部正确 |
| 售后移交 | 项目转售后 | 维保合同正确创建，信息完整 |
| SLA 计算 | 响应/解决 SLA | 计算准确，工作时间规则正确 |
| SLA 监控 | 超时告警 | 各触发点正确触发通知 |
| 状态机 | 非法转换拦截 | 非法操作被拒绝并给出原因 |
| 性能 | 工单列表 + SLA 统计 | 列表查询 < 500ms（万级）；SLA 统计 < 1s |
| 幂等 | 重复分派 / 重复解决 | 重复操作不产生副作用 |
| 安全 | 客户信息脱敏 | 列表中电话号码脱敏显示 |
| 分析 | 多维度统计 | 时间趋势/产品-版本分布/重复识别 全部可用 |
| 集成 | 售后完结 → 项目结项 | 售后完结后自动触发项目结项 |

### 9.3 验收 7 步法映射

| 步骤 | 对应验收内容 |
|---|---|
| ① 功能正确性 | 工单 CRUD + 状态流转 |
| ② 边界条件 | 工作时间计算、暂停机制、重开工单 |
| ③ 数据一致性 | 工单状态与历史表一致 |
| ④ 安全合规 | 客户信息加密/脱敏 |
| ⑤ 性能 | 列表查询 + SLA 统计 |
| ⑥ 集成 | 项目管理模块移交售后 + 合同关联 + 知识库关联 |
| ⑦ 幂等验证 | 重复分派 / 重复解决 / 重复关闭 |

---

## 10 复用资产映射

| 资产 | 来源 | 复用方式 |
|---|---|---|
| BaseService / BaseExporter | BDMS Base 模块 | 继承基类 |
| 状态机框架 | BDMS Base 模块 | 工单状态机 |
| 审计日志框架 | BDMS Base 模块 | 工单历史记录 |
| 企业微信通知 | 全局 WeCom 集成 | 工单分派 / 超时 / 解决通知 |
| 项目信息 | Project Management 模块 | 售后移交时读取项目信息 |
| 合同条款 | Contract Management 模块 | 获取售后服务 SLA 等级 |
| 知识库 | Knowledge Base 模块 | 故障排查 FAQ 和处置方案 |
| 人员信息 | 组织架构模块 | 工程师分派与绩效 |

---

## 11 技术方案

### 11.1 技术选型

| 维度 | 选型 | 依据 |
| ---|---|---|
| 语言 | Python 3.10+ | 与 BDMS 全栈一致 |
| 持久化 | SQLite（通过 core.db） | 与工单/项目/合同模块共享连接 |
| 状态机 | 自实现（10+ 转换规则） | 工单状态比 BaseEngine 复杂，需独立管理 |
| 加密 | AES-256（字段级） | 客户姓名/电话/联系人需加密存储 |
| 脱敏 | 正则 + 角色判断 | 不同角色看到不同脱敏级别 |
| 通知 | 企业微信 Webhook | 工单分派/超时/解决自动通知 |
| 定时任务 | APScheduler | SLA 超时检测 + 自动关闭 |
| Excel 导出 | openpyxl | 工单列表 + SLA 报表 + 绩效报表 |

### 11.2 依赖的 L2/L3/L4 资产

| 资产 | 层级 | 复用方式 |
| ---|---|---|
| BaseService / BaseExporter | L4 BDMS Base | 继承基类 |
| L2 Persistence-006 | L2 | SQLite + Repository 模式 |
| 企业微信通知 | L4 全局 WeCom 集成 | 工单分派/超时/解决通知 |
| 项目信息 | Project Management 模块 | 售后移交时读取项目信息 |
| 合同条款 | Contract Management 模块 | 获取售后服务 SLA 等级 |
| 知识库 | Knowledge Base 模块 | 故障排查 FAQ 和处置方案 |

### 11.3 与现有代码的复用/重构关系

- 现有 `modules/after_sales/` 在 v1.0 中未实现，v2.1 从零构建
- 状态机参考 BaseEngine 的 job 生命周期模式，但独立于 BaseEngine
- SLA 计算逻辑封装为 `SLACalculator` 纯函数类，可被 Dashboard/报表复用
- 售后服务分析能力封装为 `AfterSalesAnalyticsService`，可被 Dashboard 和报表复用
- 关联合同管理模块获取 SLA 等级，关联知识库获取故障排查方案

---

## 12 非功能设计

### 12.1 性能

| 场景 | 目标 | 手段 |
| ---|---|---|
| 工单列表查询（万级） | < 500ms | 分页 + 索引 + 状态缓存 |
| SLA 统计（月度） | < 1s | 预计算快照 + 增量更新 |
| SLA 实时计算（单条） | < 100ms | 纯 Python 计算，无 IO |
| 并发工单处理 | 200+ 活跃工单 | SQLite WAL 模式 + 连接池 |

### 12.2 可靠性

- **SLA 超时检测兜底**：定时任务每分钟扫描，即使事件丢失也能及时告警
- **工单状态一致性**：状态转换与历史表写入同事务
- **通知失败重试**：企业微信通知失败后重试 3 次（指数退避）
- **自动关闭幂等**：resolved 后 N 天自动关闭，重复执行不产生副作用

### 12.3 安全

- **字段级加密**：客户姓名/电话 AES-256 加密存储
- **角色脱敏**：非售后角色看不到完整客户信息
- **审计日志**：工单状态变更全程留痕（who/when/what）
- **API 权限**：工单创建/分派/解决需对应角色权限

### 12.4 可用性

- **降级策略**：企业微信不可用时，降级为邮件通知 + 日志告警
- **数据备份**：工单数据随 BDMS 整体备份策略执行

---

## 13 风险与权衡

| 风险 | 影响 | 缓解措施 |
| ---|---|---|
| SLA 计算规则变更 | 历史数据口径不一致 | 版本化 SLA 规则 + 数据迁移脚本 |
| 工单量激增（>500/月） | 列表查询变慢 | 分页 + 归档策略（6 个月以上工单归档） |
| 企业微信通知不稳定 | 工单分派/超时通知丢失 | 降级为邮件 + 定时任务补发 |
| 客户信息加密密钥轮换 | 历史数据不可读 | 密钥版本化 + 双密钥过渡期 |
| 状态机规则遗漏 | 非法状态转换 | 单元测试覆盖所有合法/非法转换 |

---

## 14 变更历史

| 版本 | 日期 | 作者 | 变更内容 |
|---|---|---|---|
| v2.1 | 2026-09-19 | BDMS Architecture | 初始版本：售后管理模块详细设计 |
| v2.1 | 2026-09-19 | BDMS Architecture | 新增：合同关联 + 知识库关联 + 分析能力 + 售后完结流程 |
