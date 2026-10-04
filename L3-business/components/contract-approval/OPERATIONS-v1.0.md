# contract-approval — 操作手册 (OPERATIONS)

> 版本: v1.0 · 日期: 2026-09-28

## 1. 安装与启动

### 1.1 环境依赖

- Python 3.12+
- Tesseract OCR（可选，本地识别）
- python-docx: `pip install python-docx`
- openpyxl: `pip install openpyxl`

### 1.2 安装步骤

```bash
cd L3-business/components/contract-approval
# 无需额外安装，纯逻辑层
```

### 1.3 启动命令

本组件为工作流模式，由 Agent 技能调用，无独立启动命令。

### 1.4 健康检查

```bash
# 验证模块可导入
python3 -c "from contract_approval import *; print('OK')"
```

## 2. 操作指南

### 2.1 场景一：审批新合同

1. 准备合同扫描件（PDF/图片）
2. 调用 OCR 识别 → 获取文本
3. 条款拆解 → 风险扫描 → 生成建议
4. 导出报告（Excel/Word/JSON）
5. 按建议修改合同

### 2.2 场景二：批量审批

1. 将多份合同放入 `input/` 目录
2. 批量执行审批流程
3. 汇总所有报告

### 2.3 场景三：自定义规则

1. 编辑风险扫描规则文件
2. 重新执行扫描
3. 验证新规则生效

## 3. 配置说明

### 3.1 配置文件

- 风险规则: 内置《民法典》13 项规则
- 输出格式: Excel/Word/JSON 可选

### 3.2 默认值

- OCR 引擎: Tesseract（本地优先）
- 输出格式: 三格式同时输出
- 建议优先级: 高/中/低三级

## 4. 故障排查

### 4.1 OCR 识别失败

- **症状**: 文本乱码或空白
- **原因**: 图像质量差或 Tesseract 未安装
- **解决**: 检查图像质量，安装 Tesseract 或切换远程 API

### 4.2 条款拆解不完整

- **症状**: 条款数量少于预期
- **原因**: 分段规则不匹配
- **解决**: 检查分段规则，调整正则表达式

### 4.3 风险扫描漏报

- **症状**: 已知风险未检出
- **原因**: 规则库不完整
- **解决**: 扩展规则库，添加新规则

## 5. FAQ

**Q1: 支持哪些合同格式？**
A: PDF（扫描件）、JPG、PNG、TIFF

**Q2: 识别准确率如何？**
A: 标准打印件 > 95%，手写件 > 85%

**Q3: 如何扩展风险规则？**
A: 在规则文件中添加新规则，格式见文档

## 6. 附录

### 6.1 接口清单

- `ocr_recognize(image_path) → text`
- `parse_clauses(text) → List[Clause]`
- `scan_risks(clauses) → List[RiskItem]`
- `generate_suggestions(risks) → List[Suggestion]`
- `export_report(result, format) → file_path`

### 6.2 依赖

- OCR: Tesseract / 远程多模态 API
- Word: python-docx
- Excel: openpyxl
