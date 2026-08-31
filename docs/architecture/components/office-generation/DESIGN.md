# Office 文档生成组件设计

> L2 基础设施层组件，封装多语言（Python + Node.js）多库 Office 文档生成能力，为 L3/L4 提供统一的文件生成服务。
>
> **不是单一库**。本组件是工具链集合，按场景推荐最优库，明确每个库的能力边界和已知限制。所有选型均基于实测。

## 1. 定位

| 维度 | 值 |
|---|---|
| 层级 | L2 基础设施层 |
| 组件 ID | 011 |
| 组件名称 | Office 文档生成 |
| 状态 | ✅ 已上线 (2026-08-31) — 6/6 库实测通过 + pptxgenjs-pro 已有技能 |
| 实现 | Python 生态（python-docx/docxtpl/openpyxl/xlsxwriter/pandas/python-pptx）+ Node.js（pptxgenjs，已有技能 pptxgenjs-pro） |
| ADR | ADR-016 (Office 文档生成能力) |
| 实测报告 | `/tmp/office-research/REPORT.md` |

## 2. 设计约束

1. **多库协同，不追求单一库全功能**。Word/Excel/PPT 各有 2-3 个库，按场景选用。
2. **选型基于实测，不凭文档推测**。每个库都经过实际运行验证，记录能力边界和坑。
3. **不重复造轮子**。直接使用成熟的开源库，本组件做选型、封装和最佳实践沉淀。
4. **Python 为主，Node.js 补充**。数据处理在 Python 侧完成，PPT 高品质输出用 Node.js。
5. **文件系统输出**。输出为本地文件，不做云端存储或在线预览。

## 3. 能力矩阵

### 3.1 总览

| 库 | 格式 | 功能完整度 | 样式精细度 | API 易用性 | 中文支持 | 性能 | 语言 |
|---|---|---|---|---|---|---|---|
| **python-docx** | Word | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | Python |
| **docxtpl** | Word(模板) | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | Python |
| **openpyxl** | Excel | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | Python |
| **xlsxwriter** | Excel | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | Python |
| **pandas** | Excel | ⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ | Python |
| **python-pptx** | PPT | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | Python |
| **pptxgenjs** | PPT | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | Node.js |

### 3.2 逐库能力边界（基于实测）

#### python-docx — Word 主力

| 能力 | 状态 | 说明 |
|---|---|---|
| 标题/段落/样式 | ✅ | 字体/颜色/粗体/对齐 |
| 表格 | ✅ | 自定义样式、边框、着色 |
| 列表 | ✅ | 项目符号 + 颜色控制 |
| 页眉页脚 | ✅ | |
| 图片插入 | ✅ | API 支持（未实测） |
| 模板渲染 | ❌ | 需要 docxtpl |
| 复杂页码 | ❌ | 需手动构建 XML |
| 修订追踪/批注 | ⚠️ | API 有限 |

**坑**：中文字体需同时设置 `font.name` + `rPr.rFonts.set(qn('w:eastAsia'), 'Microsoft YaHei')`，否则中文显示为方框。

#### docxtpl — Word 模板渲染

| 能力 | 状态 | 说明 |
|---|---|---|
| 变量替换 | ✅ | Jinja2 语法 |
| 条件渲染 | ✅ | `{% if %}` |
| 段落循环 | ✅ | `{% for %}` 段落级别 |
| 富文本 | ✅ | RichText 类 |
| 图片占位替换 | ✅ | InlineImage |
| 表格行循环 | ❌ | `{%tr for %}` 实测失败（patch_xml 正则只匹配一个标签）|

**定位**：基于模板的 Word 生成（非表格循环场景），与 python-docx 配合使用。

#### openpyxl — Excel 全功能

| 能力 | 状态 | 说明 |
|---|---|---|
| 多 Sheet | ✅ | 创建和管理 |
| 公式 | ✅ | SUM、百分比、跨单元格引用 |
| 条件格式 | ✅ | CellIsRule、ColorScaleRule 色阶 |
| 图表 | ✅ | 柱状图、折线图 |
| 样式 | ✅ | 字体、填充、边框、对齐 |
| 列宽/行高 | ✅ | |
| 读写已有文件 | ✅ | 区别于 xlsxwriter |
| 大数据写入性能 | ⚠️ | 不如 xlsxwriter |

**坑**：`cell()` 不支持 `number_format` 关键字参数，需单独赋值 `cell.number_format = '0.0%'`。

#### xlsxwriter — Excel 写入性能之王

| 能力 | 状态 | 说明 |
|---|---|---|
| 公式 | ✅ | 完整支持 |
| 条件格式 | ✅ | 数据条/色阶/单元格规则（比 openpyxl 更丰富）|
| 图表 | ✅ | 类型多、样式选项丰富 |
| 大数据写入 | ✅ | 10000 行 × 4 列 = 0.05s |
| 数字格式化 | ✅ | 货币、百分比等 |
| 合并单元格/冻结窗格 | ✅ | |
| 打印设置 | ✅ | |
| 修改已有文件 | ❌ | 只能创建新文件 |
| 读取 | ❌ | 不支持 |

**定位**：大数据量 Excel 生成的首选，只写场景性能最优。

#### pandas — Excel 快速导出

| 能力 | 状态 | 说明 |
|---|---|---|
| DataFrame → Excel | ✅ | `to_excel()` 一行代码 |
| 多 Sheet | ✅ | ExcelWriter |
| 统计汇总 | ✅ | sum/mean/max/min/std |
| 复杂图表 | ❌ | |
| 条件格式 | ❌ | |
| 精细样式 | ❌ | 需借助 openpyxl 后处理 |

**定位**：DataFrame → Excel 的快速导出通道，不适合精细排版。

#### python-pptx — PPT Python 方案

| 能力 | 状态 | 说明 |
|---|---|---|
| 多 Slide | ✅ | 自定义布局或空白 |
| 文本框 | ✅ | 字体/颜色/对齐/锚点 |
| 表格 | ✅ | add_table |
| 图表 | ✅ | 柱状图/折线图/饼图等 |
| 备注 | ✅ | notes_slide |
| 图片插入 | ✅ | |
| 尺寸精确控制 | ✅ | Inches/EMU |
| 内置设计系统 | ❌ | 需自己封装 |
| 布局自动计算 | ❌ | x/y/w/h 全部自己算 |

**定位**：程序化 PPT 构建的 Python 方案，适合数据驱动批量生成。

#### pptxgenjs — PPT 设计品质最优

| 能力 | 状态 | 说明 |
|---|---|---|
| 设计系统 | ✅ | 色彩/字体/卡片/流程图/泳道图 |
| 中文支持 | ✅ | Microsoft YaHei 默认 |
| 图表 | ✅ | 完整图表支持 |
| API 友好度 | ✅ | 比 python-pptx 更友好 |
| 输出品质 | ✅ | 最高 |
| Python 调用 | ⚠️ | 需通过 exec 调用 Node.js |

**定位**：高质量 PPT 生成的首选，已有 `pptxgenjs-pro` 技能封装。

## 4. 场景选型指南

| 场景 | 推荐工具 | 理由 |
|---|---|---|
| 数据报表导出 Excel | pandas + openpyxl | 一行代码导出，openpyxl 后处理格式 |
| 精美 Excel 报告 | xlsxwriter | 条件格式 + 图表 + 性能最强 |
| 修改已有 Excel | openpyxl | 唯一支持读写的库 |
| 简单 Word 文档 | python-docx | API 最直觉，纯 Python |
| 模板批量生成 Word | docxtpl | Jinja2 模板，段落循环 OK |
| 复杂排版 Word | python-docx | 完全控制，不受模板限制 |
| 高质量 PPT | pptxgenjs（已有技能） | 设计系统 + 中文 + 图表 |
| 批量生成 PPT | python-pptx | Python 原生，数据处理方便 |

## 5. API 设计（高层抽象）

> 以下为设计级 API 规范，具体实现待 `scripts/office/` 模块开发。

### 5.1 Word

```python
generate_word(
    template_path: str | None = None,   # docx 模板路径（用 docxtpl 时）
    data: dict,                          # 模板变量或构建数据
    output_path: str,
    mode: str = "programmatic"          # "programmatic" (python-docx) | "template" (docxtpl)
) → str  # 返回输出文件路径
```

- `mode="programmatic"`：用 python-docx 程序化构建
- `mode="template"`：用 docxtpl 渲染模板（段落循环 OK，表格行循环不支持）

### 5.2 Excel

```python
generate_excel(
    data: dict[str, DataFrame | list[dict]],  # sheet_name → data
    config: ExcelConfig,                      # 样式/图表/条件格式配置
    output_path: str,
    engine: str = "auto"                      # "auto" | "openpyxl" | "xlsxwriter" | "pandas"
) → str
```

- `engine="auto"`：自动选择（大数据用 xlsxwriter，需要读写用 openpyxl，纯导出用 pandas）
- `config` 支持：列宽、表头样式、条件格式、图表、冻结窗格等

### 5.3 PPT

```javascript
// Node.js / pptxgenjs（通过 pptxgenjs-pro 技能调用）
generate_ppt(
    slides_data: SlideSpec[],    // 每页内容 + 布局 + 样式
    template: string | null,     // 可选模板
    output_path: string
) → string  // 返回输出文件路径
```

```python
# Python / python-pptx（批量场景）
generate_ppt_python(
    slides_data: list[dict],
    output_path: str
) → str
```

## 6. 协同架构

```
┌─────────────────────────────────────────────────┐
│              L3 / L4 业务层                      │
│  报表生成 / 合同管理 / 报告自动化 / 演示生成       │
└──────────────────────┬──────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────┐
│         L2 Office 文档生成组件 (011)              │
│                                                   │
│  ┌──────────┐ ┌────────────┐ ┌──────────────┐   │
│  │  Word    │ │   Excel    │ │    PPT       │   │
│  │ python-  │ │ openpyxl   │ │ pptxgenjs    │   │
│  │  docx    │ │ xlsxwriter │ │  (Node.js)   │   │
│  │ +docxtpl │ │ +pandas    │ │ +python-pptx │   │
│  └──────────┘ └────────────┘ └──────────────┘   │
└──────────────────────┬──────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────┐
│          L1 运行时抽象层                          │
│   exec / 文件系统 / 沙箱隔离                       │
└─────────────────────────────────────────────────┘
```

## 7. 依赖关系

### 7.1 Python 依赖

| 库 | 用途 | 安装 |
|---|---|---|
| python-docx | Word 程序化构建 | `pip install python-docx` |
| docxtpl | Word 模板渲染 | `pip install docxtpl`（依赖 python-docx + Jinja2） |
| openpyxl | Excel 读写 + 格式 | `pip install openpyxl` |
| xlsxwriter | Excel 高性能写入 | `pip install xlsxwriter` |
| pandas | Excel 快速导出 | `pip install pandas`（依赖 numpy + openpyxl） |
| python-pptx | PPT Python 方案 | `pip install python-pptx` |

### 7.2 Node.js 依赖

| 库 | 用途 | 安装 |
|---|---|---|
| pptxgenjs | PPT 高质量生成 | `npm install -g pptxgenjs`（已安装于 `/opt/homebrew/lib/node_modules/`）|

### 7.3 现有技能协同

| 技能 | 关系 |
|---|---|
| `pptxgenjs-pro` | 本组件 PPT 子能力的高层次封装，提供设计系统 + 常用模板 |

## 8. 已知限制与 Workaround

| 限制 | 影响 | Workaround |
|---|---|---|
| docxtpl 表格行循环 bug | 模板中无法动态生成表格行 | 用 python-docx 手动构建表格，或用段落循环代替 |
| openpyxl number_format 坑 | `cell()` 不支持关键字参数 | 单独赋值 `cell.number_format = '...'` |
| xlsxwriter 只写不改 | 无法修改已有 Excel | 需要修改时用 openpyxl |
| python-pptx 布局繁琐 | 每个元素需手动计算坐标 | 封装布局函数或转用 pptxgenjs |
| pandas Excel 样式弱 | 无法做图表/条件格式 | 配合 openpyxl 后处理 |
| python-docx 中文字体 | 中文显示为方框 | 同时设置 font.name + eastAsia 字体 |
| pptxgenjs 仅限 Node.js | Python 侧无法直接调用 | 通过 exec 调用 Node.js 脚本（pptxgenjs-pro 技能已封装） |

## 9. 验证

### 9.1 实测文件清单

| 文件 | 大小 | 生成工具 | 验证点 |
|---|---|---|---|
| `sample_word.docx` | 38KB | python-docx | 标题/段落/表格/样式/列表着色/页眉页脚 |
| `rendered_working.docx` | 37KB | docxtpl | 变量替换/段落循环/条件渲染 |
| `sample_excel.xlsx` | 9.7KB | openpyxl | 多sheet/公式/条件格式/图表/样式 |
| `sample_xlsxwriter.xlsx` | 273KB | xlsxwriter | 10000 行/0.05s/数据条/图表 |
| `sample_pandas.xlsx` | 6.6KB | pandas | DataFrame 导出/多 sheet |
| `sample_ppt.pptx` | 42KB | python-pptx | 3 页/表格/柱状图/备注 |

实测文件位于 `/tmp/office-research/output/`，详细报告见 `/tmp/office-research/REPORT.md`。

### 9.2 验证结论

- ✅ 6/6 Python 库实测全部通过
- ✅ pptxgenjs 已有技能 + 实测可用
- ✅ 7 个库覆盖 Word/Excel/PPT 全场景
- ⚠️ 每个库都有已知限制，已记录 workaround

## 10. 演进方向

| 方向 | 优先级 | 条件 |
|---|---|---|
| 封装通用生成函数 (`scripts/office/`) | 高 | 第一个业务场景需要时 |
| 数据→文档统一管线 | 中 | 多格式联动需求出现时 |
| docxtpl 模板库积累 | 中 | 模板化场景增多时 |
| pptxgenjs-pro 技能扩展 | 中 | 新图表类型或设计模板需求 |
| PDF 导出能力 | 低 | 需要 PDF 输出时（libreoffice / wkhtmltopdf） |
