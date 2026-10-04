# session-recovery — 操作手册 (OPERATIONS)

> 版本: v1.0 · 日期: 2026-09-28

## 安装与启动

### 环境依赖

- python3

### 启动命令

```bash
python3 task_tracker.py current --json
python3 check_and_retry.py
```

### 健康检查

```bash
python3 L2-infra/components/session-recovery/scripts/task_tracker.py current
```

## 操作指南

### 场景一：登记任务

```bash
python3 L2-infra/components/session-recovery/scripts/task_tracker.py start \
  --id "task-001" --name "任务" --description "描述" \
  --phase "启动" --steps '["步骤1","步骤2"]'
```

### 场景二：检查当前任务

```bash
python3 L2-infra/components/session-recovery/scripts/task_tracker.py current --json
```

### 场景三：自动重试

```bash
python3 L2-infra/components/session-recovery/scripts/check_and_retry.py
```

## 配置说明

- 存储: current-task.md
- 自动重试: cron 配置

## 故障排查

### 任务未登记

- **症状**: current-task.md 不存在
- **原因**: 未调用 start
- **解决**: 检查代码是否调用了 task_tracker start

### 重试失败

- **症状**: 断点恢复失败
- **原因**: 中间状态丢失
- **解决**: 检查 progress_entries 数据
