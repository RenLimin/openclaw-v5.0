# backup — 操作手册 (OPERATIONS)

> 版本: v1.0 · 日期: 2026-09-28

## 安装与启动

### 环境依赖

- Git
- bash

### 启动命令

```bash
bash backup.sh
```

### 健康检查

```bash
# 检查最近备份
git log --oneline -1
```

## 操作指南

### 场景一：手动备份

```bash
cd /Users/bangcle/.openclaw/workspace
bash L2-infra/components/backup/backup.sh
```

### 场景二：自动备份（cron 已配置）

每日自动执行，无需手动干预。

## 配置说明

- 备份策略: git commit + push
- 存储: GitHub 远程仓库

## 故障排查

### 备份失败

- **症状**: git push 失败
- **原因**: 网络问题或权限不足
- **解决**: 检查网络连接和 git 凭据
