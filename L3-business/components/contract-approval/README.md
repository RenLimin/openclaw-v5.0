# contract-approval

**定位：** L3 业务层 — 合同审批工作流，基于《民法典》合同编进行 OCR 识别、条款拆解、风险扫描。

## 功能列表

- 合同 OCR 识别（扫描件/图片 → 结构化文本）
- 合同条款拆解（自动分段、条款分类）
- 统一审核标准（合规性检查）
- 逐条审核与整改建议（风险条款标注）
- 审批分析报告生成（Excel 输出）
- 合同文档生成（Word 输出）
- 审批结果归档（JSON + 文本）

## 目录结构

```
contract-approval/
├── input/                              # 输入合同文本
│   └── xinchuang-tech-service.txt
├── output/                             # 审批产出物
│   ├── CON-2026-001.docx               # 生成合同
│   ├── CON-2026-003.docx
│   ├── audit_report_CON-2026-002.txt    # 审批报告
│   ├── audit_report_CON-2026-002.json   # 结构化结果
│   ├── parsed_clauses_CON-2026-002.txt  # 条款拆解
│   ├── analysis_v3/                    # 分析报告（Markdown）
│   │   ├── 1-合同条款拆解.md
│   │   ├── 2-统一审核标准.md
│   │   └── 3-逐条审核与整改建议.md
│   ├── 聚信得仁采购合同/                 # 案例：采购合同审批
│   └── XSZS2603090136/                  # 案例：指南针科技审批
└── DESIGN.md
```

## 使用方式

本组件为工作流模式，由 Agent 技能（`contract-approval` skill）调用，无独立 CLI 入口。

典型流程：
1. 合同扫描件 → OCR 识别
2. 文本 → 条款拆解
3. 条款 → 风险扫描 + 审核建议
4. 输出 → Excel 报告 + Word 合同

## 依赖

- OCR 能力（Tesseract / 远程多模态 API）
- python-docx（Word 生成）
- openpyxl / xlsxwriter（Excel 生成）
- contract-approval skill（工作流编排）
