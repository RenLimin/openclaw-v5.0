# OCR-001 文档数字化 — 产品操作手册（OPERATIONS）

> 版本：v1.0（2026-09-28）
> 组件 ID：OCR-001
> 层级：L2 基础设施层
> 设计依据：DESIGN.md + ADR-202609-023
> 源码路径：`L2-infra/components/ocr-digitalization/scripts/`
> 调用方式：CLI / Python API

---

## 1. 安装与依赖

### 1.1 最小依赖安装（RapidOCR 主引擎）

```bash
pip install rapidocr-onnxruntime numpy pillow PyPDF2
```

### 1.2 可选高精度补充（PaddleOCR）

```bash
pip install paddlepaddle paddleocr
# → 首次使用自动下载模型（~100MB），可手动下载到 ~/.paddleocr/
```

### 1.3 系统依赖

**macOS** 自带 `sips`，无需额外安装。

**Linux** 需要安装 `poppler-utils` 提供 `pdftocairo`（PDF 转图片）：

```bash
# Debian/Ubuntu
apt install poppler-utils
# RHEL/CentOS
yum install poppler-utils
```

---

## 2. 快速开始（CLI 调用，L3/L4 业务通用）

### 2.1 基本用法

```bash
# 扫描件 PDF → Markdown + 纯文本（auto 引擎模式）
python3 ocr_main.py input.pdf output.md

# 指定引擎
python3 ocr_main.py input.pdf output.md --engine rapidocr  # 只用 RapidOCR（快，精度良）
python3 ocr_main.py input.pdf output.md --engine paddle      # 只用 PaddleOCR（中速，精度优）
python3 ocr_main.py input.pdf output.md --engine auto        # 自动投票（默认，优先 Rapid，低置信度才 Paddle）

# 图片输入（PNG/JPG）
python3 ocr_main.py scan.jpg output.md
```

### 2.2 输出说明

- `.md` 文件：带分页的 Markdown 格式（`--- Page 1 ---` 分隔）
- `.txt` 文件：纯文本全文（无分页）
- `.json` 文件：元数据 + 逐页结果 + 引擎信息

---

## 3. Python API 调用（L3/L4 代码复用）

```python
from ocr_digitalization import digitalize_document

# 基本用法
result = digitalize_document(
    path="contract.pdf",
    engine="auto",        # auto / rapidocr / paddle
    dpi=600,              # PDF 渲染 DPI，默认 600
    correct=True,         # 是否开启合同场景纠错，默认 True
)

# 结果结构
print(result.text)      # 纯文本全文
print(result.markdown)  # 带分页的 Markdown
print(result.pages)     # 逐页识别结果（含置信度/坐标）
print(result.meta)      # 元信息（引擎/耗时/总行数）
```

---

## 4. 核心能力说明

### 4.1 自动纠错（合同场景）

开启 `correct=True`（默认），会自动纠正 OCR 常见识别错误（约 40+ 规则）：
- 常见错字：`里→甲` / `图→目` / `任→仟` / `万→万` / `朝图→朝阳` 等
- 格式错误：多余空格、乱码字符等
- 如果是非合同文档，可关闭 `correct=False`

### 4.2 多版本预处理

默认开启 8 种不同的图像预处理版本，OCR 会尝试所有版本，取置信度最高的结果：
- 原分辨率、对比度×1.5、对比度×2.0、锐化×2.0
- 灰度对比度增强、去噪、1.5倍缩放、缩放增强
- 这是对抗低质量扫描件的关键，不可关闭

### 4.3 双引擎自动投票（`auto` 模式）

1. 先由 RapidOCR 识别全页
2. 如果全页平均置信度 < 0.6 或中文字符占比 < 30%，触发 PaddleOCR
3. 逐框对比，取置信度高的结果 → 最终输出
4. 既保证速度，又保证精度 → ✅ 推荐生产用

---

## 5. 故障排查

### 5.1 PDF 转图片失败

- 错误：`Command '['sips', ...]' returned non-zero exit status`
- 原因：系统缺少 `sips`（非 macOS）或 `poppler-utils`
- 解决：按 §1.3 安装系统依赖

### 5.2 识别结果全空或乱码

- 可能原因 1：PDF 是图片格式，但 DPI 过低 → 检查原扫描件质量，建议 ≥ 300DPI，OCR 默认用 600DPI
- 可能原因 2：图片非常暗/对比度极低 → auto 模式会自动试多种预处理，多数情况能出结果；如果仍不行，建议重新扫描
- 可能原因 3：图像为纯手写 → 不支持手写识别

### 5.3 版面错排（行顺序不对）

- 当前算法基于 y 坐标聚类分行 → 对于非常不规则的版面（如多栏分块交错）可能错排
- 可在 issue 提交示例，后续优化；当前建议手动调整

### 5.4 PaddleOCR 无法加载

- 错误：`ModuleNotFoundError: No module named 'paddle'`
- 原因：未安装 paddlepaddle
- 解决：按 §1.2 安装；或用 `--engine rapidocr` 跳过

### 5.5 识别耗时太长

- `auto` 模式下低质量页会触发 PaddleOCR，耗时增加 → 是正常行为
- 如果追求速度，用 `--engine rapidocr`，耗时减半，但精度略降

---

## 6. FAQ

**Q1: 能识别表格吗？**
A: 当前版本仅识别文本，表格结构不还原。演进路线中已计划 PP-Structure 接入，后续版本会支持。

**Q2: 能识别印章遮挡的文字吗？**
A: 当前不支持印章修复，印章遮挡的文字仍会识别错误。印章修复是演进方向。

**Q3: 如何批量处理多个文件？**
A: 当前仅支持单文件，可写简单 shell 脚本批量调用 CLI 入口；后续版本会增加批量支持。

**Q4: 输出的 JSON 有什么用？**
A: 供 L3/L4 业务做二次加工，比如提取特定字段、统计等，可直接使用结构化结果。

---

## 7. 变更历史

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-09-28 | v1.0 | 初版：安装/使用/故障排查/FAQ，基于 v1.0 全量验证 |
