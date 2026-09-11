# office-business

## 设计目标

为办公业务提供标准化模板与角色定义，覆盖合同、报告、方案、演示文稿四大类文档模板，以及业务分析师、文档工程师两类 Agent 角色。解决文档风格不统一、Agent 角色边界模糊的问题。

## 架构决策

- **纯 Markdown 模板**：无运行时依赖，模板可被任何 Agent 或人工直接使用
- **角色三件套**：每个角色通过 IDENTITY.md + SOUL.md + AGENTS.md 定义人设、灵魂和行为规范
- **模板索引化**：`templates/index.json` 提供机器可读的模板目录，支持程序化检索
- **知识库分离**：`knowledge/` 存放变量系统、结构指南、文档规范等元知识
- **分类组织**：模板按 category（contract/report/proposal/presentation）分类

## 模块划分

```
office-business/
├── roles/                      # Agent 角色定义
│   ├── business-analyst/       # 业务分析师
│   │   ├── IDENTITY.md         # 身份定义
│   │   ├── SOUL.md             # 价值观与风格
│   │   └── AGENTS.md           # 行为规范
│   └── document-engineer/      # 文档工程师
│       ├── IDENTITY.md
│       ├── SOUL.md
│       └── AGENTS.md
├── templates/                  # 文档模板
│   ├── index.json              # 模板索引（11 个）
│   ├── contract/               # 合同模板
│   │   ├── sales-contract.md
│   │   └── service-contract.md
│   ├── report/                 # 报告模板
│   │   ├── weekly-report.md
│   │   ├── monthly-report.md
│   │   ├── quarterly-report.md
│   │   └── annual-report.md
│   ├── proposal/               # 方案模板
│   │   ├── project-proposal.md
│   │   └── technical-proposal.md
│   └── presentation/           # 演示文稿模板
│       ├── project-status.md
│       └── meeting-minutes.md
└── knowledge/                  # 知识库
    ├── variable-system.md      # 变量系统说明
    ├── structure-guide.md      # 结构指南
    └── document-spec.md        # 文档规范
```

## 关键接口/数据结构

本组件为纯模板/知识库，无编程接口。

使用方式：
- 模板通过 `templates/index.json` 索引检索
- 角色通过 `roles/<role>/` 三件套配置
- 知识通过 `knowledge/` 文档查阅

## 依赖关系

- **依赖**：无运行时依赖（纯 Markdown）
- **被依赖**：`office-contract`（L4 层，复用合同模板和文档规范）

## 演进方向

1. **模板扩展**：增加更多文档类型（会议纪要、需求文档、设计文档）
2. **变量系统实现**：从文档描述升级为可执行的变量替换引擎
3. **角色扩充**：增加项目经理、技术架构师等角色定义
4. **多语言支持**：模板中英双语化
