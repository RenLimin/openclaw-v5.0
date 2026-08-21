# 知识库索引

> 按主题/标签组织的快速检索入口。AI agent 和人类均可读。

## 1. 快速链接

| 类别 | 路径 | 用途 |
|---|---|---|
| 系统架构 | `../architecture/00-system-architecture.md` | 分层架构、契约、演进路线 |
| 经验模型 | `./by-category/project-experience/README.md` | 经验沉淀规则 |
| 模板 | `./templates/` | 知识文章/卡片/ADR 模板 |
| 横切关注点 | `./cross-cutting/` | 安全/可观测/合规/成本/协作/知识管理 |

## 2. 按主题分类

### 2.1 OpenClaw 相关
- 系统层契约：`../architecture/00-system-architecture.md#4-openclaw-契约边界`
- 官方文档：https://docs.openclaw.ai

### 2.2 架构模式
_(待补充)_

### 2.3 工程实践
_(待补充)_

### 2.4 业务领域
_(待补充)_

### 2.5 横切关注点
- 安全：`./cross-cutting/security/`
- 可观测：`./cross-cutting/observability/`
- 合规：`./cross-cutting/compliance/`
- 成本：`./cross-cutting/cost/`
- 协作：`./cross-cutting/collaboration/`
- 知识管理：`./cross-cutting/knowledge-management/`

## 3. 标签云

_(自动生成中 — 每篇文档的 frontmatter 都会被索引到这里)_

## 4. 最近更新

| 日期 | 文档 | 变更 |
|---|---|---|
| 2026-08-21 | 知识库初始化 | 创建三维模型骨架 |
| 2026-08-21 | 架构文档 v0.2 | 4 层架构 + L1~L4 内部细节 |
| 2026-08-21 | [EXP-20260821-001] Tavily 显式工具解锁 | tools.alsoAllow 配置法 |
| 2026-08-21 | [ADR-202608-001] 4 层架构决策 | accepted |
| 2026-08-21 | [ADR-202608-002] 知识库三维模型 | accepted |
| 2026-08-21 | [ADR-202608-003] 知识库承载形式路径 | accepted |
| 2026-08-21 | [ADR-202608-004] 可观测性适配 | accepted + 实现 (agent_observer.py) |
| 2026-08-21 | [EXP-20260821-002] GitHub 凭据配置 | file-based credential helper |
| 2026-08-21 | [ADR-202608-005] 凭据管理通用化 | accepted + 实现 (credentials.sh) |
| 2026-08-21 | 持久化适配设计 | DESIGN.md + ADR-006 (proposed) |
