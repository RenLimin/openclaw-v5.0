# delivery-management-framework — 操作手册 (OPERATIONS)

> 版本: v1.0 · 日期: 2026-09-28

## 1. 安装与启动

### 1.1 环境依赖

- Python 3.12+

### 1.2 安装步骤

```bash
cd L3-business/components/delivery-management-framework
# 纯逻辑层，无需额外依赖
```

### 1.3 启动命令

```bash
python3 dms_cli.py --help
```

### 1.4 健康检查

```bash
python3 dms_cli.py --version
```

## 2. 操作指南

### 2.1 场景一：创建项目

```bash
python3 dms_cli.py project create --name "项目名"
```

### 2.2 场景二：管理成员

```bash
python3 dms_cli.py member add --project "项目名" --user "成员"
```

### 2.3 场景三：跟踪工作项

```bash
python3 dms_cli.py work_item list --project "项目名"
python3 dms_cli.py work_item update --id "ID" --status "in_progress"
```

## 3. 配置说明

无外部配置。

## 4. 故障排查

### 4.1 CLI 命令不存在

- **症状**: 命令未识别
- **原因**: 命令未注册
- **解决**: 检查 `cli/` 目录下的命令定义

### 4.2 状态流转错误

- **症状**: 状态不变化
- **原因**: 转移规则未定义
- **解决**: 检查状态机配置

## 5. FAQ

**Q1: 如何添加新模块？**
A: 在对应目录下创建新模块，ModuleRegistry 自动发现

**Q2: 如何扩展状态机？**
A: 在状态机配置中添加新状态和转移规则

## 6. 附录

### 6.1 CLI 命令清单

- project create/list/update
- member add/remove
- work_item list/update
- stakeholder list
- responsibility assign
- change_log list
- raci query
- state list
