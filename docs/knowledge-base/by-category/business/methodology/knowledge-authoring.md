---
id: METHODOLOGY-005
title: "知识文档编写指南"
description: "L3 业务知识文档的标准化编写规范：frontmatter 模板、内容结构、写作原则、质量标准"
source: "L3 知识库体系架构 v1.0 / L3 架构设计 v1.5"
version: "1.1"
dimension: "methodology"
sub_area: "knowledge-authoring"
stage: "manage"
tags: ["l3", "methodology", "knowledge-authoring", "authoring-guide"]
last_reviewed: "2026-09-06"
---

# 知识文档编写指南

> L3 业务知识文档的标准化编写规范。

## 1. 文档模板

每个知识文档必须包含以下 frontmatter：

```markdown
---
id: <唯一标识，如 METHODOLOGY-001>
title: "文档标题（≤30字）"
description: "文档概述（≤200字）"
source: "权威来源（书籍/标准/官网）"
version: "知识体系版本（如 PMBOK 8th）"
dimension: "业务维度（methodology/project-management/...）"
sub_area: "子领域标签（可选）"
stage: "design | develop | manage"
tags: ["tag1", "tag2", "tag3"]
last_reviewed: "YYYY-MM-DD"
---
```

**字段要求**：

| 字段 | 要求 |
|------|------|
| id | 唯一，跨知识库不重复（`kb_index.py --validate` 强校验） |
| title | ≤ 30 字，包含关键词 |
| description | ≤ 200 字，概述核心内容 |
| source | 必须标注权威来源（书籍/标准/官网），可追溯 |
| version | 知识体系版本（如 PMBOK 8th / ITIL 4） |
| dimension | 必须为合法维度名（`VALID_DIMENSIONS`） |
| tags | ≥ 3 个标签，支持检索 |
| last_reviewed | 最后审查日期，驱动季度审查 |

## 2. 内容结构

### 标准结构

```markdown
# 标题

> 一句话摘要

## 1. 概述
- 是什么
- 为什么重要
- 适用场景

## 2. 核心概念
- 关键术语定义
- 核心原则/规则

## 3. 实践指南
- 步骤/流程
- 最佳实践
- 常见误区

## 4. 工具与模板
- 可用的模板/检查清单
- 工具推荐

## 5. 案例/示例
- 实际应用场景
- 输入/输出示例

## 6. 注意事项
- 边界条件
- 常见错误
- 与其他知识的关系

## 7. 参考资料
- 来源链接
- 延伸阅读
```

### 精简结构（≤500 字文档）

```markdown
# 标题

> 一句话摘要

## 核心要点
- 要点 1
- 要点 2
- 要点 3

## 适用场景
- 场景 1
- 场景 2

## 注意事项
- 注意 1
- 注意 2
```

## 3. 写作原则

| 原则 | 说明 |
|------|------|
| **权威来源** | 必须标注来源，不编造 |
| **中文为主** | 术语保留英文原文（如 "Sprint Backlog（冲刺待办）"） |
| **结构化** | 标题 + 列表 + 表格，避免大段叙述 |
| **可操作** | 每篇知识应能直接指导行动 |
| **有时效** | 标注版本/年份，便于后续更新 |
| **可检索** | 标题和描述包含关键词，tags ≥ 3 |

## 4. 质量标准

- [ ] frontmatter 完整（id / title / description / source / version / dimension / tags / last_reviewed）
- [ ] 来源标注清晰
- [ ] 结构遵循模板
- [ ] 中文为主，术语保留英文
- [ ] 包含"适用场景"和"注意事项"
- [ ] 字数 ≥ 200 字（确保信息密度）
- [ ] `kb_index.py --validate` 无硬性错误

## 5. 参考资料

- 维度设计：[dimension-design.md](./dimension-design.md)
- 角色定义：[role-definition.md](./role-definition.md)
- 质量标准：[quality-standard.md](./quality-standard.md)

## 变更历史

- 2026-08-25: 初始版本
- 2026-09-06: 对齐 kb_index.py schema — 补 id/stage 字段要求，版本升至 1.1
