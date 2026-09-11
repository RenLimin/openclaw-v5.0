# DMS-Framework

## 设计目标

提供通用交付管理框架引擎，覆盖项目管理、里程碑、交付物、风险、RACI 等通用模块。在 delivery-management-framework 基础上扩展 SaaS 多租户、Web UI、Schema 管理等企业级能力。

## 架构决策

- **框架引擎 + 业务模块分离**：`core/` 提供框架引擎（状态机/事件总线/RACI/注册引擎），`modules/` 提供业务模块
- **SaaS 预埋**：`core/saas.py` 提供 TenantContext、AuthProvider、TenantRouter，支持多租户部署
- **Web UI 内置**：`templates/` + `static/` 提供开箱即用的 Web 界面（Jinja2 + 原生 CSS/JS）
- **Schema 管理**：独立的 schema version/diff/migrate 命令，支持数据结构演进
- **模块化扩展**：新增业务模块只需在 `modules/` 下创建子目录，ModuleRegistry 自动发现

## 模块划分

```
dms-framework/
├── dms.py                      # CLI 统一入口
├── dms_api.py                  # API 入口
├── core/                       # 框架引擎
│   ├── module.py               # ModuleRegistry + ModuleManifest
│   ├── state_machine.py        # 状态机引擎
│   ├── raci.py                 # RACI 职责引擎
│   ├── workflow_scheme.py      # 流程方案引擎
│   ├── event_bus.py            # 事件总线
│   ├── cli.py                  # CLI 框架
│   ├── database.py             # BaseModel + Repository + 迁移
│   ├── saas.py                 # TenantContext + AuthProvider + TenantRouter
│   ├── api.py                  # API 框架
│   ├── webui.py                # Web UI 引擎
│   ├── config.py               # 配置管理
│   └── migrations.py           # DDL 迁移脚本
├── modules/                    # 业务模块
│   ├── project/                # 项目管理
│   ├── milestone/              # 里程碑
│   ├── deliverable/            # 交付物
│   ├── contract/               # 合同
│   ├── quality/                # 质量
│   ├── raci/                   # RACI 管理
│   └── tenant/                 # 租户管理
├── templates/                  # Web 模板（Jinja2）
├── static/                     # 静态资源
├── tests/                      # 单元 + 集成测试
└── docs/                       # 文档
```

## 关键接口/数据结构

- `ModuleRegistry`：模块注册中心，`register(module)` / `discover()` / `resolve_dependencies()`
- `StateMachineEngine`：状态机，支持状态定义、转移规则、事件触发
- `RACIEngine`：RACI 职责引擎
- `EventBus`：事件总线，发布/订阅模式
- `TenantContext`：多租户上下文，`tenant_id` 隔离
- `AuthProvider`：认证提供者接口
- `BaseModel` / `Repository`：数据模型基类 + 仓储基类

## 依赖关系

- **依赖**：Python 3.10+、SQLite/MySQL、Jinja2（Web UI）
- **被依赖**：`delivery-center`（L4 层，继承 DMS-Framework 的模块和引擎能力）

## 演进方向

1. **v1.x 持续优化**：当前 v1.2.0，持续完善核心引擎
2. **与 delivery-management-framework 整合**：两者功能重叠，可能合并为统一框架
3. **RESTful API 完善**：从 dms_api.py 扩展为完整 API 服务
4. **插件市场**：支持第三方模块接入 ModuleRegistry
