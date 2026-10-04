# context-management — 操作手册 (OPERATIONS)

> 版本: v1.0 · 日期: 2026-09-28

## 安装与启动

### 环境依赖

- python3

### 启动命令

```bash
python3 probe_context_window.py
python3 subagent_ctx_guard.py
```

### 健康检查

```bash
python3 probe_context_window.py --check
```

## 操作指南

### 场景一：探测上下文窗口

```bash
python3 L2-infra/components/context-management/probe_context_window.py
```

### 场景二：子代理上下文保护

```bash
python3 L2-infra/components/context-management/subagent_ctx_guard.py
```

## 配置说明

- contextWindow 阈值: 按模型配置
- 分段策略: < 50% ctx window

## 故障排查

### 探测失败

- **症状**: 无法获取窗口大小
- **原因**: 模型 API 不可达
- **解决**: 检查 API 连接
