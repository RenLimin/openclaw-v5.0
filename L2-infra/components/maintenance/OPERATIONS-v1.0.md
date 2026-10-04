# maintenance — 操作手册 (OPERATIONS)

> 版本: v1.0 · 日期: 2026-09-28

## 安装与启动

### 环境依赖

- python3

### 启动命令

```bash
bash L2-infra/components/maintenance/repo_health.sh
bash L2-infra/components/maintenance/memory_maintenance.sh
bash L2-infra/scripts/error_handler/scan_errors.sh
```

### 健康检查

```bash
# 仓库健康
bash L2-infra/components/maintenance/repo_health.sh
```

## 操作指南

### 场景一：仓库健康检查

```bash
bash L2-infra/components/maintenance/repo_health.sh
```

### 场景二：内存维护

```bash
bash L2-infra/components/maintenance/memory_maintenance.sh
```

### 场景三：错误扫描

```bash
bash L2-infra/scripts/error_handler/scan_errors.sh
```

## 配置说明

- 仓库健康: 每天 09:00 自动执行
- 内存维护: 每周一 10:00 自动执行
- 错误扫描: 每 2 小时自动执行

## 故障排查

### 健康检查失败

- **症状**: 仓库不健康
- **原因**: 未提交更改或冲突
- **解决**: 提交更改或解决冲突
