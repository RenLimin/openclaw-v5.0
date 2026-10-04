# tool-policy — 操作手册 (OPERATIONS)

> 版本: v1.0 · 日期: 2026-09-28

## 安装与启动

### 环境依赖

- bash

### 启动命令

```bash
bash tool_policy_audit.sh
```

### 健康检查

```bash
bash L2-infra/components/tool-policy/tool_policy_audit.sh --health
```

## 操作指南

### 场景一：审计工具策略

```bash
bash L2-infra/components/tool-policy/tool_policy_audit.sh
```

### 场景二：检查特定工具

```bash
bash L2-infra/components/tool-policy/tool_policy_audit.sh --tool tavily_search
```

## 配置说明

- 策略: 最小权限 + 显式追加
- 审计: 六项检查

## 故障排查

### 审计失败

- **症状**: 工具状态异常
- **原因**: 配置不一致
- **解决**: 检查 tools.profile 和 alsoAllow

### allowed-but-broken

- **症状**: 工具允许但不可用
- **原因**: 依赖缺失
- **解决**: 安装对应依赖或移除工具
