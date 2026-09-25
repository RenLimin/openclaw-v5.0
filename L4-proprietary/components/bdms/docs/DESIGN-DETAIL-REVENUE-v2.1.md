# DESIGN-DETAIL-REVENUE-v2.1.md

> Bangcle Delivery Management System v2.1 — 确收分析模块详细设计
> 版本：v2.1 Detail r3（2026-09-24）
> 层级：L4 专有业务层 — 模块2：确收分析
> 继承：`DESIGN-OUTLINE-v2.1.md` §3.2 确收分析架构
> 依据：`PRD-v2.1.md` §4.2 确收分析功能清单
> 状态：待 Rex 审核

---

## 目录

0. [版本记录](#0-版本记录)
1. [模块概述](#1-模块概述)
2. [OS 依赖与限制](#2-os-依赖与限制)
3. [技术方案](#3-技术方案)
4. [接口设计](#4-接口设计)
5. [数据模型](#5-数据模型)
6. [逐 Sheet 详细定义](#6-逐-sheet-详细定义)
7. [汇总 Sheet 31 行结构定义](#7-汇总-sheet-31-行结构定义逐行)
8. [计算公式字典](#8-计算公式字典)
9. [Excel 导出样式规范](#9-excel-导出样式规范)
10. [数据导入映射](#10-数据导入映射)
11. [错误处理](#11-错误处理)
12. [CLI 命令](#12-cli-命令)
13. [测试策略](#13-测试策略)
14. [性能约束](#14-性能约束)
15. [风险与限制](#15-风险与限制)
16. [复用资产清单与使用方式](#16-复用资产清单与使用方式)
[变更历史](#变更历史)

## 0. 版本记录

| 版本 | 日期 | 变更说明 |
|---|---|---|
| v2.1 Detail r1 | 2026-09-22 | 初始版本：10 Sheet 完整定义 + 接口契约 + 数据模型 + 逐行结构 |
| v2.1 Detail r2 | 2026-09-22 | 复用资产清单与使用方式（附录） |
| v2.1 Detail r3 | 2026-09-24 | Rex 审核反馈 5 条：weekly_signing 说明 + 手工调整列定义（§1.6）+ 合同/知识库关联（§1.3）+ 原始数据来源与导入校验（§1.5）+ ASC 606 收入确认准则（§1.7） |

---

## 1. 模块概述

### 1.1 模块定位

确收分析模块（module2: revenue）负责：
1. 导入手工确收对比表（Excel）→ 落盘到统一宽表
2. 从宽表聚合计算 → 生成 10 Sheet 结构化数据
3. 导出格式化 Excel → 对齐黄金基准报表

### 1.2 黄金基准

```
~/Bangcle Workspace/01. Management/2026/2026团队报告/202606/
  2026年计划确收&实际确收对比表202601-06-0724 - 差异分析.xlsx
```

### 1.3 模块依赖

```
┌───────────────────────────────────────────────────────────────┐
│ 确收分析模块（revenue）                                          │
│                                                                 │
│ 依赖（向下）：                                                    │
│   ├── bdms.core.db（统一 SQLite 层）                              │
│   ├── bdms.core.paths（路径解析）                                 │
│   ├── bdms.core.header_mapper（表头探测）                         │
│   ├── bdms.modules.base（BaseEngine/BaseService）                 │
│   ├── 交付月报模块 dr_sheet_row（共享宽表结构，当月交付数据）        │
│   ├── 数据集成模块 weekly_signing（周报产线数据，见 §4.4 说明）      │
│   ├── 合同管理模块 cr_contracts（合同信息 + 履约义务拆分依据）        │
│   └── 产品/服务知识库 kb_item（标准产品目录 + 收入确认方法参考）      │
│                                                                 │
│ 被依赖（向上）：                                                  │
│   ├── 项目利润模块（pf_profit_snapshot 收入数据源）                 │
│   ├── 驾驶舱模块（db_snapshot 引用汇总数据）                       │
│   └── CLI / Web API（generate/export 命令）                       │
└───────────────────────────────────────────────────────────────┘
```

**weekly_signing 说明**：周报签约项目数据表，源自 ONES 周报导出（`weekly_importer.py` 导入），存储「履约ID → 所属产线」映射，用于预算执行表 c93 列（所属产线）反查填充。

**业务数据链路**：
```
财务部门（原始数据：合同金额 + 履约义务拆分明细）
    ↓ 按合同拆分履约义务及金额（ASC 606 五步法，见 §1.5）
合同管理（cr_contracts：合同条款 + 履约义务清单）
    ↓ 关联
产品/服务知识库（kb_item：标准产品目录 + 收入确认方法）
    ↓ 参照
确收分析（revenue：预算执行 + 计划确收底稿 + 汇总）
```

### 1.4 文件结构

```
modules/revenue/
├── __init__.py          # 模块导出
├── engine.py            # RevenueEngineAdapter — 计算引擎适配层
├── service.py           # RevenueService — 服务层（幂等编排）
├── importer.py          # UnifiedRevenueImporter — xlsx → 宽表（含校验）
├── validator.py         # RevenueValidator — 数据有效性/合法性校验（新增）
├── exporter.py          # RevenueReportExporter — 宽表 → 格式化 Excel
├── stats_builders.py    # 7 个统计 Sheet 构建器
├── summary_engine.py    # SummaryEngine — 汇总计算引擎
└── weekly_importer.py   # 周报签约项目导入器
```

### 1.5 原始数据来源与业务链路（新增）

#### 1.5.1 原始数据来源

| 数据 | 来源 | 提供方式 | 频率 | 说明 |
|---|---|---|---|---|
| **预算执行表原始数据** | **财务部门** | Excel（企微文档/本机导入） | 每月 | 按合同拆分履约义务明细及金额 |
| **计划确收底稿原始数据** | **财务部门 + PMO** | Excel（企微文档/本机导入） | 每月 | 履约义务计划排期 |
| 合同信息（关联参照） | 合同管理 cr_contracts | DB 共享 | 实时 | 合同条款 + 履约义务清单 |
| 标准产品目录（参照） | 知识库 kb_item | DB 共享 | 实时 | 标准产品/服务名称 + 收入确认方法参考 |
| 所属产线（c93） | weekly_signing | DB 共享 | 每周 | ONES 周报导入 |
| 当月交付数据 | dr_sheet_row | DB 共享 | 每月 | 依赖当月交付月报 |

> **业务链路**：财务部门按合同拆分履约义务明细及金额（ASC 606 五步法，见 §1.6），PMO 填写计划排期，系统汇总计算。

#### 1.5.2 数据导入有效性/合法性校验（新增）

导入时执行以下校验（`RevenueValidator`）：

| # | 校验项 | 规则 | 级别 | 处置 |
|---|---|---|---|---|
| 1 | 合同编号非空 | c2/c4 不为空 | ERROR | 拒绝该行，记入错误日志 |
| 2 | 履约ID非空 | c10 不为空 | ERROR | 拒绝该行 |
| 3 | 金额数值合法性 | c12/c13/c14 为非负数值 | ERROR | 拒绝该行 |
| 4 | 月份格式 | c7 为 YYYYMM（202501~202712） | WARNING | 标记存疑，展示人工确认 |
| 5 | 合同存在性 | c2 在 cr_contracts 中存在 | WARNING | 标记存疑（新合同可自动创建） |
| 6 | 履约义务拆分一致性 | c12 = SUM(履约义务明细金额) | WARNING | 偏差 >1% 时标记存疑 |
| 7 | 分类枚举 | c1 ∈ {新签, 递延} | ERROR | 拒绝该行 |
| 8 | 收入确认方法枚举 | c11 ∈ {时点法, 时段法} | WARNING | 标记存疑 |
| 9 | 月度计划金额合理性 | c21-c32 单月 > 合同总额 | WARNING | 标记存疑 |
| 10 | 行数对比 | 与上月偏差 >20% | WARNING | 整体提示，人工确认 |
| 11 | 重复合同+履约ID | (c2, c10) 不重复 | ERROR | 拒绝重复行 |
| 12 | 知识库产品匹配 | c25/c27 在 kb_item 有对应 | WARNING | 标记存疑 |

**存疑数据处置流程**：
```
导入 → 校验 → ERROR 行拒绝 + WARNING 行标记存疑
    ↓
存疑数据展示（Web UI 列表）
    ↓
人工确认/调整（可编辑校正值）
    ↓
确认后写入 rr_sheet_row（覆盖原值，保留 original_value 留痕）
```

### 1.6 手工调整列定义（新增）

> 按报告模版逻辑，部分数据列需手工调整/修改。明确以下列的编辑方式：

#### 1.6.1 下拉列表选择列（枚举值固定）

| 列 | 列名 | 可选值 | 数据来源 |
|---|---|---|---|
| c1 | 分类 | 新签 / 递延 | 固定枚举 |
| c11 | 收入确认方法 | 时点法 / 时段法 | 固定枚举（ASC 606） |
| c47 | 重拆履约，提前和滞后同增 | 是 / 否 | 固定枚举 |
| c50 | 确收-财务是否交接（合同编号校验） | 已交接 / 未交接 / 无需交接 | 财务反馈 |
| c51 | 确收-财务是否交接 | 已交接 / 未交接 / 无需交接 | 财务反馈 |
| c53 | 是否正常摊销 | 是 / 否 | 固定枚举 |
| c54 | 是否统计确收？ | 是 / 否 | 固定枚举（筛选标记） |
| c63 | 偏差-状态/趋势 | 正常确收 / 差异确收 / 提前确收 / 滞后确收 / 待观察 | 固定枚举 |
| c64 | 偏差-原因类别 | 交付原因-延期 / 交付原因-质量 / 客户原因-延期 / 客户原因-取消 / 市场原因 / 其他 | 固定枚举 |
| c66 | 合同分类 | 框架合同 / 普通合同 / 补充协议 / 终止协议 | 固定枚举 |
| c67 | 是否完成下单流程 | 是 / 否 / 进行中 | 固定枚举 |
| c69 | 预算填报 | 已填报 / 未填报 / 无需填报 | 固定枚举 |
| c73 | 预算趋势 | 正常 / 提前 / 滞后 / 消失 | 固定枚举 |
| c74 | 预算趋势类别 | 按计划 / 提前完成 / 滞后未完成 / 已消失 | 固定枚举 |

#### 1.6.2 文本框填写列（自由文本）

| 列 | 列名 | 填写人 | 说明 |
|---|---|---|---|
| c46 | 消失备注 | PMO | 消失原因说明 |
| c52 | 确收-财务反馈 | 财务/PMO | 财务反馈意见 |
| c62 | 偏差-备注说明 | PMO | 差异原因详细说明 |
| c68 | 关联合同（终止/补充） | PMO | 关联的补充/终止协议编号（按合同关联规则自动反查：编号前 14 位一致 + BC=补充 / ZZ=终止，见 CONTRACT-MANAGEMENT §6；支持手工修正） |
| c70 | 备注 | PMO | 通用备注 |
| c71 | 预算填写说明 | PMO | 预算填报说明 |
| c80-c92 | 异常项目管理列 | PMO | 异常报备/处置/反馈（同交付月报 Sheet 3） |

#### 1.6.3 日期选择列

| 列 | 列名 | 格式 | 说明 |
|---|---|---|---|
| c18 | 计划开始时间 | YYYY-MM-DD | |
| c19 | 计划结束时间 | YYYY-MM-DD | |
| c75 | 预估交付完成日期（周报） | YYYY-MM-DD | 周报同步 |
| c76 | 预算-预估交付完成日期（周报） | YYYY-MM-DD | 周报同步 |

#### 1.6.4 编辑权限矩阵

| 角色 | 可编辑列 | 说明 |
|---|---|---|
| PMO | §1.6.1 全部 + §1.6.2 全部 + §1.6.3 | 默认编辑人 |
| 超级管理员 | 全部列 | 含金额列（c12-c17 等） |
| 其他角色 | 只读 | 展示层面 |

> **编辑留痕**：所有手工调整写入 `rr_edit_history`（新表，见 §4.6），记录原值/新值/操作人/时间。

### 1.7 收入确认准则参照（ASC 606 / 企业会计准则14号）（新增）

> 参考业界最佳实践，合同履约义务确认收入准则与时间点：

#### 1.7.1 ASC 606 五步法模型

| 步骤 | 内容 | 本系统落地 |
|---|---|---|
| ① 识别合同 | 与客户订立可执行的书面合同 | contract_management（cr_contracts） |
| ② 识别履约义务 | 合同中各项可明确区分的承诺 | 履约义务清单（c8-c10 履约ID + 明细） |
| ③ 确定交易价格 | 预期有权收取的对价 | 单项履约义务金额（c12） |
| ④ 分摊交易价格 | 按相对单独售价分摊至各履约义务 | 财务拆分（原始数据提供） |
| ⑤ 确认收入 | 履约义务满足时确认 | 时点法 / 时段法（c11 + 见 1.7.2） |

#### 1.7.2 收入确认时点/时段判定

| 确认方法 | 判定条件（ASC 606-25/27） | 确认时间点 | 本系统对应 |
|---|---|---|---|
| **时点法** | 客户取得商品控制权时（一次性交付） | 交付/验收时点 | 交付邮件发送 / 验收文件归档（dr_sheet_row） |
| **时段法** | 满足以下之一：① 客户同时取得并消耗利益 ② 客户控制在建商品 ③ 无替代用途 + 有权就累计完成部分收款 | 服务期间内投进度确认 | 服务期（c18-c19）按月分摊（m2026xx 列） |

**软件行业典型场景**：
| 场景 | 确认方法 | 说明 |
|---|---|---|
| 软件永久授权 | 时点法 | 授权交付时点 |
| SaaS 订阅（年授权） | 时段法 | 服务期内按月/按季 |
| 安全服务（安服项目） | 时段法 | 服务期间按进度 |
| 定制开发 | 时段法 | 按里程碑/进度 |
| 维保服务 | 时段法 | 服务期内按月 |
| 硬件销售 | 时点法 | 交付验收时点 |

#### 1.7.3 与知识库关联

标准产品目录（kb_item）维护「产品类型 → 默认收入确认方法」映射：
```
kb_item(knowledge_type='product_reference')
  .metadata: {
    "default_rev_method": "时段法",     # 时段法 / 时点法
    "rev_subject": "软件服务收入",       # 收入对应科目（c28）
    "tax_subject": "6%技术服务费",      # 税金科目（c29）
    "default_service_months": 12       # 默认服务期（c20）
  }
```
导入时自动填充建议值，PMO 可手工调整。

---

## 2. OS 依赖与限制

> 确收分析模块依赖 Excel 导入（手工 Excel/CSV）和企微文档数据，间接依赖 integration 模块。

| 功能 | OS 依赖 | macOS | Windows | Linux | 说明 |
|---|---|---|---|---|---|
| 手工 Excel/CSV 导入 | openpyxl/pandas | ✅ 支持 | ✅ 支持 | ✅ 支持 | 纯 Python |
| 企微文档导入 | API/浏览器/本机导入 | ✅ 多方案降级 | ✅ 多方案降级 | ✅ 多方案降级 | 间接依赖 integration I-04 |
| 汇总计算 | pandas/SQLite | ✅ 支持 | ✅ 支持 | ✅ 支持 | 纯 Python/SQL |
| Excel 导出 | openpyxl | ✅ 支持 | ✅ 支持 | ✅ 支持 | 纯 Python |
| 差异分析 | SQLite SQL | ✅ 支持 | ✅ 支持 | ✅ 支持 | 纯 SQL，OS 无关 |
| Web UI (FastAPI) | uvicorn + Jinja2 | ✅ 支持 | ✅ 支持 | ✅ 支持 | 纯 Python |
| CLI (Click) | click | ✅ 支持 | ✅ 支持 | ✅ 支持 | 纯 Python |

**间接依赖链**：
```
revenue
├── Excel/CSV 导入 → openpyxl/pandas（全平台）
├── 企微文档 → integration I-04 → API/浏览器/本机导入
│   ├── macOS: API + 浏览器（osascript）
│   ├── Linux: API + 浏览器（Playwright）
│   └── Windows: API + 浏览器（Playwright）
├── 汇总/差异 → pandas + SQLite（OS 无关）
└── Excel/Web/CLI → 纯 Python（全平台）
```

## 3. 技术方案

### 2.1 分层架构

```
┌──────────────────────────────────────────────────────────┐
│ CLI / Web API 层                                          │
│   bdms revenue generate 202606 --mode auto               │
│   bdms revenue export 202606 --out report.xlsx           │
│   bdms revenue import 202606 --file source.xlsx          │
├──────────────────────────────────────────────────────────┤
│ Service 层（RevenueService）                               │
│   import_source() → generate() → summary()               │
│   幂等三模式：auto / read / regenerate                    │
├──────────────────────────────────────────────────────────┤
│ Engine 层（RevenueEngineAdapter + SummaryEngine）          │
│   compute() → _compute_summary_from_wide()               │
│   SummaryEngine.compute_summary()                        │
├──────────────────────────────────────────────────────────┤
│ Builder 层（stats_builders.py）                            │
│   build_all_stats_sheets() → 7 个统计 Sheet              │
├──────────────────────────────────────────────────────────┤
│ Storage 层（bdms.core.db）                                 │
│   rr_sheet_row（宽表数据）+ rr_sheet_meta（元数据）        │
│   report_month（月度登记）+ md_reference（参考数据）       │
│   weekly_signing（周报产线索引）                           │
└──────────────────────────────────────────────────────────┘
```

### 2.2 数据流转

```
手工 Excel 导入 xlsx
       │
       ▼
┌──────────────────┐
│ UnifiedRevenue   │ ──→ rr_sheet_row (sheet='预算执行表')
│ Importer         │ ──→ rr_sheet_row (sheet='计划确收底稿')
│ .import_all()    │ ──→ rr_sheet_row (sheet='汇总')
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│ RevenueService   │ ──→ 幂等判断（auto/read/regenerate）
│ .generate()      │ ──→ 调用 SummaryEngine.compute_summary()
│                  │ ──→ 缓存到 report_month.extra
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│ RevenueReport    │ ──→ 读缓存/宽表
│ Exporter         │ ──→ 渲染 10 Sheet 格式化 Excel
│ .export()        │ ──→ 输出到 output/确认收入_{month}.xlsx
└──────────────────┘
```

### 2.3 幂等设计

| 模式 | 行为 | 适用场景 |
|---|---|---|
| `auto`（默认） | 有缓存读缓存，无缓存重新计算 | 日常使用 |
| `read` | 只读已有数据，无数据报错 | 快速查询 |
| `regenerate` | 强制重新计算，覆盖缓存 | 数据修正后 |

### 2.4 缓存策略

- **generate 阶段**：`SummaryEngine.compute_summary()` 结果写入 `report_month.extra`（JSON）
- **export 阶段**：只读 `report_month.extra` 缓存，不实时计算
- **缓存失效**：`regenerate` 模式或 `import_source` 后自动失效

---

## 4. 接口设计

### 3.1 RevenueEngineAdapter

```python
class RevenueEngineAdapter(BaseEngine):
    """确认收入引擎适配器（统一宽表版）。"""

    def __init__(self, db_path: Optional[Path] = None): ...
    def check_sources(self, month: str) -> dict: ...
    def sources_available(self, month: str) -> bool: ...
    def import_source(self, month: str, excel_path: Optional[Path] = None) -> dict: ...
    def compute(self, period: str) -> dict: ...
    def load(self, month: str) -> dict: ...
    def persist(self, month: str, data: dict, overwrite: bool = True) -> dict: ...
    def summary_counts(self, month: str) -> dict: ...
    def has_data(self, month: str) -> bool: ...
    def get_reference_data(self, data_type: str) -> list: ...
    def upsert_reference_data(self, data_type: str, code: str, label: str, extra: str = None): ...
```

### 3.2 RevenueService

```python
class RevenueService(BaseService):
    """确认收入服务层。"""
    module_name: str = "revenue"

    def __init__(self, db_path: Optional[Path] = None): ...
    def generate(self, month: str, mode: str = "auto") -> dict: ...
    def import_source(self, month: str, excel_path: Optional[Path] = None) -> dict: ...
    def summary_counts(self, month: str) -> dict: ...
    def summary(self, month: str) -> dict: ...
    def sources_available(self, month: str) -> bool: ...
    def list_months(self) -> list[str]: ...
    def _load_existing(self, month: str) -> dict: ...
```

### 3.3 RevenueReportExporter

```python
class RevenueReportExporter:
    """确认收入 Excel 导出器。"""

    def __init__(self, db_path: Optional[Path] = None): ...
    def export(self, month: str, out_path: Optional[Path] = None) -> Path: ...
```

### 3.4 UnifiedRevenueImporter

```python
class UnifiedRevenueImporter:
    """统一确收导入器：xlsx → rr_sheet_row 宽表。"""

    def __init__(self, db_path: Optional[Path] = None): ...
    def import_budget_exec(self, excel_path: Path, month: str) -> dict: ...
    def import_plan_draft(self, excel_path: Path, month: str) -> dict: ...
    def import_summary(self, excel_path: Path, month: str) -> dict: ...
    def import_all(self, excel_path: Path, month: str) -> dict: ...
```

### 3.5 SummaryEngine

```python
class SummaryEngine:
    """汇总报表计算（对齐手工「汇总」sheet）。"""

    def __init__(self, db_path: Optional[Path] = None): ...
    def compute_summary(self, month: str) -> dict: ...
    @staticmethod
    def read_manual_summary(excel_path) -> dict: ...
    @staticmethod
    def read_sheet_records(excel_path, sheet_name: str, header_row: int = None) -> dict: ...
```

### 3.6 stats_builders 公共函数

```python
def build_all_stats_sheets(conn, month: str) -> dict[str, pd.DataFrame]: ...
def build_summary_analysis(conn, month: str) -> pd.DataFrame: ...
def build_budget_trend(conn, month: str) -> pd.DataFrame: ...
def build_revenue_diff_analysis(conn, month: str) -> pd.DataFrame: ...
def build_re_split_performance(conn, month: str) -> pd.DataFrame: ...
def build_revenue_legend(conn, month: str) -> pd.DataFrame: ...
def build_monthly_summary_record(conn, month: str) -> pd.DataFrame: ...
def build_performance_summary_record(conn, month: str) -> pd.DataFrame: ...
def build_full_summary(conn, month: str) -> pd.DataFrame: ...
```

### 3.7 RevenueValidator（新增）

```python
class RevenueValidator:
    """确收数据导入有效性/合法性校验器（规则见 §1.5.2）。"""

    def validate_row(self, sheet: str, row: dict, row_index: int) -> list[dict]:
        """单行校验，返回问题列表。"""

    def validate_batch(self, sheet: str, rows: list[dict], month: str) -> dict:
        """批量校验（含行数对比/重复检查等跨行规则）。
        Returns: {"errors": [...], "warnings": [...], "summary": {...}}
        """

    def persist_validation_results(self, month: str, results: dict) -> int:
        """校验结果落盘 rr_import_validation。"""

    def apply_manual_correction(
        self, validation_id: int, corrected_value: str, operator: str
    ) -> dict:
        """人工校正存疑数据（写入 corrected_value + rr_edit_history 留痕）。"""

    def list_pending(self, month: str) -> list[dict]:
        """列出待处理存疑数据（Web UI 展示）。"""

    def auto_fill_suggestions(self, month: str) -> list[dict]:
        """从知识库自动填充建议（产品目录 → 收入确认方法/科目/服务期）。"""
```

---

## 5. 数据模型

### 4.1 rr_sheet_row（宽表数据）

```sql
CREATE TABLE IF NOT EXISTS rr_sheet_row (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period TEXT NOT NULL,              -- YYYYMM（如 202606）
    sheet TEXT NOT NULL,              -- Sheet 名称
    row_index INTEGER NOT NULL,       -- 行序号
    contract_no TEXT,                 -- 索引列：合同编号
    category TEXT,                    -- 索引列：分类（递延/新签）
    archive_month TEXT,               -- 索引列：归档月份
    perf_id TEXT,                     -- 索引列：履约ID
    data TEXT NOT NULL,               -- JSON：完整行数据
    UNIQUE(period, sheet, row_index)
);
CREATE INDEX IF NOT EXISTS idx_rr_sheet ON rr_sheet_row(period, sheet);
CREATE INDEX IF NOT EXISTS idx_rr_contract ON rr_sheet_row(contract_no);
CREATE INDEX IF NOT EXISTS idx_rr_archive ON rr_sheet_row(archive_month);
```

**说明**：
- `data` 列存储完整行 JSON，key 为原始列名（中文）或标准化字段名
- 月份列在 JSON 中以 `m2026xx`（计划）/ `a2026xx`（实际）为 key
- 索引列仅用于快速查询过滤，业务数据全部在 JSON 中

### 4.2 rr_sheet_meta（Sheet 元数据）

```sql
CREATE TABLE IF NOT EXISTS rr_sheet_meta (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period TEXT NOT NULL,
    sheet TEXT NOT NULL,
    columns TEXT NOT NULL,            -- JSON 数组：列名列表
    row_count INTEGER DEFAULT 0,
    UNIQUE(period, sheet)
);
```

### 4.3 report_month（月度登记）

```sql
CREATE TABLE IF NOT EXISTS report_month (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    module TEXT NOT NULL,             -- 'revenue'
    month TEXT NOT NULL,              -- YYYYMM
    source_path TEXT,                 -- 源文件路径
    generated_at TEXT,                -- 生成时间
    row_counts TEXT,                  -- JSON: {sheet: count}
    extra TEXT,                       -- JSON: SummaryEngine 计算结果缓存
    UNIQUE(module, month)
);
```

### 4.4 weekly_signing（周报产线索引）

```sql
CREATE TABLE IF NOT EXISTS weekly_signing (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    month TEXT NOT NULL,
    perf_id TEXT NOT NULL,
    sales_contract_no TEXT,
    contract_name TEXT,
    prod_line TEXT,                   -- 所属产线（c93 数据来源）
    project_status TEXT,
    pmo_note TEXT,
    note TEXT,
    owner TEXT,
    dept TEXT,
    raw TEXT,
    UNIQUE(month, perf_id)
);
CREATE INDEX IF NOT EXISTS idx_ws_perf ON weekly_signing(perf_id);
CREATE INDEX IF NOT EXISTS idx_ws_month ON weekly_signing(month);
```

### 4.5 md_reference（参考数据）

```sql
CREATE TABLE IF NOT EXISTS md_reference (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    data_type TEXT NOT NULL,          -- 'project_manager' | 'dept' | ...
    code TEXT NOT NULL,
    label TEXT NOT NULL,
    extra TEXT,                       -- JSON 附加属性
    sort_order INTEGER DEFAULT 0,
    enabled INTEGER DEFAULT 1,
    updated_at TEXT,
    UNIQUE(data_type, code)
);
```

### 4.6 rr_edit_history（手工调整留痕表，新增）

```sql
CREATE TABLE IF NOT EXISTS rr_edit_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    month TEXT NOT NULL,               -- YYYYMM
    sheet TEXT NOT NULL,               -- 预算执行表 / 计划确收底稿
    row_index INTEGER NOT NULL,        -- 行序号
    column_name TEXT NOT NULL,         -- 列名（如 c63 偏差-状态/趋势）
    original_value TEXT,               -- 原值
    new_value TEXT,                    -- 新值
    edit_type TEXT NOT NULL,           -- dropdown / text / date / auto_fill
    operator TEXT NOT NULL,            -- 操作人
    created_at TEXT DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_rr_edit_month ON rr_edit_history(month, sheet);
CREATE INDEX IF NOT EXISTS idx_rr_edit_row ON rr_edit_history(month, sheet, row_index);
```

### 4.7 rr_import_validation（导入校验结果表，新增）

```sql
CREATE TABLE IF NOT EXISTS rr_import_validation (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    month TEXT NOT NULL,
    sheet TEXT NOT NULL,
    row_index INTEGER NOT NULL,
    column_name TEXT,
    rule_code TEXT NOT NULL,           -- V01 ~ V12（见 §1.5.2）
    severity TEXT NOT NULL,            -- ERROR / WARNING
    message TEXT NOT NULL,
    original_value TEXT,
    corrected_value TEXT,              -- 人工校正后的值（NULL = 未处理）
    status TEXT DEFAULT 'pending',     -- pending / confirmed / rejected
    operator TEXT,
    created_at TEXT DEFAULT (datetime('now','localtime')),
    resolved_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_rr_val_month ON rr_import_validation(month, status);
```

---

## 6. 逐 Sheet 详细定义

### 5.1 Sheet 1：预算执行表

**类型**：核心数据（原始明细）
**数据源**：手工 Excel 导入
**行数**：~8,988 行（含空行过滤后）
**列数**：93 列

**行结构**：
| 行 | 内容 |
|---|---|
| row 1 | 空行（手工报表上方留空） |
| row 2 | 分组标题行（"预算情况"等） |
| row 3 | 表头行（93 列名称） |
| row 4+ | 数据行 |

**列定义（93 列）**：

| 列号 | 列名 | 字段名 | 类型 | 说明 |
|---|---|---|---|---|
| c1 | 分类 | category | TEXT | 递延 / 新签 |
| c2 | 合同编号 | contract_no | TEXT | 索引列 |
| c3 | 合同编号（校准） | contract_no_cal | TEXT | 校准用合同编号 |
| c4 | 客户名称 | customer | TEXT | |
| c5 | 最终用户名称 | end_user | TEXT | |
| c6 | 签约主体 | sign_subject | TEXT | 北京梆梆 / 等 |
| c7 | 合同归档月份 | archive_month | TEXT | YYYYMM 格式 |
| c8 | 履约ID（预算） | perf_id_budget | TEXT | |
| c9 | 履约明细(预算） | perf_detail_budget | TEXT | |
| c10 | 履约ID | perf_id | TEXT | 索引列 |
| c11 | 收入确认方法 | rev_method | TEXT | 时点法 / 时段法 |
| c12 | 单项履约义务金额 | perf_amount | NUMERIC | 核心金额字段 |
| c13 | 截止20251231已确收金额 | rev_prior | NUMERIC | |
| c14 | 2026年及以后计划确收 | rev_future | NUMERIC | |
| c15 | 年初-未立项&项目异常未计划确收 | no_plan | NUMERIC | |
| c16 | 截止20251231未确收金额 | unrev_prior | NUMERIC | |
| c17 | 截止20251231未确收金额（调整） | unrev_adj | NUMERIC | |
| c18 | 计划开始时间 | plan_start | TEXT | |
| c19 | 计划结束时间 | plan_end | TEXT | |
| c20 | 计划完成时间 | plan_done | TEXT | YYYYMM |
| c21-c32 | 202601 ~ 202612 | m202601~m202612 | NUMERIC | 各月**计划**确收金额 |
| c33 | 2026年预计 | year_est | NUMERIC | SUM(c21:c32) |
| c34 | 202601-06预计 | h1_plan | NUMERIC | SUM(c21:c26) |
| c35 | 202601-06确收 | h1_actual | NUMERIC | SUM(c38:c43 实际) |
| c36 | 202601-06提前完成 | h1_ahead | NUMERIC | |
| c37 | 202601-06滞后未完成 | h1_behind | NUMERIC | |
| c38-c43 | 202601 ~ 202606 | a202601~a202606 | NUMERIC | 各月**实际**确收金额 |
| c44 | 2026消失金额 | disappear_2026 | NUMERIC | |
| c45 | 2026年及以后消失金额 | disappear_future | NUMERIC | |
| c46 | 消失备注 | disappear_note | TEXT | |
| c47 | 重拆履约，提前和滞后同增 | rebuild_perf | TEXT | |
| c48 | 合同数量统计唯一值 | — | FORMULA | SUBTOTAL(3, ...) |
| c49 | 合同数量统计位 | — | FORMULA | |
| c50 | 确收-财务是否交接（合同编号校验） | — | TEXT | |
| c51 | 确收-财务是否交接 | — | TEXT | |
| c52 | 确收-财务反馈 | — | TEXT | |
| c53 | 是否正常摊销 | — | TEXT | |
| c54 | 是否统计确收？ | — | TEXT | 筛选标记 |
| c55 | 项目经理 | project_manager | TEXT | |
| c56 | PM-周报按合同 | — | TEXT | |
| c57 | 项目经理所属团队 | — | TEXT | |
| c58 | 履约项统计状态（周报） | — | TEXT | |
| c59 | 项目验收状态（周报） | — | TEXT | |
| c60 | 实际服务/授权开始日期（周报） | — | TEXT | |
| c61 | 实际服务/授权结束日期（周报） | — | TEXT | |
| c62 | 偏差-备注说明（手工填写） | — | TEXT | |
| c63 | 偏差-状态/趋势 | — | TEXT | 正常确收 / 差异确收 / ... |
| c64 | 偏差-原因类别 | — | TEXT | 交付原因-延期 / 客户原因-... |
| c65 | 签约金额（元） | — | NUMERIC | |
| c66 | 合同分类 | — | TEXT | |
| c67 | 是否完成下单流程 | — | TEXT | |
| c68 | 关联合同（终止/补充） | — | TEXT | |
| c69 | 预算填报 | — | TEXT | |
| c70 | 备注 | — | TEXT | |
| c71 | 预算填写说明 | — | TEXT | |
| c72 | 预算日期（已提交） | — | TEXT | |
| c73 | 预算趋势 | — | TEXT | |
| c74 | 预算趋势类别 | — | TEXT | |
| c75 | 预估交付完成日期（周报） | — | TEXT | |
| c76 | 预算-预估交付完成日期（周报） | — | TEXT | |
| c77 | 预算提交（校准） | — | TEXT | |
| c78 | 异常项目合同编号 | — | TEXT | |
| c79 | 合同归档日期 | — | TEXT | |
| c80 | 状态 | — | TEXT | |
| c81 | 异常项目-类别 | — | TEXT | |
| c82 | 异常项目-处置方案 | — | TEXT | |
| c83 | 异常处置方案-影响 | — | TEXT | |
| c84 | 异常报备日期 | — | TEXT | |
| c85 | 预估异常处置完成日期 | — | TEXT | |
| c86 | 异常影响情况 | — | TEXT | |
| c87 | 交付中心反馈 | — | TEXT | |
| c88 | 营销中心反馈 | — | TEXT | |
| c89 | 异常归档日期 | — | TEXT | |
| c90 | 交付说明（异常履约项统计类别） | — | TEXT | |
| c91 | 交付说明（履约项交付情况、合同交付条款） | — | TEXT | |
| c92 | 项目异常内容 | — | TEXT | |
| c93 | 所属产线（周报） | prod_line | TEXT | ← weekly_signing 反查 |

**导入映射**：
- c1-c47：从手工 Excel 直接读取（`BUDGET_FIELDS` 映射）
- c48-c77：手工报表公式列，导入时**不导入**（系统重新计算或留空）
- c78-c92：项目异常管理列，从手工 Excel 导入
- c93：从 `weekly_signing` 表反查（`perf_id` → `prod_line`）

---

### 5.2 Sheet 2：计划确收底稿

**类型**：核心数据（原始明细）
**数据源**：手工 Excel 导入
**行数**：~36,397 行
**列数**：45 列

**行结构**：
| 行 | 内容 |
|---|---|
| row 1-2 | 空行 |
| row 3 | 表头行 |
| row 4+ | 数据行 |

**列定义（45 列）**：

| 列号 | 列名 | 字段名 | 类型 | 说明 |
|---|---|---|---|---|
| c1 | 年初-填写说明 | note | TEXT | |
| c2 | 年初-交付预计完成时间 | init_est_date | TEXT | |
| c3 | 交付预计完成时间 | est_date | TEXT | |
| c4 | 合同编号 | contract_no | TEXT | |
| c5 | 合同归档月份 | archive_month | TEXT | YYYYMM |
| c6 | 合同编号 | contract_no2 | TEXT | 第2个合同编号列 |
| c7 | 标准产品服务名称序号 | prod_seq | TEXT | |
| c8 | 履约ID | perf_id | TEXT | |
| c9 | 对应预算履约ID | budget_perf_id | TEXT | |
| c10 | 现行部门 | dept | TEXT | |
| c11 | 合同名称 | contract_name | TEXT | |
| c12 | 客户名称 | customer | TEXT | |
| c13 | 最终用户名称 | end_user | TEXT | |
| c14 | 合同备注 | contract_note | TEXT | |
| c15 | 合同操作备注 | ops_note | TEXT | |
| c16 | 产品服务税率 | tax_rate | NUMERIC | |
| c17 | 合同签订日期 | sign_date | TEXT | |
| c18 | 合同起始时间 | contract_start | TEXT | |
| c19 | 合同结束时间 | contract_end | TEXT | |
| c20 | 服务期限（月） | service_months | INTEGER | |
| c21 | 合同类型 | contract_type | TEXT | |
| c22 | 合同版本类型 | version_type | TEXT | |
| c23 | 是否赠送项项目 | gift | TEXT | |
| c24 | 标准产品类别 | prod_category | TEXT | |
| c25 | 合同产品服务名称 | prod_name | TEXT | |
| c26 | 履约义务明细 | perf_detail | TEXT | |
| c27 | 标准产品服务名称 | std_prod_name | TEXT | |
| c28 | 收入对应科目 | rev_subject | TEXT | |
| c29 | 末级税金科目名称 | tax_subject | TEXT | |
| c30 | 价格拆分依据 | price_basis | TEXT | |
| c31 | 验收文件类型 | accept_type | TEXT | |
| c32 | 合同约定的验收条款 | accept_term | TEXT | |
| c33 | 合同约定的收款节奏 | payment_term | TEXT | |
| c34 | 收入确认方法 | rev_method | TEXT | |
| c35 | 履约不执行原因 | no_exec_reason | TEXT | |
| c36 | 数量单位 | qty_unit | TEXT | |
| c37 | 数量 | qty | NUMERIC | |
| c38 | 合同金额 | contract_amount | NUMERIC | |
| c39 | 确认合同额 | confirm_amount | NUMERIC | |
| c40 | 单项履约义务金额 | perf_amount | NUMERIC | |
| c41 | 计划履约金额 | plan_perf_amount | NUMERIC | |
| c42 | 截止20251231已确收 | rev_before_2025 | NUMERIC | |
| c43 | 2026年及以后计划确收 | rev_2026_future | NUMERIC | |
| c44 | 计划-消失金额 | plan_disappear | NUMERIC | |
| c45 | 消失原因 | disappear_reason | TEXT | |

---

### 5.3 Sheet 3：汇总

**类型**：汇总表（计算 + 缓存）
**数据源**：预算执行表聚合
**行数**：31 行（固定结构）
**列数**：13 列

**列定义（13 列）**：

| 列号 | 列名 | 类型 | 公式 |
|---|---|---|---|
| A | 期间 | TEXT | "202601" ~ "202612" |
| B | 新签合同额 | NUMERIC | SUMIF(预算执行表!category="新签", archive_month=A, perf_amount) |
| C | 新签-预计确收合同额 | NUMERIC | SUMIF(category="新签", SUM(m2026xx)) |
| D | 新签-实际确收合同额 | NUMERIC | SUMIF(category="新签", SUM(a2026xx)) |
| E | 新签-完成率 | NUMERIC | D / C |
| F | 递延-预计确收合同额 | NUMERIC | SUMIF(category="递延", SUM(m2026xx)) |
| G | 递延-实际确收合同额 | NUMERIC | SUMIF(category="递延", SUM(a2026xx)) |
| H | 递延-完成率 | NUMERIC | G / F |
| I | 合计-预计确收合同额 | NUMERIC | C + F |
| J | 合计-实际确收合同额 | NUMERIC | D + G |
| K | 合计-完成率 | NUMERIC | J / I |
| L | （空） | — | |
| M | 校验 | NUMERIC | 恒等式校验 |

**31 行结构定义**：见第 6 节。

---

### 5.4 Sheet 4：汇总分析

**类型**：透视表
**数据源**：按团队/产线聚合
**行数**：~64 行
**列数**：50 列

**行结构**：
| 行 | 内容 |
|---|---|
| row 1-3 | 筛选条件行（团队/产线/项目经理，默认 "*" = 全部） |
| row 4 | 分组标题行 |
| row 5 | 子表头行 |
| row 6-17 | 各月数据（202601 ~ 202612） |
| row 18 | 1-6月小计 |
| row 19 | 合计 |
| row 20-28 | 同比分析区（Y26 1~6 合同类别 × 销售合同额/确收合同额/确收度/比重） |
| row 29-64 | 扩展分析区（各团队/产线维度展开） |

**列定义（50 列）**：

| 列号 | 列名 | 分组 | 类型 |
|---|---|---|---|
| A | （空） | — | — |
| B | 期间 | — | TEXT |
| C | 新签合同额 | 新签 | NUMERIC |
| D | 新签-预计确收合同额 | 新签 | NUMERIC |
| E | 新签-实际确收合同额 | 新签 | NUMERIC |
| F | 新签-完成率 | 新签 | NUMERIC |
| G | 递延-预计确收合同额 | 递延 | NUMERIC |
| H | 递延-实际确收合同额 | 递延 | NUMERIC |
| I | 递延-完成率 | 递延 | NUMERIC |
| J | 合计-预计确收合同额 | 新签+递延 | NUMERIC |
| K | 合计-实际确收合同额 | 新签+递延 | NUMERIC |
| L | 合计-完成率 | 新签+递延 | NUMERIC |
| M-N | （空/分隔） | — | — |
| O | 同比分析标题 | 同比 | TEXT |
| P | Y26 1~6 合同类别 | 同比 | TEXT |
| Q | 销售合同额 | 同比 | NUMERIC |
| R | 确收合同额 | 同比 | NUMERIC |
| S | 确收度 | 同比 | NUMERIC |
| T | 比重 | 同比 | NUMERIC |
| U | 预计确收合同额 | 同比 | NUMERIC |
| V-AX | 扩展列（团队/产线展开） | 多维 | MIXED |

---

### 5.5 Sheet 5：预算趋势分析

**类型**：趋势表
**数据源**：多月份预算对比
**行数**：19 行
**列数**：17 列

**行结构**：
| 行 | 内容 |
|---|---|
| row 1-3 | 表头（3 层合并） |
| row 4-9 | 递延合同（6 种状态类型） |
| row 10 | 递延合计 |
| row 11 | 新签表头 |
| row 12-16 | 新签合同（5 种状态类型） |
| row 17 | 新签合计 |
| row 18 | 递延+新签共计 |
| row 19 | 新签预计确收率 |

**状态类型**：
1. 已归档但未下单
2. 已下单但无法交付
3. 已交付但无法确收
4. 本年度正常可确收
5. 未来可确收
6. 之前年度已确收（仅递延）

**列定义（17 列）**：

| 列号 | 列名 | 类型 |
|---|---|---|
| A | 期间（合同大类：递延/新签） | TEXT |
| B | 类型（状态描述） | TEXT |
| C | 期初-合同数量（个） | INTEGER |
| D | 期初-涉及金额（万） | NUMERIC |
| E | 本年正常交付-合同数量 | INTEGER |
| F | 本年正常交付-涉及金额（万） | NUMERIC |
| G | 异常中-合同数量 | INTEGER |
| H | 异常中-涉及金额（万） | NUMERIC |
| I | 合同消失-合同数量 | INTEGER |
| J | 合同消失-涉及金额（万） | NUMERIC |
| K | 未来交付-合同数量 | INTEGER |
| L | 未来交付-涉及金额（万） | NUMERIC |
| M | 校验-数量 | INTEGER |
| N | 校验-金额 | NUMERIC |
| O | 异常说明-未立项 | INTEGER |
| P | 异常说明-已立项 | INTEGER |
| Q | （空） | — |

---

### 5.6 Sheet 6：确收差异分析

**类型**：透视表
**数据源**：项目经理维度差异
**行数**：~16 行
**列数**：4 列

**行结构**：
| 行 | 内容 |
|---|---|
| row 1-4 | 筛选条件行（项目经理/团队/消失备注/重拆履约） |
| row 5 | 空行 |
| row 6 | 透视表标题（"求和项:202601-06滞后未完成"） |
| row 7 | 表头（行标签 / 递延 / 新签 / 总计） |
| row 8-15 | 差异原因类别（交付原因-延期、客户原因-延期、等） |
| row 16 | 总计 |

**列定义（4 列）**：

| 列号 | 列名 | 类型 |
|---|---|---|
| A | 行标签（差异原因类别） | TEXT |
| B | 递延 | NUMERIC |
| C | 新签 | NUMERIC |
| D | 总计 | NUMERIC |

---

### 5.7 Sheet 7：重拆履约

**类型**：透视表
**数据源**：合同 × 提前/滞后
**行数**：~9 行
**列数**：3 列

**行结构**：
| 行 | 内容 |
|---|---|
| row 1 | 空行 |
| row 2 | 表头（合同编号 / 提前完成 / 滞后未完成） |
| row 3-8 | 数据行（有差异的合同） |
| row 9 | 总计 |

**列定义（3 列）**：

| 列号 | 列名 | 类型 |
|---|---|---|
| A | 合同编号 | TEXT |
| B | 求和项:202601-06提前完成 | NUMERIC |
| C | 求和项:202601-06滞后未完成 | NUMERIC |

---

### 5.8 Sheet 8：图例

**类型**：静态表（参考数据）
**数据源**：md_reference 表 + 计划确收底稿
**行数**：~506 行
**列数**：16 列

**列定义（16 列）**：

| 列号 | 列名 | 分组 | 类型 | 说明 |
|---|---|---|---|---|
| A | 项目经理 | 项目经理映射 | TEXT | |
| B | 部门 | 项目经理映射 | TEXT | |
| C | 备注 | 项目经理映射 | TEXT | 在职/离职状态 |
| D | （空） | — | — | 分隔 |
| E | 偏差-状态/趋势 | 偏差分类 | TEXT | 正常确收 / 差异确收（当年可消除） / ... |
| F | 偏差-原因类别 | 偏差分类 | TEXT | 交付原因-延期 / 客户原因-... |
| G | 偏差-原因类别说明 | 偏差分类 | TEXT | 详细说明 |
| H | （空） | — | — | 分隔 |
| I | 滞后验收原因 | 验收分类 | TEXT | 验收已完成 / 正常验收 / ... |
| J | 滞后验收处置措施 | 验收分类 | TEXT | N/A / 正常交付 / ... |
| K | （空） | — | — | 分隔 |
| L | 预算执行进度 | 执行进度 | TEXT | 已归档但未下单 / 已下单但... |
| M | 预算执行进度类别 | 执行进度 | TEXT | 异常中 / 本年正常交付 / ... |
| N | （空） | — | — | 分隔 |
| O | 团队 | 团队/产线 | TEXT | |
| P | 产线 | 团队/产线 | TEXT | 编码+名称 |

---

### 5.9 Sheet 9：月度汇总记录

**类型**：汇总表（历史累积）
**数据源**：按月份聚合
**行数**：~266 行（多月份累积）
**列数**：11 列

**行结构**：
| 行 | 内容 |
|---|---|
| row 1 | 分组标题行 |
| row 2 | 表头行 |
| row 3+ | 数据行（统计期间 × 合同期间 交叉） |

**列定义（11 列）**：

| 列号 | 列名 | 类型 | 公式 |
|---|---|---|---|
| A | 统计期间 | TEXT | YYYYMM |
| B | 合同期间 | TEXT | YYYYMM（归档月份） |
| C | 新签合同额（万） | NUMERIC | SUM(perf_amount) WHERE category="新签" AND archive_month=B |
| D | 新签-预计确收合同额（万） | NUMERIC | SUM(m2026xx) WHERE category="新签" AND archive_month=B |
| E | 新签-实际确收合同额（万） | NUMERIC | SUM(a2026xx) WHERE category="新签" AND archive_month=B |
| F | 递延-预计确收合同额（万） | NUMERIC | SUM(m2026xx) WHERE category="递延" AND archive_month=B |
| G | 递延-实际确收合同额（万） | NUMERIC | SUM(a2026xx) WHERE category="递延" AND archive_month=B |
| H | 合计-预计确收合同额（万） | NUMERIC | D + F |
| I | 合计-实际确收合同额（万） | NUMERIC | E + G |
| J | 合计校准（预计） | NUMERIC | 校验列（应为 0） |
| K | 合计校准（实际） | NUMERIC | 校验列（应为 0） |

---

### 5.10 Sheet 10：履约汇总记录

**类型**：汇总表（历史累积）
**数据源**：按履约维度聚合
**行数**：~126 行（多月份累积）
**列数**：6 列

**行结构**：
| 行 | 内容 |
|---|---|
| row 1 | 表头行 |
| row 2+ | 数据行（每月 6-7 行 × 多月份） |

**每月子结构（7 行）**：
| 行 | 类别 | 说明 |
|---|---|---|
| 1 | 预算完成 | 截止到当月的全年累计计划 |
| 2 | 实际完成 | 截止到当月的全年累计实际 |
| 3 | 预算-实际 | 差异（实际 - 预算） |
| 4 | 其中：提前完成 | 不含分项金额调整 |
| 5 | 滞后未完成 | 不含分项金额调整 |
| 6 | 消失 | 消失金额 |

**列定义（6 列）**：

| 列号 | 列名 | 类型 |
|---|---|---|
| A | 统计期间 | TEXT |
| B | 类别 | TEXT |
| C | 新签 | NUMERIC |
| D | 递延 | NUMERIC |
| E | 合计 | NUMERIC |
| F | 备注 | TEXT |

---

## 7. 汇总 Sheet 31 行结构定义（逐行）

| 行号 | A 列 | B 列 | C-M 列内容 | 说明 |
|---|---|---|---|---|
| 1 | （空） | （空） | （空） | 手工报表上方留空 |
| 2 | （空） | 期间 | 新签合同/（合并）/ 递延合同/（合并）/ 合计/（合并） | 分组标题行（合并单元格） |
| 3 | （空） | （空） | 新签合同额/预计确收合同额/实际确收合同额/完成率 × 3组 | 子表头行 |
| 4 | （空） | 202601 | 1月新签/递延/合计数据 | 1月数据行 |
| 5 | （空） | 202602 | 2月数据 | 2月数据行 |
| 6 | （空） | 202603 | 3月数据 | 3月数据行 |
| 7 | （空） | 202604 | 4月数据 | 4月数据行 |
| 8 | （空） | 202605 | 5月数据 | 5月数据行 |
| 9 | （空） | 202606 | 6月数据 | 6月数据行 |
| 10 | （空） | 202607 | 7月数据（计划有/实际空） | 7月数据行 |
| 11 | （空） | 202608 | 8月数据 | 8月数据行 |
| 12 | （空） | 202609 | 9月数据 | 9月数据行 |
| 13 | （空） | 202610 | 10月数据 | 10月数据行 |
| 14 | （空） | 202611 | 11月数据 | 11月数据行 |
| 15 | （空） | 202612 | 12月数据 | 12月数据行 |
| 16 | （空） | 1-6月小计 | SUM(row4:row9) | 上半年小计 |
| 17 | （空） | 合计 | SUM(全年) | 全年合计 |
| 18 | （空） | 说明1 | "1、递延合同截止{month}实际比预计..." | 递延说明 |
| 19 | （空） | 说明2 | "2、新签合同截止{month}实际比预计..." | 新签说明 |
| 20 | （空） | （空） | 履约维度： | 履约维度标题 |
| 21 | （空） | （空） | 类别/新签/递延/合计 | 履约维度表头 |
| 22 | （空） | （空） | 预算完成/值/值/值 | 预算完成行 |
| 23 | （空） | （空） | 实际完成/值/值/值 | 实际完成行 |
| 24 | （空） | （空） | 预算-实际/值/值/值 | 差异行 |
| 25 | （空） | （空） | 其中：提前完成/值/值/值 | 提前完成行 |
| 26 | （空） | （空） | 滞后未完成/值/值/值 | 滞后未完成行 |
| 27 | （空） | （空） | 消失/值/值/值 | 消失行 |
| 28 | （空） | （空） | 校验/值/值/值 | 校验行（应为0） |
| 29 | （空） | （空） | （空） | 空行 |
| 30 | （空） | （空） | （空） | 空行 |
| 31 | （空） | （空） | （空） | 空行 |

---

## 8. 计算公式字典

### 7.1 核心公式

| 编号 | 公式名称 | 表达式 | 说明 |
|---|---|---|---|
| F01 | 完成率 | `实际确收 / 预计确收` | 单月/累计完成率 |
| F02 | 新签合同额 | `SUM(perf_amount) WHERE category="新签" AND archive_month = 当前月` | 当月归档的新签合同金额 |
| F03 | 预计确收合同额 | `SUM(m2026xx) WHERE category=指定分类` | 某月计划确收 |
| F04 | 实际确收合同额 | `SUM(a2026xx) WHERE category=指定分类` | 某月实际确收 |
| F05 | 差异 | `实际完成 - 预算完成` | 正=超额，负=未完成 |
| F06 | 提前完成 | `SUM(MAX(actual - plan, 0))` 按合同 | 实际>计划的累计差 |
| F07 | 滞后未完成 | `SUM(MAX(plan - actual, 0))` 按合同 | 计划>实际的累计差 |
| F08 | 校验 | `滞后未完成 - 提前完成 - (预算 - 实际)` | 应≈0 |
| F09 | 合计预计确收 | `新签预计 + 递延预计` | 分组合计 |
| F10 | 合计实际确收 | `新签实际 + 递延实际` | 分组合计 |
| F11 | 合计完成率 | `合计实际 / 合计预计` | 综合完成率 |
| F12 | 1-6月小计 | `SUM(m202601:m202606)` | 上半年累计 |
| F13 | 全年合计 | `SUM(m202601:m202612)` | 全年累计 |
| F14 | 确收度 | `确收合同额 / 销售合同额` | 同比分析用 |
| F15 | 比重 | `单类合同额 / 总合同额` | 结构分析 |

### 7.2 汇总 Sheet 行 18-19 说明文本模板

```
row18: "{递延/新签}合同截止{year}年{month}月实际比预计完成{减少/增加}{abs(diff):.0f}万元。"
```

### 7.3 预算趋势分析公式

| 编号 | 公式 | 说明 |
|---|---|---|
| T01 | 本年正常交付: `disappear_2026 in (None, "", "0") AND rebuild_perf in (None, "", "0")` | 正常履约 |
| T02 | 异常中: `disappear_2026 not in (None, "", "0")` | 有消失金额 |
| T03 | 上年结转: `rev_prior > 0` | 有前期已确收 |
| T04 | 校验: `期初数量 = Σ(各状态数量)` | 恒等校验 |

---

## 9. Excel 导出样式规范

### 8.1 字体

| 用途 | 字体 | 大小 | 样式 | 颜色 |
|---|---|---|---|---|
| 表头 | 微软雅黑 | 10pt | bold | 白色 (FFFFFFFF) |
| 子表头 | 微软雅黑 | 10pt | bold | 黑色 |
| 数据 | 微软雅黑 | 10pt | normal | 黑色 |
| 小计/合计 | 微软雅黑 | 10pt | bold | 黑色 |

### 8.2 填充色

| 用途 | 前景色 | 背景色 |
|---|---|---|
| 主表头 | FF4472C4（蓝） | solid |
| 子表头/小计 | FFD9E1F2（浅蓝） | solid |
| 数据行 | 无 | 无 |

### 8.3 对齐

| 类型 | 水平 | 垂直 |
|---|---|---|
| 期间列 | center | center |
| 文本列 | left | center |
| 金额列 | right | center |
| 完成率列 | right | center |

### 8.4 边框

所有数据单元格：四边薄线，颜色 FFD9D9D9（浅灰）。

### 8.5 数值格式

| 类型 | 格式代码 |
|---|---|
| 金额 | `#,##0.00` |
| 完成率 | `0.0000` |
| 整数 | `#,##0` |
| 万元金额 | `#,##0.00` |

### 8.6 列宽

| Sheet | 列宽策略 |
|---|---|
| 汇总 | 固定：A=10, B=14, C-K=14/10 交替 |
| 预算执行表 | 自动（采样前 200 行，最大 40） |
| 计划确收底稿 | 自动（采样前 200 行，最大 40） |
| 其他 | 自动（采样前 200 行，最大 40） |

### 8.7 冻结窗格

| Sheet | 冻结位置 |
|---|---|
| 汇总 | B4（冻结前 3 行 + A 列） |
| 预算执行表 | D4（冻结前 3 行 + A-C 列） |
| 计划确收底稿 | D4 |
| 其他 | A2（冻结表头） |

### 8.8 行高

- 表头行：20pt（自动换行）
- 数据行：15pt（默认）

---

## 10. 数据导入映射

### 9.1 预算执行表字段映射（BUD_FIELDS）

```python
BUDGET_FIELDS = {
    "category":        ("分类",),
    "contract_no":     ("合同编号",),
    "contract_no_cal": ("合同编号(校准)", "合同编号（校准）"),
    "customer":        ("客户名称",),
    "end_user":        ("最终用户名称",),
    "sign_subject":    ("签约主体",),
    "archive_month":   ("合同归档月份",),
    "perf_id_budget":  ("履约ID(预算)", "履约ID（预算）"),
    "perf_detail_budget": ("履约明细(预算)", "履约明细（预算）"),
    "perf_id":         ("履约ID",),
    "rev_method":      ("收入确认方法",),
    "perf_amount":     ("单项履约义务金额",),
    "rev_prior":       ("截止20251231已确收金额",),
    "rev_future":      ("2026年及以后计划确收",),
    "no_plan":         ("年初-未立项&项目异常未计划确收",),
    "unrev_prior":     ("截止20251231未确收金额",),
    "unrev_adj":       ("截止20251231未确收金额(调整)",),
    "plan_start":      ("计划开始时间",),
    "plan_end":        ("计划结束时间",),
    "plan_done":       ("计划完成时间",),
    "year_est":        ("2026年预计",),
    "disappear_2026":  ("2026消失金额",),
    "disappear_future": ("2026年及以后消失金额",),
    "disappear_note":  ("消失备注",),
    "rebuild_perf":    ("重拆履约,提前和滞后同增", "重拆履约，提前和滞后同增"),
}
```

### 9.2 计划确收底稿字段映射（PLAN_FIELDS）

```python
PLAN_FIELDS = {
    "note":            ("年初-填写说明",),
    "init_est_date":   ("年初-交付预计完成时间",),
    "est_date":        ("交付预计完成时间",),
    "contract_no":     ("合同编号",),
    "archive_month":   ("合同归档月份",),
    "contract_no2":    ("合同编号",),       # 第2次出现
    "prod_seq":        ("标准产品服务名称序号",),
    "perf_id":         ("履约ID",),
    "budget_perf_id":  ("对应预算履约ID",),
    "dept":            ("现行部门",),
    "contract_name":   ("合同名称",),
    "customer":        ("客户名称",),
    "end_user":        ("最终用户名称",),
    "contract_note":   ("合同备注",),
    "ops_note":        ("合同操作备注",),
    "tax_rate":        ("产品服务税率",),
    "sign_date":       ("合同签订日期",),
    "contract_start":  ("合同起始时间",),
    "contract_end":    ("合同结束时间",),
    "service_months":  ("服务期限(月)", "服务期限（月）"),
    "contract_type":   ("合同类型",),
    "version_type":    ("合同版本类型",),
    "gift":            ("是否赠送项项目",),
    "prod_category":   ("标准产品类别",),
    "prod_name":       ("合同产品服务名称",),
    "perf_detail":     ("履约义务明细",),
    "std_prod_name":   ("标准产品服务名称",),
    "rev_subject":     ("收入对应科目",),
    "tax_subject":     ("末级税金科目名称",),
    "price_basis":     ("价格拆分依据",),
    "accept_type":     ("验收文件类型",),
    "accept_term":     ("合同约定的验收条款",),
    "payment_term":    ("合同约定的收款节奏",),
    "rev_method":      ("收入确认方法",),
    "no_exec_reason":  ("履约不执行原因",),
    "qty_unit":        ("数量单位",),
    "qty":             ("数量",),
    "contract_amount": ("合同金额",),
    "confirm_amount":  ("确认合同额",),
    "perf_amount":     ("单项履约义务金额",),
    "plan_perf_amount": ("计划履约金额",),
    "rev_before_2025": ("截止20251231已确收",),
    "rev_2026_future": ("2026年及以后计划确收",),
    "plan_disappear":  ("计划-消失金额",),
    "disappear_reason": ("消失原因",),
}
```

### 9.3 月份列探测

月份列通过 `HeaderMapper.find_month_columns("2026")` 自动探测：
- 第一次出现的 `2026xx` → 计划列 `m2026xx`
- 第二次出现的 `2026xx` → 实际列 `a2026xx`

### 9.4 数值字段集合

```python
NUMERIC_FIELDS = {
    "tax_rate", "service_months", "qty", "contract_amount", "confirm_amount",
    "perf_amount", "plan_perf_amount", "rev_before_2025", "rev_2026_future",
    "plan_disappear", "rev_prior", "rev_future", "no_plan", "unrev_prior",
    "unrev_adj", "year_est", "h1_plan", "h1_actual", "h1_ahead", "h1_behind",
    "disappear_2026", "disappear_future",
}
```

### 9.5 周报产线映射

c93 列数据来自 `weekly_signing` 表：
```python
# key: perf_id → prod_line
prod_line_index = load_prod_line_index(db_path, month)
```

---

## 11. 错误处理

### 10.1 错误码

| 错误码 | 触发条件 | 处理方式 |
|---|---|---|
| `REVENUE_SOURCE_NOT_FOUND` | 找不到源 Excel 文件 | 报错提示路径 |
| `REVENUE_SHEET_MISSING` | xlsx 中缺少必需 Sheet | 返回 `{"rows": 0, "error": "..."}` |
| `REVENUE_HEADER_DETECT_FAIL` | 无法探测表头行 | 跳过该 Sheet |
| `REVENUE_NO_DATA` | compute 时无数据 | 返回 `{"error": "无预算执行表数据"}` |
| `REVENUE_CACHE_MISS` | export 时无缓存 | 引导先执行 generate |
| `REVENUE_FORMULA_ERROR` | 公式计算异常（除零等） | 返回 None/0，不中断 |
| `REVENUE_IMPORT_PARTIAL` | 部分 Sheet 导入失败 | 返回各 Sheet 独立结果 |

### 10.2 容错规则

1. **空行过滤**：所有 Sheet 跳过全空行
2. **数值安全**：`_safe_float()` 将非法值转为 None，不抛异常
3. **除零保护**：完成率计算 `actual / plan if plan else 0`
4. **部分失败**：`import_all()` 各 Sheet 独立 try/except，部分成功仍返回
5. **降级策略**：图例从 `md_reference` 读取，无数据时从计划确收底稿提取

### 10.3 数据校验

| 校验项 | 规则 | 级别 |
|---|---|---|
| 汇总行校验 | `滞后未完成 - 提前完成 - (预算 - 实际) ≈ 0` | WARNING |
| 合计校准 | `合计预计 = 新签预计 + 递延预计` | ERROR |
| 月份完整性 | 12 个月列均存在 | WARNING |
| 行数合理性 | 预算执行表 > 0 行 | ERROR |
| 列数匹配 | 导入列数 = 元数据列数 | WARNING |

---

## 12. CLI 命令

### 11.1 命令清单

```bash
# 导入源数据
bdms revenue import <month> [--file <path>]
  导入手工 Excel → 落盘到宽表

# 生成报表
bdms revenue generate <month> [--mode auto|read|regenerate]
  计算汇总数据 → 缓存结果

# 导出 Excel
bdms revenue export <month> [--out <path>]
  读缓存 → 渲染格式化 Excel

# 查看汇总
bdms revenue summary <month>
  输出 JSON 汇总数据

# 查看导入状态
bdms revenue status <month>
  显示各 Sheet 行数

# 列出有数据的月份
bdms revenue months
  列出已导入的所有月份

# 导入周报数据
bdms revenue import-weekly <month> --file <csv_path>
  导入周报 CSV → weekly_signing 表
```

### 11.2 使用流程

```bash
# 完整工作流
bdms revenue import 202606 --file "source.xlsx"
bdms revenue generate 202606
bdms revenue export 202606 --out "report.xlsx"

# 快捷方式（import + generate 一步到位）
bdms revenue generate 202606 --mode regenerate
```

---

## 13. 测试策略

### 12.1 测试分层

| 层级 | 测试内容 | 工具 | 覆盖率目标 |
|---|---|---|---|
| 单元测试 | 字段映射、数值转换、公式计算 | pytest | > 80% |
| 集成测试 | import → generate → export 全流程 | pytest + 临时 DB | 核心路径 |
| 对比测试 | BDMS 输出 vs 黄金基准 | compare_revenue_summary.py | 汇总 Sheet 100% 对齐 |
| 回归测试 | has_data 按月份过滤、幂等语义 | pytest | 已修复缺陷 |

### 12.2 关键测试用例

| 用例 | 输入 | 预期输出 |
|---|---|---|
| TC-01 导入预算执行表 | 标准 xlsx（8988 行） | rr_sheet_row 写入 > 8000 行 |
| TC-02 导入计划确收底稿 | 标准 xlsx（36397 行） | rr_sheet_row 写入 > 30000 行 |
| TC-03 汇总计算 | 202606 数据 | 12 个月 × 3 组数据完整 |
| TC-04 汇总对比 | BDMS vs 手工 | 各月差异 < 0.01 |
| TC-05 导出 Excel | 有缓存数据 | 10 Sheet 全部生成 |
| TC-06 幂等 auto 模式 | 重复 generate | 第二次走 read 路径 |
| TC-07 空月份查询 | has_data("203012") | 返回 False |
| TC-08 部分导入失败 | 缺 1 个 Sheet | 其他 Sheet 正常导入 |
| TC-09 重拆履约计算 | 有差异合同 | 提前/滞后金额正确 |
| TC-10 万元格式化 | 金额 / 10000 | Excel 显示万元 |

### 12.3 对比测试方案

```bash
# 运行对比测试
python3 tools/compare_revenue_summary.py 202606

# 验收标准
# - 各月新签合同额差异 < 0.01
# - 各月预计确收差异 < 0.01
# - 各月实际确收差异 < 0.01
# - 完成率差异 < 0.0001
```

### 12.4 测试数据

| 数据 | 来源 | 用途 |
|---|---|---|
| 202606 完整报表 | 黄金基准 xlsx | 主测试数据 |
| 202605 历史报表 | 历史文件 | 月度汇总记录累积测试 |
| 202403 历史报表 | 历史文件 | 跨年度数据测试 |
| 空文件 | 合成 | 边界条件测试 |
| 缺列文件 | 合成 | 容错测试 |

---

## 14. 性能约束

| 操作 | 目标耗时 | 备注 |
|---|---|---|
| 导入（8988 + 36397 行） | < 30 秒 | openpyxl read_only 模式 |
| 汇总计算 | < 5 秒 | 从宽表内存聚合 |
| 导出 10 Sheet Excel | < 10 秒 | 含格式化 |
| DB 查询（单月） | < 500ms | 有索引 |

---

## 15. 风险与限制

| 风险 | 影响 | 缓解 |
|---|---|---|
| 手工报表列序变动 | 字段映射失败 | 按列名匹配 + 月份列自动探测 |
| 手工报表 Sheet 名变更 | 找不到 Sheet | 配置化 Sheet 名称映射 |
| 周报 CSV 列名变化 | c93 无法填充 | 按列名定位，降级留空 |
| 大文件内存占用 | OOM | openpyxl read_only + 分批写入 |
| 公式缓存丢失 | 对比测试偏差 | data_only=True 读缓存值 |

---

## 16. 复用资产清单与使用方式

> **原则**：所有复用资产通过 **import 引用 / 继承 / 组合** 方式使用，**禁止复制粘贴**。

| 资产 | 来源文件 | 使用方式 | 重构操作 | 本模块调用代码 |
|---|---|---|---|---|
| `BaseEngine` | `modules/base.py` | **继承** | 子类化 | `class RevenueEngine(BaseEngine): ...` |
| `BaseService` | `modules/base.py` | **继承** | 子类化 | `class RevenueService(BaseService): ...` |
| `BaseImporter` | `modules/base.py` | **继承** | 子类化 | `class RevenueImporter(BaseImporter): ...` |
| `BaseExporter` | `modules/base.py` | **继承** | 子类化 | `class RevenueExporter(BaseExporter): ...` |
| `RevenueEngineAdapter` | `modules/revenue/engine.py` | **import 引用** | 无（直接调用） | `from bdms.modules.revenue.engine import RevenueEngineAdapter` |
| `summary_engine` | `modules/revenue/summary_engine.py` | **import 引用** | 无（直接调用） | `from bdms.modules.revenue.summary_engine import compute_summary` |
| `stats_builders` | `modules/revenue/stats_builders.py` | **import 引用** | 无（直接调用） | `from bdms.modules.revenue.stats_builders import build_summary_analysis` |
| `weekly_importer` | `modules/revenue/weekly_importer.py` | **组合** | 实例化调用 | `from bdms.modules.revenue.weekly_importer import WeeklyImporter` |
| `WeComDocConnector` | `modules/integration/connectors/wecom_doc.py` | **组合** | 实例化调用 | `from bdms.modules.integration.connectors.wecom_doc import WeComDocConnector` |
| `LocalImportConnector` | `modules/integration/connectors/local_import.py` | **组合** | 实例化调用 | `from bdms.modules.integration.connectors.local_import import LocalImportConnector` |
| `dr_sheet_row` | `core/schemas_v21.py` | **DB 共享** | 只读 | `SELECT data FROM dr_sheet_row WHERE month=?` |
| `md_reference` | `core/schemas_v21.py` | **DB 共享** | 只读 | `SELECT label FROM md_reference WHERE data_type='project_manager' AND code=?` |
| `openpyxl` | 三方库 | **import 引用** | 无 | `import openpyxl; wb = openpyxl.load_workbook(path, data_only=True)` |
| `pandas` | 三方库 | **import 引用** | 无 | `import pandas as pd; df = pd.read_excel(path)` |

**重构检查清单**：
- [ ] 所有 import 路径指向源文件（非副本）
- [ ] 继承关系正确（子类 → BaseEngine/BaseService/BaseImporter/BaseExporter）
- [ ] summary_engine/stats_builders 通过 import 引用（非复制）
- [ ] integration 连接器通过组合调用（非本模块重复实现）
- [ ] 无复制粘贴代码块
- [ ] 如需修改源文件功能，通过 PR 修改源文件（非本模块内重写）

---

> 文档结束 | DESIGN-DETAIL-REVENUE-v2.1 r3 | 2026-09-24

## 变更历史

| 版本 | 日期 | 变更 |
|---|---|---|
| v2.1 r3 | 2026-09-24 | Rex 审核反馈 5 条：<br>① 明确 weekly_signing 含义（ONES 周报导入的履约ID→产线映射，c93 反查）；模块依赖增加合同管理（cr_contracts）+ 产品/服务知识库（kb_item）+ 项目利润（下游）；新增业务数据链路图<br>② 新增 §1.6 手工调整列定义：下拉列表列 14 项（枚举值）+ 文本框列 7 组 + 日期列 4 项 + 编辑权限矩阵（PMO 默认/超管全量）+ rr_edit_history 留痕表<br>③ 模块关联：合同管理（履约义务拆分依据）+ 知识库（标准产品目录 + 收入确认方法）<br>④ 新增 §1.5 原始数据来源（财务部门提供，按合同拆分履约义务）+ §1.5.2 导入校验 12 条规则（V01-V12，ERROR 拒绝/WARNING 存疑展示）+ RevenueValidator 接口 + rr_import_validation 表<br>⑤ 新增 §1.7 收入确认准则参照（ASC 606 / 企业会计准则14号）：五步法模型 + 时点法/时段法判定 + 软件行业典型场景 + 知识库自动填充建议 |
| v2.1 r2 | 2026-09-22 | 复用资产清单与使用方式 |
| v2.1 r1 | 2026-09-22 | 初版 |
