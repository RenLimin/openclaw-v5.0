"""数据仓库基类。

提供基础 CRUD + 多租户隔离：
- 所有实体带 tenant_id 字段，查询/更新自动过滤当前租户
- 存储后端默认内存 dict，可替换为 SQLAlchemy / MongoDB 等
"""

from __future__ import annotations

import threading
from datetime import datetime
from typing import Any, Dict, Generic, List, Optional, Type, TypeVar

from .base_model import TenantModel, _current_tenant

T = TypeVar("T", bound="TenantModel")


class BaseRepository(Generic[T]):
    """内存版数据仓库基类，支持多租户隔离。

    子类只需指定 model_cls，即可获得完整 CRUD。
    生产环境可替换为 SQLAlchemy / MongoDB 实现，接口不变。
    """

    model_cls: Type[T]  # 子类必须覆盖

    _store: Dict[str, Dict[str, T]] = {}  # {tenant_id: {id: model}}
    _lock = threading.RLock()

    # ── 内部工具 ────────────────────────────────────────────────

    @classmethod
    def _ensure_store(cls, tenant_id: str) -> Dict[str, T]:
        if tenant_id not in cls._store:
            cls._store[tenant_id] = {}
        return cls._store[tenant_id]

    @classmethod
    def _reset_store(cls) -> None:
        """清空所有数据 —— 仅供测试使用。"""
        with cls._lock:
            cls._store.clear()

    # ── CRUD ────────────────────────────────────────────────────

    @classmethod
    def create(cls, **data: Any) -> T:
        """创建一条记录，自动绑定当前租户。"""
        tenant_id = _current_tenant()
        data.setdefault("tenant_id", tenant_id)
        obj = cls.model_cls(**data)
        # 再次确保 tenant_id 与当前上下文一致
        if obj.tenant_id != tenant_id:
            raise ValueError(
                f"tenant_id mismatch: data={obj.tenant_id}, context={tenant_id}"
            )
        with cls._lock:
            store = cls._ensure_store(tenant_id)
            if obj.id in store:
                raise ValueError(
                    f"{cls.model_cls.__name__} id={obj.id} already exists"
                )
            store[obj.id] = obj
        return obj

    @classmethod
    def get_by_id(cls, item_id: str) -> Optional[T]:
        """按 ID 获取，自动过滤租户。"""
        tenant_id = _current_tenant()
        with cls._lock:
            store = cls._ensure_store(tenant_id)
            obj = store.get(item_id)
            if obj and not obj.is_deleted:
                return obj.model_copy()
            return None

    @classmethod
    def list(cls, *, limit: int = 100, offset: int = 0) -> List[T]:
        """列出当前租户所有未删除记录。"""
        tenant_id = _current_tenant()
        with cls._lock:
            store = cls._ensure_store(tenant_id)
            items = [
                m.model_copy() for m in store.values()
                if not m.is_deleted
            ]
        items.sort(key=lambda x: x.created_at, reverse=True)
        return items[offset:offset + limit]

    @classmethod
    def filter(
        cls, *, limit: int = 100, offset: int = 0, **conditions: Any
    ) -> List[T]:
        """按字段等值过滤。"""
        tenant_id = _current_tenant()
        with cls._lock:
            store = cls._ensure_store(tenant_id)
            results = []
            for m in store.values():
                if m.is_deleted:
                    continue
                match = True
                for k, v in conditions.items():
                    if getattr(m, k, None) != v:
                        match = False
                        break
                if match:
                    results.append(m.model_copy())
        results.sort(key=lambda x: x.created_at, reverse=True)
        return results[offset:offset + limit]

    @classmethod
    def update(cls, item_id: str, **updates: Any) -> T:
        """更新指定字段，自动维护 updated_at。"""
        tenant_id = _current_tenant()
        with cls._lock:
            store = cls._ensure_store(tenant_id)
            obj = store.get(item_id)
            if obj is None or obj.is_deleted:
                raise ValueError(
                    f"{cls.model_cls.__name__} id={item_id} not found"
                )
            # 禁止改 id / tenant_id
            updates.pop("id", None)
            updates.pop("tenant_id", None)
            updates["updated_at"] = datetime.utcnow()
            new_obj = obj.model_copy(update=updates)
            store[item_id] = new_obj
            return new_obj.model_copy()

    @classmethod
    def delete(cls, item_id: str) -> None:
        """软删除。"""
        cls.update(item_id, is_deleted=True)

    @classmethod
    def count(cls) -> int:
        """统计当前租户未删除记录数。"""
        tenant_id = _current_tenant()
        with cls._lock:
            store = cls._ensure_store(tenant_id)
            return sum(1 for m in store.values() if not m.is_deleted)
