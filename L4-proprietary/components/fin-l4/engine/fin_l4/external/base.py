"""外部数据源抽象基类 + 注册表"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional
from decimal import Decimal


@dataclass
class DataSnapshot:
    """数据快照"""
    source: str
    data_type: str          # rate / market / fx
    value: Decimal
    currency: str = "CNY"
    effective_date: str = None
    fetched_at: datetime = field(default_factory=datetime.now)
    metadata: Dict = field(default_factory=dict)
    is_cached: bool = False
    is_estimate: bool = False


class DataSource(ABC):
    """数据源抽象基类"""

    @property
    @abstractmethod
    def name(self) -> str:
        """数据源名称"""

    @property
    @abstractmethod
    def data_type(self) -> str:
        """数据类型"""

    @property
    def ttl_seconds(self) -> int:
        """缓存 TTL（秒）"""
        return 86400  # 默认 24h

    @abstractmethod
    def fetch(self, **params) -> DataSnapshot:
        """获取数据"""

    def is_available(self) -> bool:
        """检查数据源是否可用"""
        return True


class DataSourceRegistry:
    """数据源注册表"""

    _sources: Dict[str, DataSource] = {}

    @classmethod
    def register(cls, source: DataSource):
        cls._sources[source.name] = source

    @classmethod
    def get(cls, name: str) -> Optional[DataSource]:
        return cls._sources.get(name)

    @classmethod
    def list_all(cls) -> List[Dict]:
        return [
            {
                "name": s.name,
                "type": s.data_type,
                "ttl": s.ttl_seconds,
                "available": s.is_available(),
            }
            for s in cls._sources.values()
        ]

    @classmethod
    def list_by_type(cls, data_type: str) -> List[DataSource]:
        return [s for s in cls._sources.values() if s.data_type == data_type]
