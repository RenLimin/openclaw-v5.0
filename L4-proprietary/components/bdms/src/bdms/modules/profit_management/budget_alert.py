"""预算告警服务 —— BudgetAlertService。"""

from pathlib import Path
from typing import Optional, List, Dict, Any

from bdms.modules.profit_management.engine import ProfitEngine


class BudgetAlertService:
    """预算告警服务，薄封装ProfitEngine的预算告警检查。"""

    def __init__(self, db_path: Optional[Path] = None):
        self._engine = ProfitEngine(db_path)

    def check(self, project_id: int, threshold: float = 0.10) -> List[Dict[str, Any]]:
        """检查项目预算超阈值告警，返回告警列表，无告警返回空列表。"""
        return self._engine.check_budget_alert(project_id, threshold)

