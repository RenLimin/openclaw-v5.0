# 持久化适配 (L2 基础设施组件)

> 本文档是 [系统架构](../00-system-architecture.md) 的 L2 组件设计文档。
> 决策记录: [ADR-202608-006](./ADR-202608-006-persistence-adapter.md)

## 1. 定位

**层级**: L2 基础设施层
**类型**: 基础能力 (Foundation)
**状态**: ✅ 已上线 (2026-08-21) — ADR-006 已实现,persistence/ 包 + SQLite + Repository 落地

持久化适配为 L3/L4 提供**结构化数据访问能力**——统一的数据库连接、schema 管理、迁移、查询接口。

## 2. 问题定义

### 2.1 现状

| 层级 | 当前持久化能力 | 局限 |
|---|---|---|
| L1 OpenClaw | MEMORY.md + memory/ 目录 | 非结构化，不适合业务数据 |
| L2 已建组件 | 无 | — |
| L3/L4 未来 | 无 | 没有统一的数据访问层 |

### 2.2 核心矛盾

当 L3 开始建设时（如 user/order/payment 维度），每个维度都需要：
- 数据存储
- Schema 定义
- 迁移管理
- 查询接口

如果每个维度自己选数据库、自己管 schema，会导致：
- 技术栈碎片化（一个用 SQLite、一个用 PostgreSQL、一个用 JSON 文件）
- 运维复杂度 N 倍
- 跨维度查询几乎不可能

### 2.3 设计目标

1. **统一接口**：L3/L4 通过统一接口访问数据，不直接操作数据库
2. **单文件优先**：初期用 SQLite（零运维、单文件、可移植）
3. **Schema 版本化**：migration 有标准流程
4. **可演进**：未来可平滑迁移到 PostgreSQL（不破坏 L3/L4 代码）

## 3. 架构设计

### 3.1 分层模型

```
┌─────────────────────────────────────────────────────────────┐
│  L3 / L4 (业务层)                                            │
│     业务逻辑通过 Repository 接口访问数据                       │
├─────────────────────────────────────────────────────────────┤
│  Repository 层                                               │
│     业务语义的查询接口 (UserRepository, OrderRepository)      │
├─────────────────────────────────────────────────────────────┤
│  ★ 持久化适配 (本组件)                                       │
│     连接管理 / Schema 迁移 / 事务 / 查询构建器               │
├─────────────────────────────────────────────────────────────┤
│  存储引擎                                                     │
│     SQLite (当前) → PostgreSQL (未来)                        │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 组件结构

```
persistence/
├── __init__.py           # 包入口
├── connection.py         # 数据库连接管理 (工厂模式)
├── migration.py          # Schema 迁移引擎
├── repository.py         # Repository 基类
├── query.py              # 查询构建器 (轻量)
├── models.py             # 数据模型基类 (可选 ORM)
└── schemas/              # Schema 定义
   ├── v001_init.py       # 初始 schema
   └── v002_xxx.py        # 后续迁移
```

### 3.3 存储引擎选择

| 引擎 | 适用场景 | 当前选择 |
|---|---|---|
| **SQLite** | 单机、中小规模、零运维、单文件可移植 | ✅ **当前** |
| PostgreSQL | 多用户并发、大规模、网络访问 | ⏸️ 未来 |
| DuckDB | 分析型查询、OLAP | ⏸️ 未来（如果需要） |
| JSON 文件 | 极小数据、配置 | 不适合业务数据 |

**SQLite 模式决策**：
- 默认：单文件 `~/.openclaw/data/platform.db`
- WAL 模式：启用（读写并发更好，接受额外的 `-wal`/`-shm` 文件）
- 备份：单文件直接复制即可

### 3.4 连接管理

```python
# connection.py 核心接口
class Database:
    """数据库连接工厂。"""
    
    @staticmethod
    def get_connection() -> sqlite3.Connection:
        """获取线程安全的数据库连接。"""
    
    @staticmethod
    def init_schema():
        """初始化/迁移 schema。"""
    
    @staticmethod
    def backup(target: Path):
        """热备份。"""
```

**设计要点**：
- 单例连接（SQLite 单写多读，不需要连接池）
- 自动 `PRAGMA foreign_keys = ON`
- WAL 模式启用
- 连接路径可配置（默认 `~/.openclaw/data/platform.db`）

### 3.5 Schema 迁移

采用**版本号 + 迁移脚本**模式（类似 Alembic 但极简）：

```python
# schemas/v001_init.py
MIGRATION = """
CREATE TABLE IF NOT EXISTS _schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""

# schemas/v002_add_email.py
MIGRATION = """
ALTER TABLE users ADD COLUMN email TEXT;
"""
```

**迁移规则**：
1. 每次迁移是一个 Python 模块，包含 `MIGRATION` SQL 字符串
2. 按版本号顺序执行
3. `_schema_version` 表记录已执行的迁移
4. 迁移幂等（`IF NOT EXISTS` + 版本检查）
5. 迁移不可逆（不写 down migration，未来需要时再加）

### 3.6 Repository 模式

```python
# repository.py
class Repository:
    """业务仓储基类。"""
    
    table_name: str
    model_class: type
    
    def get(self, id: str) -> Optional[Model]:
    def list(self, **filters) -> List[Model]:
    def create(self, **data) -> Model:
    def update(self, id: str, **data) -> Model:
    def delete(self, id: str) -> bool:
```

**设计要点**：
- L3 维度继承 `Repository`，获得 CRUD 能力
- 不强制 ORM（初期用 raw SQL + dataclass）
- 未来可引入 SQLAlchemy Core（不破坏接口）

### 3.7 事务管理

```python
# 上下文管理器
with db.transaction() as tx:
    users_repo.create(id="u1", name="Rex")
    orders_repo.create(id="o1", user_id="u1")
    # 自动 commit / rollback
```

## 4. 技术选型

### 4.1 Python 持久化方案对比

| 方案 | 依赖 | 适合 | 评估 |
|---|---|---|---|
| **sqlite3 (stdlib)** | 零 | 简单查询、中小规模 | ✅ **当前** |
| SQLAlchemy Core | 中 | 复杂查询、多引擎 | ⏸️ 未来 |
| SQLAlchemy ORM | 中 | 复杂对象映射 | ⏸️ 未来 |
| Peewee | 轻量 | 中小项目 ORM | 可选 |
| PonyORM | 中 | 强 ORM | 过重 |
| 纯 JSON 文件 | 零 | 极小数据 | ❌ 不适合业务 |

### 4.2 当前决策：sqlite3 (stdlib) + 自封装

**理由**：
1. **零依赖**：Python 内置 `sqlite3`，不需要 `pip install`
2. **单文件可移植**：与"跨系统移植"目标一致
3. **足够**：中小规模业务数据完全够用
4. **渐进式**：未来可引入 SQLAlchemy Core（不破坏 Repository 接口）

### 4.3 演进路径

```
阶段 1 (当前): sqlite3 stdlib + 自封装 Repository
  ↓ 当查询复杂度增加
阶段 2: SQLAlchemy Core (不换接口, 只换底层)
  ↓ 当需要多用户并发 / 网络访问
阶段 3: PostgreSQL (通过 SQLAlchemy 引擎切换)
  ↓ 当需要分析型查询
阶段 4: DuckDB 用于分析 (与 PostgreSQL 并存)
```

## 5. 与其他组件的关系

```
持久化适配 (本组件)
  ↑ 被依赖
  ├── L3 通用业务 (user/order/payment/...)
  ├── L4 专有业务 (继承 L3, 使用 Repository)
  └── L2 可观测性适配 (数据库操作日志)
  
  ↓ 依赖
  ├── L1 OpenClaw (无直接依赖, 纯 Python)
  └── L2 凭据管理 (如果未来 DB 需要密码)
```

## 6. 实施计划

### 阶段 1: 设计 + ADR (当前)
- [ ] ADR-006 锁定设计决策
- [ ] 验证：手动创建 SQLite 数据库 + 测试迁移流程

### 阶段 2: 核心实现
- [ ] connection.py (连接管理)
- [ ] migration.py (迁移引擎)
- [ ] repository.py (Repository 基类)
- [ ] 测试：CRUD + 迁移

### 阶段 3: 集成
- [ ] L3 第一个维度接入 (如 UserRepository)
- [ ] 可观测性适配记录 DB 操作日志

## 7. 参考

- **Python sqlite3**: https://docs.python.org/3/library/sqlite3.html
- **SQLite WAL mode**: https://www.sqlite.org/wal.html
- **Alembic**: https://alembic.sqlalchemy.org (迁移引擎参考)
- **Repository Pattern**: Martin Fowler, "Patterns of Enterprise Application Architecture"
