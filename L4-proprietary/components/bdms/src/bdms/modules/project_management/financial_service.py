# 🔒 NO_TOKEN — 纯代码，零 AI 依赖
"""ProjectFinancialService — 项目财务服务。

对齐 DESIGN-DETAIL-PROJECT-MANAGEMENT-v2.1.md §3.3：
- 利润汇总（收入 = budget × estimated_progress，后续接 RevenueEngine）
- 利润趋势
- 利润预警
- 财务健康度评分（4 维度 × 25 分）
"""
from __future__ import annotations

from typing import Any, Dict, List

from bdms.modules.base import NotFoundError

from .engine import ProjectEngine


class ProjectFinancialService:
    """项目财务服务：利润视图 + 健康度评估。"""

    def __init__(self, db_path=None):
        self.engine = ProjectEngine(db_path)
        self.db_path = self.engine.db_path

    def _cost_engine(self):
        from .cost.engine import CostEngine
        return CostEngine(self.db_path)

    # ========================================================
    # 利润汇总（§3.3.1）
    # ========================================================

    def get_profit_summary(self, project_id: int) -> Dict[str, Any]:
        """获取项目利润汇总。

        收入估算策略（现阶段）: budget × estimated_progress
        """
        project = self.engine.get_project(project_id)
        if not project:
            raise NotFoundError(f"项目 {project_id} 不存在")

        cost = self._cost_engine().get_cost_summary(project_id)
        budget = float(project.get("budget") or 0)
        progress = self._estimate_progress(project_id)

        total_revenue = budget * progress
        total_cost = cost["total"]
        gross_profit = total_revenue - total_cost
        gross_margin = (gross_profit / total_revenue * 100) if total_revenue > 0 else 0.0

        return {
            "budget": budget,
            "total_revenue": round(total_revenue, 2),
            "total_cost": round(total_cost, 2),
            "gross_profit": round(gross_profit, 2),
            "gross_margin": round(gross_margin, 1),
            "budget_usage_pct": round(total_cost / budget * 100, 1) if budget else 0.0,
            "estimated_progress": round(progress, 3),
        }

    # ========================================================
    # 利润趋势（§3.3.2）
    # ========================================================

    def get_profit_trend(self, project_id: int, range_months: int = 12) -> List[Dict[str, Any]]:
        """获取利润趋势（按月）。

        现阶段收入按当月进度增量估算，后续接实际确收。
        """
        cost = self._cost_engine().get_cost_summary(project_id)
        budget = float(self.engine.get_project(project_id).get("budget") or 0)

        trend = []
        for m in cost["by_month"][-range_months:]:
            revenue = budget * 0.1  # 占位：月度收入均摊估算
            profit = revenue - m["total"]
            trend.append({
                "month": m["month"],
                "revenue": round(revenue, 2),
                "cost": m["total"],
                "profit": round(profit, 2),
                "margin": round(profit / revenue * 100, 1) if revenue else 0.0,
            })
        return trend

    # ========================================================
    # 利润预警（§3.3.3）
    # ========================================================

    def check_profit_alert(
        self, project_id: int, threshold_pct: float = 20.0
    ) -> Dict[str, Any]:
        """检查利润预警。"""
        summary = self.get_profit_summary(project_id)
        margin = summary["gross_margin"]

        if margin < 0:
            level = "critical"
        elif margin < threshold_pct / 2:
            level = "warning"
        else:
            level = "info"

        return {
            "alert": margin < threshold_pct,
            "current_margin": margin,
            "threshold": threshold_pct,
            "level": level,
        }

    # ========================================================
    # 财务健康度评分（§3.3.4）
    # ========================================================

    def get_financial_health_score(self, project_id: int) -> Dict[str, Any]:
        """财务健康度评分（0-100）。

        4 维度各 25 分：预算执行率 / 毛利率 / 成本增长率 / 现金流匹配度。
        """
        summary = self.get_profit_summary(project_id)
        recommendations: List[str] = []

        # 1. 预算执行率（25 分）
        usage = summary["budget_usage_pct"]
        if usage < 70:
            budget_score = 25
        elif usage < 90:
            budget_score = 20
        elif usage <= 100:
            budget_score = 10
        else:
            budget_score = 0
            recommendations.append(f"预算超支 {usage - 100:.1f}%，需控制成本")

        # 2. 毛利率（25 分）
        margin = summary["gross_margin"]
        if margin >= 30:
            margin_score = 25
        elif margin >= 20:
            margin_score = 20
        elif margin >= 10:
            margin_score = 12
        elif margin >= 0:
            margin_score = 5
        else:
            margin_score = 0
            recommendations.append("毛利率为负，项目亏损")

        # 3. 成本增长率（25 分）——按最近月成本占比估算
        cost = self._cost_engine().get_cost_summary(project_id)
        by_month = cost["by_month"]
        if len(by_month) >= 2 and by_month[-2]["total"] > 0:
            growth = (by_month[-1]["total"] - by_month[-2]["total"]) / by_month[-2]["total"] * 100
        else:
            growth = 0.0
        if growth <= 10:
            growth_score = 25
        elif growth <= 25:
            growth_score = 18
        elif growth <= 50:
            growth_score = 10
        else:
            growth_score = 3
            recommendations.append(f"成本月增 {growth:.1f}%，增长过快")

        # 4. 现金流匹配度（25 分）——成本/收入
        revenue = summary["total_revenue"]
        cost_ratio = cost["total"] / revenue if revenue > 0 else 2.0
        if cost_ratio <= 0.7:
            cash_score = 25
        elif cost_ratio <= 0.9:
            cash_score = 18
        elif cost_ratio <= 1.0:
            cash_score = 10
        else:
            cash_score = 3
            recommendations.append("成本超过收入，现金流承压")

        total = budget_score + margin_score + growth_score + cash_score
        if total >= 85:
            level = "excellent"
        elif total >= 70:
            level = "good"
        elif total >= 55:
            level = "fair"
        elif total >= 40:
            level = "poor"
        else:
            level = "critical"

        if not recommendations:
            recommendations.append("财务状况良好，保持当前节奏")

        return {
            "score": total,
            "level": level,
            "breakdown": {
                "预算执行率": budget_score,
                "毛利率": margin_score,
                "成本增长率": growth_score,
                "现金流匹配度": cash_score,
            },
            "recommendations": recommendations,
        }

    # ========================================================
    # 内部工具
    # ========================================================

    def _estimate_progress(self, project_id: int) -> float:
        """估算项目进度（0-1）：已完成阶段 / 总阶段。"""
        phases = self.engine.list_phases(project_id)
        if not phases:
            return 0.0
        completed = sum(1 for p in phases if p["status"] == "completed")
        return completed / len(phases)
