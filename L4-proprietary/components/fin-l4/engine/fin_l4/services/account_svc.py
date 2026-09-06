"""账户服务 — 调用 FIN-001 引擎"""

from decimal import Decimal
from typing import List, Dict, Optional
from fin001_account import AccountingEngine, AccountType
from fin_l4.db.repositories import AccountRepository, AuditLogRepository


# 账户类型映射
TYPE_MAP = {
    "ASSET": AccountType.ASSET,
    "LIABILITY": AccountType.LIABILITY,
    "EQUITY": AccountType.EQUITY,
    "INCOME": AccountType.INCOME,
    "EXPENSE": AccountType.EXPENSE,
}


class AccountService:
    """账户服务"""

    def __init__(self, conn):
        self.conn = conn
        self.repo = AccountRepository(conn)
        self.audit = AuditLogRepository(conn)
        self.engine = AccountingEngine()

    def create_account(self, family_id: str, code: str, name: str,
                       type: str, currency: str = "CNY",
                       parent_id: str = None,
                       opening_balance: str = "0") -> Dict:
        """创建账户"""
        # 验证类型
        if type not in TYPE_MAP:
            raise ValueError(f"无效账户类型: {type}, 可选: {list(TYPE_MAP.keys())}")

        account_id = self.repo.create(
            family_id=family_id,
            code=code,
            name=name,
            type=type,
            currency=currency,
            parent_id=parent_id,
            opening_balance=opening_balance,
        )

        # 审计日志
        self.audit.log(
            family_id=family_id,
            user="system",
            action="create",
            entity_type="account",
            entity_id=account_id,
            details={"code": code, "name": name, "type": type},
        )

        return self.repo.get(account_id)

    def get_account(self, account_id: str) -> Optional[Dict]:
        """获取账户"""
        return self.repo.get(account_id)

    def list_accounts(self, family_id: str) -> List[Dict]:
        """列出家庭所有账户"""
        return self.repo.list_by_family(family_id)

    def get_balance(self, account_id: str) -> Decimal:
        """获取账户余额"""
        return self.repo.get_balance(account_id)

    def get_trial_balance(self, family_id: str) -> Dict:
        """
        试算平衡 — 调用 FIN-001 引擎
        从 SQLite 读取账户和交易，灌入引擎计算
        """
        accounts = self.repo.list_by_family(family_id)

        # 灌入引擎
        for acc in accounts:
            self.engine.create_account(
                name=acc["name"],
                type=TYPE_MAP[acc["type"]],
                account_id=acc["id"],
                initial_balance=Decimal(acc["opening_balance"]),
            )

        # 读取交易并录入引擎
        txns = self.conn.execute(
            "SELECT * FROM fin4_transactions WHERE family_id = ? ORDER BY date",
            (family_id,)
        ).fetchall()

        for txn in txns:
            self.engine.record_transaction(
                debit_account_id=txn["debit_account_id"],
                credit_account_id=txn["credit_account_id"],
                amount=Decimal(txn["amount"]),
                date=txn["date"],
                note=txn["note"],
            )

        # 调用引擎试算平衡
        tb = self.engine.get_trial_balance()

        return {
            "debit_total": str(tb.debit_total),
            "credit_total": str(tb.credit_total),
            "is_balanced": tb.is_balanced,
            "account_count": len(accounts),
        }

    def get_account_tree(self, family_id: str) -> List[Dict]:
        """获取账户树（层级结构）"""
        accounts = self.repo.list_by_family(family_id)
        # 构建树
        roots = []
        children_map = {}
        for acc in accounts:
            acc["children"] = []
            acc["balance"] = str(self.repo.get_balance(acc["id"]))
            if acc["parent_id"]:
                children_map.setdefault(acc["parent_id"], []).append(acc)
            else:
                roots.append(acc)

        def attach_children(node):
            node["children"] = children_map.get(node["id"], [])
            for child in node["children"]:
                attach_children(child)

        for root in roots:
            attach_children(root)

        return roots
