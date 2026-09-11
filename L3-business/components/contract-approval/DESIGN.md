# contract-approval

## 设计目标

基于《民法典》合同编，为销售合同审批提供 OCR 识别、条款拆解、风险扫描、审核建议全流程自动化。解决人工审批效率低、标准不统一、风险遗漏的问题。

## 架构决策

- **工作流模式**：本组件为工作流模式，由 Agent 技能（contract-approval skill）调用，无独立 CLI 入口
- **纯逻辑层**：L3 层只做纯计算（条款解析、风险扫描），零副作用、可单元测试
- **L4 编排层**：持久化、状态机、文档生成由 L4 层（office-contract）负责
- **输入/输出分离**：`input/` 存放原始合同文本，`output/` 存放审批产出物（Excel/Word/JSON）
- **多格式输出**：支持 Excel 分析报告、Word 合同文档、JSON 结构化结果

## 模块划分

```
contract-approval/
├── input/                      # 输入合同文本
│   └── xinchuang-tech-service.txt
├── output/                     # 审批产出物
│   ├── CON-2026-001.docx       # 生成合同（Word）
│   ├── audit_report_CON-2026-002.txt  # 审批报告（文本）
│   ├── audit_report_CON-2026-002.json # 结构化结果
│   ├── parsed_clauses_CON-2026-002.txt # 条款拆解
│   ├── analysis_v3/            # 分析报告（Markdown）
│   │   ├── 1-合同条款拆解.md
│   │   ├── 2-统一审核标准.md
│   │   └── 3-逐条审核与整改建议.md
│   └── [案例目录]/              # 按案例归档
└── README.md
```

## 关键接口/数据结构

本组件为工作流模式，核心逻辑由 skill 编排，无独立 Python 模块。

典型流程：
1. 合同扫描件 → OCR 识别（Tesseract / 远程多模态 API）
2. 文本 → 条款拆解（自动分段、条款分类）
3. 条款 → 风险扫描 + 审核建议（基于《民法典》规则）
4. 输出 → Excel 报告 + Word 合同

## 依赖关系

- **依赖**：OCR 能力（Tesseract / 远程多模态 API）、python-docx、openpyxl
- **被依赖**：`office-contract`（L4 层，调用本组件的风险扫描规则和审核标准）

## 演进方向

1. **规则库扩展**：增加更多合同类型（采购、租赁、劳务）的审核标准
2. **NLP 增强**：引入 LLM 进行条款语义理解，替代关键词匹配
3. **批量审批**：支持多合同并行处理
4. **审批历史追溯**：记录每次审批的变更轨迹
