---
type: adr
id: ADR-202608-006
date: 2026-08-21
title: L2 持久化适配组件设计决策 — SQLite + Repository 模式 + 版本化迁移
status: accepted
supersedes: null
superseded_by: null
deciders: [Rex, Jerry]
layers: [L2, L3, L4]
tags: [persistence, sqlite, repository, migration, database]
supersedes: null
superseded_by: null
---

# [ADR-202608-006] L2 持久化适配组件设计决策

## 1. 状态
**accepted** — 2026-08-21 Rex 确认 · 已实现

## 2. 背景

综合开放平台进入 L2 最小可用建设阶段。下一个组件选型为**持久化适配**，因为：
- L3/L4 业务维度（user/order/payment/...）需要结构化数据存储
- 当前只有 MEMORY.md + memory/ 文件，不适合业务数据
- 每个维度自己选数据库会导致技术栈碎片化

**设计文档**: [components/persistence/DESIGN.md](./components/persistence/DESIGN.md)

## 3. 核心决策

### 决策 1: 存储引擎 — SQLite (当前)

| 候选 | 评估 | 原因 |
|---|---|---|
| **SQLite** | ✅ **采用** | 零运维、单文件可移植、Python 内置 |
| PostgreSQL | ⏸️ 未来 | 多用户并发时需要 |
| DuckDB | ⏸️ 未来 | 分析型查询时需要 |
| JSON 文件 | ❌ | 不适合业务数据 |

**理由**：
- Python 内置 `sqlite3`，零依赖
- 单文件 `~/.openclaw/data/platform.db`，可移植
- WAL 模式支持读写并发
- 备份 = 复制文件

### 决策 2: 访问模式 — Repository 模式

| 候选 | 评估 | 原因 |
|---|---|---|
| **Repository** | ✅ **采用** | 业务语义清晰、可测试、可替换底层 |
| 直接 SQL | ❌ | 重复代码、难以维护 |
| 全 ORM (SQLAlchemy ORM) | ⏸️ 未来 | 初期过重 |

**理由**：
- L3 维度继承 Repository 基类，获得 CRUD 能力
- 不强制 ORM（初期 raw SQL + dataclass）
- 未来可引入 SQLAlchemy Core（不破坏接口）

### 决策 3: Schema 管理 — 版本化迁移

| 候选 | 评估 | 原因 |
|---|---|---|
| **版本号 + 迁移脚本** | ✅ **采用** | 简单、幂等、可回溯 |
| Alembic | ⏸️ 未来 | 初期过重 |
| 手动 DDL | ❌ | 不可追溯 |

**规则**：
- 每次迁移是一个 Python 模块，包含 `MIGRATION` SQL 字符串
- 按版本号顺序执行
- `_schema_version` 表记录已执行的迁移
- 迁移幂等（`IF NOT EXISTS` + 版本检查）

### 决策 4: 演进路径

```
sqlite3 stdlib → SQLAlchemy Core → PostgreSQL → DuckDB (分析)
```

每步只换底层，不破坏 Repository 接口。

## 4. 后果

### 4.1 正面
- **统一接口**：L3/L4 通过 Repository 访问数据
- **零依赖**：Python 内置 sqlite3
- **可移植**：单文件数据库，跨系统迁移容易
- **可演进**：未来平滑迁移到 PostgreSQL

### 4.2 负面
- **SQLite 并发限制**：单写多读（对我们当前单人场景不是问题）
- **自封装工作量**：需要写 Repository 基类 + 迁移引擎
- **无 ORM**：初期手写 SQL（可用 dataclass 缓解）

### 4.3 风险
| 风险 | 缓解 |
|---|---|
| SQLite 并发瓶颈 | 单人场景无影响；未来迁移到 PostgreSQL |
| Schema 迁移失败 | 幂等设计 + 备份机制 |
| Repository 接口设计不当 | 先 MVP 验证，迭代调整 |

## 5. 实现计划

- [x] ADR-006 accepted（本文件）
- [x] 验证：手动创建 SQLite + 测试迁移流程
- [ ] 实现 connection.py / migration.py / repository.py
- [ ] 测试：CRUD + 迁移

## 6. 验证标准

1. 数据库文件创建在 `~/.openclaw/data/platform.db`
2. 迁移脚本按版本号顺序执行
3. Repository CRUD 操作正常
4. 事务回滚正确

## 7. 相关决策

- **supersedes**: null
- **superseded_by**: null
- **相关 ADR**:
  - ADR-202608-001: 4 层架构（持久化是 L2 基础能力）
  - ADR-202608-004: 可观测性适配（DB 操作需要日志）
- **相关文档**:
  - `docs/architecture/components/persistence/DESIGN.md`（完整设计）

## 8. 引用

- **Python sqlite3**: https://docs.python.org/3/library/sqlite3.html
- **SQLite WAL**: https://www.sqlite.org/wal.html
- **Repository Pattern**: Martin Fowler
- **Alembic**: https://alembic.sqlalchemy.org

## 9. 变更历史

- 2026-08-21: proposed
- 2026-08-21: accepted（Rex 确认）
