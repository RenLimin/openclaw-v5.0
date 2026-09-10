# 银行流水导入模块

FIN-L4 银行流水自动导入引擎 — 支持多种银行/支付格式，自动识别、智能分类、零重复导入。

## 功能特性

- 🏦 **4 种银行/支付格式**：招商银行 / 工商银行 / 支付宝 / 微信支付
- 📄 **双格式支持**：CSV（多编码/多分隔符自动检测）+ Excel（.xlsx）
- 🎯 **自动识别银行**：根据表头自动匹配银行模板，无需手动选择
- 🧠 **智能分类**：21 条内置规则 + 用户自定义规则 + 反馈学习，三级置信度
- 🆔 **自动去重**：基于交易哈希的唯一索引，重复导入 0 新增
- 🔍 **预览 + 确认**：两阶段导入，确认前可调整分类
- ⚙️ **YAML 驱动**：银行模板和分类规则全部可配置，零代码扩展

## 目录结构

```
services/importer/
├── __init__.py              # 对外导出
├── parser.py                # 流水解析引擎
├── classifier.py            # 智能分类引擎
├── importer_service.py      # 导入服务（整合解析+分类+去重+入库）
├── bank_templates/          # 银行模板（YAML）
│   ├── cmb.yaml             # 招商银行
│   ├── icbc.yaml            # 工商银行
│   ├── alipay.yaml          # 支付宝
│   └── wechat.yaml          # 微信支付
├── classification_rules/    # 分类规则（YAML）
│   └── default_rules.yaml   # 内置规则（21 条）
└── docs/                    # 文档
    ├── bank-formats.md      # 银行格式清单
    ├── custom-template.md   # 自定义银行模板指南
    └── classification-rules.md  # 分类规则编写指南
```

## 快速开始

### CLI 方式

```bash
# 预览导入（不入库）
finctl imp preview path/to/statement.csv

# 直接导入
finctl imp import path/to/statement.csv --bank cmb

# 查看导入历史
finctl imp list

# 确认待确认批次
finctl imp confirm <batch_id>

# 查看银行模板
finctl rules banks

# 查看分类规则
finctl rules list

# 添加自定义分类规则
finctl rules add --name "网购" --keywords "淘宝,天猫,京东" --category cat_shopping
```

### Python API 方式

```python
from fin_l4.services.importer import TransactionImporter
from fin_l4.db import init_db

conn = init_db("/path/to/fin_l4.db")
importer = TransactionImporter(conn)

# 预览
result = importer.preview_import("default", "statement.csv", source_type="auto")
print(f"新增 {result.new_count} 条 / 重复 {result.duplicate_count} 条")

# 确认导入
confirmed = importer.confirm_import(result.import_id, "default")
```

### Web UI 方式

启动 Web 服务后，访问 `/import` 页面：

1. 拖拽或选择银行流水文件上传
2. 自动识别银行格式并预览结果
3. 调整低置信度交易的分类
4. 点击"确认导入"完成

## 置信度等级

| 等级 | 阈值 | 行为 |
|------|------|------|
| **high** | score ≥ 80 | 自动确认分类，无需人工干预 |
| **medium** | 50 ≤ score < 80 | 建议确认，高亮显示 |
| **low** | score < 50 | 必须人工确认才能入库 |

## 去重机制

每条交易生成唯一哈希（SHA-256），基于以下字段：
- 交易日期 + 交易时间
- 金额（精确到分）
- 收支方向
- 对方账户/户名
- 摘要/备注

`fin4_transactions` 表上建立 `(family_id, import_hash)` 唯一索引，从数据库层面保证零重复。

## 相关文档

- [银行格式清单](docs/bank-formats.md) — 4 种支持格式的字段详情
- [自定义银行模板指南](docs/custom-template.md) — 添加新银行格式
- [分类规则编写指南](docs/classification-rules.md) — 编写自定义分类规则
