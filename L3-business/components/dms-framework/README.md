# DMS-Framework

L3 通用交付管理框架 — 框架引擎 + 通用模块 + 知识库 + L4 继承机制。

## 快速开始

```bash
# 初始化
python dms.py init

# 项目管理
python dms.py project create --name "我的项目"
python dms.py project list
python dms.py project show <id>

# Schema 管理
python dms.py schema version
python dms.py schema diff
python dms.py schema migrate

# 模块管理
python dms.py module list
```

## 架构

```
dms-framework/
├── dms.py              # CLI 统一入口
├── core/               # 框架引擎
│   ├── module.py       # ModuleRegistry + ModuleManifest
│   ├── state_machine.py # 状态机引擎
│   ├── raci.py         # RACI 职责引擎
│   ├── workflow_scheme.py # 流程方案引擎
│   ├── event_bus.py    # 事件总线
│   ├── cli.py          # CLI 框架
│   ├── database.py     # BaseModel + Repository + 迁移
│   ├── saas.py         # TenantContext + AuthProvider + TenantRouter
│   └── migrations.py   # DDL 迁移脚本
├── modules/            # 业务模块
│   ├── project/        # 项目管理
│   ├── milestone/      # 里程碑
│   ├── deliverable/    # 交付物
│   ├── risk/           # 风险
│   └── raci/           # RACI 管理
├── knowledge-base/     # 知识库
├── tests/              # 测试
└── scripts/            # 工具脚本
```

## 设计文档

- 架构设计：`docs/architecture/components/delivery-management-framework/DESIGN.md`
- ADR：`docs/knowledge-base/by-category/project-experience/adr/ADR-202609-025.md`

## 版本

- v1.2.0 (2026-09-03) — 6 项业界优化
- v1.1.0 (2026-09-03) — SaaS 预埋设计
- v1.0.0 (2026-09-03) — 初版框架设计
