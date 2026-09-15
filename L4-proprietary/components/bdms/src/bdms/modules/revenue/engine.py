"""确认收入管理 —— 计算引擎适配层。

复用策略（重要）：
revenue-recognition 的引擎直接操作强类型 SQLite 表（plan_draft/budget_exec/
monthly_summary/performance_summary），列映射定义在 config.py（PlanCol/BudgetCol）。
重写为 BDMS 宽表会引入二次转换风险。

因此本模块**直接复用原引擎与 DB schema**，只增加：
  1. 统一的 DB 路径管理（BDMS 可指定独立 DB）
  2. 幂等语义包装（auto/read/regenerate）
  3. 与 BDMS 元数据表（job/report_month）的对接

原始实现位于 L4-proprietary/components/revenue-recognition/。
"""

import sys
from pathlib import Path
from typing import Optional

from bdms.core import db as _db
from bdms.core.paths import find_revenue_source, month_dir

# ─── 复用 revenue-recognition 的引擎 ───
_REVENUE_DIR = Path(__file__).resolve().parents[5] / "revenue-recognition" / "src"
if str(_REVENUE_DIR) not in sys.path:
    sys.path.insert(0, str(_REVENUE_DIR))

try:
    from revenue_recognition.v1 import engine as _rr_engine
    from revenue_recognition.v1 import importer as _rr_importer
    from revenue_recognition.v1 import config as _rr_config
    from revenue_recognition.v1 import db as _rr_db
    _HAS_REVENUE = True
except ImportError as e:  # pragma: no cover
    _rr_engine = _rr_importer = _rr_config = _rr_db = None
    _HAS_REVENUE = False
    _REVENUE_IMPORT_ERROR = str(e)


# 本模块产出的 Sheet 清单（对齐源实现）
SHEETS = [
    "计划确收底稿", "预算执行表", "汇总", "汇总分析",
    "月度汇总记录", "履约汇总记录", "确收差异分析",
    "预算趋势分析", "图例", "重拆履约",
]


class RevenueEngineAdapter:
    """确认收入引擎适配器。

    将 revenue-recognition 的 RevenueEngine 包装为 BDMS 统一接口。
    """

    def __init__(self, db_path: Optional[Path] = None):
        # 确认收入使用独立 DB（保持与原实现 schema 兼容）
        from bdms.core.paths import DATA_DIR
        self.db_path = Path(db_path) if db_path else (DATA_DIR / "revenue.db")

    def _engine(self):
        if not _HAS_REVENUE:
            raise RuntimeError(f"无法加载 revenue-recognition: {_REVENUE_IMPORT_ERROR}")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        return _rr_engine.RevenueEngine(self.db_path)

    # ─── 数据源 ───

    def check_sources(self, month: str) -> dict:
        return {"manual_report": find_revenue_source(month)}

    def sources_available(self, month: str) -> bool:
        return find_revenue_source(month) is not None

    # ─── 导入（原始 xlsx → DB）───

    def import_source(self, month: str, excel_path: Optional[Path] = None) -> dict:
        """导入原始确收对比表到 DB。"""
        if not _HAS_REVENUE:
            raise RuntimeError(f"无法加载 revenue-recognition: {_REVENUE_IMPORT_ERROR}")

        path = Path(excel_path) if excel_path else find_revenue_source(month)
        if not path or not Path(path).exists():
            raise FileNotFoundError(f"{month} 找不到确收对比表")

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # 初始化原实现的 schema
        _rr_db.init_db(self.db_path)

        counts = {}
        for name, fn in [
            ("plan_draft", _rr_importer.import_plan_draft),
            ("budget_exec", _rr_importer.import_budget_exec),
            ("monthly_summary", _rr_importer.import_monthly_summary),
            ("performance_summary", _rr_importer.import_performance_summary),
        ]:
            try:
                counts[name] = fn(Path(path), self.db_path)
            except Exception as e:
                counts[name] = f"error: {str(e)[:100]}"
        return counts

    # ─── 计算 ───

    def compute(self, period: str) -> dict:
        """计算全部确收报表数据。"""
        eng = self._engine()
        result = {}
        for name, method in [
            ("summary", eng.compute_summary),
            ("monthly_detail", eng.compute_monthly_detail),
            ("performance_summary", eng.compute_performance_summary),
            ("variance_analysis", eng.compute_variance_analysis),
            ("budget_trend", eng.compute_budget_trend),
            ("yoy_comparison", eng.compute_yoy_comparison),
        ]:
            try:
                result[name] = method(period)
            except Exception as e:
                result[name] = {"error": str(e)[:200]}
        try:
            result["rebuild_perf"] = eng.compute_rebuild_perf()
        except Exception as e:
            result["rebuild_perf"] = {"error": str(e)[:200]}
        return result

    def get_reference_data(self, data_type: str) -> list:
        """读取图例等参考数据。"""
        return self._engine().get_reference_data(data_type)

    def upsert_reference_data(self, data_type: str, code: str, label: str,
                              extra: str = None) -> None:
        """写入参考数据。"""
        self._engine().upsert_reference_data(data_type, code, label, extra)

    def has_data(self, month: str) -> bool:
        """检查确认收入数据是否已落盘。"""
        if not _HAS_REVENUE:
            return False
        if not self.db_path.exists():
            return False
        conn = _db.get_connection(self.db_path)
        try:
            if not _db.table_exists(conn, "budget_exec"):
                return False
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM budget_exec WHERE archive_month IS NOT NULL"
            ).fetchone()
            return bool(row and row["n"] > 0)
        except Exception:
            return False
        finally:
            conn.close()
