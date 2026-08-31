# Office 文档生成能力深度调研报告

> 调研日期：2026-08-31 | 实测环境：Python 3.14 / Node v26.7.0 | 工作目录：/tmp/office-research/

## 1. 能力矩阵

| 库 | 格式 | 功能完整度 | 样式精细度 | API易用性 | 中文支持 | 性能 | 依赖 |
|---|---|---|---|---|---|---|---|
| **python-docx** | Word | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | 纯Python |
| **docxtpl** | Word(模板) | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | python-docx+Jinja2 |
| **openpyxl** | Excel | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | 纯Python |
| **xlsxwriter** | Excel | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | 纯Python |
| **pandas** | Excel | ⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ | numpy+openpyxl |
| **python-pptx** | PPT | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | 纯Python |
| **pptxgenjs** | PPT | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | Node.js |

## 2. 逐库实测结论

### 2.1 python-docx — Word 首选 ✅

**实测结果**：标题/段落/表格/样式/列表着色/页眉页脚 全部 OK
**输出**：`sample_word.docx` (38KB)

**能做什么**：
- 标题、段落、样式（字体/颜色/粗体/对齐）
- 表格（自定义样式、边框、着色）
- 列表（项目符号 + 颜色控制）
- 页眉页脚
- 图片插入（未实测但 API 支持）

**不能做什么**：
- 不支持模板渲染（需要 docxtpl）
- 不支持复杂页码（需手动构建 XML）
- 不支持修订追踪/批注（API 有限）

**坑**：
- 中文字体需同时设置 `font.name` + `rPr.rFonts.set(qn('w:eastAsia'), 'Microsoft YaHei')`，否则中文显示为方框

**定位**：**程序化构建 Word 文档的主力工具**

---

### 2.2 docxtpl — Word 模板渲染 ✅（有限制）

**实测结果**：变量替换/段落循环/条件 正常；表格行循环有 bug
**输出**：`rendered_working.docx` (37KB)

**能做什么**：
- Jinja2 模板渲染（变量、条件、循环）
- 段落级别的 `{% for %}` / `{% if %}` 正常
- 富文本（RichText 类）
- 图片占位替换（InlineImage）

**不能做什么（实测坑）**：
- ⚠️ **表格行循环 `{%tr for %}` 实测失败**：`patch_xml` 正则只匹配一个 `{%tr %}` 标签，for 和 endfor 分属不同 cell 时无法配对
- workaround：段落循环正常，表格行循环需改用 python-docx 手动构建

**定位**：**基于模板的 Word 生成（非表格循环场景）**，与 python-docx 配合使用

---

### 2.3 openpyxl — Excel 全功能 ✅

**实测结果**：多sheet/公式/条件格式/图表/样式 全部 OK
**输出**：`sample_excel.xlsx` (9.7KB)

**能做什么**：
- 多 Sheet 创建和管理
- 公式（SUM、百分比、跨单元格引用）
- 条件格式（CellIsRule、ColorScaleRule 色阶）
- 图表（柱状图、折线图）
- 样式（字体、填充、边框、对齐）
- 列宽/行高调整
- **可以读写已有 Excel 文件**（xlsxwriter 只能写新的）

**坑**：
- ⚠️ `cell()` 不支持 `number_format` 关键字参数，需单独赋值 `cell.number_format = '0.0%'`
- 图表样式选项有限（相比 xlsxwriter）

**定位**：**Excel 读写 + 全功能操作的主力库**

---

### 2.4 xlsxwriter — Excel 写入性能之王 ✅

**实测结果**：公式/条件格式(数据条+色阶+单元格规则)/图表/大数据写入 全部 OK
**输出**：`sample_xlsxwriter.xlsx` (273KB)，含 10000 行数据

**能做什么**：
- 公式（完整支持）
- 条件格式（数据条/色阶/单元格规则，**比 openpyxl 更丰富**）
- 图表（类型多、样式选项丰富）
- **大数据写入极快**：10000 行 × 4 列 = 0.05s
- 货币格式、百分比格式等数字格式化
- 合并单元格、冻结窗格、打印设置

**不能做什么**：
- ⚠️ **不能修改已有文件**（只能创建新文件）
- 不支持读取

**定位**：**大数据量 Excel 生成的首选**，只写场景性能最优

---

### 2.5 pandas — 数据导出最简 ✅

**实测结果**：DataFrame 导出/多sheet/基础格式 OK
**输出**：`sample_pandas.xlsx` (6.6KB)

**能做什么**：
- `DataFrame.to_excel()` 一行代码导出
- 多 Sheet（通过 `ExcelWriter`）
- 配合 openpyxl 做格式调整
- 汇总统计（sum/mean/max/min/std）

**不能做什么**：
- 不能做复杂图表
- 不能做条件格式
- 样式控制弱（需借助 openpyxl 后处理）

**定位**：**DataFrame → Excel 的快速导出通道**，不适合精细排版

---

### 2.6 python-pptx — PPT 全功能 ✅

**实测结果**：多slide/标题页/表格/柱状图/备注 全部 OK
**输出**：`sample_ppt.pptx` (42KB)，3 页 Slide

**能做什么**：
- 多 Slide 创建（自定义布局或空白）
- 文本框（字体/颜色/对齐/锚点）
- 表格（add_table）
- 图表（柱状图/折线图/饼图等）
- 备注（notes_slide）
- 图片插入
- 尺寸精确控制（Inches/EMU）

**坑**：
- API 较底层，布局计算需手动（x/y/w/h 全部自己算）
- 没有内置设计系统，需自己封装
- 图表样式选项有限

**定位**：**程序化 PPT 构建的 Python 方案**，需配合设计规范封装

---

### 2.7 pptxgenjs — PPT 设计品质最优 ✅（已有技能）

**状态**：已安装（`/opt/homebrew/lib/node_modules/pptxgenjs`），已有 `pptxgenjs-pro` 技能

**优势**：
- 设计系统完善（色彩/字体/卡片/流程图/泳道图）
- 中文支持好（Microsoft YaHei 默认）
- API 比 python-pptx 更友好
- 输出品质最高

**限制**：
- 仅限 Node.js 环境
- 不适合数据处理（先 Python 处理 → 传给 Node 生成）

**定位**：**高质量 PPT 生成的首选**，已有完整技能封装

---

## 3. 推荐工具链

### 按场景

| 场景 | 推荐 | 理由 |
|---|---|---|
| **数据报表导出 Excel** | pandas + openpyxl | 一行代码导出，openpyxl 后处理格式 |
| **精美 Excel 报告** | xlsxwriter | 条件格式+图表+性能最强 |
| **修改已有 Excel** | openpyxl | 唯一支持读写的库 |
| **简单 Word 文档** | python-docx | API 最直觉，纯 Python |
| **模板批量生成 Word** | docxtpl | Jinja2 模板，段落循环 OK |
| **复杂排版 Word** | python-docx | 完全控制，不受模板限制 |
| **高质量 PPT** | pptxgenjs（已有技能） | 设计系统+中文+图表 |
| **批量生成 PPT** | python-pptx | Python 原生，数据处理方便 |

### Rex 的最优工具链（Python 为主 + JS 补充）

```
Word  → python-docx（主力）+ docxtpl（模板场景）
Excel → openpyxl（读写+格式）+ xlsxwriter（大数据写入）+ pandas（快速导出）
PPT   → pptxgenjs（高质量，已有技能）+ python-pptx（Python 原生批量）
```

### 协同方案

1. **数据处理用 Python**（pandas 清洗 → openpyxl/xlsxwriter 生成 Excel）
2. **Word 报告用 python-docx**（程序化构建）或 **docxtpl**（模板渲染）
3. **PPT 用 pptxgenjs-pro 技能**（NODE_PATH=/opt/homebrew/lib/node_modules node script.js）
4. **三格式联动**：同一份数据 → 分别生成 Word 报告 + Excel 数据表 + PPT 演示

## 4. 已知限制与注意事项

| 限制 | 影响 | Workaround |
|---|---|---|
| docxtpl 表格行循环 bug | 模板中无法动态生成表格行 | 用 python-docx 手动构建表格，或用段落循环代替 |
| openpyxl number_format | cell() 不支持关键字参数 | 单独赋值 `cell.number_format = '...'` |
| xlsxwriter 只写不改 | 无法修改已有 Excel | 需要修改时用 openpyxl |
| python-pptx 布局繁琐 | 每个元素需手动计算坐标 | 封装布局函数或转用 pptxgenjs |
| pandas Excel 样式弱 | 无法做图表/条件格式 | 配合 openpyxl 后处理 |

## 5. 下一步建议

1. **封装通用生成函数**：把 python-docx / openpyxl / pptxgenjs 的常用模式封装为可复用模块
2. **建立数据→文档管线**：定义统一的数据输入格式（JSON/dict），驱动三种格式输出
3. **模板库积累**：docxtpl 模板文件管理（段落循环可用，表格循环需 workaround）
4. **pptxgenjs-pro 技能扩展**：补充更多图表类型和数据驱动生成模式
