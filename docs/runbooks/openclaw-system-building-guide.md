# OpenClaw 系统建设手册

> 综合开放平台系统建设的**单一操作手册**。本文档覆盖从初始化到运维的完整建设路径。
>
> **配套文件**：
> - `docs/architecture/00-system-architecture.md` — 系统架构（单一事实来源）
> - `docs/knowledge-base/` — 知识库（ADR + EXP）
> - `docs/architecture/components/*/DESIGN.md` — 组件设计文档（7 份）
> - `docs/conventions/commit-and-config.md` — Commit 与配置变更约定
>
> **维护原则**：
> - 系统建设步骤变了 → 改本文档
> - 官方文档有 breaking changes → 同步更新引用链接
> - 单文件、单一来源、人机共读
> - 2026-08-23 创建

## 0. 元信息

| 字段 | 值 |
|---|---|
| 文档版本 | 1.0 (2026-08-23) |
| 文档状态 | active |
| 配套架构文档版本 | 0.8 |
| OpenClaw 版本 | 2026.7.2-beta.7 (dabe191) |
| Node.js | v26.7.0 |
| 平台 | macOS 26.5.2 (arm64) |

---

## 1. 建设路径总览

系统建设分**四个阶段**，每阶段有明确的入口条件与完成标志：

| 阶段 | 名称 | 状态 | 入口条件 | 完成标志 |
|---|---|---|---|---|
| 一 | 基座搭建 | ✅ 已完成 | — | L2 最小可用 + 7 组件建成 |
| 二 | 业务能力沉淀 | ⏳ 待 Rex 定夺 | 阶段一 ADR 全部完成 | L3 维度建设启动 |
| 三 | 自建知识库系统 | ⏳ 暂缓 | 触发条件 ≥2/7 | DB + Web 渲染上线 |
| 四 | 企业级治理 | ⏳ 预留 | 业务/团队规模驱动 | 横切关注点全面落地 |

> **当前阶段**：阶段一已完成，阶段二入口条件已满足（待 Rex 拍板）。

---

## 2. 阶段一：基座搭建

### 2.1 安装 OpenClaw

**官方文档**：`/start/getting-started.md` · `/install/`

```bash
# macOS / Linux
curl -fsSL https://openclaw.ai/install.sh | bash

# 验证
openclaw --version
node --version  # 需 v22.22.3+ / v24.15+ / v25.9+ (推荐 v26)
```

**前置条件**：
- Node.js v22.22.3+（推荐 v26）
- 一个模型 provider 的 API key

### 2.2 初始化工作区

**官方文档**：`/concepts/agent-workspace.md` · `/start/onboarding.md`

```bash
# 交互式引导（推荐首次使用）
openclaw onboard

# 或手动创建
mkdir -p ~/.openclaw/workspace
```

**工作区标准文件**：

| 文件 | 用途 | 必须？ |
|---|---|---|
| `AGENTS.md` | Agent 操作指令（工具使用规则、安全红线） | ✅ |
| `SOUL.md` | AI 人设/性格/沟通风格 | ✅ |
| `USER.md` | 用户偏好/稳定指令 | ✅ |
| `IDENTITY.md` | AI 名字/物种/emoji | 推荐 |
| `MEMORY.md` | 长期事实/决策（主会话专用） | ✅ |
| `memory/YYYY-MM-DD.md` | 每日日志 | ✅（自动创建） |
| `DREAMS.md` | Dream Diary（可选） | 可选 |

> ⚠️ **MEMORY.md 安全边界**：主会话专用，**不在**群聊或共享场景加载（含个人上下文）。

### 2.3 配置模型 Provider

**官方文档**：`/gateway/configuration.md` · `/gateway/configuration-examples.md` · `/concepts/model-providers.md`

**最小配置** (`~/.openclaw/openclaw.json`)：

```json5
{
  agents: {
    defaults: {
      workspace: "~/.openclaw/workspace",
      model: { primary: "anthropic/claude-sonnet-4-6" },
    },
  },
}
```

**配置编辑方式**（4 种，任选）：

| 方式 | 命令/路径 | 适用场景 |
|---|---|---|
| 交互式向导 | `openclaw onboard` / `openclaw configure` | 首次配置 |
| CLI 单行 | `openclaw config set <path> <value>` | 精确修改 |
| Control UI | `http://127.0.0.1:18789` → Config tab | 可视化编辑 |
| 直接编辑 | `~/.openclaw/openclaw.json` | 批量修改（支持热重载） |

> ⚠️ **配置格式**：JSON5（支持注释和尾逗号）。所有字段可选，缺失走安全默认值。

### 2.4 启动 Gateway

```bash
# 前台启动（调试用）
openclaw gateway start

# 后台服务（推荐）
openclaw gateway install  # 注册 LaunchAgent
openclaw gateway status   # 验证状态
```

**验证**：
```bash
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:18789/  # 应返回 200
openclaw status
```

### 2.5 首个对话

```bash
# WebChat
openclaw webchat

# 或直接访问
open http://127.0.0.1:18789
```

---

## 3. L1 — 系统层（OpenClaw 基座）

> **约束**：L1 不可修改，升级跟随官方版本。breaking changes 需走 ADR。

### 3.1 L1 能力清单

| 能力类 | 具体能力 | 官方文档 |
|---|---|---|
| Agent Runtime | 嵌入式 agent loop、模型路由、prompt 组装、会话管理 | `/concepts/agent-loop.md` · `/concepts/agent.md` |
| Skills | 技能发现/加载/调用；frontmatter 元数据；本地 + ClawHub | `/tools/skills.md` · `/tools/creating-skills.md` |
| Memory | MEMORY.md + memory/ 目录、会话持久化、记忆检索 | `/concepts/memory.md` · `/concepts/memory-search.md` |
| Cron | 定时任务、agent turn、isolated run、triggers | `/automation/cron-jobs.md` |
| Gateway | WS gateway、IM 通道、webchat、Canvas | `/concepts/architecture.md` |
| Config | profile、config schema、env 注入、SecretRef | `/gateway/configuration.md` |
| Tools | exec/read/write/edit/apply_patch/process/sessions_spawn/web_search | `/tools/` |
| Plugins | Tavily/1Password/MCP 等；hooks 注入 | `/plugins/manage-plugins.md` |
| Audit | 工具调用审计、消息生命周期 | `/gateway/audit.md` |
| Compaction | 自动压缩、手动 /compact、溢出恢复 | `/concepts/compaction.md` |
| Heartbeat | 定期 agent turn、通知规则 | `/gateway/heartbeat.md` |

### 3.2 会话管理

**官方文档**：`/concepts/session.md` · `/concepts/main-session.md`

| 概念 | 说明 |
|---|---|
| 主会话 (Main Session) | 所有 DM 共享的滚动会话，key = `agent:<agentId>:main` |
| 群组隔离 | 每个群聊独立会话 |
| Cron 隔离 | 每次 cron run 独立会话 |
| 会话可见性 | `tools.sessions.visibility` 控制跨会话可见范围 |

### 3.3 上下文管理

**官方文档**：`/concepts/compaction.md` · `/concepts/session-pruning.md` · `/reference/session-management-compaction.md`

**两层防线**（原设计三层，pruning 已证实不生效）：

| 层 | 机制 | 配置 | 状态 |
|---|---|---|---|
| 第 1 层 | Auto-compaction | `agents.defaults.compaction.mode: "safeguard"` | ✅ 生效 |
| ~~第 2 层~~ | ~~Session pruning~~ | ~~`contextPruning.mode: "cache-ttl"`~~ | ❌ 死配置 |
| 第 3 层 | Mid-turn precheck | `midTurnPrecheck.enabled: true` | ✅ 生效 |

> ⚠️ **cache-ttl 死配置**：`buildContextPruningFactory` 在 provider 白名单校验处提前 return。本机 provider=`coding-plan` 不在白名单（仅 Anthropic 系 + 少数例外）。

**compaction 模型委托**：
```json5
{
  agents: {
    defaults: {
      compaction: {
        model: "coding-plan/deepseek-v4-flash",  // 大 ctx(1049k)，且**与主会话同 provider**
        // ⚠️ 2026-08-24 教训：勿指向另一个 provider。显式 compaction.model 不继承 fallback
        // 链（concepts/compaction.md:101），compaction.fallbacks 是非法字段 ⇒ 该 provider
        // 一挂，压缩就没兜底，造成「会话活着但压缩死了」的分裂故障。
        mode: "safeguard",
        keepRecentTokens: 30000,       // cut-point 预算
        maxActiveTranscriptBytes: "20mb",
        midTurnPrecheck: { enabled: true },
      },
    },
  },
}
```

**contextWindow 必须显式声明**：

| 模型 | 实测值 | 配置值 |
|---|---|---|
| glm-5.3 | 1,048,568 | 1048576 |
| minimax-m3 | ~1,046,182 | 1048576 |
| ark-code-latest | 224,051 | 229376 |
| kimi-k2.7-code | 262144 | 262144 |

> **实测法**：`scripts/probe_context_window.py` 二分探边界，不盲信官方文档。

---

## 4. L2 — 基础设施层建设

### 4.1 组件建设状态

| 组件 | ADR | DESIGN.md | 实现 | 验证 |
|---|---|---|---|---|
| 可观测性 | 004 | `components/observability/` | `scripts/observability/agent_observer.py` | `--daily --jsonl` |
| 凭据管理 | 005 | `components/credentials/` | `scripts/credentials.sh` | `scan_secrets.sh` |
| 持久化 | 006 | `components/persistence/` | `persistence/` | 迁移幂等测试 |
| 配置管理 | 007 | `components/config/` | `scripts/config.sh` | `config.sh diff` |
| 工具策略 | 008 | `components/tool-policy/` | `scripts/tool_policy_audit.sh` | 六项审计 |
| 记忆语义检索 | 009 | `components/memory-embedding/` | 配置态 | 向量召回实测 |
| 知识库能力 | 010 | `components/knowledge-base/` | `scripts/kb_index.py` | pre-commit 阻塞 |

### 4.2 凭据管理

**官方文档**：`/gateway/secrets.md` · `/reference/secretref-credential-surface.md` · `/cli/secrets.md`

#### 4.2.1 SecretRef 迁移流程

```bash
# 1. 审计当前状态
openclaw secrets audit --check

# 2. 交互式配置（推荐）
openclaw secrets configure

# 3. 或手动迁移
# 3a. 创建凭据文件
echo "<secret>" > ~/.openclaw/secrets/<name>
chmod 600 ~/.openclaw/secrets/<name>

# 3b. 注册 provider
openclaw config set secrets.providers.<providerName> \
  '{"source":"file","path":"~/.openclaw/secrets/<name>","mode":"singleValue"}'

# 3c. 改为引用
openclaw config set <credential.path> \
  '{"source":"file","provider":"<providerName>","id":"value"}'

# 4. 验证
openclaw secrets audit --check  # 应报 plaintext=0
```

#### 4.2.2 本机凭据状态

| 字段 | 状态 | SecretRef Provider |
|---|---|---|
| `models.providers.coding-plan.apiKey` | ✅ SecretRef | `codingplankey` |
| `models.providers.longCat.apiKey` | ✅ SecretRef | `longcatkey` |
| `plugins.entries.tavily.config.webSearch.apiKey` | ✅ SecretRef | `tavilykey` |
| `gateway.auth.token` | ✅ SecretRef | `gatewayauthtoken` |
| `channels.wecom.secret` | ❌ 明文 | core `.trim()` 不兼容 |

> ⚠️ **channels.wecom.secret 不得使用 SecretRef**：`dist/channel-B2DGqAWl.js:1799` 无条件对 `account.secret` 调 `.trim()`，收到 SecretRef 对象后抛异常。官方 SecretRef 覆盖矩阵**未收录 wecom**，这个缺席是有原因的。

#### 4.2.3 凭据扫描

```bash
# Shell 层（pre-commit 友好）
bash scripts/scan_secrets.sh
bash scripts/scan_secrets.sh --range HEAD~3..HEAD  # 指定范围

# Python 层（独立使用）
python3 scripts/cred_scan.py ~/.openclaw/openclaw.json
```

### 4.3 配置管理

**官方文档**：`/gateway/configuration.md` · `/cli/config.md` · `/gateway/doctor.md`

#### 4.3.1 配置变更四步法

| 步骤 | 命令 | 说明 |
|---|---|---|
| ① dry-run | `openclaw config patch --file <patch.json> --dry-run` | 校验 schema |
| ② 应用 | `openclaw config patch --file <patch.json>` | 执行变更 |
| ③ **读回确认** | `openclaw config get <path>` | **强制！不要信 "Applied N updates"** |
| ④ 快照入库 | `python3 scripts/snapshot_config.py` | 脱敏后 git add |

#### 4.3.2 配置快照脱敏

```bash
# 检查是否需要更新
python3 scripts/snapshot_config.py --check

# 重生快照
python3 scripts/snapshot_config.py

# 查看 diff
python3 scripts/snapshot_config.py --diff
```

**脱敏策略**：精确字段名匹配 + 值形态兜底（防 `GROQ_API_KEY` 类命名漏网）。

#### 4.3.3 配置备份链

OpenClaw 自动维护 5 份轮转备份：`.bak` / `.bak.1` / `.bak.2` / `.bak.3` / `.bak.4` + `.last-good`。

### 4.4 工具策略治理

**官方文档**：`/gateway/config-tools.md` · `/tools/elevated.md` · `/gateway/sandbox-vs-tool-policy-vs-elevated.md`

#### 4.4.1 「允许」≠「可用」三态模型

| 状态 | 说明 | 危险性 |
|---|---|---|
| `denied` | 策略拒绝，工具不出现 | 低 — 明确失败 |
| `allowed-but-broken` | 策略允许，但缺依赖/凭据 | **高 — 静默失败** |
| `allowed-and-working` | 策略允许且真实可用 | — |

#### 4.4.2 当前策略配置

```json5
{
  tools: {
    profile: "coding",
    alsoAllow: ["tavily_search", "tavily_extract"],
  },
}
```

#### 4.4.3 关键规则

- `allow` 与 `alsoAllow` **不能**在同一 scope 并存
- `deny` 优先于 `allow`
- `deny: ["write"]` **不会**连带 deny `apply_patch`（不对称）
- `tools.elevated` 仅在 sandbox 开启时有效（本机 sandbox=off ⇒ no-op）

#### 4.4.4 审计

```bash
bash scripts/tool_policy_audit.sh  # 六项检查，退出码 0=健康
```

### 4.5 记忆语义检索

**官方文档**：`/concepts/memory-search.md` · `/reference/memory-config.md` · `/concepts/memory-builtin.md`

#### 4.5.1 本地 GGUF Embedding

```json5
{
  memory: {
    search: {
      provider: "local",
      fallback: "none",
    },
  },
}
```

**关键约束**：
- 模型文件名：`hf_ggml-org_embeddinggemma-300m-qat-Q8_0.gguf`（768 维）
- ⚠️ **不可改名**、**不可设 `local.modelPath`**（两者都会破坏索引身份）
- HuggingFace 在本网络不可达，用 `hf-mirror.com`

#### 4.5.2 验证

```bash
openclaw memory search "测试查询" --json
# 应返回 vectorScore > 0（非零表示向量召回生效）
```

### 4.6 知识库工具链

**官方文档**：`/concepts/agent.md`（workspace 章节）

```bash
# schema 校验
python3 scripts/kb_index.py --validate

# 三维分布统计
python3 scripts/kb_index.py --stats

# 交叉查询
python3 scripts/kb_index.py --query layer=L2 stage=manage

# 孤儿/断链检测
python3 scripts/kb_index.py --xref

# 重生 INDEX.md
python3 scripts/kb_index.py --emit-index
```

### 4.7 可观测性

```bash
# 每日观测摘要
python3 scripts/observability/agent_observer.py --daily --jsonl

# 会话状态
openclaw status
openclaw cron list --all
```

---

## 5. 安全

**官方文档**：`/gateway/security/index.md` · `/gateway/security/exposure-runbook.md` · `/gateway/authentication.md`

### 5.1 网关认证

```json5
{
  gateway: {
    auth: {
      mode: "token",     // "token" | "password" | "trusted-proxy"
      token: { source: "file", provider: "gatewayauthtoken", id: "value" },
    },
    bind: "loopback",    // 仅本机访问
  },
}
```

### 5.2 端口暴露面

```bash
# 检查所有 LISTEN 端口
lsof -nP -iTCP -sTCP:LISTEN | grep -v 127.0.0.1 | grep -v "::1"
# 应无输出（全部绑 loopback）
```

**当前状态**：全部 LISTEN 端口绑 `127.0.0.1`/`[::1]`，无一对外暴露。

### 5.3 沙箱

**官方文档**：`/gateway/sandboxing.md`

| 模式 | 说明 | 本机状态 |
|---|---|---|
| `off` | 无沙箱（默认） | ✅ 当前 |
| `non-main` | 除主会话外全部沙箱化 | ⚪ 暂缓（无可用 backend） |
| `all` | 全部会话沙箱化 | ⚪ 暂缓 |

> ⚠️ **暂缓理由**：backend 默认 `docker`，本机 Docker 不可用；`openshell` 插件未安装；无远程 SSH 开发机。设了反而破坏 WeCom 会话。

### 5.4 速率限制

**官方文档**：`/gateway/security/rate-limiting.md`

| 限制 | 默认值 | 说明 |
|---|---|---|
| Auth lockout | 5 次/15min | 暴力破解防护 |
| Browser throttle | 10 req/s | 浏览器工具 |
| Webhook throttle | 100 req/s | Webhook 入口 |
| Restart cooldown | 5s | 重启间隔 |

### 5.5 审计

```bash
# 凭据审计
openclaw secrets audit --check

# 安全审计
openclaw security audit --deep

# 配置 lint
openclaw doctor --lint
openclaw doctor --lint --json
```

### 5.6 备份与恢复

```bash
# 记忆+技能加密备份
mkdir -p ~/.openclaw/backups/memory-snapshot
tar czf /tmp/memory-backup.tar.gz -C ~/.openclaw memory/ MEMORY.md DREAMS.md
tar czf /tmp/skills-backup.tar.gz -C ~/.openclaw workspace/skills/
openssl enc -aes-256-cbc -salt -pbkdf2 -in /tmp/memory-backup.tar.gz \
  -out ~/.openclaw/backups/memory-snapshot/memory-$(date +%Y%m%d).tar.gz.enc \
  -pass file:<(echo -n "$(hostname)-openclaw-backup")
openssl enc -aes-256-cbc -salt -pbkdf2 -in /tmp/skills-backup.tar.gz \
  -out ~/.openclaw/backups/memory-snapshot/skills-$(date +%Y%m%d).tar.gz.enc \
  -pass file:<(echo -n "$(hostname)-openclaw-backup")
rm -f /tmp/memory-backup.tar.gz /tmp/skills-backup.tar.gz

# 解密验证
openssl enc -aes-256-cbc -d -pbkdf2 \
  -in ~/.openclaw/backups/memory-snapshot/memory-*.tar.gz.enc \
  -pass file:<(echo -n "$(hostname)-openclaw-backup") | tar tzf -
```

---

## 6. 自动化与调度

**官方文档**：`/automation/cron-jobs.md` · `/automation/cron-vs-heartbeat.md` · `/gateway/heartbeat.md`

### 6.1 Cron vs Heartbeat 选择

| 场景 | 用 Heartbeat | 用 Cron |
|---|---|---|
| 定期检查（邮件/日历/天气） | ✅ | — |
| 精确定时任务（每日 9:00 报告） | — | ✅ |
| 一次性提醒 | — | ✅ |
| 需要完整会话上下文 | ✅ | — |
| 需要隔离运行 | — | ✅ |

### 6.2 Cron 任务管理

```bash
# 列出全部任务
openclaw cron list --all

# 创建一次性任务
openclaw automations create "2026-08-25T09:00:00+08:00" \
  --name "Reminder" \
  --session main \
  --system-event "Check something" \
  --delete-after-run

# 创建周期任务
openclaw automations create \
  --schedule '{"kind":"cron","expr":"0 9 * * *","tz":"Asia/Shanghai"}' \
  --name "Daily Report" \
  --session isolated \
  --script "python3 scripts/observability/agent_observer.py --daily --jsonl"

# 手动触发
openclaw automations run <jobId>

# 删除
openclaw automations remove <jobId>
```

> ⚠️ **delivery.mode=none**：无 channel 环境必须设，否则投递失败会污染 job 状态。

### 6.3 Heartbeat 配置

```json5
{
  agents: {
    defaults: {
      heartbeat: {
        every: "30m",  // 默认 30m
      },
    },
  },
}
```

---

## 7. 技能与插件

**官方文档**：`/tools/skills.md` · `/tools/creating-skills.md` · `/tools/skill-workshop.md` · `/plugins/manage-plugins.md`

### 7.1 技能类型

| 类型 | 位置 | 优先级 |
|---|---|---|
| 内置 (bundled) | OpenClaw 安装目录 | 最低 |
| ClawHub | `~/.openclaw/skills/` | 中 |
| Workspace | `workspace/skills/` | **最高** |

### 7.2 创建技能

```markdown
---
name: my-skill
description: 触发短语 — 具体任务
---

# 技能名称

## 何时使用

## 步骤

## 验证
```

### 7.3 Skill Workshop

```json5
{
  skills: {
    workshop: {
      autonomous: { mode: "propose" },  // "off" | "propose" | "auto"
      approvalPolicy: "pending",         // "auto" | "pending"
    },
  },
}
```

> ⚠️ **安全加固**：`autonomous.mode` 默认 `auto` 会自动生成技能。已降为 `propose` + `approvalPolicy: pending`。

### 7.4 插件管理

```bash
# 列出全部插件
openclaw plugins list

# 安装
openclaw plugins install @openclaw/tavily-plugin

# 启用/禁用
openclaw plugins enable tavily
openclaw plugins disable tavily

# 检查兼容性
openclaw plugins check
```

### 7.5 plugins.allow 白名单

```json5
{
  plugins: ["llama-cpp", "longcat", "tavily", "wecom-openclaw-plugin", "openclaw-weixin"],
}
```

> ⚠️ **严格白名单**：设置后 enabled 插件 57→5。改后必须逐项验证依赖能力。

---

## 8. 频道接入

**官方文档**：`/gateway/config-channels.md` · `/channels/`

### 8.1 频道配置模板

```json5
{
  channels: {
    // Telegram 示例
    telegram: {
      botToken: { source: "file", provider: "telegramkey", id: "value" },
      allowFrom: ["@your_username"],
      groups: { "*": { requireMention: true } },
    },

    // Discord 示例
    discord: {
      botToken: { source: "file", provider: "discordkey", id: "value" },
      allowFrom: ["your_user_id"],
    },
  },
}
```

### 8.2 频道通用规则

- `allowFrom`：DM 白名单（建议始终设置）
- `groups.*.requireMention`：群聊是否需要 @才响应
- `dmPolicy`：`"open"` / `"pairing"`（pairing 需审批）
- 凭据必须用 SecretRef，不得明文

---

## 9. 运维与巡检

### 9.1 日常检查清单

| 检查项 | 命令 | 期望 |
|---|---|---|
| 网关状态 | `openclaw status` | 渠道 OK |
| 凭据审计 | `openclaw secrets audit --check` | `plaintext=0` |
| Cron 健康 | `openclaw cron list --all` | 全部 `lastRunStatus=ok` |
| 端口暴露面 | `lsof -nP -iTCP -sTCP:LISTEN` | 全部 `127.0.0.1`/`::1` |
| 知识库 | `python3 scripts/kb_index.py --validate` | 0 错误 |
| 工具策略 | `bash scripts/tool_policy_audit.sh` | 退出码 0 |

### 9.2 诊断命令梯

```bash
# 1. 快速状态
openclaw status
openclaw gateway status

# 2. 日志
openclaw logs --follow

# 3. 诊断
openclaw doctor
openclaw doctor --lint
openclaw doctor --lint --json

# 4. 修复
openclaw doctor --fix  # 应用推荐修复
```

### 9.3 常见错误处理

| 错误 | 原因 | 修复 |
|---|---|---|
| `plaintext=N` | 明文凭据残留 | `openclaw secrets configure` 迁移 |
| `unresolved=N` | SecretRef 解析失败 | 检查 provider 路径与文件权限 |
| `lastRunStatus=error` | Cron 任务失败 | `openclaw cron runs <jobId>` 查历史 |
| `delivery failed` | Cron 投递失败 | 设 `delivery.mode=none` |
| 渠道 `unconfigured` | 频道凭据缺失 | 检查 SecretRef 配置 |

### 9.4 重启恢复

**官方文档**：`/gateway/restart-recovery.md`

- 重启**不丢失**会话状态、transcript、后台任务
- 中断的 agent turn 自动恢复
- 排队的投递继续 drain

### 9.5 LaunchAgent 管理（macOS）

```bash
# 查看自有服务
launchctl list | grep openclaw

# 新增服务必须登记到架构文档 §8.1.1
# 清理流程见技能 macos-orphan-launchagent-cleanup
```

---

## 10. 参考资源

### 10.1 官方文档索引

| 分类 | 路径 | 关键文档 |
|---|---|---|
| 入门 | `/start/` | `getting-started.md` · `onboarding.md` |
| 概念 | `/concepts/` | `architecture.md` · `agent.md` · `memory.md` · `session.md` · `compaction.md` |
| 配置 | `/gateway/` | `configuration.md` · `configuration-reference.md` · `secrets.md` |
| 工具 | `/tools/` | `skills.md` · `elevated.md` · `exec.md` · `subagents.md` |
| 频道 | `/channels/` | `wechat.md` · `telegram.md` · `discord.md` |
| 插件 | `/plugins/` | `manage-plugins.md` · `manifest.md` |
| 自动化 | `/automation/` | `cron-jobs.md` · `cron-vs-heartbeat.md` |
| 安全 | `/gateway/security/` | `index.md` · `exposure-runbook.md` · `rate-limiting.md` |
| CLI | `/cli/` | `config.md` · `secrets.md` · `doctor.md` · `cron.md` · `agent.md` |

### 10.2 本系统文档

| 文档 | 路径 |
|---|---|
| 系统架构 | `docs/architecture/00-system-architecture.md` |
| 资产清单 | `docs/architecture/01-asset-inventory.md` |
| 知识库 | `docs/knowledge-base/README.md` |
| Commit 约定 | `docs/conventions/commit-and-config.md` |
| ADR 清单 | `docs/knowledge-base/by-category/project-experience/adr/` |
| EXP 清单 | `docs/knowledge-base/by-category/project-experience/correct/` |
| 组件设计 | `docs/architecture/components/*/DESIGN.md` |

### 10.3 关键经验教训

| 卡片 | 教训 |
|---|---|
| EXP-001 | Tavily 需 `alsoAllow` 解锁（plugin 升级时重新验证）|
| EXP-003 | compaction 模型应委托给最大 ctx 模型 |
| EXP-004 | contextWindow 必须实测，不盲信文档 |
| EXP-005 | cron `delivery.mode=none` 避免状态污染 |
| EXP-006 | WeCom aibot 无法主动投递 |
| EXP-007 | 第三方插件兼容性需实测 |
| EXP-009 | 引用官方文档必须读完相关章节 |
| EXP-010 | 用启发式代替证据（记录造假/dry-run 幻觉/局部检查）|

---

## 11. 变更历史

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-08-23 | 1.0 | 初版创建 — 覆盖阶段一全部建设步骤 |
---

## 12. 多 Agent 与委托

**官方文档**：`/concepts/multi-agent.md` · `/concepts/delegate-architecture.md`

### 12.1 多 Agent 路由

```json5
{
  agents: {
    entries: {
      personal: {
        workspace: "~/.openclaw/workspace-personal",
        identity: { name: "Personal", emoji: "🏠" },
      },
      work: {
        workspace: "~/.openclaw/workspace-work",
        identity: { name: "Work", emoji: "💼" },
      },
    },
  },
  multiAgent: {
    bindings: [
      { agentId: "personal", match: { channel: "telegram" } },
      { agentId: "work", match: { channel: "slack" } },
    ],
  },
}
```

### 12.2 委托架构

- Agent 以自身身份行动（不冒充人类）
- 显式委托权限
- 适用组织部署场景

---

## 13. 模型选择与故障转移

**官方文档**：`/concepts/model-providers.md` · `/concepts/model-failover.md` · `/concepts/models.md`

### 13.1 Provider 配置

```json5
{
  models: {
    providers: {
      "coding-plan": {
        api: "openai-completions",
        baseUrl: "https://ark.cn-beijing.volces.com/api/coding/v3",
        apiKey: { source: "file", provider: "codingplankey", id: "value" },
        models: [
          { id: "ark-code-latest", contextWindow: 229376 },
        ],
      },
    },
  },
}
```

### 13.2 故障转移

```json5
{
  agents: {
    defaults: {
      model: {
        primary: "coding-plan/ark-code-latest",
        fallbacks: ["coding-plan/deepseek-v4-flash"],
      },
    },
  },
}
```

---

## 14. 高级主题

### 14.1 OAuth

**官方文档**：`/concepts/oauth.md`

- 适用订阅制 provider（Claude Pro/Max、ChatGPT 等）
- Token 自动刷新
- 不得与 SecretRef 组合（policy guard）

### 14.2 Memory QMD

**官方文档**：`/reference/memory-config.md`

- SQLite 向量加速（sqlite-vec）
- 多模态索引（文本 + 图片）
- MMR 多样性排序

### 14.3 Dreaming

**官方文档**：`/concepts/dreaming.md`

```json5
{
  plugins: {
    entries: {
      "memory-core": {
        config: {
          dreaming: {
            enabled: true,
            schedule: "0 3 * * *",
          },
        },
      },
    },
  },
}
```

### 14.4 Prompt Caching

**官方文档**：`/reference/prompt-caching.md`

- 自动对 Anthropic 系生效
- cache-ttl pruning 仅对 Anthropic 系 + 少数例外生效

### 14.5 Self-Learning

**官方文档**：`/tools/self-learning.md`

| 模式 | 说明 |
|---|---|
| `off` | 不自动生成技能 |
| `propose` | 生成待审批提案（本机当前设置）|
| `auto` | 自动生成并应用（⚠️ 不安全）|

### 14.6 Hooks

**官方文档**：`/automation/hooks.md`

- 事件驱动：`/new` / `/reset` / `/stop` / compaction / gateway lifecycle
- 发现自目录，需显式启用

### 14.7 MCP

**官方文档**：`/tools/mcp.md`

```json5
{
  mcp: {
    servers: {
      myServer: {
        command: "npx",
        args: ["-y", "my-mcp-server"],
      },
    },
  },
}
```

---

## 15. 故障排查

**官方文档**：`/help/troubleshooting.md` · `/gateway/troubleshooting.md`

### 15.1 命令梯（按顺序执行）

```bash
# Step 1: 快速状态
openclaw status
openclaw gateway status

# Step 2: 日志
openclaw logs --follow

# Step 3: 诊断
openclaw doctor
openclaw doctor --lint
openclaw doctor --lint --json

# Step 4: 修复
openclaw doctor --fix

# Step 5: 深度安全审计
openclaw security audit --deep
```

### 15.2 常见问题速查

| 症状 | 诊断 | 修复 |
|---|---|---|
| 网关无法启动 | `openclaw logs` | Schema 校验失败 → `openclaw config validate` |
| 渠道显示 `unconfigured` | `openclaw channels list` | 检查 SecretRef 与 auth 配置 |
| Cron 持续 `error` | `openclaw cron runs <jobId>` | 检查 delivery.mode 与脚本退出码 |
| 记忆检索返回空 | `openclaw memory search "test" --json` | 检查 embedding provider 与向量索引 |
| 工具不可用 | `bash scripts/tool_policy_audit.sh` | 检查 profile/alsoAllow/deny |
| 会话历史丢失 | `openclaw sessions list` | 检查 transcript 文件是否存在 |
| 备份无法解密 | `openssl enc -d ...` | 确认加密时使用的 passphrase 一致 |

### 15.3 紧急回退

```bash
# 恢复配置备份
cp ~/.openclaw/openclaw.json.bak ~/.openclaw/openclaw.json
openclaw gateway restart

# 恢复记忆备份
openssl enc -aes-256-cbc -d -pbkdf2 \
  -in ~/.openclaw/backups/memory-snapshot/memory-*.tar.gz.enc \
  -pass file:<(echo -n "$(hostname)-openclaw-backup") | tar xzf - -C ~/.openclaw/
```

---

## 附录 A：配置参考速查

### A.1 顶层配置域

| 域 | 说明 | 官方文档 |
|---|---|---|
| `agents.*` | Agent 默认/多 Agent/会话/消息 | `/gateway/config-agents.md` |
| `channels.*` | 频道配置 | `/gateway/config-channels.md` |
| `tools.*` | 工具策略/实验开关 | `/gateway/config-tools.md` |
| `models.*` | 模型 provider 定义 | `/concepts/model-providers.md` |
| `memory.*` | 记忆搜索/QMD | `/reference/memory-config.md` |
| `plugins.*` | 插件配置 | `/plugins/manage-plugins.md` |
| `skills.*` | 技能配置 | `/tools/skills-config.md` |
| `mcp.*` | MCP 服务器 | `/tools/mcp.md` |
| `cron.*` | 自动化全局配置 | `/automation/cron-jobs.md` |
| `gateway.*` | Gateway 运行时 | `/gateway/configuration-reference.md` |

### A.2 本机实际配置

| 配置项 | 值 |
|---|---|
| `agents.defaults.model.primary` | `coding-plan/ark-code-latest` |
| `agents.defaults.model.fallbacks` | `["coding-plan/deepseek-v4-flash"]` |
| `agents.defaults.compaction.model` | `coding-plan/deepseek-v4-flash`（同主会话 provider）|
| `agents.defaults.compaction.mode` | `safeguard` |
| `agents.defaults.contextPruning.mode` | `cache-ttl`（⚠️ 不生效）|
| `tools.profile` | `coding` |
| `tools.alsoAllow` | `["tavily_search", "tavily_extract"]` |
| `memory.search.provider` | `local` |
| `memory.search.fallback` | `none` |
| `plugins.allow` | `["llama-cpp","longcat","tavily","wecom-openclaw-plugin","openclaw-weixin"]` |
| `gateway.auth.mode` | `token` |
| `gateway.bind` | `loopback` |
| `skills.workshop.autonomous.mode` | `propose` |
| `skills.workshop.approvalPolicy` | `pending` |

---

## 附录 B：CLI 命令速查

| 命令 | 用途 |
|---|---|
| `openclaw status` | 网关 + 渠道状态 |
| `openclaw doctor` | 诊断 + 修复建议 |
| `openclaw doctor --fix` | 应用推荐修复 |
| `openclaw doctor --lint` | 配置 lint |
| `openclaw config get <path>` | 读取配置 |
| `openclaw config set <path> <value>` | 设置配置 |
| `openclaw config patch --file <f>` | 批量变更 |
| `openclaw config validate` | Schema 校验 |
| `openclaw secrets audit --check` | 凭据审计 |
| `openclaw secrets configure` | 交互式 SecretRef 配置 |
| `openclaw cron list --all` | 列出全部 cron 任务 |
| `openclaw automations create ...` | 创建自动化任务 |
| `openclaw plugins list` | 列出插件 |
| `openclaw plugins install <pkg>` | 安装插件 |
| `openclaw channels list` | 列出渠道状态 |
| `openclaw memory search <query>` | 记忆检索 |
| `openclaw logs --follow` | 实时日志 |

---

## 附录 C：文件路径速查

| 路径 | 用途 |
|---|---|
| `~/.openclaw/openclaw.json` | 主配置（JSON5）|
| `~/.openclaw/openclaw.json.bak*` | 配置备份链（5 份轮转）|
| `~/.openclaw/secrets/` | 凭据文件目录（700）|
| `~/.openclaw/secrets/INDEX.md` | 凭据索引 |
| `~/.openclaw/workspace/` | Agent 工作区 |
| `~/.openclaw/workspace/AGENTS.md` | Agent 操作指令 |
| `~/.openclaw/workspace/SOUL.md` | AI 人设 |
| `~/.openclaw/workspace/USER.md` | 用户偏好 |
| `~/.openclaw/workspace/MEMORY.md` | 长期记忆 |
| `~/.openclaw/workspace/memory/` | 每日日志 |
| `~/.openclaw/workspace/skills/` | 本地技能（最高优先级）|
| `~/.openclaw/backups/memory-snapshot/` | 加密备份 |
| `~/.openclaw/backups/launchagents-2026-08-23/` | LaunchAgent plist 备份 |
| `~/.openclaw/logs/` | 网关日志 |
| `~/.openclaw/agents/main/sessions/` | 会话 transcript |
| `~/.openclaw/agents/main/agent/models.json` | 生成的模型目录 |
| `~/.openclaw/npm/projects/` | 外部插件源码 |
| `~/.openclaw/credentials/` | OAuth 凭据目录 |

---

## 附录 D：端口与服务

| 服务 | 端口 | 绑定 | 说明 |
|---|---|---|---|
| Gateway | 18789 | `127.0.0.1` / `[::1]` | WebChat + WS API |

> 历史已清除的端口：`*:18793`（dashboard，全网卡）、`127.0.0.1:20128`（model-scheduling）、`8088`（delivery-web）。

---

## 附录 E：外部依赖版本

| 依赖 | 版本 | 说明 |
|---|---|---|
| OpenClaw | 2026.7.2-beta.7 (dabe191) | L1 基座 |
| Node.js | v26.7.0 | 运行时 |
| @openclaw/llama-cpp-provider | 2026.7.1 | 本地 embedding |
| @openclaw/tavily-plugin | 2026.7.1 | Web 搜索 |
| longcat provider | 外部插件 | compaction fallback |
| wecom-openclaw-plugin | 外部插件 | 企业微信渠道 |
