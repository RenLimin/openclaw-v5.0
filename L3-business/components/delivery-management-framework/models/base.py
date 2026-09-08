#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BaseModel — 统一数据模型基类
支持 tenant_id 自动注入，统一 CRUD
"""

from dataclasses import dataclass, fields
from typing import Optional
import uuid
import datetime

# 当前租户上下文占位，实际由应用层设置
class TenantContext:
    from contextvars import ContextVar
    _current = ContextVar("tenant_id", default="system")

    @classmethod
    def set(cls, tenant_id: str):
        cls._current.set(tenant_id)

    @classmethod
    def current(cls) -> str:
        return cls._current.get()

@dataclass
class BaseModel:
    """所有数据模型的基类"""
    id: Optional[str] = None
    created_at: Optional[datetime.datetime] = None
    updated_at: Optional[datetime.datetime] = None
    tenant_id: str = "system"

    def __post_init__(self):
        # 自动生成 ID
        if self.id is None:
            self.id = str(uuid.uuid4())
        # 自动注入当前租户
        if self.tenant_id == "system":
            self.tenant_id = TenantContext.current()
        # 设置时间戳
        if self.created_at is None:
            self.created_at = datetime.datetime.now()
        self.updated_at = datetime.datetime.now()

    def dict(self):
        """转换为字典，适合数据库存储"""
        result = {}
        for f in fields(self):
            result[f.name] = getattr(self, f.name)
        return result

    @classmethod
    def table_name(cls):
        """返回数据库表名"""
        return cls.__name__.lower()
