# tool-policy

**定位：** L2 基础设施层 — 工具策略审计，验证"允许 ≠ 可用"，确保授权边界与实际可用性一致。

## 功能列表

- 工具策略配置审计（tools.profile/allow/deny）
- 工具实际可用性检查（二进制存在性、环境变量、网络可达性）
- 授权边界 vs 实际能力差异报告
- 退出码语义（0=健康，1=发现问题）

## 目录结构

```
tool-policy/
├── tool_policy_audit.sh     # 审计入口脚本
└── DESIGN.md
```

## 使用方式

```bash
./tool_policy_audit.sh
```

## 依赖

- bash 4+
- `openclaw` CLI（读取配置）
