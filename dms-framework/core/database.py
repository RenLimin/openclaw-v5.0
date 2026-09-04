"""
core/database.py — 存储抽象层
SQLite 默认实现，预留 PostgreSQL 迁移能力。
提供 Database / BaseModel / Repository / MigrationManager 四层抽象。
所有表强制携带 tenant_id，默认 "system"。
"""
from __future__ import annotations


import sqlite3

# 清除 sqlite3 默认类型转换器（Python 3.12+ 已弃用，且不支持 ISO 格式带 T）
# 时间字段统一存 ISO 字符串，应用层自行解析
for _conv_key in list(sqlite3.converters.keys()):
    if _conv_key.upper() in ("DATE", "TIMESTAMP", "DATETIME"):
        del sqlite3.converters[_conv_key]
import threading
from dataclasses import dataclass, field, fields, asdict
from datetime import datetime, timezone
from typing import Any, Callable, ClassVar, Generic, TypeVar, Optional


T = TypeVar("T")


# ---------------------------------------------------------------------------
# Database — 连接 + 租户上下文 + 事务
# ---------------------------------------------------------------------------

class Database:
    """存储抽象层：当前 SQLite，后续可切 PostgreSQL。

    线程安全：每线程一个连接（thread-local），避免 SQLite 并发写问题。
    租户上下文：通过 set_tenant_context 注入，所有查询自动携带 tenant_id 过滤。
    """

    def __init__(self, url: str = "sqlite:///delivery.db") -> None:
        self._url = url
        self._db_path = url.replace("sqlite:///", "", 1) if url.startswith("sqlite:///") else url
        self._local = threading.local()
        self._tenant: str = "system"
        self._lock = threading.Lock()

    # -- 连接管理 ----------------------------------------------------------

    def connect(self) -> sqlite3.Connection:
        """获取当前线程的数据库连接，惰性创建。"""
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(
                self._db_path,
                detect_types=sqlite3.PARSE_DECLTYPES,
                check_same_thread=False,
            )
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            self._local.conn = conn
        return conn

    def close(self) -> None:
        """关闭当前线程连接。"""
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None

    # -- 租户上下文 --------------------------------------------------------

    def set_tenant_context(self, tenant_id: str) -> None:
        """设置当前租户（RLS 模拟）。后续查询自动用该 tenant_id 过滤。"""
        if not tenant_id or not isinstance(tenant_id, str):
            raise ValueError("tenant_id must be a non-empty string")
        self._tenant = tenant_id

    def get_current_tenant(self) -> str:
        """获取当前租户：优先 TenantContext（调用方设置），回退到内部 _tenant。"""
        try:
            from core.saas import TenantContext
            tc = TenantContext.current()
            if tc and tc != "system":
                return tc
        except ImportError:
            pass
        return self._tenant

    # -- 事务 --------------------------------------------------------------

    def execute(self, sql: str, params: tuple | dict = ()) -> sqlite3.Cursor:
        """执行 SQL，自动带 tenant_id 占位符绑定（调用方自行在 SQL 中引用）。"""
        return self.connect().execute(sql, params)

    def commit(self) -> None:
        self.connect().commit()

    def rollback(self) -> None:
        self.connect().rollback()


# ---------------------------------------------------------------------------
# BaseModel — ORM-lite 基类
# ---------------------------------------------------------------------------

@dataclass
class BaseModel:
    """数据模型基类，提供 save / delete / get / list 基础方法。

    约定：
    - 子类必须定义 `id: str` 作为主键
    - 所有表自动包含 `tenant_id` 字段，默认 "system"
    - 表名由子类 `__tablename__` 指定
    """

    id: str = ""
    tenant_id: str = "system"
    created_at: str = ""
    updated_at: str = ""

    __tablename__: ClassVar[str] = ""

    # -- 生命周期钩子 ------------------------------------------------------

    def _before_save(self) -> None:
        now = datetime.now(timezone.utc).isoformat()
        if not self.created_at:
            self.created_at = now
        self.updated_at = now
        if not self.id:
            import uuid
            self.id = str(uuid.uuid4())

    # -- CRUD --------------------------------------------------------------

    def save(self, db: Database) -> None:
        """插入或更新（按 id 判存在）。"""
        self._before_save()
        if self.tenant_id == "system":
            self.tenant_id = db.get_current_tenant()

        table = self.__tablename__
        if not table:
            raise ValueError(f"{type(self).__name__} must define __tablename__")

        data = asdict(self)
        existing = self._find_by_id(db, self.id)

        if existing:
            cols = [f.name for f in fields(self)]
            set_clause = ", ".join(f"{c} = ?" for c in cols if c != "id")
            values = [data[c] for c in cols if c != "id"] + [self.id, db.get_current_tenant()]
            sql = f"UPDATE {table} SET {set_clause} WHERE id = ? AND tenant_id = ?"
            db.execute(sql, tuple(values))
        else:
            cols = [f.name for f in fields(self)]
            placeholders = ", ".join("?" * len(cols))
            col_names = ", ".join(cols)
            values = [data[c] for c in cols]
            sql = f"INSERT INTO {table} ({col_names}) VALUES ({placeholders})"
            db.execute(sql, tuple(values))
        db.commit()
        db.commit()

    def delete(self, db: Database) -> None:
        table = self.__tablename__
        db.execute(
            f"DELETE FROM {table} WHERE id = ? AND tenant_id = ?",
            (self.id, db.get_current_tenant()),
        )
        db.commit()

    @classmethod
    def get(cls, db: Database, id: str) -> Optional["BaseModel"]:
        row = cls._find_by_id(db, id)
        return cls._row_to_instance(row) if row else None

    @classmethod
    def list(cls, db: Database, **filters: Any) -> list["BaseModel"]:
        table = cls.__tablename__
        where = ["tenant_id = ?"]
        params: list[Any] = [db.get_current_tenant()]
        for k, v in filters.items():
            where.append(f"{k} = ?")
            params.append(v)
        sql = f"SELECT * FROM {table} WHERE {' AND '.join(where)} ORDER BY created_at DESC"
        cursor = db.execute(sql, tuple(params))
        return [cls._row_to_instance(row) for row in cursor.fetchall()]

    # -- 内部方法 ----------------------------------------------------------

    @classmethod
    def _find_by_id(cls, db: Database, id: str) -> sqlite3.Row | None:
        table = cls.__tablename__
        cursor = db.execute(
            f"SELECT * FROM {table} WHERE id = ? AND tenant_id = ?",
            (id, db.get_current_tenant()),
        )
        return cursor.fetchone()

    @classmethod
    def _row_to_instance(cls, row: sqlite3.Row) -> "BaseModel":
        kwargs = {f.name: row[f.name] for f in fields(cls) if f.name in row.keys()}
        return cls(**kwargs)


# ---------------------------------------------------------------------------
# Repository — 泛型仓储
# ---------------------------------------------------------------------------

class Repository(Generic[T]):
    """泛型仓储，对 BaseModel 子类做租户隔离的 CRUD 封装。"""

    def __init__(self, db: Database, model_class: type[T], table: str) -> None:
        self._db = db
        self._model = model_class
        self._table = table

    def add(self, entity: T) -> T:
        assert isinstance(entity, BaseModel)
        entity.save(self._db)
        return entity

    def get(self, id: str) -> T | None:
        return self._model.get(self._db, id)  # type: ignore[return-value]

    def update(self, entity: T) -> T:
        assert isinstance(entity, BaseModel)
        entity.save(self._db)
        return entity

    def delete(self, id: str) -> bool:
        entity = self.get(id)
        if entity is None:
            return False
        assert isinstance(entity, BaseModel)
        entity.delete(self._db)
        return True

    def list(self, **filters: Any) -> list[T]:
        return self._model.list(self._db, **filters)

    def get_by_id_ignore_tenant(self, id: str) -> Optional[T]:
        """按 ID 查询，忽略 tenant 隔离（用于管理视图）。"""
        table = self._model.__tablename__
        cursor = self._db.execute(f"SELECT * FROM {table} WHERE id = ?", (id,))
        row = cursor.fetchone()
        return self._model._row_to_instance(row) if row else None  # type: ignore[return-value]

    def count(self, **filters: Any) -> int:
        where = ["tenant_id = ?"]
        params: list[Any] = [self._db.get_current_tenant()]
        for k, v in filters.items():
            where.append(f"{k} = ?")
            params.append(v)
        sql = f"SELECT COUNT(*) FROM {self._table} WHERE {' AND '.join(where)}"
        cursor = self._db.execute(sql, tuple(params))
        return int(cursor.fetchone()[0])


# ---------------------------------------------------------------------------
# MigrationManager — 版本化迁移
# ---------------------------------------------------------------------------

@dataclass
class Migration:
    version: str
    description: str
    up: Callable[[sqlite3.Connection], None]


class MigrationManager:
    """Schema 版本化迁移管理器。

    每个模块通过 register 注册自己的迁移脚本，
    migrate() 按版本号拓扑排序后顺序执行。
    使用 __schema_version 表追踪当前版本。
    """

    VERSION_TABLE = "__schema_version"

    def __init__(self) -> None:
        self._migrations: dict[str, Migration] = {}

    def register(self, version: str, description: str, up: Callable[[sqlite3.Connection], None]) -> None:
        if version in self._migrations:
            raise ValueError(f"Migration version {version} already registered")
        self._migrations[version] = Migration(version=version, description=description, up=up)

    def get_current_version(self, db: Database) -> str:
        conn = db.connect()
        try:
            conn.execute(
                f"CREATE TABLE IF NOT EXISTS {self.VERSION_TABLE} "
                f"(version TEXT PRIMARY KEY, applied_at TEXT)"
            )
            cursor = conn.execute(
                f"SELECT version FROM {self.VERSION_TABLE} ORDER BY version DESC LIMIT 1"
            )
            row = cursor.fetchone()
            return row["version"] if row else "0"
        except Exception:
            return "0"

    def migrate(self, db: Database, target: str = "latest") -> None:
        """执行所有未应用的迁移。target='latest' 表示全部应用。"""
        conn = db.connect()
        conn.execute(
            f"CREATE TABLE IF NOT EXISTS {self.VERSION_TABLE} "
            f"(version TEXT PRIMARY KEY, applied_at TEXT)"
        )
        applied = {
            row["version"]
            for row in conn.execute(f"SELECT version FROM {self.VERSION_TABLE}").fetchall()
        }
        pending = [m for v, m in sorted(self._migrations.items()) if v not in applied]
        if target != "latest":
            pending = [m for m in pending if m.version <= target]

        for migration in pending:
            migration.up(conn)
            conn.execute(
                f"INSERT INTO {self.VERSION_TABLE} (version, applied_at) VALUES (?, ?)",
                (migration.version, datetime.now(timezone.utc).isoformat()),
            )
        db.commit()

    def diff(self, db: Database) -> list[str]:
        """返回待应用的迁移版本列表。"""
        current = self.get_current_version(db)
        return [
            f"{v} — {m.description}"
            for v, m in sorted(self._migrations.items())
            if v > current
        ]
