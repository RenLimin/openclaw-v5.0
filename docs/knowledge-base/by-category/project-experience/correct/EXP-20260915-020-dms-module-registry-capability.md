---
title: "DMS 能力卡片：模块注册引擎 (ModuleRegistry)"
id: EXP-20260915-020
date: 2026-09-15
type: correct
project: delivery-management-framework
category: project-experience
layers: [L3]
phase: develop
tags: [dms, capability, module-registry, hot-plug, dependency-resolution]
---

# DMS 能力卡片：模块注册引擎 (ModuleRegistry)

## 概述
DMS 框架的模块注册引擎是整个框架的"装配中枢"，负责模块发现、注册、依赖解析和生命周期管理。所有业务模块都通过 `ModuleManifest` 声明自己，由 `ModuleRegistry` 统一调度。

## 核心价值
- **热插拔**：模块注册即用，不影响框架核心
- **依赖自动解析**：按依赖顺序拓扑排序初始化，避免循环依赖
- **统一契约**：所有模块遵循相同的 manifest 格式，可被 CLI / 事件总线 / 状态机自动发现
- **可观测**：列出所有已注册模块及其版本、依赖关系

## 核心组件

### ModuleManifest（模块声明）
模块的"身份证"，包含所有元信息：

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | str | 模块唯一名称 |
| `version` | str | 语义化版本号 |
| `description` | str | 模块描述 |
| `tables` | List[str] | 依赖的数据库表 |
| `commands` | List[CommandDef] | 暴露的 CLI 命令 |
| `dependencies` | List[str] | 依赖的其他模块名 |
| `hooks` | Dict[str, str] | 事件钩子（event → handler） |
| `config_schema` | dict | 配置 schema（可选） |

### CommandDef（命令定义）
CLI 命令的最小声明单元：

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | str | 命令名 |
| `handler` | Callable | 处理函数（接收 argparse subparser） |
| `description` | str | 命令描述 |

### ModuleRegistry（注册中心）
核心引擎，提供以下 API：

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `register(manifest)` | ModuleManifest | None | 注册模块，同名覆盖 |
| `unregister(name)` | str | None | 注销模块 |
| `get_module(name)` | str | Optional[ModuleManifest] | 获取模块信息 |
| `list_modules()` | — | List[ModuleManifest] | 列出所有模块 |
| `resolve_dependencies()` | — | Dict[str, List[str]] | 解析依赖，返回拓扑排序结果 |
| `get_dependency_order()` | — | List[str] | 按依赖顺序返回模块列表 |

## 关键特性

### 1. 依赖解析与循环检测
- 深度优先搜索（DFS）实现拓扑排序
- 自动检测循环依赖并抛出 `ValueError`
- 缺失依赖会报明确错误（不是静默失败）
- 注册新模块自动使缓存失效，下次解析重新计算

### 2. 注册即生效
- 模块注册后，CLI 自动出现对应命令（通过 manifest.commands）
- 事件钩子自动绑定到 EventBus（通过 manifest.hooks）
- 数据库表自动创建（通过 manifest.tables）

### 3. 幂等设计
- 重复注册同名模块：发出 warning 后覆盖（不是报错）
- 注销不存在的模块：发出 warning 后静默返回
- 依赖解析结果有缓存，注册/注销后自动失效

## 使用示例

```python
from registry.module_registry import ModuleRegistry, ModuleManifest, CommandDef

# 1. 创建注册中心
registry = ModuleRegistry()

# 2. 定义模块
def my_command_handler(subparser):
    subparser.add_argument("--name", required=True)
    # ... 实际处理逻辑

manifest = ModuleManifest(
    name="my_module",
    version="1.0.0",
    description="我的示例模块",
    dependencies=["project"],
    commands=[
        CommandDef(
            name="my_module:create",
            handler=my_command_handler,
            description="创建我的模块实例"
        )
    ]
)

# 3. 注册
registry.register(manifest)

# 4. 查询
print(registry.list_modules())  # [ModuleManifest(name='my_module', ...)]
print(registry.get_dependency_order())  # ['project', 'my_module']
```

## 设计决策

### 为什么用 manifest 模式而不是继承？
- **声明式优于继承**：模块只需要声明自己是什么，不需要继承复杂基类
- **组合优于继承**：模块通过依赖关系组合，不是通过继承树耦合
- **易测试**：manifest 是纯数据结构，mock 成本极低

### 为什么依赖解析结果要缓存？
- 依赖解析是 O(V+E) 的 DFS，模块多了有成本
- 绝大多数时间注册关系不变，缓存可避免重复计算
- 注册/注销操作自动失效缓存，保证正确性

## 测试覆盖
`tests/test_registry.py` — 18 个测试用例，覆盖：

| 测试组 | 用例数 | 覆盖点 |
|--------|--------|--------|
| 基础 CRUD | 7 | register / unregister / get / list / overwrite / 不存在处理 |
| 依赖解析 | 6 | 简单依赖 / 链式依赖 / 无依赖 / 缺失依赖 / 循环检测 / 自动解析 |
| 缓存机制 | 1 | 注册后缓存失效 |

**测试状态：18/18 passed**

## 扩展方向
- 模块版本兼容性检查（semver 约束）
- 模块启用/禁用开关（不卸载，只是停止响应）
- 模块健康检查接口
- 模块元数据持久化（当前仅内存）
- 模块级权限控制

## 参考
- 代码：`L3-business/components/delivery-management-framework/registry/module_registry.py`
- 测试：`L3-business/components/delivery-management-framework/tests/test_registry.py`
- 相关 ADR：[ADR-025](../adr/ADR-202609-025-delivery-management-framework.md)
- 姊妹能力：[RACI 引擎](EXP-20260915-022-dms-raci-capability.md) / [状态机引擎](EXP-20260915-021-dms-state-machine-capability.md)
