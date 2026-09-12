# Revenue Recognition — 设计文档

## 设计目标

1. **自动化** — 替代手工 Excel 汇总计算，消除人工错误
2. **可验证** — 自动生成结果可与手工报表逐项对比
3. **可追溯** — 原始数据持久化在 SQLite，计算逻辑透明
4. **可扩展** — v1 版本预留多版本演进路径

## 架构决策

### 为什么用 SQLite？

- 零运维，单文件存储
- 支持 SQL 聚合查询，适合确收汇总场景
- WAL 模式支持并发读
- 与 Python 标准库无缝集成

### 为什么分 v1 子包？

- 手工报表结构可能年度变化
- 版本化隔离（v1 → v2）允许平滑迁移
- 测试可以按版本独立运行

### 为什么 mock openpyxl？

- 手工报表文件大、Sheet 多，直接读取慢
- 测试关注逻辑正确性，非 Excel I/O
- mock 让测试快速、确定、CI 友好

## 模块划分

```
┌─────────────┐     ┌──────────┐     ┌─────────────┐     ┌──────────┐
│  importer   │────▶│  SQLite  │────▶│   engine    │────▶│ exporter │
│ (Excel → DB)│     │  (db.py) │     │ (计算汇总)   │     │ (DB → XLSX)│
└─────────────┘     └──────────┘     └─────────────┘     └──────────┘
                                            │
                                            ▼
                                     ┌──────────────┐
                                     │  validator   │
                                     │ (自动 vs 手工) │
                                     └──────────────┘
```

| 模块 | 职责 | 关键函数/类 |
|------|------|------------|
| config.py | 路径、列映射、常量 | `BudgetCol`, `PlanCol`, `SUMMARY_MONTHS` |
| db.py | 连接管理、表结构初始化 | `get_connection()`, `init_db()` |
| importer.py | Excel → SQLite 导入 | `import_plan_draft()`, `import_budget_exec()` |
| engine.py | 汇总计算引擎 | `RevenueEngine.compute_summary()`, `.compute_monthly_detail()`, `.compute_performance_summary()`, `.compute_rebuild_perf()` |
| exporter.py | Excel 报表生成 | `RevenueExporter.export()` |
| validator.py | 差异核对 | `validate_summary_sheet()`, `_values_equal()` |
| main.py | 流程编排 | `main()` |

## 数据流

```
手工 Excel (.xlsx)
    │
    ▼
importer.import_all()
    │
    ├── plan_draft 表  (计划确收底稿明细)
    └── budget_exec 表 (预算执行明细)
    │
    ▼
RevenueEngine
    │
    ├── compute_summary()        → 按期间×分类聚合
    ├── compute_monthly_detail() → 月度明细
    ├── compute_performance_summary() → 履约维度
    └── compute_rebuild_perf()   → 重拆履约
    │
    ▼
RevenueExporter.export()
    │
    └── 确收自动化报表_{period}.xlsx
        ├── 汇总
        ├── 月度汇总记录
        ├── 履约汇总记录
        ├── 确收差异分析
        ├── 重拆履约
        └── 图例
    │
    ▼
validator.validate_all_sheets()
    │
    └── ValidationReport (PASS/FAIL + 差异明细)
```

## 关键接口

### RevenueEngine

```python
class RevenueEngine:
    def compute_summary(period: str) -> dict       # {"new": [...], "deferred": [...]}
    def compute_monthly_detail(period: str) -> list  # [{period, contract_period, ...}]
    def compute_performance_summary(period: str) -> dict  # {"new": {}, "deferred": {}, "total": {}}
    def compute_rebuild_perf() -> list               # [{contract_no, ahead, behind}]
```

### RevenueExporter

```python
class RevenueExporter:
    def export(period: str, output_path: Path) -> Path
```

### ValidationReport

```python
@dataclass
class ValidationReport:
    sheet_name: str
    total_cells: int
    matched_cells: int
    mismatched_cells: int
    diffs: list[CellDiff]
    is_passed: bool
```

## 容错策略

- **数值容差** — 浮点比较使用 `tolerance=0.01`
- **空值处理** — `None` 与 `0` 视为等价
- **#REF 跳过** — Excel 公式错误单元格不参与比对
- **旧数据清理** — 每次导入先 `DELETE` 再 `INSERT`

## 测试策略

- 临时 SQLite 数据库（tempfile），不污染生产数据
- mock openpyxl 依赖，测试逻辑确定性
- 覆盖：配置常量、DB 表结构、计算引擎、导入导出、核对验证、主流程
