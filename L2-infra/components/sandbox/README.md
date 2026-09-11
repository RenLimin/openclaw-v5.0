# sandbox

**定位：** L2 基础设施层 — 沙箱隔离服务，管理子会话的生命周期、权限控制和文件挂载。

## 功能列表

- 沙箱创建/销毁/启动/停止
- 权限策略检查（命令白名单/黑名单）
- 沙箱状态查询
- 文件挂载管理（只读/读写）
- 输出捕获
- CLI 管理入口
- L1 运行时适配器解耦（不绑定具体容器运行时）

## 目录结构

```
sandbox/
├── service.py                   # 核心服务（沙箱生命周期 + 权限）
├── __init__.py
├── scripts/
│   ├── cli.py                   # CLI 入口
│   ├── sandbox.py               # SandboxManager 实现
│   ├── policy.py                # 权限策略定义
│   └── utils/
│       ├── __init__.py
│       └── utils.py             # 工具函数
├── tests/
│   ├── conftest.py
│   └── test_smoke.py
└── DESIGN.md
```

## 使用方式

```bash
# CLI 管理
python3 scripts/cli.py --help

# 编程方式
from service import SandboxIsolationService
svc = SandboxIsolationService()
```

## 依赖

- Python 3
- L1-runtime 适配器层（`adapters.openclaw.openclaw.adapter`）
