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
| 文档版本 | 1.2 (2026-08-24 — 沙箱隔离方案 B 落地：colima+docker+non-main，实测 uid=1000/写拦截/断网/WeCom 正常) |
| 文档状态 | active |
| 决策状态 | 4 层架构已锁定（ADR-001 accepted） |
| 配套文档 | `../knowledge-base/README.md` |
| 待办 | 无（L3 启动待 Rex 拍板，见 §6.2）|

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

**L1 能力使用盘点**（2026-08-24 实查，原「预留位」问号已回答）：

| L1 能力 | 使用状态 | 说明 |
|---|---|---|
| Agent Runtime | ✅ 全量使用 | 主 agent + cron isolated run；`agents.entries.main.model` 显式钉模型隔离 sticky 污染 |
| Skills | ✅ 使用 | 91/103 可见；**12 个「允许但非功能」**（缺 bin/env，见 AGENTS.md）；self-learning 已降为 propose |
| Memory | ✅ 全量使用 + 自建监控 | MEMORY.md + memory/ + 语义检索（本地 GGUF）；ADR-009 决策 4 监控已落地 |
| Cron | ✅ 使用 | 4 个 enabled；均显式钉 model + fallbacks |
| Gateway | ⚠️ **部分使用** | 仅 **WeCom + webchat**；其余 20+ IM 通道 not installed |
| Config | ✅ 全量使用 | + 自建变更治理（ADR-007 快照/审计/漂移） |
| Tools | ⚠️ **受限使用** | `profile: coding` + `alsoAllow: [tavily_search, tavily_extract]` |
| Plugins | ✅ 使用 | 4 个钉版本 + integrity 全绿；`plugins.allow` 严格白名单（enabled 57→5） |
| Audit | ✅ 使用 | 工具调用审计 + prompt injection 检测（L1 内建） |

**未使用的 L1 能力及原因**：

| 能力 | 原因 |
|---|---|
| 20+ IM 通道（Telegram/Slack/Discord/Matrix/…） | 无业务需求；仅 WeCom 满足团队协作。**非缺口**，按需启用即可 |
| **沙箱隔离** `agents.defaults.sandbox.mode` | ✅ **已启用** `non-main`（2026-08-24 方案 B 落地）。colima 0.10.3 + docker 29.7.2 + `openclaw-sandbox:bookworm-slim` 335MB。官方加固基线：`workspaceAccess=ro` / `readOnlyRoot` / `network:none` / `capDrop:ALL`。已实测：子会话 `uid=1000(sandbox)` + 容器 hostname + Linux 根 + 写拦截 + 断网；WeCom 会话正常（`alsoAllow` 补了 memory/web/messaging） |
| `remote.batch` embedding API | 仅支持 gemini/openai/voyage；本系统用本地 llama-cpp |
| MCP / 1Password 等 plugin | 无需求；`plugins.allow` 白名单外 |

**受限的 L1 能力**：

| 限制 | 手段 | 实际效果 |
|---|---|---|
| 工具白名单 | `tools.profile: coding` + `alsoAllow` | 非 coding 类工具不可用；Tavily 经 alsoAllow 显式解锁（EXP-001） |
| `tools.elevated` | — | ⚠️ **实为 no-op**：sandbox 默认 off ⇒ exec 本就在 host。真正生效的是 `tools.deny` + `toolsBySender`（2026-08-23 纠正） |
| 插件加载 | `plugins.allow` 严格白名单 | enabled 57→5；**改后必须逐项验证依赖能力** |
| 通道准入 | `dmPolicy: pairing`, `allowFrom: []` | WeCom 需配对才能私聊 |

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
| **配置管理** | profile、config schema、env 注入、SecretRef 包装；**变更治理（快照/审计/漂移检测）** | 已建设 (ADR-007) |
| **可观测性适配** | logging、metrics、tracing | 已建设 (ADR-004) |
| **持久化适配** | memory、文件、KV、未来 SQL/NoSQL | 已建设 (ADR-006) |
| **工具/技能封装** | domain-specific skills、L1 工具的二次封装 | 复用 + 自建 (Tavily) |
| **调度/任务编排** | cron、agent turn、isolated run、heartbeat | 复用 L1 |
| **知识库能力** | Markdown 解析/索引/三维查询/交叉引用/schema 治理/**渲染**/**导出** | 已建设 (ADR-010，工具链层)；**ADR-003 §4.4 六项子能力全备 (2026-08-24)** |
| **凭据管理** | 集中式 secrets 存储、SecretRef 解析 | 已建设 (ADR-005) |
| **工具策略** | `tools.profile` + `alsoAllow` 治理；**「允许」vs「可用」分离审计** | 已建设 (ADR-008) |
| **上下文管理** | auto-compaction + contextWindow 校准（session pruning ❌ 死配置） | 已建设，**2/3 层实际生效** (EXP-20260821-003, EXP-20260824-011) |
| **记忆语义检索** | 本地 GGUF embedding（零成本/零外发）+ 向量索引 + **健康监控** | 已建设 (ADR-009 决策 4 已落地 2026-08-24) |

> **状态取值口径**：`已建设` 要求 **ADR + DESIGN.md + 实现** 三件齐备（见下方四件套清单）。
> `复用 L1` 表示不自建，直接用 L1 能力。若仅有实现而缺 ADR/DESIGN，**不得标「已建设」**。

**已建设组件四件套清单**（截至 2026-08-23）：

| 组件 | ADR | DESIGN.md | 实现 | 验证方式 |
|---|---|---|---|---|
| 可观测性 | 004 | `components/observability/` | `scripts/observability/agent_observer.py` | `--daily --jsonl` 实跑 |
| 凭据管理 | 005 | `components/credentials/` | `scripts/credentials.sh` | `scan_secrets.sh` |
| 持久化 | 006 | `components/persistence/` | `persistence/` (connection/repository/migration/schemas) | 迁移幂等测试 |
| 配置管理 | 007 | `components/config/` | `scripts/config.sh` | `config.sh diff` 漂移检测 |
| 工具策略 | 008 | `components/tool-policy/` | `scripts/tool_policy_audit.sh` | 六项审计 |
| 记忆语义检索 | 009 | `components/memory-embedding/` | 配置态（`memory.search.provider=local`）+ `scripts/observability/memory_search_monitor.py` | 行为探针三态判据 + **注入故障双向验证** |
| 知识库能力 | 010 | `components/knowledge-base/` | `scripts/kb_index.py`（解析/索引/检索/关联/**渲染**/**导出** 六项全备）| pre-commit 阻塞实测 + **导出往返无损 24/24 字节一致** |

**已建设组件清单**（截至 2026-08-23）：

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
   - 功能: 两层防线自动管理上下文溢出（原设计为三层，第 2 层已证实不生效 —— 见下）
     - 第 1 层: Auto-compaction — 阈值维护 + 溢出恢复；摘要委托给**同 provider 的大 ctx 模型**（`compaction.model` = `coding-plan/deepseek-v4-flash`，1049k）— 避免“用已溢出的模型去压缩”的死锁（EXP-003）
       - ⚠️ **2026-08-24 修正**：原为 `longcat/LongCat-2.0`（跨 provider 委托）。实测证明**跨 provider 是反模式** —— LongCat 网络故障时 ARK 侧全程 200 正常，却因压缩模型死在另一个 provider 上，造成「会话活着但压缩死了」的分裂故障。且显式 `compaction.model` **不继承 fallback 链**（`concepts/compaction.md:101`）、`compaction.fallbacks` 又是非法字段 ⇒ 拿不到兜底。**压缩模型应与主会话同 provider**，共享同一条网络/鉴权命运
     - ~~第 2 层: Session pruning — cache-ttl 模式修剪旧 tool results~~ → **❌ 不生效**（provider 不在 cache-ttl 白名单，详见关键配置节）
     - 第 3 层: Mid-turn precheck — 多轮工具调用中途的 ctx 压力信号；**它不做内联压缩**，而是中止当前 prompt 提交并交给外层 recovery 路径
   - 关键配置:
     - `mode: "safeguard"` — 更严格保护 + 摘要质量审计（`qualityGuard` 在 safeguard 下默认启用）
     - `keepRecentTokens: 30000` — **cut-point 预算**（token 计，非消息条数），压缩时保留最近 30k token 的 transcript 尾部**逐字不改**；官方默认 `20000`，此处显式提高以保留更多近期上下文
     - `maxActiveTranscriptBytes: "20mb"` — transcript 达 20MB 触发 preflight 本地压缩（开下一次 run 前）
     - `midTurnPrecheck.enabled: true` — 中途检查（**官方默认 `false`，需显式开启**）
     - `contextPruning: { mode: "cache-ttl", ttl: "5m" }` — **❌ 已证实 100% 不生效的死配置**（2026-08-23 第三轮 review 结案）
       - **根因**：`buildContextPruningFactory`（`dist/selection-B_4MkgWU.js:18595-18598`）确认 `mode === "cache-ttl"` 后立即调 `isCacheTtlEligibleProvider` 做 provider 白名单校验，不过则**提前 return**，pruning extension 从未注册。
       - **白名单完整出路**（`dist/proxy-dRac3ChC.js:28-33` + `selection-B_4MkgWU.js:8770-8790`）：`provider ∈ {anthropic, anthropic-vertex}`、`amazon-bedrock`+Anthropic 模型、`modelApi === "anthropic-messages"`、`kilocode`+`anthropic/*`、Google `gemini-2.5/3`。
       - **本机逐条不命中**：provider=`coding-plan`、`api=openai-completions`、主模型 `coding-plan/ark-code-latest`。插件覆盖路径（`resolveProviderCacheTtlEligibility`）亦不存在 —— `plugins.allow` 内 4 个插件对 `isCacheTtlEligible` 钩子均**零命中**。
       - **官方文档为何不够**：`session-pruning.md:54` 只讲「自动默认仅 Anthropic 系」，未说明**显式配置也受同一白名单约束**。`reference/prompt-caching.md:104` 列出的允许路由全为 Anthropic 系，是该白名单的文档投影。
       - **处置**：配置保留无害（本就不跑），但**不得当作防线依赖**。若需控制 tool result 膨胀，本机唯一有效路径是 compaction 系 + 收紧单次工具输出。
   - contextWindow 校准: 官方数据 + **实测二分探边界**修正
     - glm-5.3: 1M（实测 1,048,568 通过，ARK 端点无需 `[1m]` 后缀）
     - minimax-m3: 1M（实测；曾误设 512000 — 那是 MiniMax 直连 API 的限制）
     - ark-code-latest: **229376 (224k)**（实测 224,051 通过 / 230,051 拒绍）
     - kimi-k2.7-code: 262144
   - 文档: `../knowledge-base/by-category/project-experience/correct/EXP-20260821-003-compaction-model-delegation.md`

5. **配置管理** (2026-08-22)
   - 组件 ID: `scripts/config.sh` + `config-snapshots/`
   - 定位: **治理封装**，不重新实现 L1 的配置读写（严禁绕过 `openclaw config`）
   - 解决的四个治理问题（均有已发生事故背书）:
     - P1 变更不可追溯 → 脱敏快照入 git（`.bak` 仅 5 份轮转且不答“谁改的”）
     - P2 “应用成功”≠“生效” → 四步流程固化，**强制读回确认**
     - P3 能力声明靠推断 → `probe_context_window.py` 二分实测
     - P4 配置漂移无人发现 → `--check` 模式 + pre-commit 提醒（不阻塞）
   - 关键子命令: `audit` / `snapshot` / `diff` / `apply <patch>` / `probe <model>`
   - 脱敏策略: **精确字段名匹配 + 白名单**（子串匹配会误伤 `maxTokens`/`keepRecentTokens`）
   - 契约: L3 不直接读 `~/.openclaw/openclaw.json`，经 `config.sh audit` 与快照访问
   - ADR: `../knowledge-base/by-category/project-experience/adr/ADR-202608-007-config-management.md`
   - 设计: `components/config/DESIGN.md`

6. **工具策略治理** (2026-08-22)
   - 组件 ID: `tools.profile` + `tools.alsoAllow` + `scripts/tool_policy_audit.sh`
   - 核心认知: **「允许」≠「可用」** —— 三态治理（denied / allowed-but-broken / allowed-and-working）
   - 当前策略: `profile: "coding"` + `alsoAllow: [tavily_search, tavily_extract]`（最小权限）
   - 官方规则要点: `allow` 与 `alsoAllow` 同 scope 互斥；deny 优先；
     `deny:["write"]` 不连带 `apply_patch`，但 `allow:["write"]` 会连带启用
   - 实测发现: `memory_search` 静默降级（缺 embedding provider）· 12 技能缺依赖
   - ADR: `../knowledge-base/by-category/project-experience/adr/ADR-202608-008-tool-policy-governance.md`
   - 设计: `components/tool-policy/DESIGN.md`

7. **知识库能力** (2026-08-23)
   - 组件 ID: `scripts/kb_index.py`
   - 定位: **工具链层**（非服务层）。Markdown 是永久单一来源，本组件只读并产出可重建的索引/视图
   - 能力: `--validate`（schema 校验）/ `--stats`（三维分布）/ `--query`（layer×stage×category 交叉）
     / `--tags`（聚合）/ `--xref`（引用图 + 孤岛/断链）/ `--emit-index`（幂等生成）/ `--json`
   - 契约: **不反向写内容文件**（唯一例外：INDEX.md 标记区，纯派生视图）
   - 治理: pre-commit 第 3 段 — 阻断性错误（非法 layer/stage/category、重复 ID、缺 title）拒绝提交
   - 首跑抳到 34 处问题，其中 **11 篇缺 `stage`** 属静默失败（文档可读但三维查询静默漏掉）
     — 与 ADR-008 三态模型同类，也是本组件存在的核心理由
   - ADR: `../knowledge-base/by-category/project-experience/adr/ADR-202608-010-knowledge-base-tooling.md`
   - 设计: `components/knowledge-base/DESIGN.md`
   - 评估: `../knowledge-base/by-category/project-experience/correct/EXP-20260823-008-kb-phase3-evaluation.md`

**L2 组件建设状态**：**7 个组件四件套齐备**（ADR + DESIGN.md + 实现 + 验证）——
可观测性 · 凭据管理 · 持久化 · 配置管理 · 工具策略 · 记忆语义检索 · 知识库能力。

> ⚠️ **口径说明（2026-08-24 校准）**：上方能力表有 10 行，但其中
> - **上下文管理** —— 配置态组件，**2/3 层实际生效**（session pruning 是死配置）；有 EXP 无独立 ADR/DESIGN ⇒ 按本文档口径**不计入「已建设」7 个**
> - **工具/技能封装**（Tavily）—— 标「复用 + 自建」，有 EXP-001 无独立 ADR/DESIGN
> - **调度/任务编排** —— 标「复用 L1」，不自建
>
> 三者均非缺口，只是不满足「ADR + DESIGN + 实现」三件齐备的**计数口径**。

**预留位**：
- 知识库**自建系统**（服务形态：DB + Web 渲染）— 与上方「知识库能力」组件区分：
  当前已建的是**工具链层**（CLI + Markdown 为源），自建系统是**服务层**。
  启动条件见 ADR-003 §4.2 七触发条件（2026-08-24 复测仍 **0/7**，暂缓 — 见 EXP-20260823-008 / EXP-20260824-012）
  ⏸️ **就绪度：能力已备 6/6，需求未达 0/7** —— §4.4 六项子能力（含新增 `--render` / `--export`，导出往返无损实测 24/24 字节一致）已全部覆盖，触发条件达成即可启动，无能力缺口。
  ⚠️ 七触发条件**不是待办清单**：它们度量需求强度，人为凑指标属 Goodhart's law，且只能靠灌水/虚报/改阈值实现（分别重犯 ADR-002 污染、EXP-010 造假、EXP-009 事后修判据）。

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

**当前**：未启动（§6.1 阶段一已完成，但此层的入口条件停在 §6.2 阶段二）

**待 Rex 定夺是否启动**（§6.2 阶段二入口条件已满足）

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

**当前**：未启动（§6.1 阶段一已完成，此层依赖 L3 启动）

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

### 5.4 工具策略治理

**核心认知修正**：工具治理不只是"哪些被 deny"，而是**三种状态**：

| 状态 | `profile`/`allow`/`deny` 可表达 | 危险性 |
|---|---|---|
| `denied` | ✅ | 低 —— 明确失败 |
| `allowed-but-broken` | ❌ **不能** | **高 —— 静默失败** |
| `allowed-and-working` | ✅ | — |

**已验证案例**：Tavily `tavily_search` / `tavily_extract` 在 `profile=coding` 下默认 deny，
通过 `alsoAllow` 解锁（EXP-20260821-001）

**原预留问题的回答**（2026-08-22 实测）：

1. **"是否有其他 plugin 工具受同样影响？"**
   → 当前仅 Tavily 需显式解锁。发现的**反向不对称**已于 2026-08-23 查清：
   - `terminal`/`screen`：官方文档表格列入 `group:ui`，但**运行时 `POLICY_TOOL_GROUPS`
     仅含 `browser`+`canvas`**（`dist/register-pGYK5dOd.js:3928`）。它们不被任何 `group:`
     覆盖 ⇒ `coding` profile 的 allowlist 不构成排除路径 ⇒ **天然可用**。
   - `dashboard`：**不属 `group:ui`**（文档版与运行时版都没有），是 workboard 插件工具，
     走 plugin 注册路径。**原将它归入 `group:ui` 是事实错误。**
   - → **官方文档表格已过期**（`config-tools.md:41` 列 5 个，运行时只 2 个），属官方文档缺口。
   - → 结论仍成立：**官方 profile 表不足以完整预测实际工具面** —— 但现在知道原因了。

2. **"升级是否改变 coding profile 的 deny 列表？"**
   → 无法预判，已转为**监控点**：升级后重跑 `scripts/tool_policy_audit.sh`。
   DESIGN.md 记录了当前官方 profile 表作为比对基线。

**实测发现的真实问题**：

| 问题 | 严重性 | 状态 |
|---|---|---|
| `memory_search` 静默降级为 keyword-only（缺 embedding provider） | **高** | 待定夺（推荐本地 GGUF，零成本） |
| 12 个技能允许但缺依赖（含 `AGENTS.md` 引用的 `sag`） | 中 | 待定夺（`doctor --fix`） |
| 媒体工具在 profile 内但无 provider | 低 | 官方预期行为，无需处理 |

**审计**：`bash scripts/tool_policy_audit.sh`（六项检查）
**详见**：`components/tool-policy/DESIGN.md` · ADR-008

---

## 6. 演进路线

### 6.1 阶段一：基座搭建（✅ 已完成，2026-08-21~23）

| 项 | 状态 |
|---|---|
| L1 + L2 最小可用 | ✅ 已完成 |
| L3 / L4 暂未启动 | ⏳ |
| 知识库轻量方案（Markdown + 元数据）| ✅ 已建设 |
| 工作区基础文件（AGENTS / IDENTITY / SOUL / USER / MEMORY）| ✅ |
| 7 个 L2 组件建成 | ✅ 见 §3.2 四件套清单 |
| 9 份 ADR accepted | ✅ |

**目标**：跑通分层，验证契约 ✅

**完成条件核对**：
- ✅ 系统架构文档（本文件）
- ✅ 知识库骨架（三维模型 + ADR-002）
- ✅ 工作区配置（USER/IDENTITY/SOUL）
- ✅ 第一个 L2 组件（Tavily）
- ✅ ADR-001/002/003（4 层架构 + 三维模型 + 演进路径）
- ⚠️ 上下文管理（auto-compaction + contextWindow 实测；**session pruning 层不生效**，详见 §L2 第 4 项）
- ✅ 配置管理（快照 + 四步流程 + 漂移检测）
- ✅ 工具策略治理（三态模型 + 六项审计）
- ✅ 记忆语义检索（本地 GGUF embedding）
- ✅ 知识库工具链（`kb_index.py`：schema 校验/三维查询/交叉引用/INDEX 自动生成）

**入口条件完成**：
- 阶段一所有 ADR 已 accepted（见 §7）
- L2 最小可用稳固（7 组件，均有 ADR + DESIGN.md + 实现 + 验证）

### 6.2 阶段二：业务能力沉淀（**已满足入口条件，待 Rex 定夺**）

| 项 | 状态 |
|---|---|
| L3 按业务维度逐步建设 | ⏳ 待定夺 |
| L4 开始引入 | ⏳ 待定夺 |
| 知识库继续以文件形式承载，增加工具链 | ✅ 已交付（`kb_index.py`）|

**目标**：验证 L3 维度划分、L4 继承机制

**入口条件**（§6.1 完成后）：
- ✅ 阶段一 ADR 全部完成（9 份 accepted）
- ✅ L2 最小可用稳固（7 组件，含四件套）

**入口条件已满足**。阶段二未启动的原因是 Rex 要求暂缓 L3 建设（2026-08-23）。

**待 Rex 拍板**：
- L3 第一个业务维度选什么？
- 维度划分原则见 §3.3.1

### 6.2 阶段二：业务能力沉淀

| 项 | 状态 |
|---|---|
| L3 按业务维度逐步建设 | ⏳ |
| L4 开始引入 | ⏳ |
| 知识库继续以文件形式承载，但增加**结构化元数据 + 索引** | ⏳ |

**目标**：验证 L3 维度划分、L4 继承机制

**入口条件**：阶段一 ADR 全部完成、L2 最小可用稳固

### 6.3 阶段三：自建知识库系统（**暂缓** — 触发条件 0/7，见 EXP-20260823-008）

| 项 | 状态 |
|---|---|
| L2 工具链层（`kb_index.py`） | ✅ 已交付（见 §3.2 组件清单）|
| L2 服务层（DB + Web 渲染） | ⏳ 暂缓 |
| 人机协作阅读、跨系统移植 | ⏸️ **CLI 能力已就绪**（`--render` / `--export` 往返无损 24/24）；**服务形态**暂缓 |
| 文档/经验/ADR 全部迁入自建系统 | ⏳ 暂缓 |
| 文件形式保留为**导出格式** | ✅ 策略已定 |

**目标**：知识库系统本身成为 L2/L3 能力，**自指**（用知识库方法管理知识库系统的知识）

**入口条件**：阶段二业务沉淀稳定、知识库有足够内容驱动自建系统的需求

**启动触发条件**（ADR-003 §4.2，**需 ≥2 个达成**）：
- 2026-08-24 复测：**0/7**（文档 **24 篇**、团队 2 人、检索 1 步、**孤岛 0 / 断链 0**、L3/L4 仅 design 有内容）
- 2026-08-23 首测：0/7（文档 23 篇、孤岛 1）—— 见 EXP-20260823-008
- ⏸️ **就绪度：能力已备 6/6**（§4.4 六项子能力全覆盖，含 `--render`/`--export`）**，需求未达 0/7**
- 下一评估：ADR-003 阶段 1 验收（2026-09-21 或内容质变时）
- 完整评估：`../knowledge-base/by-category/project-experience/correct/EXP-20260823-008-kb-phase3-evaluation.md`

> **注意**：阶段三（自建系统）与 §3.2 已建成的「知识库能力」组件（`kb_index.py` 工具链）是**不同物**。
> 工具链是自建系统的解析内核，先建工具链 = 降低自建时的开发成本，不是提前启动阶段三。

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

**ADR 清单**（按优先级）：

| # | 主题 | 优先级 | 状态 |
|---|---|---|---|
| ADR-001 | 4 层架构决策 | 高 | ✅ accepted (2026-08-21) |
| ADR-002 | 知识库三维模型 | 中 | ✅ accepted (2026-08-21) |
| ADR-003 | 知识库承载形式演进路径 | 中 | ✅ accepted (2026-08-21) |
| ADR-004 | L2 可观测性适配 | 中 | ✅ accepted (2026-08-21) |
| ADR-005 | L2 凭据管理通用化 | 高 | ✅ accepted (2026-08-21) |
| ADR-006 | L2 持久化适配（SQLite + Repository） | 高 | ✅ accepted (2026-08-21) |
| ADR-007 | L2 配置管理（治理封装） | 高 | ✅ accepted (2026-08-22) |
| ADR-008 | L2 工具策略治理（三态模型） | 中 | ✅ accepted (2026-08-22) |
| ADR-009 | L2 记忆语义检索（本地 GGUF embedding） | 高 | ✅ accepted (2026-08-22) |

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

### 8.1.1 运行时服务层（LaunchAgent）

> 本层在 v0.7 之前**完全未入档**，导致 5 个孤儿服务长期潜伏（含 2 个存活 16–17 天的幽灵进程）。

**当前自有服务（实测@2026-08-23 11:00）**：

| Label | plist | 状态 | 监听 | 备注 |
|---|---|---|---|---|
| `ai.openclaw.gateway` | `~/Library/LaunchAgents/ai.openclaw.gateway.plist` | ✅ PID 44602 / exit 0 | `127.0.0.1:18789` + `[::1]:18789` | L1 核心，**不可动** |

**已清除的孤儿服务（2026-08-23，Rex 授权）**：

| Label | 清理前状态 | 端口 | 指向代码 |
|---|---|---|---|
| `ai.openclaw.dashboard` | PID 67715，存活 17d20h | **`*:18793`（全网卡暴露）** | `workspace/model-scheduling-dashboard/` 已不存在 |
| `ai.openclaw.model-scheduling` | PID 66605，存活 16d18h | `127.0.0.1:20128` | `~/.openclaw/model-scheduling/` 已不存在 |
| `ai.openclaw.delivery-management-web` | 未运行，exit 2 | 8088 | `business/bangcle-security-delivery/` 仅剩 logs |
| `bangcle.delivery-web` | 未运行，exit 78 | 8088 | 同上 + env wrapper（已丢） |
| `pm2.bangcle`（Label 实为 **`com.PM2`**） | 未加载，`root:wheel` | — | pm2 可执行文件 + `~/.pm2` 均不存在 |

清理后：**当前全部 LISTEN 端口均绑 `127.0.0.1`/`[::1]`，无一对外暴露**（清 dashboard 前有 `*:18793`）。

**备份**：`~/.openclaw/backups/launchagents-2026-08-23/` 共 5 个 plist（重开发时的端口/入口/版本唯一线索）。
业务代码已随 `openclaw reset` 清除，需从 GitHub 重新拉取。

**治理规则（新增）**：

1. 新增任何 LaunchAgent 必须同步登记到本节，包括 Label、plist 路径、监听地址、代码入口
2. **清理 workspace 目录时必须同步 `bootout` 对应 LaunchAgent** —— `KeepAlive` 只在进程**退出**时重启，不检查可执行文件是否还在，代码删了进程不退就会以空壳状态长期存活
3. 监听地址默认绑 `127.0.0.1`，`*:<port>` 需显式理由
4. 清理流程见技能 `macos-orphan-launchagent-cleanup`

**相关日志路径**：`~/Library/Logs/openclaw/`（已清空）、`business/*/logs/`（已清空，目录保留）

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
| 2026-08-22 | 0.4 | 新增 L2 配置管理组件（ADR-007）：脱敏快照 + 四步变更流程 + 实测探边界 + 漂移检测；contextWindow 改为实测值（ark-code-latest 224k）|
| 2026-08-22 | 0.5 | 新增 L2 工具策略治理（ADR-008）：三态治理模型 + 六项审计；§5.4 回答原预留问题；**L2 核心组件建设完成** |
| 2026-08-22 | 0.6 | 新增 L2 记忆语义检索组件（ADR-009）：本地 GGUF embedding 为主 provider |
| 2026-08-23 | 0.7 | 建设路径 review — 文档与实际对齐；§3.2 组件表修正（7 组件全部标「已建设」+ 收集四件套清单）；§6 阶段标记完成/入口条件/暂缓状态；§0 元信息清掉过期待办；ADR-010 accepted |
| 2026-08-23 | 0.8 | 全盘 review + 14 项修复：修正「各模型自治」与实配 `compaction.model` 委托的自相矛盾；补 §8.1.1 LaunchAgent 服务层；凭据明文 5→1 处（SecretRef）；`plugins.allow` 显式白名单；self-learning 降为 `propose` + `approvalPolicy: pending`；技能 25→23（macos 四合一）；EXP-009 沉淀 |
| 2026-08-24 | 0.9 | compaction 跨 provider 反模式定案 → 改 `coding-plan/deepseek-v4-flash`（同主会话 provider）；上下文管理实际生效率由「已建设」纠正为 **2/3 层**（session pruning 死配置）；记忆检索健康监控落地（ADR-009 决策 4，行为探针 + 注入故障双向验证）；sticky 模型隔离 |
| 2026-08-24 | 1.0 | 知识库六项子能力补齐（新增 `--render` 渲染 / `--export` 导出，往返无损实测 24/24 字节一致 + xref 双向对称）⇒ 阶段 3 **能力就绪 6/6**；七条件复测仍 0/7 ⇒ 维持暂缓，并在 ADR-003 §4.2.1 明确「触发条件非待办清单」；`.zshenv` 非法变量名 + 冗余明文 key 清理 |
| 2026-08-24 | 1.1 | 回答 Rex「建设到哪一步」：L1 能力使用盘点补全（9 项逐一实查 + 未使用/受限原因表，原两个「预留位」问号已答）；L2 组件计数口径校准（能力表 10 行 vs 四件套 7 个的差异说明，原名单漏记忆语义检索、误列上下文管理）；§6.3 阶段 3 数据由 08-23 旧值更新为 08-24 复测值（24 篇/孤岛 0）|

---

## 相关文档

- 知识库索引：`../knowledge-base/README.md`
- 经验沉淀模型：`../knowledge-base/by-category/project-experience/README.md`
- ADR 模板：`../knowledge-base/templates/ADR.md`
- 经验卡片模板：`../knowledge-base/templates/EXPERIENCE-CARD.md`
- EXP-20260821-001（Tavily 工具解锁）：`../knowledge-base/by-category/project-experience/correct/EXP-20260821-001-tavily-tools-also-allow.md`
