---
name: ocr-digitalization
description: L2 OCR 文档数字化组件 — 扫描件/图片 → 高精度文本 + 签名/印章自动检测
---

# OCR 文档数字化（OCR-001）

L2 基础设施组件。将扫描件、图片、PDF 转换为可处理的结构化文本，自动检测签名、印章等签署要素。

## 公共 API

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'ocr-digitalization', 'scripts'))
from ocr_engine import digitalize_document_v5, ocr_image, pdf_to_images, detect_signature_page_v2
from ocr_backends import correct_ocr_errors, preprocess_image
```

### 核心函数

| 函数 | 说明 |
|---|---|
| `digitalize_document_v5(pdf_path, output_path, ...)` | 端到端：PDF → OCR 文本 + 签名/印章检测 |
| `ocr_image(image, engine='rapidocr')` | 单图 OCR，返回 List[OCRLine] |
| `pdf_to_images(pdf_path, dpi=300)` | PDF 转图（PyMuPDF 渲染，DPI 与像素严格对应） |
| `detect_signature_page_v2(image, page_num, output_dir, ocr_lines, ocr_scale=1.0)` | 签署页检测：左右分栏 + 印章/签名联检 + 整列截取 |
| `detect_red_seals(image, page_num, output_dir)` | 红色印章检测 |
| `correct_ocr_errors(text)` | OCR 文本纠错（40+ 规则） |

## 设计文档

详见 `docs/architecture/components/ocr-digitalization/DESIGN.md`

## ADR

[ADR-202609-023](../docs/knowledge-base/by-category/project-experience/adr/ADR-202609-023-ocr-digitalization.md) — 已 accepted

## 依赖

- RapidOCR（主引擎，纯 CPU，默认）
- PaddleOCR（可选，GPU 加速）
- PyMuPDF（PDF 渲染）
- Pillow
- NumPy
