# backup

**定位：** L2 基础设施层 — 数据备份与恢复，遵循 3-2-1 备份策略。

## 功能列表

- SQLite 快照备份（每日，gateway 运行时可用）
- workspace 敏感内容加密备份（memory/ skills/，AES-256-CBC）
- 官方全量备份封装（`openclaw backup create --verify`）
- 多版本保留与自动清理（默认 14 份）
- 备份验证（解密校验 + SQLite 快照完整性检查）
- 密钥分离存储（`~/.openclaw/secrets/backup.key`，权限 600）

## 目录结构

```
backup/
├── backup.sh          # 主入口脚本
└── DESIGN.md          # 设计文档
```

## 使用方式

```bash
./backup.sh              # 默认 = --daily
./backup.sh --daily      # 每日：SQLite 快照 + memory/skills 加密
./backup.sh --full       # 深度：官方全量（需先停 gateway）
./backup.sh --verify     # 验证最近一次加密备份 + SQLite 快照
./backup.sh --keep 14    # 保留最近 14 份（默认 14）
```

环境变量 `BACKUP_KEY` 可覆盖默认加密密钥。

## 依赖

- `openclaw` CLI（官方 backup 命令）
- OpenSSL（AES-256-CBC 加密）
- bash 4+
