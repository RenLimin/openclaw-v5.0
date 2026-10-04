# persistence — 操作手册 (OPERATIONS)

> 版本: v1.0 · 日期: 2026-09-28

## 安装与启动

### 环境依赖

- python3

### 启动命令

```bash
# 作为库使用，无独立启动
```

### 健康检查

```bash
python3 -c "from persistence import *; print('OK')"
```

## 操作指南

### 场景一：数据库操作

```python
from persistence.connection import get_session
session = get_session()
# CRUD 操作
```

### 场景二：迁移

```bash
python3 L2-infra/components/persistence/migrations/001_initial_schema.sql
```

## 配置说明

- 存储: SQLite
- 模式: Repository + Unit of Work

## 故障排查

### 连接失败

- **症状**: 数据库不可达
- **原因**: 文件权限或路径错误
- **解决**: 检查文件路径和权限
