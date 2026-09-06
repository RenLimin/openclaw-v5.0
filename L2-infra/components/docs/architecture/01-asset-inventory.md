# 系统资产清单

> **本文件由脚本自动生成，请勿手工编辑。**
> 生成器：`scripts/gen_asset_inventory.py` · 触发：git pre-commit hook
> 手动重生成：`python3 scripts/gen_asset_inventory.py`

最后生成：2026-09-06 14:38 UTC+08:00

本清单是 [系统架构文档](./00-system-architecture.md) 的附件，按 4 层架构组织（层级定义见 [ADR-202608-001](../knowledge-base/by-category/project-experience/adr/ADR-202608-001-four-layer-architecture.md)）。

**安全边界**：本清单只记录资产的**存在与元信息**，绝不包含凭据值、token、密钥内容。

---

## L1 — 系统层资产 (OpenClaw 基座)

| 资产 | 值 |
|---|---|
| OpenClaw | OpenClaw 2026.9.1 (ad6fe23) |
| Node.js | v26.7.0 |

> L1 不可修改，升级跟随官方版本。breaking changes 需走 ADR。

## L2 — 插件资产 (Plugins)

**总计** 64 个（启用 33） · bundled 59 · global 5

> 内置（bundled）插件随 OpenClaw 版本提供，多为按需激活的模型 provider。下表只列**主动安装**或**实际提供工具**的插件。

| ID | 来源 | 提供的工具 | 提供的能力 |
|---|---|---|---|
| `llama-cpp` | global | — | model-provider: llama-cpp |
| `memory-core` | bundled | `intent`, `memory_get`, `memory_search` | — |
| `ollama` | bundled | `node_inference` | web-search: ollama; model-provider: ollama, ollama-cloud |
| `openclaw-weixin` | global | — | channel: openclaw-weixin |
| `tavily` | global | `tavily_search`, `tavily_extract` | web-search: tavily |
| `wecom-openclaw-plugin` | global | `wecom_mcp` | channel: wecom |
| `xai` | bundled | `code_execution`, `x_search` | web-search: grok; model-provider: xai |

**内置模型 provider**（20 个，按需激活）：`anthropic`, `clawrouter`, `copilot-proxy`, `fal`, `github-copilot`, `google`, `huggingface`, `litellm`, `lmstudio`, `microsoft-foundry`, `minimax`, `nvidia`, `ollama`, `openai`, `opencode-go`, `openrouter`, `sglang`, `together`, `vllm`, `xai`

## L2 — 技能资产 (Skills)

**总计** 100 个（可用 89）

| 来源 | 数量 | 说明 |
|---|---|---|
| `openclaw-bundled` | 50 | OpenClaw 内置（随版本升级） |
| `openclaw-custodian` | 4 | — |
| `openclaw-extra` | 21 | 插件附带技能 |
| `openclaw-managed` | 25 | 已安装的托管技能 |

## L2 — Agent 资产

| ID | 身份 | 模型 | Workspace | 默认 |
|---|---|---|---|---|
| `main` | 🦞 main | `model-scheduling/auto` | `/Users/bangcle/.openclaw/workspace` | — |
| `ms-coding` | 🦞 ms-coding | `coding-plan/doubao-seed-code-preview-251028` | `/Users/bangcle/.openclaw/workspace` | — |
| `ms-research` | 🦞 ms-research | `coding-plan/doubao-seed-2-1-turbo` | `/Users/bangcle/.openclaw/workspace` | — |

## L2 — 工具策略资产

| 配置项 | 值 |
|---|---|
| `tools.profile` | `coding` |
| `tools.alsoAllow` | `tavily_search`, `tavily_extract`, `wecom_mcp`, `message`, `group:messaging` |

> `alsoAllow` 是 profile 之上的显式例外，理由见 [EXP-20260821-001](../knowledge-base/by-category/project-experience/correct/EXP-20260821-001-tavily-tools-also-allow.md)。

## L2 — 凭据资产 (仅元信息，不含凭据值)

> 凭据清单 (含轮换周期等元信息): `~/.openclaw/secrets/INDEX.md`

### SecretRef Providers

| 别名 | 说明 |
|---|---|
| `codingplan` | 配置值由 OpenClaw redact，详见 `openclaw config get secrets.providers` |
| `gatewayauthtoken` | 配置值由 OpenClaw redact，详见 `openclaw config get secrets.providers` |
| `longcatkey` | 配置值由 OpenClaw redact，详见 `openclaw config get secrets.providers` |
| `memorysearchkey` | 配置值由 OpenClaw redact，详见 `openclaw config get secrets.providers` |
| `tavilykey` | 配置值由 OpenClaw redact，详见 `openclaw config get secrets.providers` |

### 凭据文件

| 文件 | 权限 | 大小 |
|---|---|---|
| `~/.openclaw/secrets/INDEX.md` | `600` | 2425 B |
| `~/.openclaw/secrets/backup.key` | `600` | 65 B |
| `~/.openclaw/secrets/codingplan.apiKey` | `600` | 46 B |
| `~/.openclaw/secrets/gateway.auth.token` | `600` | 48 B |
| `~/.openclaw/secrets/github.token` | `600` | 40 B |
| `~/.openclaw/secrets/longcat.apiKey` | `600` | 32 B |
| `~/.openclaw/secrets/memory.search.remote.apiKey` | `600` | 9 B |
| `~/.openclaw/secrets/tavily.apiKey` | `600` | 58 B |

> ⚠️ 标记表示权限不是 600，应执行 `chmod 600` 收紧。

## L2 — 调度资产 (Cron)

| 名称 | 启用 | 调度 | 目标 |
|---|---|---|---|
| Heartbeat (main) | ✅ | 每 1800s | `main` |
| provider 健康探测 | ✅ | cron `0 */1 * * *` | `isolated` |
| 错误扫描 | ✅ | cron `0 */2 * * *` | `isolated` |
| 会话错误自动处理 | ✅ | cron `0 */2 * * *` | `isolated` |
| openclaw-backup-scheduled | ✅ | 每 86400s | `isolated` |
| 会话生命周期管理 | ✅ | cron `0 2 * * *` | `isolated` |
| Memory Dreaming Promotion | ✅ | cron `0 3 * * *` | `isolated` |

## 文档资产

| 类别 | 数量 |
|---|---|
| ADR（架构决策记录） | 0 |
| EXP（经验卡片） | 0 |
| 模板 | 0 |

## 仓库资产

| 项 | 值 |
|---|---|
| Remote | https://github.com/RenLimin/openclaw-v5.0.git |
| HEAD | `58bb8f0` |
| Commit 数 | 230 |

**不入版本控制**（见 `.gitignore`）：`MEMORY.md` · `memory/` · `skills/` · `business/*/logs/`

---

## L3 / L4 资产

_(未启动 — 详见 [架构文档 §6 演进路线](./00-system-architecture.md#6-演进路线))_

