# L2 系统备份机制 — 设计文档

> 版本：v1.0
> 创建日期：2026-09-01
> 状态：✅ 已上线
> 层级：L2 基础设施层

---

## 一、概述

### 1.1 定位

系统级自动化备份能力，确保配置、凭据、会话、工作区的可恢复性。

### 1.2 核心目标

1. **自动化**：每日自动备份，无需人工干预
2. **版本化**：Git 版本化，支持任意时间点恢复
3. **完整性**：覆盖配置 + 凭据 + 会话 + 工作区
4. **可验证**：支持备份验证和恢复测试

---

## 二、架构设计

### 2.1 备份策略

| 维度 | 方案 |
|---|---|
| **频率** | 每 24 小时自动执行 |
| **存储** | `~/.openclaw/backups/auto-git`（本地 Git 仓库） |
| **类型** | `openclaw backup enable` Gateway automation |
| **格式** | Git 版本化 SQLite dump |
| **保留** | 无限（Git 历史） |

### 2.2 备份内容

| 内容 | 说明 |
|---|---|
| 配置 | `openclaw.json`（脱敏后） |
| 凭据 | SecretRef 引用的凭据数据 |
| 会话 | 会话历史和上下文 |
| 工作区 | Workspace 文件（AGENTS/MEMORY/SOUL 等） |

### 2.3 自动化配置

```bash
# 启用自动备份
openclaw backup enable --every 24h --repository ~/.openclaw/backups/auto-git

# 手动触发备份
openclaw backup create

# 验证备份
openclaw backup verify <archive>

# 恢复备份
openclaw backup restore <archive>
```

---

## 三、备份验证

### 3.1 定期验证

每月执行一次备份验证：
```bash
openclaw backup verify latest
```

### 3.2 恢复测试

每季度执行一次恢复测试（恢复到临时目录）：
```bash
openclaw backup restore latest --staging ~/.openclaw/backups/staging-test
```

---

## 四、监控

### 4.1 备份状态检查

```bash
openclaw cron list --all | grep backup
```

### 4.2 失败通知

备份失败时自动通知 Rex（通过 WeCom）。

---

## 五、变更历史

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-09-01 | v1.0 | 初始化：启用每日自动备份 + 手动备份机制 |
