# 系统资产清单

> **本文件由脚本自动生成，请勿手工编辑。**
> 生成器：`scripts/gen_asset_inventory.py` · 触发：git pre-commit hook
> 手动重生成：`python3 scripts/gen_asset_inventory.py`

最后生成：2026-08-21 14:56 UTC+08:00

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

**总计** 76 个（启用 55） · bundled 74 · global 2

> 内置（bundled）插件随 OpenClaw 版本提供，多为按需激活的模型 provider。下表只列**主动安装**或**实际提供工具**的插件。

| ID | 来源 | 提供的工具 | 提供的能力 |
|---|---|---|---|
| `longcat` | global | — | model-provider: longcat |
| `tavily` | global | — | web-search: tavily |

**内置模型 provider**（31 个，按需激活）：`anthropic`, `byteplus`, `clawrouter`, `cohere`, `comfy`, `copilot-proxy`, `fal`, `github-copilot`, `google`, `huggingface`, `litellm`, `lmstudio`, `meta`, `microsoft-foundry`, `minimax`, `mistral`, `novita`, `nvidia`, `ollama`, `openai`, `opencode`, `opencode-go`, `openrouter`, `sglang`, `synthetic`, `together`, `vllm`, `volcengine`, `vydra`, `xai`, `xiaomi`

## L2 — 技能资产 (Skills)

**总计** 84 个（可用 72）

| 来源 | 数量 | 说明 |
|---|---|---|
| `openclaw-bundled` | 51 | OpenClaw 内置（随版本升级） |
| `openclaw-extra` | 3 | 插件附带技能 |
| `openclaw-managed` | 25 | 已安装的托管技能 |
| `openclaw-workspace` | 5 | **本 workspace 自建**（受版本控制） |

### 自建技能（workspace）

| 名称 | 描述 |
|---|---|
| `edit-tool-exact-whitespace-recovery` | Edit-tool "oldText not found" usually means a whitespace mismatch. On macOS, use `od -c... |
| `git-https-token-file-credential-helper` | Push to GitHub over HTTPS with a token file, no plaintext token in git config, plus fir... |
| `openclaw-add-tool-via-also-allow` | Add a blocked tool in OpenClaw without changing global profile: patch tools.alsoAllow, ... |
| `openclaw-debug-missing-tool` | Diagnose OpenClaw "documented tool not callable" via tools.profile and plugin capabilit... |
| `openclaw-generated-asset-inventory` | Generate a self-updating OpenClaw asset/inventory doc from CLI JSON sources with drift ... |

## L2 — Agent 资产

| ID | 身份 | 模型 | Workspace | 默认 |
|---|---|---|---|---|
| `main` | 🦞 Jerry | `longcat/LongCat-2.0` | `/Users/bangcle/.openclaw/workspace` | ✅ |

## L2 — 工具策略资产

| 配置项 | 值 |
|---|---|
| `tools.profile` | `coding` |
| `tools.alsoAllow` | `tavily_search`, `tavily_extract` |

> `alsoAllow` 是 profile 之上的显式例外，理由见 [EXP-20260821-001](../knowledge-base/by-category/project-experience/correct/EXP-20260821-001-tavily-tools-also-allow.md)。

## L2 — 凭据资产 (仅元信息，不含凭据值)

### SecretRef Providers

| 别名 | 说明 |
|---|---|
| `tavilykey` | 配置值由 OpenClaw redact，详见 `openclaw config get secrets.providers` |

### 凭据文件

| 文件 | 权限 | 大小 |
|---|---|---|
| `~/.openclaw/secrets/github.token` | `600` | 40 B |
| `~/.openclaw/secrets/tavily.apiKey` | `600` | 58 B |

> ⚠️ 标记表示权限不是 600，应执行 `chmod 600` 收紧。

## L2 — 调度资产 (Cron)

| 名称 | 启用 | 调度 | 目标 |
|---|---|---|---|
| Heartbeat (main) | ✅ | 每 1800s | `main` |
| Memory Dreaming Promotion | ✅ | cron `0 3 * * *` | `isolated` |

## 文档资产

| 类别 | 数量 |
|---|---|
| ADR（架构决策记录） | 4 |
| EXP（经验卡片） | 2 |
| 模板 | 4 |

### ADR 清单

| 文件 | 状态 |
|---|---|
| [`ADR-202608-001-four-layer-architecture`](../knowledge-base/by-category/project-experience/adr/ADR-202608-001-four-layer-architecture.md) | accepted |
| [`ADR-202608-002-knowledge-base-three-dimensions`](../knowledge-base/by-category/project-experience/adr/ADR-202608-002-knowledge-base-three-dimensions.md) | accepted |
| [`ADR-202608-003-knowledge-base-evolution-path`](../knowledge-base/by-category/project-experience/adr/ADR-202608-003-knowledge-base-evolution-path.md) | accepted |
| [`ADR-202608-004-observability-adapter`](../knowledge-base/by-category/project-experience/adr/ADR-202608-004-observability-adapter.md) | proposed |

### 经验卡片清单

| 文件 | 状态 |
|---|---|
| [`EXP-20260821-001-tavily-tools-also-allow`](../knowledge-base/by-category/project-experience/correct/EXP-20260821-001-tavily-tools-also-allow.md) | active |
| [`EXP-20260821-002-github-file-credential-helper`](../knowledge-base/by-category/project-experience/correct/EXP-20260821-002-github-file-credential-helper.md) | active |

## 仓库资产

| 项 | 值 |
|---|---|
| Remote | https://github.com/RenLimin/openclaw-v5.0.git |
| HEAD | `6dde979` |
| Commit 数 | 14 |

**不入版本控制**（见 `.gitignore`）：`MEMORY.md` · `memory/` · `skills/` · `business/*/logs/`

---

## L3 / L4 资产

_(未启动 — 详见 [架构文档 §6 演进路线](./00-system-architecture.md#6-演进路线))_

