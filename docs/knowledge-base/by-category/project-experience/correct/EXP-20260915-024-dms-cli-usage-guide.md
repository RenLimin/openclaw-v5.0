---
title: "DMS CLI 使用指南"
id: EXP-20260915-024
date: 2026-09-15
type: correct
project: delivery-management-framework
category: project-experience
layers: [L3]
phase: manage
tags: [dms, cli, usage-guide, command-line, module-registration]
---

# DMS CLI 使用指南

## 概述
DMS 框架提供统一的 CLI 入口 `dms`，基于 `CLIFramework` 构建，支持命令自动注册和模块热插拔。所有模块的命令都通过同一个入口访问。

## 快速开始

### 查看帮助
```bash
cd L3-business/components/delivery-management-framework
python3 dms_cli.py --help
```

输出示例：
```
dms — 交付管理框架 CLI

可用命令:
  project   — 项目管理
  workitem  — 工作项管理
  ...

用法:
  dms <module> <command> [options]
```

### 查看模块命令帮助
```bash
python3 dms_cli.py project --help
```

## CLI 架构

### CLIFramework 核心
`cli/cli.py` 中的 `CLIFramework` 类是 CLI 的骨架：

```
CLIFramework
  ├─ register_command(CommandDef)   # 注册命令
  ├─ run(args)                      # 运行 CLI
  └─ print_help()                   # 打印帮助
```

### 命令注册机制
命令通过 `CommandDef` 声明，由 `CLIFramework.register_command()` 注册：

```python
from cli.cli import CLIFramework, CommandDef

def create_project_handler(subparser):
    # 第一步：给 subparser 添加参数
    subparser.add_argument("--name", required=True, help="项目名称")
    subparser.add_argument("--owner", help="负责人")
    
    # 第二步：返回实际执行函数
    def execute(args):
        print(f"创建项目: {args.name}, 负责人: {args.owner}")
        return 0
    return execute
```

**注意 handler 的两段式设计**：
1. **参数定义阶段**：接收 subparser，添加参数定义
2. **执行阶段**：返回一个函数，接收解析后的 args 并执行

这种设计让命令声明和执行逻辑分离，框架可以先构建完整的 argparse 树，再根据解析结果调用对应执行函数。

### 与 ModuleManifest 集成
模块通过 `manifest.commands` 声明自己的命令列表，由框架统一注册到 CLI：

```python
manifest = ModuleManifest(
    name="project",
    version="1.0.0",
    commands=[
        CommandDef(
            name="project:create",
            handler=create_project_handler,
            description="创建项目"
        ),
        CommandDef(
            name="project:list",
            handler=list_projects_handler,
            description="列出所有项目"
        ),
    ]
)
```

注册模块后，`dms project:create` 命令自动可用——不需要改 CLI 代码。

## 常用操作

### 模块操作
```bash
# 列出所有已注册模块
python3 dms_cli.py module list

# 查看模块详情
python3 dms_cli.py module info <module_name>
```

### 项目操作
```bash
# 创建项目
python3 dms_cli.py project:create --name "新项目" --owner zhangsan

# 列出项目
python3 dms_cli.py project:list

# 查看项目详情
python3 dms_cli.py project:get <project_id>

# 删除项目
python3 dms_cli.py project:delete <project_id>
```

### 工作项操作
```bash
# 创建工作项
python3 dms_cli.py workitem:create --project-id <pid> --title "任务1"

# 列出工作项
python3 dms_cli.py workitem:list --project-id <pid>

# 状态流转
python3 dms_cli.py workitem:transition <id> --event start
```

### RACI 操作
```bash
# 分配职责
python3 dms_cli.py raci:assign --project-id <pid> --member user1 --capability scope_management --role R

# 查看矩阵
python3 dms_cli.py raci:matrix --project-id <pid>

# 检测冲突
python3 dms_cli.py raci:conflicts --project-id <pid>
```

> **注意**：具体可用命令取决于已注册的模块。用 `--help` 查看当前完整列表。

## 扩展新命令

### 第一步：定义命令处理函数
```python
def my_command_handler(subparser):
    """命令处理函数，接收 subparser，返回执行函数"""
    subparser.add_argument("--id", required=True, help="资源 ID")
    subparser.add_argument("--name", help="名称")
    
    def execute(args):
        # 实际业务逻辑
        print(f"处理 {args.id}: {args.name}")
        return 0  # 返回 0 表示成功
    
    return execute
```

### 第二步：注册到 ModuleManifest
```python
from dataclasses import field
from registry.module_registry import ModuleManifest, CommandDef

manifest = ModuleManifest(
    name="my_module",
    version="1.0.0",
    commands=[
        CommandDef(
            name="my_module:do_something",
            handler=my_command_handler,
            description="做某件事"
        ),
    ]
)
```

### 第三步：注册模块
```python
from registry.module_registry import ModuleRegistry

registry = ModuleRegistry()
registry.register(manifest)
```

完成！命令自动出现在 CLI 帮助信息中。

## 命令命名约定

推荐格式：`<module>:<action>`，例如：

| 命令 | 说明 |
|------|------|
| `project:create` | 创建项目 |
| `project:list` | 列出项目 |
| `project:get` | 获取项目详情 |
| `project:delete` | 删除项目 |
| `workitem:transition` | 工作项状态流转 |
| `raci:matrix` | 查看 RACI 矩阵 |

好处：
- 一眼看出属于哪个模块
- 避免命名冲突
- 与模块名对齐，方便查找

## 编程式调用
不通过命令行，直接在代码中使用：

```python
from cli.cli import CLIFramework, CommandDef

cli = CLIFramework(prog="my-dms")

# 注册命令
cli.register_command(CommandDef(
    name="hello",
    handler=lambda sp: (lambda args: print("hello") or 0),
    description="Say hello"
))

# 运行
exit_code = cli.run(["hello"])
```

## 退出码约定

| 退出码 | 含义 |
|--------|------|
| 0 | 成功 |
| 1 | 通用错误（命令不存在、参数错误等） |
| 2 | 输入/参数错误 |
| 3+ | 业务自定义错误码 |

建议业务命令遵循此约定，方便脚本集成。

## 调试技巧

### 1. 查看所有已注册命令
```bash
python3 dms_cli.py --help
```

### 2. 详细日志
```bash
DMS_LOG_LEVEL=DEBUG python3 dms_cli.py project:create --name test
```

### 3. 编程式调试
```python
from cli.cli import CLIFramework

# 手动构建 CLI，检查注册了哪些命令
cli = CLIFramework()
# ... 注册各种命令 ...
print(list(cli._commands.keys()))  # 列出所有命令名
```

## 设计决策

### 为什么用两段式 handler（参数定义 + 执行函数）？
传统做法是 handler 直接接收 `args` 执行，但这样 argparse 的参数定义分散在各处，无法构建完整的帮助信息。两段式设计让框架：
1. 先调用所有 handler 的参数定义阶段，构建完整的 argparse 子命令树
2. 用户 `--help` 可以看到所有命令和参数
3. 解析后再调用执行阶段

这是借鉴了 click / typer 等现代 CLI 框架的设计思路，但用更轻量的方式实现。

### 为什么命令名用冒号分隔？
对比几种方案：

| 方案 | 例子 | 优缺点 |
|------|------|--------|
| 子命令嵌套 | `dms project create` | 直观，但实现复杂（多级子解析器） |
| 冒号分隔 | `dms project:create` | 简单，一眼看出模块，实现成本低 |
| 短横线 | `dms project-create` | 简单，但模块边界不清晰 |

选择冒号分隔：实现简单 + 模块边界清晰 + 跟 manifest 中的声明直接对应。

## 常见问题

### Q: 我注册了命令，但 --help 看不到？
- 确认模块已经被 `register()` 注册到 ModuleRegistry
- 确认 manifest.commands 里有对应的 CommandDef
- 确认命令名格式正确（`module:action`）

### Q: handler 什么时候被调用？
分两次：
1. **构建解析器时**：调用 handler(subparser) 来添加参数定义
2. **执行命令时**：handler 返回的函数被调用，传入解析后的 args

### Q: 命令参数冲突怎么办？
不同模块的命令参数不会冲突——每个命令有自己独立的 subparser。但如果两个命令同名，后注册的会覆盖先注册的（发出 warning）。建议严格遵循 `<module>:<action>` 命名约定。

## 扩展方向
- 交互式 REPL 模式（进入 dms shell，连续执行命令）
- 命令别名（alias）支持
- 管道模式（命令输出可被下一个命令消费）
- 配置文件（默认参数从配置文件读取）
- Shell 补全（bash / zsh 自动补全）
- 命令输出格式（text / json / table 切换）

## 参考
- 代码：`L3-business/components/delivery-management-framework/cli/cli.py`
- 入口：`L3-business/components/delivery-management-framework/dms_cli.py`
- 测试：`L3-business/components/delivery-management-framework/tests/test_cli.py`
- 相关 ADR：[ADR-025](../adr/ADR-202609-025-delivery-management-framework.md)
- 姊妹能力：[模块注册引擎](EXP-20260915-020-dms-module-registry-capability.md)
