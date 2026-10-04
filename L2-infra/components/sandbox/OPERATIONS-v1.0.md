# sandbox — 操作手册 (OPERATIONS)

> 版本: v1.0 · 日期: 2026-09-28

## 安装与启动

### 环境依赖

- Docker (Colima)

### 启动命令

```bash
python3 sandbox.py --start
```

### 健康检查

```bash
python3 L2-infra/components/sandbox/sandbox.py --health
```

## 操作指南

### 场景一：启动沙箱

```bash
python3 L2-infra/components/sandbox/sandbox.py --start
```

### 场景二：在沙箱中执行命令

```bash
python3 L2-infra/components/sandbox/sandbox.py --exec "command"
```

## 配置说明

- 镜像: 自定义沙箱镜像
- 安全: workspaceAccess=ro / readOnlyRoot / network:none

## 故障排查

### 启动失败

- **症状**: Docker 容器无法启动
- **原因**: Colima 未运行
- **解决**: 启动 Colima: `colima start`
