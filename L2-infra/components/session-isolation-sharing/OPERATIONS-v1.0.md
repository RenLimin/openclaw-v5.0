# session-isolation-sharing — 操作手册 (OPERATIONS)

> 版本: v1.0 · 日期: 2026-09-28

## 安装与启动

### 环境依赖

- python3

### 启动命令

```bash
python3 cli.py --help
python3 orchestrator.py --help
```

### 健康检查

```bash
python3 L2-infra/components/session-isolation-sharing/cli.py --health
```

## 操作指南

### 场景一：跨会话共享

```bash
python3 L2-infra/components/session-isolation-sharing/cli.py share --from session-A --to session-B --data state.json
```

### 场景二：任务编排

```bash
python3 L2-infra/components/session-isolation-sharing/orchestrator.py --tasks tasks.yml
```

## 配置说明

- 共享: 基于文件协议
- 编排: 依赖排序 + 错峰发起

## 故障排查

### 共享失败

- **症状**: 状态不可见
- **原因**: 协议不匹配
- **解决**: 检查协议版本
