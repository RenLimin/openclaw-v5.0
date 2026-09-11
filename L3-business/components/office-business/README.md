# office-business

**定位：** L3 业务层 — 办公业务模板与角色库，提供合同/报告/方案/演示文稿的标准模板和 Agent 角色定义。

## 功能列表

- 合同模板（销售合同、服务合同）
- 报告模板（周报、月报、季报、年报）
- 方案模板（项目方案、技术方案）
- 演示文稿模板（项目状态、会议纪要）
- Agent 角色定义（业务分析师、文档工程师）
- 知识库（变量系统、结构指南、文档规范）
- 模板索引（`index.json`，11 个模板）

## 目录结构

```
office-business/
├── roles/
│   ├── business-analyst/             # 业务分析师角色
│   │   ├── IDENTITY.md
│   │   ├── SOUL.md
│   │   └── AGENTS.md
│   └── document-engineer/           # 文档工程师角色
│       ├── IDENTITY.md
│       ├── SOUL.md
│       └── AGENTS.md
├── templates/
│   ├── index.json                    # 模板索引（11 个）
│   ├── contract/
│   │   ├── sales-contract.md        # 销售合同模板
│   │   └── service-contract.md      # 服务合同模板
│   ├── report/
│   │   ├── weekly-report.md         # 周报模板
│   │   ├── monthly-report.md        # 月报模板
│   │   ├── quarterly-report.md      # 季报模板
│   │   └── annual-report.md         # 年报模板
│   ├── proposal/
│   │   ├── project-proposal.md      # 项目方案模板
│   │   └── technical-proposal.md    # 技术方案模板
│   └── presentation/
│       ├── project-status.md         # 项目状态演示
│       └── meeting-minutes.md        # 会议纪要演示
└── knowledge/
    ├── README.md
    ├── variable-system.md            # 变量系统说明
    ├── structure-guide.md            # 结构指南
    └── document-spec.md              # 文档规范
```

## 使用方式

模板通过 `templates/index.json` 索引，按 category 分类检索。角色定义通过 `roles/<role>/` 下的 IDENTITY/SOUL/AGENTS 三件套配置。

```bash
# 查看模板索引
cat templates/index.json

# 使用模板
cat templates/report/weekly-report.md
```

## 依赖

- 无运行时依赖（纯 Markdown 模板）
- 配合 office-generation 引擎进行文档渲染
