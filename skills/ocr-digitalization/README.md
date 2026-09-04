# OCR 文档数字化组件（OCR-001）

L2 基础设施层组件。扫描件/图片 → 高精度文本 + 签署要素自动检测。

## 快速开始

```bash
# 激活虚拟环境
source .venv-ocr/bin/activate

# 端到端数字化
python skills/ocr-digitalization/scripts/ocr_engine.py \
  input.pdf \
  output.md \
  --signature-dir signatures/ \
  --json result.json
```

## 功能特性

- **多引擎**：RapidOCR（默认，纯 CPU）+ PaddleOCR（可选）
- **高精度**：300 DPI PyMuPDF 渲染 + 8 版本预处理 + 版面分析
- **场景纠错**：40+ 合同场景专项 OCR 纠错规则
- **签署要素检测**：红色印章检测 + 手写签名检测 + 签署页智能识别
- **坐标系统一**：OCR 与检测用同图，DPI 与像素严格对应，杜绝坐标偏移
- **调试可视化**：检测结果红框（印章）/绿框（签名）输出 debug.png

## 目录结构

```
ocr-digitalization/
├── SKILL.md              # 技能元数据 + 公共 API
├── README.md             # 使用说明
├── checklists/           # 检查清单
│   └── ocr-quality.md    # OCR 质量检查清单
└── scripts/
    ├── ocr_engine.py     # v5 主引擎（端到端流水线）
    └── ocr_backends.py   # 后端实现 + 预处理 + 纠错
```

## 架构地位

- **层级**：L2 基础设施层
- **组件 ID**：OCR-001
- **对偶组件**：Office 文档生成（ADR-016）— 一读一写
- **被依赖**：SCA-001（合同审批）、知识库扫描件导入、法务审查等
