# BDMS v2.1 — 交付月报模块详细设计文档

> **Bangcle Delivery Management System — Delivery Report Module**
> 版本：v2.1 Detail r2（2026-09-22）
> 层级：L4 专有业务层 — 模块 #3
> 依据：`PRD-v2.1.md` §模块 3 + `DESIGN-OUTLINE-v2.1.md` §模块 3
> 前置：`DR_SCHEMA`（宽表 JSON 行存储）已就绪
> 状态：待 Rex 审核

## 目录

1. [模块概述](#1-模块概述)
2. [OS 依赖与限制](#2-os-依赖与限制)
3. [技术方案](#3-技术方案)
4. [接口设计](#4-接口设计)
5. [数据模型](#5-数据模型)
6. [逐 Sheet 详细定义](#6-逐-sheet-详细定义)
7. [开发自检项](#7-开发自检项)
8. [复用资产清单与使用方式](#8-复用资产清单与使用方式)
9. [验收标准](#9-验收标准)
10. [审核记录与变更历史](#10-审核记录与变更历史)

## 0. 版本记录

| 版本 | 日期 | 变更说明 |
|---|---|---|
| v2.1 Detail r1 | 2026-09-22 | 初版：15 Sheet 定义 + 分步流程 |
| v2.1 Detail r2 | 2026-09-22 | Rex 审核反馈 6 条：数据来源细化 + 图例预落盘 + 分步执行 + DASHBOARD 统计 + Validator + 业界最佳实践 + dr_import_validation |

---

## 1. 模块概述

### 1.1 业务目标

按照手工报表解析后的三类数据——**原始数据**、**公式计算数据**、**统计汇总数据**——实现 Bangcle 交付月报 Excel（15 Sheet）的自动生成，以 202606 黄金基准（`2026交付月报-20260630.xlsx`）为验收标准，达到逐格一致。

### 1.2 数据来源与获取方式

| # | 数据源 | 获取方式 | 数据量特征 | 导入频率 | 备注 |
|---|---|---|---|---|---|
| 1 | 签约合同导出 CSV | **ONES 浏览器自动化**导出 | ~15,682 行（同一年度逐月增加） | 月报生成时 | 主数据源 |
| 2 | POC&提前实施导出 CSV | **ONES 浏览器自动化**导出 | ~4,270 行（同一年度逐月增加） | 月报生成时 | 主数据源 |
| 3 | 异常项目导出 CSV | **ONES 浏览器自动化**导出 | ~352 行 | 月报生成时 | 主数据源 |
| 4 | 确收交接导出 CSV | **企业微信文档**（优先）/ 系统通用数据导入（备选） | ~514 行 | 月报生成时 | 如企微存在技术瓶颈，通过系统通用数据导入功能实现 |
| 5 | 验收交接导出 CSV | **企业微信文档**（优先）/ 系统通用数据导入（备选） | ~531 行 | 月报生成时 | 如企微存在技术瓶颈，通过系统通用数据导入功能实现 |
| 6 | 图例配置表 | **黄金基准 Sheet-15** 预提取 | ~502 行 × 48 列 | 一次性预落盘 | 为公式计算提供 VLOOKUP 映射 |

> **数据获取技术方案**：
> - ONES CSV：通过 integration 模块 I-01 连接器（浏览器自动化）导出
> - 企微文档：通过 integration 模块 I-04 连接器（API 接口）获取
> - 系统通用导入：如企微 API 存在技术瓶颈，通过 integration I-05（本机导入 Excel/CSV）实现
> - 图例配置：从黄金基准 Sheet-15 提取后预落盘到 `md_reference`（data_type='legend_config'）

#### 1.2.1 业界最佳实践参考

| 产品/方案 | 核心能力 | 借鉴点 | 本系统落地 |
|---|---|---|---|
| **Power BI Report Server** | 报表自动化 | 数据集 → 报表分层 + 定时刷新 | extract → compute → export 分步执行 |
| **SSRS (SQL Server Reporting)** | 企业报表 | 模板化报表 + 订阅分发 | 15 Sheet 模板 + 黄金基准对齐 |
| **Apache Superset** | 数据可视化 | SQL → 图表 + 下钻 | DASHBOARD 实时聚合统计 Sheet |
| **Airbyte/dbt** | 数据管道 | ELT 分层 + 数据质量测试 | Validator 12 条规则 + 存疑数据流程 |
| **Great Expectations** | 数据校验 | 数据质量断言 + 告警 | validate_not_null/type/enum/row_count |
| **Excel Power Query** | 数据转换 | M 语言管道 + 刷新 | _apply_computations 计算管线 |

### 1.3 设计原则

| 原则 | 落地方式 |
|---|---|
| **计算与输出分离** | `engine.compute()` 纯计算（无 DB 写入）；`engine.persist()` 负责落盘；`exporter.export()` 纯 IO 不做业务计算 |
| **公式计算落盘** | 公式计算在 compute 阶段完成，由 persist 写入 dr_sheet_row（以值写入，非 Excel 公式） |
| **统计汇总走 DASHBOARD** | 统计汇总数据通过 DASHBOARD 实时聚合生成，无需单独落盘；导出时直接通过 DASHBOARD 功能生成 |
| **幂等可重入** | auto / read / regenerate 三模式；`persist(overwrite=True)` 保证重复执行一致 |
| **宽表 JSON 行** | `dr_sheet_row(data JSON)` 避免 83 列硬编码 DDL |
| **黄金基准对齐** | `tools/compare_delivery_report.py` 逐格比对验证 |

> **关于 compute 纯计算 vs 公式落盘**：不冲突。compute() 方法是纯函数（输入→输出，不写 DB），但 persist() 负责将 compute 的结果落盘。公式计算在 compute 阶段完成计算逻辑，由 persist 阶段写入 DB。

### 1.4 月报生成分步流程

每次新生成月报时，分步执行：

```
Step 1: 提取原始数据并落盘
    ├── 1a. ONES 导出签约/POC/异常 CSV（浏览器自动化）
    ├── 1b. 企微/导入获取确收/验收 CSV
    ├── 1c. 解析 CSV → dr_sheet_row（原始数据 Sheet 1-5）
    └── 1d. 图例配置预落盘（md_reference）

Step 2: 校验原始数据有效性
    ├── 2a. 非空检查（必填字段：合同编号、项目名称等）
    ├── 2b. 数据类型检查（日期格式、金额数值等）
    ├── 2c. 枚举值检查（状态标志、类型编码等）
    ├── 2d. 行数合理性检查（与上月对比，偏差 >20% 警告）
    └── 2e. 存疑数据展示 → 人工调整（Web UI 标注 + 编辑）

Step 3: 公式计算数据计算并落盘
    ├── 3a. 状态桶计算（c56 IFS 状态桶 + c57-c65 九状态列）
    ├── 3b. 考核列计算（交付计划准确率/按时交付率 4 列组）
    ├── 3c. VLOOKUP 跨 sheet 列（项目经理→部门映射）
    ├── 3d. 校验列计算（c53/c66）
    └── 3e. 落盘 dr_sheet_row（formula 类型）

Step 4: 统计汇总数据生成（通过 DASHBOARD）
    ├── 4a. 10 个统计 Sheet 定义（结构 + 列名）
    ├── 4b. 数据通过 DASHBOARD 实时聚合生成（不单独落盘）
    └── 4c. 导出时直接读取 DASHBOARD 聚合结果

Step 5: Excel 导出
    ├── 5a. 核心数据 Sheet（1-5）：读 dr_sheet_row 原始数据 + 公式计算结果
    ├── 5b. 统计 Sheet（6-14）：读 DASHBOARD 实时聚合结果
    └── 5c. 图例 Sheet（15）：读 md_reference legend_config
```

### 1.5 文件结构

```
modules/delivery_report/
├── __init__.py          # 模块入口
├── engine.py            # 计算引擎（DeliveryReportEngine）
├── service.py           # 编排服务（DeliveryReportService）
├── validator.py         # 数据校验器（新增）
├── exporter.py          # Excel 导出（DeliveryReportExporter）
└── stats_builders_c.py  # 统计 Sheet 结构定义（C 组 10 个，仅定义结构）

modules/dashboard/
└── delivery_report_connector.py  # DASHBOARD 聚合查询适配（新增）

docs/
├── DESIGN-DETAIL-DELIVERY-REPORT-v2.1.md  # 本文档
└── archive/

tools/
└── compare_delivery_report.py

tests/
└── test_delivery_report_export.py
```

---

## 2. OS 依赖与限制

> 本模块通过 integration 模块间接依赖浏览器自动化（ONES 数据源），需对齐 INTEGRATION 模块的 OS 适配方案。

| 功能 | OS 依赖 | macOS | Windows | Linux | 说明 |
|---|---|---|---|---|---|
| ONES 数据导入（签约/POC/异常） | 浏览器自动化 | ✅ osascript（已验证） | 🔶 Playwright（待适配） | 🔶 Playwright（待适配） | 间接依赖 integration I-01 |
| 企微文档导入（确收/验收） | API/浏览器/本机导入 | ✅ 多方案降级 | ✅ 多方案降级 | ✅ 多方案降级 | 间接依赖 integration I-04 |
| 统计汇总生成 | DASHBOARD 实时聚合 | ✅ 支持 | ✅ 支持 | ✅ 支持 | 纯 SQL 聚合，OS 无关 |
| Excel 导出 | openpyxl | ✅ 支持 | ✅ 支持 | ✅ 支持 | 纯 Python |
| 数据校验 | pandas | ✅ 支持 | ✅ 支持 | ✅ 支持 | 纯 Python |
| Web UI (FastAPI) | uvicorn + Jinja2 | ✅ 支持 | ✅ 支持 | ✅ 支持 | 纯 Python |
| CLI (Click) | click | ✅ 支持 | ✅ 支持 | ✅ 支持 | 纯 Python |

**间接依赖链**：
```
delivery_report
├── ONES 数据源 → integration I-01 → 浏览器自动化
│   ├── macOS: osascript + Chrome（已验证）
│   ├── Linux: Playwright Headless（待验证）
│   └── Windows: Playwright Headless（待开发）
├── 企微文档 → integration I-04 → API/浏览器/本机导入（多方案降级）
├── 统计汇总 → DASHBOARD 实时聚合（OS 无关）
└── Excel/校验/Web/CLI → 纯 Python（全平台）
```

## 3. 技术方案

### 2.1 分层架构

```
┌─────────────────────────────────────────────────────────────┐
│                    CLI / Web API 入口                         │
│              bdms-cli report generate 2026-06                 │
│              bdms-cli report export 2026-06                   │
├─────────────────────────────────────────────────────────────┤
│                   Service 层（编排）                          │
│             DeliveryReportService.generate()                 │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Step 1: extract_raw_data()  → 原始数据落盘           │   │
│  │  Step 2: validate_raw_data() → 校验 + 存疑展示        │   │
│  │  Step 3: compute_formula()   → 公式计算落盘           │   │
│  │  Step 4: stats_via_dashboard() → DASHBOARD 实时聚合   │   │
│  │  Step 5: export()           → Excel 导出              │   │
│  └──────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────┤
│                   Engine 层（计算）                           │
│             DeliveryReportEngine.compute()                   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  1. load_ones_sign_contracts()  → df_sign             │   │
│  │  2. load_ones_poc()             → df_poc              │   │
│  │  3. load_ones_exceptions()      → df_exc              │   │
│  │  4. load_handover_revenue()     → df_rev              │   │
│  │  5. load_handover_acceptance()  → df_acc              │   │
│  │  6. build_sign_sheet_df()       → 签约 83 列          │   │
│  │  7. build_poc_sheet_df()        → POC 84 列           │   │
│  │  8. build_exception_df()        → 异常 38 列          │   │
│  │  9. build_revenue_handover_df() → 确收 23 列          │   │
│  │ 10. build_acceptance_handover_df()→ 验收 27 列         │   │
│  │ 11. _apply_computations()       → VLOOKUP/公式/状态    │   │
│  └──────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────┤
│                   数据校验层（新增）                          │
│             DeliveryReportValidator                         │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  1. validate_not_null()      → 非空检查               │   │
│  │  2. validate_data_type()     → 类型检查               │   │
│  │  3. validate_enum()          → 枚举值检查             │   │
│  │  4. validate_row_count()     → 行数合理性             │   │
│  │  5. collect_suspicious()     → 存疑数据收集           │   │
│  └──────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────┤
│                   Persist 层（落盘）                          │
│             DeliveryReportEngine.persist()                   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  dr_sheet_row:   month, sheet, row_index, data(JSON)  │   │
│  │  dr_sheet_meta:  month, sheet, columns(JSON), count   │   │
│  │  report_month:   module, month, row_counts            │   │
│  │  md_reference:   legend_config（图例预落盘）          │   │
│  └──────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────┤
│                   Export 层（输出）                           │
│             DeliveryReportExporter.export()                  │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  1. 核心数据 Sheet（1-5）：读 dr_sheet_row            │   │
│  │  2. 统计 Sheet（6-14）：读 DASHBOARD 实时聚合         │   │
│  │  3. 图例 Sheet（15）：读 md_reference                  │   │
│  │  4. openpyxl 样式 → 字体/颜色/列宽/冻结/筛选          │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 数据流

```
ONES CSV（签约/POC/异常）         企微文档/导入（确收/验收）
    ↓ 浏览器自动化/API              ↓ API/通用导入
原始 DataFrame                      原始 DataFrame
    ↓ build_*_sheet_df()            ↓ build_*_sheet_df()
基础 DataFrame（原始列）
    ↓ _apply_computations()
完整 DataFrame（公式计算列）
    ↓ persist()
dr_sheet_row（JSON 宽表）+ dr_sheet_meta + md_reference（图例）
    ↓ export()
交付月报_{YYYYMM}.xlsx（15 Sheet）
    ├── Sheet 1-5：核心数据（dr_sheet_row）
    ├── Sheet 6-14：统计（DASHBOARD 实时聚合）
    └── Sheet 15：图例（md_reference）
```

### 2.3 计算契约（核心约束）

| 约束 | 说明 |
|---|---|
| ❌ exporter 禁止任何业务计算 | export 只做读 DB + 写 Excel 格式 |
| ✅ 公式计算在 compute 阶段完成 | 结果由 persist 落盘到 dr_sheet_row |
| ✅ 公式结果以值写入 | 非 Excel 公式 |
| ✅ 统计 Sheet 通过 DASHBOARD 实时生成 | 无需单独落盘，导出时直接读取 |
| ✅ 图例配置预落盘 | 从黄金基准 Sheet-15 提取 → md_reference |

---

## 4. 接口设计

### 3.1 DeliveryReportEngine

```python
class DeliveryReportEngine:
    """交付月报计算引擎（无状态，方法可独立调用）。"""

    # ─── 数据源检查 ───
    def check_sources(self, month: str) -> dict:
        """检查某月数据源是否齐备。"""

    def sources_available(self, month: str) -> bool:
        """签约数据源是否可用（最低门槛）。"""

    # ─── 分步执行 ───
    def extract_raw_data(self, month: str) -> dict:
        """Step 1: 提取原始数据并落盘。
        调用 integration 连接器获取 ONES CSV + 企微文档。
        返回：{sheet_name: DataFrame}
        """

    def compute(self, month: str) -> dict[str, pd.DataFrame]:
        """Step 3: 公式计算（纯函数，无 DB 写入）。
        前置：原始数据已落盘。
        返回：{sheet_name: DataFrame}
        """

    def persist(self, month: str, data: dict[str, pd.DataFrame],
                overwrite: bool = True) -> dict[str, int]:
        """将公式计算结果落盘到 dr_sheet_row。"""

    # ─── 读取 ───
    def load(self, month: str) -> dict[str, pd.DataFrame]:
        """从 DB 读取某月全部 Sheet 数据。"""

    def has_data(self, month: str) -> bool:
        """DB 中是否已有该月数据。"""
```

### 3.2 DeliveryReportValidator（新增）

```python
class DeliveryReportValidator:
    """原始数据校验器。"""

    def validate_not_null(self, df: pd.DataFrame, required_cols: list[str]) -> list[dict]:
        """非空检查。返回：[{row: int, col: str, value: None}]"""

    def validate_data_type(self, df: pd.DataFrame, col_types: dict[str, str]) -> list[dict]:
        """数据类型检查（date/numeric/text）。"""

    def validate_enum(self, df: pd.DataFrame, col_enums: dict[str, list[str]]) -> list[dict]:
        """枚举值检查。"""

    def validate_row_count(self, sheet: str, current: int, previous: int,
                           threshold: float = 0.2) -> dict:
        """行数合理性检查（与上月对比）。
        偏差 >threshold 时返回警告。"""

    def collect_suspicious(self, month: str) -> dict:
        """收集所有存疑数据。
        Returns: {
            "errors": [{"sheet": str, "row": int, "col": str, "issue": str, "value": any}],
            "warnings": [{"sheet": str, "row": int, "col": str, "issue": str}],
            "summary": {"total_errors": int, "total_warnings": int}
        }
        """

    def apply_manual_fixes(self, month: str, fixes: list[dict]) -> dict:
        """应用人工调整。
        fixes: [{"sheet": str, "row_index": int, "col": str, "value": any}]
        """
```

### 3.3 DeliveryReportService

```python
class DeliveryReportService(BaseService):
    """交付月报编排服务（分步执行）。"""

    module_name: str = "delivery_report"

    def generate(self, month: str, mode: str = "auto") -> dict:
        """分步执行月报生成。
        Step 1: extract_raw_data → 落盘
        Step 2: validate → 返回存疑数据（如需人工调整，等待后继续）
        Step 3: compute → persist 落盘
        Step 4: 统计汇总通过 DASHBOARD 实时生成
        """

    def generate_with_validation(self, month: str,
                                  fixes: list[dict] = None) -> dict:
        """带校验的生成流程。
        如有存疑数据，应用 fixes 后继续。
        """

    def export(self, month: str, out_path: Path = None) -> Path:
        """导出 Excel。"""
```

### 3.4 DeliveryReportExporter

```python
class DeliveryReportExporter:
    """交付月报 Excel 导出器（只做 IO + 格式，不做计算）。"""

    SHEET_ORDER: list[str] = [
        "签约", "POC&提前实施", "异常项目", "确收交接", "验收交接",
        "异常台账", "交付效率统计", "签约统计", "产品-授权&维保统计",
        "POC&提前实施统计", "提前实施分事业部统计", "异常统计",
        "交付异常分事业部统计", "交接统计", "图例",
    ]

    def export(self, month: str, out_path: Path = None) -> Path:
        """导出某月数据为 Excel。
        核心数据（Sheet 1-5）：读 dr_sheet_row
        统计 Sheet（6-14）：读 DASHBOARD 实时聚合
        图例（Sheet 15）：读 md_reference legend_config
        """
```

---

## 5. 数据模型

### 4.1 dr_sheet_row（核心数据表）

> 与旧版一致。宽表 JSON 行模式。

### 4.2 dr_sheet_meta（Sheet 元信息表）

> 与旧版一致。

### 4.3 report_month（月度登记）

> 与旧版一致。

### 4.4 md_reference（字典表 — 扩展）

新增 data_type：

| data_type | 说明 | 预落盘来源 |
|---|---|---|
| `legend_config` | 图例配置（48 列 × ~502 行） | 黄金基准 Sheet-15 |
| `legend_pm_dept` | 项目经理→部门映射（核心 2 列） | 黄金基准 Sheet-15 A:B |
| `legend_team_stats` | 销售团队→统计团队映射 | 黄金基准 Sheet-15 AA:AB |
| `legend_baseline` | 基准列（预算-预估日期等） | 黄金基准 Sheet-15 F:K |
| `legend_pm_full` | 项目经理全量映射（含考核项） | 黄金基准 Sheet-15 M:Y |

**图例 48 列分组结构**（以 202606 基准为例）：

| 组 | 列范围 | 内容 | 列数 |
|---|---|---|---|
| 第一组 | A-D | 项目经理、部门、中心、备注 | 4 |
| 第二组 | F-K | 考核项、偏差类别、是否跨月等 | 6 |
| 第三组 | M-Y | 日期列映射（预估/预算/基线） | 13 |
| 第四组 | AA-AB | 销售团队→统计团队 | 2 |
| 第五组 | AD-AF | 其他映射（直签/代理等） | 3 |
| 空列 | E, L, Z, AC | 分隔空列 | 4 |
| **合计** | A-AF | | **48** |

> 空列（E/L/Z/AC）为分隔列，导出时保留空列位。

### 4.5 dr_import_validation（导入校验结果表，新增）

> 对齐 REVENUE 模块的 rr_import_validation 模式（存疑数据统一落盘 + 人工处置流程）。

```sql
CREATE TABLE IF NOT EXISTS dr_import_validation (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    month TEXT NOT NULL,
    sheet TEXT NOT NULL,               -- 签约 / POC&提前实施 / 异常项目 / 确收交接 / 验收交接
    row_index INTEGER NOT NULL,
    column_name TEXT,
    rule_code TEXT NOT NULL,           -- V01 ~ V10（见 §3.2 DeliveryReportValidator）
    severity TEXT NOT NULL,            -- ERROR / WARNING
    message TEXT NOT NULL,
    original_value TEXT,
    corrected_value TEXT,              -- 人工校正后的值（NULL = 未处理）
    status TEXT DEFAULT 'pending',     -- pending / confirmed / rejected
    operator TEXT,
    created_at TEXT DEFAULT (datetime('now','localtime')),
    resolved_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_dr_val_month ON dr_import_validation(month, status);
```


---

## 6. 逐 Sheet 详细定义

### 5.1 Sheet 1：签约

| 属性 | 值 |
|---|---|
| **类型** | 核心数据 |
| **数据源** | ONES 签约合同导出 CSV（浏览器自动化） |
| **行数基准** | ~15,682（202606 实测，同一年度逐月增加） |
| **列数** | 83 |

**关键公式列**：

| # | 列名 | 计算逻辑 |
|---|---|---|
| 53 | 履约项合计 | COUNTIF 当前合同编号在整列的出现次数 |
| 54 | 校验 | `c53 - SUM(c45:c52)` |
| 56 | 项目统计状态 | IFS 状态桶（基于 c45-c52 九状态标志） |
| 57-65 | 九状态列 | 每状态一列，值为 1/0 |
| 66 | 统计校验 | `SUM(c57:c65) - c53` |
| 67 | 履约项统计状态 | 财报-交付/确收状态 |
| 68-72 | 考核列（交付计划准确率） | 差异/提前延后/是否跨月/考核扣分 |
| 73-76 | 考核列（按时交付率） | 差异/提前延后/是否跨月/考核扣分 |
| 79 | 销售团队-统计 | `VLOOKUP(责任销售所属团队, 图例!AA:AB, 2, FALSE)` |

### 5.2 Sheet 2：POC&提前实施

| 属性 | 值 |
|---|---|
| **类型** | 核心数据 |
| **数据源** | ONES POC 导出 CSV（浏览器自动化） |
| **行数基准** | ~4,270（202606 实测，同一年度逐月增加） |
| **列数** | 84 |

**c80「统计所属项目」**：列 CE，逐行去重标记。
```python
# 计算逻辑：每行校验其上方行（同列）是否已存在相同的所属项目值
# - 如上方已出现 → 本单元格为空（去重）
# - 如上方未出现 → 本单元格为当前行的所属项目数值
# 实现：
seen = set()
for i, val in enumerate(df['所属项目']):
    if val in seen:
        c80[i] = None  # 已出现过，置空
    else:
        c80[i] = val   # 首次出现，显示值
        seen.add(val)
```

### 5.3 Sheet 3：异常项目

| 属性 | 值 |
|---|---|
| **类型** | 核心数据 |
| **数据源** | ONES 异常导出 CSV（浏览器自动化） |
| **行数基准** | ~352 |
| **列数** | 38 |

### 5.4 Sheet 4：确收交接

| 属性 | 值 |
|---|---|
| **类型** | 核心数据 |
| **数据源** | 企业微信文档（优先）/ 系统通用导入（备选） |
| **行数基准** | ~514 |
| **列数** | 23 |

### 5.5 Sheet 5：验收交接

| 属性 | 值 |
|---|---|
| **类型** | 核心数据 |
| **数据源** | 企业微信文档（优先）/ 系统通用导入（备选） |
| **行数基准** | ~531 |
| **列数** | 27 |

### 5.6 Sheet 6-14：统计汇总

| Sheet | 名称 | 数据生成方式 | 说明 |
|---|---|---|---|
| 6 | 交付效率统计 | **DASHBOARD 实时聚合** | 项目经理团队/部门/中心 3 组 |
| 7 | 签约统计 | **DASHBOARD 实时聚合** | 按统计项目编号/部门 |
| 8 | 产品-授权&维保统计 | **DASHBOARD 实时聚合** | 按产品分类 |
| 9 | POC&提前实施统计 | **DASHBOARD 实时聚合** | 多维度 |
| 10 | 提前实施分事业部统计 | **DASHBOARD 实时聚合** | 按事业部 |
| 11 | 异常统计 | **DASHBOARD 实时聚合** | 多维交叉（条件默认全部时应与手工一致） |
| 12 | 异常台账 | **DASHBOARD 实时聚合** | 36 行固定结构 |
| 13 | 交付异常分事业部统计 | **DASHBOARD 实时聚合** | 按事业部 |
| 14 | 交接统计 | **DASHBOARD 实时聚合** | 按区域 |

> **统计 Sheet 说明**：
> - 统计汇总数据通过 DASHBOARD 实时聚合生成，无需单独落盘
> - 导出时直接读取 DASHBOARD 聚合结果（耗时 < 3s）
> - 异常统计 54 列结构：条件默认全部时应与手工基准一致；当月自动生成报表与手工报表也应一致
> - 异常台账固定 36 行（2025 基准 12 行 + 2026 基准 13 行 + 3 空行 + 8 末尾空行）

### 5.7 Sheet 15：图例

| 属性 | 值 |
|---|---|
| **类型** | 静态配置 |
| **数据源** | md_reference（legend_config，从黄金基准预提取） |
| **行数** | ~502 |
| **列数** | 48 |
| **列分组** | A-D(4) + E(空) + F-K(6) + L(空) + M-Y(13) + Z(空) + AA-AB(2) + AC(空) + AD-AF(3) = 48 |

---

## 7. 开发自检项

> 以下条目为开发/验收时的自检项，无需人工确认，逐项对比 202606 黄金基准通过即可。

| # | 自检项 | 校验方法 | 影响范围 |
|---|---|---|---|
| 1 | 交付效率统计偏差率公式 | 公式计算数据中已处理 ABS，按参考手工基准计算 | Sheet 6 |
| 2 | 异常统计 54 列结构 | 对比 202606 基准 Sheet-11 逐列核实（列名 + 列序 + 值） | Sheet 11 |
| 3 | POC c80 统计所属项目 | 逐行去重标记：上方已出现则为空，否则显示值 | Sheet 2 |

---

## 8. 复用资产清单与使用方式

> **原则**：所有复用资产通过 **import 引用 / 继承 / 组合** 方式使用，**禁止复制粘贴**。

| 资产 | 来源文件 | 使用方式 | 重构操作 | 本模块调用代码 |
|---|---|---|---|---|
| `load_ones_sign_contracts` | `delivery-center/v2/` 或 `modules/revenue/weekly_importer.py` | **import 引用** | 重构为 integration I-01 连接器方法 | `from bdms.modules.integration.connectors.ones import OnesConnector` |
| `build_sign_sheet_df` | `delivery-center/v2/` | **import 引用** | 迁入本模块 engine.py | `from .legacy_adapter import build_sign_sheet_df` |
| `stats_builders_c` | `modules/delivery_report/stats_builders_c.py` | **import 引用** | 直接调用 | `from .stats_builders_c import build_abnormal_ledger, build_efficiency_stats, ...` |
| `BaseEngine` | `modules/base.py` | **继承** | 子类化 | `class DeliveryReportEngine(BaseEngine): ...` |
| `BaseService` | `modules/base.py` | **继承** | 子类化 | `class DeliveryReportService(BaseService): ...` |
| `BaseExporter` | `modules/base.py` | **继承** | 子类化 | `class DeliveryReportExporter(BaseExporter): ...` |
| `DashboardService` | `modules/dashboard/service.py` | **组合** | 实例化调用（统计汇总） | `from bdms.modules.dashboard.service import DashboardService; dashboard = DashboardService()` |
| `md_reference` | `core/schemas_v21.py` | **DB 共享** | 读写字典 | `SELECT label FROM md_reference WHERE data_type='legend_config' AND code=?` |
| `dr_sheet_row` | `core/schemas_v21.py` | **DB 共享** | 读写宽表 | `INSERT INTO dr_sheet_row (month, sheet, row_index, data) VALUES (...)` |

**重构检查清单**：
- [ ] 所有 import 路径指向源文件（非副本）
- [ ] delivery-center v2 代码通过 import 引用（非复制到本模块）
- [ ] 统计汇总通过 DashboardService 调用（非本模块重复实现）
- [ ] 继承关系正确（子类 → BaseEngine/BaseService/BaseExporter）
- [ ] 无复制粘贴代码块
- [ ] 如需修改源文件功能，通过 PR 修改源文件（非本模块内重写）

---

## 9. 验收标准

| 维度 | 标准 |
|---|---|
| 15 Sheet 完整性 | 全部 15 Sheet 存在 |
| 行数误差 | 核心数据 Sheet ≤ 1；统计 Sheet 通过 DASHBOARD 实时生成 |
| 列名一致性 | 100%（含列序） |
| 公式计算 | 与手工报表值一致 |
| 原始数据 | 与 ONES/企微导出 CSV 一致 |
| 图例配置 | 与黄金基准 Sheet-15 一致 |

---

## 10. 审核记录与变更历史

### 8.1 审核

| 轮次 | 日期 | 审核人 | 结论 | 意见 |
|---|---|---|---|---|
| 1 | 2026-09-22 | Rex | ⏳ 待审 | — |

### 8.2 变更历史

| 版本      | 日期         | 变更                                                                                                                                                                                                                                                           |
| ------- | ---------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| v2.1 r2 | 2026-09-22 | Rex 审核反馈 6 条修改：<br>① 明确公式计算落盘不冲突（compute 纯计算 + persist 落盘）<br>② 细化数据来源获取方式（ONES 浏览器自动化 + 企微文档/通用导入）<br>③ 新增图例配置预落盘（从黄金基准 Sheet-15 提取）<br>④ 新增分步执行流程（提取→校验→公式计算→统计汇总→导出）<br>⑤ 统计汇总走 DASHBOARD（不单独落盘）<br>⑥ 新增 DeliveryReportValidator 数据校验器<br>⑦ 图例 48 列分组结构定义 |
| v2.1 r1 | 2026-09-22 | 初版                                                                                                                                                                                                                                                           |
