"""交易/记账服务"""

import csv
import io
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import List, Dict, Optional
from fin_l4.db.repositories import (
    TransactionRepository, AccountRepository, CategoryRepository,
    AuditLogRepository
)


class TransactionService:
    """记账服务"""

    def __init__(self, conn):
        self.conn = conn
        self.repo = TransactionRepository(conn)
        self.account_repo = AccountRepository(conn)
        self.category_repo = CategoryRepository(conn)
        self.audit = AuditLogRepository(conn)

    def record(self, family_id: str, date_str: str, amount: str,
               debit_account_id: str, credit_account_id: str,
               note: str = None, category_id: str = None) -> Dict:
        """记一笔"""
        # 验证金额
        try:
            amt = Decimal(amount)
            if amt <= 0:
                raise ValueError("金额必须为正数")
        except (InvalidOperation, ValueError) as e:
            raise ValueError(f"无效金额: {amount}") from e

        # 验证账户存在
        debit_acc = self.account_repo.get(debit_account_id)
        credit_acc = self.account_repo.get(credit_account_id)
        if not debit_acc:
            raise ValueError(f"借方账户不存在: {debit_account_id}")
        if not credit_acc:
            raise ValueError(f"贷方账户不存在: {credit_account_id}")

        txn_id = self.repo.create(
            family_id=family_id,
            date=date_str,
            amount=amount,
            debit_account_id=debit_account_id,
            credit_account_id=credit_account_id,
            note=note,
            category_id=category_id,
            source="manual",
        )

        self.audit.log(
            family_id=family_id,
            user="system",
            action="create",
            entity_type="transaction",
            entity_id=txn_id,
            details={
                "date": date_str,
                "amount": amount,
                "debit_account": debit_acc["name"],
                "credit_account": credit_acc["name"],
                "note": note,
            },
        )

        return {"id": txn_id, "status": "ok"}

    def list_transactions(self, family_id: str, account_id: str = None,
                         from_date: str = None, to_date: str = None,
                         limit: int = 100) -> List[Dict]:
        """查询交易明细"""
        return self.repo.list_by_family(family_id, account_id, from_date, to_date, limit)

    def import_csv(self, family_id: str, csv_content: str,
                   debit_map: Dict[str, str] = None,
                   credit_map: Dict[str, str] = None) -> Dict:
        """
        CSV 导入
        格式: date, description, amount, category
        amount 正数=收入, 负数=支出
        """
        results = {"imported": 0, "errors": []}
        reader = csv.DictReader(io.StringIO(csv_content))

        # 默认账户映射（可自定义）
        default_debit = debit_map or {}
        default_credit = credit_map or {}

        for row_num, row in enumerate(reader, start=2):
            try:
                date_str = row.get("date", "")
                amount_str = row.get("amount", "0")
                description = row.get("description", "")
                category = row.get("category", "")

                amount = Decimal(amount_str)
                abs_amount = abs(amount)

                # 根据金额正负确定借贷方向
                if amount > 0:
                    # 收入：贷方=收入类，借方=资产类
                    debit_id = default_debit.get("income", "")
                    credit_id = default_credit.get("income", "")
                else:
                    # 支出：借方=费用类，贷方=资产类
                    debit_id = default_debit.get("expense", "")
                    credit_id = default_credit.get("expense", "")

                if not debit_id or not credit_id:
                    results["errors"].append(f"行 {row_num}: 未配置账户映射")
                    continue

                self.repo.create(
                    family_id=family_id,
                    date=date_str,
                    amount=str(abs_amount),
                    debit_account_id=debit_id,
                    credit_account_id=credit_id,
                    note=description,
                    source="imported",
                )
                results["imported"] += 1

            except Exception as e:
                results["errors"].append(f"行 {row_num}: {str(e)}")

        self.audit.log(
            family_id=family_id,
            user="system",
            action="import",
            entity_type="transaction",
            details={"imported": results["imported"], "errors": len(results["errors"])},
        )

        return results
