# 系统架构

> 综合开放平台的分层架构设计。本文档是系统建设的**单一事实来源 (Single Source of Truth)**。
>
> **维护原则**：
> - 架构变了 → 改本文档
> - 架构决策变了 → 改本文档 + 新增/更新 ADR
> - 单文件、单一来源、可被审计
> - 2026-08-21 初始化并补全内部细节

## 0. 元信息

| 字段 | 值 |
|---|---|
| 文档版本 | 0.3 (2026-08-21 上下文管理组件 + auto-compaction 配置) |
| 文档状态 | active |
| 决策状态 | 4 层架构已锁定（待 ADR-001 落档） |
| 配套文档 | `../knowledge-base/README.md` |
| 待办 | ADR-001（4 层架构决策记录） |

---

## 1. 设计原则

| 原则 | 说明 |
|---|---|
| **分层自治** | 每层只依赖下层，禁止跨层调用（如基础设施层不能直接调用通用业务层） |
| **契约稳定** | 层间通过明确定义的接口契约通信，契约变更需走 ADR |
| **适配优先** | 自定义能力必须适配官方系统层，不得破坏基座契约 |
| **复用优先** | 专有业务必须从通用业务层继承，仅叠加专有规则 |
| **治理横切** | 安全、合规、可观测、成本、组织协作作为横切关注点贯穿所有层 |
| **演进可逆** | 每一层的扩展点允许演进，但不得破坏已有契约 |
| **单一来源** | 系统状态以本文档为准；变更必须更新本文档 |

## 2. 分层架构

### 2.1 全景图

```
┌─────────────────────────────────────────────────────────────┐
│              横切关注点 (Cross-Cutting Concerns)            │
│   安全 · 合规 · 可观测 · 成本 · 组织协作 · 知识管理         │
└─────────────────────────────────────────────────────────────┘
                          ▲
┌─────────────────────────────────────────────────────────────┐
│  L4  专有业务层 (Proprietary Business Layer)                 │
│      · 继承通用业务能力 + 专有业务规则                       │
│      · 业务专有数据模型、专有流程、专有策略                   │
├─────────────────────────────────────────────────────────────┤
│  L3  通用业务层 (Generic Business Layer)                     │
│      · 跨场景通用业务能力（用户、商品、订单、支付…）          │
│      · 按业务维度切分，每维度独立演进                         │
├─────────────────────────────────────────────────────────────┤
│  L2  基础设施层 (Infrastructure Layer)                       │
│      · 自定义组件 / 系统资产                                  │
│      · 必须适配 L1 OpenClaw 官方契约                         │
├─────────────────────────────────────────────────────────────┤
│  L1  系统层 (System Layer) — OpenClaw 官方                  │
│      · 基座能力：Agent、Skills、Memory、Cron、Gateway、…     │
│      · 不可改，作为系统依赖                                  │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 调用关系

```
L4 → L3 → L2 → L1    (允许)
L4 → L2 / L1         (禁止)
L3 → L4              (禁止)
L1 → 任何上层         (反向依赖，禁止)
```

**允许的**：
- L4 调用 L3、L3 调用 L2、L2 调用 L1
- 同层内通过契约调用

**禁止的**：
- 任何层"穿越"调用下下层
- 任何层反向依赖
- L2 直接 hack L1 内部实现

---

## 3. 各层详细职责

### 3.1 L1 — 系统层 (System Layer)

**来源**：OpenClaw 官方

**职责**：提供基座能力，作为系统依赖

**能力清单**（明列 OpenClaw 提供的原子能力，方便 L2 适配）：

| 能力类 | 具体能力 |
|---|---|
| **Agent Runtime** | 嵌入式 agent loop、模型路由、prompt 组装、会话管理、channel 投递 |
| **Skills** | 技能发现、加载、调用；frontmatter 元数据；本地 + ClawHub + 自建 |
| **Memory** | MEMORY.md + memory/ 目录、会话持久化、daily logs、记忆检索 |
| **Cron** | 定时任务、agent turn、isolated run、triggers、wakeMode |
| **Gateway** | WS gateway、IM 通道（telegram/whatsapp/discord/...）、webchat |
| **Config** | profile、config schema、env 注入、SecretRef |
| **Tools** | exec、read、write、edit、apply_patch、process、sessions_spawn、web_search、web_fetch |
| **Plugins** | Tavily/1Password/MCP 等；hooks 注入（before_prompt_build、agent_end 等） |
| **Audit** | 工具调用审计、消息生命周期、prompt injection 检测 |

**约束**：
- **不可修改** L1 内部实现
- 升级跟随 OpenClaw 官方版本；breaking changes 需走 ADR
- 任何 L2 适配不得 hack 内部实现

**演进方式**：
- 跟随 OpenClaw 升级（当前：2026.7.2-beta.7）
- 关注 release notes 中的 breaking changes
- L2 适配层必须能优雅降级或快速响应

**预留位**：
- 哪些 L1 能力是本系统**未使用**的？为什么不用？→ 待 L2 建设时记录
- 哪些 L1 能力**受限**（如 `tools.profile` deny）？→ 详见 §3.2 L2 配置小节

### 3.2 L2 — 基础设施层 (Infrastructure Layer)

**来源**：自定义

**职责**：封装/适配 L1 能力，提供本系统专用的基础设施服务

**关键约束**：
- 必须适配 L1 契约（不能绕过、不能 hack）
- 提供给 L3 的接口必须稳定（契约变更需 ADR）
- 不感知 L3 / L4 的业务含义

**组件分类**（按职能）：

| 组件类 | 说明 | 状态 |
|---|---|---|
| **配置管理** | profile、config schema、env 注入、SecretRef 包装 | 复用 L1 |
| **可观测性适配** | logging、metrics、tracing | 预留位 (待建设) |
| **持久化适配** | memory、文件、KV、未来 SQL/NoSQL | 部分复用 + 预留位 |
| **工具/技能封装** | domain-specific skills、L1 工具的二次封装 | 复用 + 自建 (Tavily) |
| **调度/任务编排** | cron、agent turn、isolated run、heartbeat | 复用 L1 |
| **知识库能力** | 自建系统的演进目标 | 轻量方案 (Markdown + frontmatter) |
| **凭据管理** | 集中式 secrets 存储、SecretRef 解析 | 已建设 (Tavily key 案例) |
| **工具策略** | `tools.profile` + `alsoAllow` 治理 | 已建设 (EXP-20260821-001) |
| **上下文管理** | auto-compaction + session pruning + contextWindow 校准 | 已建设 (EXP-20260821-003) |

**已建设组件清单**（截至 2026-08-21）：

1. **Tavily 集成** (2026-08-21)
   - 组件 ID: `plugins.entries.tavily`
   - Key 存储: `~/.openclaw/secrets/tavily.apiKey` (chmod 600, file-based SecretRef)
   - Provider: `secrets.providers.tavilykey`
   - 工具解锁: `tools.alsoAllow: [tavily_search, tavily_extract]`
   - 文档: `../knowledge-base/by-category/project-experience/correct/EXP-20260821-001-tavily-tools-also-allow.md`

2. **workspace 配置** (2026-08-21)
   - 路径: `~/.openclaw/workspace/`
   - 关键文件: `AGENTS.md` / `IDENTITY.md` / `SOUL.md` / `USER.md` / `MEMORY.md`
   - `.gitignore` 保护: MEMORY.md、memory/、skills/、business/*/logs/

3. **主 agent** (默认)
   - Agent ID: `main`
   - 模型: `coding-plan/ark-code-latest`
   - 工具 profile: `coding` + `alsoAllow: [tavily_search, tavily_extract]`

4. **上下文管理** (2026-08-21)
   - 组件 ID: `agents.defaults.compaction` + `agents.defaults.contextPruning`
   - 功能: 三层防线自动管理上下文溢出
     - 第 1 层: Auto-compaction — 阈值维护 + 溢出恢复，摘要委托 LongCat-2.0 (1M ctx)
     - 第 2 层: Session pruning — cache-ttl 模式修剪旧 tool results
     - 第 3 层: Mid-turn precheck — 多轮工具调用中途 ctx 压力检查
   - 关键配置:
     - `mode: "safeguard"` — 更严格保护 + 摘要质量审计
     - `keepRecentTokens: 30000` — 压缩保留 30k 近期消息
     - `maxActiveTranscriptBytes: "20mb"` — transcript 达 20MB 预压缩
     - `midTurnPrecheck.enabled: true` — 中途检查
     - `contextPruning: { mode: "cache-ttl", ttl: "5m" }` — 5分钟 TTL 修剪
   - contextWindow 校准: 4 个模型从 200k 默认值修正至官方值
     - glm-5.3: 200k → 1M | kimi-k2.7-code: 200k → 262k | minimax-m3: 200k → 1M | ark-code-latest: 200k → 262k
   - 文档: `../knowledge-base/by-category/project-experience/correct/EXP-20260821-003-compaction-model-delegation.md`

**预留位**（待 L2 建设时填充）：
- 可观测性组件（metrics、trace）
- 持久化组件（关系数据库/对象存储）
- 工具策略治理文档（哪些工具 deny/allow/why）

**演进方式**：
- 优先复用 L1 能力
- 必要时自建 wrapper，但不得 hack L1
- 每个组件必须有"配置 → 验证 → 监控"三件套
- 组件变更如影响 L3 接口 → 需 ADR

### 3.3 L3 — 通用业务层 (Generic Business Layer)

**来源**：自定义

**职责**：跨场景通用的业务能力，可被 L4 复用

**组织方式**：
- **按业务维度切分**，每维度独立模块
- 维度划分原则（详见 §3.3.1）
- 维度间通过契约通信

**关键约束**：
- **不感知专有业务上下文**（不知道具体客户/项目）
- **不直接依赖 L4**（反向依赖禁止）
- 通过契约提供服务
- 每个维度独立演进、独立版本

#### 3.3.1 业务维度划分原则

| 维度类型 | 划分依据 | 示例 |
|---|---|---|
| **领域实体** | 业务核心实体 | user / product / order / payment |
| **领域流程** | 跨实体的业务流 | checkout / fulfillment / refund |
| **横切能力** | 通用工具 | notification / search / analytics / audit |

**判断标准**（"这个能力属于 L3 还是 L4？"）：
- ✅ L3：跨项目/跨客户通用、不含专有规则、有明确实体或流程定义
- ❌ L4：仅 1 个项目/客户使用、含专有规则或专有数据

#### 3.3.2 通用业务层状态

**当前**：未启动（阶段一）

**待 L2 最小可用后启动**（阶段二）

**预留位**（待启动时填充）：
- L3 第一个维度的选型理由
- 维度间的依赖图
- 维度的最小能力清单
- 维度的契约形式（API / event / data schema）

**演进方式**：
- 每个维度独立仓库 / 独立模块
- 版本化（semver）
- 契约变更需 ADR
- 测试覆盖率作为合并门槛

### 3.4 L4 — 专有业务层 (Proprietary Business Layer)

**来源**：自定义

**职责**：在通用业务能力之上叠加专有业务信息

**关键约束**：
- **必须继承 L3**，不得重写通用能力
- 仅新增：专有规则、专有数据、专有流程
- 与 L3 的扩展点必须显式声明
- 不直接调用 L2（应通过 L3 间接获得 L2 能力）

**继承机制**：

```
L4 专有业务
  ├── extends L3 通用业务维度 A (核心能力复用)
  ├── extends L3 通用业务维度 B (核心能力复用)
  └── adds 专有规则/数据/流程 (差异化)
```

**扩展点类型**：

| 扩展类型 | 说明 | 例子 |
|---|---|---|
| **数据扩展** | 继承 L3 schema，添加专有字段 | `User` L3 + `User.proprietary_metadata` L4 |
| **规则扩展** | 继承 L3 业务逻辑，添加专有规则 | `Order.validate()` L3 + `Order.compliance_check()` L4 |
| **流程扩展** | 继承 L3 流程，插入专有步骤 | `checkout` L3 + `risk_assessment` L4 |
| **接口扩展** | L4 暴露专有 API，不影响 L3 | `/api/proprietary/*` |

**当前**：未启动（阶段一）

**预留位**（待启动时填充）：
- L4 第一个项目的选型
- 专有规则的清单
- L4 部署形态

---

## 4. 横切关注点 (Cross-Cutting Concerns)

横切关注点**不构成独立层**，而是贯穿 L1~L4 的约束与能力。

| 关注点 | 在每层的要求 | 当前状态 |
|---|---|---|
| **安全** | 凭据管理、权限边界、输入校验、审计日志 | ✅ 凭据管理 (Tavily SecretRef)；⏳ 权限边界预留位 |
| **合规** | 数据驻留、隐私、监管要求 | ⏳ 预留位 |
| **可观测** | 日志、指标、追踪、告警 | ⏳ 预留位（当前依赖 L1 + 业务日志） |
| **成本** | 资源使用、API 调用、外部服务计费 | ⏳ 预留位 |
| **组织协作** | 文档、决策记录、知识沉淀 | ✅ 已建设 (知识库 + ADR + EXP) |
| **知识管理** | 知识库分层、经验沉淀、ADR | ✅ 已建设 (轻量方案) |

---

## 5. OpenClaw 契约边界

> 这是本系统最重要的约束——**基础设施层不得破坏的边界**。

### 5.1 可控范围
- Skills / 自定义插件
- Workspace 文件 / 配置
- Cron / 自动化任务
- 自有工具（exec、文件、网络）
- Memory / 日志
- 第三方集成（IM、平台）
- `plugins.entries.<id>.config`（plugin-specific）
- `tools.profile` + `tools.alsoAllow`（工具策略）

### 5.2 不可控范围
- OpenClaw 核心行为 / 安全策略
- Gateway 内部实现
- Agent prompt / 工具策略（除非显式允许）
- 系统提示注入
- L1 内部 API 行为

### 5.3 扩展点（已知）
- Skills：新增、扩展
- Agent 配置：模型、工具、权限
- Cron：自定义任务
- 工具：新增（需符合契约）
- Memory：读写
- 外部平台：经由 OpenClaw 提供的接入
- SecretRef：provider 形式（env/file/exec）

> 任何试图绕过 5.2 或在 5.3 之外扩展的能力，必须先走 ADR。

### 5.4 已知工具策略问题

**Issue 模式**：`tools.profile` 限制 + plugin 显式工具

**已验证案例**：Tavily `tavily_search` / `tavily_extract` 在 `profile=coding` 下默认 deny，通过 `alsoAllow` 解锁（详见 EXP-20260821-001）

**预留位**：
- 是否有其他 plugin 工具受同样影响？
- 未来 OpenClaw 升级是否改变 coding profile 的 deny 列表？

---

## 6. 演进路线

### 6.1 阶段一：基座搭建（**当前**）

| 项 | 状态 |
|---|---|
| L1 + L2 最小可用（基于 OpenClaw workspace） | ✅ 进行中 |
| L3 / L4 暂未启动 | ⏳ |
| 知识库采用 **Markdown + 元数据** 轻量方案 | ✅ 已建设 |
| 工作区基础文件（AGENTS / IDENTITY / SOUL / USER / MEMORY） | ✅ |
| 第一个 L2 组件（Tavily 集成） | ✅ |

**目标**：跑通分层，验证契约

**当前进度**：
- ✅ 系统架构文档（本文件）
- ✅ 知识库骨架（三维模型）
- ✅ 工作区配置（USER/IDENTITY/SOUL）
- ✅ 第一个 L2 组件（Tavily）
- ⏳ 第一份 ADR（4 层架构决策）

**下一里程碑**（阶段一内）：
1. ADR-001: 4 层架构决策
2. ADR-002: 知识库三维模型
3. ADR-003: 知识库承载形式（Markdown → 自建系统的路径）

### 6.2 阶段二：业务能力沉淀

| 项 | 状态 |
|---|---|
| L3 按业务维度逐步建设 | ⏳ |
| L4 开始引入 | ⏳ |
| 知识库继续以文件形式承载，但增加**结构化元数据 + 索引** | ⏳ |

**目标**：验证 L3 维度划分、L4 继承机制

**入口条件**：阶段一 ADR 全部完成、L2 最小可用稳固

### 6.3 阶段三：自建知识库系统

| 项 | 状态 |
|---|---|
| 在 L2 / L3 中实现**自建知识库系统** | ⏳ |
| 支持人机协作阅读、跨系统移植 | ⏳ |
| 文档/经验/ADR 全部迁入自建系统 | ⏳ |
| 文件形式的知识库作为**导出格式**保留 | ⏳（策略已定）|

**目标**：知识库系统本身成为 L2/L3 能力，**自指**（用知识库方法管理知识库系统的知识）

**入口条件**：阶段二业务沉淀稳定、知识库有足够内容驱动自建系统的需求

### 6.4 阶段四：企业级治理

| 项 | 状态 |
|---|---|
| 横切关注点全面落地 | ⏳ |
| 完整的可观测、合规、安全体系 | ⏳ |
| 成本管理（资源、API、外部服务计费） | ⏳ |

**目标**：系统具备企业级能力

**入口条件**：业务规模/团队规模驱动治理需求

---

## 7. 决策记录

本系统的所有重大架构决策均通过 ADR 沉淀。

**待办 ADR 列表**（按优先级）：

| # | 主题 | 优先级 | 状态 |
|---|---|---|---|
| ADR-001 | 4 层架构决策 | 高 | ✅ accepted (2026-08-21) |
| ADR-002 | 知识库三维模型 | 中 | ✅ accepted (2026-08-21) |
| ADR-003 | 知识库承载形式演进路径 | 中 | ✅ accepted (2026-08-21) |
| ADR-004 | L1 工具策略治理（`alsoAllow` 用法） | 低 | ⏳（已有 EXP-20260821-001，待触发升级条件时再升） |

**ADR 模板**：`../knowledge-base/templates/ADR.md`

**ADR 存放路径**：`../knowledge-base/by-category/project-experience/adr/`

---

## 8. 依赖与选型约束

### 8.1 强依赖

| 依赖 | 用途 | 约束 |
|---|---|---|
| OpenClaw 2026.7.2-beta.7+ | L1 基座 | 升级需关注 breaking changes |
| @openclaw/tavily-plugin 2026.7.1+ | L2 web 搜索/提取 | 通过 `plugins.entries.tavily` 集成 |
| Node.js v26.7.0 | OpenClaw runtime | 跟随 OpenClaw 最低版本 |
| macOS 26.5.2 | 当前运行平台 | 跨平台时需注意 LaunchAgent → systemd 迁移 |

### 8.2 选型边界（本架构限制下）

| 类别 | 可选 | 不可选 |
|---|---|---|
| Agent framework | OpenClaw 体系内的 skills/plugins | 自建 L1 类似物（违反 L1 不可改） |
| 知识库系统 | Markdown + frontmatter（当前）/ 自建系统（演进） | 强依赖单一外部 SaaS（不利于跨系统移植） |
| 凭据管理 | OpenClaw SecretRef（env/file/exec） | 硬编码到 markdown |
| 工具来源 | OpenClaw built-in + approved plugins | hack L1 内部 API |

### 8.3 预留位

- 模型选择：当前用 `coding-plan/ark-code-latest`，是否需要 fallback 模型？
- 多 agent：当前只有 `main`，是否需要专用 sub-agents？

---

## 9. 术语表

| 术语 | 含义 |
|---|---|
| **基座** | L1 系统层（OpenClaw）的代称 |
| **契约** | 层间或模块间明确定义的接口约定，变更需 ADR |
| **维度** | L3 业务能力的切分单位（如 user/order/payment） |
| **扩展点** | 父层为子层预留的可扩展位置 |
| **横切关注点** | 贯穿多层的通用约束（安全/合规/可观测等）|
| **SecretRef** | OpenClaw 的凭据引用机制，源支持 env/file/exec |
| **alsoAllow** | 工具策略：在 profile 之上追加允许列表 |

---

## 10. 变更历史

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-08-21 | 0.1 | 初版骨架（4 层架构 + 契约 + 演进路线） |
| 2026-08-21 | 0.3 | 新增 L2 上下文管理组件：auto-compaction 三层防线 + contextWindow 校准 + session pruning |

---

## 相关文档

- 知识库索引：`../knowledge-base/README.md`
- 经验沉淀模型：`../knowledge-base/by-category/project-experience/README.md`
- ADR 模板：`../knowledge-base/templates/ADR.md`
- 经验卡片模板：`../knowledge-base/templates/EXPERIENCE-CARD.md`
- EXP-20260821-001（Tavily 工具解锁）：`../knowledge-base/by-category/project-experience/correct/EXP-20260821-001-tavily-tools-also-allow.md`
