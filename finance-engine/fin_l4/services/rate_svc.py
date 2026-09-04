"""利率同步服务 — 调用 FIN-004 引擎"""

from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional
from fin004_rate import RateEngine
from fin_l4.db.repositories import RateSnapshotRepository


class RateService:
    """利率同步服务"""

    def __init__(self, conn):
        self.conn = conn
        self.repo = RateSnapshotRepository(conn)
        self.engine = RateEngine()

    def sync_rates(self) -> Dict:
        """手动同步利率 — 调用 FIN-004"""
        results = {"lpr": [], "central_bank": [], "errors": []}

        # LPR 利率
        for term in ["1y", "5y"]:
            try:
                snapshot = self.engine.get_current_lpr(term=term)
                self.repo.save(
                    rate_type="LPR",
                    term=term,
                    rate=str(snapshot.rate),
                    effective_date=str(snapshot.effective_date),
                    source=snapshot.source,
                )
                results["lpr"].append({
                    "term": term,
                    "rate": str(snapshot.rate),
                    "date": str(snapshot.effective_date),
                })
            except Exception as e:
                results["errors"].append(f"LPR {term}: {str(e)}")

        # 央行基准利率
        try:
            cb = self.engine.get_central_bank_rate(country="CN")
            self.repo.save(
                rate_type="CENTRAL_BANK",
                term=cb.term or "loan_1y",
                rate=str(cb.rate),
                effective_date=str(cb.effective_date) if cb.effective_date else None,
                source=cb.source,
            )
            results["central_bank"].append({
                "rate": str(cb.rate),
                "term": cb.term,
                "date": str(cb.effective_date) if cb.effective_date else None,
            })
        except Exception as e:
            results["errors"].append(f"央行利率: {str(e)}")

        return results

    def get_latest(self, rate_type: str = "LPR",
                   term: str = None) -> Optional[Dict]:
        """查询最新利率"""
        return self.repo.get_latest(rate_type, term)

    def get_history(self, rate_type: str = "LPR",
                    term: str = None, limit: int = 50) -> List[Dict]:
        """查询历史利率"""
        return self.repo.get_history(rate_type, term, limit)
