# BDMS v2.1 设计大纲

> Bangcle Delivery Management System — 设计文档第一部分
> 版本：v2.1 Outline（2026-09-18）
> 层级：L4 专有业务层
> 继承：L3 `delivery-management-framework`（整体框架）
> 模块3 合同审核管理 额外继承：L3 `contract-approval`（纯逻辑核心）
> 状态：设计阶段，待 Rex 审核

---

## 0. 版本定位

| 维度 | v1.0（现有） | v2.1（本次迭代） |
|---|---|---|
| 模块数 | 5（月报/确收/主数据/看板/设置） | **6**（+合同审核管理） |
| 架构 | 平层模块（core + 5 modules） | **分层**（core + base + modules + L3 框架契约层） |
| 流程覆盖 | 交付月报 + 确收分析（财务侧） | **16 个流程阶段全链路**（立项→实施→交付→验收→确收→售后→结项→风控→成本） |
| 代码 vs AI | 部分逻辑由 AI 生成 | **全代码实现**，AI 仅作为独立 Agent 调用入口 |
| 可复用资产 | 零散复用 delivery-center / revenue-recognition | **系统化复用** L3/L2 组件，显式列出可复用清单 |
| 高内聚低耦合 | 部分共享但无明确边界 | **明确接口契约**，模块可独立被 AI Agent 调用 |

---

## 1. 设计目标与原则

### 1.1 核心目标

1. **功能完整** — 对齐 Bangcle 项目管理完整流程（16 个阶段 / 62 个流程节点，来源：`~/Downloads/项目管理流程.docx`），覆盖：立项审批 → 合同下单 → 项目立项 → 项目实施（产品/安服/定制/外包）→ 项目交付 → 项目验收 → 收入确认 → 转售后 → 项目结项 → 成本管理 → 风险处置。现有交付月报 + 确收分析模块保留并优化。
2. **高内聚低耦合** — 每个模块只负责一个业务域，模块间通过明确接口交互
3. **全代码实现** — 核心逻辑 100% 代码实现，AI 仅作为 Agent 调用入口（CLI / API）
4. **独立可调用** — 每个模块暴露纯函数 + CLI 子命令，AI Agent 可独立执行单模块任务
5. **资产复用最大化** — 显式列出 L3/L2/L4 全层级可复用资产，减少重复建设

### 1.1.1 Bangcle 交付管理全流程对齐（已解析并纳入设计）

来源：`~/Downloads/项目管理流程.docx`（16 阶段 / 62 节点）

| 阶段 | 节点 | 对应 BDMS 模块 |
|---|---|---|
| #1 | 立项章程审批（概算/合同/POC/提前实施） | contract_management |
| #2-1/2-2 | 合同下单 / POC / 提前实施申请 | contract_management + project_management |
| #2-3 | 销售合同下单进度监控 | project_management |
| #3-1/3-2 | 项目立项 + 履约项维护 | project_management + master_data |
| #4 | 项目实施前准备（设备/迁移） | project_management |
| #5-1~5-3 | 产品实施任务 + 执行 + 管理 | project_management |
| #6-1~6-3 | 安服实施任务 + 执行 + 管理 | project_management |
| #7-1/7-2 | 产品定制开发需求 + 执行 | project_management |
| #8-1/8-2 | 外包/外采申请 + 管理 | project_management |
| #9-1/9-2 | 项目交付 + 交付监控 | project_management → delivery_report 子引擎 |
| #10-1/10-2 | 项目验收 + 验收监控 | project_management → delivery_report 子引擎 |
| #11 | 收入确认材料交接 | project_management → revenue 子引擎 |
| #12-1~12-3 | 转售后 + 售后工单 + 售后管理 | after_sales |
| #13-1/13-2 | 项目结项 + 结项监控 | project_management（结项域） |
| #14 | 项目成本管理（工时/设备） | project_management → cost 子引擎 |
| #15 | 成本确认材料交接 | project_management → cost 子引擎 |
| #16 | 项目风险处置 | project_management → risk 子引擎 |

> **设计策略**：16 阶段不是 16 个模块，而是按 L3 域聚合为 8 个模块（见 §2.2 模块清单）。每个阶段的流程节点作为模块内的子功能 / 子工作流实现。

### 1.2 设计原则

| 原则 | 含义 | 落地方式 |
|---|---|---|
| **单一职责** | 一个模块只负责一个业务域 | 8 个模块，每模块有明确边界 |
| **接口驱动** | 模块间通过接口交互，不直接依赖实现 | BaseService / BaseEngine 契约 |
| **纯计算优先** | 引擎层纯函数，无副作用 | engine.py 不写 DB、不发请求 |
| **幂等可重入** | 同一输入多次执行结果一致 | auto/read/regenerate 三模式 |
| **AI 友好** | 每个模块都能被 AI Agent 独立调用 | 统一 CLI 入口 + Python API |

---

## 2. 整体架构

### 2.1 分层架构

```
┌─────────────────────────────────────────────────────────────┐
│                      AI Agent 层                              │
│   bdms-cli / FastAPI / WebSocket （各模块独立入口）            │
├─────────────────────────────────────────────────────────────┤
│                      L4 模块层（8 个模块：4 业务 + 4 横切）                    │
│                                                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐        │
│  │合同管理       │  │项目管理       │  │售后管理       │        │
│  │L3: Contract  │  │L3: Project   │  │L3: After-    │        │
│  │Management    │  │Management    │  │sales Mgmt    │        │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘        │
│         │                 │                 │                 │
│         │    ┌────────────┴────────────┐   │                 │
│         │    │ 子引擎：                  │   │                 │
│         │    │ • delivery_report（交付月报）│   │                 │
│         │    │ • revenue（确收管理）      │   │                 │
│         │    │ • cost（成本管理）         │   │                 │
│         │    │ • risk（风险处置）         │   │                 │
│         │    └─────────────────────────┘   │                 │
│         │                 │                 │                 │
│  ┌──────┴───────┐  ┌──────┴───────┐  ┌──────┴───────┐        │
│  │ 数据看板      │  │ 基础数据      │  │ 系统设置      │        │
│  │ 横切         │  │ 横切         │  │ 横切         │        │
│  └──────────────┘  └──────────────┘  └──────────────┘        │
│  ┌──────────────────────────────────────────────┐              │
│  │ integration（横切：ONES/OA/工时/企微/财务）    │              │
│  │ knowledge_base（横切：产品/服务知识库）         │              │
│  └──────────────────────────────────────────────┘              │
├───────┴─────────────┴─────────────┴─────────────┴────────────┤
│                   Base 层 （模块共性抽象）                      │
│      BaseService / BaseEngine / BaseExporter / BaseImporter    │
├─────────────────────────────────────────────────────────────┤
│                   L3 契约层 （继承自 L3）                       │
│   DMS Framework 接口 / ContractApproval 纯逻辑核心              │
│   （状态机 / 风险扫描 / 审核标准 / DDD 骨架）                    │
├─────────────────────────────────────────────────────────────┤
│                   Core 层 （跨模块基础设施）                    │
│      DB / Paths / Schemas / EventBus / Registry               │
├─────────────────────────────────────────────────────────────┤
│                   L2 基础设施层 （系统级复用）                   │
│   OCR-001 / Office-011 / Persistence-006 / Memory-009          │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 模块清单（8 个模块，按 L3 通用业务层域划分，含横切）

| # | 模块名 | L3 域 | 子引擎 | 覆盖流程阶段 | AI Agent 独立调用 |
|---|---|---|---|---|---|
| 1 | `contract_management` | Contract Management | 合同风险扫描、分级审批、文档生成（继承 L3 `contract-approval`） | #1 立项审批 / #2 合同下单 | ✅ `bdms contract scan/approve` |
| 2 | `project_management` | Project Management | 项目立项/结项/生命周期 + 4 个子引擎（见下） | #3~#16（立项→实施→交付→验收→确收→结项→成本→风控） | ✅ `bdms project create/close` |
| 3 | `after_sales` | After-sales Management | 售后交接、工单受理、SLA 管理 | #12 转售后 / 售后工单 | ✅ `bdms after-sales ticket` |
| 4 | `dashboard` | 横切 | 多模块聚合、下钻穿透、趋势分析 | 全阶段 | ✅ `bdms dashboard summary` |
| 5 | `master_data` | 横切 | 图例/部门/产品线等字典 | 全阶段 | ✅ `bdms master-data list` |
| 6 | `settings` | 横切 | 全局配置、默认参数 | 全阶段 | ✅ `bdms settings get/set` |
| 7 | `integration` | 横切 | 外部系统数据接入（ONES/OA/工时/企微/财务） | 全阶段 | ✅ `bdms integration sync ones` |
| 8 | `knowledge_base` | 横切 | 产品/服务知识库（规格/SLA/手册/条款/FAQ） | project_management / after_sales / contract_management | ✅ `bdms knowledge search` |

> **子引擎（归属 project_management 域，但独立可调用）**：
>
> | 子引擎 | 原 v2.1 模块 | 独立 CLI | 独立 Python API |
> |---|---|---|---|
> | `delivery_report` | 交付月报 | `bdms delivery-report generate` | `from bdms.modules.project_management.delivery_report import DeliveryReportEngine` |
> | `revenue` | 收入确认 | `bdms revenue generate` | `from bdms.modules.project_management.revenue import RevenueEngineAdapter` |
> | `cost` | 成本管理 | `bdms cost timesheet/device` | `from bdms.modules.project_management.cost import CostEngine` |
> | `risk` | 风险处置 | `bdms risk report/list` | `from bdms.modules.project_management.risk import RiskEngine` |
>
> 子引擎**对外保留独立接口**（CLI + Python API + 测试），仅模块归属到 L3 域。

### 2.3 模块依赖关系

```
contract_management ──┐
                  ├──> master_data
project_management ─┤
                  │   ├── delivery_report (子引擎)
                  │   ├── revenue (子引擎)
                  │   ├── cost (子引擎)
                  │   └── risk (子引擎)
                  │
after_sales ────────┤
                  │
dashboard ────────┴── 依赖各模块数据（只读）
integration ──────┴── 为各模块提供标准化数据（单向写入）
knowledge_base ───┴── 为 project/after_sales/contract 提供知识检索
```

- 各业务模块 → 依赖 `master_data`（字典数据）+ `settings`（配置）
- `dashboard` → 只读各业务模块数据，不反向依赖
- 模块间**不直接调用**，通过 DB 共享数据 + 事件总线解耦

---

## 3. 模块设计概要

### 3.1 模块 1：合同管理（`contract_management`）

**L3 域**：Contract Management

**业务域**：销售合同全生命周期审核管理

**继承来源**：L3 `contract-approval` 纯逻辑核心（状态机 + 风险扫描 + 审核标准）

**核心功能**：
1. **合同录入** — 基本信息 + 条款解析（OCR 或手动）
2. **风险扫描** — 基于《民法典》13 类条款自动审核
3. **审批流转** — 分级审批状态机（draft → review1-4 → approved → signed → archived）
4. **合同生成** — 基于模板生成 docx
5. **审计追踪** — 全操作日志，不可篡改

**接口**：
```python
class ContractManagenmentEngine(BaseEngine):
    """纯计算层（继承 L3 contract-approval 纯逻辑核心）"""
    def parse_contract(text: str) -> dict
    def scan_risks(contract: dict) -> list[RiskItem]
    def get_approval_level(amount: float) -> int
    def validate_state_transition(from_state, to_state, role) -> bool

class ContractManagementService(BaseService):
    """编排层（L4 持久化 + 流程管理）"""
    def create_contract(**data) -> dict
    def submit_approval(contract_id) -> dict
    def approve(contract_id, approver, role, comment) -> dict
    def reject(contract_id, approver, role, comment) -> dict
    def scan_risks(contract_id) -> dict
    def generate_docx(contract_id) -> Path
    def sign(contract_id) -> dict
    def archive(contract_id) -> dict
    def list_contracts(filters) -> list
    def get_contract(contract_id) -> dict
    def audit_log(contract_id) -> list
```

**数据模型**（新增表，前缀 `cr_`）：

| 表 | 用途 |
|---|---|
| `cr_contract` | 合同主表（基本信息 + 状态 + 金额） |
| `cr_contract_clause` | 合同条款明细（解析结果） |
| `cr_risk_item` | 风险扫描结果（逐条记录） |
| `cr_approval_log` | 审批日志（谁/何时/什么操作） |
| `cr_audit_trail` | 操作审计（全量操作记录） |
| `cr_template` | 合同模板管理 |

**复用资产**：
- ✅ **L3 contract-approval 纯逻辑核心**（状态机 + 风险扫描 + 审核标准，零副作用）
- ✅ L2 OCR-001（扫描件数字化）
- ✅ L2 Office-011（docx 生成 + Excel 报告）
- ✅ L2 Persistence-006（SQLite + Repository）

**AI Agent 独立调用**：
```bash
bdms contract create --title "xxx" --amount 150000
bdms contract scan 1
bdms contract approve 1 --approver "Rex" --role "销售经理"
```

---

### 3.2 模块 2：项目管理（`project_management`）

**L3 域**：Project Management（核心域）

**业务域**：项目全生命周期管理，覆盖 Bangcle 流程阶段 #3~#16

**架构**：project_management 是一个"大模块"，内聚 5 个子引擎，所有子引擎**独立可调用**：

```
project_management/
├── project_core/          # 项目立项/结项/生命周期（核心）
├── delivery_report/       # 子引擎：交付月报 + 验收（原 v1.0 模块）
├── revenue/               # 子引擎：确收管理（原 v1.0 模块）
├── cost/                  # 子引擎：成本管理（新增）
└── risk/                  # 子引擎：风险处置（新增）
```

#### 3.2.1 核心：项目管理引擎（`project_core`）

**接口**：
```python
class ProjectEngine(BaseEngine):
    def init_project(**data) -> dict          # 项目立项
    def update_scope(project_id, **data) -> dict
    def close_project(project_id) -> dict      # 结项
    def get_status(project_id) -> dict
    def list_projects(filters) -> list
```

#### 3.2.2 子引擎 1：交付月报（`delivery_report`）

**接口**：
```python
class DeliveryReportEngine(BaseEngine):
    def compute(month: str) -> dict[str, DataFrame]
    def persist(month, data, overwrite) -> dict
    def load(month) -> dict
    def has_data(month) -> bool

class DeliveryReportService(BaseService):
    def generate(month, mode="auto") -> dict
    def export(month, out_path) -> Path
```

#### 3.2.3 子引擎 2：确收管理（`revenue`）

**接口**：
```python
class RevenueEngineAdapter(BaseEngine):
    def compute(period: str) -> dict
    def import_source(period, excel_path) -> dict
    def persist(period, data, overwrite) -> dict
    def load(period) -> dict
    def has_data(period) -> bool
```

#### 3.2.4 子引擎 3：成本管理（`cost`）

**接口**：
```python
class CostEngine(BaseEngine):
    def submit_timesheet(**data) -> dict     # 工时填报
    def approve_timesheet(ts_id) -> dict       # 工时审批
    def get_device_usage(project_id) -> list   # 设备领用
    def sync_travel_cost(project_id, month) -> dict  # 差旅对账
    def get_cost_summary(project_id) -> dict
```

#### 3.2.5 子引擎 4：风险处置（`risk`）

**接口**：
```python
class RiskEngine(BaseEngine):
    def report_risk(**data) -> dict           # 异常报备
    def review_risk(risk_id, action) -> dict   # 审核
    def get_risk_summary(project_id) -> dict   # 风险台账
    def escalate(risk_id) -> dict              # 升级/协同
```

**AI Agent 独立调用（全部子引擎）**：
```bash
bdms project create --title "xxx" --contract-id 1   # 项目立项
bdms project close 1                                 # 结项
bdms delivery-report generate 202608  # project_management 子引擎                   # 交付月报
bdms cost timesheet submit --project 1 --hours 8      # 工时填报
bdms risk report --project 1 --type exception          # 风险报备
```

**复用资产**：
- ✅ L3 DMS Framework（DDD 骨架 + 状态机 + 事件总线）
- ✅ L2 Office-011（Excel 导出）
- ✅ L2 Persistence-006（SQLite + Repository）
- ✅ 现有 BDMS `delivery_report/` + `revenue/` 计算逻辑

---

### 3.3 模块 3：售后管理（`after_sales`）

**L3 域**：After-sales Management

**业务域**：售后维保与工单管理

**核心功能**：
- 售后交接（项目转售后）
- 工单受理与分派
- SLA 监控（响应/解决时长）
- 产品问题汇总

**接口**：
```python
class AfterSalesService(BaseService):
    def transfer_to_after_sales(project_id) -> dict
    def create_ticket(**data) -> dict
    def assign_ticket(ticket_id, assignee) -> dict
    def resolve_ticket(ticket_id, resolution) -> dict
    def list_tickets(filters) -> list
    def get_sla_summary(month) -> dict
```

**数据模型**（新增表，前缀 `as_`）：

| 表 | 用途 |
|---|---|
| `as_ticket` | 工单主表 |
| `as_ticket_log` | 工单操作日志 |
| `as_sla_snapshot` | SLA 统计快照 |

**复用资产**：
- ✅ L3 DMS Framework（状态机用于工单流转）
- ✅ L2 Persistence-006（SQLite）

**AI Agent 独立调用**：
```bash
bdms after-sales transfer 1           # 项目 1 转售后
bdms after-sales ticket create --type exception
bdms after-sales ticket list --status open
```

---

### 3.4 模块 4：数据看板（`dashboard`）

**L3 域**：横切

**业务域**：多模块数据聚合与可视化

**核心功能**：
- 总览指标卡（交付数量/确收金额/合同数量/异常数）
- 趋势图（按月）
- 下钻穿透（点击指标 → 对应模块明细）
- 对比分析（环比/同比）

**接口**：
```python
class DashboardService:
    def summary(month=None, range_months=12) -> dict
    def trend(metric, range_months=12) -> list
    def drill_down(metric, month) -> list
    def compare(metric, baseline_month) -> dict
```

**设计要点**：
- 只读各模块 DB，不写入
- 聚合计算在 dashboard 模块内完成，不侵入业务模块
- 支持缓存（`db_snapshot` 表）

---

### 3.5 模块 5：基础数据（`master_data`）

**L3 域**：横切

**业务域**：跨模块共享的字典/参考数据

**核心功能**：
- 图例定义（交付/确收各场景图例）
- 部门/产品线/区域等业务字典
- CRUD + 批量导入

**接口**：
```python
class MasterDataService:
    def list(data_type, filters=None) -> list
    def get(data_type, code) -> dict
    def create(data_type, code, label, extra=None) -> dict
    def update(data_type, code, **fields) -> dict
    def delete(data_type, code) -> dict
    def import_batch(data_type, rows) -> dict
```

**复用资产**：
- ✅ 现有 `md_reference` 表（无需新建）

---

### 3.6 模块 6：系统设置（`settings`）

**L3 域**：横切

**业务域**：全局配置管理

**核心功能**：
- 默认时间跨度
- 默认月份
- Excel 输出目录
- 自动化开关

**接口**：
```python
class SettingsService:
    def get(key, default=None) -> any
    def set(key, value, description=None) -> None
    def get_all() -> dict
    def reset(key) -> None
```

**复用资产**：
- ✅ 现有 `sys_settings` 表

---

### 3.7 模块 7：数据集成（`integration`）— 横切

**L3 域**：横切

**定位**：所有外部系统的数据入口，统一认证/拉取/标准化/落地

**核心职责**：
- 统一认证管理（每个连接器独立凭据，走 L2 凭据管理）
- 数据拉取（API 调用 / 浏览器自动化 / 本地文件路径）
- 数据标准化（转换为 BDMS 统一中间格式）
- 幂等落地（source_id + connector_name + batch_id，重复拉取不重复）
- 错误重试（指数退避）+ 告警

**连接器清单**：

| 连接器 | 数据源 | 落地目标 | 同步方式 |
|---|---|---|---|
| `ones` | ONES 项目管理 | project_management / delivery_report | API / 浏览器自动化 |
| `oa` | OA 系统（合同/立项/验收/采购） | contract_management / project_management | API |
| `timesheet` | 工时门户 | project_management → cost | API / 本地文件 |
| `wecom_doc` | 企业微信文档 | after_sales / risk | API / 本地文件 |
| `finance` | 财务报表（确收对比表） | project_management → revenue | 本地文件 / API |

**接口**：
```python
class IntegrationService:
    def list_connectors() -> list[dict]
    def get_connector_status(name: str) -> dict
    def sync(connector_name: str, **params) -> SyncResult
    def get_staging_data(connector_name: str, batch_id: str) -> list[dict]

class BaseConnector(ABC):
    def authenticate() -> bool
    def fetch(**params) -> list[dict]
    def normalize(raw: list) -> list[dict]
    def load_to_staging(records: list) -> int
```

**本地存储路径支持**：
```python
class LocalPathConnector(BaseConnector):
    """本地文件路径作为数据源的连接器基类"""
    def __init__(self, path: Path):
        self.path = path
    def fetch(self, **params) -> list[dict]:
        # 从本地路径读取文件（Excel/CSV/JSON）
        ...
```

**复用资产**：
- ✅ L2 凭据管理（SecretRef）
- ✅ L2 持久化适配（staging 表）
- ✅ L3 DMS Framework（事件总线通知各模块）

**AI Agent 独立调用**：
```bash
bdms integration list                           # 列出连接器
bdms integration status ones                    # 查看 ones 连接器状态
bdms integration sync ones --mode incremental   # 增量同步
bdms integration sync finance --path ./报表.xlsx  # 本地文件同步
bdms integration staging list ones batch_001    # 查看 staging 数据
```

---

### 3.8 模块 8：产品/服务知识库（`knowledge_base`）— 横切

**L3 域**：横切

**定位**：为多个业务模块提供产品/服务知识支撑

**与 master_data 的区别**：
- master_data → 字典（code → label），精确匹配
- knowledge_base → 知识文档（规格/手册/SLA/FAQ），语义检索 + 精确匹配

**核心数据**：

| 知识类型 | 用途 | 服务模块 |
|---|---|---|
| 产品规格书 | 项目实施参考 | project_management |
| 服务 SLA 标准 | 售后工单 SLA 计算 | after_sales |
| 部署/实施手册 | 实施任务指导 | project_management |
| 验收标准/方式 | 验收条款参照 | project_management → delivery_report |
| 合同条款模板 | 合同起草参考 | contract_management |
| 产品定价参考 | 合同金额审核 | contract_management |
| 故障排查 FAQ | 售后工单辅助 | after_sales |

**接口**：
```python
class KnowledgeBaseService:
    def search(query: str, product_id: str = None, top_k: int = 5) -> list[KnowledgeItem]
    def get_product_spec(product_id: str) -> dict
    def get_sla_standard(service_type: str) -> dict
    def get_contract_clause_template(clause_type: str) -> str
    def get_troubleshooting_faq(product_id: str, symptom: str) -> list[dict]
    def add_knowledge(**data) -> dict
    def update_knowledge(kb_id, **data) -> dict
```

**存储方案**：

| 组件 | 说明 |
|---|---|
| 结构化字段 | `kb_id`, `product_id`, `knowledge_type`, `title`, `tags`, `updated_at` |
| 内容存储 | Markdown 文本（支持富文本/图片引用） |
| 语义索引 | 接入 L2 Memory-009（本地 GGUF embedding，已验证可用） |
| 全文检索 | SQLite FTS5（已就绪） |

**数据模型**（新增表，前缀 `kb_`）：

| 表 | 用途 |
|---|---|
| `kb_item` | 知识条目主表 |
| `kb_item_embedding` | 语义向量索引 |

**复用资产**：
- ✅ L2 Memory-009（本地 embedding，768 维 GGUF，已验证可用）
- ✅ L2 Persistence-006（SQLite + FTS5）

**AI Agent 独立调用**：
```bash
bdms knowledge search "如何配置策略"            # 语义搜索
bdms knowledge search "策略配置" --product-id P001  # 按产品过滤
bdms knowledge get-spec --product-id P001          # 获取产品规格
bdms knowledge get-sla --service-type 安服          # 获取 SLA 标准
bdms knowledge get-faq --product-id P001 --symptom "启动失败"  # FAQ
bdms knowledge add --product-id P001 --type spec --title "配置手册" --file ./手册.md
```

---

## 4. Base 层设计

Base 层是 v2.1 的核心抽象，目的是**消除模块间的重复代码**，同时保持每个模块的独立性。

### 4.1 BaseService

所有业务模块的 Service 层基类，提供：
- 幂等生成骨架（auto/read/regenerate 三模式）
- Job 生命周期管理（创建/更新/完成/失败）
- 状态查询（has_data / list_months）

```python
class BaseService(ABC):
    module_name: str
    engine: BaseEngine

    def generate(month, mode="auto") -> dict
    def has_data(month) -> bool
    def list_months() -> list
    def _load_existing(month) -> dict  # 子类可覆盖
    def _count_rows(data) -> dict[str, int]
```

### 4.2 BaseEngine

所有计算引擎的接口契约，确保模块间计算层接口一致。

```python
class BaseEngine(ABC):
    def compute(month) -> dict       # 纯计算
    def persist(month, data, overwrite) -> dict  # 落盘
    def load(month) -> dict          # 读取
    def has_data(month) -> bool      # 检查
```

### 4.3 BaseExporter

Excel 导出器的共享骨架，统一样式/列映射机制。

```python
class BaseExporter(ABC):
    sheet_order: list[str]

    def export(month, out_path=None) -> Path
    def _write_all_sheets(wb, month, conn) -> None  # 子类实现

    # 共享工具
    def _write_header_row(ws, row_idx, headers) -> None
    def _auto_column_width(ws, columns, sample_rows) -> None
    def _apply_data_style(cell, data_type) -> None
```

### 4.4 BaseImporter

数据导入器的共享骨架（统一数据校验/幂等导入/日志）。

```python
class BaseImporter(ABC):
    def import_all(source_path, month) -> dict
    def validate_source(source_path) -> bool
    def _parse_source(source_path) -> dict  # 子类实现
    def _persist_data(month, data) -> dict  # 子类实现
```

---

## 5. 数据架构

### 5.1 统一 DB（`data/bdms.db`）

**元数据表**（core 层）：
- `job` — 任务记录
- `report_month` — 月度数据登记
- `import_log` — 导入日志
- `md_reference` — 参考数据/字典
- `sys_settings` — 系统设置
- `db_snapshot` — 看板快照

**业务表**（按模块前缀分区）：

| 前缀 | 模块 | 核心表 |
|---|---|---|
| `dr_` | delivery_report | `dr_sheet_row` / `dr_sheet_meta` |
| `rr_` | revenue | `rr_sheet_row` / `rr_sheet_meta` |
| `cr_` | contract_management | `cr_contract` / `cr_contract_clause` / `cr_risk_item` / `cr_approval_log` / `cr_audit_trail` / `cr_template` |
| `as_` | after_sales | `as_ticket` / `as_ticket_log` / `as_sla_snapshot` |
| `st_` | integration | `staging_ones` / `staging_oa` / `staging_timesheet` / `staging_wecom` / `staging_finance` |
| `kb_` | knowledge_base | `kb_item` / `kb_item_embedding` |

### 5.2 表设计原则

1. **模块前缀隔离** — 每个模块的表有唯一前缀，避免命名冲突
2. **宽表 vs 强类型表** — 报表类用宽表（`*_sheet_row` + JSON data），交易类用强类型表（合同/审批）
3. **幂等键** — 每个业务表有明确的唯一约束，支持 `INSERT OR REPLACE`
4. **索引策略** — 默认按月（YYYYMM）+ 模块前缀建索引；同时支持按精确日期（YYYYMMDD）查询扩展，关键业务表（合同/项目/工时/工单）必须包含日期字段以支持日粒度查询

---

## 6. AI Agent 调用设计

### 6.1 统一 CLI 入口

```bash
bdms <module> <command> [options]
```

示例：
```bash
# 交付月报
bdms delivery-report generate 202608              # 子引擎，独立可调用
bdms delivery-report generate 202608 --mode regenerate  # 子引擎，独立可调用
bdms delivery-report export 202608 --out ./report.xlsx    # 子引擎，独立可调用

# 确认收入
bdms revenue import 202606 --source ./确收对比表.xlsx
bdms revenue generate 202606
bdms revenue export 202606

# 合同审核
bdms contract create --title "xxx" --amount 150000
bdms contract scan 1
bdms contract approve 1 --approver "Rex" --role "销售经理"
bdms contract list --status review1

# 基础数据
bdms master-data list legend
bdms master-data create legend --code "A" --label "正常交付"

# 看板
bdms dashboard summary 202608

# 数据集成
bdms integration list
bdms integration status ones
bdms integration sync ones --mode incremental
bdms integration sync finance --path ./报表.xlsx

# 设置
bdms settings get
bdms settings set default_months_back 6
```

### 6.2 Python API 入口

每个模块的 Service 类都是独立的 Python API，AI Agent 可以直接 import 调用：

```python
from bdms.modules.integration.service import IntegrationService  # 横切
from bdms.modules.project_management.revenue import RevenueService  # 子引擎
svc = RevenueService()
result = svc.generate("202606", mode="auto")
```

### 6.3 Agent 独立性保证

| 保证 | 方式 |
|---|---|
| 不依赖 Web | CLI + Python API 双通道，均不依赖 Web Server |
| 不依赖其他模块 | 每个模块的核心功能自包含，数据自足 |
| 纯函数可测 | engine 层纯函数，可独立单元测试 |
| 失败隔离 | 一个模块出错不影响其他模块 |

---

## 7. 可复用资产清单（全系统资产，L4/L3/L2/L1 四级）

### 7.1 L4 层可复用（现有 BDMS / 交付中心资产）

| 资产 | 来源 | 复用方式 | 价值评估 |
|---|---|---|---|
| 交付月报计算逻辑（5 Sheet） | BDMS v1 `delivery_report/` (子引擎) | 保留，接入 Base | ⭐⭐⭐⭐⭐ |
| 交付月报 Excel 导出器 | BDMS v1 `delivery_report/exporter.py` | 保留，接入 BaseExporter | ⭐⭐⭐⭐⭐ |
| 确收引擎 + 10 Sheet 计算 | BDMS v1 `revenue/engine.py` | 保留，接入 Base | ⭐⭐⭐⭐⭐ |
| 确收 Excel 导出器 | BDMS v1 `revenue/exporter.py` | 保留，接入 BaseExporter | ⭐⭐⭐⭐ |
| 统一 DB 层（宽表设计） | BDMS v1 `core/db.py` | 保留并加固 | ⭐⭐⭐⭐⭐ |
| 统计分析 Sheet 构建器 | BDMS v1 `stats_builders_c.py` | 保留，融入 project_management → delivery_report 子引擎 | ⭐⭐⭐⭐ |
| 看板模块 + 快照机制 | BDMS v1 `dashboard/` | 保留并扩展 | ⭐⭐⭐⭐ |
| 基础数据模块 | BDMS v1 `master_data/` | 保留并扩展 | ⭐⭐⭐ |
| 系统设置模块 | BDMS v1 `settings/` | 保留 | ⭐⭐⭐ |
| Web UI 框架（FastAPI + Jinja2） | BDMS v1 `web/` | 保留并扩展 | ⭐⭐⭐⭐ |
| 统一 CLI 入口 | BDMS v1 `cli/main.py` | 保留并扩展 | ⭐⭐⭐ |
| ONES 数据导入器 | BDMS v1 `weekly_importer.py` | 保留，接入 BaseImporter | ⭐⭐⭐⭐ |
| 合同审批工作流脚本（SCA-001） | L3 skills `contract-approval/scripts/` | 重构为 contract_management 模块 | ⭐⭐⭐⭐ |
| ONES 数据导入器 | BDMS v1 `weekly_importer.py` | 重构为 integration 模块 | ⭐⭐⭐⭐ |
| 产品/服务知识库 | 新增 | knowledge_base 模块（语义检索 + FTS5） | ⭐⭐⭐⭐ |
| delivery-center v2 全套代码 | `delivery-center/` 项目 | 按需迁入 BDMS | ⭐⭐⭐ |

### 7.2 L3 层可复用

| 资产 | 来源 | 复用方式 | 价值评估 |
|---|---|---|---|
| 合同审批状态机 | L3 `contract-approval/core/` | 直接继承（纯逻辑，零副作用） | ⭐⭐⭐⭐⭐ |
| 风险扫描引擎 | L3 `contract-approval/core/risk_scanner.py` | 直接调用 | ⭐⭐⭐⭐⭐ |
| 审核标准库 | L3 `contract-approval/checklists/` | 数据文件引用 | ⭐⭐⭐⭐ |
| DDD 骨架 | L3 `delivery-management-framework/` | 接口契约参考 | ⭐⭐⭐ |
| DMS 统一 CLI 模式 | L3 `dms-framework/` | 模式借鉴 | ⭐⭐⭐ |

### 7.2 L2 层可复用

| 资产 | 来源 | 复用方式 | 价值评估 |
|---|---|---|---|
| OCR 数字化引擎 | L2 `ocr-digitalization/` | 兼容层调用（contract_ocr_v5） | ⭐⭐⭐⭐⭐ |
| Office 文档生成 | L2 `office-doc-generation/` | Excel/docx 样式模板 | ⭐⭐⭐⭐ |
| SQLite 持久化 | L2 `persistence-adapter/` | 已在 core/db.py 中实现 | ⭐⭐⭐⭐ |
| 记忆语义检索 | L2 `memory-search/` | 合同知识库检索（可选） | ⭐⭐⭐ |

### 7.3 现有代码可复用

| 资产 | 来源 | 复用方式 | 价值评估 |
|---|---|---|---|
| 交付月报计算逻辑 | `delivery-center/v2/` | 迁入 engine.py | ⭐⭐⭐⭐⭐ |
| 确收计算逻辑 | `revenue-recognition/` | 迁入 engine.py | ⭐⭐⭐⭐⭐ |
| 统一 DB 层 | 现有 `core/db.py` | 保留，加固 | ⭐⭐⭐⭐⭐ |
| 现有 5 模块代码 | 现有 `modules/` | 重构接入 Base 层 | ⭐⭐⭐⭐ |
| Web UI 框架 | 现有 `web/` | 扩展新模块页面 | ⭐⭐⭐⭐ |

### 7.4 文档可复用

| 资产 | 来源 | 价值 |
|---|---|---|
| ARCHITECTURE.md v1.0 | 现有 | 基础架构参考 |
| MODULE-CONTRACT.md v1.0 | 现有 | 接口契约参考 |
| VERIFICATION-202606.md | 现有 | 验收基线 |
| 交付验收 7 步法 | AGENTS.md | 质量保障方法论 |

### 7.5 文档命名规范（v2.1 起统一）

本项目所有设计文档统一按以下规则命名，避免重复、便于追溯：

| 文档类型 | 命名格式 | 示例 |
|---|---|---|
| 设计大纲 | `DESIGN-OUTLINE-v<版本号>.md` | `DESIGN-OUTLINE-v2.1.md` |
| 详细设计 | `DESIGN-DETAIL-v<版本号>.md` | `DESIGN-DETAIL-v2.1.md` |
| 架构文档 | `ARCHITECTURE-v<版本号>.md` | `ARCHITECTURE-v2.1.md` |
| 模块契约 | `MODULE-CONTRACT-v<版本号>.md` | `MODULE-CONTRACT-v2.1.md` |
| 验收报告 | `VERIFICATION-<标识>-v<版本号>.md` | `VERIFICATION-202606-v2.1.md` |
| 历史版本 | `archive/<原文件名>` | `archive/DESIGN-OUTLINE-v2.0.md` |

**规则**：
- 每份文档只有一份当前版本，历史版本移入 `archive/`
- 版本号语义化：主版本.次版本（v2.1 = 第 2 大版，第 1 次迭代）
- 设计大纲通过后，基于同版本号出详细设计（v2.1 大纲 → v2.1 详细设计）

---

## 8. 开发落地路径（分步）

> Rex 要求：一步一步落地，先设计，再开发

### Phase 0：设计阶段（当前）
- [x] 设计大纲（本文件，7 模块架构）
- [ ] 模块 1 详细设计（delivery_report）
- [ ] 模块 2 详细设计（revenue）
- [ ] 模块 3 详细设计（contract_management）
- [ ] 模块 4-6 详细设计（master_data/dashboard/settings）
- [ ] Base 层详细设计
- [ ] 数据模型详细设计
- [ ] Rex 审核确认 → 进入开发

### Phase 1：架构加固
- [ ] Base 层完整实现（BaseService/BaseEngine/BaseExporter/BaseImporter）
- [ ] Core 层加固（事件总线、模块注册器）
- [ ] 现有模块 1-2 重构接入 Base

### Phase 2：新模块开发
- [ ] integration 模块（数据集成层，7 个连接器）
- [ ] contract_management 模块（合同审核管理）
  - [ ] 数据模型（6 张表）
  - [ ] Engine 层（继承 L3 纯逻辑）
  - [ ] Service 层（审批流转）
  - [ ] Importer（OCR 集成）
  - [ ] Exporter（Excel 报告）
  - [ ] CLI 入口
  - [ ] 单元测试

### Phase 3：Web UI 扩展
- [ ] 合同审核页面（列表/详情/审批操作）
- [ ] 看板页面（聚合展示）
- [ ] 导航整合

### Phase 4：集成与验收
- [ ] 全链路集成测试
- [ ] 黄金基准对比（202606）
- [ ] 幂等测试
- [ ] 交付验收 7 步法
- [ ] 文档更新

---

## 9. 风险与决策点

| 风险/决策点 | 影响 | 建议方案 |
|---|---|---|
| L3 contract-approval 纯逻辑核心是否完整可用 | 高 | 先做一次 PoC 验证，确认状态机/风险扫描可直接继承 |
| 宽表 vs 强类型表的边界 | 中 | 报表类用宽表，交易类用强类型，合同审核用强类型 |
| 模块间数据共享方式 | 中 | DB 共享 + 事件总线，避免直接调用 |
| 合同 OCR 数字化精度 | 中 | 复用 L2 OCR-001，人工审核兜底 |
| 现有 5 模块重构风险 | 中 | 逐步迁移，先接 BaseService，再验证功能，最后删旧代码 |

---

## 10. 待 Rex 确认的问题

> ✅ 已由 Rex 于 2026-09-18 拍板确认

| # | 问题 | 决策 |
|---|---|---|
| 1 | 模块 3 contract_management 的范围 | **完整审批流**（起草→审批→签署→归档）。先继承 L3 contract-approval 写入详细设计文档，Rex 通过人工审核确认或调整 |
| 2 | 合同数据隔离策略 | **BDMS 统一 DB**（`cr_` 前缀表）。涉密数据（金额/客户信息/联系人）需要**加密存储 + 脱敏机制** |
| 3 | Web UI 是否同步 v2.1 | **暂缓**。详细设计文档通过本轮审批后，再统一执行 |
| 4 | L3 contract-approval 是否先做 PoC | **暂缓**。详细设计文档通过本轮审批后，再统一执行 |

---

## 变更历史

- 2026-09-18: v2.1 Outline 初版，6 模块架构 + Base 层 + 合同审核管理 + 复用资产清单
- 2026-09-18: v2.1 Outline 第1轮审核调整 — ① 继承关系修正（整体仅 delivery-management-framework，模块3 单独继承 contract-approval）② 对齐 Bangcle 项目管理完整流程（16 阶段 / 62 节点）③ 模块从 6 重组为 6（按 L3 域）（+项目管理/项目执行/售后/成本/风险）④ 索引策略补充按日期可扩展 ⑤ 文档命名规范统一 ⑥ 资产清单扩容到 L4/L3/L2 四级
