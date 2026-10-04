# config — 操作手册 (OPERATIONS)

> 版本: v1.0 · 日期: 2026-09-28

## 安装与启动

### 环境依赖

- bash
- python3

### 启动命令

```bash
bash config.sh --help
```

### 健康检查

```bash
bash config.sh audit
```

## 操作指南

### 场景一：配置快照

```bash
bash L2-infra/components/config/config.sh snapshot
```

### 场景二：漂移检测

```bash
bash L2-infra/components/config/config.sh diff
```

### 场景三：安全写入

```bash
bash L2-infra/components/config/config_safe_write.sh <patch_file>
```

## 配置说明

- 快照目录: `config-snapshots/`
- 脱敏策略: 精确字段名匹配

## 故障排查

### 快照失败

- **症状**: 快照文件未生成
- **原因**: 权限问题
- **解决**: 检查目录权限

### 漂移误报

- **症状**: 未变更但报漂移
- **原因**: 快照过期
- **解决**: 重新生成快照
