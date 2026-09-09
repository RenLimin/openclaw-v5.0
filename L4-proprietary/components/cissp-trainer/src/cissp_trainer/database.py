"""
数据库初始化与会话管理
"""

from pathlib import Path
from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from .models import Base

# 默认数据库路径：组件 data/db/cissp_trainer.db
DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "db" / "cissp_trainer.db"

_engine = None
_SessionLocal = None


def get_engine(db_path: str | Path | None = None):
    """获取数据库 engine（懒加载 + 单例）"""
    global _engine, _SessionLocal
    path = Path(db_path) if db_path else DEFAULT_DB_PATH
    path_key = str(path.resolve())

    # 如果已有 engine 且路径匹配，复用
    if _engine is not None and _engine.url.database == path_key:
        return _engine

    path.parent.mkdir(parents=True, exist_ok=True)
    url = f"sqlite:///{path_key}"
    _engine = create_engine(url, echo=False, future=True,
                            connect_args={"check_same_thread": False})
    _SessionLocal = sessionmaker(bind=_engine, autocommit=False, autoflush=False, future=True)
    return _engine


def get_session(db_path: str | Path | None = None) -> Session:
    """获取一个新的数据库 session"""
    get_engine(db_path)
    return _SessionLocal()


@contextmanager
def session_scope(db_path: str | Path | None = None):
    """上下文管理器：自动 commit/rollback/close"""
    session = get_session(db_path)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db(db_path: str | Path | None = None, drop_first: bool = False):
    """初始化数据库（建表）"""
    engine = get_engine(db_path)
    if drop_first:
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    return engine
