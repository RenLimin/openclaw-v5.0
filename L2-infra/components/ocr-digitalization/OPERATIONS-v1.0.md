# ocr-digitalization — 操作手册 (OPERATIONS)

> 版本: v1.0 · 日期: 2026-09-28

## 安装与启动

### 环境依赖

- python3
- RapidOCR / PaddleOCR
- Tesseract（可选）

### 启动命令

```bash
python3 ocr_digitize.py <image_path>
python3 contract_ocr.py <contract_image>
```

### 健康检查

```bash
python3 -c "from ocr_digitize import OCREngine; print('OK')"
```

## 操作指南

### 场景一：单页识别

```bash
python3 L2-infra/components/ocr-digitalization/ocr_digitize.py scan.jpg
```

### 场景二：批量识别

```bash
for img in scans/*.jpg; do
  python3 L2-infra/components/ocr-digitalization/ocr_digitize.py "$img"
done
```

### 场景三：合同识别

```bash
python3 L2-infra/components/ocr-digitalization/contract_ocr.py contract.pdf
```

## 配置说明

- 主引擎: RapidOCR
- 备选: PaddleOCR
- DPI: 600
- 预处理: 8 版本

## 故障排查

### 识别率低

- **症状**: 文本乱码
- **原因**: 图像质量差
- **解决**: 提高扫描质量或增强预处理

### 引擎不可用

- **症状**: 引擎加载失败
- **原因**: 依赖缺失
- **解决**: 安装对应 OCR 库
