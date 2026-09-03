---
type: experience
id: EXP-20260903-001
date: 2026-09-03
title: OCR 坐标系统一陷阱：DPI 不一致导致 bbox 偏移
layers: [L3]
stage: develop
severity: high
category: correct
tags: [ocr, pdf, image-processing, dpi, coordinate-system, signature-detection]
status: active
supersedes: null
superseded_by: null
---

# [EXP-20260903-001] OCR 坐标系统一陷阱：DPI 不一致导致 bbox 偏移

## 1. 背景

在合同审批 OCR 模块中，需要从 PDF 转图后进行两项操作：
1. **OCR 文字识别** — 输出带 bbox 的文字位置
2. **签名/印章检测** — 根据关键词位置裁取周围区域做二次检测

两者需要共享同一套坐标系统，否则签名截图会裁到空白区域。

## 2. 问题

**症状**：
- OCR 文字识别结果正常，文字 bbox 位置准确
- 签名/印章检测时，按 OCR 坐标裁剪出的区域是**空白**的
- 印章截图偏到了文字上方/下方，实际印章位置与预期偏移数十像素

**排查发现**：
- OCR 用的图和检测用的图**不是同一张**
- 两张图的**像素尺寸不同**，但文件名相同，肉眼难辨
- 坐标直接混用 → 系统性偏移

## 3. 根因

v4 的 `pdf_to_images` 函数使用 macOS 内置的 `sips` 工具将 PDF 转图片：

```bash
sips -s dpiWidth 300 -s dpiHeight 300 input.pdf --out output.png
```

**关键陷阱**：`sips -s dpiWidth` **只修改图片元数据中的 DPI 字段，不改变实际像素尺寸**。PDF 渲染的像素数由 PDF 内部的默认 DPI（通常 72）和页面大小决定，`-s dpiWidth` 不会重新渲染。

后果：
- 以为输出的是 300 DPI 的图 → 实际像素还是 72 DPI 渲染的量
- 另一个流程用不同方式转图（比如 PyMuPDF 指定 dpi=300）→ 像素尺寸真的不同
- 两套坐标混用 → bbox 偏移倍数 = 300/72 ≈ 4.17×

## 4. 解决方案

### 方案：统一用 PyMuPDF 渲染，OCR 和检测共用同一张图

**采用**：`pdf_to_images` 改用 PyMuPDF 渲染，像素与 DPI 严格对应：

```python
import fitz  # PyMuPDF

def pdf_to_images(pdf_path, dpi=300):
    doc = fitz.open(pdf_path)
    images = []
    for page in doc:
        # 指定 matrix，像素尺寸 = 页面点数 * (dpi/72)
        mat = fitz.Matrix(dpi/72, dpi/72)
        pix = page.get_pixmap(matrix=mat)
        images.append(pix)  # pix.width / pix.height 严格对应 DPI
    return images
```

**签名检测直接复用 OCR 同图**：
- OCR 输出 `ocr_scale=1.0`（坐标与图像像素 1:1 对应）
- 签名检测函数接收同一张图 + OCR bbox → 坐标天然一致
- 不再做二次转图或缩放

## 5. 验证

**验证步骤**：
1. 用同一 PDF 分别跑 sips 和 PyMuPDF 转图，比较像素尺寸
2. 在 OCR 结果中取一个已知文字 bbox，直接在图上裁剪，确认能裁到文字
3. 印章检测：取"盖章"关键词 bbox，向四周扩展裁剪，确认能裁到印章

**实际结果**（2026-09-03 验证）：
- ✅ PyMuPDF 转图像素尺寸 = 页面点数 × (dpi/72)，严格对应
- ✅ OCR 和检测用同图后，签名/印章裁剪 100% 命中
- ✅ 墨迹验证：低墨迹区域输出警告，避免静默裁到空白

## 6. 教训与原则

**教训 1：所有图像处理函数必须显式带 DPI/scale 参数，不隐式假设**
- 函数签名里必须有 `dpi` 或 `scale` 参数
- 禁止"默认 DPI"的黑箱转换——调用方必须知道自己在什么坐标空间
- 返回值中附带图像实际尺寸和 DPI，方便校验

**教训 2：OCR 和检测用同一张图，坐标天然一致，最省心**
- 只要两个流程用不同方式出图，就一定有坐标不一致的风险
- 最优解：一次出图，多方复用，`ocr_scale=1.0`
- 实在不能共用 → 必须有显式的坐标转换函数，且写单元测试

**教训 3：加墨水验证阈值，低墨迹输出警告，避免静默失败**
- 裁剪后检查区域内像素方差/黑色像素占比
- 低于阈值 → 打 warning 日志，说明"可能裁错了位置"
- 静默失败比报错更危险——你以为检测了，实际上什么都没检测到

**设计原则**：
- **坐标空间透明化**：每张图、每个 bbox 都要能追溯到它的 DPI/scale
- **一次渲染，多方消费**：不要为不同流程重复渲染 PDF
- **失败可见**：检测类操作必须有"我没检测到有效内容"的信号机制

## 7. 相关组件

- **OCR-001**：OCR 文字识别模块（PaddleOCR / RapidOCR）
- **SCA-001**：签名/印章检测模块（Signature & Seal Detection）
- **PDF-001**：PDF 转图工具函数 `pdf_to_images`

## 8. 变更历史

- 2026-09-03: 创建（记录 OCR 坐标系统一问题及修复方案）
