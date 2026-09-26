# BDMS v2.0 设计大纲

> Bangcle Delivery Management System — 设计文档第一部分
> 版本：v2.0 Outline（2026-09-18）
> 层级：L4 专有业务层
> 继承：L3 `delivery-management-framework` + L3 `contract-approval`
> 状态：设计阶段，待 Rex 审核

---

## 0. 版本定位

| 维度 | v1.0（现有） | v2.0（本次重构） |
|---|---|---|
| 模块数 | 5（月报/确收/主数据/看板/设置） | **6**（+合同审核管理） |
| 架构 | 平层模块（core + 5 modules） | **分层**（core + base + modules + L3 契约层） |
| 代码 vs AI | 部分逻辑由 AI 生成 | **全代码实现**，AI 仅作为独立 Agent 调用入口 |
| 可复用资产 | 零散复用 delivery-center / revenue-recognition | **系统化复用** L3/L2 组件，显式列出可复用清单 |
| 高内聚低耦合 | 部分共享但无明确边界 | **明确接口契约**，模块可独立被 AI Agent 调用 |

---

## 1. 设计目标与原则

### 1.1 核心目标

1. **功能完整** — 覆盖交付端到端全链路：合同审核 → 交付执行 → 收入确认 → 数据看板
2. **高内聚低耦合** — 每个模块只做一件事，模块间通过明确接口交互
3. **全代码实现** — 核心逻辑 100% 代码实现，AI 仅作为 Agent 调用入口（CLI / API）
4. **独立可调用** — 每个模块暴露纯函数 + CLI 子命令，AI Agent 可独立执行单模块任务
5. **资产复用最大化** — 显式列出 L3/L2 可复用资产，减少重复建设

### 1.2 设计原则

| 原则 | 含义 | 落地方式 |
|---|---|---|
| **单一职责** | 一个模块只负责一个业务域 | 6 个模块，每模块有明确边界 |
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
│                      L4 业务模块层                             │
│                                                               │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐        │
│  │交付月度   │ │确认收入   │ │合同审核   │ │交付看板   │  ...    │
│  │管理       │ │管理       │ │管理       │ │           │        │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘        │
│       │             │             │             │              │
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

### 2.2 模块清单（6 个模块）

| # | 模块名 | 业务域 | 核心职责 | AI Agent 可独立调用 |
|---|---|---|---|---|
| 1 | `delivery_report` | 交付执行 | 交付月报生成、统计分析 | ✅ `bdms delivery-report generate` |
| 2 | `revenue` | 收入确认 | 确收差异分析、报表导出 | ✅ `bdms revenue generate` |
| 3 | `contract_review` | 合同审核 | 合同风险扫描、审批流转、文档生成 | ✅ `bdms contract scan/approve` |
| 4 | `master_data` | 基础数据 | 图例、部门、产品线等字典维护 | ✅ `bdms master-data list` |
| 5 | `dashboard` | 数据看板 | 多模块聚合展示、下钻穿透 | ✅ `bdms dashboard summary` |
| 6 | `settings` | 系统设置 | 全局配置、默认参数 | ✅ `bdms settings get/set` |

### 2.3 模块依赖关系

```
contract_review ──┐
                  ├──> master_data
delivery_report ──┤      │
                  │      ▼
revenue ──────────┤   settings
                  │
dashboard ────────┴── 依赖各模块数据（只读）
```

- 各业务模块 → 依赖 `master_data`（字典数据）+ `settings`（配置）
- `dashboard` → 只读各业务模块数据，不反向依赖
- 模块间**不直接调用**，通过 DB 共享数据 + 事件总线解耦

---

## 3. 模块设计概要

### 3.1 模块 1：交付月度管理（`delivery_report`）

**业务域**：交付执行过程的月度数据汇总与分析

**核心功能**：
- ONES 数据导入（签约/POC/异常项目）
- 5 大 Sheet 计算（签约/POC&提前实施/异常项目/确收交接/验收交接）
- 统计分析（交付效率/异常台账）
- Excel 导出（对齐手工报表格式）

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

**复用资产**：
- ✅ L2 Office-011（Excel 样式/格式）
- ✅ 现有 `delivery-center` v2 计算逻辑（迁入）
- ✅ L3 DMS Framework（DDD 骨架）

---

### 3.2 模块 2：确认收入管理（`revenue`）

**业务域**：财务确收对比与分析

**核心功能**：
- 财务报表导入（预算执行表/计划确收底稿）
- 10 大 Sheet 计算（汇总/预算执行/计划确收/汇总分析/月度记录/履约记录/差异分析/趋势分析/图例/重拆履约）
- Excel 导出（对齐财务报表格式）

**接口**：
```python
class RevenueEngineAdapter(BaseEngine):
    def compute(period: str) -> dict
    def import_source(period, excel_path) -> dict
    def persist(period, data, overwrite) -> dict
    def load(period) -> dict
    def has_data(period) -> bool

class RevenueService(BaseService):
    def generate(month, mode="auto") -> dict
    def import_source(month, path) -> dict
    def export(month, out_path) -> Path
    def summary(month) -> dict
```

**复用资产**：
- ✅ L2 Office-011（Excel 导出）
- ✅ 现有 `revenue-recognition` 逻辑（迁入）
- ✅ 统一宽表设计（`rr_sheet_row` / `rr_sheet_meta`）

---

### 3.3 模块 3：合同审核管理（`contract_review`）— 新增

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
class ContractReviewEngine(BaseEngine):
    """纯计算层（继承 L3 纯逻辑核心）"""
    def parse_contract(text: str) -> dict  # 条款解析
    def scan_risks(contract: dict) -> list[RiskItem]  # 风险扫描
    def get_approval_level(amount: float) -> int  # 分级计算
    def validate_state_transition(from_state, to_state, role) -> bool

class ContractReviewService(BaseService):
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
- ✅ L2 OCR-001（扫描件数字化，兼容层已就绪）
- ✅ L2 Office-011（docx 生成 + Excel 报告）
- ✅ L2 Persistence-006（SQLite + Repository 模式）

---

### 3.4 模块 4：交付基础数据（`master_data`）

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

### 3.5 模块 5：交付统计看板（`dashboard`）

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

### 3.6 模块 6：系统设置（`settings`）

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

## 4. Base 层设计

Base 层是 v2.0 的核心抽象，目的是**消除模块间的重复代码**，同时保持每个模块的独立性。

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
| `cr_` | contract_review | `cr_contract` / `cr_contract_clause` / `cr_risk_item` / `cr_approval_log` / `cr_audit_trail` / `cr_template` |

### 5.2 表设计原则

1. **模块前缀隔离** — 每个模块的表有唯一前缀，避免命名冲突
2. **宽表 vs 强类型表** — 报表类用宽表（`*_sheet_row` + JSON data），交易类用强类型表（合同/审批）
3. **幂等键** — 每个业务表有明确的唯一约束，支持 `INSERT OR REPLACE`
4. **索引策略** — 按月/按模块建索引，确保按月查询性能

---

## 6. AI Agent 调用设计

### 6.1 统一 CLI 入口

```bash
bdms <module> <command> [options]
```

示例：
```bash
# 交付月报
bdms delivery-report generate 202608
bdms delivery-report generate 202608 --mode regenerate
bdms delivery-report export 202608 --out ./report.xlsx

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

# 设置
bdms settings get
bdms settings set default_months_back 6
```

### 6.2 Python API 入口

每个模块的 Service 类都是独立的 Python API，AI Agent 可以直接 import 调用：

```python
from bdms.modules.revenue.service import RevenueService
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

## 7. 可复用资产清单

### 7.1 L3 层可复用

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

---

## 8. 开发落地路径（分步）

> Rex 要求：一步一步落地，先设计，再开发

### Phase 0：设计阶段（当前）
- [x] 设计大纲（本文件）
- [ ] 模块 1 详细设计（delivery_report）
- [ ] 模块 2 详细设计（revenue）
- [ ] 模块 3 详细设计（contract_review）
- [ ] 模块 4-6 详细设计（master_data/dashboard/settings）
- [ ] Base 层详细设计
- [ ] 数据模型详细设计
- [ ] Rex 审核确认 → 进入开发

### Phase 1：架构加固
- [ ] Base 层完整实现（BaseService/BaseEngine/BaseExporter/BaseImporter）
- [ ] Core 层加固（事件总线、模块注册器）
- [ ] 现有模块 1-2 重构接入 Base

### Phase 2：新模块开发
- [ ] contract_review 模块（合同审核管理）
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
| 1 | 模块 3 contract_review 的范围 | **完整审批流**（起草→审批→签署→归档）。先继承 L3 contract-approval 写入详细设计文档，Rex 通过人工审核确认或调整 |
| 2 | 合同数据隔离策略 | **BDMS 统一 DB**（`cr_` 前缀表）。涉密数据（金额/客户信息/联系人）需要**加密存储 + 脱敏机制** |
| 3 | Web UI 是否同步 v2.0 | **暂缓**。详细设计文档通过本轮审批后，再统一执行 |
| 4 | L3 contract-approval 是否先做 PoC | **暂缓**。详细设计文档通过本轮审批后，再统一执行 |

---

## 变更历史

- 2026-09-18: v2.0 Outline 初版，6 模块架构 + Base 层 + 合同审核管理 + 复用资产清单
