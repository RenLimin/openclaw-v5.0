# BDMS v2.1 Base 层详细设计

> 版本：v2.1 Detail（2026-09-19）
> 层级：L4 专有业务层 — Base 层
> 继承：无（基础抽象层）
> 状态：设计阶段，待 Rex 审核

---

## 1. 模块概述

Base 层是 BDMS v2.1 的核心抽象基础设施，为所有业务模块提供标准化的接口契约、幂等骨架和共享工具。

**L3 域归属**：横切（横跨 8 个模块）

**与其他模块的交互方式**：
- 所有业务模块的 Service 层继承或组合 BaseService
- 所有 Engine 实现 BaseEngine 接口
- 报表导出器继承 BaseExporter
- 数据导入器继承 BaseImporter

---

## 2. 技术方案

### 2.1 技术选型

| 维度 | 选型 | 依据 |
|---|---|---|
| 语言 | Python 3.10+ | 现有 BDMS 全栈 Python |
| 设计模式 | 模板方法模式（Template Method） | BaseService.generate() 骨架固定，子类填充细节 |
| 抽象机制 | ABC + abstractmethod | 强制子类实现契约接口 |
| 数据交换 | dict + pandas DataFrame | 与现有 delivery_report/revenue 引擎兼容 |
| 持久化 | SQLite（通过 bdms.core.db） | 现有统一 DB 层，宽表 + 强类型表混合 |

### 2.2 依赖的 L2/L3 资产

| 资产 | 层级 | 复用方式 |
|---|---|---|
| bdms.core.db | L4 Core | get_connection / save_sheet_rows / load_sheet_rows |
| bdms.core.paths | L4 Core | DATA_DIR / OUTPUT_DIR / ensure_dirs |
| bdms.core.schemas | L4 Core | DR_SCHEMA / RR_SCHEMA / DASHBOARD_SCHEMA |
| L2 Persistence-006 | L2 | SQLite + Repository 模式（已在 core/db 中实现） |

### 2.3 与现有代码的复用/重构关系

现有 `modules/base.py` 已实现 BaseEngine、BaseService、BaseExporter 骨架。v2.1 在此基础上：

1. **BaseEngine**：保持现有 compute/persist/load/has_data 四方法契约
2. **BaseService**：保持 generate/auto/read/regenerate 三模式幂等骨架，增加 job 生命周期钩子
3. **BaseExporter**：保持 export/_write_all_sheets 模板，增加样式常量统一
4. **新增 BaseImporter**：统一数据校验/幂等导入/错误重试骨架

---

## 3. 接口契约

### 3.1 BaseEngine（计算引擎接口契约）

```python
class BaseEngine(ABC):
    """计算引擎抽象基类。

    设计约定：
      - compute(month) → 纯计算，不落盘，返回 dict
      - persist(month, data, overwrite=True) → 落盘到 DB，返回 {sheet: row_count}
      - load(month) → 从 DB 读，返回与 compute 同构的 dict
      - has_data(month) → DB 中是否已有该月数据
      - check_sources(month) → 返回数据源状态（可选实现）
      - sources_available(month) → bool（可选实现）
    """

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path) if db_path else (DATA_DIR / "bdms.db")

    @abstractmethod
    def compute(self, month: str) -> dict:
        """计算某月数据。纯函数，无副作用。"""

    @abstractmethod
    def persist(self, month: str, data: dict, overwrite: bool = True) -> dict[str, int]:
        """将计算结果落盘到 DB。返回 {sheet_name: row_count}。"""

    @abstractmethod
    def load(self, month: str) -> dict:
        """从 DB 读取某月数据。返回 {sheet_name: DataFrame 或 list[dict]}。"""

    @abstractmethod
    def has_data(self, month: str) -> bool:
        """DB 中是否已有该月数据。"""

    # ─── 可选实现 ───

    def check_sources(self, month: str) -> dict:
        """检查某月的数据源是否齐备。默认返回空 dict。"""
        return {}

    def sources_available(self, month: str) -> bool:
        """数据源是否可用。默认返回 True。"""
        return True
```

**子类实现清单**：

| 子引擎                  | 模块                                 | compute 返回              | 特殊行为                    |
| -------------------- | ---------------------------------- | ----------------------- | ----------------------- |
| DeliveryReportEngine | project_management/delivery_report | {sheet: DataFrame}      | 复用 delivery-center 计算函数 |
| RevenueEngineAdapter | project_management/revenue         | {sheet: dict}           | 从宽表读数据，按需聚合             |
| CostEngine           | project_management/cost            | {cost_type: list[dict]} | 工时/设备/差旅                |
| RiskEngine           | project_management/risk            | {risk_item: dict}       | 异常报备/审核                 |

### 3.2 BaseService（幂等编排服务基类）

```python
class BaseService:
    """幂等编排服务基类。

    子类必须设置：
      - module_name: str（注册到 job / report_month 的模块名）
      - engine: BaseEngine（计算引擎实例）

    幂等模式：
      - mode="auto"：有数据则读，无数据则算
      - mode="read"：强制读取（无数据报错）
      - mode="regenerate"：强制重新计算并覆盖
    """

    module_name: str = ""
    engine: BaseEngine = None

    def __init__(self):
        if not self.module_name:
            raise ValueError(f"{type(self).__name__} 必须设置 module_name")
        if self.engine is None:
            raise ValueError(f"{type(self).__name__} 必须设置 engine")
        self.meta_db_path = DATA_DIR / "bdms.db"

    def generate(self, month: str, mode: str = MODE_AUTO) -> dict:
        """幂等生成/读取。

        Returns: {
            "month", "mode", "action" (read|generated),
            "sheets", "job_id", "total_rows"
        }

        钩子方法（子类可覆盖）：
          - _load_existing(month) → dict：自定义 read 行为
          - _count_rows(data) → dict[str, int]：自定义行数统计
          - _on_job_start(job_id, month, mode)：job 创建后的回调
          - _on_job_finish(job_id, result)：job 完成后的回调
        """

    def has_data(self, month: str) -> bool:
        """检查某月是否有数据。"""

    def list_months(self) -> list[dict]:
        """列出已有数据的月份。"""

    # ─── 内部方法 ───

    def _finish_job(self, job_id, status, progress, message, output_path):
        """更新 job 状态。"""

    def _load_existing(self, month: str) -> dict:
        """读取已有数据（默认委托 engine.load）。"""
        return self.engine.load(month)
```

**子类实现清单**：

| 子服务 | 模块 | 特殊行为 |
|---|---|---|
| DeliveryReportService | delivery_report | 无（纯继承） |
| RevenueService | revenue | 覆盖 _load_existing、list_months；新增 import_source/summary |
| ContractManagementService | contract_management | 新增 submit_approval/approve/reject/sign/archive |
| ProjectManagementService | project_management | 新增 init_project/update_scope/close_project |
| AfterSalesService | after_sales | 新增 transfer/create_ticket/assign/resolve |
| CostService | cost | 新增 submit_timesheet/approve_timesheet |
| RiskService | risk | 新增 report_risk/review_risk |

### 3.3 BaseExporter（Excel 导出骨架）

```python
class BaseExporter(ABC):
    """Excel 导出骨架。

    子类必须设置：
      - sheet_order: list[str] — 导出 sheet 顺序
      - module_name: str — 用于输出文件名
    """

    sheet_order: list[str] = []
    module_name: str = ""

    # ─── 统一样式常量 ───

    HEADER_FONT = Font(bold=True, size=11)
    HEADER_PATTERN = "44568B"
    BORDER = Border(bottom=Side(style="thin"))
    NUMBER_FORMAT = "#,##0.00"
    DATE_FORMAT = "YYYY-MM-DD"
    COLUMN_PADDING = 2

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path) if db_path else (DATA_DIR / "bdms.db")

    def export(self, month: str, out_path: Optional[Path] = None) -> Path:
        """导出 Excel。

        1. 打开 DB 连接
        2. 创建 Workbook
        3. 调用 self._write_all_sheets(wb, month, conn)
        4. 保存到 OUTPUT_DIR（或指定路径）
        5. 返回输出路径
        """

    @abstractmethod
    def _write_all_sheets(self, wb, month: str, conn) -> None:
        """子类写所有 sheet 内容。"""

    # ─── 共享工具方法 ───

    def _write_header_row(self, ws, row_idx: int, headers: list[str]) -> None:
        """写表头行（统一样式）。"""

    def _auto_column_width(self, ws, columns: list[str], sample_rows: list[dict]) -> None:
        """自动列宽。"""

    def _apply_data_style(self, cell, data_type: str) -> None:
        """应用数据类型样式（number/date/text）。"""

    def _write_dataframe(self, ws, df: pd.DataFrame, start_row: int = 0) -> None:
        """DataFrame 直接写入。"""
```

**子类实现清单**：

| 子导出器 | 模块 | sheet_order |
|---|---|---|
| DeliveryReportExporter | delivery_report | ["签约", "POC&提前实施", "异常项目", "确收交接", "验收交接"] |
| RevenueExporter | revenue | ["计划确收底稿", "预算执行表", "汇总", "汇总分析", "月度汇总记录", "履约汇总记录", "确收差异分析", "预算趋势分析", "图例", "重拆履约"] |
| DashboardExporter | dashboard | ["KPI总览", "趋势图", "状态分布", "异常分布", "部门统计"] |
| ContractExporter | contract_management | ["合同概览", "风险明细", "审批日志", "审计追踪"] |
| AfterSalesExporter | after_sales | ["工单列表", "SLA统计"] |

### 3.4 BaseImporter（数据导入骨架）

```python
class BaseImporter(ABC):
    """数据导入器共享骨架。

    统一处理：数据校验、幂等导入、错误日志。

    子类必须实现：
      - source_type: str — 导入来源类型标识
      - _parse_source(source_path) → dict：解析源文件
      - _validate_parsed(data) → bool：校验解析结果
      - _persist_data(month, data) → dict：幂等落盘
    """

    source_type: str = ""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path) if db_path else (DATA_DIR / "bdms.db")

    def import_all(self, source_path: Path, month: str) -> dict:
        """完整导入流程：

        1. validate_source → 不可读则抛异常
        2. _parse_source → 解析
        3. _validate_parsed → 校验
        4. _persist_data → 幂等落盘
        5. register_month → 登记
        6. 写 import_log → 日志
        """

    def validate_source(self, source_path: Path) -> bool:
        """校验源文件是否可读（默认检查存在性+扩展名）。"""

    @abstractmethod
    def _parse_source(self, source_path: Path) -> dict:
        """解析源文件。"""

    @abstractmethod
    def _validate_parsed(self, data: dict) -> bool:
        """校验解析后的数据。"""

    @abstractmethod
    def _persist_data(self, month: str, data: dict) -> dict[str, int]:
        """幂等落盘。返回 {table: row_count}。"""
```

**子类实现清单**：

| 子导入器 | 模块 | source_type | 源格式 |
|---|---|---|---|
| UnifiedRevenueImporter | revenue | "xlsx_revenue" | 确收对比表 xlsx |
| ONESIntegrationImporter | integration | "ones_csv" | 签约/POC/异常 CSV |
| TimesheetImporter | integration | "timesheet_xlsx" | 工时表 xlsx |
| ContractOCRImporter | contract_management | "contract_pdf" | 合同扫描件 PDF/图片 |
| FinanceImporter | integration | "finance_xlsx" | 财务报表 xlsx |

---

## 4. 核心数据流

### 4.1 幂等生成骨架（BaseService.generate）

```
generate(month, mode)
  │
  ├─ create_job(conn, module, month, mode) → job_id
  │
  ├─ [钩子] _on_job_start(job_id, month, mode)
  │
  ├─ 判断 action：
  │   ├─ mode=read → action=read（必须 has_data）
  │   ├─ mode=regenerate → action=generated
  │   └─ mode=auto → has_data ? read : generated
  │
  ├─ action=read → _load_existing(month) → data
  │   └─ _count_rows(data) → sheets count
  │
  ├─ action=generated → engine.compute(month) → data
  │   └─ engine.persist(month, data, overwrite) → sheets count
  │
  ├─ register_month(conn, module, month, row_counts)
  │
  ├─ [钩子] _on_job_finish(job_id, result)
  │
  └─ _finish_job(job_id, "done", 100, message) → result dict
       └─ 异常时 _finish_job(job_id, "failed", 0, error)
```

**Job 生命周期**：

| 状态 | 触发条件 | 终态 |
|---|---|---|
| pending | create_job | running |
| running | 开始执行 compute/load | done/failed |
| done | 成功完成 | ✓ |
| failed | 异常 | ✓ |

### 4.2 Excel 导出流程

```
export(month, out_path)
  │
  ├─ get_connection(db_path) → conn
  ├─ Workbook() → wb
  ├─ remove default sheet
  │
  ├─ _write_all_sheets(wb, month, conn)  ← 子类实现
  │   ├─ 遍历 sheet_order
  │   ├─ 每个 sheet：load data → _write_header_row → _write_dataframe
  │   └─ 应用样式常量（HEADER_FONT, BORDER 等）
  │
  ├─ target = out_path OR OUTPUT_DIR / f"{module_name}_{month}.xlsx"
  ├─ wb.save(target)
  └─ return target
```

### 4.3 数据导入流程

```
import_all(source_path, month)
  │
  ├─ validate_source(source_path) → bool
  │   └─ 不可读 → raise FileNotFoundError
  │
  ├─ _parse_source(source_path) → data  ← 子类实现
  │
  ├─ _validate_parsed(data) → bool  ← 子类实现
  │   └─ 不合法 → raise ValueError
  │
  ├─ _persist_data(month, data) → counts  ← 子类实现
  │   └─ 幂等：INSERT OR REPLACE + 唯一约束
  │
  ├─ register_month(conn, module, month, row_counts=counts)
  │
  ├─ import_log(source_type, row_count, status="done")
  │
  └─ return {"month", "source_type", "sheets": counts, "total_rows"}
```

---

## 5. 数据模型

Base 层本身不引入新表，但定义了模块表设计的通用规范：

### 5.1 表前缀规范

| 前缀 | 模块 | 示例表 |
|---|---|---|
| `dr_` | delivery_report | dr_sheet_row, dr_sheet_meta |
| `rr_` | revenue | rr_sheet_row, rr_sheet_meta |
| `cr_` | contract_management | cr_contract, cr_risk_item |
| `as_` | after_sales | as_ticket, as_sla_snapshot |
| `pm_` | project_management | pm_project, pm_project_scope |
| `ct_` | cost | ct_timesheet, ct_device_usage |
| `rk_` | risk | rk_risk_item, rk_risk_review |
| `st_` | integration | st_staging_* |
| `kb_` | knowledge_base | kb_item, kb_item_embedding |
| `md_` | master_data | md_reference（已有） |
| `sys_` | settings | sys_settings（已有） |
| `job` | core | job（已有） |

### 5.2 宽表行设计规范

报表类数据（dr_sheet_row, rr_sheet_row）遵循：

```sql
CREATE TABLE IF NOT EXISTS {prefix}_sheet_row (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    {month_col} TEXT NOT NULL,           -- YYYYMM
    sheet TEXT NOT NULL,
    row_index INTEGER NOT NULL,
    data TEXT NOT NULL,                  -- JSON
    -- 可选索引列（按需）
    {index_columns},
    UNIQUE({month_col}, sheet, row_index)
);
CREATE INDEX IF NOT EXISTS idx_{prefix}_sheet ON {prefix}_sheet_row({month_col}, sheet);
```

### 5.3 幂等键设计

| 表类型 | 幂等键 | 冲突策略 |
|---|---|---|
| 宽表行 | (month, sheet, row_index) | INSERT OR REPLACE |
| 强类型业务表 | 业务主键（如 contract_id） | INSERT OR REPLACE / ON CONFLICT UPDATE |
| 元数据表 | 唯一约束（如 module+month） | INSERT OR REPLACE |
| staging 表 | (source_id, connector_name, batch_id) | INSERT OR REPLACE |

---

## 6. CLI 命令设计

Base 层不提供独立 CLI，但定义了各模块 CLI 的通用模式：

```bash
bdms <module> <command> [--mode auto|read|regenerate] [--out <path>] [--source <path>]
```

**通用参数**：

| 参数 | 说明 |
|---|---|
| `--mode` | 幂等模式（auto/read/regenerate） |
| `--out` | 输出文件路径（可选，默认 OUTPUT_DIR） |
| `--source` | 源文件路径（导入时使用） |
| `--json` | JSON 输出格式 |

---

## 7. 实现路径

### Step 1：Base 层加固（1 天）

| 步骤 | 产出物 | 验证方式 |
|---|---|---|
| 1.1 完善 base.py（增加 BaseImporter） | base.py v2.0 | import 无报错 |
| 1.2 增加单元测试 | tests/test_base.py | pytest 全通过 |
| 1.3 接入现有 delivery_report/revenue 引擎 | 引擎继承 BaseEngine | 现有测试全通过 |
| 1.4 创建 Base 层使用示例文档 | docs/BASE-USAGE.md | 人工走查 |

### Step 2：现有模块接入 Base（1 天）

| 步骤 | 产出物 | 验证方式 |
|---|---|---|
| 2.1 DeliveryReportService 继承 BaseService | 代码重构 | 现有测试全通过 |
| 2.2 RevenueService 组合 BaseService | 代码重构 | 现有测试全通过 |
| 2.3 DashboardService 接入 BaseService | 代码重构 | 现有测试全通过 |
| 2.4 SettingsService 接入 BaseService | 代码重构 | 现有测试全通过 |

### Step 3：新模块开发时直接复用

各新模块在 Step 1 完成后，直接按 Base 契约实现。

**依赖关系**：

```
Step 1（Base 层）
  ↓
Step 2（现有模块接入）
  ↓
Step 3（新模块复用）← 所有新模块依赖于此
```

**回滚方案**：
- Base 层变更向后兼容（新增方法有默认实现）
- 现有模块接入失败 → 回退到旧版 base.py（git revert）
- 单元测试作为回归守护

---

## 8. 错误处理策略

### 8.1 错误分类

| 错误类型 | 示例 | 处理方式 |
|---|---|---|
| 数据源缺失 | find_ones_file 返回 None | raise FileNotFoundError，提示检查数据源目录 |
| 计算引擎异常 | delivery-center 导入失败 | raise RuntimeError，提示检查依赖安装 |
| DB 写入失败 | SQLite 锁定 | 重试 3 次（指数退避），失败则 _finish_job(failed) |
| 参数校验失败 | 非法 mode | raise ValueError，提示可用模式 |
| 幂等冲突 | 唯一约束违反 | INSERT OR REPLACE（静默覆盖） |
| 导入格式异常 | Excel 列名不匹配 | raise ValueError，提示期望列名 |

### 8.2 Job 失败处理

- 所有异常通过 `_finish_job(job_id, "failed", 0, str(e))` 记录
- BaseService 不捕获异常，向上抛出由 CLI/Web 层处理
- 连续 3 次 failed 的 job 触发告警（由 observability cron 处理）

---

## 9. 预期效果 + 验收标准

### 9.1 预期效果

**功能**：
- 所有业务模块的 Engine/Service/Exporter/Importer 遵循统一接口契约
- 幂等生成骨架（auto/read/regenerate）在所有模块中行为一致
- Excel 导出样式统一（表头、边框、列宽、数字格式）

**性能**：
- Base 层开销 < 1ms/次调用（纯 Python 抽象层）
- Job 生命周期管理不引入额外 DB 写入延迟

**质量**：
- 模块间重复代码减少 ≥ 60%（估算）
- 新模块开发时间缩短 ≥ 50%（复用 Base 骨架）

### 9.2 验收标准

| 类别 | 标准 | 验证方式 |
|---|---|---|
| **功能验收** | BaseEngine/BaseService/BaseExporter/BaseImporter 各 1 个实例通过测试 | pytest |
| **功能验收** | 现有 delivery_report/revenue 模块接入 Base 后，全部已有测试通过 | pytest |
| **数据验收** | 接入前后，202606 黄金基准数据生成结果零差异 | 对比脚本 |
| **性能验收** | generate(month) 单次调用 Base 层耗时 < 1ms | timeit |
| **幂等验收** | 同一 month 连续 generate 3 次，结果完全一致 | 对比 MD5 |
| **错误验收** | 数据源缺失/参数非法/DB 锁定 → 异常信息清晰，job 记录为 failed | 手动注入故障 |
| **文档验收** | Base 层使用示例文档完整（覆盖 4 个基类的典型用法） | 人工走查 |

### 9.3 交付验收 7 步法映射

| 步骤 | 本模块映射 |
|---|---|
| 独立审计 | base.py 独立 review（接口契约完整性） |
| 契约对齐 | 4 个基类接口与 v2.1 大纲 §4 完全对齐 |
| 全入口执行 | 现有模块接入后 CLI 全量执行 |
| 黄金基准 | 202606 数据零差异 |
| 幂等测试 | 重复 generate 结果一致 |
| 调用点扫描 | 所有 Service/Engine 继承链检查 |
| 回归锁定 | 接入后现有测试 100% 通过 |

---

## 10. 复用资产映射

| 资产 | 来源 | 复用方式 | 价值 |
|---|---|---|---|
| bdms.core.db | L4 Core | 直接调用 get_connection / save_sheet_rows | ⭐⭐⭐⭐⭐ |
| bdms.core.paths | L4 Core | DATA_DIR / OUTPUT_DIR | ⭐⭐⭐⭐ |
| bdms.core.schemas | L4 Core | DR_SCHEMA / RR_SCHEMA | ⭐⭐⭐⭐ |
| L2 Persistence-006 | L2 | SQLite + Repository（已在 core 实现） | ⭐⭐⭐⭐ |
| 现有 base.py | L4 | 扩展 BaseImporter + 完善现有实现 | ⭐⭐⭐⭐⭐ |

---

## 11 Web UI 规范

### 11.1 为什么 BASE 层不包含 Web UI

Base 层是**纯后端抽象层**，只定义 Service / Engine / Exporter / Importer 的接口契约和通用骨架，不涉及任何 Web 层实现。原因：

1. **职责分离**：Base 层的核心使命是统一后端业务逻辑的接口，Web UI 是表现层，应独立于业务逻辑
2. **多端适配**：同一个 BaseService 可能被 Web / CLI / API / 定时任务四种入口调用，Base 层不应绑定任何一种入口
3. **可测试性**：Base 层无 Web 依赖，纯 Python 单测即可覆盖全部契约
4. **框架中立**：未来如果从 FastAPI 切到 Flask 或其他框架，Base 层无需改动

### 11.2 Web UI 的统一规范（在 Base 层定义，在各模块实现）

Base 层虽不实现 Web UI，但**定义所有模块必须遵守的 Web UI 规范**，确保 8 个模块的前端体验一致。

| 规范项 | 要求 | 实现位置 |
|---|---|---|
| 路由前缀 | `/api/<module>/` 统一 RESTful 风格 | 各模块的 `web/routes.py` |
| 响应格式 | 统一 `{code, message, data, total}` | `core/web_utils.py` 统一封装 |
| 错误码 | 统一错误码表（1xxx=参数, 2xxx=权限, 3xxx=业务, 4xxx=系统, 5xxx=外部） | `core/error_codes.py` |
| 分页参数 | `page` / `page_size` / `sort_by` / `sort_order` | `core/web_utils.py` 分页装饰器 |
| 权限校验 | `@require_role(role)` 装饰器 | `core/auth.py` |
| API 文档 | 自动生成 Swagger/OpenAPI | FastAPI 内置 |
| 前端组件 | 统一组件库（表格/表单/弹窗/详情页） | `web/components/` |
| 布局 | 左侧菜单 + 顶部导航 + 内容区三栏布局 | `web/layouts/` |
| 状态管理 | Pinia（Vue）或 React Context | 统一 store 规范 |
| 样式 | 统一 Design Token（颜色/字号/间距/圆角） | `web/styles/tokens.css` |

### 11.3 BaseWebService（Web 层基类，可选实现）

```python
class BaseWebService:
    """Web 层通用能力基类（各模块 Web 层可选继承）。
    
    提供：分页封装、响应格式化、错误码映射、权限校验、参数校验。
    业务模块的 Web 层继承此类，减少样板代码。
    """
    
    module_name: str = ""
    
    def success_response(self, data=None, message: str = "ok") -> dict:
        return {"code": 0, "message": message, "data": data}
    
    def paginated_response(self, items: list, total: int, 
                          page: int, page_size: int) -> dict:
        return {
            "code": 0,
            "message": "ok",
            "data": {
                "items": items,
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": (total + page_size - 1) // page_size
            }
        }
    
    def error_response(self, code: int, message: str) -> dict:
        return {"code": code, "message": message, "data": None}
```

---

## 12 复用资产治理：统一编写与优化规范

### 12.1 原则：复用 ≠ 直接照搬

现有可复用资产（bdms.core / v1.0 base.py / L2 组件 / L3 框架）**不能直接拿来就用**，必须按照 BDMS v2.1 的整体设计框架统一编写、适配和优化。

**核心理念**：复用是"输入"，不是"输出"。输出必须符合 v2.1 的统一规范。

### 12.2 复用资产的三层适配流程

```
原始资产（v1.0 / L2 / L3 / 第三方）
    │
    ▼
第 1 层：接口对齐
    ├─ 检查是否符合 BaseEngine / BaseService 契约
    ├─ 不符合的 → 写 Adapter 层包装
    └─ 符合的 → 直接继承
    │
    ▼
第 2 层：规范统一
    ├─ 命名规范（模块前缀 / 表前缀 / 方法命名）
    ├─ 错误处理规范（异常类型 + 错误码）
    ├─ 日志规范（结构化日志 + 统一格式）
    ├─ 配置规范（settings 表 + 环境变量）
    └─ 测试规范（pytest + 覆盖率要求）
    │
    ▼
第 3 层：优化增强
    ├─ 性能优化（批处理 / 缓存 / 索引）
    ├─ 可靠性增强（重试 / 降级 / 熔断）
    ├─ 安全加固（输入校验 / 权限控制 / 加密）
    └─ 可观测性（指标 / 日志 / 追踪）
```

### 12.3 现有资产的适配清单

| 资产 | 原始状态 | 适配动作 | 适配后位置 |
|---|---|---|---|
| v1.0 `base.py` BaseEngine | 有 compute/persist/load/has_data 四方法 | 补齐类型注解 + 错误处理规范 + 增加 job 钩子 | `modules/base.py` |
| v1.0 `base.py` BaseService | 有 generate 三模式 | 增加生命周期钩子 + 完善幂等保证 + 错误码映射 | `modules/base.py` |
| v1.0 `base.py` BaseExporter | 有 export + _write_all_sheets | 统一样式常量 + 增加错误处理 + 性能优化 | `modules/base.py` |
| v1.0 `core/db.py` | get_connection / save_sheet_rows | 增加连接池 + 事务封装 + 重试机制 | `core/db.py` |
| v1.0 `core/schemas.py` | DR_SCHEMA / RR_SCHEMA | 补全所有模块 schema + 统一命名规范 | `core/schemas.py` |
| L2 Persistence-006 | Repository 模式文档 | 实现适配层，符合 Base 契约 | `core/repository.py` |
| L3 contract-approval | 纯逻辑核心（状态机/风险/分级） | 写 Adapter，封装为 ContractEngine，符合 BaseEngine 契约 | `modules/contract_management/engine.py` |
| L2 Memory-009 | embedding HTTP 服务 | 封装 EmbeddingProvider，支持降级和重试 | `modules/knowledge_base/embedding.py` |
| L2 OCR-001 | RapidOCR 能力 | 封装 ContractOCRImporter，符合 BaseImporter 契约 | `modules/contract_management/ocr_importer.py` |

### 12.4 适配质量门禁

所有复用资产在进入 v2.1 代码库前，必须通过以下检查：

1. ✅ **接口契约对齐**：符合 BaseEngine / BaseService / BaseExporter / BaseImporter 接口
2. ✅ **命名规范**：表前缀、方法名、变量名符合 BDMS v2.1 规范
3. ✅ **错误处理**：异常类型统一 + 错误码映射 + 日志格式统一
4. ✅ **幂等保证**：有副作用的操作必须幂等
5. ✅ **单元测试**：核心逻辑覆盖率 ≥ 80%
6. ✅ **类型注解**：所有公共方法有完整 type hints
7. ✅ **文档注释**：所有公共类/方法有 docstring

---

## 13 与业界最佳实践的对比与优化空间

### 13.1 对标框架

| 业界框架/模式 | 核心思想 | BDMS 当前做法 | 差距 | 优化建议 |
|---|---|---|---|---|
| **DDD（领域驱动设计）** | 聚合根 + 值对象 + 领域事件 + 仓储 | 有 Service/Engine 分层，但缺显式聚合根和领域事件 | 缺领域建模 | 每个模块定义 1 个聚合根（如 Project / Contract / Ticket），跨模块交互走领域事件 |
| **Clean Architecture** | 依赖倒置，内层不依赖外层 | Base 层不依赖具体实现，但 Service 层直接依赖 DB | 依赖方向基本对，但可更严格 | 引入 Repository Interface，Service 依赖接口而非具体 DB 实现 |
| **Hexagonal（六边形架构）** | 核心逻辑 + Port/Adapter | 有 Adapter 思想（如 L3 适配），但未系统化 | 缺显式 Port 定义 | 每个模块定义入站端口（API/CLI）和出站端口（DB/外部服务） |
| **Saga 模式** | 分布式事务编排 | 跨模块操作（如结项）靠 Service 编排，无补偿机制 | 缺补偿 | 结项等跨模块操作定义 Saga + 补偿步骤，失败时自动回滚 |
| **Outbox Pattern** | 事务性消息发送 | 事件发布与 DB 写入在同一事务？当前不确定 | 可能不一致 | 引入 outbox 表，事件与业务数据同事务写入，后台异步发布 |
| **Circuit Breaker** | 外部依赖失败快速失败 | 有重试，但无熔断 | 缺熔断 | 集成模块的外部连接器增加熔断机制（连续 N 次失败后暂停） |
| **Specification 模式** | 业务规则封装为可组合的规格 | 风险扫描/分级审批硬编码在规则引擎中 | 可组合性差 | 引入 Specification 模式，规则可动态组合和查询 |
| **Value Object** | 值对象不可变、相等性按值 | 金额、日期范围等用基本类型（Decimal/date） | 缺领域概念 | 定义 Money / DateRange / Status 等值对象 |

### 13.2 系统已有知识库的对标结论

| 知识库条目 | 相关内容 | 已吸收 | 未吸收 |
|---|---|---|---|
| ADR-006 持久化适配 | SQLite → SQLAlchemy → PostgreSQL 演进路径 | ✅ 用了 SQLite + Repository 思想 | ⚠️ 未预留 SQLAlchemy 迁移路径 |
| ADR-009 记忆语义检索 | 本地 GGUF embedding + FTS5 | ✅ KB 模块用了同样方案 | ✅ 完整吸收 |
| ADR-016 Office 文档生成 | openpyxl + python-docx | ✅ Exporter 用 openpyxl | ✅ 完整吸收 |
| ADR-018 合同审批 | 分级审批 + 风险扫描 + 审计追踪 | ✅ Contract 模块完整继承 | ✅ 完整吸收 |
| EXP-018 PPT 能力调研 | 表格/流程图/高级形状 | ⚠️ 未涉及（非核心能力） | N/A |
| 交付验收 7 步法 | 独立审计/契约对齐/黄金基准/幂等测试等 | ✅ 各模块验收标准映射了 7 步法 | ✅ 完整吸收 |

### 13.3 建议的优化项（按优先级）

#### P0（v2.1 必须做）

1. **Repository Interface（仓储接口）**
   - 问题：Service 层直接依赖 SQLite 实现，未来换 PostgreSQL 成本高
   - 方案：在 Base 层定义 `BaseRepository` 接口，各模块实现具体仓储，Service 依赖接口
   - 成本：低（每个模块 +1 个接口文件）
   - 收益：高（数据库切换成本从"重写"降到"新增实现"）

2. **领域事件 + Outbox**
   - 问题：跨模块数据一致性依赖事件总线，但事件发布与 DB 写入不同事务
   - 方案：引入 outbox 表，事件与业务数据同事务写入，后台 worker 异步发布
   - 成本：中（+ outbox 表 + 发布 worker）
   - 收益：高（彻底解决跨模块数据不一致）

#### P1（v2.2 可做）

3. **聚合根 + 值对象**
   - 问题：当前 Service 层偏贫血模型，业务逻辑分散
   - 方案：核心模块定义聚合根（Project / Contract / Ticket），封装业务规则
   - 成本：中（重构 Service 层）
   - 收益：中（代码更内聚，业务规则集中）

4. **Saga + 补偿**
   - 问题：结项等跨模块操作失败时，部分已执行的步骤无法回滚
   - 方案：定义 Saga 编排器 + 每步补偿动作
   - 成本：中高 | 收益：中（极端场景才触发）

#### P2（远期）

5. **Specification 模式**
   - 问题：风险扫描/权限判断等规则硬编码，难以动态组合
   - 方案：引入 Specification 模式，规则可组合、可序列化
   - 成本：高 | 收益：低（当前规则量不大，硬编码够用）

6. **Circuit Breaker（熔断器）**
   - 问题：集成模块的外部连接器失败时持续重试，可能雪崩
   - 方案：外部连接器增加熔断器（连续 N 次失败后暂停 M 分钟）
   - 成本：低（integration 模块加个装饰器）
   - 收益：中（提高系统稳定性）

---

## 14 AI Token 消耗标记规范

### 14.1 原则：代码实现优先，大模型仅在必要时使用

BDMS 是**纯代码实现的业务系统**，核心逻辑（计算/状态机/报表/CRUD）必须 100% 由代码完成。大模型仅在语义理解、自然语言交互、智能推荐等场景下作为可选增强能力使用。

### 14.2 Token 消耗标记规则

每个系统功能必须明确标记是否消耗大模型 Token：

| 标记 | 含义 | 典型场景 |
|---|---|---|
| 🔒 **NO_TOKEN** | 纯代码逻辑，零 Token 消耗 | CRUD / 状态机 / 报表计算 / Excel 导出 / 数据导入 |
| ⚡ **OPTIONAL_TOKEN** | 可选使用大模型，不用也能工作（降级为纯规则） | 智能搜索 / 自动摘要 / 推荐 / 辅助生成 |
| 🔥 **REQUIRED_TOKEN** | 必须使用大模型，无模型则功能不可用 | OCR 智能提取 / 自然语言查询 / 智能问答 |

### 14.3 BDMS v2.1 各模块 Token 消耗标记

| 模块 | 主要功能 | Token 标记 | 说明 |
|---|---|---|---|
| **BASE** | 基类/骨架/通用工具 | 🔒 NO_TOKEN | 纯抽象层，零 AI 依赖 |
| **DATA-MODEL** | 表结构/索引/关系 | 🔒 NO_TOKEN | 纯数据定义 |
| **DELIVERY-REPORT** | 月报计算/Excel 导出 | 🔒 NO_TOKEN | 纯计算 + 导出 |
| **PROJECT-MANAGEMENT** | 项目全生命周期/成本/风险 | 🔒 NO_TOKEN | 状态机 + CRUD + 计算 |
| **CONTRACT-MANAGEMENT** | 合同审批/风险扫描/文档生成 | ⚡ OPTIONAL_TOKEN | OCR 智能提取用 AI；纯规则风险扫描不用 |
| **AFTER-SALES** | 工单/SLA/售后移交 | ⚡ OPTIONAL_TOKEN | FAQ 智能推荐用 AI；工单流转纯代码 |
| **INTEGRATION** | 外部数据接入/标准化 | 🔒 NO_TOKEN | 纯数据搬运 + 格式转换 |
| **KNOWLEDGE-BASE** | 混合检索/知识管理 | ⚡ OPTIONAL_TOKEN | 语义检索用 embedding（轻量）；纯全文检索也能用 |
| **DASHBOARD** | 数据聚合/可视化 | 🔒 NO_TOKEN | 纯 SQL 聚合 + 图表渲染 |

### 14.4 详细 Token 消耗清单

| 功能点 | 所属模块 | 标记 | 单次消耗估算 | 触发频率 |
|---|---|---|---|---|
| 知识语义检索 | KB | ⚡ OPTIONAL | ~200 tokens（embedding） | 高（每次搜索） |
| OCR 字段提取 | Contract | ⚡ OPTIONAL | ~2000 tokens | 中（每份合同 1 次） |
| FAQ 智能推荐 | After-sales | ⚡ OPTIONAL | ~500 tokens | 中（每次工单创建） |
| 知识自动摘要 | KB | ⚡ OPTIONAL | ~1000 tokens | 低（知识创建时 1 次） |
| 自然语言查询 | Dashboard | 🔥 REQUIRED | ~3000 tokens | 低（可选高级功能） |
| 风险智能评估 | Project/Risk | ⚡ OPTIONAL | ~1500 tokens | 低（每次风险上报） |

> **注**：embedding 模型（768 维 GGUF）本地运行，**不消耗云端 Token**，仅占用本地计算资源。上表中的 token 估算仅针对云端 LLM 调用。

### 14.5 Token 成本治理

1. **默认关闭可选 AI 功能**：所有 OPTIONAL_TOKEN 功能默认关闭，需管理员显式开启
2. **用量上限**：每个功能设置每日/每月 Token 用量上限，超限自动降级
3. **降级策略**：AI 功能不可用时，自动降级为纯规则/纯检索模式，不阻塞主流程
4. **可观测**：所有 AI 调用记录到 `ai_usage_log` 表，包含功能点、消耗 tokens、费用、耗时、成功率
5. **预算告警**：月度消耗达到预算的 80% 时告警，达到 100% 时自动关闭非核心 AI 功能

---

## 15 非功能设计

### 15.1 性能

| 场景 | 目标 | 手段 |
| ---|---|---|
| BaseService.generate() 调用 | < 1ms 额外开销 | 纯 Python 抽象层，无 IO |
| BaseExporter.export() | < 3s（15 Sheet） | 批量写入 + openpyxl 优化 |
| BaseImporter.import_all() | < 5s（1000 行） | 事务批量插入 |

### 15.2 可靠性

- **向后兼容**：所有新增方法有默认实现，不破坏现有子类
- **异常传递**：Base 层不吞异常，向上抛出由 CLI/Web 层处理
- **Job 失败记录**：所有异常通过 `_finish_job(failed)` 持久化
- **幂等保证**：INSERT OR REPLACE + 唯一约束，重复调用安全

### 15.3 安全

- **SQL 注入防护**：所有 DB 操作使用参数化查询
- **文件导入校验**：BaseImporter 校验源文件可读性 + 解析后校验
- **字段加密**：敏感字段由子类负责加密，Base 层提供加密工具函数

### 15.4 可测试性

- **基类可独立测试**：4 个基类各有 mock 子类 + 单元测试
- **集成测试覆盖**：现有 delivery_report/revenue 接入后全量回归
- **契约测试**：子类必须实现所有 abstractmethod，否则实例化失败

---

## 16 风险与权衡

| 风险 | 影响 | 缓解措施 |
| ---|---|---|
| Base 层接口变更 | 所有子类需适配 | 语义化版本 + 弃用周期 + 双版本并行 |
| 抽象过度 | 子类样板代码增多 | 提供代码生成模板 + 文档示例 |
| 性能瓶颈（多模块共享 Base） | 所有模块依赖同一抽象层 | Base 层纯 Python 逻辑，无 IO 竞争 |
| 现有模块接入成本高 | 接入时需修改现有代码 | 兼容层适配 + 渐进式迁移 + 回归测试守护 |
| 子类实现不一致 | 接口契约形同虚设 | 抽象方法强制 + CI 接口合规检查 |

---

## 变更历史

- 2026-09-19: v2.1 Detail 初版（Base 层详细设计）
- 2026-09-19: 补全非功能设计 + 风险与权衡
