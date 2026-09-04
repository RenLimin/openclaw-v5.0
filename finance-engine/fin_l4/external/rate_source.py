"""利率数据源 — 基于 FIN-004 引擎"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from fin_l4.external.base import DataSource, DataSnapshot
from decimal import Decimal
from datetime import date


class RateSource(DataSource):
    """利率数据源"""
    
    def __init__(self):
        # 延迟导入避免循环
        from fin004_rate import RateEngine
        self.engine = RateEngine()
    
    @property
    def name(self) -> str:
        return "rate_lpr"
    
    @property
    def data_type(self) -> str:
        return "rate"
    
    @property
    def ttl_seconds(self) -> int:
        return 86400  # 24h
    
    def fetch(self, **params) -> DataSnapshot:
        term = params.get("term", "5y")
        snapshot = self.engine.get_current_lpr(term=term)
        return DataSnapshot(
            source=self.name,
            data_type="rate",
            value=snapshot.rate,
            effective_date=str(snapshot.effective_date),
            metadata={"term": term, "raw_source": snapshot.source},
        )
    
    def is_available(self) -> bool:
        try:
            self.engine.get_current_lpr(term="5y")
            return True
        except Exception:
            return False
