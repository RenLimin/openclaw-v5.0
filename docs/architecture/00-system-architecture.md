# 系统架构

> 综合开放平台的分层架构设计。本文档是系统建设的**单一事实来源 (Single Source of Truth)**。
>
> **维护原则**：
> - 架构变了 → 改本文档
> - 架构决策变了 → 改本文档 + 新增/更新 ADR
> - 单文件、单一来源、可被审计
> - 2026-08-21 初始化,2026-08-24 重构为运行时抽象范式

## 0. 元信息

| 字段 | 值 |
|---|---|
| 文档版本 | 2.8 (2026-09-01 — 新增 L4 Bangcle PPT 模板系统) |
| 文档状态 | active |
| 运行时 cron | 仅 heartbeat:main(30m),所有业务 cron 已清除(2026-08-26) |
| 决策状态 | 5 层架构已锁定(ADR-012 accepted,替代 ADR-001) |
| 配套文档 | `../knowledge-base/README.md` |
| 待办 | 无(L3 启动待 Rex 拍板,见 §6.2) |

---

## 1. 设计原则

| 原则 | 说明 |
|---|---|
| **分层自治** | 每层只依赖下层,禁止跨层调用 |
| **契约稳定** | 层间通过明确定义的接口契约通信,契约变更需走 ADR |
| **运行时抽象** | L2-L4 只依赖抽象契约,不绑定任何具体 Agent 运行时(ADR-012) |
| **适配隔离** | 运行时切换只改 L1 适配层,不影响上层 |
| **复用优先** | 专有业务必须从通用业务层继承,仅叠加专有规则 |
| **治理横切** | 安全、合规、可观测、成本、组织协作作为横切关注点贯穿所有层 |
| **演进可逆** | 每一层的扩展点允许演进,但不得破坏已有契约 |
| **单一来源** | 系统状态以本文档为准;变更必须更新本文档 |

### 1.1 运行时选型原则

> AI Agent 运行时是**可变因素**,系统安装部署后由使用人指定。

| 原则 | 说明 |
|---|---|
| **安装时选型** | 系统安装完成后,由使用人根据业务需求选择 Agent 运行时 |
| **最小契约** | 运行时只需满足 L1 抽象契约(§3.2),不要求功能完全对等 |
| **适配层隔离** | 每个运行时一个适配层,切换时不影响 L2-L4 |
| **当前默认** | OpenClaw 是当前默认运行时(2026-08-24),非唯一选项 |

**可选运行时**(示例,不限于此):

| 运行时 | 适用场景 | 当前状态 |
|---|---|---|
| **OpenClaw** | 全功能 Agent 平台,多通道,插件生态 | ✅ 当前默认 |
| **Claude Code** | 编码为主,CLI 交互 | 📋 可选 |
| **CrewAI** | 多 Agent 协作,工作流编排 | 📋 可选 |
| **LangGraph** | 复杂状态机,精细控制 | 📋 可选 |
| **自研运行时** | 特殊需求,完全定制 | 📋 可选 |

### 1.2 开发状态标记

> 本文档所有「状态」字段使用以下六态标记。

| 标记 | 含义 | 说明 |
|---|---|---|
| 📐 | 设计态 | 纯设计文档,不涉及代码开发 |
| 📋 | 架构预留 | 接口/概念已定义,待后续版本落地 |
| 🚧 | 部分就绪 | 核心能力已有实现,部分子模块待开发 |
| 🔨 | 开发中 | 当前迭代正在实现 |
| 🧪 | 测试中 | 已实现,正在集成测试 |
| ✅ | 已上线 | 生产环境稳定运行 |

**回写规则**: 每次开发迭代完成后,更新对应的状态标记 + 记录版本号/日期。

---

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
│      · 运行时无关                                            │
├─────────────────────────────────────────────────────────────┤
│  L3  通用业务层 (Generic Business Layer)                     │
│      · 跨场景通用业务能力                                    │
│      · 运行时无关                                            │
├─────────────────────────────────────────────────────────────┤
│  L2  基础设施层 (Infrastructure Layer)                       │
│      · 自定义组件 / 系统资产                                 │
│      · 只依赖 L1 抽象契约,不绑定具体运行时                   │
├─────────────────────────────────────────────────────────────┤
│  L1  运行时抽象层 (Runtime Abstraction Layer)                │
│      · 定义 Agent 运行时的最小能力契约                       │
│      · 当前实现: OpenClaw (适配层: adapters/openclaw/)       │
│      · 适配层: adapter.py / config.py / health.py            │
│      · 可替换: Claude Code / CrewAI / LangGraph / 自研       │
├─────────────────────────────────────────────────────────────┤
│  L0  系统安装层 (Installation Layer)                         │
│      · 0→1 安装 / 运行时选型 / 环境验证                      │
│      · 一键部署 + 适配层初始化                               │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 调用关系

```
L4 → L3 → L2 → L1 → L0    (允许)
L4 → L2 / L1 / L0         (禁止 — 跨层调用)
L3 → L4                   (禁止 — 反向依赖)
L1 → 任何上层              (禁止 — 反向依赖)
```

**允许的**:
- 上层调用下层(逐层,不跳跃)
- 同层内通过契约调用
- L0 被 L1 调用(安装层提供环境信息)

**禁止的**:
- 任何层"穿越"调用下下层
- 任何层反向依赖
- L2-L4 直接调用具体运行时 API(必须通过 L1 抽象接口)

---

## 3. 各层详细职责

### 3.1 L0 — 系统安装层 (Installation Layer)

**来源**: 自定义

**职责**: 从零到可运行(0 → 1),包括运行时选型和适配层初始化。

**安装流水线**:

| 步骤 | 内容 | 产出 |
|---|---|---|
| 0.0 | 环境检测(OS/依赖/网络/权限) | 环境报告 |
| 0.1 | 运行时选型(使用人指定) | 运行时配置 |
| 0.2 | 运行时安装(含依赖) | 可用运行时 |
| 0.3 | 适配层初始化 | L1 抽象接口就绪 |
| 0.4 | 系统验证(契约测试) | 验证报告 |
| 0.5 | 快照入库 | 可回溯的基线 |

**选型流程**:

```
使用人指定运行时
  └→ 检查运行时是否满足 L1 最小契约(§3.2)
       ├→ 满足 → 安装运行时 + 初始化适配层
       └→ 不满足 → 提示缺失能力,要求补充适配层或选择其他运行时
```

**当前状态**: 📋 架构预留(当前直接安装 OpenClaw,选型流程待实现)

**演进方式**:
- 新增运行时 = 新增适配层 + 选型选项
- 不影响已有 L2-L4

### 3.2 L1 — 运行时抽象层 (Runtime Abstraction Layer)

**来源**: 抽象契约(自定义) + 适配层(按运行时)

**职责**: 定义 Agent 运行时的最小能力契约,隔离具体实现。

**设计约束**:
- **不可直接调用**: L2-L4 只能通过抽象接口调用,不能直接引用具体运行时 API
- **最小契约**: 只抽象当前实际需要的接口,不为未来假设过度设计
- **适配层隔离**: 每个运行时一个适配层,放在 `adapters/<runtime>/` 目录下

#### 3.2.1 L1 最小能力契约

Agent 运行时必须提供以下能力,无论底层框架是什么:

| # | 能力 | 抽象接口 | 说明 |
|---|---|---|---|
| 1 | **Agent Loop** | `execute(message, context) → response` | 接收消息,推理,工具调用,返回结果 |
| 2 | **工具执行** | `register_tool(name, schema, fn)` / `call_tool(name, input) → output` | 注册和调用工具 |
| 3 | **记忆** | `memory_read(key)` / `memory_write(key, val)` / `memory_search(query)` | 持久化记忆读写检索 |
| 4 | **定时调度** | `schedule(cron, task)` / `cancel(task_id)` / `list_schedules()` | 定时触发任务 |
| 5 | **通道接入** | `register_channel(name, adapter)` / `send_message(channel, msg)` | 消息输入输出 |
| 6 | **配置管理** | `config_get(path)` / `config_set(path, val)` / `config_validate()` | 配置读写校验 |
| 7 | **凭据管理** | `credential_get(ref)` / `credential_rotate(ref)` | 凭据安全引用和轮转 |
| 8 | **沙箱隔离** | `sandbox_execute(command, opts) → result` | 隔离执行环境 |
| 9 | **上下文管理** | `context_status() → tokens` / `context_compact()` | 上下文状态查询和压缩 |
| 10 | **健康检查** | `health() → status` | 运行时健康状态 |

#### 3.2.2 适配层规范

```
adapters/
├── openclaw/          ← 当前默认实现
│   ├── adapter.py     ← L1 抽象接口的 OpenClaw 实现
│   ├── config.py      ← OpenClaw 特有配置映射
│   └── health.py      ← OpenClaw 健康检查
├── claude-code/       ← 未来可选(待实现)
├── crewai/            ← 未来可选(待实现)
└── custom/            ← 自研运行时(待实现)
```

适配层职责:
- 将 L1 抽象接口翻译为具体运行时的 API 调用
- 处理运行时特有概念到抽象契约的映射
- 提供运行时健康检查和能力报告
- 版本绑定: 适配层与运行时版本同步更新

#### 3.2.3 当前默认运行时: OpenClaw

> OpenClaw 是当前默认 Agent 运行时(2026-08-24),通过适配层实现 L1 抽象契约。

**OpenClaw 能力到 L1 契约的映射**:

| L1 契约 | OpenClaw 实现 | 备注 |
|---|---|---|
| Agent Loop | 内置 agent loop + 模型路由 | 自动 prompt 组装,会话管理 |
| 工具执行 | 运行时工具系统 | 通过 ToolPolicy 控制可见工具集 |
| 记忆 | 运行时记忆系统 | 语义检索(当前: 本地 embedding) |
| 定时调度 | 运行时调度器 | 支持 cron/every/event 三种调度 |
| 通道接入 | 运行时通道系统 | 当前: WeCom + webchat |
| 配置管理 | 运行时配置系统 | 结构化配置,支持加密引用 |
| 凭据管理 | 运行时凭据系统 | 集中式安全存储,支持轮转 |
| 沙箱隔离 | 运行时沙箱 | 容器后端,非主会话隔离 |
| 上下文管理 | 运行时上下文系统 | 自动压缩 + 溢出防护状态机 |
| 健康检查 | 运行时自检 | 全面健康状态报告 |

**OpenClaw 特有概念**(仅在适配层内部使用,L2-L4 不可见):

| 概念 | 说明 | L2-L4 是否可见 |
|---|---|---|
| `tools.profile` | 工具白名单配置 | ❌ 抽象为 ToolPolicy |
| `tools.alsoAllow` | 工具追加允许 | ❌ 抽象为 ToolPolicy |
| `plugins.allow` | 插件白名单 | ❌ 抽象为 PluginRegistry |
| `SecretRef` | 凭据引用机制 | ❌ 抽象为 CredentialProvider |
| `heartbeat` | 心跳轮询 | ❌ 抽象为 HealthCheck |
| `compaction.model` | 压缩模型委托 | ❌ 抽象为 ContextManager |

**OpenClaw 版本**: 2026.7.2-beta.7(适配层需同步更新)

#### 3.2.4 L1 能力使用盘点(2026-08-24 实查)

| L1 能力 | 使用状态 | 说明 |
|---|---|---|
| Agent Loop | ✅ 全量使用 | 主 agent + 定时任务隔离运行 |
| 工具执行 | ✅ 使用 | 通过 ToolPolicy 控制可见工具集 |
| 记忆 | ✅ 全量使用 + 自建监控 | 语义检索 + 健康监控 |
| 定时调度 | ✅ 使用 | 1 个 enabled 调度任务(heartbeat:main, 30m) |
| 通道接入 | ⚠️ 部分使用 | 当前: WeCom + webchat |
| 配置管理 | ✅ 全量使用 | + 自建变更治理(ADR-007) |
| 凭据管理 | ✅ 全量使用 | 集中式凭据存储 |
| 沙箱隔离 | ✅ 已启用 | 容器后端,非主会话隔离 |
| 上下文管理 | ✅ 全量使用 | 自动压缩 + 溢出防护状态机 |
| 健康检查 | ✅ 全量使用 | 全面自检 + 行为探针 |

### 3.3 L2 — 基础设施层 (Infrastructure Layer)

**来源**: 自定义

**职责**: 封装/适配 L1 能力,提供本系统专用的基础设施服务。

**关键约束**:
- **只依赖 L1 抽象契约**,不直接调用具体运行时 API
- 提供给 L3 的接口必须稳定(契约变更需 ADR)
- 不感知 L3 / L4 的业务含义
- 运行时切换时,L2 组件**无需修改**(适配层吸收差异)

**组件分类**(按职能):

| 组件类 | 说明 | 状态 | 标记 |
|---|---|---|---|
| **配置管理** | 变更治理(快照/审计/漂移检测) | 已上线 | ✅ |
| **可观测性适配** | logging、metrics、tracing | 已上线 | ✅ |
| **持久化适配** | memory、文件、KV、未来 SQL/NoSQL | 已上线 | ✅ |
| **知识库能力** | Markdown 解析/索引/三维查询/交叉引用/渲染/导出 | 已上线 | ✅ |
| **凭据管理** | 集中式 secrets 存储、SecretRef 解析 | 已上线 | ✅ |
| **工具策略** | 工具可见性治理(三态模型) | 已上线 | ✅ |
| **上下文管理** | 自动压缩 + 溢出防护状态机 | 已上线 | ✅ |
| **记忆语义检索** | 本地 embedding + 向量索引 + 健康监控 | 已上线 | ✅ |
| **沙箱隔离** | Docker 后端 + 加固基线 | 已上线 | ✅ |
| **会话生命周期管理** | 自动清理过期会话(分级策略 + deleteAfterRun),cron 已清除,待重建 | 设计完备 / cron 未启用 | 📋 |
| **错误自动处理** | 检测→分级→自愈闭环(Error Contract),cron 已清除,待重建 | 设计完备 / cron 未启用 | 📋 |
| **模型调度** | 智能模型路由(多级 fallback + token 压缩 + 用量感知) | 已上线 | ✅ |
| **Office 文档生成** | Word/Excel/PPT 文件生成（python-docx/openpyxl/xlsxwriter/pptxgenjs） | 已上线 | ✅ |
| **工具/技能封装** | domain-specific skills、工具二次封装 | 复用 + 自建 | 🚧 |
| **调度/任务编排** | 定时任务、隔离运行、心跳 | 复用 L1 | 📋 |

> **状态取值口径**: `已上线` 要求 **ADR + DESIGN.md + 实现** 三件齐备。

**已建设组件四件套清单**:

| 组件 | ADR | DESIGN.md | 实现 | 验证方式 |
|---|---|---|---|---|
| 可观测性 | 004 | `components/observability/` | `scripts/observability/agent_observer.py` | `--daily --jsonl` 实跑 |
| 凭据管理 | 005 | `components/credentials/` | `scripts/credentials.sh` | `scan_secrets.sh` |
| 持久化 | 006 | `components/persistence/` | `persistence/` (connection/repository/migration/schemas) | 迁移幂等测试 |
| 配置管理 | 007 | `components/config/` | `scripts/config.sh` | `config.sh diff` 漂移检测 |
| 工具策略 | 008 | `components/tool-policy/` | `scripts/tool_policy_audit.sh` | 六项审计 |
| 记忆语义检索 | 009 | `components/memory-embedding/` | 配置态 + `scripts/observability/memory_search_monitor.py` | 行为探针三态判据 |
| 知识库能力 | 010 | `components/knowledge-base/` | `scripts/kb_index.py`(六项子能力全备) | pre-commit 阻塞实测 |
| Office 文档生成 | 011 | `components/office-generation/` | 6 库工具链(python-docx/docxtpl/openpyxl/xlsxwriter/pandas/python-pptx) + pptxgenjs-pro 技能 | 6/6 库实测通过 |

**已建设组件清单**(详细):

1. **上下文管理** (2026-08-21, 08-24 升级)
   - 组件 ID: 上下文管理配置 + 溢出防护状态机
   - 功能: 两层防线自动管理上下文溢出
     - 第 1 层: Auto-compaction — 阈值维护 + 溢出恢复;摘要委托给**同 provider 的大 ctx 模型**
     - 第 2 层: Mid-turn precheck — 中途检查,中止并交给 recovery
     - ~~Session pruning~~ → ❌ 不生效(运行时 provider 白名单限制)
   - 溢出防护状态机: NORMAL → WARN → DIVERT → HARD_LIMIT → RECOVERED
     - 各模型水位阈值(基于实测 contextWindow):
       - ark-code-latest(224k): WARN 134k / DIVERT 179k / HARD_LIMIT 201k
       - deepseek-v4-flash(1024k): WARN 614k / DIVERT 819k / HARD_LIMIT 921k
   - 关键配置:
     - `mode: "safeguard"` / `keepRecentTokens: 30000` / `maxActiveTranscriptBytes: "20mb"`
     - `midTurnPrecheck.enabled: true`
   - contextWindow 校准(实测二分探边界):
     - ark-code-latest: 229376(224k) / deepseek-v4-flash: 1048576 / glm-5.3: 1M / minimax-m3: 1M
   - 文档: `../knowledge-base/by-category/project-experience/correct/EXP-20260821-003-compaction-model-delegation.md`

2. **配置管理** (2026-08-22)
   - 组件 ID: `scripts/config.sh` + `config-snapshots/`
   - 定位: **治理封装**,不重新实现运行时的配置读写
   - 解决的四个治理问题:
     - P1 变更不可追溯 → 脱敏快照入 git
     - P2 "应用成功"≠"生效" → 四步流程固化,强制读回确认
     - P3 能力声明靠推断 → 实测探边界
     - P4 配置漂移无人发现 → `--check` 模式 + pre-commit 提醒
   - 关键子命令: `audit` / `snapshot` / `diff` / `apply <patch>` / `probe <model>`
   - 脱敏策略: 精确字段名匹配 + 白名单
   - ADR: ADR-007

3. **工具策略治理** (2026-08-22)
   - 组件 ID: `scripts/tool_policy_audit.sh`
   - 核心认知: **「允许」≠「可用」** —— 三态治理(denied / allowed-but-broken / allowed-and-working)
   - 当前策略: 最小权限原则,基础工具集 + 显式追加
   - 实测发现: 记忆检索静默降级(缺 embedding provider)· 12 技能缺依赖
   - ADR: ADR-008

4. **知识库能力** (2026-08-23)
   - 组件 ID: `scripts/kb_index.py`
   - 定位: **工具链层**(非服务层)。Markdown 是永久单一来源,本组件只读
   - 能力: `--validate` / `--stats` / `--query` / `--tags` / `--xref` / `--emit-index` / `--json` / `--render` / `--export`
   - 契约: 不反向写内容文件(唯一例外: INDEX.md 标记区,纯派生视图)
   - 治理: pre-commit 第 3 段 — 阻断性错误拒绝提交
   - ADR: ADR-010

5. **凭据管理** (2026-08-21)
   - 组件 ID: `scripts/credentials.sh`
   - 方案: 文件存储 + SecretRef provider + 标准生命周期(add/rotate/revoke/audit)
   - ADR: ADR-005

6. **持久化适配** (2026-08-21)
   - 组件 ID: `persistence/` (connection/repository/migration/schemas)
   - 方案: SQLite + Repository 模式 + 版本化迁移
   - 演进路径: sqlite3 stdlib → SQLAlchemy Core → PostgreSQL
   - ADR: ADR-006

7. **记忆语义检索** (2026-08-22)
   - 组件 ID: `scripts/observability/memory_search_monitor.py`
   - 方案: 本地 GGUF embedding(零成本/零外发) + 向量索引
   - 健康监控: 行为探针三态判据(ok / degraded / down) + 注入故障双向验证
   - ADR: ADR-009

8. **沙箱隔离** (2026-08-24)
   - 组件 ID: Docker 后端 + 加固基线
   - 方案: colima 0.10.3 + docker 29.7.2 + 自定义沙箱镜像
   - 基线: `workspaceAccess=ro` / `readOnlyRoot` / `network:none` / `capDrop:ALL`
   - 验证: 子会话 uid=1000(sandbox) + 写拦截 + 断网 + 上层通道正常

9. **会话生命周期管理** (2026-08-24, 08-26 状态更新)
   - 组件 ID: `pruneAfter=48h` + `deleteAfterRun` + 分级策略 (cron 已清除,待重建)
   - 功能: 自动清理过期会话,保持会话存储健康
   - 分级策略:
     - 主会话: 永不清理
     - cron run: 完成后立即清理(deleteAfterRun)
     - 已完成 subagent: 7d 后清理
     - 探测会话: 24h 后清理
     - 每日 02:00 自动执行 `sessions cleanup --enforce`
   - 保护: `--active-key agent:main:main` 保护主会话
   - **当前状态**: 设计 + ADR + DESIGN.md 齐备,cron 任务已于 08-26 清除,待 Rex 决定是否重建
   - ADR: ADR-013
   - 设计: `components/session-lifecycle/DESIGN.md`

10. **错误自动处理** (2026-08-24, 08-26 状态更新)
    - 组件 ID: Error Contract 分级 + cron 扫描 (cron 已清除,待重建)
    - 功能: 检测→分级→自愈闭环
    - 检测: 每 2h 扫描 cron runs 失败 + 上下文水位 + 记忆检索健康
    - 分级: Sev1-4(对齐 ADR-011 Error Contract)
    - 自愈: 记忆降级→重建索引 / 上下文溢出→分流 / cron 失败→记录模式
    - 通知: Sev1 立即通知 / Sev2 下次 heartbeat / Sev3-4 日志
    - **当前状态**: 设计 + ADR + DESIGN.md 齐备,cron 任务已于 08-26 清除,待 Rex 决定是否重建
    - ADR: ADR-014
    - 设计: `components/error-handling/DESIGN.md`

11. **模型调度** (2026-08-24)
    - 组件 ID: `model-scheduling/`
    - 功能: 智能模型路由 — 按任务类型、用量、网络健康选择最优模型
    - 核心能力:
      - 模型注册表: `config/models.yaml`(从 openclaw.json 自动同步)
      - 路由规则: `config/routing.yaml`(多级 fallback + token 压缩)
      - 用量追踪: `config/usage.json`(每周从 provider API 获取)
      - 健康探测: 每小时 ping provider,标记不可用
      - 任务分类: coding / reasoning / research / chat → 不同模型策略
    - 多级 fallback: L1 优先 → L2 降级 → L3 保底
    - Token 压缩: 参考 9router RTK,对超大工具输出截断(git diff > 200 行 → 100 行)
    - 设计约束:
      - 只读 openclaw.json(通过 `config get`),绝不写入
      - 外部文件存储所有状态,故障不影响系统运行
      - 变更前必须 dry-run + 读回验证
    - 脚本: `sync_models.py` / `fetch_usage.py` / `router.py` / `health_check.py` / `proxy.py` / `config_watcher.py`
    - 代理服务: `proxy.py`(:3000,自动任务路由 + 模型选择)
    - 热更新: `config_watcher.py`(文件变更 → ≤ 10 秒自动生效)
    - 自动启动: LaunchAgent `ai.openclaw.model-scheduling`(开机自启 + 崩溃重启)
    - 回退方案: `config/rollback_main_agent.json` + `config/rollback_defaults.json` + `config/rollback_provider.json`
    - 设计: `model-scheduling/DESIGN.md`

12. **Office 文档生成** (2026-08-31)
    - 组件 ID: 011
    - 功能: 按需求 + 原始数据生成 Word/Excel/PPT 文件
    - 工具链:
      - Word: python-docx(主力) + docxtpl(模板渲染)
      - Excel: openpyxl(读写+格式) + xlsxwriter(大数据写入) + pandas(快导出)
      - PPT: pptxgenjs(高质量,已有技能 pptxgenjs-pro) + python-pptx(Python原生批量)
    - 实测验证: 6/6 库全部通过实测
      - sample_word.docx (38KB) — 标题/表格/样式/页眉页脚
      - rendered_working.docx (37KB) — 模板渲染/段落循环/条件
      - sample_excel.xlsx (9.7KB) — 多sheet/公式/条件格式/图表
      - sample_xlsxwriter.xlsx (273KB) — 10000行/0.05s/数据条/图表
      - sample_pandas.xlsx (6.6KB) — DataFrame导出/多sheet
      - sample_ppt.pptx (42KB) — 3页/表格/柱状图/备注
    - 已知限制: docxtpl表格循环bug / xlsxwriter只写不改 / openpyxl number_format需单独赋值
    - ADR: ADR-016
    - 设计: `components/office-generation/DESIGN.md`

**L2 组件建设状态**: **12 个组件设计齐备**,其中 10 个已上线(7 个治理组件 + 沙箱 + 模型调度),2 个 cron 驱动型(会话生命周期管理 + 错误自动处理)设计完备但 cron 已清除、待重建。

**配置安全保护** (横切关注点,2026-08-26):
- **问题**：自定义资产直接写入 openclaw.json 无任何保护,可能导致系统 crash(参考 08-26 SQLite 损坏事故)
- **统一原则**：所有写 openclaw.json 的操作必须经过保护通道(五步流程: 回退点→dry-run→写入→validate→读回)
- **安全写入通道**：`scripts/config_safe_write.sh` — 统一入口,禁止绕过
- **已加固资产**：`adapter.py`(内部实现同等保护) / `config.sh apply`(深层读回+自动回退) / `setup_agents.sh`(幂等+动态rollback)
- **回退机制**：写入前自动保存带时间戳的快照到 `~/.openclaw/backups/config-safe-write/`,失败自动恢复

**预留位**:
- 知识库**自建系统**(服务形态: DB + Web 渲染) — 与上方「知识库能力」组件区分
  - 启动条件见 ADR-003 §4.2 七触发条件(2026-08-24 复测仍 **0/7**,暂缓)
  - 就绪度: 能力已备 6/6,需求未达 0/7

**演进方式**:
- 优先复用 L1 能力
- 必要时自建 wrapper,但不得绕过 L1 抽象层
- 每个组件必须有"配置 → 验证 → 监控"三件套
- 组件变更如影响 L3 接口 → 需 ADR

### 3.4 L3 — 通用业务层 (Generic Business Layer)

**来源**: 自定义

**职责**: 跨场景通用的业务能力,可被 L4 复用。**运行时无关**。

**组织方式**:
- 按业务维度切分,每维度独立模块
- 维度间通过契约通信

**关键约束**:
- 不感知专有业务上下文
- 不直接依赖 L4(反向依赖禁止)
- 不直接调用 L1/L2(应通过 L3 间接获得基础设施能力)

#### 3.4.1 业务维度划分原则

| 维度类型 | 划分依据 | 示例 |
|---|---|---|
| **领域实体** | 业务核心实体 | user / product / order / payment |
| **领域流程** | 跨实体的业务流 | checkout / fulfillment / refund |
| **横切能力** | 通用工具 | notification / search / analytics / audit |

**判断标准**("这个能力属于 L3 还是 L4?"):
- ✅ L3: 跨项目/跨客户通用、不含专有规则
- ❌ L4: 仅 1 个项目/客户使用、含专有规则或专有数据

#### 3.4.2 通用业务层状态

**当前**: 📐 设计中 — [L3 架构设计](./02-generic-business-layer.md) v1.3 + [知识库体系架构](./03-knowledge-base-architecture.md) v1.0 已提交，待 Rex 评审确认后启动建设

**预留位**(待启动时填充):
- L3 第一个维度的选型理由
- 维度间的依赖图
- 维度的最小能力清单
- 维度的契约形式(API / event / data schema)

### 3.5 L4 — 专有业务层 (Proprietary Business Layer)

**来源**: 自定义

**职责**: 在通用业务能力之上叠加专有业务信息。**运行时无关**。

**关键约束**:
- 必须继承 L3,不得重写通用能力
- 仅新增: 专有规则、专有数据、专有流程
- 不直接调用 L2(应通过 L3 间接获得)

**继承机制**:

```
L4 专有业务
  ├── extends L3 通用业务维度 A
  ├── extends L3 通用业务维度 B
  └── adds 专有规则/数据/流程
```

**扩展点类型**:

| 扩展类型 | 说明 | 例子 |
|---|---|---|
| **数据扩展** | 继承 L3 schema,添加专有字段 | `User` L3 + `User.proprietary_metadata` L4 |
| **规则扩展** | 继承 L3 业务逻辑,添加专有规则 | `Order.validate()` L3 + `Order.compliance_check()` L4 |
| **流程扩展** | 继承 L3 流程,插入专有步骤 | `checkout` L3 + `risk_assessment` L4 |
| **接口扩展** | L4 暴露专有 API,不影响 L3 | `/api/proprietary/*` |

**当前**: 🚧 建设中 — 首个 L4 组件 [Bangcle PPT 模板系统](./components/bangcle-ppt-template/DESIGN.md) 已注册 (CPT-012, ADR-017)

**已建设组件**:

| 组件 ID | 名称 | 职责 | ADR | DESIGN.md | 状态 |
|---|---|---|---|---|---|
| CPT-012 | Bangcle PPT 模板系统 | Bangcle 官方 VI 设计规范 + 页面类型模板 + pptxgenjs 代码模板 | ADR-017 | `components/bangcle-ppt-template/` | 🚧 (技能已建,待实测) |

> **与 L2 协同**: Bangcle PPT 模板系统(L4)调用 pptxgenjs-pro(L2, CPT-004)通用生成能力,叠加 Bangcle 专属设计规范。

---

## 4. 横切关注点 (Cross-Cutting Concerns)

横切关注点**不构成独立层**,而是贯穿 L0~L4 的约束与能力。

| 关注点 | 在每层的要求 | 当前状态 | 标记 |
|---|---|---|---|
| **安全** | 凭据管理、权限边界、输入校验、审计日志 | 凭据管理已上线 | 🚧 |
| **合规** | 数据驻留、隐私、监管要求 | 架构预留 | 📋 |
| **可观测** | 日志、指标、追踪、告警 | 架构预留(当前依赖运行时 + 业务日志) | 📋 |
| **成本** | 资源使用、API 调用、外部服务计费 | 架构预留 | 📋 |
| **组织协作** | 文档、决策记录、知识沉淀 | 已上线(知识库 + ADR + EXP) | ✅ |
| **知识管理** | 知识库分层、经验沉淀、ADR | 已上线(轻量方案) | ✅ |

---

## 5. 运行时契约边界

> 这是本系统最重要的约束 —— **L2-L4 不得绕过 L1 抽象层直接调用运行时 API**。

### 5.1 可控范围
- Skills / 自定义插件
- Workspace 文件 / 配置
- 定时任务 / 自动化任务
- 自有工具(exec、文件、网络)
- Memory / 日志
- 第三方集成(IM、平台)
- 工具策略(通过 ToolPolicy 抽象)
- 凭据管理(通过 CredentialProvider 抽象)

### 5.2 不可控范围
- 运行时核心行为 / 安全策略
- Gateway 内部实现
- Agent prompt / 工具策略(除非显式允许)
- 系统提示注入
- 运行时内部 API 行为

### 5.3 扩展点(已知)
- Skills: 新增、扩展
- Agent 配置: 模型、工具、权限
- 定时任务: 自定义任务
- 工具: 新增(需符合契约)
- Memory: 读写
- 外部平台: 经由运行时提供的接入
- 凭据: SecretRef(provider 形式: env/file/exec)

> 任何试图绕过 5.2 或在 5.3 之外扩展的能力,必须先走 ADR。

### 5.4 工具策略治理

**核心认知修正**: 工具治理不只是"哪些被 deny",而是**三种状态**:

| 状态 | 可表达 | 危险性 |
|---|---|---|
| `denied` | ✅ | 低 —— 明确失败 |
| `allowed-but-broken` | ❌ **不能** | **高 —— 静默失败** |
| `allowed-and-working` | ✅ | — |

**审计**: `bash scripts/tool_policy_audit.sh`(六项检查)

### 5.5 统一错误契约

> 跨层错误协议,定义见 [ADR-202608-011](../knowledge-base/by-category/project-experience/adr/ADR-202608-011-unified-error-contract.md)

所有层(L0-L4)产生的错误统一使用以下结构:

| 字段 | 说明 |
|---|---|
| `code` | 全局唯一,格式 `ERR_{LAYER}_{TYPE}` |
| `severity` | Sev1 致命 / Sev2 严重 / Sev3 警告 / Sev4 信息 |
| `recoverable` | 系统能否自动恢复 |
| `retryable` | 是否可以重试 |
| `message` | 人类可读描述 |
| `context` | 至少含 `layer` + `component` |

**已分类的历史错误**: 见 ADR-011 §6.4

---

## 6. 演进路线

### 6.1 阶段一:基座搭建(✅ 已上线,2026-08-21~24)

| 项 | 状态 | 标记 |
|---|---|---|
| L0 + L1 + L2 最小可用 | 已上线 | ✅ |
| L3 / L4 暂未启动 | 架构预留 | 📋 |
| 知识库轻量方案(Markdown + 元数据) | 已上线 | ✅ |
| 工作区基础文件(AGENTS / IDENTITY / SOUL / USER / MEMORY) | 已上线 | ✅ |
| 12 个 L2 组件四件套齐备 | 已上线 | ✅ |
| 16 份 ADR accepted | 已上线 | ✅ |
| 模型调度(智能路由 + 多级 fallback + token 压缩) | 已上线 | ✅ |
| 上下文溢出防护状态机 | 已上线 | ✅ |
| 运行时抽象层(L1) | 已上线 | ✅ |
| 会话生命周期管理(cron + 分级策略) | 已上线 | ✅ |
| 错误自动处理(检测→分级→自愈闭环) | 已上线 | ✅ |
| Office 文档生成(Word/Excel/PPT,6库实测) | 已上线 | ✅ |
| L4 Bangcle PPT 模板系统(VI规范,ADR-017) | 建设中 | 🚧 |

**目标**: 跑通分层,验证契约 ✅

**完成条件核对**:
- ✅ 系统架构文档(本文件)
- ✅ 知识库骨架(三维模型 + ADR-002)
- ✅ 工作区配置(USER/IDENTITY/SOUL)
- ✅ 第一个 L2 组件(Tavily)
- ✅ ADR-001/002/003(4 层架构 + 三维模型 + 演进路径)
- 🚧 上下文管理(自动压缩 + 溢出防护状态机;session pruning 层不生效 — 2/3 层实际生效)
- ✅ 配置管理(快照 + 四步流程 + 漂移检测)
- ✅ 工具策略治理(三态模型 + 六项审计)
- ✅ 记忆语义检索(本地 embedding + 健康监控)
- ✅ 知识库工具链(`kb_index.py`: 六项子能力全备)
- ✅ 沙箱隔离(Docker + non-main,实测 uid=1000)
- ✅ 运行时抽象层(L1 契约 + OpenClaw 适配层)

### 6.2 阶段二:业务能力沉淀(**已满足入口条件,待 Rex 定夺**)

| 项 | 状态 | 标记 |
|---|---|---|
| L3 按业务维度逐步建设 | 架构预留 | 📋 |
| L4 开始引入 | 架构预留 | 📋 |
| 知识库继续以文件形式承载,增加工具链 | 已上线 | ✅ |

**目标**: 验证 L3 维度划分、L4 继承机制

**入口条件**: 阶段一 ADR 全部完成、L2 最小可用稳固

**入口条件已满足**。阶段二未启动的原因是 Rex 要求暂缓 L3 建设。

### 6.3 阶段三:自建知识库系统(**暂缓** — 触发条件 0/7)

| 项 | 状态 | 标记 |
|---|---|---|
| L2 工具链层(`kb_index.py`) | 已上线 | ✅ |
| L2 服务层(DB + Web 渲染) | 架构预留 | 📋 |
| 人机协作阅读、跨系统移植 | CLI 已就绪 / 服务形态预留 | 🚧 |
| 文档/经验/ADR 全部迁入自建系统 | 架构预留 | 📋 |
| 文件形式保留为**导出格式** | 已上线 | ✅ |

**启动触发条件**(ADR-003 §4.2,**需 ≥2 个达成**):
- 2026-08-24 复测: **0/7**
- 就绪度: 能力已备 6/6,需求未达 0/7
- 下一评估: ADR-003 阶段 1 验收(2026-09-21 或内容质变时)

### 6.4 阶段四:企业级治理

| 项 | 状态 | 标记 |
|---|---|---|
| 横切关注点全面落地 | 架构预留 | 📋 |
| 完整的可观测、合规、安全体系 | 架构预留 | 📋 |
| 成本管理(资源、API、外部服务计费) | 架构预留 | 📋 |

**入口条件**: 业务规模/团队规模驱动治理需求

---

## 7. 决策记录

| # | 主题 | 优先级 | 状态 |
|---|---|---|---|
| ADR-001 | 4 层架构决策 | 高 | ✅ accepted (2026-08-21,已被 ADR-012 替代为 5 层) |
| ADR-002 | 知识库三维模型 | 中 | ✅ accepted (2026-08-21) |
| ADR-003 | 知识库承载形式演进路径 | 中 | ✅ accepted (2026-08-21) |
| ADR-004 | L2 可观测性适配 | 中 | ✅ accepted (2026-08-21) |
| ADR-005 | L2 凭据管理通用化 | 高 | ✅ accepted (2026-08-21) |
| ADR-006 | L2 持久化适配(SQLite + Repository) | 高 | ✅ accepted (2026-08-21) |
| ADR-007 | L2 配置管理(治理封装) | 高 | ✅ accepted (2026-08-22) |
| ADR-008 | L2 工具策略治理(三态模型) | 中 | ✅ accepted (2026-08-22) |
| ADR-009 | L2 记忆语义检索(本地 GGUF embedding) | 高 | ✅ accepted (2026-08-22) |
| ADR-010 | L2 知识库工具链 | 中 | ✅ accepted (2026-08-23) |
| ADR-011 | 统一错误契约(Error Contract) | 中 | ✅ accepted (2026-08-24) |
| ADR-012 | Agent 运行时作为可变因素 | 高 | ✅ accepted (2026-08-24) |
| ADR-013 | L2 会话生命周期管理 | 中 | ✅ accepted (2026-08-24) |
| ADR-014 | L2 错误自动处理(检测→分级→自愈闭环) | 高 | ✅ accepted (2026-08-24) |
| ADR-015 | L2 动态压缩模型路由 | 中 | ✅ accepted (2026-08-25) |
| ADR-016 | L2 Office 文档生成能力(Word/Excel/PPT,6库实测) | 高 | ✅ accepted (2026-08-31) |
| ADR-017 | L4 Bangcle PPT 模板系统(VI规范+页面类型模板) | 中 | ✅ accepted (2026-09-01) |

---

## 8. 依赖与选型约束

### 8.1 强依赖

| 依赖 | 用途 | 约束 |
|---|---|---|
| Node.js v26.7.0 | Agent 运行时基础 | 跟随运行时最低版本 |
| macOS 26.5.2 | 当前运行平台 | 跨平台时需注意服务管理差异 |

### 8.1.1 运行时服务管理

> 运行时以系统服务方式启动,通过 LaunchAgent(macOS)或 systemd(Linux)管理。

**当前服务**(实测@2026-08-24):

| Label | 状态 | 监听 | 备注 |
|---|---|---|---|
| 运行时核心服务 | ✅ 运行中 | loopback | 不可动 |

**治理规则**:
1. 新增任何系统服务必须同步登记到本节
2. 清理 workspace 目录时必须同步停用对应服务
3. 监听地址默认绑 `127.0.0.1`,全网卡暴露需显式理由

### 8.2 选型边界

| 类别 | 可选 | 不可选 |
|---|---|---|
| Agent 运行时 | OpenClaw / Claude Code / CrewAI / LangGraph / 自研 | 不满足 L1 最小契约的运行时 |
| 知识库系统 | Markdown + frontmatter(当前)/ 自建系统(演进) | 强依赖单一外部 SaaS |
| 凭据管理 | SecretRef(env/file/exec) | 硬编码到 markdown |
| 工具来源 | 运行时 built-in + approved plugins | 绕过 L1 抽象层 |

---

## 9. 术语表

| 术语 | 含义 |
|---|---|
| **运行时** | Agent 运行时的简称,如 OpenClaw / Claude Code / CrewAI |
| **L1 抽象契约** | 运行时必须提供的最小能力集(§3.2.1) |
| **适配层** | 将 L1 抽象接口翻译为具体运行时 API 的代码层 |
| **契约** | 层间或模块间明确定义的接口约定,变更需 ADR |
| **维度** | L3 业务能力的切分单位(如 user/order/payment) |
| **扩展点** | 父层为子层预留的可扩展位置 |
| **横切关注点** | 贯穿多层的通用约束(安全/合规/可观测等) |
| **SecretRef** | 凭据引用机制(运行时适配层内部实现,L2-L4 通过 CredentialProvider 抽象访问) |
| **ToolPolicy** | 工具可见性治理抽象(替代运行时的 tools.profile/alsoAllow) |
| **CredentialProvider** | 凭据管理抽象(替代运行时的 SecretRef 直接调用) |
| **ContextManager** | 上下文管理抽象(替代运行时的 compaction 配置直接访问) |
| **HealthCheck** | 健康检查抽象(替代运行时的 heartbeat/doctor 直接调用) |

---

## 10. 变更历史

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-08-21 | 0.1 | 初版骨架(4 层架构 + 契约 + 演进路线) |
| 2026-08-21 | 0.3 | 新增 L2 上下文管理组件 |
| 2026-08-22 | 0.4 | 新增 L2 配置管理组件 |
| 2026-08-22 | 0.5 | 新增 L2 工具策略治理 |
| 2026-08-22 | 0.6 | 新增 L2 记忆语义检索组件 |
| 2026-08-23 | 0.7 | 建设路径 review — 文档与实际对齐 |
| 2026-08-23 | 0.8 | 全盘 review + 14 项修复 |
| 2026-08-24 | 0.9 | compaction 跨 provider 反模式定案 |
| 2026-08-24 | 1.0 | 知识库六项子能力补齐 |
| 2026-08-24 | 1.1 | L1 能力盘点补全 |
| 2026-08-24 | 1.2 | 沙箱隔离方案 B 落地 |
| 2026-08-24 | 1.3 | v4.0 对比优化: 状态机 + 六态标记 + Error Contract |
| 2026-08-24 | **2.0** | **范式转换: Agent 运行时作为可变因素。新增 L0 安装层 + L1 运行时抽象层。4 层 → 5 层。L2 解耦(68 处运行时硬耦合 → 抽象接口)。§5 从"OpenClaw 契约边界"改为"运行时契约边界"。ADR-012 accepted。** |
| 2026-08-24 | 2.1 | 补齐 L2 缺失能力: ① 会话生命周期管理(cron 每日清理 + deleteAfterRun + 分级策略,ADR-013); ② 错误自动处理(检测→分级→自愈闭环,ADR-014)。14 份 ADR accepted。10 个 L2 组件齐备。 |
| 2026-08-24 | 2.2 | 建设模型调度组件 model-scheduling: ① 模型注册表(从 openclaw.json 自动同步); ② 智能路由(任务分类 + 多级 fallback); ③ token 压缩(参考 9router RTK); ④ 用量追踪(每周从 provider API 获取); ⑤ 健康探测(每小时 ping)。11 个 L2 组件齐备。 |
| 2026-08-25 | 2.3 | model-scheduling 完善: ① 代理服务(proxy.py,自动启动+热更新); ② 自动启动(LaunchAgent,开机自启+崩溃重启); ③ 热更新(config_watcher.py,文件变更→≤10秒生效); ④ 端到端验证(闲聊→doubao-lite,编码→ark-code,推理→deepseek); ⑤ 回退方案(3份rollback文件)。 |
| 2026-08-26 | **2.4** | **agent 重建(SQLite 损坏) + cron 全清 + 心跳重建。L2 状态更新: 会话生命周期管理 + 错误自动处理 cron 已清除(设计保留,📋 待重建)。资产清单与运行时对齐。AGENTS.md 新增 L1 长任务隔离章节。** |
| 2026-08-31 | 2.7 | 新增 L2 Office 文档生成组件(011): python-docx/docxtpl/openpyxl/xlsxwriter/pandas/python-pptx 6库实测 + pptxgenjs-pro 技能协同,ADR-016 accepted。12 个 L2 组件齐备,10 个已上线。 |
| 2026-09-01 | 2.8 | 新增 L4 Bangcle PPT 模板系统(CPT-012,ADR-017): 深度解析官方模板设计规范(VI色/思源黑体/页面类型),创建 DESIGN.md + skills/bangcle-ppt 技能。首个 L4 组件。 |

---

## 相关文档

- 知识库索引: `../knowledge-base/README.md`
- 经验沉淀模型: `../knowledge-base/by-category/project-experience/README.md`
- ADR 模板: `../knowledge-base/templates/ADR.md`
- 经验卡片模板: `../knowledge-base/templates/EXPERIENCE-CARD.md`
- OpenClaw 文档: https://docs.openclaw.ai
