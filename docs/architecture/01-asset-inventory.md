# 系统资产清单

> **本文件由脚本自动生成，请勿手工编辑。**
> 生成器：`scripts/gen_asset_inventory.py` · 触发：git pre-commit hook
> 手动重生成：`python3 scripts/gen_asset_inventory.py`

最后生成：2026-11-08 21:21 UTC+08:00

本清单是 [系统架构文档](./00-system-architecture.md) 的附件，按 4 层架构组织（层级定义见 [ADR-202608-001](../knowledge-base/by-category/project-experience/adr/ADR-202608-001-four-layer-architecture.md)）。

**安全边界**：本清单只记录资产的**存在与元信息**，绝不包含凭据值、token、密钥内容。

---

## L1 — 系统层资产 (OpenClaw 基座)

| 资产 | 值 |
|---|---|
| OpenClaw | OpenClaw 2026.9.8 (fc23bc8) |
| Node.js | v26.7.0 |

> L1 不可修改，升级跟随官方版本。breaking changes 需走 ADR。

## L2 — 插件资产 (Plugins)

**总计** 72 个（启用 8） · bundled 64 · config 1 · global 7

> 内置（bundled）插件随 OpenClaw 版本提供，多为按需激活的模型 provider。下表只列**主动安装**或**实际提供工具**的插件。

| ID | 来源 | 提供的工具 | 提供的能力 |
|---|---|---|---|
| `context-guardian` | global | — | — |
| `llama-cpp` | global | — | model-provider: llama-cpp |
| `longcat` | global | — | model-provider: longcat |
| `memory-core` | bundled | `intent`, `memory_get`, `memory_search` | — |
| `openclaw-weixin` | global | — | channel: openclaw-weixin |
| `session-boundary-guard` | config | — | — |
| `tavily` | global | `tavily_search`, `tavily_extract` | web-search: tavily |
| `wecom-openclaw-plugin` | global | `wecom-cli`, `wecom_mcp` | channel: wecom |

## L2 — 技能资产 (Skills)

**总计** 114 个（可用 103）

| 来源 | 数量 | 说明 |
|---|---|---|
| `openclaw-bundled` | 49 | OpenClaw 内置（随版本升级） |
| `openclaw-custodian` | 4 | — |
| `openclaw-extra` | 35 | 插件附带技能 |
| `openclaw-managed` | 26 | 已安装的托管技能 |

### 自建技能（按层分布）

| 层级 | 名称 | 描述 | 路径 |
|---|---|---|---|
| L4 专有业务 | `bangcle-ppt` | Bangcle PPT 模板系统，提供梆梆安全官方 VI 规范的 PPT 生成能力 | `L4-proprietary/skills/bangcle-ppt` |
| L4 专有业务 | `bangcle-project-manager-expert` | Bangcle 项目管理专家 — L4 层 Bangcle 项目管理相关的统一入口。识别项目管理意图并路由协调：交付实施台账、履约义务... | `L4-proprietary/skills/bangcle-project-manager-expert` |
| L4 专有业务 | `bdms-web-ui-design` |  | `L4-proprietary/skills/bdms-web-ui-design` |
| L4 专有业务 | `contract-manager-expert` | Bangcle 合同管理专家 — L4 层 Bangcle 合同管理相关的统一入口。合同智能审查（全文扫描/数字化/22 条风险规则）... | `L4-proprietary/skills/contract-manager-expert` |
| L4 专有业务 | `fin-l4` | 家庭及个人理财管理系统 FIN-L4：记账、预算、贷款、保险、投资、报表、导出。数据全本地 SQLite，Web UI + CLI +... | `L4-proprietary/skills/fin-l4` |
| L4 专有业务 | `ones-browser-export` | ONES 数据获取：浏览器自动化导出 CSV + GraphQL API 查询。支持签约项目统计/POC统计/异常处置等视图导出，以及... | `L4-proprietary/skills/ones-browser-export` |
| L4 专有业务 | `product-kb` | Bangcle 产品知识库 — 产品信息查询、合同标的匹配、文档知识检索；OA 产品中心文档自动增量同步（水位过滤/一键编排） | `L4-proprietary/skills/product-kb` |
| L4 专有业务 | `product-manager-expert` | Bangcle 产品管理专家 — L4 层 Bangcle 产品相关的统一入口。产品咨询解答、跨产品组合方案、产品知识库检准与维护、O... | `L4-proprietary/skills/product-manager-expert` |
| L3 通用业务 | `bangcle-customer-profile` | Bangcle 客户画像分析：业务目标是制定客户画像，基于项目工作项/评论/附件与知识库，输出客户画像，重点为客户环境（云/OS/CP... | `L3-business/skills/bangcle-customer-profile` |
| L3 通用业务 | `bangcle-obligation-summary` | Bangcle 项目履约义务汇总：业务目标是为指定的项目经理服务，参考历史项目的交付情况，按最终用户/客户检索全部项目履约义务工作项，... | `L3-business/skills/bangcle-obligation-summary` |
| L3 通用业务 | `bangcle-project-report` | Bangcle 项目汇报材料生成：输入「客户 + 周期 + 受众」，从 ONES/合同台账取数，经完整取数→口径清洗→多维汇总→目标闭... | `L3-business/skills/bangcle-project-report` |
| L3 通用业务 | `bangcle-project-retrospective` | Bangcle 项目复盘建议：业务目标是对项目或项目集（Program）做复盘，输出产品差异/优化空间与项目管理复盘（含责任方建议），... | `L3-business/skills/bangcle-project-retrospective` |
| L3 通用业务 | `bangcle-project-summary` | Bangcle 项目信息汇总：业务目标是汇总项目交付实施情况，从 ONES 等系统汇总客户名下全部项目/产品/工作项/交付物/责任人，... | `L3-business/skills/bangcle-project-summary` |
| L3 通用业务 | `contract-approval` | 销售合同审批工作流：起草、分级审批、风险扫描、合同生成、归档。基于《民法典》合同编 + CLM 7 阶段方法论。L3 纯逻辑核心，L4... | `L3-business/skills/contract-approval` |
| L2 基础设施 | `dag-orchestrator` | DAG 工作流编排器。将复杂任务分解为有向无环图（DAG），支持并行执行和变量传递。 | `L2-infra/skills/dag-orchestrator` |
| L2 基础设施 | `meeting-minutes` | 把会议录音转写/速记提炼为结构化、可溯源、术语统一的正式纪要，支持会后材料合并与多格式交付。触发：整理会议纪要、会议记录、校订智能纪要... | `L2-infra/skills/meeting-minutes` |
| L2 基础设施 | `ocr-digitalization` | L2 OCR 文档数字化组件 — 扫描件/图片 → 高精度文本 + 签名/印章自动检测 | `L2-infra/skills/ocr-digitalization` |
| L2 基础设施 | `ontology-identity-gate` | 为 Agent 运营本体（Proposal Gate）提供 run-scoped 身份令牌（HMAC-SHA256，零第三方依赖）+ ... | `L2-infra/skills/ontology-identity-gate` |
| L2 基础设施 | `pdf-toolkit` | Page-level PDF operations: merge multiple PDFs into one, split into... | `L2-infra/skills/pdf-toolkit` |
| L2 基础设施 | `role-library` | 标准化 Agent 角色库。支持按角色执行任务，覆盖数据分析、报告生成、系统运维、文档管理等场景。 | `L2-infra/skills/role-library` |
| L2 基础设施 | `system-health-check` |  | `L2-infra/skills/system-health-check` |
| L2 基础设施 | `web-ui-design` |  | `L2-infra/skills/web-ui-design` |

_自建技能总计: 22 个（L2: 8, L3: 6, L4: 8, 根目录: 0）_

## L2 — Agent 资产

| ID | 身份 | 模型 | Workspace | 默认 |
|---|---|---|---|---|
| `main` | 🦞 main | `model-scheduling/auto` | `/Users/bangcle/.openclaw/workspace` | ✅ |

## L2 — 工具策略资产

| 配置项 | 值 |
|---|---|
| `tools.profile` | `full` |
| `tools.alsoAllow` | `tavily_search`, `tavily_extract`, `message`, `group:messaging`, `wecom-cli`, `wecom-openclaw-plugin`, `imap` |

> `alsoAllow` 是 profile 之上的显式例外，理由见 [EXP-20260821-001](../knowledge-base/by-category/project-experience/correct/EXP-20260821-001-tavily-tools-also-allow.md)。

## L2 — 凭据资产 (仅元信息，不含凭据值)

> 凭据清单 (含轮换周期等元信息): `~/.openclaw/secrets/INDEX.md`

### SQLite Secret Store（主存储）

| 名称 | 类型 | 作用域 |
|---|---|---|
| `CODING_PLAN_API_KEY` | secret | team |
| `DEEPSEEK_API_KEY` | secret | team |
| `IAM_BASIC` | env | team |
| `IAM_EMAIL_API` | secret | team |
| `LONGCAT_API_KEY` | secret | team |
| `OA_BASIC` | env | team |
| `ONES_BASIC` | env | team |
| `TAVILY_API_KEY` | secret | team |

### 文件式 SecretRef Providers（辅助）

| 别名 | source | path |
|---|---|---|
| `gatewayauthtoken` | `__OPENCLAW_REDACTED__` | `__OPENCLAW_REDACTED__` |
| `llamacpp` | `__OPENCLAW_REDACTED__` | `__OPENCLAW_REDACTED__` |
| `memorysearchkey` | `__OPENCLAW_REDACTED__` | `__OPENCLAW_REDACTED__` |

### 凭据文件

| 文件 | 权限 | 大小 |
|---|---|---|
| `~/.openclaw/secrets/INDEX.md` | `600` | 3003 B |
| `~/.openclaw/secrets/backup.key` | `600` | 65 B |
| `~/.openclaw/secrets/gateway.auth.token` | `600` | 48 B |
| `~/.openclaw/secrets/iam.basic` | `600` | 18 B |
| `~/.openclaw/secrets/iam.email_password` | `600` | 16 B |
| `~/.openclaw/secrets/iam.email_username` | `600` | 21 B |
| `~/.openclaw/secrets/iam.password` | `600` | 8 B |
| `~/.openclaw/secrets/iam.username` | `600` | 9 B |
| `~/.openclaw/secrets/llama.cpp.apiKey` | `600` | 49 B |
| `~/.openclaw/secrets/memory.search.remote.apiKey` | `600` | 9 B |
| `~/.openclaw/secrets/oa.basic` | `600` | 19 B |
| `~/.openclaw/secrets/ones.basic` | `600` | 31 B |

> ⚠️ 标记表示权限不是 600，应执行 `chmod 600` 收紧。

## L2 — 调度资产 (Cron)

| 名称 | 启用 | 调度 | 目标 | 投递 |
|---|---|---|---|---|
| 系统错误扫描（含上下文溢出自动恢复） | ✅ | 每 900s | `isolated` | wecom/1313 |
| session-auto-retry | ✅ | 每 1800s | `isolated` | wecom/1313 |
| quota-restore-check | ✅ | 每 7200s | `isolated` | wecom/1313 |
| Memory Dreaming Promotion | ✅ | cron `0 3 * * *` | `isolated` | — |
| workspace-temp-cleanup (INFRA-CLN-001) | ✅ | cron `30 3 * * *` | `isolated` | wecom/1313 |
| daily-inspection-detail | ✅ | cron `0 9 * * *` | `isolated` | wecom/1313 |
| oa-reconcile-daily (P4.4) | ✅ | cron `30 9 * * *` | `isolated` | last |

## L2 — 重启安全与压缩守护

| 资产 | 路径 | 职责 |
|---|---|---|
| compaction-guard hook | `hooks/compaction-guard/` | 订阅 session:compact:before/after，将 in-flight 压缩写入状态文件 |
| pre-restart guard | `L2-infra/components/gateway-safety/scripts/pre_restart_guard.py` | 有新鲜 in-flight 压缩则 rc=1 硬阻断；标记超 6 分钟视为 stale |
| safe restart wrapper | `L2-infra/components/gateway-safety/scripts/safe_restart.sh` | 先跑 guard，通过后才执行 openclaw gateway restart |

> config-patch 触发的进程内自动重启无外部否决点，仅能事前 guard + 优先热加载。

## L2 — 会话边界护栏（ADR-202611-036）

| 资产 | 路径 | 职责 |
|---|---|---|
| ADR-202611-036 决策 | `docs/knowledge-base/by-category/project-experience/adr/ADR-202611-036-session-boundary-guard.md` | 机制性拦截 agent 向 pinned/live 会话注入消息/任务（FB-20261103-03）；sessionKey 前缀判据，不依赖实时状态查询 |
| 护栏插件 | `L2-infra/components/session-boundary-guard/` | before_tool_call 插件：匹配 sessions_send/sessions_spawn(visible)，目标 agent:main:dashboard:* → requireApproval/block（fail-closed 15s）；纯逻辑 core.js 零依赖可单测 |
| 审计日志 | `~/.openclaw/state/session-boundary-guard.jsonl` | 每次拦截记录来源/目标/工具/决策（ts/sourceSessionKey/toolName/targetSessionKey/decision/mode），反哺 delivery-quality |

> 放行路径：sessions_spawn 普通 subagent（旁路排查唯一合法路径）、resume 自己 child、cron/wecom 会话投递、conversations_send 外部渠道。状态：✅ 已上线（2026-11-03）。

## L2 — Prompt 治理（ADR-035 纵切层）

| 资产 | 路径 | 职责 |
|---|---|---|
| ADR-035 决策 | `docs/knowledge-base/by-category/project-experience/adr/ADR-202610-035-prompt-rule-system.md` | Prompt 规则为贯穿 L0~L4 的正交纵切层；P0-P3 四级 + 规则即代码/指令边界 |
| P1 通用应答契约 | `L2-infra/prompts/answer-spec-base.md` | 证据分级强制时间戳、数据时效/降级、claim-引文绑定、溯源链、交付自检（v1.2） |
| P1 输出格式契约 | `L2-infra/prompts/format-spec-base.md` | 报告型统一信封 F1-F5(H1/元信息/数据基准/§0溯源/质量信号)+report/receipt判定(v1.0) |
| P2 项目域契约 | `L3-business/prompts/project-answer-spec.md` | 项目/进度/风险维度合格判据（v1.2，跨域机制直接适用 P1） |
| P2 合同域契约 | `L3-business/prompts/contract-answer-spec.md` | 合同主体/金额/节点/风险维度合格判据（v1.2） |
| P2 产品域契约 | `L4-proprietary/prompts/product-answer-spec.md` | 产品/需求/文档出处维度合格判据（v1.2） |
| 应答契约校验器 | `L2-infra/prompts/tools/check_answer_contract.py` | 确定性 fail-closed：内容(时间戳/溯源/降级)+格式(信封F1-F5)双层校验，被12 SKILL闸门调用 |
| 黄金基准测试 | `L2-infra/prompts/tests/run_tests.sh` | 2 合规必 PASS / 2 违规必 BLOCK + guard 单测；pre-commit 自动运行防门禁退化 |
| 运行时交付守卫 | `hooks/answer-contract-guard/` | message:sent 审计携带证据标记的交付，写 answer-contract-audit.log；只观察不拦截 |
| 交付质量反馈库 | `L2-infra/components/delivery-quality/feedback.jsonl` | 默认记录 Rex 交付纠正（record.py），git-tracked JSONL；6 维度/域/严重度结构化 |
| 反馈即时 review | `L2-infra/components/delivery-quality/review.py` | 反馈确认后即时触发(事件驱动,无cron)：聚类+复发根因(≥2)+高危单次，只读报告反哺 P2/fixture/KB |

> 12 个 SKILL 引用校验器：9 个分析类强制闸门 + 3 个作用域受限（system-health-check / fin-l4 / role-library，仅约束报告结论、豁免操作回执）。规则即代码（CHECK_RULES）保留在代码层；纯工具型 skill（PDF/OCR/DAG/UI/数据源/PPT 渲染）不挂硬门以防误拦。

## 文档资产

| 类别 | 数量 |
|---|---|
| ADR（架构决策记录） | 32 |
| EXP（经验卡片） | 32 |
| 模板 | 4 |

### ADR 清单

| 文件 | 状态 |
|---|---|
| [`ADR-202608-001-four-layer-architecture`](../knowledge-base/by-category/project-experience/adr/ADR-202608-001-four-layer-architecture.md) | accepted |
| [`ADR-202608-002-knowledge-base-three-dimensions`](../knowledge-base/by-category/project-experience/adr/ADR-202608-002-knowledge-base-three-dimensions.md) | accepted |
| [`ADR-202608-003-knowledge-base-evolution-path`](../knowledge-base/by-category/project-experience/adr/ADR-202608-003-knowledge-base-evolution-path.md) | accepted |
| [`ADR-202608-004-observability-adapter`](../knowledge-base/by-category/project-experience/adr/ADR-202608-004-observability-adapter.md) | accepted |
| [`ADR-202608-005-credential-management`](../knowledge-base/by-category/project-experience/adr/ADR-202608-005-credential-management.md) | accepted |
| [`ADR-202608-006-persistence-adapter`](../knowledge-base/by-category/project-experience/adr/ADR-202608-006-persistence-adapter.md) | accepted |
| [`ADR-202608-007-config-management`](../knowledge-base/by-category/project-experience/adr/ADR-202608-007-config-management.md) | accepted |
| [`ADR-202608-008-tool-policy-governance`](../knowledge-base/by-category/project-experience/adr/ADR-202608-008-tool-policy-governance.md) | accepted |
| [`ADR-202608-009-memory-embedding-provider`](../knowledge-base/by-category/project-experience/adr/ADR-202608-009-memory-embedding-provider.md) | accepted |
| [`ADR-202608-010-knowledge-base-tooling`](../knowledge-base/by-category/project-experience/adr/ADR-202608-010-knowledge-base-tooling.md) | accepted |
| [`ADR-202608-011-unified-error-contract`](../knowledge-base/by-category/project-experience/adr/ADR-202608-011-unified-error-contract.md) | accepted |
| [`ADR-202608-012-agent-runtime-as-variable`](../knowledge-base/by-category/project-experience/adr/ADR-202608-012-agent-runtime-as-variable.md) | accepted |
| [`ADR-202608-013-session-lifecycle-management`](../knowledge-base/by-category/project-experience/adr/ADR-202608-013-session-lifecycle-management.md) | accepted |
| [`ADR-202608-014-error-auto-handling`](../knowledge-base/by-category/project-experience/adr/ADR-202608-014-error-auto-handling.md) | accepted |
| [`ADR-202608-015-dynamic-compaction-model-routing`](../knowledge-base/by-category/project-experience/adr/ADR-202608-015-dynamic-compaction-model-routing.md) | accepted |
| [`ADR-202608-016-office-document-generation`](../knowledge-base/by-category/project-experience/adr/ADR-202608-016-office-document-generation.md) | accepted |
| [`ADR-202608-017-bangcle-ppt-template`](../knowledge-base/by-category/project-experience/adr/ADR-202608-017-bangcle-ppt-template.md) | accepted |
| [`ADR-202608-018-context-management`](../knowledge-base/by-category/project-experience/adr/ADR-202608-018-context-management.md) | accepted |
| [`ADR-202608-019-sandbox-isolation`](../knowledge-base/by-category/project-experience/adr/ADR-202608-019-sandbox-isolation.md) | accepted |
| [`ADR-202608-020-model-scheduling`](../knowledge-base/by-category/project-experience/adr/ADR-202608-020-model-scheduling.md) | accepted |
| [`ADR-202608-021-system-backup`](../knowledge-base/by-category/project-experience/adr/ADR-202608-021-system-backup.md) | accepted |
| [`ADR-202608-022-bdms-delivery-center`](../knowledge-base/by-category/project-experience/adr/ADR-202608-022-bdms-delivery-center.md) | accepted |
| [`ADR-202609-018-sales-contract-approval`](../knowledge-base/by-category/project-experience/adr/ADR-202609-018-sales-contract-approval.md) | accepted |
| [`ADR-202609-023-ocr-digitalization`](../knowledge-base/by-category/project-experience/adr/ADR-202609-023-ocr-digitalization.md) | accepted |
| [`ADR-202609-024-session-isolation-sharing`](../knowledge-base/by-category/project-experience/adr/ADR-202609-024-session-isolation-sharing.md) | proposed |
| [`ADR-202609-025-delivery-management-framework`](../knowledge-base/by-category/project-experience/adr/ADR-202609-025-delivery-management-framework.md) | accepted |
| [`ADR-202609-026-personal-finance-framework-L3`](../knowledge-base/by-category/project-experience/adr/ADR-202609-026-personal-finance-framework-L3.md) | accepted |
| [`ADR-202609-027-fin-l4-system-design`](../knowledge-base/by-category/project-experience/adr/ADR-202609-027-fin-l4-system-design.md) | accepted |
| [`ADR-202609-028-l0-installation-layer`](../knowledge-base/by-category/project-experience/adr/ADR-202609-028-l0-installation-layer.md) | proposed |
| [`ADR-202609-029-l3-office-business-dimension`](../knowledge-base/by-category/project-experience/adr/ADR-202609-029-l3-office-business-dimension.md) | proposed |
| [`ADR-202610-035-prompt-rule-system`](../knowledge-base/by-category/project-experience/adr/ADR-202610-035-prompt-rule-system.md) | accepted |
| [`ADR-202611-036-session-boundary-guard`](../knowledge-base/by-category/project-experience/adr/ADR-202611-036-session-boundary-guard.md) | proposed |

### 经验卡片清单

| 文件 | 状态 |
|---|---|
| [`EXP-20260821-001-tavily-tools-also-allow`](../knowledge-base/by-category/project-experience/correct/EXP-20260821-001-tavily-tools-also-allow.md) | active |
| [`EXP-20260821-002-github-file-credential-helper`](../knowledge-base/by-category/project-experience/correct/EXP-20260821-002-github-file-credential-helper.md) | active |
| [`EXP-20260821-003-compaction-model-delegation`](../knowledge-base/by-category/project-experience/correct/EXP-20260821-003-compaction-model-delegation.md) | superseded |
| [`EXP-20260822-004-context-window-empirical-probe`](../knowledge-base/by-category/project-experience/correct/EXP-20260822-004-context-window-empirical-probe.md) | active |
| [`EXP-20260822-005-cron-delivery-pollutes-status`](../knowledge-base/by-category/project-experience/correct/EXP-20260822-005-cron-delivery-pollutes-status.md) | active |
| [`EXP-20260822-006-wecom-aibot-cannot-push-proactively`](../knowledge-base/by-category/project-experience/correct/EXP-20260822-006-wecom-aibot-cannot-push-proactively.md) | active |
| [`EXP-20260823-007-plugin-declares-compat-but-imports-missing-sdk-subpath`](../knowledge-base/by-category/project-experience/correct/EXP-20260823-007-plugin-declares-compat-but-imports-missing-sdk-subpath.md) | active |
| [`EXP-20260823-008-kb-phase3-evaluation`](../knowledge-base/by-category/project-experience/correct/EXP-20260823-008-kb-phase3-evaluation.md) | active |
| [`EXP-20260823-009-review-selective-citation-and-drift-taxonomy`](../knowledge-base/by-category/project-experience/correct/EXP-20260823-009-review-selective-citation-and-drift-taxonomy.md) | active |
| [`EXP-20260823-010-heuristics-instead-of-evidence`](../knowledge-base/by-category/project-experience/correct/EXP-20260823-010-heuristics-instead-of-evidence.md) | active |
| [`EXP-20260824-011-catalog-is-not-entitlement`](../knowledge-base/by-category/project-experience/correct/EXP-20260824-011-catalog-is-not-entitlement.md) | active |
| [`EXP-20260824-012-kb-phase3-readiness`](../knowledge-base/by-category/project-experience/correct/EXP-20260824-012-kb-phase3-readiness.md) | active |
| [`EXP-20260901-018-ppt-capability-deep-research`](../knowledge-base/by-category/project-experience/correct/EXP-20260901-018-ppt-capability-deep-research.md) | active |
| [`EXP-20260902-001-contract-approval-skill`](../knowledge-base/by-category/project-experience/correct/EXP-20260902-001-contract-approval-skill.md) | — |
| [`EXP-20260903-001-ocr-coordinate-system`](../knowledge-base/by-category/project-experience/correct/EXP-20260903-001-ocr-coordinate-system.md) | active |
| [`EXP-20260903-002-audit-scope-filter`](../knowledge-base/by-category/project-experience/correct/EXP-20260903-002-audit-scope-filter.md) | active |
| [`EXP-20260903-006-dms-framework-phase1`](../knowledge-base/by-category/project-experience/correct/EXP-20260903-006-dms-framework-phase1.md) | — |
| [`EXP-20260903-007-dms-framework-phase2`](../knowledge-base/by-category/project-experience/correct/EXP-20260903-007-dms-framework-phase2.md) | — |
| [`EXP-20260903-008-dms-framework-phase3`](../knowledge-base/by-category/project-experience/correct/EXP-20260903-008-dms-framework-phase3.md) | — |
| [`EXP-20260903-009-dms-framework-phase4`](../knowledge-base/by-category/project-experience/correct/EXP-20260903-009-dms-framework-phase4.md) | — |
| [`EXP-20260903-010-dms-framework-l3-complete`](../knowledge-base/by-category/project-experience/correct/EXP-20260903-010-dms-framework-l3-complete.md) | — |
| [`EXP-20260915-013-double-entry-bookkeeping-for-family`](../knowledge-base/by-category/project-experience/correct/EXP-20260915-013-double-entry-bookkeeping-for-family.md) | active |
| [`EXP-20260915-014-decimal-precision-finance`](../knowledge-base/by-category/project-experience/correct/EXP-20260915-014-decimal-precision-finance.md) | active |
| [`EXP-20260915-015-bank-statement-import-4-formats`](../knowledge-base/by-category/project-experience/correct/EXP-20260915-015-bank-statement-import-4-formats.md) | active |
| [`EXP-20260915-016-web-ui-component-library`](../knowledge-base/by-category/project-experience/correct/EXP-20260915-016-web-ui-component-library.md) | active |
| [`EXP-20260915-020-dms-module-registry-capability`](../knowledge-base/by-category/project-experience/correct/EXP-20260915-020-dms-module-registry-capability.md) | — |
| [`EXP-20260915-021-dms-state-machine-capability`](../knowledge-base/by-category/project-experience/correct/EXP-20260915-021-dms-state-machine-capability.md) | — |
| [`EXP-20260915-022-dms-raci-capability`](../knowledge-base/by-category/project-experience/correct/EXP-20260915-022-dms-raci-capability.md) | — |
| [`EXP-20260915-023-dms-event-bus-capability`](../knowledge-base/by-category/project-experience/correct/EXP-20260915-023-dms-event-bus-capability.md) | — |
| [`EXP-20260915-024-dms-cli-usage-guide`](../knowledge-base/by-category/project-experience/correct/EXP-20260915-024-dms-cli-usage-guide.md) | — |
| [`EXP-20260915-025-dms-best-practices`](../knowledge-base/by-category/project-experience/correct/EXP-20260915-025-dms-best-practices.md) | — |
| [`EXP-20261003-001-48h-ops-retrospective`](../knowledge-base/by-category/project-experience/correct/EXP-20261003-001-48h-ops-retrospective.md) | active |

## 仓库资产

| 项 | 值 |
|---|---|
| Remote | https://github.com/RenLimin/openclaw-v5.0.git |
| HEAD | `42b5d6c` |
| Commit 数 | 627 |

**不入版本控制**（见 `.gitignore`）：`MEMORY.md` · `memory/` · `skills/` · `business/*/logs/`

---

## L2 / L3 / L4 组件资产

### L2 基础设施

| 组件 | Python 模块 | 文档 | 测试 | 路径 |
|---|---|---|---|---|
| `.deprecated` | 0 | 0 | 0 | `L2-infra/components/.deprecated` |
| `ai-knowledge-base` | 93 | 29 | 13 | `L2-infra/components/ai-knowledge-base` |
| `backup` | 0 | 0 | 0 | `L2-infra/components/backup` |
| `browser-automation` | 0 | 0 | 0 | `L2-infra/components/browser-automation` |
| `config` | 6 | 0 | 2 | `L2-infra/components/config` |
| `context-management` | 5 | 0 | 1 | `L2-infra/components/context-management` |
| `credentials` | 3 | 0 | 1 | `L2-infra/components/credentials` |
| `delivery-quality` | 2 | 0 | 0 | `L2-infra/components/delivery-quality` |
| `gateway-safety` | 4 | 0 | 1 | `L2-infra/components/gateway-safety` |
| `knowledge-base` | 19 | 0 | 6 | `L2-infra/components/knowledge-base` |
| `logs` | 3 | 0 | 0 | `L2-infra/components/logs` |
| `maintenance` | 3 | 0 | 1 | `L2-infra/components/maintenance` |
| `memory-embedding` | 3 | 0 | 1 | `L2-infra/components/memory-embedding` |
| `model-scheduling` | 16 | 0 | 2 | `L2-infra/components/model-scheduling` |
| `observability` | 9 | 0 | 1 | `L2-infra/components/observability` |
| `ocr-digitalization` | 24 | 0 | 7 | `L2-infra/components/ocr-digitalization` |
| `office-generation` | 16 | 0 | 6 | `L2-infra/components/office-generation` |
| `persistence` | 8 | 0 | 1 | `L2-infra/components/persistence` |
| `role-library` | 0 | 0 | 0 | `L2-infra/components/role-library` |
| `sandbox` | 9 | 0 | 1 | `L2-infra/components/sandbox` |
| `scheduler-guard` | 1 | 0 | 0 | `L2-infra/components/scheduler-guard` |
| `session-boundary-guard` | 0 | 0 | 0 | `L2-infra/components/session-boundary-guard` |
| `session-isolation` | 17 | 0 | 6 | `L2-infra/components/session-isolation` |
| `session-recovery` | 12 | 0 | 5 | `L2-infra/components/session-recovery` |
| `tool-policy` | 0 | 0 | 0 | `L2-infra/components/tool-policy` |
| `web-common` | 13 | 4 | 2 | `L2-infra/components/web-common` |
| `workspace-temp-cleanup` | 2 | 0 | 1 | `L2-infra/components/workspace-temp-cleanup` |

### L3 通用业务

| 组件 | Python 模块 | 文档 | 测试 | 路径 |
|---|---|---|---|---|
| `cissp-learning` | 0 | 0 | 0 | `L3-business/components/cissp-learning` |
| `contract-approval` | 0 | 0 | 0 | `L3-business/components/contract-approval` |
| `contract-management` | 27 | 6 | 10 | `L3-business/components/contract-management` |
| `delivery-management-framework` | 40 | 0 | 10 | `L3-business/components/delivery-management-framework` |
| `dms-framework` | 50 | 0 | 17 | `L3-business/components/dms-framework` |
| `finance-engine` | 51 | 0 | 12 | `L3-business/components/finance-engine` |
| `health-engine` | 0 | 0 | 0 | `L3-business/components/health-engine` |
| `health-management` | 30 | 0 | 7 | `L3-business/components/health-management` |
| `office-business` | 0 | 0 | 0 | `L3-business/components/office-business` |

### L4 专有业务

| 组件 | Python 模块 | 文档 | 测试 | 路径 |
|---|---|---|---|---|
| `.deprecated` | 24 | 0 | 0 | `L4-proprietary/components/.deprecated` |
| `bangcle-contract` | 82 | 12 | 3 | `L4-proprietary/components/bangcle-contract` |
| `bangcle-ppt` | 33 | 0 | 6 | `L4-proprietary/components/bangcle-ppt` |
| `bdms` | 198 | 9 | 24 | `L4-proprietary/components/bdms` |
| `cissp-trainer` | 25 | 0 | 9 | `L4-proprietary/components/cissp-trainer` |
| `delivery-center` | 82 | 0 | 16 | `L4-proprietary/components/delivery-center` |
| `fin-l4` | 58 | 0 | 14 | `L4-proprietary/components/fin-l4` |
| `office-contract` | 15 | 0 | 3 | `L4-proprietary/components/office-contract` |
| `product-kb` | 15 | 14 | 3 | `L4-proprietary/components/product-kb` |
| `revenue-recognition` | 21 | 0 | 0 | `L4-proprietary/components/revenue-recognition` |

---

## L3 / L4 资产

### L4 专有业务组件

| 名称 | 描述 | 路径 | 状态 |
|---|---|---|---|
| `bdms` | BDMS 交付管理系统：交付月报（导入/校验/问题审核/审批工作流）、确认收入、对比分析、基础数据、统计看板、系统设定。FastAPI + SQLite + Jinja，复用 web-common | `L4-proprietary/components/bdms` | 活跃；v2.1 全量交付，2026-11 按定稿原型重建前端（后端 API 零改动） |
| `bangcle-ppt` | Bangcle PPT 模板系统，提供梆梆安全官方 VI 规范的 PPT 生成能力 | `L4-proprietary/skills/bangcle-ppt` | 已交付 |

#### BDMS 内部结构

| 部分 | 内容 |
|---|---|
| Web 层 | `src/bdms/web/`：`main.py`（入口/侧栏配置）·`api.py`·`api_v2.py`（REST，后端 API 已覆盖全部工作流）·`templates/`（index/report/revenue/revenue_compare/master_data/dashboard/settings/base 等）·`static/`（css/js/img） |
| 业务模块 | `src/bdms/modules/`：`delivery_report`（交付月报）·`revenue`（确收）·`dashboard`（看板）·`master_data`（基础数据）·`contract_management`·`profit_management`·`project_management`·`integration`·`settings` |
| 基础设施 | `src/bdms/core/`·`cli/`·`security.py`（访问控制） |
| 原型 | `prototype/bdms-ui-prototype.html`（UI/视觉定稿基准，真实页面对照重建） |
| 设计文档 | `PRD/设计大纲/8 份详细设计/实施计划/操作手册/验证` v2.1；重建方案 `DESIGN-OUTLINE-BDMS-REBUILD-v1.0.md` |
| 回滚 | `backups/pre-rebuild-20261101/`（重建前完整前端快照）；`data/backups/`（DB 周期备份） |

> 演进路线见 [架构文档 §6 演进路线](./00-system-architecture.md#6-演进路线)。

