# BDMS v2.1 设计大纲（概要设计）

> Bangcle Delivery Management System — 设计文档第一部分
> 版本：v2.1 Outline r2（2026-09-22）
> 层级：L4 专有业务层
> 继承：L3 `delivery-management-framework`（整体框架）
> 依据：`PRD-v2.1.md`（已审核通过）
> 状态：待 Rex 审核

---

## 0. 版本定位

| 维度 | v1.0（现有） | v2.1（本次迭代） |
|---|---|---|
| 模块数 | 5（月报/确收/主数据/看板/设置） | **7**（合同审核/项目管理/交付月报/确收分析/项目利润/驾驶舱/数据集成） |
| 架构 | 平层模块（core + 5 modules） | **分层**（core + base + modules + L3 框架契约层） |
| 流程覆盖 | 交付月报 + 确收分析（财务侧） | **16 个流程阶段全链路**（立项→实施→交付→确收→验收→售后→结项→成本），风险横向覆盖 |
| 数据获取 | 浏览器自动化 | **浏览器自动化 + 本机导入 + 知识库落盘** |
| 报表基准 | 202605 | **202606** |
| 可复用资产 | 零散复用 | **系统化复用** L3/L2 组件，显式列出可复用清单 |

---

## 1. 设计目标与原则

### 1.1 核心目标

1. **功能完整** — 对齐 Bangcle 项目管理完整流程（16 阶段 / 62 流程节点），覆盖：立项审批 → 合同下单 → 项目立项 → 项目实施（产品/安服/定制/外包）→ 项目交付 → 收入确认 → 项目验收 → 转售后 → 项目结项 → 成本管理，**风险横向覆盖全流程**
2. **高内聚低耦合** — 每个模块只负责一个业务域，模块间通过明确接口交互
3. **报表自动生成** — 按手工报表解析后的原始数据、公式计算数据、统计汇总数据实现自动生成
4. **驾驶舱可配置** — 用户可配置 KPI 卡片和图表，默认以交付月报+确收分析统计汇总为初始看板
5. **数据自动化** — 浏览器自动化 + 本机导入 + 知识库落盘，频率可配置（默认人工触发）

### 1.1.1 Bangcle 交付管理全流程对齐

来源：`~/Downloads/项目管理流程.docx`（16 阶段 / 62 节点）

| 阶段 | 节点 | 对应 BDMS 模块 | 风险覆盖 |
|---|---|---|---|
| #1 | 立项章程审批（概算/合同/POC/提前实施） | contract_management | ✅ |
| #2-1/2-2 | 合同下单 / POC / 提前实施申请 | contract_management + project_management | ✅ |
| #2-3 | 销售合同下单进度监控 | project_management | ✅ |
| #3-1/3-2 | 项目立项 + 履约项维护 | project_management + master_data | ✅ |
| #4 | 项目实施前准备（设备/迁移） | project_management | ✅ |
| #5-1~5-3 | 产品实施任务 + 执行 + 管理 | project_management | ✅ |
| #6-1~6-3 | 安服实施任务 + 执行 + 管理 | project_management | ✅ |
| #7-1/7-2 | 产品定制开发需求 + 执行 | project_management | ✅ |
| #8-1/8-2 | 外包/外采申请 + 管理 | project_management | ✅ |
| #9-1/9-2 | 项目交付 + 交付监控 | project_management → delivery_report | ✅ |
| #11 | 收入确认材料交接 | project_management → revenue | ✅ |
| #10-1/10-2 | 项目验收 + 验收监控 | project_management | ✅ |
| #12-1~12-3 | 转售后 + 售后工单 + 售后管理 | project_management | ✅ |
| #13-1/13-2 | 项目结项 + 结项监控 | project_management | ✅ |
| #14 | 项目成本管理（工时/设备/差旅） | project_management → profit_management | ✅ |
| #15 | 成本确认材料交接 | project_management → profit_management | ✅ |
| #16 | 项目风险处置 | project_management（风险横向覆盖全流程） | ✅ |

> **设计策略**：
> - 16 阶段不是 16 个模块，而是按业务域聚合为 **7 个模块**
> - 风险横向覆盖 = 每个阶段都有风险报备入口 + 独立风险模块贯穿项目生命周期
> - 确收→验收顺序：理论上同一时间点，实现时先交付/确收，再项目验收

### 1.2 设计原则

| 原则 | 含义 | 落地方式 |
|---|---|---|
| **单一职责** | 一个模块只负责一个业务域 | 7 个模块，每模块有明确边界 |
| **接口驱动** | 模块间通过接口交互，不直接依赖实现 | BaseService / BaseEngine 契约 |
| **纯计算优先** | 引擎层纯函数，无副作用 | engine.py 不写 DB、不发请求 |
| **幂等可重入** | 同一输入多次执行结果一致 | auto/read/regenerate 三模式 |
| **AI 友好** | 每个模块都能被 AI Agent 独立调用 | 统一 CLI 入口 + Python API |
| **知识库落盘** | 合同模板/风险规则/产品文档统一入知识库 | kb_item 表 + 语义索引 |

---

## 2. 整体架构

### 2.1 分层架构

```
┌─────────────────────────────────────────────────────────────┐
│                      AI Agent 层                              │
│   bdms-cli / FastAPI / WebSocket （各模块独立入口）            │
├─────────────────────────────────────────────────────────────┤
│                      L4 模块层（7 个模块）                     │
│                                                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐        │
│  │合同审核管理   │  │项目管理       │  │交付月报       │        │
│  │contract_mgmt │  │project_mgmt  │  │delivery_rpt  │        │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘        │
│         │                 │                 │                 │
│  ┌──────┴───────┐  ┌──────┴───────┐  ┌──────┴───────┐        │
│  │确收分析       │  │项目利润管理   │  │驾驶舱管理     │        │
│  │revenue       │  │profit_mgmt   │  │dashboard     │        │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘        │
│         │                 │                 │                 │
│  ┌──────┴─────────────────┴─────────────────┴───────┐        │
│  │数据集成（横切：ONES/OA/工时/企微/本机导入）       │        │
│  └───────────────────────────────────────────────────┘        │
├─────────────────────────────────────────────────────────────┤
│                   Base 层 （模块共性抽象）                      │
│      BaseService / BaseEngine / BaseExporter / BaseImporter    │
├─────────────────────────────────────────────────────────────┤
│                   Core 层 （跨模块基础设施）                    │
│      DB / Paths / Schemas / EventBus / Registry               │
├─────────────────────────────────────────────────────────────┤
│                   L2 基础设施层 （系统级复用）                   │
│   OCR-001 / Office-011 / Persistence-006 / Memory-009          │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 模块清单（7 个模块）

| # | 模块名 | 类型 | 核心能力 | 覆盖流程阶段 | AI Agent 独立调用 |
|---|---|---|---|---|---|
| 1 | `contract_management` | ★核心 | 合同起草/审批/风险扫描/OCR/归档 | #1 立项审批 / #2 合同下单 | ✅ `bdms contract scan/approve` |
| 2 | `project_management` | ★核心 | 项目立项/实施/交付/确收/验收/结项/风险处置 | #3~#16 | ✅ `bdms project create/close` |
| 3 | `delivery_report` | ★核心 | 交付月报 15 Sheet 自动生成 | #9 交付 | ✅ `bdms delivery-report generate` |
| 4 | `revenue` | ★核心 | 确收分析 10 Sheet 自动生成 | #11 确收 | ✅ `bdms revenue generate` |
| 5 | `profit_management` | ★核心 | 收入-成本=利润，项目级利润率 | #14 成本 | ✅ `bdms profit summary` |
| 6 | `dashboard` | ★核心 | 驾驶舱配置/下钻/编辑/默认月报看板 | 全阶段 | ✅ `bdms dashboard summary` |
| 7 | `integration` | 横切 | ONES/OA/工时/企微/本机导入，频率可配置 | 全阶段 | ✅ `bdms integration sync` |

### 2.3 模块依赖关系

```
contract_management ──┐
                  ├──> master_data（字典/图例）
project_management ─┤
                  │
delivery_report ←──┤（依赖 integration 数据导入）
                  │
revenue ──────────┤（依赖 delivery_report 当月数据）
                  │
profit_management ─┤（依赖 revenue 收入数据）
                  │
dashboard ────────┴── 只读各模块数据（不反向依赖）

integration ──────┴── 为各模块提供标准化数据（单向写入，频率可配置）
```

**依赖规则**：
- `integration` → 单向写入各模块（频率可配置，默认人工触发）
- `delivery_report` → `revenue`（确收依赖当月交付月报数据）
- `revenue` → `profit_management`（利润依赖确收收入数据）
- `dashboard` → 只读各模块数据
- 模块间**不直接调用**，通过 DB 共享数据 + 事件总线解耦

---

## 3. 模块设计概要

### 3.1 模块 1：合同审核管理（`contract_management`）

**业务域**：销售合同全生命周期审核管理

**核心功能**：
1. **合同起草** — 基于知识库中的 Bangcle 官方模板（11 份）生成 docx
2. **风险扫描** — 基于知识库中的民法典 13 项风险点自动扫描
3. **分级审批** — 按金额/风险分级：部门经理→法务→高管
4. **合同签署** — 电子签章 + 纸质签署记录
5. **合同归档** — 对接 OA 归档流程
6. **OCR 导入** — 扫描件/图片→结构化数据

**接口**：
```python
class ContractManagementEngine(BaseEngine):
    def parse_contract(text: str) -> dict
    def scan_risks(contract: dict) -> list[RiskItem]
    def get_approval_level(amount: float) -> int
    def validate_state_transition(from_state, to_state, role) -> bool

class ContractManagementService(BaseService):
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

**知识库落盘**：
- 合同模板（11 份 docx → kb_item）
- 民法典风险规则库（13 项 → kb_item）

**复用资产**：
- ✅ L2 OCR-001（扫描件数字化）
- ✅ L2 Office-011（docx 生成 + Excel 报告）
- ✅ L2 Persistence-006（SQLite + Repository）
- ✅ L3 contract-approval 纯逻辑核心

---

### 3.2 模块 2：项目管理（`project_management`）

**业务域**：项目全生命周期管理（立项→实施→交付→确收→验收→售后→结项），风险横向覆盖

**核心功能**：
1. **项目立项** — ONES 同步 + 合同关联 + 履约项维护
2. **实施管理** — 产品/安服/定制/外包四类实施
3. **交付管理** — 交付邮件→确收交接→验收（先确收再验收）
4. **验收管理** — 验收文件→客户确认→验收归档
5. **售后管理** — 维保→工单→关闭
6. **项目结项** — 全部履约完成后归档
7. **风险处置** — 异常报备→处置方案→关闭（每个阶段都有风险报备入口）

**接口**：
```python
class ProjectEngine(BaseEngine):
    def init_project(**data) -> dict          # 项目立项
    def update_scope(project_id, **data) -> dict
    def close_project(project_id) -> dict      # 结项
    def get_status(project_id) -> dict
    def list_projects(filters) -> list

class ProjectService(BaseService):
    def create_project(**data) -> dict
    def update_project(project_id, **data) -> dict
    def close_project(project_id) -> dict
    def transfer_to_after_sales(project_id) -> dict
    def report_risk(**data) -> dict           # 风险报备入口
    def resolve_risk(risk_id, action) -> dict  # 风险处置
    def list_risks(filters) -> list
```

**数据模型**（新增表，前缀 `pm_`）：

| 表 | 用途 |
|---|---|
| `pm_project` | 项目主表（基本信息 + 状态 + 合同关联） |
| `pm_project_member` | 项目成员（项目经理/工程师） |
| `pm_milestone` | 里程碑（阶段节点记录） |
| `pm_delivery_record` | 交付记录（邮件/确收/验收） |
| `pm_risk_record` | 风险记录（报备→处置→关闭） |
| `pm_after_sales` | 售后记录（维保/工单） |

---

### 3.3 模块 3：交付月报（`delivery_report`）

**业务目标**：按照手工报表解析后的原始数据、公式计算数据、统计汇总数据，实现自动生成交付月报 Excel（15 Sheet）

**黄金基准**：`~/Bangcle Workspace/01. Management/2026/2026团队报告/202606/2026交付月报-20260630.xlsx`

**依赖**：数据集成模块（ONES/OA 数据导入）

**报表结构**（15 Sheet）：

| # | Sheet 名称 | 类型 | 数据源 |
|---|---|---|---|
| 1 | 签约 | 核心数据 | ONES 签约合同导出 |
| 2 | POC&提前实施 | 核心数据 | ONES POC 导出 |
| 3 | 异常项目 | 核心数据 | ONES 异常导出 |
| 4 | 确收交接 | 核心数据 | ONES 确收交接导出 |
| 5 | 验收交接 | 核心数据 | ONES 验收交接导出 |
| 6 | 交付效率统计 | 透视表 | 签约数据聚合 |
| 7 | 签约统计 | 透视表 | 签约数据聚合 |
| 8 | 产品-授权&维保统计 | 数据表 | 签约数据产品分类 |
| 9 | POC&提前实施统计 | 透视表 | POC 数据聚合 |
| 10 | 提前实施分事业部统计 | 透视表 | POC 数据按事业部聚合 |
| 11 | 异常统计 | 透视表 | 异常数据多维交叉 |
| 12 | 异常台账 | 汇总表 | 异常数据按年份×类型 |
| 13 | 交付异常分事业部统计 | 透视表 | 异常数据按事业部 |
| 14 | 交接统计 | 透视表 | 确收+验收按区域聚合 |
| 15 | 图例 | 静态表 | 项目经理-部门映射字典 |

**计算契约**：
- 所有计算在 engine.compute() 阶段完成并落盘到 DB
- exporter 只做纯 IO（读 DB + 写 Excel 格式），禁止任何业务计算
- 公式计算结果以值写入（非 Excel 公式）

**接口**：
```python
class DeliveryReportEngine(BaseEngine):
    def compute(month: str) -> dict[str, DataFrame]  # 纯计算
    def persist(month, data, overwrite) -> dict       # 落盘
    def load(month) -> dict                           # 读取（等价于 compute）
    def has_data(month) -> bool

class DeliveryReportService(BaseService):
    def generate(month, mode="auto") -> dict
    def export(month, out_path) -> Path
```

**数据模型**（前缀 `dr_`）：
- `dr_sheet_row` — 宽表（签约/POC/异常/确收/验收原始数据）
- `dr_sheet_meta` — Sheet 元数据

**验收标准**：
- 15 Sheet 全部存在
- 每个 Sheet 行数误差 ≤ 1
- 所有 Sheet 列名 100% 一致（含列序）
- 公式计算结果与手工报表值一致

---

### 3.4 模块 4：确收分析（`revenue`）

**业务目标**：按照手工报表解析后的原始数据、公式计算数据、统计汇总数据，实现自动生成确收分析 Excel（10 Sheet）

**黄金基准**：`~/Bangcle Workspace/01. Management/2026/2026团队报告/202606/2026年计划确收&实际确收对比表202601-06-0724 - 差异分析.xlsx`

**依赖**：
- 数据集成模块（手工 Excel 导入）
- **交付月报模块**（确收分析依赖当月交付月报数据 `dr_sheet_row`）

**报表结构**（10 Sheet）：

| # | Sheet 名称 | 类型 | 数据源 |
|---|---|---|---|
| 1 | 预算执行表 | 核心数据 | 手工 Excel 导入 |
| 2 | 计划确收底稿 | 核心数据 | 手工 Excel 导入 |
| 3 | 汇总 | 汇总表 | 预算执行表聚合 |
| 4 | 汇总分析 | 透视表 | 按团队/产线聚合 |
| 5 | 预算趋势分析 | 趋势表 | 多月份预算对比 |
| 6 | 确收差异分析 | 透视表 | 项目经理维度差异 |
| 7 | 重拆履约 | 透视表 | 合同×提前/滞后 |
| 8 | 图例 | 静态表 | 项目经理-部门映射 |
| 9 | 月度汇总记录 | 汇总表 | 按月份聚合 |
| 10 | 履约汇总记录 | 汇总表 | 按履约维度聚合 |

**接口**：
```python
class RevenueEngine(BaseEngine):
    def compute(period: str) -> dict
    def import_source(period, excel_path) -> dict
    def persist(period, data, overwrite) -> dict
    def load(period) -> dict
    def has_data(period) -> bool

class RevenueService(BaseService):
    def generate(period, mode="auto") -> dict
    def export(period, out_path) -> Path
```

**数据模型**（前缀 `rr_`）：
- `rr_sheet_row` — 宽表（预算执行表/计划确收底稿原始数据）
- `rr_sheet_meta` — Sheet 元数据

**验收标准**：
- 10 Sheet 全部存在
- 核心数据 Sheet 行数=手工
- 汇总 Sheet 行数=31（含说明行+履约维度+空行）
- 辅助 Sheet 行数误差 ≤ 1，列名 100% 一致
- 公式计算结果与手工报表值一致

---

### 3.5 模块 5：项目利润管理（`profit_management`）

**业务目标**：实时计算项目级利润率（收入 - 成本 = 利润），支持按项目/部门/时间维度分析

**依赖**：确收模块（收入数据）

**核心功能**：
1. **收入确认** — 对接确收模块，收入数据自动同步
2. **成本核算** — 工时×费率 + 设备折旧 + 差旅（系统导入 Excel/CSV）
3. **利润计算** — 收入 - 成本 = 利润
4. **利润报表** — 按项目/部门/时间维度
5. **成本异常告警** — 成本超预算 10% 告警

**接口**：
```python
class ProfitEngine(BaseEngine):
    def compute_profit(project_id, period) -> dict
    def get_cost_summary(project_id) -> dict
    def check_budget_alert(project_id) -> list

class ProfitService(BaseService):
    def submit_timesheet(**data) -> dict
    def approve_timesheet(ts_id) -> dict
    def import_travel_cost(project_id, file_path) -> dict
    def get_profit_report(project_id, period) -> dict
    def list_projects_profit(period) -> list
```

**数据模型**（前缀 `pf_`）：

| 表 | 用途 |
|---|---|
| `pf_timesheet` | 工时记录 |
| `pf_cost_item` | 成本项（工时/设备/差旅） |
| `pf_profit_snapshot` | 利润快照（按项目/期间） |

---

### 3.6 模块 6：驾驶舱管理（`dashboard`）

**业务目标**：用户可配置驾驶舱，支持 KPI 卡片、趋势图表、下钻明细、字段编辑。系统默认以交付月报和确收分析月报统计汇总数据为初始看板。

**参考**：业界最佳实践（ONES 自定义看板 / Grafana / Tableau / Power BI / Metabase / DataV）

**核心功能**：

#### 6.1 默认驾驶舱

| 区域 | 内容 | 数据源 |
|---|---|---|
| 顶部 KPI 区 | 12 个核心 KPI 卡片 | 各模块实时数据 |
| 交付月报区 | 签约数/交付数/及时率/异常数 | delivery_report 统计汇总 |
| 确收分析区 | 确收金额/确收率/预算完成率 | revenue 统计汇总 |
| 项目利润区 | 收入/成本/利润/毛利率 | profit_management 汇总 |
| 风险区 | 风险项目数/异常处置状态 | project_management |

#### 6.2 KPI 卡片（12 个核心指标）

| # | KPI | 数据源 | 计算方式 |
|---|---|---|---|
| 1 | 合同数量 | contract_management | COUNT(cr_contracts) |
| 2 | 合同金额 | contract_management | SUM(amount) |
| 3 | 在建项目数 | project_management | COUNT(status='executing') |
| 4 | 交付项目数 | delivery_report | COUNT(delivery_month=current) |
| 5 | 交付及时率 | delivery_report | is_timely / total |
| 6 | 验收项目数 | project_management | COUNT(acceptance_month=current) |
| 7 | 确收金额 | revenue | SUM(actual_amount) |
| 8 | 确收率 | revenue | SUM(actual) / SUM(plan) |
| 9 | 售后工单数 | project_management | COUNT(as_tickets) |
| 10 | 项目成本 | profit_management | SUM(cost) |
| 11 | 风险项目数 | project_management | COUNT(risk_status='open') |
| 12 | 毛利率 | profit_management | (revenue - cost) / revenue |

#### 6.3 下钻功能

| 功能 | 描述 |
|---|---|
| KPI 下钻 | 点击 KPI 卡片→弹出明细列表 |
| 维度下钻 | 部门→项目→单条记录，三级下钻 |
| 筛选/排序/分页 | 多维筛选 + 任意列排序 + 分页 |

#### 6.4 明细编辑

| 功能 | 描述 |
|---|---|
| 字段编辑 | 备注、状态等字段可编辑 |
| 编辑权限 | 按角色控制字段范围 |
| 编辑历史 | 修改人/时间/前后值可追溯 |
| 批量编辑 | 勾选多条批量修改 |
| 撤销 | 会话内可撤销 |

**接口**：
```python
class DashboardService:
    def get_default_view() -> dict           # 默认驾驶舱（月报统计汇总）
    def summary(month=None) -> dict          # KPI 汇总
    def trend(metric, range_months) -> list  # 趋势
    def drill_down(metric, month) -> list    # 下钻明细
    def list_views() -> list                 # 视图列表
    def save_view(name, config) -> dict      # 保存视图
    def edit_field(record_id, field, value) -> dict  # 字段编辑
    def get_edit_history(record_id) -> list   # 编辑历史
```

**数据模型**（前缀 `db_`）：

| 表 | 用途 |
|---|---|
| `db_view_config` | 驾驶舱视图配置 |
| `db_edit_history` | 编辑历史记录 |

---

### 3.7 模块 7：数据集成（`integration`）

**业务目标**：通过浏览器自动化从 OA、ONES、工时门户等系统获取数据 + 本机导入，减少人工录入。频率可配置，默认为人工触发（如生成新的交付月报、确收分析报告时）

**连接器清单**：

| # | 连接器 | 数据源 | 落地目标 | 频率 |
|---|---|---|---|---|
| I-01 | ones | ONES 项目管理 | project_management / delivery_report | 可配置（默认人工触发） |
| I-02 | oa | OA 合同流程 | contract_management / project_management | 可配置（默认人工触发） |
| I-03 | timesheet | 工时门户 | profit_management | 可配置（默认人工触发） |
| I-04 | wecom_doc | 企微文档 | revenue / project_management | 可配置（默认人工触发） |
| I-05 | local_import | 本机导入（Excel/CSV/手工录入） | 各模块 | 人工触发 |

**触发时机**：
- 生成新的交付月报时
- 生成新的确收分析报告时
- 手动点击"刷新数据"按钮
- 定时任务（如配置为每日/每周）

**接口**：
```python
class IntegrationService:
    def list_connectors() -> list[dict]
    def get_connector_status(name: str) -> dict
    def sync(connector_name: str, **params) -> SyncResult
    def get_staging_data(connector_name: str, batch_id: str) -> list[dict]
    def configure_frequency(connector_name: str, schedule: str) -> dict

class BaseConnector(ABC):
    def authenticate() -> bool
    def fetch(**params) -> list[dict]
    def normalize(raw: list) -> list[dict]
    def load_to_staging(records: list) -> int
```

**数据模型**（前缀 `st_`）：
- `staging_ones` / `staging_oa` / `staging_timesheet` / `staging_wecom` — 暂存表

---

## 4. Base 层设计

### 4.1 BaseService

所有业务模块的 Service 层基类：
- 幂等生成骨架（auto/read/regenerate 三模式）
- Job 生命周期管理
- 状态查询

```python
class BaseService(ABC):
    module_name: str
    engine: BaseEngine

    def generate(month, mode="auto") -> dict
    def has_data(month) -> bool
    def list_months() -> list
```

### 4.2 BaseEngine

所有计算引擎的接口契约：

```python
class BaseEngine(ABC):
    def compute(month) -> dict       # 纯计算
    def persist(month, data, overwrite) -> dict  # 落盘
    def load(month) -> dict          # 读取
    def has_data(month) -> bool
```

### 4.3 BaseExporter

Excel 导出器的共享骨架：

```python
class BaseExporter(ABC):
    sheet_order: list[str]

    def export(month, out_path=None) -> Path
    def _write_all_sheets(wb, month, conn) -> None
```

### 4.4 BaseImporter

数据导入器的共享骨架：

```python
class BaseImporter(ABC):
    def import_all(source_path, month) -> dict
    def validate_source(source_path) -> bool
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

**业务表**（按模块前缀分区）：

| 前缀 | 模块 | 核心表 |
|---|---|---|
| `cr_` | contract_management | `cr_contract` / `cr_contract_clause` / `cr_risk_item` / `cr_approval_log` / `cr_audit_trail` |
| `pm_` | project_management | `pm_project` / `pm_project_member` / `pm_milestone` / `pm_delivery_record` / `pm_risk_record` / `pm_after_sales` |
| `dr_` | delivery_report | `dr_sheet_row` / `dr_sheet_meta` |
| `rr_` | revenue | `rr_sheet_row` / `rr_sheet_meta` |
| `pf_` | profit_management | `pf_timesheet` / `pf_cost_item` / `pf_profit_snapshot` |
| `db_` | dashboard | `db_view_config` / `db_edit_history` |
| `st_` | integration | `staging_ones` / `staging_oa` / `staging_timesheet` / `staging_wecom` |
| `kb_` | knowledge_base | `kb_item` / `kb_item_embedding` |

### 5.2 表设计原则

1. **模块前缀隔离** — 每个模块的表有唯一前缀
2. **宽表 vs 强类型表** — 报表类用宽表（`*_sheet_row` + JSON data），交易类用强类型表
3. **幂等键** — 每个业务表有明确的唯一约束
4. **索引策略** — 默认按月（YYYYMM）+ 模块前缀建索引

---

## 6. AI Agent 调用设计

### 6.1 统一 CLI 入口

```bash
bdms <module> <command> [options]
```

示例：
```bash
# 合同审核
bdms contract create --title "xxx" --amount 150000
bdms contract scan 1
bdms contract approve 1 --approver "Rex" --role "销售经理"

# 项目管理
bdms project create --title "xxx" --contract-id 1
bdms project close 1
bdms project risk-report --project 1 --type exception

# 交付月报
bdms delivery-report generate 202606
bdms delivery-report export 202606 --out ./report.xlsx

# 确收分析
bdms revenue import 202606 --source ./确收对比表.xlsx
bdms revenue generate 202606
bdms revenue export 202606

# 项目利润
bdms profit summary 202606
bdms profit timesheet submit --project 1 --hours 8

# 驾驶舱
bdms dashboard summary 202606
bdms dashboard trend delivery_count --months 12

# 数据集成
bdms integration list
bdms integration sync ones --mode incremental
bdms integration sync local --path ./报表.xlsx
```

### 6.2 Python API 入口

```python
from bdms.modules.delivery_report.service import DeliveryReportService
svc = DeliveryReportService()
result = svc.generate("202606", mode="auto")
```

---

## 7. 知识库设计

### 7.1 知识库范围

| 知识类型 | 内容 | 来源路径 | 服务模块 |
|---|---|---|---|
| 合同模板 | Bangcle 官方模板 11 份 | 本地 docx | contract_management |
| 风险规则库 | 民法典 13 项风险点 | 知识库 | contract_management |
| 产品规格书 | 产品技术规格 | `/Bangcle Workspace/07. Bangcle Prod/` | project_management |
| 服务 SLA 标准 | 售后 SLA 计算规则 | `/Bangcle Workspace/07. Bangcle Prod/` | project_management |
| 实施手册 | 部署/实施指导 | `/Bangcle Workspace/07. Bangcle Prod/` | project_management |
| 验收标准 | 验收条款参照 | 知识库 | delivery_report |
| 故障排查 FAQ | 售后工单辅助 | 知识库 | project_management |

### 7.2 存储方案

| 组件 | 说明 |
|---|---|
| 结构化字段 | `kb_id`, `product_id`, `knowledge_type`, `title`, `tags`, `updated_at` |
| 内容存储 | Markdown 文本（支持富文本/图片引用） |
| 语义索引 | L2 Memory-009（本地 GGUF embedding，768 维） |
| 全文检索 | SQLite FTS5 |

### 7.3 产品文档导入路径

```
/Users/bangcle/Bangcle Workspace/07. Bangcle Prod/
├── 安全服务产品线/（20+ 产品文档）
├── 安全保护产品线/
├── 安全检测产品线/
├── 安全监测产品线/
├── 物联网服务产品线/
└── 内容安全产品线/
```

---

## 8. 可复用资产清单（全系统）

> 覆盖 BDMS 已建设资产、独立开发项目、L3 通用业务层、L2 基础设施层、L4 专有业务层全量资产。

### 8.1 BDMS 已建设资产（当前 v1.0 代码）

#### 8.1.1 Core 层（已上线）

| 资产 | 文件 | 复用方式 | 价值 |
|---|---|---|---|
| 统一 DB 层 | `core/db.py` | 保留并加固（连接池 + 迁移） | ⭐⭐⭐⭐⭐ |
| 路径管理 | `core/paths.py` | 直接复用 | ⭐⭐⭐⭐ |
| Schema 定义 | `core/schemas.py` | 扩展为 v2.1 | ⭐⭐⭐⭐ |
| Schema v2.1 | `core/schemas_v21.py` | 直接复用 | ⭐⭐⭐⭐ |
| Header 映射器 | `core/header_mapper.py` | 直接复用（列名标准化） | ⭐⭐⭐⭐ |
| v1→v2 迁移 | `core/migrate_v1_to_v2.py` | 直接复用 | ⭐⭐⭐ |
| Schema 校验 | `core/verify_schema.py` | 直接复用 | ⭐⭐⭐ |

#### 8.1.2 Base 层（已上线）

| 资产 | 文件 | 复用方式 | 价值 |
|---|---|---|---|
| BaseService | `modules/base.py` | 保留并扩展 | ⭐⭐⭐⭐⭐ |
| BaseRepository | `modules/base_repository.py` | 保留并扩展 | ⭐⭐⭐⭐⭐ |

#### 8.1.3 业务模块（已上线）

| 资产 | 文件 | 复用方式 | 价值 |
|---|---|---|---|
| 合同管理引擎 | `modules/contract_management/engine.py` | 保留，接入 Base | ⭐⭐⭐⭐⭐ |
| 合同管理服务 | `modules/contract_management/service.py` | 保留，接入 BaseService | ⭐⭐⭐⭐⭐ |
| 合同审批 CLI | `modules/contract_management/cli.py` | 保留并扩展 | ⭐⭐⭐⭐ |
| 合同 docx 生成 | `modules/contract_management/docx_generator.py` | 直接复用 | ⭐⭐⭐⭐⭐ |
| 合同 Excel 导出 | `modules/contract_management/exporter.py` | 接入 BaseExporter | ⭐⭐⭐⭐ |
| 合同 OCR 导入 | `modules/contract_management/ocr_importer.py` | 直接复用 | ⭐⭐⭐⭐ |
| 合同数据模型 | `modules/contract_management/models.py` | 直接复用 | ⭐⭐⭐⭐ |
| 合同加密模块 | `modules/contract_management/_crypto.py` | 直接复用 | ⭐⭐⭐⭐ |
| 交付月报引擎 | `modules/delivery_report/engine.py` | 保留，接入 Base | ⭐⭐⭐⭐⭐ |
| 交付月报服务 | `modules/delivery_report/service.py` | 保留，接入 BaseService | ⭐⭐⭐⭐⭐ |
| 交付月报导出 | `modules/delivery_report/exporter.py` | 保留，接入 BaseExporter | ⭐⭐⭐⭐⭐ |
| 统计构建器 | `modules/delivery_report/stats_builders_c.py` | 保留，融入 engine | ⭐⭐⭐⭐ |
| 确收引擎 | `modules/revenue/engine.py` | 保留，接入 Base | ⭐⭐⭐⭐⭐ |
| 确收服务 | `modules/revenue/service.py` | 保留，接入 BaseService | ⭐⭐⭐⭐⭐ |
| 确收导出 | `modules/revenue/exporter.py` | 保留，接入 BaseExporter | ⭐⭐⭐⭐ |
| 确收导入 | `modules/revenue/importer.py` | 直接复用 | ⭐⭐⭐⭐ |
| 确收统计构建器 | `modules/revenue/stats_builders.py` | 保留，融入 engine | ⭐⭐⭐⭐ |
| 汇总引擎 | `modules/revenue/summary_engine.py` | 保留并扩展 | ⭐⭐⭐⭐⭐ |
| 周数据导入 | `modules/revenue/weekly_importer.py` | 重构为 integration | ⭐⭐⭐⭐ |
| 项目管理引擎 | `modules/project_management/engine.py` | 保留，接入 Base | ⭐⭐⭐⭐⭐ |
| 项目管理服务 | `modules/project_management/service.py` | 保留，接入 BaseService | ⭐⭐⭐⭐⭐ |
| 项目数据模型 | `modules/project_management/models.py` | 直接复用 | ⭐⭐⭐⭐ |
| 项目变更引擎 | `modules/project_management/change/engine.py` | 保留 | ⭐⭐⭐⭐ |
| 成本引擎 | `modules/project_management/cost/engine.py` | 保留，融入 profit_management | ⭐⭐⭐⭐ |
| 成本服务 | `modules/project_management/cost/service.py` | 保留 | ⭐⭐⭐⭐ |
| 成本导出 | `modules/project_management/cost/exporter.py` | 接入 BaseExporter | ⭐⭐⭐ |
| 成本导入 | `modules/project_management/cost/importer.py` | 直接复用 | ⭐⭐⭐⭐ |
| 风险引擎 | `modules/project_management/risk/engine.py` | 保留 | ⭐⭐⭐⭐ |
| 风险服务 | `modules/project_management/risk/service.py` | 保留 | ⭐⭐⭐⭐ |
| 风险导出 | `modules/project_management/risk/exporter.py` | 接入 BaseExporter | ⭐⭐⭐ |
| 财务服务 | `modules/project_management/financial_service.py` | 保留 | ⭐⭐⭐⭐ |
| 看板引擎 | `modules/dashboard/engine.py` | 保留，扩展为驾驶舱 | ⭐⭐⭐⭐ |
| 看板服务 | `modules/dashboard/service.py` | 保留，扩展为驾驶舱 | ⭐⭐⭐⭐ |
| 主数据引擎 | `modules/master_data/engine.py` | 直接复用 | ⭐⭐⭐ |
| 主数据服务 | `modules/master_data/service.py` | 直接复用 | ⭐⭐⭐ |
| 系统设置引擎 | `modules/settings/engine.py` | 直接复用 | ⭐⭐⭐ |
| 系统设置服务 | `modules/settings/service.py` | 直接复用 | ⭐⭐⭐ |

#### 8.1.4 Web 层（已上线）

| 资产 | 文件 | 复用方式 | 价值 |
|---|---|---|---|
| FastAPI 主入口 | `web/main.py` | 保留并扩展 | ⭐⭐⭐⭐⭐ |
| API 路由 | `web/api.py` | 保留并扩展 | ⭐⭐⭐⭐ |
| 合同页面路由 | `web/contract.py` | 保留 | ⭐⭐⭐⭐ |
| 项目页面路由 | `web/project.py` | 保留 | ⭐⭐⭐⭐ |
| 看板 MVP | `web/dashboard_mvp.py` | 扩展为驾驶舱 | ⭐⭐⭐⭐ |
| 安全 API | `web/security_api.py` | 直接复用 | ⭐⭐⭐⭐ |
| 安全模块 | `security.py` | 直接复用 | ⭐⭐⭐⭐ |
| 基础模板 | `web/templates/base.html` | 直接复用 | ⭐⭐⭐⭐ |
| 合同模板 | `web/templates/contract.html` | 直接复用 | ⭐⭐⭐ |
| 项目模板 | `web/templates/project.html` | 直接复用 | ⭐⭐⭐ |
| 看板模板 | `web/templates/dashboard_mvp.html` | 扩展为驾驶舱 | ⭐⭐⭐⭐ |
| 报表模板 | `web/templates/report.html` | 直接复用 | ⭐⭐⭐ |
| 主数据模板 | `web/templates/master_data.html` | 直接复用 | ⭐⭐⭐ |
| 设置模板 | `web/templates/settings.html` | 直接复用 | ⭐⭐⭐ |
| 样式表 | `web/static/css/style.css` | 直接复用 | ⭐⭐⭐ |
| BDMS JS | `web/static/js/bdms.js` | 直接复用 | ⭐⭐⭐ |
| 合同 JS | `web/static/js/contract.js` | 直接复用 | ⭐⭐⭐ |
| 项目 JS | `web/static/js/project.js` | 直接复用 | ⭐⭐⭐ |
| 报表 JS | `web/static/js/report.js` | 直接复用 | ⭐⭐⭐ |
| 看板 JS | `web/static/js/dashboard_mvp.js` | 扩展为驾驶舱 | ⭐⭐⭐ |
| Chart.js | `web/static/js/chart.umd.min.js` | 直接复用 | ⭐⭐⭐⭐ |

#### 8.1.5 CLI 层（已上线）

| 资产 | 文件 | 复用方式 | 价值 |
|---|---|---|---|
| 统一 CLI 入口 | `cli/main.py` | 保留并扩展 | ⭐⭐⭐ |

#### 8.1.6 工具脚本（已上线）

| 资产 | 文件 | 复用方式 | 价值 |
|---|---|---|---|
| 确收汇总对比 | `tools/compare_revenue_summary.py` | 直接复用 | ⭐⭐⭐⭐ |
| 手工报表探测 | `tools/probe_manual.py` | 直接复用 | ⭐⭐⭐⭐ |
| 报表对比 | `tools/compare_report.py` | 直接复用 | ⭐⭐⭐⭐ |
| 月报对比 | `tools/compare_delivery_report.py` | 直接复用 | ⭐⭐⭐⭐ |

#### 8.1.7 测试资产（已上线）

| 资产 | 文件 | 复用方式 | 价值 |
|---|---|---|---|
| E2E 测试 | `tests/test_web_e2e.py` | 保留并扩展 | ⭐⭐⭐⭐⭐ |
| 合同管理测试 | `tests/test_contract_management.py` | 直接复用 | ⭐⭐⭐⭐ |
| 项目管理测试 | `tests/test_project_management.py` | 直接复用 | ⭐⭐⭐⭐ |
| 看板测试 | `tests/test_dashboard.py` | 扩展为驾驶舱 | ⭐⭐⭐ |
| 看板 MVP 测试 | `tests/test_dashboard_mvp.py` | 直接复用 | ⭐⭐⭐ |
| 主数据测试 | `tests/test_master_data.py` | 直接复用 | ⭐⭐⭐ |
| 月报导出测试 | `tests/test_delivery_report_export.py` | 直接复用 | ⭐⭐⭐⭐ |
| 设置测试 | `tests/test_settings.py` | 直接复用 | ⭐⭐⭐ |
| 确收测试 | `tests/test_revenue.py` | 直接复用 | ⭐⭐⭐⭐ |
| 周导入测试 | `tests/test_weekly_importer.py` | 重构为 integration | ⭐⭐⭐ |

#### 8.1.8 文档资产（已沉淀）

| 资产 | 文件 | 价值 |
|---|---|---|
| 详细设计-BASE | `docs/DESIGN-DETAIL-BASE-v2.1.md` | ⭐⭐⭐⭐ |
| 详细设计-数据模型 | `docs/DESIGN-DETAIL-DATA-MODEL-v2.1.md` | ⭐⭐⭐⭐ |
| 详细设计-合同管理 | `docs/DESIGN-DETAIL-CONTRACT-MANAGEMENT-v2.1.md` | ⭐⭐⭐⭐⭐ |
| 详细设计-项目管理 | `docs/DESIGN-DETAIL-PROJECT-MANAGEMENT-v2.1.md` | ⭐⭐⭐⭐ |
| 详细设计-知识库 | `docs/DESIGN-DETAIL-KNOWLEDGE-BASE-v2.1.md` | ⭐⭐⭐⭐ |
| 详细设计-驾驶舱 | `docs/DESIGN-DETAIL-DASHBOARD-v2.1.md` | ⭐⭐⭐⭐ |
| 详细设计-Web UI | `docs/DESIGN-DETAIL-WEB-UI-v2.1.md` | ⭐⭐⭐⭐ |
| 详细设计-数据集成 | `docs/DESIGN-DETAIL-INTEGRATION-v2.1.md` | ⭐⭐⭐⭐ |
| 详细设计-售后 | `docs/DESIGN-DETAIL-AFTER-SALES-v2.1.md` | ⭐⭐⭐ |
| 实施计划 | `docs/IMPLEMENTATION-PLAN-v2.1.md` | ⭐⭐⭐ |
| E2E 验收 | `docs/VERIFICATION-E2E-v2.1.md` | ⭐⭐⭐⭐ |
| MVP 最终验收 | `docs/VERIFICATION-MVP-FINAL-v2.1.md` | ⭐⭐⭐⭐ |
| Phase1.1 验收 | `docs/VERIFICATION-Phase1.1-Contract-Management-v2.1.md` | ⭐⭐⭐ |
| Phase1.2 验收 | `docs/VERIFICATION-Phase1.2-Project-Management-v2.1.md` | ⭐⭐⭐ |

---

### 8.2 L4 专有业务层（独立项目/技能）

| 资产 | 来源 | 复用方式 | 价值 |
|---|---|---|---|
| 合同审批工作流（SCA-001） | `L4-proprietary/skills/contract-approval/` | 重构为 contract_management 模块 | ⭐⭐⭐⭐ |
| Bangcle PPT 模板系统 | `L4-proprietary/skills/bangcle-ppt/` | PPT 报告生成（驾驶舱导出） | ⭐⭐⭐ |
| FIN-L4 理财系统 | `L4-proprietary/skills/fin-l4/` | 无直接复用（独立领域） | ⭐ |
| ONES 浏览器导出 | `L4-proprietary/skills/ones-browser-export/` | 重构为 integration 模块的 ONES 连接器 | ⭐⭐⭐⭐ |

---

### 8.3 L3 通用业务层

#### 8.3.1 DMS 框架

| 资产 | 来源 | 复用方式 | 价值 |
|---|---|---|---|
| DMS 统一 CLI 模式 | `L3-business/components/dms-framework/` | 模式借鉴 | ⭐⭐⭐ |
| DDD 骨架 | `L3-business/components/dms-framework/` | 接口契约参考 | ⭐⭐⭐ |
| 事件总线 | `L3-business/components/dms-framework/` | 模块间解耦 | ⭐⭐⭐ |
| 合同数据库 | `L3-business/contracts.db` | 参考数据 | ⭐⭐ |

#### 8.3.2 合同审批技能

| 资产 | 来源 | 复用方式 | 价值 |
|---|---|---|---|
| 合同审批状态机 | `L3-business/skills/contract-approval/core/` | 直接继承（纯逻辑，零副作用） | ⭐⭐⭐⭐⭐ |
| 风险扫描引擎 | `L3-business/skills/contract-approval/core/risk_scanner.py` | 直接调用 | ⭐⭐⭐⭐⭐ |
| 审核标准库 | `L3-business/skills/contract-approval/checklists/` | 数据文件引用 | ⭐⭐⭐⭐ |
| 审批脚本 | `L3-business/skills/contract-approval/scripts/` | 重构参考 | ⭐⭐⭐ |
| 审批测试 | `L3-business/skills/contract-approval/tests/` | 测试参考 | ⭐⭐⭐ |

---

### 8.4 L2 基础设施层

| 资产 | 来源 | 复用方式 | 价值 |
|---|---|---|---|
| OCR 数字化引擎 | `L2-infra/components/ocr-digitalization/` | 兼容层调用（contract_ocr） | ⭐⭐⭐⭐⭐ |
| Office 文档生成 | `L2-infra/components/office-generation/` | Excel/docx 样式模板 | ⭐⭐⭐⭐ |
| SQLite 持久化 | `L2-infra/components/persistence/` | 已在 core/db.py 中实现 | ⭐⭐⭐⭐ |
| 记忆语义检索 | `L2-infra/components/memory-embedding/` | 知识库语义检索 | ⭐⭐⭐ |
| 凭据管理 | `L2-infra/components/credentials/` | 集成连接器认证 | ⭐⭐⭐⭐ |
| Web 公共组件 | `L2-infra/components/web-common/` | 前端布局/样式 | ⭐⭐⭐ |
| 可观测性 | `L2-infra/components/observability/` | 日志/监控 | ⭐⭐⭐ |
| 上下文管理 | `L2-infra/components/context-management/` | 会话管理 | ⭐⭐ |
| 沙箱隔离 | `L2-infra/components/sandbox/` | 安全隔离 | ⭐⭐ |
| 工具策略 | `L2-infra/components/tool-policy/` | Agent 调用 | ⭐⭐ |
| 会话恢复 | `L2-infra/components/session-recovery/` | 任务恢复 | ⭐⭐ |
| 模型调度 | `L2-infra/components/model-scheduling/` | AI 模型路由 | ⭐ |
| 配置管理 | `L2-infra/components/config/` | 系统配置 | ⭐⭐ |
| 知识库组件 | `L2-infra/components/knowledge-base/` | 知识条目管理 | ⭐⭐⭐ |

---

### 8.5 资产复用统计

| 层级 | 资产数 | 高价值（⭐⭐⭐⭐⭐） | 已上线 | 待复用 |
|---|---|---|---|---|
| BDMS 已建设 | 87 | 12 | 87 | 0 |
| L4 独立项目 | 4 | 1 | 2 | 2 |
| L3 通用业务 | 8 | 3 | 5 | 3 |
| L2 基础设施 | 15 | 2 | 15 | 0 |
| **合计** | **114** | **18** | **109** | **5** |

---

## 9. 开发落地路径

### Phase 0：设计阶段（当前）
- [x] PRD-v2.1 审核通过
- [x] 设计大纲（本文件）
- [ ] 详细设计（各模块 DESIGN-DETAIL）
- [ ] Rex 审核确认 → 进入开发

### Phase 1：架构加固
- [ ] Base 层完整实现
- [ ] Core 层加固（事件总线、模块注册器）
- [ ] 现有模块重构接入 Base

### Phase 2：核心模块开发
- [ ] contract_management 模块
- [ ] project_management 模块
- [ ] profit_management 模块

### Phase 3：报表模块完善
- [ ] delivery_report 15 Sheet 完整实现
- [ ] revenue 10 Sheet 完整实现
- [ ] 驾驶舱管理（默认月报看板 + 下钻 + 编辑）

### Phase 4：数据集成
- [ ] integration 模块（5 个连接器）
- [ ] 知识库导入（合同模板 + 产品文档）
- [ ] 频率配置 + 人工触发

### Phase 5：Web UI + 安全
- [ ] 各模块页面
- [ ] 驾驶舱配置页面
- [ ] Token 鉴权 + 内外网访问控制

### Phase 6：集成与验收
- [ ] 全链路集成测试
- [ ] 黄金基准对比（202606）
- [ ] E2E 自测 + 人工测试

---

## 10. 风险与决策点

| 风险/决策点 | 影响 | 建议方案 |
|---|---|---|
| L3 contract-approval 纯逻辑核心可用性 | 高 | 先做 PoC 验证状态机/风险扫描 |
| 确收分析依赖交付月报数据 | 高 | 确保先生成当月交付月报，再生成确收分析 |
| 产品文档知识库导入量 | 中 | 按产品线分批导入，优先安服产品线 |
| 现有 5 模块重构风险 | 中 | 逐步迁移，先接 BaseService，再验证 |
| 驾驶舱下钻性能 | 中 | 大数据量用分页 + 缓存快照 |

---

## 11. 已确认的决策

| # | 问题 | 决策 | 备注 |
|---|---|---|---|
| 1 | 产品文档知识库导入范围 | **全部产品线一次性导入** | 6 产品线 |
| 2 | 驾驶舱字段编辑权限粒度 | **按角色 + 按项目双重控制** | 角色控字段范围 + 项目控数据范围 |
| 3 | 数据集成频率配置方式 | **页面配置（Web UI）** | 实时生效 |
| 4 | 用户角色 | **去掉财务角色**，相关操作权限移交 PMO | PMO = 交付中心与财务对接角色 |

---

## 变更历史

- 2026-09-22: v2.1 Outline r3 — Rex 审核反馈
  - 可复用资产从 23 项扩展到 **114 项**（全系统资产：BDMS 87 + L4 4 + L3 8 + L2 15）
  - 待确认问题全部决策落地（知识库全部导入、权限角色+项目双重控制、频率页面配置）
  - **去掉财务角色**，相关操作权限移交 PMO（交付中心与财务对接角色）
- 2026-09-22: v2.1 Outline r2 — 基于 PRD-v2.1 r2 重写
  - 模块数 8→7（合并子引擎到 project_management）
  - 流程顺序修正：立项→实施→交付→确收→验收→售后→结项→成本
  - 风险横向覆盖全流程
  - 新增项目利润管理模块
  - 统计看板→驾驶舱管理（默认月报汇总为初始看板）
  - 数据集成频率可配置（默认人工触发）
  - 知识库纳入全部产品/服务文档
  - 确收分析依赖当月交付月报数据
  - 黄金基准→202606
- 2026-09-22: v2.1 Outline r3 — 新增功能完整性矩阵和自测问题修复流程
- 2026-09-21: v2.1 Outline r2 — Phase 3 新增网络安全模块
- 2026-09-18: v2.1 Outline 初版
