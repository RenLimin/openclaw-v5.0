# 凭据管理组件设计

> L2 基础设施层 · 凭据管理组件
>
> **2026-09-11 创建**：集中式 secrets 存储、SecretRef 解析、凭据扫描三合一。

## 1. 定位

| 维度 | 值 |
|---|---|
| 层级 | L2 基础设施层 |
| 组件类 | 凭据管理 |
| 状态 | ✅ 已建设 (2026-08) |
| ADR | ADR-202608-005 (凭据管理) |
| 验证 | smoke test + 手动审计 |

## 2. 设计约束

1. **文件权限强制 600**：所有凭据文件必须 `chmod 600`，目录 `chmod 700`。
2. **无尾换行存储**：凭据值用 `printf '%s'` 写入，避免换行符污染。
3. **永不打印凭据值**：扫描器只输出路径、长度、SHA-8 摘要，不暴露原文。
4. **备份保留**：轮换时旧值备份为 `.bak.<timestamp>`，需人工确认后删除。
5. **扫描误报控制**：要求密钥前缀后紧跟 ≥16 位实际字符，避免文档字面量自触发。
6. **SecretRef 识别**：`${...}` / `secret://` / `env:` / `op://` 等间接引用不算明文泄漏。

## 3. 架构

```
┌──────────────────────────────────────────────────────┐
│                    credentials                        │
├──────────────┬───────────────────┬───────────────────┤
│credentials.sh│  scan_secrets.sh  │   cred_scan.py    │
│ 生命周期管理  │  推送前泄漏扫描    │  递归凭据形状扫描  │
│ (add/rotate/ │  (staged/range)   │  (JSON 文件)      │
│  revoke/audit)│                   │                   │
└──────────────┴───────────────────┴───────────────────┘
```

### 3.1 模块职责

| 模块 | 文件 | 职责 |
|---|---|---|
| 生命周期管理 | `credentials.sh` | 凭据接入、轮换、撤销、审计、权限检查 |
| 推送前扫描 | `scan_secrets.sh` | Git staged/commit 区间内的凭据泄漏检测 |
| 递归形状扫描 | `cred_scan.py` | 递归扫描 JSON 文件中的凭据形态字段 |

## 4. 核心模块详解

### 4.1 credentials.sh — 凭据生命周期

**存储位置**：`~/.openclaw/secrets/`

**索引文件**：`~/.openclaw/secrets/INDEX.md`（Markdown 表格，记录 service → 文件名映射）

**五个操作**：

| 操作 | 命令 | 说明 |
|---|---|---|
| add | `credentials.sh add <service> <type>` | 交互式输入，创建 `service.type` 文件 |
| rotate | `credentials.sh rotate <service>` | 备份旧值 → 写入新值 |
| revoke | `credentials.sh revoke <service>` | 交互确认后删除文件 |
| audit | `credentials.sh audit` | 全量审计权限 + 大小 |
| check | `credentials.sh check` | 轻量权限检查（给 cron 用） |

**凭据类型**：`token` / `apiKey` / `pem` / `json`

**引用方式**（add 后二选一）：
- **方式 A — SecretRef**：通过 `openclaw config set secrets.providers.<name>` 注册 file provider
- **方式 B — Credential helper**：由 OpenClaw 内置 credential helper 管理

### 4.2 scan_secrets.sh — 推送前泄漏扫描

**两种模式**：
- `staged`（默认）：扫描 `git diff --cached` 已暂存的新增行
- `range`：扫描指定 commit 区间 `git diff A..B`

**检测模式（14 类）**：

| 类别 | 模式示例 |
|---|---|
| API Key | `ark-*`, `sk-*`, `tvly-*`, `AIza*` (Google), `xox[baprs]-*` (Slack) |
| GitHub Token | `ghp_*`, `gho_*`, `github_pat_*` |
| 私有密钥 | `-----BEGIN ... PRIVATE KEY-----` |
| AWS | `aws_secret_access_key=...` |
| JSON 字段 | `"apiKey"/"api_key"/"password"/"secret": "..."` |
| 归属标识 | `"botId"/"corpId"/"appId"/"clientId"/"tenantId"/"chatId": "..."` |
| WeCom 密钥 | `"corpSecret"/"appSecret"/"botSecret"/"encodingAESKey": "..."` |

**退出码**：0 = 干净，1 = 发现疑似凭据。

### 4.3 cred_scan.py — 递归凭据形状扫描

**输入**：一个或多个 JSON 文件路径。

**分类逻辑**：

```
字段名命中 KEY_PAT (secret/token/key/password/...)？
  ├── 值是 SecretRef/间接引用 → 标记为 SECRETREF
  ├── 值匹配 PLAIN_MARKERS (sk-/ghp_/tvly-/AKIA/...) → 标记为 PLAINTEXT
  ├── 值长度 ≥ 20 且字段名可疑 → 标记为 PLAINTEXT
  └── 值长度 < 20 且字段名可疑 → 标记为 SHORT
```

**输出**：按 PLAINTEXT / SECRETREF / OTHER-SHORT 三组，每组显示路径、长度、SHA-8 摘要。

**安全保证**：全程不打印凭据原文，仅输出 SHA-256 前 8 字符。

## 5. 检测模式对照

| 模式 | 文件 | 场景 |
|---|---|---|
| `ark-[A-Za-z0-9_-]{16,}` | scan_secrets.sh | 火山 ARK API Key |
| `sk-[A-Za-z0-9_-]{16,}` | scan_secrets.sh + cred_scan.py | OpenAI/通用 API Key |
| `ghp_[A-Za-z0-9]{16,}` | scan_secrets.sh + cred_scan.py | GitHub Personal Access Token |
| `tvly-[A-Za-z0-9_-]{16,}` | scan_secrets.sh + cred_scan.py | Tavily API Key |
| `xox[baprs]-*` | scan_secrets.sh + cred_scan.py | Slack Token |
| `AKIA[0-9A-Z]{16}` | cred_scan.py | AWS Access Key ID |
| `ya29.*` | cred_scan.py | Google OAuth Token |
| `eyJ[A-Za-z0-9_-]+.*` | cred_scan.py | JWT |
| `[0-9a-f]{32,64}` | cred_scan.py | 十六进制哈希/密钥 |
| `-----BEGIN ... PRIVATE KEY-----` | scan_secrets.sh | PEM 私钥 |

## 6. 存储结构

```
~/.openclaw/secrets/
├── INDEX.md              # 凭据索引（Markdown 表）
├── <service>.<type>      # 凭据文件（chmod 600）
├── <service>.<type>.bak.<timestamp>  # 轮换备份
└── .DS_Store             # macOS 元数据（自动跳过）
```

## 7. 依赖

| 依赖 | 类型 | 说明 |
|---|---|---|
| bash | 运行时 | credentials.sh / scan_secrets.sh 需要 bash 环境 |
| python3 | 运行时 | cred_scan.py 纯标准库实现 |
| git | 运行时 | scan_secrets.sh 依赖 git diff |
| stat | 运行时 | 跨平台权限检测（macOS `-f %Lp` / Linux `-c %a`） |
| OpenClaw config | 可选 | SecretRef provider 注册 |

## 8. 演进方向

| 方向 | 优先级 | 触发条件 |
|---|---|---|
| 集成到 pre-commit | 高 | 当前手动调用，可加入 pre-commit hooks |
| 自动轮换 | 中 | 支持定期自动 rotate（需配合通知机制） |
| 加密存储 | 中 | 当前明文文件存储，可引入 keychain 或 age 加密 |
| 凭据使用追踪 | 低 | 记录每个凭据的最后使用时间，标记过期凭据 |
| 与 OpenClaw secrets provider 深度集成 | 低 | 当前 add 后需手动注册 provider |

## 9. 变更记录

| 日期 | 变更 |
|---|---|
| 2026-08 | credentials.sh 首版（add/rotate/revoke/audit/check 五操作） |
| 2026-08 | scan_secrets.sh 首版（14 类模式，staged/range 双模式） |
| 2026-08 | cred_scan.py 首版（递归 JSON 扫描，SHA-8 摘要输出） |
| 2026-09-11 | 编写 DESIGN.md |
