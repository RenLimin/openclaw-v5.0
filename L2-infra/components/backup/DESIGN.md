# L2 备份组件 (backup) — 设计

> **状态**: 已上线（2026-08-22 创建）
> **层级**: L2 基础设施层
> **组件类**: 系统备份

## 1. 定位

| 维度 | 值 |
|---|---|
| 层级 | L2 基础设施层 |
| 组件类 | 系统备份与恢复 |
| 状态 | ✅ 已建设 |
| 设计依据 | 业界 3-2-1 最佳实践 + 官方 `docs/cli/backup.md` |

## 2. 职责

为 OpenClaw 系统提供**多层备份能力**，覆盖从轻量快照到深度全量的不同恢复场景：

1. **SQLite 快照**（每日，gateway 运行时可用）— 会话数据库 + 全局状态
2. **workspace 敏感内容加密备份** — memory/ + skills/ 的 AES-256-CBC 加密归档
3. **官方深度全量备份**（可选，需 gateway 停止）— 含配置/凭据/会话/workspace 便携归档
4. **验证与恢复** — 解密抽查 + SQLite 完整性校验
5. **多版本保留 + 自动清理** — 默认保留 14 份

## 3. 核心设计

### 3.1 三层备份策略

```
┌──────────────────────────────────────────────────────┐
│                    --daily（默认）                     │
│  ┌─────────────┐  ┌──────────────────────────────┐   │
│  │ SQLite 快照  │  │ memory/skills 加密备份        │   │
│  │ (运行时可用) │  │ (AES-256-CBC, pbkdf2)        │   │
│  └─────────────┘  └──────────────────────────────┘   │
├──────────────────────────────────────────────────────┤
│                    --full                             │
│  ┌────────────────────────────────────────────────┐  │
│  │ 官方 backup create --verify                     │  │
│  │ (需 gateway 停止, SQLite lock 限制)             │  │
│  └────────────────────────────────────────────────┘  │
├──────────────────────────────────────────────────────┤
│                    --verify                           │
│  ┌────────────────────────────────────────────────┐  │
│  │ 解密抽查 + SQLite verify                        │  │
│  └────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────┘
```

### 3.2 备份模式对比

| 模式 | 触发方式 | gateway 要求 | 内容 | 耗时 |
|---|---|---|---|---|
| `--daily` | cron / 手动 | 运行中即可 | SQLite + 加密 memory/skills | 秒级 |
| `--full` | 手动（维护前） | 必须停止 | 全量便携归档 | 分钟级 |
| `--verify` | 手动 / cron | 运行中即可 | 只验证不备份 | 秒级 |

### 3.3 存储布局

```
~/Backups/openclaw/
├── sqlite/                  # SQLite 快照（agent:main + global）
│   └── <timestamp>/         # 每次快照一个目录
├── memory-snapshot/         # 加密备份
│   ├── memory-<ts>.tar.gz.enc
│   ├── skills-<ts>.tar.gz.enc
│   └── config-snapshot-<ts>.json  # 脱敏配置快照（明文）
└── official/                # 官方全量备份
    └── <ts>-openclaw-backup.tar.gz
```

### 3.4 加密方案

| 维度 | 方案 |
|---|---|
| 算法 | AES-256-CBC |
| KDF | PBKDF2, 100,000 迭代 |
| 密钥文件 | `~/.openclaw/secrets/backup.key`（权限 600） |
| 密钥生成 | `openssl rand -base64 48`，首次运行自动生成 |
| 密钥覆盖 | 环境变量 `BACKUP_KEY` 可覆盖 |
| 密钥丢失 | 加密备份**永久不可解** → 需同步备份到密码管理器 |

### 3.5 保留策略

- 默认保留 14 份（`KEEP=14`，环境变量 `BACKUP_KEEP` 可覆盖）
- SQLite 快照：按修改时间清理，保留 `KEEP*2` 份（agent + global 各 KEEP）
- 加密备份：按时间戳分组（memory/skills 配对），保留 KEEP 组
- 清理在每次备份完成后自动执行

### 3.6 验证机制

| 验证项 | 方法 |
|---|---|
| 加密备份完整性 | `openssl enc -d` + `tar tzf` 解密抽查（不解出到磁盘） |
| SQLite 快照完整性 | `openclaw backup sqlite verify` |

## 4. 接口与用法

```bash
# 默认 = 每日备份
bash L2-infra/components/backup/backup.sh

# 显式指定模式
bash L2-infra/components/backup/backup.sh --daily   # SQLite + 加密
bash L2-infra/components/backup/backup.sh --full    # 官方全量（需停 gateway）
bash L2-infra/components/backup/backup.sh --verify  # 仅验证

# 保留策略
bash L2-infra/components/backup/backup.sh --keep 30
```

### 4.1 环境变量

| 变量 | 说明 | 默认值 |
|---|---|---|
| `BACKUP_KEY` | 覆盖加密密钥 | 从 `backup.key` 读取 |
| `BACKUP_KEEP` | 保留份数 | 14 |
| `OPENCLAW_BACKUP_ROOT` | 备份根目录 | `~/Backups/openclaw` |

## 5. 依赖

| 依赖 | 用途 |
|---|---|
| `openclaw` CLI | `backup sqlite create` / `backup create` / `backup sqlite verify` |
| `openssl` | 加密 / 解密验证 |
| `tar` | 打包 memory/ + skills/ |
| Homebrew PATH | launchd/cron 环境下补齐 `/opt/homebrew/bin` |

## 6. 设计约束

1. **备份目录不在 `~/.openclaw/` 内** — 官方 `backup create` 拒绝写入源路径内
2. **密钥与备份同级隔离** — 密钥在 `~/.openclaw/secrets/`，备份在 `~/Backups/openclaw/`
3. **配置快照脱敏后明文存储** — 方便快速对比，不含敏感值
4. **幂等** — 重复运行只生成一份快照（时间戳精度秒级）
5. **失败可见** — `set -euo pipefail`，任何步骤失败立即中止

## 7. 演进方向

| 方向 | 优先级 | 触发条件 |
|---|---|---|
| 备份状态通知 | 中 | 集成 wecom 通知，备份失败主动告警 |
| 自动 cron 调度 | 中 | 接入 L2 cron 管理，每日自动执行 |
| 远程备份 | 低 | 加密备份同步到远程存储（S3/TOS） |
| 增量备份 | 低 | memory/ 变更量大时，减少全量加密开销 |

## 8. 变更记录

| 日期 | 变更 |
|---|---|
| 2026-08-22 | 首版：三层备份策略 + AES 加密 + 保留清理 |
| 2026-08-23 | 配置快照脱敏后明文入库 |
