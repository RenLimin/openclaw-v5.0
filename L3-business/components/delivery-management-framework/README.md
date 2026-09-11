# delivery-management-framework

**定位：** L3 业务层 — 交付管理框架（DMF），提供项目管理、RACI 矩阵、状态机、事件总线的领域驱动设计骨架。

## 功能列表

- 项目管理（Project 模型 + 成员管理）
- 工作项管理（WorkItem 模型）
- RACI 责任矩阵（Responsible/Accountable/Consulted/Informed）
- 状态机引擎（状态定义、转移规则、事件触发）
- 事件总线（发布/订阅模式）
- 模块注册引擎（自动发现、依赖解析、生命周期管理）
- 变更日志（ChangeLog 模型）
- 利益相关者管理（Stakeholder 模型）
- 统一 CLI 框架（命令自动注册）
- 多租户 + 软删除

## 目录结构

```
delivery-management-framework/
├── __init__.py
├── dms_cli.py                       # CLI 统一入口（dms 命令）
├── cli/
│   ├── __init__.py
│   └── cli.py                       # CLI 框架（命令注册/分发）
├── models/
│   ├── __init__.py
│   └── base.py                      # BaseModel（tenant_id + CRUD）
├── project/
│   ├── __init__.py
│   └── project_model.py
├── project_member/
│   ├── __init__.py
│   └── project_member_model.py
├── work_item/
│   ├── __init__.py
│   └── work_item_model.py
├── stakeholder/
│   ├── __init__.py
│   └── stakeholder_model.py
├── responsibility/
│   ├── __init__.py
│   └── assignment_model.py
├── change_log/
│   ├── __init__.py
│   └── change_log_model.py
├── raci/
│   ├── __init__.py
│   └── raci.py                      # RACI 引擎
├── state_machine/
│   ├── __init__.py
│   └── state_machine.py             # 状态机引擎
├── event_bus/
│   ├── __init__.py
│   └── event_bus.py                 # 事件总线
├── registry/
│   ├── __init__.py
│   └── module_registry.py           # 模块注册引擎
├── repo/
│   ├── __init__.py
│   └── base_repo.py                 # 通用仓储基类
├── migrations/
│   └── 0001_initial.sql             # 初始建表脚本
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── test_cli.py
    ├── test_registry.py
    ├── test_event_bus.py
    ├── test_state_machine.py
    ├── test_raci.py
    ├── test_models_base.py
    ├── test_models_project.py
    ├── test_models_work_item.py
    ├── test_models_other.py
    └── test_repo.py
```

## 使用方式

```bash
# CLI 入口
python3 dms_cli.py --help

# 编程方式
from registry.module_registry import ModuleRegistry
from state_machine.state_machine import StateMachineEngine
from raci.raci import RACIEngine
```

## 依赖

- Python 3.10+
- SQLite / MySQL（通过 repo 层适配）
