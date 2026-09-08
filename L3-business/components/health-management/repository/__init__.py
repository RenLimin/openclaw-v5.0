"""数据仓库层。"""

from .base import BaseRepository, _current_tenant, set_current_tenant

__all__ = ["BaseRepository", "_current_tenant", "set_current_tenant"]
