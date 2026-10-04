# dms-framework — 设计大纲 (DESIGN-OUTLINE)

> 版本: v1.0 · 日期: 2026-09-28

## 1. 整体架构

```
dms.py (CLI 统一入口)
    ↓
ModuleRegistry (模块注册引擎)
    ↓
core/ (框架引擎)
├── module.py          # ModuleRegistry + ModuleManifest
├── state_machine.py   # 状态机引擎
├── raci.py            # RACI 职责引擎
├── workflow_scheme.py # 流程方案引擎
├── event_bus.py       # 事件总线
├── database.py        # BaseModel + Repository + 迁移
├── saas.py            # TenantContext + AuthProvider + TenantRouter
├── api.py             # API 框架
├── webui.py           # Web UI 引擎
└── migrations.py      # DDL 迁移脚本
    ↓
modules/ (业务模块)
├── project/           # 项目管理
├── milestone/         # 里程碑
├── deliverable/       # 交付物
├── contract/          # 合同
├── quality/           # 质量
├── raci/              # RACI 管理
└── tenant/            # 租户管理
```

## 2. 模块划分

| 模块 | 职责 | 输入 | 输出 |
|---|---|---|---|
| ModuleRegistry | 模块注册与发现 | 模块定义 | 模块实例 |
| StateMachineEngine | 状态定义与转移 | 当前状态 + 事件 | 新状态 |
| EventBus | 事件发布/订阅 | 事件 + 数据 | 订阅者通知 |
| RACIEngine | 责任矩阵管理 | 角色分配 | 责任查询 |
| TenantContext | 租户上下文 | 请求 | 租户隔离 |

## 3. 接口契约

- `register(module)` / `discover()` / `resolve_dependencies()`
- `transition(state, event)` → new_state
- `publish(event, data)` / `subscribe(event, handler)`
- `assign_raci(task, roles)` / `query_raci(task)`

## 4. 技术选型

- CLI: argparse + 命令自动注册
- Web: Jinja2 + 原生 CSS/JS
- ORM: SQLite + Repository 模式
- 多租户: TenantContext 上下文注入

## 5. 分层约束

- L3 通用层：不绑定专有业务
- 被 L4 继承：BDMS 等 L4 组件调用本框架
