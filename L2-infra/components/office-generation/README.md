# office-generation

**定位：** L2 基础设施层 — Office 文档（Word/Excel/PPT）程序化生成引擎。

## 功能列表

- Word 文档引擎（段落、表格、样式、列表、查找替换）
- Excel 引擎（单元格、公式、图表、合并、冻结、多 Sheet）
- PPT 引擎（幻灯片、文本框、表格、图表、备注、中文支持）
- 统一工厂入口（`factory.py`，按文件类型分发）
- Markdown → Office 转换（converter.py）
- 多引擎适配（xlsxwriter、pandas、openpyxl）
- 测试覆盖（工厂测试 + 大量输出验证）

## 目录结构

```
office-generation/
├── src/office_engine/
│   ├── __init__.py
│   ├── factory.py           # 统一工厂入口
│   ├── word_engine.py       # Word 引擎
│   ├── excel_engine.py      # Excel 引擎
│   ├── ppt_engine.py        # PPT 引擎
│   ├── converter.py         # Markdown → Office 转换
│   └── exceptions.py        # 异常定义
├── agent-slides/            # Agent Slides 适配包
├── agent-slides-tool/       # Agent Slides Tool 适配包
├── research/                # 研究样本与报告
├── tests/
│   ├── conftest.py
│   ├── test_factory.py
│   └── output/              # 测试输出文件
└── DESIGN.md
```

## 使用方式

```python
from office_engine.factory import OfficeFactory

# 创建文档
doc = OfficeFactory.create("word", "output.xlsx")
doc = OfficeFactory.create("excel", "output.xlsx")
doc = OfficeFactory.create("ppt", "output.pptx")
```

## 依赖

- python-docx（Word 处理）
- openpyxl / xlsxwriter / pandas（Excel 处理）
- python-pptx（PPT 处理）
- Python 3.10+
