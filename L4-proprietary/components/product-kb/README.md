# Bangcle 产品/服务知识库

L4 专有业务模块，提供 Bangcle 产品知识库，支持合同标的比对、产品知识问答、产品对比等功能。

## 目录结构

```
.
├── docs/               # 设计文档
├── product_kb/         # Python 包
│   ├── __init__.py
│   ├── db.py           # 数据库操作
│   ├── io.py           # 导入/扫描/抽取
│   ├── index.py        # 切片索引构建
│   ├── search.py       # 混合检索
│   ├── contract.py     # 合同比对
│   └── cli.py          # CLI 入口
├── scripts/            # 便捷脚本
│   ├── init_db.sh      # 初始化数据库
│   ├── import_price.sh # 导入价格表
│   ├── scan_docs.sh    # 扫描文档目录
│   └── build_index.sh  # 构建全文和向量索引
├── data/               # 数据库存储（gitignore）
├── tests/              # 测试
└── README.md
```

## 快速开始

### 1. 初始化数据库

```bash
./scripts/init_db.sh
```

### 2. 导入价格表

```bash
./scripts/import_price.sh "/path/to/梆梆_产品价格查询-2026-09-08.xlsx"
```

### 3. 扫描文档目录

```bash
./scripts/scan_docs.sh "/path/to/07. Bangcle Prod/"
```

### 4. 构建索引

```bash
./scripts/build_index.sh [--full]
```

`--full` 用于全量重建，默认增量构建。

### 5. 数据质量检查

```bash
python -m product_kb.cli check
```

### 6. 合同比对

准备 CSV 文件：

```csv
产品名称,型号,数量,单价
全渠道应用安全监测软件V6.0,APP授权扩展年付费许可版,2,90000
...
```

运行：

```bash
python -m product_kb.cli match --input test.csv [--output result.xlsx]
```

### 7. 知识问答查询

```bash
python -m product_kb.cli query "鸿蒙Next SDK加固支持什么版本？"
```

## 设计文档

- [PRD-v1.0.md](docs/PRD-v1.0.md) — 需求文档
- [DESIGN-OUTLINE-v1.0.md](docs/DESIGN-OUTLINE-v1.0.md) — 设计大纲
- [DESIGN-DETAIL-v1.0.md](docs/DESIGN-DETAIL-v1.0.md) — 详细设计
- [VERIFICATION-v1.0.md](docs/VERIFICATION-v1.0.md) — 验证方案
- [OPERATIONS-v1.0.md](docs/OPERATIONS-v1.0.md) — 操作手册
- [IMPLEMENTATION-PLAN-v1.0.md](docs/IMPLEMENTATION-PLAN-v1.0.md) — 开发计划

## 依赖

- Python 3.10+
- `openpyxl` `python-docx` `python-pptx` `PyPDF2`
- 复用现有 L2 组件：持久化 / 记忆检索 / OCR

## 许可证

Copyright (c) 2026 Bangcle
