# OCR 文档数字化组件（OCR-001）

> L2 基础设施层组件 | 扫描件/图片 → 高精度文本 + 签署要素自动检测

## 安装依赖

```bash
# 必需依赖
pip install rapidocr-onnxruntime pymupdf pillow numpy scipy

# 可选：PaddleOCR（GPU 加速，体积较大）
# pip install paddleocr paddlepaddle
```

> **注意**：`rapidocr-onnxruntime` 是纯 CPU 引擎，开箱即用，无需 CUDA。
> PaddleOCR 精度更高但安装包大（约 1GB），仅在需要时安装。

## 快速开始（3 步跑通）

### 第 1 步：准备扫描件 PDF

把要数字化的 PDF 放到工作目录，比如 `合同扫描件.pdf`。

### 第 2 步：运行 OCR

```bash
python skills/ocr-digitalization/scripts/ocr_engine.py \
  合同扫描件.pdf \
  合同.md \
  --signature-dir signatures/ \
  --json ocr_result.json
```

### 第 3 步：查看输出

```
合同.md              # 数字化后的 Markdown（含签名/印章位置标注）
signatures/          # 签名、印章截图
  ├── page_3_seal_1.png       # 第3页第1个印章
  ├── page_3_sig_甲方签字.png  # 第3页甲方签字区域
  └── page_3_sig_乙方签字.png  # 第3页乙方签字区域
ocr_result.json      # 结构化 OCR 结果（供程序读取）
```

打开 `合同.md` 查看全文，检查 `signatures/` 下的截图是否完整。

## 功能特性

- **多引擎**：RapidOCR（默认，纯 CPU）+ PaddleOCR（可选）
- **原生提取优先**：非扫描 PDF 直接用 PyMuPDF 抽文本，100% 准确
- **高精度**：300 DPI PyMuPDF 渲染 + 多版本预处理 + 版面分析
- **场景纠错**：40+ 合同场景专项 OCR 纠错规则
- **签署要素检测**：红色印章检测 + 手写签名检测 + 签署页智能识别
- **坐标系统一**：OCR 与检测用同图，DPI 与像素严格对应，杜绝坐标偏移
- **调试可视化**：检测结果红框（印章）/绿框（签名）输出 debug.png

## 输出文件说明

| 文件 | 格式 | 说明 |
|---|---|---|
| `output.md` | Markdown | 数字化全文，按页分隔，签名/印章位置有标注 |
| `signatures/page_X_seal_N.png` | PNG | 第 X 页第 N 个红色印章截图 |
| `signatures/page_X_sig_标签.png` | PNG | 第 X 页对应标签的签名区域截图（如"甲方签字"、"乙方签字"） |
| `ocr_result.json` | JSON | 结构化结果，包含 seals / signatures / text / meta |

### ocr_result.json 结构

```json
{
  "seals": [
    {"type": "seal", "page": 3, "label": "", "confidence": 0.92,
     "image_path": "signatures/page_3_seal_1.png", "bbox": [100, 200, 300, 400]}
  ],
  "signatures": [
    {"type": "signature", "page": 3, "label": "甲方签字", "confidence": 0.85,
     "image_path": "signatures/page_3_sig_甲方签字.png", "bbox": [150, 500, 400, 650]}
  ],
  "text": "纯文本全文...",
  "meta": {
    "pages": 5,
    "total_lines": 320,
    "total_chars": 12000,
    "source": "ocr",
    "seals_found": 1,
    "signatures_found": 2
  }
}
```

## 目录结构

```
ocr-digitalization/
├── SKILL.md              # 技能元数据 + 公共 API + CLI + 集成指南
├── README.md             # 本文件（使用说明）
├── checklists/
│   └── ocr-quality.md    # OCR 质量检查清单
└── scripts/
    ├── ocr_engine.py     # v5 主引擎（端到端流水线）
    └── ocr_backends.py   # 后端实现 + 预处理 + 纠错
```

## 常见问题

### Q: OCR 文字识别不准怎么办？

**排查步骤：**

1. **提高 DPI**：`--dpi 400` 或 `--dpi 600`（更慢但更准）
2. **更换引擎**：`--engine paddle`（如果已安装 PaddleOCR）
3. **检查扫描质量**：确认原图清晰、无倾斜、无反光
4. **预处理**：如果图片偏暗/模糊，可以先做对比度增强再 OCR
5. **查看纠错规则**：常见合同术语错误已在 `correct_ocr_errors` 中自动修正，可补充自定义规则

### Q: 印章检测不到怎么办？

**可能原因与解决：**

1. **印章不是红色**：黑色/蓝色印章无法通过红色像素检测，需要改用通用检测方案
2. **印章太小或太淡**：提高 DPI（`--dpi 400`）后重试
3. **印章被文字覆盖严重**：降低检测阈值（修改 `detect_red_seals` 中的最小面积参数）
4. **印章在骑缝处**：骑缝章当前版本不支持，仅检测完整印章

### Q: 手写签名检测不到怎么办？

1. **确认有关键词**：签名检测依赖"甲方签字"、"乙方签字"等关键词定位，如果标签文字缺失会检测不到
2. **检查 DPI**：分辨率太低会导致 OCR 漏识别关键词
3. **签名区域太小**：可以调整 `detect_signature_page_v2` 中的墨色密度阈值

### Q: 内存不足 / 速度太慢怎么办？

1. **降低 DPI**：`--dpi 200` 或 `--dpi 150`，精度略有下降但速度大幅提升
2. **关闭签名检测**：`--no-signatures`，跳过印章/签名检测步骤
3. **原生 PDF 跳过 OCR**：如果是可复制文本的 PDF，会自动走原生提取路径，非常快
4. **分批处理**：超大 PDF 可以拆分后逐页处理

### Q: 输出的签名截图坐标和实际位置对不上？

检查 DPI 是否一致。OCR 和检测必须使用相同 DPI 渲染的图片，否则坐标会偏移。
默认情况下 `pdf_to_images` 和 `ocr_image` 都使用同一套图片，坐标是对齐的。

## 与 contract-approval 的关系

```
contract-approval (SCA-001, L4 业务层)
        │
        ▼  依赖
ocr-digitalization (OCR-001, L2 基础设施层)
```

- **依赖方向**：contract-approval 依赖 ocr-digitalization
- **集成方式**：通过 `contract-approval/scripts/contract_ocr_v5.py` 兼容层调用
- **用途**：扫描件合同审核场景下，先 OCR 数字化再做条款解析和审核
- **解耦设计**：兼容层做 re-export，OCR 组件升级不影响业务层代码

## 架构地位

- **层级**：L2 基础设施层
- **组件 ID**：OCR-001
- **对偶组件**：Office 文档生成（ADR-016）— 一读一写
- **被依赖**：SCA-001（合同审批）、知识库扫描件导入、法务审查等
