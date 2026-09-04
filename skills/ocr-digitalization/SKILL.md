---
name: ocr-digitalization
description: L2 OCR 文档数字化组件 — 扫描件/图片 → 高精度文本 + 签名/印章自动检测
---

# OCR 文档数字化（OCR-001）

L2 基础设施组件。将扫描件、图片、PDF 转换为可处理的结构化文本，自动检测签名、印章等签署要素。

## CLI 用法

```bash
python skills/ocr-digitalization/scripts/ocr_engine.py <pdf_path> <output_md> [options]
```

### 命令行参数

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `input` | 位置参数（必填） | — | 输入 PDF 或图片路径 |
| `output` | 位置参数 | `output.md` | 输出 Markdown 文件路径 |
| `--engine` | 字符串 | `auto` | OCR 引擎：`rapidocr` / `paddle` / `auto` |
| `--dpi` | int | `300` | PDF 渲染 DPI，数值越高精度越高但越慢 |
| `--signature-dir` | 字符串 | `{pdf同目录}/signatures` | 签名/印章截图保存目录 |
| `--no-signatures` | flag | 关闭 | 不检测签名和印章（提速） |
| `--json` | 字符串 | 空 | 额外导出 OCR 检测结果 JSON（供上层集成使用） |
| `--debug` | flag | 关闭 | 输出调试信息（检测中间图等，开发用） |

### CLI 示例

```bash
# 最简用法：PDF → Markdown
python skills/ocr-digitalization/scripts/ocr_engine.py 合同扫描件.pdf 合同.md

# 指定引擎 + DPI + 签名目录 + JSON 导出
python skills/ocr-digitalization/scripts/ocr_engine.py \
  合同扫描件.pdf \
  合同.md \
  --engine rapidocr \
  --dpi 300 \
  --signature-dir ./output/signatures \
  --json ./output/ocr_result.json

# 只做纯文本 OCR，不检测签名（更快）
python skills/ocr-digitalization/scripts/ocr_engine.py 扫描件.pdf 文本.md --no-signatures
```

## Python API 用法

### 场景 1：端到端数字化 PDF（最常用）

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'ocr-digitalization', 'scripts'))
from ocr_engine import digitalize_document_v5

result = digitalize_document_v5(
    pdf_path="合同扫描件.pdf",
    output_path="合同.md",          # 可选，不传则不写文件
    engine="rapidocr",              # rapidocr / paddle / auto
    dpi=300,
    extract_signatures=True,        # 是否检测签名/印章
    signature_dir="./signatures"    # 签名截图保存目录
)

print(result.text)                  # 纯文本全文
print(result.markdown)              # Markdown（含签名/印章标注）
print(f"页数: {result.meta['pages']}")
print(f"印章: {result.meta['seals_found']} 处")
print(f"签名: {result.meta['signatures_found']} 处")

# 遍历印章
for seal in result.seals:
    print(f"🔴 第{seal.page}页 印章: {seal.image_path}, bbox={seal.bbox}")

# 遍历签名
for sig in result.signatures:
    print(f"✍️  第{sig.page}页 {sig.label}: {sig.image_path}")
```

### 场景 2：单图 OCR

```python
from PIL import Image
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'ocr-digitalization', 'scripts'))
from ocr_engine import ocr_image

image = Image.open("page_001.png")
lines = ocr_image(image, engine="rapidocr")

for line in lines:
    print(f"[{line.bbox}] ({line.confidence:.2f}) {line.text}")
    # line.bbox = (x1, y1, x2, y2)
    # line.confidence = 0.0 ~ 1.0
    # line.text = 识别文本
```

### 场景 3：仅检测签名印章

```python
from PIL import Image
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'ocr-digitalization', 'scripts'))
from ocr_engine import detect_signature_page_v2, ocr_image, pdf_to_images

# 先把 PDF 转图
images = pdf_to_images("合同.pdf", dpi=300)

for page_num, image in enumerate(images, start=1):
    # 先做 OCR 获得行信息（用于定位"甲方签字"等关键词）
    ocr_lines = ocr_image(image, engine="rapidocr")

    # 检测签署页的签名和印章
    signatures, seals = detect_signature_page_v2(
        image=image,
        page_num=page_num,
        output_dir="./signatures",    # 截图保存目录
        ocr_lines=ocr_lines,          # OCR 结果，用于关键词定位
        ocr_scale=1.0                 # OCR 坐标与图像像素的缩放比
    )

    print(f"第{page_num}页: 签名 {len(signatures)} 处, 印章 {len(seals)} 处")
```

## 公共 API 总览

| 函数 / 类 | 说明 |
|---|---|
| `digitalize_document_v5(pdf_path, ...)` | 端到端：PDF → OCR 文本 + 签名/印章检测 |
| `ocr_image(image, engine='rapidocr')` | 单图 OCR，返回 `List[OCRLine]` |
| `pdf_to_images(pdf_path, dpi=300)` | PDF 转图（PyMuPDF 渲染，DPI 与像素严格对应） |
| `detect_signature_page_v2(image, page_num, output_dir, ocr_lines, ocr_scale=1.0)` | 签署页检测：左右分栏 + 印章/签名联检 + 整列截取 |
| `detect_red_seals(image, page_num, output_dir)` | 红色印章检测（独立调用） |
| `correct_ocr_errors(text)` | OCR 文本纠错（40+ 合同场景规则） |
| `OCRResultV5` | 端到端结果对象（text / markdown / pages / signatures / seals / meta） |
| `OCRLine` | 单行 OCR 结果（text / bbox / confidence / source） |
| `SignatureRegion` | 签名/印章区域（type / page / bbox / confidence / image_path / label） |

## 集成指南

### 方式一：sys.path 直接引入（推荐，性能最好）

在其他 skill 的脚本中，把 ocr-digitalization 的 scripts 目录加到 sys.path：

```python
import sys, os

# 相对路径方式（假设调用方在 skills/xxx/scripts/ 下）
_ocr_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        '..', '..', 'ocr-digitalization', 'scripts')
if _ocr_dir not in sys.path:
    sys.path.insert(0, _ocr_dir)

from ocr_engine import digitalize_document_v5, ocr_image, pdf_to_images

# 正常使用
result = digitalize_document_v5("合同.pdf", "合同.md")
```

**适用场景**：同一仓库内的 skill 互相调用，代码在同一台机器上。

### 方式二：兼容层 re-export（向后兼容）

如果你的项目里已有 `contract_ocr_v5.py` 之类的兼容层文件，可以直接从兼容层引入：

```python
# contract-approval skill 内自带兼容层
from contract_ocr_v5 import digitalize_document_v5

result = digitalize_document_v5("合同.pdf", "合同.md")
```

兼容层内部其实就是方式一的 sys.path + re-export，好处是调用方代码不用改，升级 OCR 组件时只改兼容层即可。

**适用场景**：已有代码依赖旧路径，或需要解耦两个 skill。

### 方式三：CLI 子进程调用（松耦合）

```python
import subprocess

subprocess.run([
    "python", "skills/ocr-digitalization/scripts/ocr_engine.py",
    "合同.pdf", "output.md",
    "--signature-dir", "signatures/",
    "--json", "ocr_result.json"
], check=True)

# 然后读 output.md 和 ocr_result.json
```

**适用场景**：跨语言、跨进程、完全解耦。缺点是启动开销和序列化成本。

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
- SciPy
