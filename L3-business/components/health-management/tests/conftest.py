"""共享测试配置。"""

import sys
import os
from pathlib import Path

# 将组件根目录加入 sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest

from repository.base import (
    BaseRepository,
    set_current_tenant,
    reset_current_tenant,
)


TENANT_A = "tenant-a-001"
TENANT_B = "tenant-b-002"


@pytest.fixture(autouse=True)
def clean_store():
    """每个测试前清空内存存储 + 设置默认租户。"""
    BaseRepository._reset_store()
    token = set_current_tenant(TENANT_A)
    yield
    reset_current_tenant(token)
    BaseRepository._reset_store()


@pytest.fixture
def tenant_a():
    return TENANT_A


@pytest.fixture
def tenant_b():
    return TENANT_B


@pytest.fixture
def switch_tenant():
    """切换到另一个租户的上下文管理器。"""
    def _switch(tenant_id: str):
        from contextlib import contextmanager

        @contextmanager
        def _ctx():
            token = set_current_tenant(tenant_id)
            try:
                yield
            finally:
                reset_current_tenant(token)

        return _ctx()

    return _switch
