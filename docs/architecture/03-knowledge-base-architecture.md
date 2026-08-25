# L3 业务知识库体系架构

> 本文档定义 L3 通用业务层的知识库体系架构。
> 是 L3 建设的"元层"——先于具体知识内容存在的设计。

## 0. 元信息

| 字段 | 值 |
|---|---|
| 文档版本 | 1.0 (2026-08-25) |
| 文档状态 | design |
| 决策状态 | 待 ADR 锁定 |
| 配套文档 | `../knowledge-base/README.md`（现有技术知识库） |
| 待办 | Rex 评审确认 → 开始知识文档建设 |

---

## 1. 定位

### 1.1 两个知识库的关系

系统中存在**两个知识库**，它们互补而非替代：

| 维度 | 技术知识库（已有） | 业务知识库（本文件） |
|------|-------------------|---------------------|
| 定位 | 技术基础设施视角 | 业务能力视角 |
| 组织方式 | 层级(L1~L4) × 阶段 × 类别 | 业务维度 × 角色 × 知识类型 |
| 举例 | "L2 可观测性设计" | "项目管理中的可观测性" |
| 工具 | kb_index.py（已有） | kb_index.py（复用 + 扩展） |
| 文档数 | 29 篇 | 预计 100+ 篇 |

### 1.2 交叉引用模型

```
技术知识库（纵深）          业务知识库（横向）
     ↓                          ↓
  L2 可观测性  ←————交叉引用————→  项目管理中的可观测性
  凭据管理     ←————交叉引用————→  SaaS 安全工程中的凭据策略
  持久化适配   ←————交叉引用————→  家庭理财中的数据持久化
```

**规则**：
- 技术文档中引用业务场景（"在项目管理中，可观测性用于..."）
- 业务文档中引用技术实现（"项目状态追踪依赖 L2 持久化组件"）
- 交叉引用通过 `xref` frontmatter 字段实现

---

## 2. 业界最佳实践

### 2.1 2026 知识库进化三阶段

**来源**：eGain / Atlan / Enterprise Knowledge

| 阶段 | 特征 | 我们的位置 |
|------|------|-----------|
| Stage 1: 静态 Wiki | 文档堆积，关键字搜索 | ❌ 已过 |
| Stage 2: 可搜索文档 | 结构化索引，标签检索 | ✅ 当前（kb_index.py） |
| Stage 3: 治理型检索 substrate | AI 自动化 + 治理 + 语义关系 | 🎯 目标 |

### 2.2 关键设计原则

**来源**：Enterprise Knowledge Graph / Atlan / eGain

| 原则 | 说明 | 我们的实现 |
|------|------|-----------|
| **Taxonomy（分类法）** | 层级分类 + 受控词表 | 业务维度 → 子领域 → 文档 |
| **Ontology（本体）** | 概念间语义关系 | 角色间协作关系 + 阶段间契约 |
| **交叉引用** | 文档间双向链接 | xref frontmatter + kb_index.py --xref |
| **治理** | 版本 + 审查 + 过期管理 | last_reviewed + version + 季度审查 |
| **语义检索** | 超越关键字的意图理解 | memory_search（向量 + 关键字双轨） |
| **迭代演进** | 不追求完美 schema 先行 | 先最小可用，持续扩展 |

### 2.3 反模式（避免）

| 反模式 | 症状 | 我们的防范 |
|--------|------|-----------|
| 瀑布式设计 | schema 设计超过 6 个月 | 迭代式：先建 → 验证 → 调整 |
| 完美主义 | 想覆盖所有实体再开始 | 先建核心 10 篇 → 验证 → 扩展 |
| 孤立建设 | 业务知识库与技术知识库不关联 | 交叉引用规则强制关联 |
| 缺乏治理 | 知识过时无人维护 | last_reviewed + 季度审查提醒 |

---

## 3. 业务知识库目录结构

### 3.1 总体结构

```
knowledge-base/by-category/business/
├── README.md                        # L3 业务知识库总索引
├── INDEX.md                         # 快速索引（标签/角色/维度）
│
├── methodology/                     # L3 建设方法论
│   ├── README.md
│   ├── dimension-design.md
│   ├── role-definition.md           ✅ 已就绪
│   ├── knowledge-authoring.md       ✅ 已就绪
│   ├── quality-standard.md
│   └── lessons-learned.md
│
├── project-management/              # 项目管理维度
├── contract-management/             # 合同管理维度
├── after-sales/                     # 售后管理维度
├── implementation/                  # 实施管理维度
├── family-finance/                  # 家庭理财维度
│
├── software-development/            # 软件开发（全生命周期）
│   ├── README.md
│   ├── knowledge/                  # 跨阶段通用知识
│   ├── roles/                      # 跨阶段通用角色
│   ├── templates/                  # 跨阶段通用模板
│   └── {dimension}/                # 各阶段独立目录（01-08）
│
└── cross-cutting/                   # 横切知识（跨业务领域）
    ├── communication/              # 沟通方法论
    ├── decision-making/            # 决策框架
    ├── stakeholder-management/    # 干系人管理
    └── risk-management/            # 风险管理（通用）
```

### 3.2 单维度标准结构

每个业务维度遵循统一结构：

```
<dimension>/
├── README.md                        # 维度索引
├── knowledge/                       # 业务知识（按子领域分目录）
│   ├── <sub-area-1>/
│   │   ├── <topic>.md
│   │   └── ...
│   ├── <sub-area-2>/
│   └── ...
├── roles/                           # 角色定义
│   ├── <role-1>/
│   │   ├── SOUL.md
│   │   ├── AGENTS.md
│   │   └── IDENTITY.md
│   ├── <role-2>/
│   └── ...
└── templates/                       # 交付物模板
    └── <template>.md
```

---

## 4. 知识文档标准

### 4.1 Frontmatter 规范

```yaml
---
title: "文档标题（≤30字）"
description: "文档概述（≤200字）"
source: "权威来源（书籍/标准/官网）"
version: "知识体系版本"
category: "business"                  # 固定：标记为业务知识库
dimension: "project-management"        # 所属业务维度
sub_area: "pmbok-8th"                 # 子领域
type: "industry"                      # industry / theory / experience
tags: ["tag1", "tag2", "tag3"]        # ≥ 3 个
xref:                                # 交叉引用（可选）
  - path: "by-layer/L2-infrastructure/observability/DESIGN.md"
    relation: "implements"            # implements / extends / related
  - path: "by-category/project-management/roles/project-manager/AGENTS.md"
    relation: "referenced_by"
last_reviewed: "2026-08-25"
---
```

### 4.2 交叉引用关系类型

| 关系 | 说明 | 示例 |
|------|------|------|
| `implements` | 技术实现业务需求 | L2 可观测性 ← 项目管理中的可观测性 |
| `extends` | 业务扩展技术能力 | 项目管理 → L2 持久化（项目状态存储） |
| `referenced_by` | 被角色/模板引用 | 知识文档 ← 角色 AGENTS.md |
| `related` | 相关但非直接依赖 | 合同管理 ↔ 项目管理 |
| `depends_on` | 前置依赖 | 测试工程 → 前后端开发（需要可测试版本） |

### 4.3 标签体系

**维度标签**（必选 1 个）：
```
project-management, contract-management, after-sales, implementation,
family-finance, product-design, system-architecture, frontend-dev,
backend-dev, testing, devops-sre, data-engineering, security-engineering
```

**知识类型标签**（必选 1 个）：
```
industry-practice, theoretical-knowledge, project-experience
```

**流程阶段标签**（可选）：
```
planning, execution, monitoring, closing, operations
```

**通用标签**（可选，≥ 1 个）：
```
risk, quality, compliance, communication, documentation, automation
```

---

## 5. 知识检索体系

### 5.1 双轨检索

| 检索方式 | 工具 | 适用场景 |
|----------|------|----------|
| **语义检索** | memory_search（向量 + 关键字） | 自然语言问题，跨维度召回 |
| **结构化检索** | kb_index.py --query | 精确查询（维度/标签/类型） |

### 5.2 检索场景

| 场景 | 检索方式 | 示例 |
|------|----------|------|
| 角色激活 | 语义检索 | "帮我管理项目" → 召回项目管理维度知识 |
| 知识查找 | 结构化检索 | `kb_index.py --query dimension=project-management type=industry` |
| 交叉引用 | kb_index.py --xref | 查看某篇文档的所有关联文档 |
| 维度导航 | README.md 索引 | 浏览某个维度的全部知识 |

### 5.3 知识召回链

```
用户问题
  ↓
意图识别（关键词 + 上下文）
  ↓
匹配业务维度
  ↓
memory_search（语义检索，召回相关知识）
  ↓
加载角色（SOUL + AGENTS）
  ↓
角色 + 知识 → 执行任务
```

---

## 6. 治理机制

### 6.1 知识生命周期

```
创建 → 审查 → 发布 → 使用 → 定期审查 → 更新/归档
  ↑                                          │
  └──────────────────────────────────────────┘
```

### 6.2 审查标准

| 检查项 | 标准 | 频率 |
|--------|------|------|
| 来源有效性 | 来源链接可访问，版本未过时 | 每季度 |
| 内容准确性 | 与最新版本知识体系一致 | 每季度 |
| 交叉引用完整性 | xref 指向的文档存在且有效 | 每月 |
| 检索有效性 | memory_search 能正确召回 | 每月 |

### 6.3 版本管理

- 知识文档标注 `version`（如 "PMBOK 8th"）
- 知识体系升级时，批量审查受影响的文档
- 重大变更记录在 `methodology/lessons-learned.md`

---

## 7. kb_index.py 扩展建议

现有 `kb_index.py` 已支持 6 项子能力。为支持业务知识库，建议扩展：

| 扩展 | 说明 | 优先级 |
|------|------|--------|
| `--query dimension=<dim>` | 按业务维度查询 | P0 |
| `--query xref=<path>` | 查询某文档的交叉引用 | P0 |
| `--query role=<role>` | 查询某角色的知识引用 | P1 |
| `--stats business` | 业务知识库统计（按维度/角色） | P1 |
| `--validate business` | 业务知识库 frontmatter 校验 | P0 |
| `--emit-index business` | 生成业务知识库 INDEX.md | P1 |

---

## 8. 实施计划

### 阶段 0: 知识库体系架构（本文件） ← 当前

| 步骤 | 内容 | 产出 |
|------|------|------|
| 1 | 设计知识库体系架构 | 本文件 |
| 2 | 定义 frontmatter 规范 | §4.1 |
| 3 | 定义交叉引用规则 | §4.2 |
| 4 | 定义标签体系 | §4.3 |
| 5 | 扩展 kb_index.py | 新增业务知识库查询能力 |

### 阶段 1: 项目管理维度知识

| 步骤 | 内容 | 产出 |
|------|------|------|
| 1 | PMBOK 8th 核心知识 | 4 篇 |
| 2 | 敏捷方法论 | 4 篇 |
| 3 | 风险管理 | 3 篇 |
| 4 | 干系人管理 | 3 篇 |
| 5 | 交叉引用到技术知识库 | xref 标注 |

### 阶段 2: 其他维度知识（按优先级）

---

## 9. 验证标准

| 检查项 | 标准 | 验证方式 |
|--------|------|----------|
| 目录结构合规 | 所有维度遵循标准结构 | `kb_index.py --validate business` |
| frontmatter 完整 | 必填字段齐全 | `kb_index.py --validate` |
| 交叉引用有效 | xref 指向的文档存在 | `kb_index.py --xref` |
| 检索召回率 | 业务问题召回相关知识 ≥ 80% | `memory_search` 实测 |
| 标签覆盖率 | 每篇文档 ≥ 3 个标签 | `kb_index.py --tags` |
| 知识时效性 | last_reviewed ≤ 90 天 | 季度审查 |

---

## 10. 变更历史

| 日期 | 版本 | 变更 |
|------|------|------|
| 2026-08-25 | 1.0 | 初始设计 |

---

## 相关文档

- 系统架构主文档: `00-system-architecture.md`
- L3 通用业务层: `02-generic-business-layer.md`
- 现有技术知识库: `../knowledge-base/README.md`
- 经验沉淀模型: `../knowledge-base/by-category/project-experience/README.md`
