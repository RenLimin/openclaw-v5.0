# DESIGN-DETAIL-v1.0.md — 收入确认自动化模块

## 1. 模块详细设计

### 1.1 config.py

常量配置模块：
- 路径：`MANUAL_REPORT_PATH`（手工报表路径）、`DATA_DIR`、`OUTPUT_DIR`、`DB_PATH`
- Sheet 名称：`SHEET_PLAN_DRAFT`、`SHEET_BUDGET_EXEC`、`SHEET_SUMMARY`、`SHEET_MONTHLY_RECORD`、`SHEET_PERFORMANCE_RECORD`、`SHEET_VARIANCE`、`SHEET_TREND`、`SHEET_LEGEND`、`SHEET_REBUILD_PERF`
- 列映射：`BudgetCol` 枚举（预算执行表列）、`PlanCol` 枚举（确收底稿表列）
- 其他：`SUMMARY_MONTHS`（汇总月份列表）

### 1.2 db.py

数据库连接与初始化：
- `get_connection()`：获取数据库连接，配置 WAL 模式、外键开启、行工厂为字典
- `init_db()`：初始化表结构，创建 plan_draft 和 budget_exec 表，添加索引；幂等操作，重复执行不报错
- 表结构：
  - plan_draft：存储确收底稿明细，字段包括 contract_no, perf_id, rev_method, note, contract_amount, perf_amount
  - budget_exec：存储预算执行明细，字段包括 category, contract_no, month_range, rev_method, actual_range, perf_amount

### 1.3 importer.py

Excel → SQLite 导入：
- `SafeFloat`：安全转换单元格数值为 float，处理空值、字符串、逗号千分位
- `SafeStr`：安全转换单元格为字符串，处理空值、空白
- `import_plan_draft()`：导入确收底稿，清空旧数据，逐行读取导入
- `import_budget_exec()`：导入预算执行数据，清空旧数据，逐行读取导入
- `import_all()`：批量导入两个 Sheet

### 1.4 engine.py

确收计算引擎：
- `RevenueEngine`：主类，持有数据库连接
- `compute_summary(period)`：按期间×分类聚合新签和递延确收，返回字典
- `compute_monthly_detail(period)`：计算月度明细，每条含期间、合同期间、新签确收、递延确收、总计
- `compute_performance_summary(period)`：计算履约维度汇总，返回新签、递延、总计三个部分
- `compute_rebuild_perf()`：计算重拆履约，返回每个合同的提前/滞后数据

### 1.5 exporter.py

Excel 报表导出：
- `RevenueExporter`：主类，持有计算引擎引用
- `export(period, output_path)`：执行导出，创建所有 Sheet 并写入数据，返回输出文件路径
- 导出 Sheet：
  - Summary：确收汇总表
  - Monthly Record：月度汇总记录
  - Performance Record：履约汇总记录
  - Variance Analysis：确收差异分析
  - Rebuild Perf：重拆履约
  - Legend：图例
- 样式：使用与手工报表一致的字体、填充、边框

### 1.6 validator.py

结果验证：
- `ValidationReport`：验证报告数据类，包含 sheet 名称、总单元格数、匹配数、不匹配数、差异列表、是否通过
- `CellDiff`：单元格差异数据类，包含位置、自动值、手工值
- `validate_summary_sheet()`：验证单个 Sheet，返回验证报告
- `validate_all_sheets()`：验证所有 Sheet，汇总所有差异
- `_values_equal()`：数值比较，容忍 0.01 差异，空值与零等价，跳过 #REF 错误

### 1.7 main.py

流程编排：
- `main()`：依次执行初始化数据库、数据导入、计算所有结果、导出报表、验证结果，输出验证报告

## 2. 数据流

```
手工 Excel 报表
    ↓
importer 读取并清洗数据
    ↓
SQLite 持久化存储 plan_draft / budget_exec
    ↓
engine 计算各类汇总
    ↓
exporter 生成 Excel 自动化报表
    ↓
validator 对比自动化报表 vs 手工报表，输出差异报告
```

## 3. 数据模型

| 表 | 字段 | 类型 | 说明 |
|---|----|------|------|
| plan_draft | contract_no | TEXT | 合同编号 |
| | perf_id | TEXT | 履约ID |
| | rev_method | TEXT | 确收方式 |
| | note | TEXT | 备注 |
| | contract_amount | REAL | 合同金额 |
| | perf_amount | REAL | 履约金额 |
| budget_exec | category | TEXT | 分类 |
| | contract_no | TEXT | 合同编号 |
| | month_range | TEXT | 月份范围 |
| | rev_method | TEXT | 确收方式 |
| | actual_range | TEXT | 实际执行范围 |
| | perf_amount | REAL | 金额 |

## 4. 接口契约

```python
# engine
class RevenueEngine:
    def compute_summary(period: str) -> dict: ...
    def compute_monthly_detail(period: str) -> list[dict]: ...
    def compute_performance_summary(period: str) -> dict: ...
    def compute_rebuild_perf() -> list[dict]: ...

# exporter
class RevenueExporter:
    def export(period: str, output_path: Path) -> Path: ...

# validator
@dataclass
class ValidationReport:
    sheet_name: str
    total_cells: int
    matched_cells: int
    mismatched_cells: int
    diffs: list[CellDiff]
    is_passed: bool

@dataclass
class CellDiff:
    cell: str
    auto: Any
    manual: Any
