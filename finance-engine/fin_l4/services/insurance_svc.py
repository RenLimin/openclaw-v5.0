"""保险服务 — 调用 FIN-003 引擎"""

from decimal import Decimal
from typing import List, Dict, Optional
from fin003_insurance import InsuranceEngine, InsuranceType
from fin_l4.db.repositories import InsuranceRepository, AuditLogRepository


TYPE_MAP = {
    "term_life": InsuranceType.TERM_LIFE,
    "whole_life": InsuranceType.WHOLE_LIFE,
    "endowment": InsuranceType.ENDOWMENT,
    "critical_illness": InsuranceType.CRITICAL_ILLNESS,
    "medical": InsuranceType.MEDICAL,
    "annuity": InsuranceType.ANNUITY,
    "universal_life": InsuranceType.UNIVERSAL_LIFE,
    "tax_deferred": InsuranceType.TAX_DEFERRED,
}


class InsuranceService:
    """保险服务"""

    def __init__(self, conn):
        self.conn = conn
        self.repo = InsuranceRepository(conn)
        self.audit = AuditLogRepository(conn)
        self.engine = InsuranceEngine()

    def add_policy(self, family_id: str, product_name: str, policy_type: str,
                   sum_assured: str, annual_premium: str, term_years: int,
                   payment_years: int, insured_name: str = None,
                   insured_age: int = None, insured_gender: str = None,
                   start_date: str = None) -> Dict:
        """添加保单"""
        if policy_type not in TYPE_MAP:
            raise ValueError(f"无效险种: {policy_type}")

        from datetime import date as date_mod
        policy_id = self.repo.create(
            family_id=family_id,
            product_name=product_name,
            policy_type=policy_type,
            sum_assured=sum_assured,
            annual_premium=annual_premium,
            term_years=term_years,
            payment_years=payment_years,
            insured_name=insured_name,
            insured_age=insured_age,
            insured_gender=insured_gender,
            start_date=start_date or str(date_mod.today()),
        )

        self.audit.log(
            family_id=family_id,
            user="system",
            action="create",
            entity_type="insurance",
            entity_id=policy_id,
            details={"name": product_name, "type": policy_type},
        )

        return self.repo.get(policy_id)

    def get_cash_value(self, policy_id: str, as_of_year: int) -> Dict:
        """获取现金价值 — 调用 FIN-003"""
        policy_data = self.repo.get(policy_id)
        if not policy_data:
            raise ValueError(f"保单不存在: {policy_id}")

        policy = self.engine.create_policy(
            product_name=policy_data["product_name"],
            policy_type=TYPE_MAP[policy_data["policy_type"]],
            annual_premium=Decimal(policy_data["annual_premium"]),
            sum_assured=Decimal(policy_data["sum_assured"]),
            term_years=policy_data["term_years"],
            payment_years=policy_data["payment_years"],
            insured_age=policy_data["insured_age"] or 30,
            insured_gender=policy_data["insured_gender"] or "M",
        )

        result = self.engine.calculate_cash_value(policy.id, as_of_year)
        return {
            "policy_id": policy_id,
            "as_of_year": as_of_year,
            "guaranteed_cv": str(result.guaranteed_cv),
            "non_guaranteed_cv": str(result.non_guaranteed_cv),
            "total_cv": str(result.total_cv),
            "is_estimate": result.is_estimate,
        }

    def list_policies(self, family_id: str) -> List[Dict]:
        """列出家庭所有保单"""
        rows = self.repo.list_by_family(family_id)
        return [{
            "id": r["id"],
            "policy_number": r.get("policy_number") or (r.get("extra_terms") and __import__("json").loads(r["extra_terms"]).get("policy_number", "")) or r["id"][:8],
            "name": r.get("product_name", ""),
            "type": r.get("policy_type", ""),
            "sum_assured": r.get("sum_assured", "0"),
            "premium": r.get("annual_premium", "0"),
            "status": r.get("status", "active"),
            "term_years": r.get("term_years", 0),
        } for r in rows]

    def get_policy_detail(self, policy_id: str) -> Dict:
        """保单详情（含现金价值表）"""
        policy = self.repo.get(policy_id)
        if not policy:
            raise ValueError(f"保单不存在: {policy_id}")

        # 现金价值表（前10年）
        cv_table = []
        for year in range(1, min(policy["term_years"] + 1, 11)):
            try:
                cv = self.get_cash_value(policy_id, year)
                cv_table.append({
                    "year": year,
                    "cash_value": cv["total_cv"],
                    "cumulative_premium": str(Decimal(policy["annual_premium"]) * year),
                    "net_gain": str(Decimal(cv["total_cv"]) - Decimal(policy["annual_premium"]) * year),
                })
            except Exception:
                break

        return {**policy, "cash_value_table": cv_table}

    def surrender_policy(self, policy_id: str) -> Dict:
        """退保"""
        policy = self.repo.get(policy_id)
        if not policy:
            raise ValueError(f"保单不存在: {policy_id}")

        # 计算当前现金价值（按已缴费年数）
        from datetime import date
        start = date.fromisoformat(policy["start_date"])
        years_elapsed = (date.today() - start).days // 365
        years_elapsed = max(1, min(years_elapsed, policy["term_years"]))

        cv = self.get_cash_value(policy_id, years_elapsed)

        # 更新状态
        self.repo.update_status(policy_id, "surrendered")

        self.audit.log(
            family_id=policy["family_id"],
            user="system",
            action="surrender",
            entity_type="insurance",
            entity_id=policy_id,
            details={"cash_value": cv["total_cv"]},
        )

        return {"policy_id": policy_id, "cash_value": cv["total_cv"], "status": "surrendered"}

    def get_coverage_gap(self, family_id: str, monthly_income: str = "35000") -> List[Dict]:
        """保障缺口分析"""
        policies = self.repo.list_by_family(family_id)
        income = Decimal(monthly_income)

        # 建议保额（12倍年收入为基准）
        recommendations = {
            "term_life": income * 12 * 10,      # 寿险: 10倍年收入
            "whole_life": income * 12 * 5,
            "critical_illness": income * 12 * 5,  # 重疾: 5倍年收入
            "medical": income * 12 * 2,
            "endowment": income * 12 * 3,
            "annuity": income * 12 * 5,
            "universal_life": income * 12 * 3,
            "tax_deferred": income * 12 * 2,
        }

        type_names = {
            "term_life": "定期寿险",
            "whole_life": "终身寿险",
            "critical_illness": "重疾险",
            "medical": "医疗险",
            "endowment": "两全险",
            "annuity": "年金险",
            "universal_life": "万能险",
            "tax_deferred": "税延养老",
        }

        # 按险种汇总
        coverage = {}
        for pol in policies:
            if pol["status"] != "active":
                continue
            ptype = pol["policy_type"]
            coverage[ptype] = coverage.get(ptype, Decimal("0")) + Decimal(pol["sum_assured"])

        gaps = []
        for ptype, recommended in recommendations.items():
            current = coverage.get(ptype, Decimal("0"))
            gap = max(Decimal("0"), recommended - current)
            gaps.append({
                "type": ptype,
                "type_name": type_names.get(ptype, ptype),
                "current": str(current.quantize(Decimal("0.01"))),
                "recommended": str(recommended.quantize(Decimal("0.01"))),
                "gap": str(gap.quantize(Decimal("0.01"))),
            })

        return gaps
