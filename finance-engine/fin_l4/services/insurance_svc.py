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
                   insured_age: int = None, insured_gender: str = None) -> Dict:
        """添加保单"""
        if policy_type not in TYPE_MAP:
            raise ValueError(f"无效险种: {policy_type}")

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
        return self.repo.list_by_family(family_id)
