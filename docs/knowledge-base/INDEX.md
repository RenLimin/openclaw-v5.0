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

### 2.2 按三维检索（推荐）

手维分类已被工具取代。用 `scripts/kb_index.py`：

```bash
python3 scripts/kb_index.py --query layer=L2 stage=manage
python3 scripts/kb_index.py --query tag=cron
python3 scripts/kb_index.py --tags      # tag 聚合
python3 scripts/kb_index.py --xref      # 交叉引用 + 孤岛/断链
python3 scripts/kb_index.py --stats     # 三维分布
python3 scripts/kb_index.py --validate  # schema 校验（pre-commit 已集成）
```

全量条目、标签云、三维分布见下方 **§5 自动生成区**。

### 2.3 横切关注点
- 安全：`./cross-cutting/security/`
- 可观测：`./cross-cutting/observability/`
- 合规：`./cross-cutting/compliance/`
- 成本：`./cross-cutting/cost/`
- 协作：`./cross-cutting/collaboration/`
- 知识管理：`./cross-cutting/knowledge-management/`

## 3. 标签云

见 §5 自动生成区（由 `kb_index.py --emit-index` 维护，不再手写）。

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
| 2026-08-21 | 持久化适配 | ADR-006 accepted + 实现 (connection/migration/repository) |
| 2026-08-21 | [EXP-20260821-003] compaction 死锁与上下文管理 | 跨模型切换溢出修复（§3.3 数值已被 EXP-004 修正）|
| 2026-08-22 | [EXP-20260822-004] contextWindow 实测法 | 二分探边界；glm-5.3=1M / minimax-m3=1M / ark-code-latest=224k |
| 2026-08-22 | [约定] commit 与配置变更 | Conventional Commits + 配置快照防丢失 |
| 2026-08-22 | [EXP-20260822-005] cron delivery 污染 job 状态 | 无 channel 环境须 delivery.mode=none；每日观测摘要已转 ok |
| 2026-08-22 | [ADR-202608-007] L2 配置管理 | accepted + 实现 (config.sh: audit/snapshot/diff/apply/probe) |
| 2026-08-22 | 架构文档 v0.4 | 配置管理组件从“复用 L1”→“已建设”；ctx 改为实测值 |
| 2026-08-22 | [ADR-202608-008] L2 工具策略治理 | accepted；三态模型（denied / allowed-but-broken / allowed-and-working）+ 六项审计 |
| 2026-08-22 | 架构文档 v0.5 | §5.4 回答原预留问题；ADR 清单补至 008；**L2 核心组件建设完成** |
| 2026-08-22 | [ADR-202608-009] L2 记忆语义检索 | accepted + 实测；本地 GGUF embedding 修复 memory_search 静默降级 |
| 2026-08-22 | 架构文档 v0.6 | 新增记忆语义检索组件 |
| 2026-08-22 | [EXP-20260822-006] WeCom aibot 无法主动推送 | 实测 errcode 93006；README 误读警示；快照脱敏漏列表元素同期修复 |
| 2026-08-23 | [EXP-20260823-007] 插件声明兼容却 import 缺失 SDK 入口 | openclaw-weixin 加载失败；peerDependencies 不校验子路径；降级无效（4 版本同问题）|
| 2026-08-23 | [工具] `kb_index.py` 知识库索引器 | ADR-003 阶段 2；schema 校验/三维查询/交叉引用/INDEX 自动生成；首跑修正 34 处问题 |
| 2026-08-23 | [EXP-20260823-008] 阶段 3 启动评估 | 0/7 触发条件，**自建暂缓**；定性条件 2/3/4 已用工具实测 |

## 5. 自动生成区

> 标记之间的内容由 `scripts/kb_index.py --emit-index` 维护，标记之外手写保留。

<!-- kb_index:auto:start -->

> 以下内容由 `scripts/kb_index.py --emit-index` 自动生成，请勿手工编辑。
> 来源：25 篇 Markdown（ADR-003 §4.3 — Markdown 是唯一来源）。

### 全部条目

| ID | 标题 | layers | stage | status |
|---|---|---|---|---|
| [ADR-202608-001](./by-category/project-experience/adr/ADR-202608-001-four-layer-architecture.md) | 综合开放平台采用 4 层分层架构 (L1 系统层 / L2 基础设施层 / L3 通用业务层 / L4 专有业务层) | L1,L2,L3,L4 | design | accepted |
| [ADR-202608-002](./by-category/project-experience/adr/ADR-202608-002-knowledge-base-three-dimensions.md) | 知识库采用 3 维矩阵组织 (层级 × 阶段 × 类别) | L1,L2,L3,L4 | design | accepted |
| [ADR-202608-003](./by-category/project-experience/adr/ADR-202608-003-knowledge-base-evolution-path.md) | 知识库承载形式采用 "Markdown + 元数据先行, 自建系统演进" 路径 | L2,L3 | design | accepted |
| [ADR-202608-004](./by-category/project-experience/adr/ADR-202608-004-observability-adapter.md) | L2 可观测性适配组件设计决策 — 本地结构化日志优先, 渐进式演进 | L1,L2 | design | accepted |
| [ADR-202608-005](./by-category/project-experience/adr/ADR-202608-005-credential-management.md) | L2 凭据管理通用化 — 文件存储 + SecretRef 引用 + 标准生命周期 | L1,L2 | design | accepted |
| [ADR-202608-006](./by-category/project-experience/adr/ADR-202608-006-persistence-adapter.md) | L2 持久化适配组件设计决策 — SQLite + Repository 模式 + 版本化迁移 | L2,L3,L4 | design | accepted |
| [ADR-202608-007](./by-category/project-experience/adr/ADR-202608-007-config-management.md) | L2 配置管理组件设计决策 — 治理封装而非重新实现 | L1,L2 | manage | accepted |
| [ADR-202608-008](./by-category/project-experience/adr/ADR-202608-008-tool-policy-governance.md) | L2 工具策略治理 — 「允许」与「可用」分离审计 | L1,L2 | manage | accepted |
| [ADR-202608-009](./by-category/project-experience/adr/ADR-202608-009-memory-embedding-provider.md) | L2 记忆语义检索 — 本地 GGUF embedding 为主 provider | L1,L2 | design | accepted |
| [ADR-202608-010](./by-category/project-experience/adr/ADR-202608-010-knowledge-base-tooling.md) | L2 知识库工具链组件 — Markdown 解析/索引/三维查询/schema 治理 | L2 | develop | accepted |
| [EXP-20260821-001](./by-category/project-experience/correct/EXP-20260821-001-tavily-tools-also-allow.md) | Tavily plugin 显式工具通过 tools.alsoAllow 解锁（绕过 tools.profile=coding 的 deny） | L1,L2 | develop | active |
| [EXP-20260821-002](./by-category/project-experience/correct/EXP-20260821-002-github-file-credential-helper.md) | GitHub token 用 file-based credential helper 配置（避免明文入 git config） | L2 | develop | active |
| [EXP-20260821-003](./by-category/project-experience/correct/EXP-20260821-003-compaction-model-delegation.md) | 跨模型会话溢出死锁 — 用 compaction.model 委托大 ctx 模型解压 | L1 | manage | superseded |
| [EXP-20260822-004](./by-category/project-experience/correct/EXP-20260822-004-context-window-empirical-probe.md) | contextWindow 实测法 — 二分探边界定官方声明的真实上限 | L1 | manage | active |
| [EXP-20260822-005](./by-category/project-experience/correct/EXP-20260822-005-cron-delivery-pollutes-status.md) | cron delivery 失败会污染 job 状态 — 无 channel 环境须设 delivery.mode=none | L1,L2 | manage | active |
| [EXP-20260822-006](./by-category/project-experience/correct/EXP-20260822-006-wecom-aibot-cannot-push-proactively.md) | WeCom aibot 单聊只能应答不能主动推送（93006） | L1,L2 | manage | active |
| [EXP-20260823-007](./by-category/project-experience/correct/EXP-20260823-007-plugin-declares-compat-but-imports-missing-sdk-subpath.md) | 第三方 channel 插件声明兼容却 import 不存在的 SDK 入口 | L1,L2 | manage | active |
| [EXP-20260823-008](./by-category/project-experience/correct/EXP-20260823-008-kb-phase3-evaluation.md) | 知识库阶段 3 启动评估 — 用工具链实测替代主观判断，结论为暂缓自建 | L2 | design | active |
| [EXP-20260823-009](./by-category/project-experience/correct/EXP-20260823-009-review-selective-citation-and-drift-taxonomy.md) | 建设期全盘 review — 选择性引用官方文档导致 ADR 核心论证错误 | L1,L2 | manage | active |
| [EXP-20260823-010](./by-category/project-experience/correct/EXP-20260823-010-heuristics-instead-of-evidence.md) | 用启发式代替证据 — 记录造假、dry-run 幻觉、局部检查三种同源错误 | L1,L2 | manage | active |
| [EXP-20260824-011](./by-category/project-experience/correct/EXP-20260824-011-catalog-is-not-entitlement.md) | 平台目录 ≠ 当前套餐权限 — 邻近信息源代替权威源的第三次同源错误 | L1,L2 | manage | active |
| [EXP-20260824-012](./by-category/project-experience/correct/EXP-20260824-012-kb-phase3-readiness.md) | 知识库阶段 3 就绪度 — 补齐六项子能力，但拒绝人为凑触发条件 | L2 | design | active |

### 标签云

`openclaw`(5) · `knowledge-base`(5) · `secretref`(4) · `governance`(3) · `channel`(3) · `migration`(2) · `observability`(2) · `cross-cutting`(2) · `credentials`(2) · `security`(2) · `memory-search`(2) · `embedding`(2) · `tooling`(2) · `markdown`(2) · `plugin`(2) · `context-window`(2) · `volcengine`(2) · `cron`(2) · `delivery`(2) · `adr-003`(2) · `review`(2) · `evidence`(2) · `methodology`(2) · `architecture`(1) · `layering`(1) · `foundation`(1) · `taxonomy`(1) · `organization`(1) · `self-hosted`(1) · `strategy`(1) · `logging`(1) · `tracing`(1) · `monitoring`(1) · `secrets`(1) · `persistence`(1) · `sqlite`(1) · `repository`(1) · `database`(1) · `config`(1) · `snapshot`(1) · `drift-detection`(1) · `secret-redaction`(1) · `tools`(1) · `policy`(1) · `least-privilege`(1) · `silent-degradation`(1) · `memory`(1) · `semantic-search`(1) · `local-model`(1) · `privacy`(1) · `fail-closed`(1) · `indexing`(1) · `tavily`(1) · `tools-profile`(1) · `web-search`(1) · `git`(1) · `github`(1) · `compaction`(1) · `model-switch`(1) · `ark-code-latest`(1) · `longcat`(1) · `ark`(1) · `glm`(1) · `minimax`(1) · `probe`(1) · `empirical`(1) · `automations`(1) · `wecom`(1) · `proactive-messaging`(1) · `platform-limit`(1) · `compatibility`(1) · `peer-dependency`(1) · `weixin`(1) · `third-party`(1) · `evaluation`(1) · `yagni`(1) · `documentation-drift`(1) · `adr`(1) · `confirmation-bias`(1) · `plugins-allow`(1) · `self-learning`(1) · `verification`(1) · `dry-run`(1) · `false-positive`(1) · `entitlement`(1) · `false-memory`(1) · `readiness`(1) · `export`(1) · `render`(1) · `portability`(1) · `goodhart`(1)

### 三维分布 (layer × stage)

| layer | design | develop | manage |
|---|---|---|---|
| L1 | 5 | 1 | 10 |
| L2 | 9 | 3 | 8 |
| L3 | 4 | 0 | 0 |
| L4 | 3 | 0 | 0 |

<!-- kb_index:auto:end -->
