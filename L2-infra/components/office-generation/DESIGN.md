# Office 文档生成组件设计

> L2 基础设施层 · Word/Excel/PPT 文档生成（多库工具链）

## 1. 定位

| 维度 | 值 |
|---|---|
| 层级 | L2 基础设施层 |
| 组件类 | Office 文档生成 |
| 状态 | ✅ 已建设 (2026-08-31) — 持续迭代 |
| 验证 | 工厂测试 6 用例 + smoke test + 各引擎单测 |

## 2. 设计约束

1. **多库工具链**：不绑定单一库，根据场景选择最优工具（python-docx / openpyxl / xlsxwriter / python-pptx / pptxgenjs）。
2. **统一接口**：三种格式 SDK 遵循隐式契约 — `__init__` / `save` / `close` / `format` / `metadata` / `parse` / `to_markdown`。
3. **工厂模式**：`OfficeDocument` 统一入口，按扩展名自动识别格式，延迟加载具体实现类。
4. **双引擎 Excel**：读/改已有文件用 openpyxl，全新写入性能优先用 xlsxwriter（`switch_to_xlsxwriter()` 显式切换）。
5. **中文支持**：所有格式默认 Microsoft YaHei 字体，同时设置 eastAsia 字体（Word/PPT），避免中文显示为方框。
6. **格式转换**：优先 LibreOffice（soffice headless），不可用时抛 `OfficeUnsupportedError`。
7. **异常分层**：`OfficeEngineError` → `OfficeParseError` / `OfficeFormatError` / `OfficeUnsupportedError`。

## 3. 架构

```
┌─────────────────────────────────────────────────────────────┐
│                   OfficeDocument (工厂)                      │
│         create(doc_type)  /  open(path)  /  detect_format    │
├──────────────┬──────────────────┬───────────────────────────┤
│  WordDocument│  ExcelDocument   │  PPTDocument              │
│  (python-docx)│ (openpyxl +      │  (python-pptx)            │
│              │  xlsxwriter)     │                           │
├──────────────┴──────────────────┴───────────────────────────┤
│                   OfficeConverter                            │
│              (LibreOffice soffice headless)                  │
└─────────────────────────────────────────────────────────────┘
```

### 3.1 模块职责

| 模块 | 文件 | 职责 |
|---|---|---|
| factory | `src/office_engine/factory.py` | 统一工厂：`OfficeDocument.create()` / `.open()` / `.detect_format()` |
| word_engine | `src/office_engine/word_engine.py` | Word SDK：基于 python-docx 的程序化构建与解析 |
| excel_engine | `src/office_engine/excel_engine.py` | Excel SDK：openpyxl + xlsxwriter 双引擎，WorksheetProxy 屏蔽差异 |
| ppt_engine | `src/office_engine/ppt_engine.py` | PPT SDK：基于 python-pptx 的统一封装 |
| converter | `src/office_engine/converter.py` | 格式转换：LibreOffice soffice headless → PDF |
| exceptions | `src/office_engine/exceptions.py` | 统一异常类层次 |
| agent-slides | `agent-slides/src/agent_slides/` | 幻灯片 agent 占位（待实现） |
| agent-slides-tool | `agent-slides-tool/src/agent_slides_tool/` | 幻灯片工具 agent 占位（待实现） |

### 3.2 工具链选型（基于 2026-08-31 深度调研）

| 格式 | 主力库 | 备选 | 场景 |
|---|---|---|---|
| Word | python-docx | docxtpl（模板） | 程序化构建主力 |
| Excel | openpyxl | xlsxwriter（大数据写入）+ pandas（快速导出） | 读写 + 格式 + 图表 |
| PPT | pptxgenjs（已有技能） | python-pptx | 高质量 / Python 批量 |

## 4. 核心 API

### 4.1 工厂入口

```python
from office_engine import OfficeDocument

# 按类型创建
doc = OfficeDocument.create("word")   # → WordDocument
xls = OfficeDocument.create("excel")  # → ExcelDocument
ppt = OfficeDocument.create("ppt")    # → PPTDocument

# 按路径打开（自动识别）
doc = OfficeDocument.open("report.pptx")  # → PPTDocument
```

### 4.2 WordDocument（python-docx）

```python
doc = WordDocument()
doc.add_heading("标题", level=1)
doc.add_paragraph("正文", bold=True, align="center")
doc.add_table(rows=3, cols=2, data=[["A","B"],["C","D"]])
doc.add_list(["item1", "item2"], ordered=False)
doc.add_image("photo.png", width=5.0)
doc.set_header("页眉")
doc.set_footer("页脚", page_number=True)
doc.find_replace("{{name}}", "Rex")
parsed = doc.parse()       # → 结构化 JSON
md = doc.to_markdown()    # → Markdown
doc.save("output.docx")
```

### 4.3 ExcelDocument（openpyxl + xlsxwriter 双引擎）

```python
doc = ExcelDocument()
ws = doc.get_sheet("Sheet1")
doc.set_cell(ws, "A1", "值", font={"bold": True}, fill={"color":"FFFF00"})
doc.set_row(ws, 1, ["列1","列2","列3"], header=True)
doc.add_table(ws, "A1:C10", data)
doc.add_chart(ws, "column", "图表标题", "B1:B10", "A1:A10")
doc.add_conditional_format(ws, "A1:A10", "cell_is", {"operator":"greaterThan","value":100})
doc.set_formula(ws, "C1", "=SUM(A1:B1)")
doc.freeze_panes(ws, "A2")
doc.merge_cells(ws, "A1:C1")

# 切换到 xlsxwriter（性能模式，仅全新写入）
doc.switch_to_xlsxwriter()

# DataFrame 快速导出
ExcelDocument.from_dataframe(df, "output.xlsx")
```

### 4.4 PPTDocument（python-pptx）

```python
ppt = PPTDocument()
slide = ppt.add_slide("title_content")
ppt.set_slide_title(slide, "标题")
ppt.add_text_box(slide, 1, 2, 8, 4, "正文内容", font_size=18)
ppt.add_table(slide, 1, 1, 8, 6, rows=3, cols=2, data=data)
ppt.add_chart(slide, 1, 1, 8, 4, "column", {"系列1":[1,2,3]}, ["A","B","C"])
ppt.add_image(slide, "photo.png", 1, 1, w=5, h=3)
ppt.add_notes(slide, "备注内容")
ppt.find_replace("{{year}}", "2026")
ppt.duplicate_slide(0)
ppt.delete_slide(1)
parsed = ppt.parse()
md = ppt.to_markdown()
ppt.save("output.pptx")
```

### 4.5 OfficeConverter（LibreOffice）

```python
from office_engine import OfficeConverter

if OfficeConverter.is_available():
    OfficeConverter.to_pdf("report.docx", "report.pdf")
```

## 5. 关键设计细节

### 5.1 Excel 双引擎策略

| 场景 | 引擎 | 原因 |
|---|---|---|
| 读/改已有文件 | openpyxl | 唯一支持读写的库 |
| 全新写入 + 大数据量 | xlsxwriter | 10000 行 × 4 列 = 0.05s |
| DataFrame 快速导出 | pandas + openpyxl | `df.to_excel()` 一行代码 |

引擎切换通过 `switch_to_xlsxwriter()` 显式调用，切换后 openpyxl 数据丢失（设计约束）。`WorksheetProxy` 代理对象屏蔽底层引擎差异。

### 5.2 中文字体处理

- **Word**：同时设置 `run.font.name` + `rPr.rFonts.set(qn('w:eastAsia'), 'Microsoft YaHei')`
- **PPT**：同时设置 `run.font.name` + `a:ea typeface='Microsoft YaHei'`
- **Excel**：通过 font dict 设置 `name: 'Microsoft YaHei'`

### 5.3 已知限制

| 限制 | 影响 | Workaround |
|---|---|---|
| xlsxwriter 只写不改 | 无法修改已有 Excel | 用 openpyxl |
| openpyxl number_format | 不支持关键字参数 | 单独赋值 `cell.number_format` |
| python-pptx 布局繁琐 | 每个元素需手动计算坐标 | 封装布局函数或转 pptxgenjs |
| docxtpl 表格行循环 bug | 模板无法动态生成表格行 | 用 python-docx 手动构建 |
| LibreOffice 不可用 | PDF 转换失败 | 安装 LibreOffice 或转用其他方案 |

## 6. 存储格式

| 路径 | 说明 |
|---|---|
| `src/office_engine/` | 核心 SDK 源码 |
| `research/` | 深度调研报告 + 样本文件 |
| `tests/` | 测试用例 + 输出样本 |
| `tests/output/` | 测试生成的文档（gitignore） |

## 7. 依赖

| 依赖 | 类型 | 说明 |
|---|---|---|
| python-docx | pip | Word 文档构建 |
| openpyxl | pip | Excel 读写 |
| xlsxwriter | pip | Excel 高性能写入 |
| pandas | pip | DataFrame 快速导出（可选） |
| python-pptx | pip | PPT 构建 |
| LibreOffice (soffice) | 系统包 | PDF 转换（可选） |
| pptxgenjs | npm | 高质量 PPT（已有 pptxgenjs-pro 技能，独立于本组件） |

## 8. 演进方向

| 方向 | 优先级 | 触发条件 |
|---|---|---|
| 数据→文档管线 | 高 | 需要统一 JSON 输入驱动三格式输出 |
| 模板库积累 | 中 | docxtpl 模板管理（段落循环场景） |
| agent-slides 实现 | 低 | 占位模块，待需求明确 |
| 布局封装函数 | 中 | PPT 手动坐标计算过于繁琐 |
| 三格式联动 | 低 | 同一份数据 → Word + Excel + PPT |

## 9. 验证

- **工厂测试**：`tests/test_factory.py` — 6 用例（按类型创建、按路径打开、格式识别、异常路径）
- **引擎测试**：`tests/test_word_engine.py` / `test_excel_engine.py` / `test_ppt_engine.py` / `test_converter.py`
- **smoke test**：`tests/test_smoke.py` — 验证目录结构和 Python 文件存在
- **样本验证**：`research/` 下含各库实测输出样本（docx/xlsx/pptx）

## 10. 变更记录

| 日期 | 变更 |
|---|---|
| 2026-08-31 | 深度调研报告完成（7 库实测，能力矩阵 + 选型建议） |
| 2026-08-31 | Office Engine v2 首版（统一 SDK + 工厂模式） |
| 2026-08-31 | Excel 双引擎实现（openpyxl + xlsxwriter） |
| 2026-08-31 | PPT SDK 首版（python-pptx 封装） |
| 2026-08-31 | 格式转换模块首版（LibreOffice soffice headless） |
