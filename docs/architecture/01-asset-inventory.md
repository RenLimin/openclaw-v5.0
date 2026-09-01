# 系统资产清单

> **本文件由脚本自动生成，请勿手工编辑。**
> 生成器：`scripts/gen_asset_inventory.py` · 触发：git pre-commit hook
> 手动重生成：`python3 scripts/gen_asset_inventory.py`

最后生成：2026-09-01 10:24 UTC+08:00

本清单是 [系统架构文档](./00-system-architecture.md) 的附件，按 4 层架构组织（层级定义见 [ADR-202608-001](../knowledge-base/by-category/project-experience/adr/ADR-202608-001-four-layer-architecture.md)）。

**安全边界**：本清单只记录资产的**存在与元信息**，绝不包含凭据值、token、密钥内容。

---

## L1 — 系统层资产 (OpenClaw 基座)

| 资产 | 值 |
|---|---|
| OpenClaw | OpenClaw 2026.7.2-beta.7 (dabe191) |
| Node.js | v26.7.0 |

> L1 不可修改，升级跟随官方版本。breaking changes 需走 ADR。

## L2 — 插件资产 (Plugins)

**总计** 79 个（启用 6） · bundled 74 · global 5

> 内置（bundled）插件随 OpenClaw 版本提供，多为按需激活的模型 provider。下表只列**主动安装**或**实际提供工具**的插件。

| ID | 来源 | 提供的工具 | 提供的能力 |
|---|---|---|---|
| `llama-cpp` | global | — | — |
| `longcat` | global | — | model-provider: longcat |
| `openclaw-weixin` | global | — | channel: openclaw-weixin |
| `tavily` | global | — | web-search: tavily |
| `wecom-openclaw-plugin` | global | — | channel: wecom |

## L2 — 技能资产 (Skills)

**总计** 117 个（可用 105）

| 来源 | 数量 | 说明 |
|---|---|---|
| `openclaw-bundled` | 51 | OpenClaw 内置（随版本升级） |
| `openclaw-extra` | 16 | 插件附带技能 |
| `openclaw-managed` | 25 | 已安装的托管技能 |
| `openclaw-workspace` | 25 | **本 workspace 自建**（受版本控制） |

### 自建技能（workspace）

| 名称 | 描述 |
|---|---|
| `config-snapshot-redaction-and-drift-check` | Committing sanitized config snapshots to git: exact-key redaction, secret scan, and --c... |
| `config-snapshot-redaction-verification` | Sanitized config snapshot leaks a secret/ID before commit: fix key-list redaction and v... |
| `config-snapshot-tenant-identifier-leak-audit` | Auditing config snapshots for leaked tenant IDs (botId/corpId/appId) before committing ... |
| `edit-stale-state-break-loop` | Breaking edit-tool retry loops when prior mutations already changed the target text |
| `edit-tool-exact-whitespace-recovery` | Edit-tool "oldText not found" usually means a whitespace mismatch. On macOS, use `od -c... |
| `git-https-token-file-credential-helper` | Push to GitHub over HTTPS with a token file, no plaintext token in git config, plus fir... |
| `git-nothing-to-commit-untracked-file-triage` | Diagnose "nothing to commit" or a missing file from a commit: check ignore/tracking sta... |
| `macos-orphan-launchagent-cleanup` | 卸载并彻底清除指向已删除代码的 macOS LaunchAgent 孤儿服务与幽灵进程，含 lsof 误判规避 |
| `markdown-frontmatter-schema-audit-gate` | Validate and gate Markdown doc frontmatter (layers/stage/tags/IDs, cross-refs, relative... |
| `node-plugin-capability-check-from-dist-source` | Verify an installed npm/OpenClaw plugin's real capability (e.g. proactive send, require... |
| `openclaw-add-tool-via-also-allow` | Add a blocked tool in OpenClaw without changing global profile: patch tools.alsoAllow, ... |
| `openclaw-channel-proactive-delivery-triage` | Diagnose OpenClaw channel proactive/cron delivery failures (e.g. WeCom bot summary not ... |
| `openclaw-channel-regression-log-audit` | Regression-test an OpenClaw chat channel after gateway restart using gateway.log layer ... |
| `openclaw-config-drift-audit` | Audit an OpenClaw install for config/docs drift: channel-vs-plugin status conflicts, do... |
| `openclaw-config-patch-array-replace` | "openclaw config patch" array fields (e.g. models[]) replace entirely — never merge. Us... |
| `openclaw-config-readback-and-backup-chain-audit` | openclaw.json key missing after an earlier "applied" patch: read back config, audit .ba... |
| `openclaw-config-schema-and-plugin-doc-discovery` | Find real openclaw config paths, plugin channel docs, and CLI subcommands before editin... |
| `openclaw-context-overflow-compaction-recovery` | Fix OpenClaw sessions where /compact also fails after switching to a smaller-context mo... |
| `openclaw-cron-delivery-test-and-rollback` | Test or roll back OpenClaw cron/automation delivery (announce, failureAlert) after not-... |
| `openclaw-cron-delivery-triage` | Cron/automation job shows status=error but its output files are fine — diagnose deliver... |
| `openclaw-debug-missing-tool` | Diagnose OpenClaw "documented tool not callable" via tools.profile and plugin capabilit... |
| `openclaw-generated-asset-inventory` | Generate a self-updating OpenClaw asset/inventory doc from CLI JSON sources with drift ... |
| `openmaic` | OpenMAIC assistant for setting up, generating, and extending OpenMAIC. Use when the use... |
| `pptxgenjs-pro` | Generate professional PowerPoint slides with PptxGenJS. Use for creating slides with ca... |
| `probe-model-context-window-limit` | Measure a provider model's real input-token limit by binary-search probe before setting... |

## L2 — Agent 资产

| ID | 身份 | 模型 | Workspace | 默认 |
|---|---|---|---|---|
| `main` | 🦞 Jerry | `model-scheduling/auto` | `/Users/bangcle/.openclaw/workspace` | ✅ |
| `ms-coding` | 🦞 Jerry | `coding-plan/ark-code-latest` | `/Users/bangcle/.openclaw/workspace` | — |
| `ms-research` | 🦞 Jerry | `coding-plan/doubao-seed-2.1-turbo` | `/Users/bangcle/.openclaw/workspace` | — |
| `ms-reasoning` | 🦞 Jerry | `coding-plan/deepseek-v4-flash` | `/Users/bangcle/.openclaw/workspace` | — |
| `ms-chat` | 🦞 Jerry | `coding-plan/doubao-seed-2.0-lite` | `/Users/bangcle/.openclaw/workspace` | — |

## L2 — 工具策略资产

| 配置项 | 值 |
|---|---|
| `tools.profile` | `coding` |
| `tools.alsoAllow` | `tavily_search`, `tavily_extract` |

> `alsoAllow` 是 profile 之上的显式例外，理由见 [EXP-20260821-001](../knowledge-base/by-category/project-experience/correct/EXP-20260821-001-tavily-tools-also-allow.md)。

## L2 — 凭据资产 (仅元信息，不含凭据值)

> 凭据清单 (含轮换周期等元信息): `~/.openclaw/secrets/INDEX.md`

### SecretRef Providers

| 别名 | 说明 |
|---|---|
| `codingplankey` | 配置值由 OpenClaw redact，详见 `openclaw config get secrets.providers` |
| `gatewayauthtoken` | 配置值由 OpenClaw redact，详见 `openclaw config get secrets.providers` |
| `longcatkey` | 配置值由 OpenClaw redact，详见 `openclaw config get secrets.providers` |
| `tavilykey` | 配置值由 OpenClaw redact，详见 `openclaw config get secrets.providers` |

### 凭据文件

| 文件 | 权限 | 大小 |
|---|---|---|
| `~/.openclaw/secrets/INDEX.md` | `600` | 2425 B |
| `~/.openclaw/secrets/backup.key` | `600` | 65 B |
| `~/.openclaw/secrets/coding-plan.apiKey` | `600` | 46 B |
| `~/.openclaw/secrets/gateway.auth.token` | `600` | 48 B |
| `~/.openclaw/secrets/github.token` | `600` | 40 B |
| `~/.openclaw/secrets/longcat.apiKey` | `600` | 32 B |
| `~/.openclaw/secrets/tavily.apiKey` | `600` | 58 B |

> ⚠️ 标记表示权限不是 600，应执行 `chmod 600` 收紧。

## L2 — 调度资产 (Cron)

| 名称 | 启用 | 调度 | 目标 |
|---|---|---|---|
| Heartbeat (main) | ✅ | 每 1800s | `main` |
| Provider 健康探测 | ✅ | cron `0 */1 * * *` | `isolated` |
| 错误扫描 | ✅ | cron `0 */2 * * *` | `isolated` |
| Memory Dreaming Promotion | ✅ | cron `0 3 * * *` | `isolated` |

## 文档资产

| 类别 | 数量 |
|---|---|
| ADR（架构决策记录） | 16 |
| EXP（经验卡片） | 12 |
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

## 仓库资产

| 项 | 值 |
|---|---|
| Remote | https://github.com/RenLimin/openclaw-v5.0.git |
| HEAD | `301f243` |
| Commit 数 | 125 |

**不入版本控制**（见 `.gitignore`）：`MEMORY.md` · `memory/` · `skills/` · `business/*/logs/`

---

## L3 / L4 资产

_(未启动 — 详见 [架构文档 §6 演进路线](./00-system-architecture.md#6-演进路线))_

