# 持久化适配组件设计

> L2 基础设施层 · 持久化适配（SQLite + Repository 模式 + 版本化迁移）

## 1. 定位

| 维度 | 值 |
|---|---|
| 层级 | L2 基础设施层 |
| 组件类 | 持久化适配 |
| 状态 | ✅ 已建设 (2026-08-23) — 基础版 |
| ADR | ADR-202608-006 (persistence-adapter, accepted) |
| 验证 | smoke test |

## 2. 设计约束

1. **SQLite 优先**：默认使用 SQLite（文件型、零配置），未来可切换 PostgreSQL。
2. **WAL 模式**：启用 Write-Ahead Logging，提升并发读写性能。
3. **外键约束**：`PRAGMA foreign_keys=ON`，保证引用完整性。
4. **线程安全**：每个线程独立连接（`threading.local()` 懒初始化），避免连接共享冲突。
5. **Repository 模式**：业务层通过 Repository 基类访问数据，子类只需定义 `table_name`。
6. **版本化迁移**：Schema 变更通过版本号 + SQL 脚本管理，按顺序幂等执行。
7. **最小起步**：初始 schema 仅 `users` + `config` 两张业务表 + `_schema_version` 元数据表。

## 3. 架构

```
┌─────────────────────────────────────────────────────────────┐
│                   L3 / L4 (业务层)                           │
│           UserRepository / ConfigRepository / ...            │
├─────────────────────────────────────────────────────────────┤
│                Repository 基类 (repository.py)                │
│     get / list / create / update / delete / count            │
├─────────────────────────────────────────────────────────────┤
│               连接管理 (connection.py)                        │
│     get_connection / close / init_schema                     │
│     WAL + foreign_keys + thread-local                        │
├─────────────────────────────────────────────────────────────┤
│               迁移引擎 (migration.py)                        │
│     run_migrations / get_current_version / apply_migration   │
├─────────────────────────────────────────────────────────────┤
│               Schema 脚本 (schemas/v001_init.py)              │
│     MIGRATION 常量（SQL 文本）                                │
├─────────────────────────────────────────────────────────────┤
│                   SQLite (platform.db)                       │
│     ~/.openclaw/data/platform.db                             │
└─────────────────────────────────────────────────────────────┘
```

### 3.1 模块职责

| 模块 | 文件 | 职责 |
|---|---|---|
| connection | `connection.py` | 数据库连接管理：线程安全懒初始化、WAL、外键、schema 初始化入口 |
| repository | `repository.py` | Repository 基类：通用 CRUD 操作，子类只需定义 `table_name` |
| migration | `migration.py` | Schema 迁移引擎：版本发现、顺序执行、幂等设计 |
| schemas | `schemas/v001_init.py` | 初始 schema 脚本：users + config 表 |

### 3.2 数据流

```
业务代码
  ↓  UserRepository.create(id="u1", name="Rex")
Repository 基类
  ↓  INSERT INTO users (id, name) VALUES (?, ?)
connection.get_connection()
  ↓  sqlite3.connect("~/.openclaw/data/platform.db")
SQLite (WAL mode)
```

## 4. 核心 API

### 4.1 连接管理

```python
from persistence.connection import get_connection, close, init_schema

# 获取当前线程的数据库连接（懒初始化）
conn = get_connection()

# 初始化 schema（执行所有待执行的迁移）
init_schema()

# 关闭当前线程的连接
close()
```

### 4.2 Repository 基类

```python
from persistence.repository import Repository

class UserRepository(Repository):
    table_name = "users"

repo = UserRepository()

# CRUD
user = repo.create(id="u1", name="Rex", email="rex@example.com")
found = repo.get("u1")
users = repo.list()
users = repo.list(where="name = ?", params=("Rex",))
updated = repo.update("u1", name="Rex Updated")
deleted = repo.delete("u1")
count = repo.count()
```

### 4.3 迁移引擎

```bash
# 迁移自动执行：init_schema() → run_migrations()
# 发现 schemas/v*.py → 按版本号排序 → 跳过已执行 → 顺序执行
```

迁移文件命名规范：`v{version}_{description}.py`（如 `v001_init.py`），每个文件导出 `MIGRATION` 常量（SQL 文本）。

## 5. 存储格式

| 路径 | 格式 | 说明 |
|---|---|---|
| `~/.openclaw/data/platform.db` | SQLite | 主数据库文件 |
| `~/.openclaw/data/platform.db-wal` | SQLite WAL | Write-Ahead Log |
| `~/.openclaw/data/platform.db-shm` | SQLite | 共享内存文件 |

### 5.1 初始 Schema（v001）

```sql
-- 用户表
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT
);

-- 配置表（系统级 KV）
CREATE TABLE IF NOT EXISTS config (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_config_key ON config(key);
```

### 5.2 版本元数据表

```sql
CREATE TABLE IF NOT EXISTS _schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
)
```

## 6. 关键设计细节

### 6.1 线程安全

- 使用 `threading.local()` 存储每线程独立的 `sqlite3.Connection`
- `get_connection()` 懒初始化：首次调用时创建连接 + 设置 WAL + 外键
- `close()` 关闭当前线程连接并清理

### 6.2 迁移幂等设计

- 所有 SQL 使用 `CREATE TABLE IF NOT EXISTS` / `CREATE INDEX IF NOT EXISTS`
- `_schema_version` 表记录已执行版本，重复执行 `init_schema()` 不会重复应用
- 版本号严格递增，按排序顺序执行

### 6.3 Repository 模式

- 基类提供通用 CRUD：`get` / `list` / `create` / `update` / `delete` / `count`
- 子类只需定义 `table_name` 即可获得完整数据访问能力
- `list()` 支持可选 `where` 条件 + 参数化查询（防 SQL 注入）
- `create()` 返回插入的数据 dict（不含数据库生成的字段）

## 7. 依赖

| 依赖 | 类型 | 说明 |
|---|---|---|
| Python 3.14+ sqlite3 | 标准库 | 内置 SQLite 支持 |
| pathlib | 标准库 | 数据目录路径管理 |

零外部依赖。

## 8. 演进方向

| 方向 | 优先级 | 触发条件 |
|---|---|---|
| PostgreSQL 支持 | 低 | 需要多写并发或网络访问时 |
| 连接池 | 低 | 多线程高并发场景 |
| ORM 集成（SQLAlchemy） | 低 | 业务实体复杂度超过手工 SQL |
| 软删除 | 中 | 业务需要保留删除记录时 |
| 审计日志 | 低 | 需要追踪数据变更历史时 |
| 数据库加密 | 低 | 存储敏感数据时 |

## 9. 验证

- **smoke test**：`tests/test_smoke.py` — 验证目录结构和 Python 文件存在
- **手动验证**：
  ```python
  from persistence import init_schema, Repository
  init_schema()
  class UserRepo(Repository):
      table_name = "users"
  repo = UserRepo()
  repo.create(id="test", name="Test")
  assert repo.get("test")["name"] == "Test"
  ```

## 10. 变更记录

| 日期 | 变更 |
|---|---|
| 2026-08-23 | 首版：connection + repository + migration + v001_init schema |
| 2026-08-23 | ADR-202608-006 accepted |
