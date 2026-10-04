# session-isolation — 操作手册 (OPERATIONS)

> 版本: v1.0 · 日期: 2026-09-28

## 安装与启动

### 环境依赖

- python3

### 启动命令

```bash
python3 cli.py --help
```

### 健康检查

```bash
python3 L2-infra/components/session-isolation/cli.py --health
```

## 操作指南

### 场景一：创建任务

```bash
python3 L2-infra/components/session-isolation/cli.py task-init --id task-001
```

### 场景二：写入状态

```bash
python3 L2-infra/components/session-isolation/cli.py state-write --scope project --data '{"key": "value"}'
```

### 场景三：记录事件

```bash
python3 L2-infra/components/session-isolation/cli.py event-log --task task-001 --event completed
```

## 配置说明

- 协议: Task/State/Event 三件套
- 命名空间: session/task/project/user/global

## 故障排查

### 协议不匹配

- **症状**: 状态写入失败
- **原因**: 协议版本不一致
- **解决**: 更新协议定义
