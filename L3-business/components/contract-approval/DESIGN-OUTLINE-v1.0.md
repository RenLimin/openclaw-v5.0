# contract-approval — 设计大纲 (DESIGN-OUTLINE)

> 版本: v1.0 · 日期: 2026-09-28

## 1. 整体架构

```
合同扫描件
    ↓ OCR 识别 (Tesseract / 远程多模态)
合同文本
    ↓ 条款拆解 (自动分段 + 条款分类)
条款列表
    ↓ 风险扫描 (《民法典》13 项规则)
风险项列表
    ↓ 审核建议生成 (优先级排序)
审批报告 (Excel/Word/JSON)
```

## 2. 模块划分

| 模块 | 职责 | 输入 | 输出 |
|---|---|---|---|
| OCR 适配器 | 图像→文本 | 扫描件/图片 | 结构化文本 |
| 条款拆解器 | 文本→条款列表 | 合同文本 | 分类条款列表 |
| 风险扫描器 | 条款→风险项 | 条款列表 | 风险项列表 |
| 建议生成器 | 风险→整改建议 | 风险项列表 | 优先级建议 |
| 报告生成器 | 结果→多格式 | 全量结果 | Excel/Word/JSON |

## 3. 接口契约

- `ocr_recognize(image_path) → text`
- `parse_clauses(text) → List[Clause]`
- `scan_risks(clauses) → List[RiskItem]`
- `generate_suggestions(risks) → List[Suggestion]`
- `export_report(result, format) → file_path`

## 4. 技术选型

- OCR: Tesseract (本地) + 远程多模态 API (兜底)
- Word: python-docx
- Excel: openpyxl
- JSON: stdlib json

## 5. 分层约束

- L3 纯逻辑层：零副作用、可单元测试
- L4 编排层：持久化、状态机、文档生成
- 单向依赖：L4 → L3，反向禁止
