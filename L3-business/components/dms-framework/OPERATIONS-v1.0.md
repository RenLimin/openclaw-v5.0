# dms-framework — 操作手册 (OPERATIONS)

> 版本: v1.0 · 日期: 2026-09-28

## 1. 安装与启动

### 1.1 环境依赖

- Python 3.12+
- Jinja2: `pip install jinja2`

### 1.2 安装步骤

```bash
cd L3-business/components/dms-framework
pip install jinja2
```

### 1.3 启动命令

```bash
# CLI 模式
python3 dms.py --help

# Web UI 模式
python3 dms.py webui start
```

### 1.4 健康检查

```bash
# 验证模块注册
python3 dms.py module list

# 验证状态机
python3 dms.py state list
```

## 2. 操作指南

### 2.1 场景一：创建项目

```bash
python3 dms.py project create --name "项目名"
python3 dms.py member add --project "项目名" --user "成员"
python3 dms.py milestone create --project "项目名" --name "里程碑"
```

### 2.2 场景二：跟踪进度

```bash
python3 dms.py work_item list --project "项目名"
python3 dms.py work_item update --id "ID" --status "in_progress"
```

### 2.3 场景三：查看仪表板

```bash
python3 dms.py webui start
# 浏览器访问对应端口
```

## 3. 配置说明

### 3.1 配置文件

- `config.py`: 全局配置
- `migrations/`: 数据库迁移脚本

### 3.2 默认值

- 存储: SQLite
- 端口: 默认配置
- 租户: 单租户模式

## 4. 故障排查

### 4.1 模块注册失败

- **症状**: 模块未显示在列表中
- **原因**: 模块目录结构不正确
- **解决**: 检查模块是否有 `__init__.py` 和 `MANIFEST.yml`

### 4.2 状态流转错误

- **症状**: 状态不变化
- **原因**: 转移规则未定义
- **解决**: 检查状态机配置

### 4.3 事件订阅者未收到通知

- **症状**: 事件发布后无响应
- **原因**: 订阅者未注册或事件名不匹配
- **解决**: 检查订阅者注册代码

## 5. FAQ

**Q1: 如何添加新业务模块？**
A: 在 `modules/` 下创建子目录，定义 `MANIFEST.yml`，ModuleRegistry 自动发现

**Q2: 如何扩展状态机？**
A: 在状态机配置中添加新状态和转移规则

**Q3: 支持多租户吗？**
A: 支持，通过 TenantContext 实现租户隔离

## 6. 附录

### 6.1 CLI 命令清单

- `project create/list/update`
- `member add/remove`
- `milestone create/list`
- `work_item list/update`
- `module list/discover`
- `state list`
- `raci assign/query`
- `webui start`
- `migrate/diff/version`
