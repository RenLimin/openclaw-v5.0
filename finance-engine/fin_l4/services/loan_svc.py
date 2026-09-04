"""贷款服务 — 调用 FIN-002 引擎"""

from datetime import date
from decimal import Decimal
from typing import List, Dict, Optional
from fin002_loan import LoanEngine, LoanMethod, LoanSummary
from fin_l4.db.repositories import LoanRepository, AuditLogRepository


METHOD_MAP = {
    "equal_payment": LoanMethod.EQUAL_PAYMENT,
    "equal_principal": LoanMethod.EQUAL_PRINCIPAL,
    "interest_only": LoanMethod.INTEREST_ONLY,
    "flexible": LoanMethod.FLEXIBLE,
}


class LoanService:
    """贷款服务"""

    def __init__(self, conn):
        self.conn = conn
        self.repo = LoanRepository(conn)
        self.audit = AuditLogRepository(conn)
        self.engine = LoanEngine()

    def create_loan(self, family_id: str, name: str, principal: str,
                    annual_rate: str, term_months: int,
                    method: str = "equal_payment",
                    start_date: str = None) -> Dict:
        """创建贷款"""
        if method not in METHOD_MAP:
            raise ValueError(f"无效还款方式: {method}")

        loan_id = self.repo.create(
            family_id=family_id,
            name=name,
            principal=principal,
            annual_rate=annual_rate,
            term_months=term_months,
            method=method,
            start_date=start_date or str(date.today()),
        )

        self.audit.log(
            family_id=family_id,
            user="system",
            action="create",
            entity_type="loan",
            entity_id=loan_id,
            details={"name": name, "principal": principal, "rate": annual_rate},
        )

        return self.repo.get(loan_id)

    def get_schedule(self, loan_id: str) -> List[Dict]:
        """获取还款计划 — 调用 FIN-002"""
        loan_data = self.repo.get(loan_id)
        if not loan_data:
            raise ValueError(f"贷款不存在: {loan_id}")

        # 用 L3 引擎计算还款计划
        loan = self.engine.create_loan(
            name=loan_data["name"],
            principal=Decimal(loan_data["principal"]),
            annual_rate=Decimal(loan_data["annual_rate"]),
            term_months=loan_data["term_months"],
            method=METHOD_MAP[loan_data["method"]],
            start_date=date.fromisoformat(loan_data["start_date"]),
        )

        schedule = self.engine.calculate_amortization_schedule(loan)
        return [
            {
                "period": e.period,
                "payment": str(e.payment),
                "principal": str(e.principal),
                "interest": str(e.interest),
                "remaining_balance": str(e.remaining_balance),
            }
            for e in schedule.entries
        ]

    def get_summary(self, loan_id: str) -> Dict:
        """获取贷款摘要"""
        loan_data = self.repo.get(loan_id)
        if not loan_data:
            raise ValueError(f"贷款不存在: {loan_id}")

        loan = self.engine.create_loan(
            name=loan_data["name"],
            principal=Decimal(loan_data["principal"]),
            annual_rate=Decimal(loan_data["annual_rate"]),
            term_months=loan_data["term_months"],
            method=METHOD_MAP[loan_data["method"]],
            start_date=date.fromisoformat(loan_data["start_date"]),
        )

        summary = self.engine.get_loan_summary(loan)
        return {
            "name": loan_data["name"],
            "monthly_payment": str(summary.next_payment_amount),
            "total_interest": str(summary.total_interest),
            "remaining_balance": str(summary.remaining_balance),
            "paid_periods": summary.paid_periods,
            "remaining_periods": summary.remaining_periods,
        }

    def prepay(self, loan_id: str, amount: str) -> Dict:
        """提前还款测算"""
        loan_data = self.repo.get(loan_id)
        if not loan_data:
            raise ValueError(f"贷款不存在: {loan_id}")

        loan = self.engine.create_loan(
            name=loan_data["name"],
            principal=Decimal(loan_data["principal"]),
            annual_rate=Decimal(loan_data["annual_rate"]),
            term_months=loan_data["term_months"],
            method=METHOD_MAP[loan_data["method"]],
            start_date=date.fromisoformat(loan_data["start_date"]),
        )

        result = self.engine.calculate_early_payoff(loan, Decimal(amount), date.today())
        return {
            "interest_saved": str(result.interest_saved),
            "break_even_months": result.break_even_months,
        }

    def list_loans(self, family_id: str) -> List[Dict]:
        """列出家庭所有贷款"""
        return self.repo.list_by_family(family_id)

    def execute_prepay(self, loan_id: str, amount: str, date_str: str = None) -> Dict:
        """执行提前还款（实际扣款）"""
        from datetime import date
        loan_data = self.repo.get(loan_id)
        if not loan_data:
            raise ValueError(f"贷款不存在: {loan_id}")

        # 计算节省利息
        prepay_result = self.prepay(loan_id, amount)

        # 更新贷款状态（减少本金）
        new_principal = Decimal(loan_data["principal"]) - Decimal(amount)
        self.repo.update_principal(loan_id, str(new_principal))

        self.audit.log(
            family_id=loan_data["family_id"],
            user="system",
            action="prepay",
            entity_type="loan",
            entity_id=loan_id,
            details={"amount": amount, "interest_saved": prepay_result["interest_saved"]},
        )

        return {
            "loan_id": loan_id,
            "prepay_amount": amount,
            "new_principal": str(new_principal),
            "interest_saved": prepay_result["interest_saved"],
        }

    def close_loan(self, loan_id: str) -> Dict:
        """结清贷款"""
        loan_data = self.repo.get(loan_id)
        if not loan_data:
            raise ValueError(f"贷款不存在: {loan_id}")

        self.repo.update_status(loan_id, "closed")

        self.audit.log(
            family_id=loan_data["family_id"],
            user="system",
            action="close",
            entity_type="loan",
            entity_id=loan_id,
            details={},
        )

        return {"loan_id": loan_id, "status": "closed"}
