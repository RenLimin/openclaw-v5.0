# Revenue Recognition — 确收管理模块

## 功能概述

自动化确收报表生成系统。从手工 Excel 报表读取计划确收底稿和预算执行数据，经 SQLite 存储、计算引擎汇总后，生成与手工报表结构一致的自动化 Excel 报表，并提供逐项核对验证。

## 目录结构

```
revenue-recognition/
├── README.md                  # 本文件
├── DESIGN.md                  # 设计文档
├── src/
│   └── revenue_recognition/
│       ├── __init__.py
│       └── v1/
│           ├── __init__.py
│           ├── config.py      # 路径与常量配置
│           ├── db.py          # SQLite 数据库连接与表结构
│           ├── importer.py    # Excel → SQLite 数据导入
│           ├── engine.py      # 计算引擎（汇总/同比/差异）
│           ├── exporter.py    # Excel 报表导出
│           ├── validator.py   # 自动 vs 手工核对
│           ├── main.py        # CLI 主入口
│           └── tests/         # 单元测试
│               ├── conftest.py
│               ├── test_config.py
│               ├── test_db.py
│               ├── test_engine.py
│               ├── test_importer.py
│               ├── test_exporter.py
│               ├── test_validator.py
│               └── test_main.py
└── src/data/
    └── revenue.db             # SQLite 数据文件（运行时生成）
```

## 快速开始

### 环境要求

- Python 3.10+
- openpyxl（Excel 读写）
- pytest（测试）

### 安装依赖

```bash
pip install openpyxl pytest
```

### 运行完整流程

```bash
cd L4-proprietary/components/revenue-recognition
python3 -m revenue_recognition.v1.main
```

### 运行测试

```bash
cd L4-proprietary/components/revenue-recognition
python3 -m pytest src/ -v
```

## CLI 用法

```
python3 -m revenue_recognition.v1.main
```

执行 5 个阶段：
1. **初始化数据库** — 创建 SQLite 表结构
2. **数据导入** — 从手工 Excel 读取到底稿/预算表
3. **计算引擎** — 汇总、月度明细、履约维度
4. **导出报表** — 生成自动化 Excel
5. **核对验证** — 逐项对比自动生成 vs 手工报表

## 输出

- `src/data/revenue.db` — SQLite 数据库
- `src/output/确收自动化报表_{period}.xlsx` — 自动化报表

## 配置

所有路径和列映射常量在 `config.py` 中定义：
- `MANUAL_REPORT_PATH` — 手工报表路径
- `BudgetCol` / `PlanCol` — 列号映射
- `SUMMARY_MONTHS` — 汇总月份列表
