# credentials — 操作手册 (OPERATIONS)

> 版本: v1.0 · 日期: 2026-09-28

## 安装与启动

### 环境依赖

- python3

### 启动命令

```bash
bash credentials.sh audit
python3 cred_scan.py
```

### 健康检查

```bash
bash L2-infra/components/credentials/credentials.sh audit
```

## 操作指南

### 场景一：凭据扫描

```bash
python3 L2-infra/components/credentials/cred_scan.py
```

### 场景二：凭据审计

```bash
bash L2-infra/components/credentials/credentials.sh audit
```

### 场景三：凭据备份

```bash
# 从 secret store 导出
openclaw secrets store list
```

## 配置说明

- 凭据存储: SQLite secret store
- 扫描范围: 全 workspace

## 故障排查

### 凭据泄露告警

- **症状**: 扫描发现明文凭据
- **原因**: 配置文件或代码中硬编码
- **解决**: 迁移到 SecretRef

### SecretRef 解析失败

- **症状**: 引用无法解析
- **原因**: 凭据已删除或过期
- **解决**: 重新添加凭据
