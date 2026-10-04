# observability — 操作手册 (OPERATIONS)

> 版本: v1.0 · 日期: 2026-09-28

## 安装与启动

### 环境依赖

- python3

### 启动命令

```bash
python3 agent_observer.py --daily --jsonl
python3 memory_search_monitor.py
```

### 健康检查

```bash
python3 L2-infra/components/observability/scripts/agent_observer.py --health
```

## 操作指南

### 场景一：每日观测

```bash
python3 L2-infra/components/observability/scripts/agent_observer.py --daily
```

### 场景二：记忆检索监控

```bash
python3 L2-infra/components/observability/scripts/memory_search_monitor.py
```

## 配置说明

- 日志: 结构化 JSON
- 指标: 计数器/直方图/计时器

## 故障排查

### 日志丢失

- **症状**: 部分日志缺失
- **原因**: 日志级别过滤
- **解决**: 检查日志级别配置
