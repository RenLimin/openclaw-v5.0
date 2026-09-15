# BDMS 模块契约（并行建设用）

> 版本：v1.0（2026-09-15）
> 用途：多会话并行建设时的接口约定，避免返工

## 1. 目录与文件边界

```
L4-proprietary/components/bdms/src/bdms/
├── core/                      [已完成，勿改]
│   ├── db.py                  统一 DB（get_connection / save_sheet_rows / ...）
│   ├── paths.py               路径解析
│   ├── schemas.py             业务表 schema
│   └── header_mapper.py       表头自适应
├── modules/
│   ├── delivery_report/       [模块1 已完成] engine.py / service.py / exporter.py
│   ├── revenue/               [模块2 已完成] engine.py / importer.py / summary_engine.py
│   ├── master_data/           [模块3 ← Agent A]
│   ├── dashboard/             [模块4 ← Agent B]
│   └── settings/              [模块5 ← Agent A]
├── web/                       [主会话建设]
└── cli/                       [主会话建设]
```

## 2. 模块统一接口契约

每个模块的 `service.py` 必须暴露：

```python
class XxxService:
    def __init__(self, db_path: Optional[Path] = None): ...

    # 查询类
    def list_xxx(self, **filters) -> list[dict]: ...
    def get_xxx(self, key) -> dict | None: ...

    # 变更类（写操作，返回结果 dict）
    def create_xxx(self, **data) -> dict: ...
    def update_xxx(self, key, **data) -> dict: ...
    def delete_xxx(self, key) -> dict: ...
```

每个 `engine.py` 必须**纯计算/纯查询，无副作用**。

## 3. 数据层约定

### 3.1 已建表（core/schemas.py）

| 表 | 用途 | 归属 |
|---|---|---|
| `md_reference` | 图例/参考数据（data_type, code, label, extra, sort_order, enabled） | 模块3 |
| `sys_settings` | 系统设置（key, value, description） | 模块5 |
| `db_snapshot` | 看板聚合快照（month, metric, dimension, value, extra） | 模块4 |
| `dr_sheet_row` / `dr_sheet_meta` | 交付月报 Sheet 数据 | 模块1 |
| `rr_sheet_row` / `rr_sheet_meta` | 确收 Sheet 数据 | 模块2 |
| `job` / `report_month` / `import_log` | 元数据 | core |

### 3.2 DB 访问

```python
from ...core import db as _db

conn = _db.get_connection(self.db_path)   # 自动 row_factory
try:
    rows = conn.execute("SELECT ...").fetchall()
    conn.commit()          # 写操作必须 commit
finally:
    conn.close()
```

### 3.3 系统设置默认键（模块5）

```python
from ...core.db import DEFAULT_SETTINGS
# view.default_months_back   默认显示数据跨度（月）
# view.default_month         默认选中月份
# view.available_months      可选月份列表
# report.auto_overwrite      自动覆盖
# report.excel_output_dir    Excel 输出目录
```

## 4. 数据源参考（只读）

| 数据 | 路径 |
|---|---|
| ONES 导出 CSV | `~/.openclaw/data/ones_exports/` |
| 团队报告（按月） | `/Users/bangcle/Bangcle Workspace/01. Management/2026/2026团队报告/{YYYYMM}/` |
| 图例来源 | 手工报表「图例」sheet（506 行 × 16 列） |

用 `bdms.core.paths` 里的函数获取，不要硬编码。

## 5. 代码规范

- Python 3.10+，类型注解
- 相对导入：`from ...core import db as _db`（三级）
- 中文注释，中英混合命名（变量英文、注释中文）
- 每个模块写 `tests/test_<module>.py`
- **禁止**修改 core/ 和已完成的模块1/2

## 6. 验证要求

每个模块交付前必须：
1. `python3 -c "import py_compile; py_compile.compile('文件路径', doraise=True)"` 语法通过
2. 写一个可执行的验证脚本证明功能可用（真实数据，非 mock）
3. 输出验证结果（不是"应该可以"，要有实际运行输出）

## 7. 环境

```bash
cd /Users/bangcle/.openclaw/workspace/L4-proprietary/components/bdms
export PYTHONPATH=src
```
