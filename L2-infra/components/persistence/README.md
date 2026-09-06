# 持久化适配 (L2 基础设施组件)

> 本包为综合开放平台的 L2 持久化能力提供统一接口。
> 决策记录: [ADR-202608-006](../../docs/knowledge-base/by-category/project-experience/adr/ADR-202608-006-persistence-adapter.md) (accepted)

## 设计

```
L3 / L4 (业务层)
  ↓ 通过 Repository 接口
Repository 层 (业务语义 CRUD)
  ↓ 通过 Database 接口
持久化适配 (本包)
  ↓
SQLite (当前) → PostgreSQL (未来)
```

## 使用

```python
from persistence import Database, Repository

# 初始化
Database.init_schema()

# 定义 Repository
class UserRepository(Repository):
    table_name = "users"
    
    def row_to_model(self, row):
        return {"id": row["id"], "name": row["name"]}

# CRUD
repo = UserRepository()
user = repo.create(id="u1", name="Rex")
found = repo.get("u1")
users = repo.list()
repo.update("u1", name="Rex Updated")
repo.delete("u1")
```

## 文件

| 文件 | 作用 |
|---|---|
| `connection.py` | 数据库连接管理（单例、WAL、外键） |
| `migration.py` | Schema 迁移引擎 |
| `repository.py` | Repository 基类 |
| `schemas/v001_init.py` | 初始 schema |
