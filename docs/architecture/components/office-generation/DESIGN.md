# Office 文档引擎设计 v2

> L2 基础设施层组件 011 — 从 v1 工具链集合演进为统一 SDK。
> 覆盖 Word / Excel / PPT 三大格式的 create / read / update / parse / convert 全生命周期能力。
> 纯技术基础设施，不含业务逻辑。

## 1. 定位

| 维度 | 值 |
|---|---|
| 层级 | L2 基础设施层 |
| 组件 ID | 011 |
| 组件名称 | Office 文档引擎（Office Engine） |
| 状态 | 🚧 v2 升级中（2026-09-07）— v1 已上线（2026-08-31，6/6 库实测通过） |
| 包名 | `office_engine` |
| 形态 | Python 包 + 统一 API + 可选外部依赖（LibreOffice） |
| ADR | ADR-016 v2 |
| 代码 | `L2-infra/components/office-generation/src/` |
| 测试 | `L2-infra/components/office-generation/tests/` |

### v1 → v2 变化

| 维度 | v1（工具链） | v2（统一 SDK） |
|---|---|---|
| 能力 | create（生成） | create / read / update / parse / convert |
| 调用方式 | 业务层自行 import 各库 | `from office_engine import OfficeDocument` |
| 错误处理 | 各库自带异常 | 统一异常体系 |
| 中文支持 | 业务层自行处理 | SDK 内置默认字体 |
| 文档解析 | ❌ | ✅ JSON + Markdown |
| 格式转换 | ❌ | ✅ PDF（可选，LibreOffice） |
| 引擎选择 | 业务层决策 | SDK 内部自动选择 + 手动覆盖 |

## 2. 设计原则

1. **纯技术定位**：只做格式操作，不感知业务含义（合同/报表/方案都一样）。
2. **多引擎协同**：不追求单一库全功能，按场景自动选择最优引擎，对外透明。
3. **统一 API**：Word/Excel/PPT 三套 SDK 接口风格一致，生命周期方法同名。
4. **可选依赖**：PDF 转换等依赖外部工具的能力作为可选模块，不可用时优雅降级。
5. **Escape Hatch**：允许访问原生对象（`.native` 属性），极端场景不被 SDK 限制。
6. **中文友好**：默认 Microsoft YaHei，内置字体 fallback 策略。
7. **可测试**：所有 SDK 方法都有 round-trip 测试（生成 → 解析 → 验证）。

## 3. 架构

```
┌─────────────────────────────────────────────────────────┐
│                    OfficeDocument 工厂                    │
│              OfficeDocument.create() / .open()            │
│              自动识别格式，返回对应 SDK 实例               │
└──────────┬───────────┬───────────┬──────────────────────┘
           │           │           │
┌──────────▼──┐ ┌──────▼──────┐ ┌─▼──────────┐ ┌────────────┐
│ WordDocument│ │ExcelDocument│ │PPTDocument │ │OfficeConv- │
│  (python-   │ │(openpyxl +  │ │(python-    │ │ erter      │
│   docx +    │ │ xlsxwriter +│ │  pptx)     │ │(LibreOffice│
│  docxtpl)   │ │   pandas)   │ │            │ │  可选)     │
└─────────────┘ └─────────────┘ └────────────┘ └────────────┘
           │           │           │                │
┌──────────┴───────────┴───────────┴────────────────┘
│              统一基础设施层                              │
│   异常体系 / 日志 / 字体管理 / 引擎自动选择              │
└───────────────────────────────────────────────────────┘
```

## 4. 统一 API 契约

三套 SDK 共享同一套生命周期方法。

### 4.1 基类接口

```python
class OfficeDocumentBase:
    # —— 生命周期 ——
    def __init__(self, path: str | None = None):
        """path=None 新建文档；path 非空则打开已有文档"""
    
    def save(self, path: str | None = None) -> str:
        """保存文档。path=None 则覆盖原路径，返回最终路径"""
    
    def close(self):
        """释放资源"""
    
    # —— 上下文管理器 ——
    def __enter__(self): ...
    def __exit__(self, *args): ...
    
    # —— 元数据 ——
    @property
    def format(self) -> str:
        """docx / xlsx / pptx"""
    
    @property
    def metadata(self) -> dict:
        """作者 / 标题 / 主题 / 创建时间 / 修改时间"""
    
    # —— 解析 ——
    def parse(self) -> dict:
        """结构化提取为 JSON"""
    
    def to_markdown(self) -> str:
        """转换为 Markdown"""
    
    # —— 原生访问 ——
    @property
    def native(self):
        """Escape hatch：返回底层库的原生对象"""
```

### 4.2 统一异常

```python
class OfficeEngineError(Exception):
    """所有 Office Engine 异常的基类"""
    code: str          # ERR_OFFICE_*
    severity: str      # Sev1 / Sev2 / Sev3 / Sev4
    component: str     # word / excel / ppt / converter / factory

class OfficeParseError(OfficeEngineError):
    """解析失败"""

class OfficeFormatError(OfficeEngineError):
    """格式不支持 / 文件损坏"""

class OfficeUnsupportedError(OfficeEngineError):
    """能力不可用（如 LibreOffice 未安装）"""

class OfficeEngineNotFound(OfficeEngineError):
    """底层引擎（库）未安装"""
```

## 5. Word SDK

**底层引擎**：python-docx（主力） + docxtpl（模板渲染）

### 5.1 Create / Edit

| 方法 | 说明 |
|---|---|
| `add_heading(text, level=1)` | 标题（1-9 级） |
| `add_paragraph(text, style=None, **kwargs)` | 段落，支持 bold/italic/color/font_size/align |
| `add_table(rows, cols, data=None, style="Table Grid", merge=None)` | 表格 + 合并单元格 |
| `add_image(path, width=None, height=None)` | 图片插入 |
| `add_list(items, ordered=False)` | 有序 / 无序列表 |
| `add_page_break()` | 分页符 |
| `set_header(text)` / `set_footer(text, page_number=False)` | 页眉页脚 |
| `set_font_default(font_name, font_size)` | 设置默认字体 |
| `find_replace(find_text, replace_text)` | 全局查找替换 |
| `apply_style(paragraph_or_run, style_name)` | 应用样式 |
| `render_template(data: dict)` | 模板渲染（docxtpl） |

### 5.2 Parse

```python
def parse(self) -> dict:
    return {
        "metadata": {...},
        "sections": [
            {
                "headings": [{"level": 1, "text": "..."}],
                "paragraphs": [{"text": "...", "style": "..."}],
                "tables": [
                    {
                        "rows": 3, "cols": 2,
                        "data": [["A", "B"], ["C", "D"]],
                        "merged_cells": []
                    }
                ],
                "images": [{"index": 0, "type": "png", "size": [w, h]}]
            }
        ]
    }

def to_markdown(self) -> str:
    """标题用 # / ##，段落直接输出，表格用 Markdown 表格，列表用 - 或 1."""
```

### 5.3 中文字体处理

- 默认字体：`Microsoft YaHei`
- 每个 Run 同时设置 `font.name` 和 `rPr.rFonts.set(qn('w:eastAsia'), 'Microsoft YaHei')`
- 字体检测：初始化时检测系统可用字体，按优先级 fallback
  - macOS：PingFang SC → Microsoft YaHei → Heiti SC → Arial
  - Windows：Microsoft YaHei → SimSun → Arial
  - Linux：Noto Sans CJK SC → WenQuanYi Micro Hei → DejaVu Sans

## 6. Excel SDK

**底层引擎**：openpyxl（读写）+ xlsxwriter（纯写入高性能）+ pandas（快速导出）

### 6.1 引擎自动选择逻辑

| 场景 | 引擎 | 理由 |
|---|---|---|
| 打开已有文件 / 需要读 | openpyxl | 唯一支持读写的库 |
| 新建 + 大数据量 + 只写 | xlsxwriter | 性能最优 |
| 新建 + 需要图表 / 复杂条件格式 | xlsxwriter | 样式和图表能力最强 |
| DataFrame 快速导出 | pandas + openpyxl | 一行代码 |
| 不确定 | openpyxl | 最通用 |

对外透明：用户只调 `ExcelDocument`，内部按操作模式自动切换。
手动覆盖：`ExcelDocument(engine="xlsxwriter")` 强制指定。

### 6.2 Create / Edit

| 方法 | 说明 |
|---|---|
| `add_sheet(name, index=None) -> SheetProxy` | 添加 Sheet |
| `get_sheet(name_or_index) -> SheetProxy` | 获取 Sheet |
| `set_cell(sheet, cell_ref, value, **style)` | 写单元格 + 样式 |
| `set_row(sheet, row_num, values, start_col=1, header=False)` | 写一行 |
| `set_column_width(sheet, col_letter, width)` | 列宽 |
| `add_table(sheet, range_str, data, header_style=None)` | 表格写入 |
| `add_chart(sheet, chart_type, title, data_range, cat_range, anchor)` | 图表（柱/饼/折线/条/散点） |
| `add_conditional_format(sheet, range_str, rule_type, options)` | 条件格式 |
| `set_formula(sheet, cell_ref, formula)` | 公式 |
| `freeze_panes(sheet, cell_ref)` | 冻结窗格 |
| `merge_cells(sheet, range_str)` | 合并单元格 |
| `from_dataframe(df, sheet_name="Sheet1")` | DataFrame 导入（pandas） |
| `find_replace(sheet, find_text, replace_text)` | 查找替换 |

### 6.3 Parse

```python
def parse(self) -> dict:
    return {
        "metadata": {...},
        "sheets": [
            {
                "name": "Sheet1",
                "used_range": {"min_row": 1, "max_row": 100, "min_col": 1, "max_col": 5},
                "tables": [
                    {
                        "name": "Table1",
                        "range": "A1:E10",
                        "headers": ["A", "B", ...],
                        "row_count": 9
                    }
                ],
                "charts": [{"type": "bar", "title": "..."}],
                "merged_cells": ["A1:C1"],
                "formulas": {"B10": "=SUM(B1:B9)"}
            }
        ]
    }

def to_markdown(self, sheet=None) -> str:
    """指定 sheet 输出 Markdown 表格；None 则全部 sheet 输出"""
```

### 6.4 注意事项

- `number_format` 单独赋值，不能在 `cell()` 构造时传（openpyxl 坑）
- xlsxwriter 模式下调用任何"读"操作 → 自动降级到 openpyxl（记录 warning）
- 大文件（>10万行）提示用户用 xlsxwriter 只读模式

## 7. PPT SDK

**底层引擎**：python-pptx（Python 原生 SDK）
**高品质补充**：pptxgenjs（通过 pptxgenjs-pro 技能调用，不在本 SDK 范围内）

### 7.1 Create / Edit

| 方法 | 说明 |
|---|---|
| `add_slide(layout="blank") -> SlideProxy` | 添加幻灯片 |
| `get_slide(index) -> SlideProxy` | 获取幻灯片 |
| `add_text_box(slide, x, y, w, h, text, **style)` | 文本框 |
| `add_table(slide, x, y, w, h, rows, cols, data, header=True)` | 表格 |
| `add_chart(slide, x, y, w, h, chart_type, data, categories, title)` | 图表 |
| `add_image(slide, path, x, y, w=None, h=None)` | 图片 |
| `add_notes(slide, text)` | 备注 |
| `set_slide_title(slide, text)` | 标题 |
| `find_replace(find_text, replace_text)` | 全局查找替换 |
| `duplicate_slide(index)` | 复制幻灯片 |
| `delete_slide(index)` | 删除幻灯片 |
| `slide_count() -> int` | 页数 |

**支持的布局**：blank / title / title_content / two_content / section_header / title_only / content_with_caption / picture_with_caption

### 7.2 Parse

```python
def parse(self) -> dict:
    return {
        "metadata": {...},
        "slides": [
            {
                "index": 0,
                "layout": "title",
                "title": "标题文字",
                "text_boxes": [
                    {"text": "...", "position": [x, y, w, h]}
                ],
                "tables": [
                    {"rows": 3, "cols": 2, "data": [...], "position": [...]}
                ],
                "images": [{"index": 0, "position": [...]}],
                "charts": [{"type": "bar", "title": "..."}],
                "notes": "备注文字"
            }
        ]
    }

def to_markdown(self) -> str:
    """每页一个 ## 标题 + 内容列表（大纲模式）"""
```

### 7.3 中文字体

- 默认字体：`Microsoft YaHei`
- 文本框 Run 同时设置 eastAsia 字体
- 字体 fallback 策略同 Word

## 8. 工厂类

```python
class OfficeDocument:
    """统一入口，自动识别格式"""
    
    @staticmethod
    def create(doc_type: str, path: str | None = None, **kwargs) -> OfficeDocumentBase:
        """
        按类型创建文档
        doc_type: "word" | "excel" | "ppt"
        """
    
    @staticmethod
    def open(path: str, **kwargs) -> OfficeDocumentBase:
        """
        打开已有文档，按扩展名自动识别
        .docx → WordDocument
        .xlsx → ExcelDocument
        .pptx → PPTDocument
        """
    
    @staticmethod
    def detect_format(path: str) -> str:
        """检测文件格式"""
```

## 9. 格式转换

```python
class OfficeConverter:
    """基于 LibreOffice 的格式转换，可选能力。"""
    
    @staticmethod
    def is_available() -> bool:
        """检测 LibreOffice 是否可用"""
    
    @staticmethod
    def to_pdf(input_path: str, output_path: str | None = None) -> str:
        """转换为 PDF，返回输出路径"""
    
    @staticmethod
    def get_version() -> str | None:
        """获取 LibreOffice 版本"""
```

### 检测路径（按优先级）

1. `soffice`（PATH 中）
2. `/Applications/LibreOffice.app/Contents/MacOS/soffice`（macOS）
3. `C:\Program Files\LibreOffice\program\soffice.exe`（Windows）
4. `/usr/bin/soffice`（Linux）

### 转换命令

```bash
soffice --headless --convert-to pdf --outdir <output_dir> <input_file>
```

## 10. 代码组织

```
L2-infra/components/office-generation/
├── src/                          # SDK 源码
│   ├── __init__.py               # 导出 OfficeDocument / OfficeConverter / 异常
│   ├── exceptions.py             # 统一异常体系
│   ├── factory.py                # OfficeDocument 工厂
│   ├── converter.py              # OfficeConverter 格式转换
│   ├── word_engine.py            # WordDocument SDK
│   ├── excel_engine.py           # ExcelDocument SDK
│   ├── ppt_engine.py             # PPTDocument SDK
│   └── utils/                    # 公共工具
│       ├── font.py               # 字体检测 / fallback
│       └── logging.py            # 日志
├── tests/                        # 测试
│   ├── test_word_engine.py
│   ├── test_excel_engine.py
│   ├── test_ppt_engine.py
│   ├── test_factory.py
│   ├── test_converter.py
│   ├── fixtures/                 # 测试用例文件
│   └── output/                   # 测试输出（gitignore）
├── research/                     # v1 调研产物（保留）
│   ├── REPORT.md
│   ├── scripts/
│   └── output/
├── agent-slides/                 # PPT 高阶能力（保留，独立演进）
├── agent-slides-tool/            # PPT 工具（保留，独立演进）
└── DESIGN.md                     # 本文件
```

## 11. 与 L3 / L4 的边界

### L2 做的（纯技术）
- 文档格式操作（create / read / update / parse / convert）
- 字体 / 样式 / 布局等排版细节
- 格式兼容性处理
- 统一异常和日志

### L3 做的（业务维度）
- 文档业务知识（结构规范、写作规范、审核标准）
- 通用模板资产（合同/报告/方案/汇报模板 + 索引）
- 文档业务角色（文档工程师、分析师等）
- 模板变量体系和填充校验

### L4 做的（专有业务）
- 专有业务规则（Bangcle VI 规范、销售合同审批流等）
- 专有数据和专有模板
- 专有流程（审批、签署、归档等）

### 调用路径（正确）
```
L4 专有业务 → L3 Office 业务维度 → L2 Office Engine（本组件）
```

### 当前待纠正（v2 M3 阶段）
```
BDMS (L4) → openpyxl (直调 L2 底层库)  ❌ 跨层直调
SCA-001 (L4) → python-docx (直调)       ❌ 跨层直调
Bangcle PPT (L4) → pptxgenjs (直调)     ❌ 跨层直调
```
M3 阶段统一改为经 L3 Office 维度间接调用。

## 12. 依赖关系

### 必选（Python）
| 库 | 用途 | 版本要求 |
|---|---|---|
| python-docx | Word 程序化构建 + 模板 | ≥1.1.0 |
| docxtpl | Word 模板渲染 | ≥0.16.0 |
| openpyxl | Excel 读写 | ≥3.1.0 |
| xlsxwriter | Excel 高性能写入 | ≥3.1.0 |
| pandas | DataFrame 快速导出 | ≥2.0.0 |
| python-pptx | PPT 程序化构建 | ≥0.6.21 |

### 可选
| 工具 | 用途 | 说明 |
|---|---|---|
| LibreOffice | PDF 转换 | 检测到自动启用，未安装则抛 OfficeUnsupportedError |
| Pillow | 图片处理 | python-docx 依赖，通常已安装 |

## 13. 验证

### 13.1 测试矩阵

| 测试类型 | Word | Excel | PPT | Factory | Converter |
|---|---|---|---|---|---|
| 基础创建 | ✅ | ✅ | ✅ | ✅ | — |
| 保存 / 重命名 | ✅ | ✅ | ✅ | — | — |
| 打开已有文件 | ✅ | ✅ | ✅ | ✅ | — |
| 样式设置 | ✅ | ✅ | ✅ | — | — |
| 表格操作 | ✅ | ✅ | ✅ | — | — |
| 图表操作 | — | ✅ | ✅ | — | — |
| 查找替换 | ✅ | ✅ | ✅ | — | — |
| parse → JSON | ✅ | ✅ | ✅ | — | — |
| to_markdown | ✅ | ✅ | ✅ | — | — |
| round-trip（生成→解析） | ✅ | ✅ | ✅ | — | — |
| 中文字体 | ✅ | ✅ | ✅ | — | — |
| 格式识别 | — | — | — | ✅ | — |
| 可用性检测 | — | — | — | — | ✅ |
| 异常场景 | ✅ | ✅ | ✅ | ✅ | ✅ |

### 13.2 Round-trip 验证标准

```
生成文档 → 保存到磁盘 → 重新打开 → parse → 验证数据一致
```

通过率要求：
- 文本内容：100% 一致
- 表格结构（行列数）：100% 一致
- 表格数据：100% 一致
- 样式：抽样验证（不要求 100% 精确还原）

## 14. 已知限制与 Workaround

| 限制 | 影响 | Workaround |
|---|---|---|
| docxtpl 表格行循环 bug | 模板中无法动态生成表格行 | 用 python-docx 手动构建表格 |
| xlsxwriter 只写不改 | 需要修改已有 Excel 时不适用 | 自动降级到 openpyxl |
| openpyxl number_format 坑 | cell() 不支持关键字参数 | SDK 内部单独赋值 |
| python-pptx 布局繁琐 | 需手动计算坐标 | 封装布局辅助函数 |
| 中文字体跨平台差异 | 文档显示不一致 | 字体 fallback 策略 + 启动时检测 |
| LibreOffice 可能不可用 | PDF 转换失败 | 优雅降级 + 明确提示安装 |
| python-pptx 无动画支持 | 无法生成带动画的 PPT | 提示用户用 pptxgenjs 技能 |

## 15. 演进方向

| 方向 | 优先级 | 条件 |
|---|---|---|
| L3 Office 业务维度（M2） | 高 | M1 完成后立即启动 |
| L4 业务组件迁移（M3） | 中 | L3 维度就绪后 |
| Skill 入口 + 模板市场 CLI（M4） | 中 | M2 完成后 |
| 高级能力：Word 目录生成 | 低 | 有业务需求时 |
| 高级能力：Excel 透视表 | 低 | 有业务需求时 |
| 高级能力：PPT 母版系统 | 低 | 有业务需求时 |
| 在线预览 / 缩略图生成 | 低 | 有 Web UI 需求时 |
