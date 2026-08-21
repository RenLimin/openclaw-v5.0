# docs/ — 文档中心

> 系统所有正式文档的根目录。AI agent 和人类共同维护。

## 目录结构

```
docs/
├── README.md                          (本文件)
│
├── architecture/                      系统架构
│   └── 00-system-architecture.md      4 层架构 + OpenClaw 契约 + 演进路线
│
└── knowledge-base/                    知识库
    ├── README.md                      三维模型说明
    ├── INDEX.md                       快速索引
    ├── by-layer/                      按层级 (L1~L4)
    ├── by-stage/                      按阶段 (design/develop/manage)
    ├── by-category/                   按类别 (业界/理论/经验)
    │   └── project-experience/
    │       ├── README.md              经验沉淀模型
    │       ├── correct/               正确经验
    │       ├── incorrect/             错误经验(踩坑)
    │       └── adr/                   架构决策记录
    ├── cross-cutting/                 横切关注点
    └── templates/                     模板
        ├── KB-ARTICLE.md
        ├── EXPERIENCE-CARD.md
        ├── ADR.md
        └── LIBRARY-ITEM.md
```

## 文档治理

| 文档类型 | 创建时机 | 维护者 |
|---|---|---|
| 架构文档 | 系统级决策 | 所有人 |
| 知识文章 (KB) | 学习中/参考中 | 引用者 |
| 经验卡片 (EXP) | 踩坑/发现做法时 | 踩坑者 |
| ADR | 重大架构决策 | 决策参与者 |

详见 `knowledge-base/README.md` 的使用规范。

## 新增文档的流程

1. **确定三维坐标** (层级 × 阶段 × 类别)
2. **选择模板** (`templates/`)
3. **填 frontmatter**
4. **放置到对应目录**
5. **更新 INDEX.md**（如适用）
6. **如有架构影响** → 同步到 `MEMORY.md`
