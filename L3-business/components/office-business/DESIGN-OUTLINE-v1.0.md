# office-business — 设计大纲 (DESIGN-OUTLINE)

> 版本: v1.0 · 日期: 2026-09-28

## 1. 整体架构

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
│   ├── report/                 # 报告模板
│   ├── proposal/               # 方案模板
│   └── presentation/           # 演示文稿模板
└── knowledge/                  # 知识库
    ├── variable-system.md      # 变量系统说明
    ├── structure-guide.md      # 结构指南
    └── document-spec.md        # 文档规范
```

## 2. 模块划分

| 模块 | 职责 |
|---|---|
| roles/ | 角色三件套定义 |
| templates/ | Markdown 模板 |
| knowledge/ | 变量/规范元知识 |

## 3. 接口契约

无代码接口，纯 Markdown 文件引用。

## 4. 技术选型

- 纯 Markdown，无运行时依赖
- JSON 索引（`index.json`）供程序化检索

## 5. 分层约束

- L3 通用层：不绑定专有业务
- 可被 L4 继承引用
