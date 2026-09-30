# DMS-Framework — 操作手册（OPERATIONS）

> 版本：v1.0（2026-09-29）
> 层级：L3 通用业务层
> 状态：⏳ 待 Rex 审核

---

## 1. 安装与启动

### 1.1 环境依赖

| 依赖 | 最低版本 | 用途 | 安装命令 |
|------|---------|------|---------|
| Python | 3.10+ | 运行时 | `brew install python` |
| FastAPI | 0.100+ | REST API | `pip install fastapi` |
| Uvicorn | 0.20+ | ASGI 服务器 | `pip install uvicorn` |
| Pydantic | 2.0+ | 数据校验 | `pip install pydantic` |
| Jinja2 | 3.0+ | Web 模板 | `pip install jinja2` |
| python-jose | 3.3+ | JWT 认证 | `pip install python-jose[cryptography]` |
| passlib | 1.7+ | 密码哈希 | `pip install passlib[bcrypt]` |

一键安装：
```bash
cd ~/.openclaw/workspace/L3-business/components/dms-framework
pip install fastapi uvicorn pydantic jinja2 python-jose[cryptography] passlib[bcrypt]
```

### 1.2 安装步骤

```bash
# 1. 进入组件目录
cd ~/.openclaw/workspace/L3-business/components/dms-framework

# 2. 安装依赖
pip install fastapi uvicorn pydantic jinja2 python-jose passlib

# 3. 初始化数据库（一次性）
python3 dms.py init --db delivery.db

# 4. 验证安装
python3 dms.py module list
```

### 1.3 启动命令

```bash
# ── CLI 模式 ──
python3 dms.py <module> <command> [options]

# ── API 模式 ──
python3 dms_api.py serve --host 127.0.0.1 --port 8000

# ── Web UI 模式 ──
python3 dms_api.py serve --host 127.0.0.1 --port 8000
# 浏览器打开 http://localhost:8000

# ── 健康检查 ──
curl -s http://127.0.0.1:8000/health | python3 -m json.tool
# 预期：{"status": "ok", "modules": 15, "version": "1.0.0"}
```

---

## 2. 操作指南

### 2.1 场景一：模块管理

> 作为开发者，我想查看已注册的所有模块。

```bash
# 列出所有模块
python3 dms.py module list

# 预期输出：
# 模块              版本       描述
# ------------------------------------------------------------
# budget           1.0.0     预算管理
# communication    1.0.0     沟通管理
# contract         1.0.0     合同管理
# decision         1.0.0     决策记录
# deliverable      1.0.0     交付物管理
# issue            1.0.0     问题管理
# milestone        1.0.0     里程碑管理
# project          1.0.0     项目管理
# quality          1.0.0     质量管理
# raci             1.0.0     RACI 职责管理
# resource         1.0.0     资源管理
# risk             1.0.0     风险管理
# sla              1.0.0     SLA 管理
# task             1.0.0     任务管理
# tenant           1.0.0     租户管理
```

### 2.2 场景二：Schema 迁移

> 作为运维，我想查看和执行数据库迁移。

```bash
# 查看待执行迁移
python3 dms.py schema diff --db delivery.db

# 预期输出：
# 待执行迁移: 1.0.0 — Initial schema

# 执行迁移
python3 dms.py schema migrate --db delivery.db

# 预期输出：
# Current version: 0
# Migrated to: 1.0.0
```

### 2.3 场景三：事件总线监控

> 作为管理员，我想查看事件总线状态。

```bash
# 查看事件统计
python3 dms.py event stats --db delivery.db

# 预期输出：
# 📊 事件总线统计
#    订阅模式数: 0（模块未初始化时）
#    订阅者总数: 0
#    历史事件数: 0
```

### 2.4 场景四：工作流方案切换

> 作为项目管理员，我想切换项目的工作流方案。

```bash
# 列出所有工作流方案
python3 dms.py workflow list --db delivery.db

# 预期输出：
# Active scheme: default
#   default           Default workflow scheme
#     task             → task_flow
#     milestone        → milestone_flow
#     deliverable      → deliverable_flow
#   agile             Agile workflow scheme
#   waterfall         Waterfall workflow scheme

# 切换到敏捷方案
python3 dms.py workflow set --name agile --db delivery.db

# 预期输出：Switched to: agile

# 解析映射
python3 dms.py workflow resolve --entity-type task --db delivery.db

# 预期输出：task → agile_task_flow
```

### 2.5 场景五：API 认证

> 作为用户，我想登录并获取访问令牌。

```bash
# 登录获取 token
curl -s -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin123"}' | python3 -m json.tool

# 预期输出：
# {
#   "access_token": "eyJ...",
#   "token_type": "bearer",
#   "user_id": "admin",
#   "tenant_id": "system",
#   "roles": ["admin"]
# }

# 使用 token 访问受保护接口
curl -s http://127.0.0.1:8000/api/v1/projects \
  -H "Authorization: Bearer eyJ..." | python3 -m json.tool

# 查看当前用户
curl -s http://127.0.0.1:8000/api/v1/auth/me \
  -H "Authorization: Bearer eyJ..." | python3 -m json.tool
```

### 2.6 场景六：租户管理

> 作为管理员，我想创建和管理租户。

```bash
# 创建租户
curl -s -X POST http://127.0.0.1:8000/api/v1/tenants \
  -H "Authorization: Bearer eyJ..." \
  -H "Content-Type: application/json" \
  -d '{"name": "租户A", "tier": "business"}' | python3 -m json.tool

# 预期输出：{"id": "uuid", "name": "租户A", "tier": "business", ...}

# 列出租户
curl -s http://127.0.0.1:8000/api/v1/tenants \
  -H "Authorization: Bearer eyJ..." | python3 -m json.tool

# 获取租户详情
curl -s http://127.0.0.1:8000/api/v1/tenants/{tenant_id} \
  -H "Authorization: Bearer eyJ..." | python3 -m json.tool

# 删除租户
curl -s -X DELETE http://127.0.0.1:8000/api/v1/tenants/{tenant_id} \
  -H "Authorization: Bearer eyJ..." | python3 -m json.tool
```

### 2.7 场景七：模块 CRUD

> 作为用户，我想通过 API 管理模块数据。

```bash
# 创建项目
curl -s -X POST http://127.0.0.1:8000/api/v1/project \
  -H "Authorization: Bearer eyJ..." \
  -H "Content-Type: application/json" \
  -d '{"name": "项目A", "description": "描述", "status": "active"}' | python3 -m json.tool

# 列出项目（支持搜索/分页/排序）
curl -s "http://127.0.0.1:8000/api/v1/project?search=项目&page=1&page_size=10" \
  -H "Authorization: Bearer eyJ..." | python3 -m json.tool

# 获取项目详情
curl -s http://127.0.0.1:8000/api/v1/project/{project_id} \
  -H "Authorization: Bearer eyJ..." | python3 -m json.tool

# 更新项目
curl -s -X PUT http://127.0.0.1:8000/api/v1/project/{project_id} \
  -H "Authorization: Bearer eyJ..." \
  -H "Content-Type: application/json" \
  -d '{"name": "项目A-更新"}' | python3 -m json.tool

# 删除项目
curl -s -X DELETE http://127.0.0.1:8000/api/v1/project/{project_id} \
  -H "Authorization: Bearer eyJ..." | python3 -m json.tool

# 执行状态迁移
curl -s -X POST http://127.0.0.1:8000/api/v1/task/{task_id}/actions/submit \
  -H "Authorization: Bearer eyJ..." | python3 -m json.tool

# 批量创建
curl -s -X POST http://127.0.0.1:8000/api/v1/project/batch \
  -H "Authorization: Bearer eyJ..." \
  -H "Content-Type: application/json" \
  -d '{"items": [{"name": "P1"}, {"name": "P2"}]}' | python3 -m json.tool

# 批量删除
curl -s -X DELETE http://127.0.0.1:8000/api/v1/project/batch \
  -H "Authorization: Bearer eyJ..." \
  -H "Content-Type: application/json" \
  -d '{"ids": ["id1", "id2"]}' | python3 -m json.tool
```

---

## 3. 配置说明

### 3.1 配置文件清单

| 文件 | 用途 | 必需 |
|------|------|------|
| `dms.json` | 应用配置（JSON） | ❌ 使用默认值 |
| `config/dms.json` | 备选配置路径 | ❌ |
| `/etc/dms/config.json` | 系统级配置 | ❌ |

### 3.2 环境变量

| 变量 | 说明 | 示例 |
|------|------|------|
| `DMS_JWT_SECRET` | JWT 签名密钥 | `my-secret-key` |
| `DMS_JWT_EXPIRE_HOURS` | Token 过期小时数 | `24` |
| `DMS_API_HOST` | API 监听地址 | `127.0.0.1` |
| `DMS_API_PORT` | API 监听端口 | `8000` |
| `DMS_DEFAULT_TENANT` | 默认租户 | `system` |
| `DMS_TENANT_ISOLATION` | 隔离模式 | `shared` |
| `DMS_WEBUI_ENABLED` | 启用 Web UI | `true` |
| `DMS_MODULES_ENABLED` | 启用模块 | `*` 或 `project,task` |
| `DMS_DB_URL` | 数据库 URL | `sqlite:///delivery.db` |
| `DMS_LOG_LEVEL` | 日志级别 | `INFO` |

### 3.3 配置优先级

```
环境变量 > 配置文件 > 默认值
```

---

## 4. 故障排查

### 4.1 服务无法启动

| 症状 | 原因 | 解决方案 |
|------|------|---------|
| `ModuleNotFoundError: fastapi` | 缺依赖 | `pip install fastapi uvicorn` |
| `ModuleNotFoundError: jose` | 缺 JWT 依赖 | `pip install python-jose[cryptography]` |
| `Address already in use` | 端口被占用 | `lsof -i :8000` → kill 占用进程 |
| `PermissionError: delivery.db` | 数据库文件权限 | `chmod 644 delivery.db` |

### 4.2 数据库错误

| 症状 | 原因 | 解决方案 |
|------|------|---------|
| `sqlite3.OperationalError: no such table` | 未初始化 | `python3 dms.py init` |
| `sqlite3.IntegrityError` | 数据冲突 | 检查 tenant_id 唯一性 |
| `Migration version X already registered` | 重复迁移 | 检查迁移注册代码 |

### 4.3 API 错误

| 症状 | 原因 | 解决方案 |
|------|------|---------|
| 401 Unauthorized | Token 失效或缺失 | 重新登录获取 token |
| 403 Forbidden | 权限不足 | 检查用户角色 |
| 404 Not Found | 资源不存在 | 检查 ID 是否正确 |
| 501 Not Implemented | 模块未实现该操作 | 检查模块方法名约定 |
| 400 Bad Request | 参数错误 | 检查请求体格式 |

### 4.4 CLI 错误

| 症状 | 原因 | 解决方案 |
|------|------|---------|
| `No handler for command` | 命令未注册 | 检查模块 manifest.commands |
| `Module not found` | 模块未注册 | 检查 build_registry() |
| `Circular dependency` | 循环依赖 | 检查模块 dependencies 声明 |

### 4.5 日志位置

| 日志 | 路径 | 说明 |
|------|------|------|
| 应用日志 | `stdout` | 默认输出到控制台 |
| 数据库日志 | `delivery.db` | SQLite 文件 |

---

## 5. FAQ

### Q1: 如何添加新模块？

```python
# 1. 在 modules/ 下创建新目录
mkdir modules/my_module

# 2. 定义模块（__init__.py）
from core.module import BaseModule, ModuleManifest, CommandDef

manifest = ModuleManifest(
    name="my_module",
    version="1.0.0",
    description="我的模块",
    dependencies=[],  # 依赖其他模块时声明
    commands=[
        CommandDef(name="my_module hello", handler=lambda args, ctx: print("Hello!")),
    ],
    tables=["my_table"],
)

class MyModule(BaseModule):
    def initialize(self, db, config, container):
        # 建表、注册事件等
        pass

def _factory(manifest):
    return MyModule(manifest)

# 3. 在 dms.py 的 build_registry() 中注册
from modules.my_module import manifest, _factory
registry.register(manifest, _factory)
```

### Q2: 如何扩展状态机？

```python
from core.state_machine import StateMachine, State, Transition

machine = StateMachine("my_flow")
machine.add_state(State("draft", "todo", is_start=True))
machine.add_state(State("review", "in_progress"))
machine.add_state(State("done", "done", is_terminal=True))
machine.add_transition(Transition("submit", "draft", "review"))
machine.add_transition(Transition("approve", "review", "done"))

# 注册到引擎
engine.register("my_flow", machine)
```

### Q3: 如何添加事件监听？

```python
def on_project_created(event):
    print(f"Project created: {event.payload}")

# 订阅
event_bus.subscribe("project.created", on_project_created)

# 通配符订阅
event_bus.subscribe("project.*", on_project_event)
```

### Q4: 如何切换数据库到 PostgreSQL？

```python
# 修改 Database 类中的连接逻辑
# 或使用环境变量
export DMS_DB_URL="postgresql://user:pass@localhost/dms"
```

### Q5: 如何禁用 Web UI？

```bash
export DMS_WEBUI_ENABLED=false
```

---

## 6. 附录

### 6.1 API 接口清单

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |
| GET | `/api/v1` | API 根（重定向到文档） |
| GET | `/docs` | Swagger 文档 |
| GET | `/redoc` | ReDoc 文档 |
| POST | `/api/v1/auth/login` | 用户登录 |
| GET | `/api/v1/auth/me` | 当前用户 |
| POST | `/api/v1/auth/api-keys` | 创建 API Key |
| GET | `/api/v1/modules` | 列出模块 |
| GET/POST | `/api/v1/{module}` | 模块 CRUD |
| GET/PUT/DELETE | `/api/v1/{module}/{id}` | 模块实例操作 |
| POST | `/api/v1/{module}/{id}/actions/{action}` | 状态迁移 |
| POST/DELETE | `/api/v1/{module}/batch` | 批量操作 |
| GET/POST | `/api/v1/tenants` | 租户管理 |
| GET/DELETE | `/api/v1/tenants/{id}` | 租户详情/删除 |

### 6.2 CLI 命令清单

| 命令 | 说明 |
|------|------|
| `dms init` | 初始化框架 + 数据库 |
| `dms module list` | 列出已注册模块 |
| `dms schema diff` | 查看待执行迁移 |
| `dms schema migrate` | 执行数据库迁移 |
| `dms event stats` | 查看事件总线统计 |
| `dms workflow list` | 列出工作流方案 |
| `dms workflow set --name <name>` | 切换工作流方案 |
| `dms workflow resolve --entity-type <type>` | 解析实体映射 |
| `dms <module> <command>` | 模块业务命令 |

### 6.3 模块清单

| 模块 | 表名 | 说明 |
|------|------|------|
| tenant | tenants | 租户管理 |
| project | projects | 项目管理 |
| milestone | milestones | 里程碑 |
| deliverable | deliverables | 交付物 |
| risk | risks | 风险 |
| raci | raci_assignments | RACI 职责 |
| quality | quality_checks | 质量 |
| resource | resources | 资源 |
| budget | budgets | 预算 |
| communication | communications | 沟通 |
| contract | contracts | 合同 |
| sla | sla_items | SLA |
| task | tasks | 任务 |
| issue | issues | 问题 |
| decision | decisions | 决策 |

### 6.4 默认用户

| 用户名 | 密码 | 角色 | 租户 |
|--------|------|------|------|
| admin | admin123 | admin | system |

> ⚠️ 生产环境必须修改默认密码！

### 6.5 版本历史

| 版本 | 日期 | 说明 |
|------|------|------|
| v1.0.0 | 2026-09-29 | 初版框架（五件套文档配套） |
