# OCR 文档数字化组件设计

> L2 基础设施层组件，封装扫描件/图片文档数字化能力，为 L3/L4 提供统一的高精度文本识别服务。
>
> **与 Office 文档生成对偶**：一个"读"（OCR）、一个"写"（Office 生成），共同构成文档处理基础设施。

## 1. 定位

| 维度 | 值 |
|---|---|
| 层级 | L2 基础设施层 |
| 组件 ID | OCR-001 |
| 组件名称 | 文档数字化（OCR） |
| 状态 | ✅ 已上线 (2026-09-02) — 双引擎 + 优化管线实测通过 |
| 实现 | `skills/ocr-digitalization/scripts/ocr_backends.py`（核心引擎） |
| ADR | ADR-202609-023 |
| 引擎 | RapidOCR（主）+ PaddleOCR（高精度补充）+ 多版本预处理 |

## 2. 设计约束

1. **文件进文件出**。输入：PDF/图片路径；输出：纯文本 + Markdown。无外部服务、无状态。
2. **完整适配 OpenClaw**。脚本可被 skill、automation（cron/heartbeat）、agent 直接调用，不依赖特定运行时。
3. **避免耦合**。组件只依赖文件系统 + OCR 引擎库；不感知 L3/L4 业务语义。L4 通过 CLI 调用。
4. **可回滚**。输出文本独立保存，引擎升级不破坏既有产物。
5. **多引擎不绑定**。引擎可插拔，PaddleOCR 不可用时自动回退 RapidOCR。

## 3. 处理管线

```
扫描件 PDF / 图片
   │
   ▼
┌─────────────────────────────────┐
│ 1. PDF 转图片 (600 DPI, sips)    │
└─────────────────────────────────┘
   │
   ▼
┌─────────────────────────────────┐
│ 2. 多版本图像预处理             │
│    original / contrast1.5       │
│    contrast2.0 / sharp2.0       │
│    gray_contrast / denoised     │
│    scaled_1.5x / scaled_enh     │
└─────────────────────────────────┘
   │
   ▼
┌─────────────────────────────────┐
│ 3. 多引擎识别 + 最优选择        │
│    RapidOCR (主)                │
│    PaddleOCR (补充, 可用时)     │
│    按置信度+中文比投票取优       │
└─────────────────────────────────┘
   │
   ▼
┌─────────────────────────────────┐
│ 4. 版面分析 + 行排序            │
│    y 聚类分行 → x 排序合并      │
└─────────────────────────────────┘
   │
   ▼
┌─────────────────────────────────┐
│ 5. 合同场景错误纠错             │
│    40+ 规则词典                 │
└─────────────────────────────────┘
   │
   ▼
  纯文本 (.txt) + Markdown (.md)
```

## 4. 能力矩阵

| 能力 | 状态 | 说明 |
|---|---|---|
| 扫描件 PDF → 文本 | ✅ | 600DPI 渲染 |
| 图片 → 文本 | ✅ | PNG/JPG 直接输入 |
| 多版本预处理 | ✅ | 8 种版本自动选最优 |
| 版面分析 | ✅ | 行聚类 + 排序 |
| 中文识别 | ✅ | 中英混排 |
| 自动纠错 | ✅ | 合同场景 40+ 规则 |
| 双引擎投票 | ✅ | RapidOCR + PaddleOCR |
| 表格结构还原 | 🚧 | 演进方向（PP-Structure） |
| 印章遮挡文字恢复 | 🚧 | 需图像修复 |

## 5. API 设计

### 5.1 CLI（当前）

```bash
# 基本用法：PDF → Markdown + 纯文本
python3 contract_ocr.py <input.pdf> <output.md>

# 指定引擎
python3 contract_ocr.py <input.pdf> <output.md> --engine rapidocr
python3 contract_ocr.py <input.pdf> <output.md> --engine paddle
python3 contract_ocr.py <input.pdf> <output.md> --engine auto

# 图片输入
python3 contract_ocr.py <input.png> <output.md>
```

### 5.2 Python API（供 L3/L4 复用）

```python
from contract_ocr import digitalize_document

# PDF → 结构化文本
result = digitalize_document(
    path="contract.pdf",
    engine="auto",        # auto / rapidocr / paddle
    dpi=600,
    correct=True,          # 合同纠错
)
result.text      # 纯文本全文
result.markdown  # Markdown 带分页
result.pages     # 逐页结果（含置信度）
result.meta      # 引擎、耗时、行数
```

## 6. 引擎选型与边界

| 引擎 | 中文精度 | 速度 | 依赖 | 适用 |
|---|---|---|---|---|
| **RapidOCR** | 良 | 快（~2s/页） | onnxruntime | 默认主引擎 |
| **PaddleOCR** | 优 | 中（~5s/页） | paddlepaddle | 高精度场景 |
| tesseract | 差 | 中 | 系统级 | ❌ 不推荐中文 |
| macOS Vision | 差（中文） | 快 | pyobjc | ❌ 中文不达标 |

**引擎回退**：`--engine auto` 时，RapidOCR 优先；若结果中文字符占比 < 30% 或置信度 < 0.6，触发 PaddleOCR 对比，取优。

## 7. 依赖关系

### 7.1 Python 依赖
| 库 | 用途 | 必须 |
|---|---|---|
| `rapidocr-onnxruntime` | 主 OCR 引擎 | ✅ |
| `paddleocr` + `paddlepaddle` | 高精度补充 | ⚠️ 可选 |
| `PyPDF2` | PDF 解析 | ✅ |
| `Pillow` | 图像处理 | ✅ |
| `numpy` | 数组运算 | ✅ |
| `openpyxl` | 导出（可选） | ⚠️ |

### 7.2 系统依赖
| 工具 | 用途 | 平台 |
|---|---|---|
| `sips` | PDF→图片 | macOS |
| `poppler` | PDF→图片（备选） | 跨平台 |

## 8. 与现有系统协同

| 调用方 | 用途 | 层级 |
|---|---|---|
| 合同审批 SCA-001 | 扫描件合同 → 审核文本 | L4 |
| 知识库工具链 | 扫描件资料导入 | L2/L3 |
| 法务审查 | 合同条款数字化 | L3 |
| 档案管理 | 历史合同归档检索 | L3 |

## 9. 验证标准

1. **完整覆盖**：合同扫描件 10 页，逐页识别无缺失（页数 = 原文页数）
2. **关键字段准确**：甲方名称、金额、违约金比例等关键信息识别正确
3. **版面可读**：段落顺序正确，无乱序
4. **纠错生效**：已知错误模式（里→甲、朝图→朝阳、任→仟）被纠正
5. **双引擎回退**：PaddleOCR 不可用时，RapidOCR 单引擎可完成识别

## 10. 演进方向

1. **表格结构还原**：接入 PP-Structure，识别表格行列
2. **印章区域修复**：图像修复恢复印章遮挡文字
3. **版式还原**：识别标题层级、段落，输出近似原文排版
4. **合同模板匹配**：已知模板字段精确定位（配合 L4 Bangcle 模板）
5. **批量处理**：多文件队列 + 进度报告

## 11. 变更历史

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-09-02 | v1.0 | 组件创建，双引擎 + 优化管线 |
