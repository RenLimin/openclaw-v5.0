"""
FIN-001 账户体系 — 复式记账引擎

纯函数式设计，不持有状态，不访问数据库。
L4 层负责持久化，L3 只负责计算。
"""

from decimal import Decimal, ROUND_HALF_UP
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Tuple
from datetime import date, datetime
import uuid


# ========== 枚举 ==========

class AccountType(Enum):
    """会计科目类型"""
    ASSET = "asset"           # 资产（借增贷减）
    LIABILITY = "liability"   # 负债（贷增借减）
    INCOME = "income"         # 收入（贷增借减）
    EQUITY = "equity"         # 权益（贷增借减）
    EXPENSE = "expense"       # 费用（借增贷减）


class DebitCredit(Enum):
    """借贷方向"""
    DEBIT = "debit"    # 借方
    CREDIT = "credit"  # 贷方


# ========== 数据模型 ==========

@dataclass
class Account:
    """账户"""
    id: str
    name: str
    type: AccountType
    currency: str = "CNY"
    parent_id: Optional[str] = None
    balance: Decimal = field(default_factory=lambda: Decimal("0"))
    created_at: date = field(default_factory=date.today)
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if isinstance(self.balance, (int, float, str)):
            self.balance = Decimal(str(self.balance)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@dataclass
class Transaction:
    """交易分录"""
    id: str
    date: date
    debit_account_id: str
    credit_account_id: str
    amount: Decimal
    note: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    source: str = "manual"  # manual / imported / system

    def __post_init__(self):
        if isinstance(self.amount, (int, float, str)):
            self.amount = Decimal(str(self.amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if self.amount <= 0:
            raise ValueError(f"交易金额必须 > 0，收到: {self.amount}")


@dataclass
class AccountBalance:
    """账户余额明细"""
    account_id: str
    account_name: str
    account_type: AccountType
    debit_balance: Decimal
    credit_balance: Decimal
    net_balance: Decimal


@dataclass
class TrialBalance:
    """试算平衡表"""
    date: date
    debit_total: Decimal
    credit_total: Decimal
    is_balanced: bool
    accounts: List[AccountBalance]


@dataclass
class ReconciliationItem:
    """对账差异项"""
    date: date
    description: str
    amount: Decimal
    in_ours: bool       # 在我们账上
    in_theirs: bool     # 在对方账上


@dataclass
class ReconciliationResult:
    """对账结果"""
    account_id: str
    our_balance: Decimal
    their_balance: Decimal
    difference: Decimal
    is_reconciled: bool
    items: List[ReconciliationItem]


# ========== 核心引擎 ==========

class AccountingEngine:
    """
    复式记账引擎

    纯内存操作，不持有持久化状态。
    L4 层负责加载/保存账户和交易数据。
    """

    def __init__(self):
        self._accounts: Dict[str, Account] = {}
        self._transactions: List[Transaction] = []
        # 创建系统级"初始余额"账户，用于配平初始余额
        self._opening_balance_account = Account(
            id="SYS-OPENING-BALANCE",
            name="初始余额",
            type=AccountType.EQUITY,
        )
        self._accounts["SYS-OPENING-BALANCE"] = self._opening_balance_account

    # ---------- 账户管理 ----------

    def create_account(
        self,
        name: str,
        type: AccountType,
        currency: str = "CNY",
        initial_balance: Decimal = Decimal("0"),
        parent_id: Optional[str] = None,
        account_id: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> Account:
        """创建账户"""
        if parent_id and parent_id not in self._accounts:
            raise ValueError(f"父账户不存在: {parent_id}")

        acc_id = account_id or f"ACC-{uuid.uuid4().hex[:8].upper()}"
        if acc_id in self._accounts:
            raise ValueError(f"账户 ID 已存在: {acc_id}")

        initial = _to_decimal(initial_balance)
        account = Account(
            id=acc_id,
            name=name,
            type=type,
            currency=currency,
            parent_id=parent_id,
            balance=Decimal("0"),
            metadata=metadata or {},
        )
        self._accounts[acc_id] = account

        # 初始余额配平：通过系统账户借贷相等
        # 日期设为 date.min，确保 as_of_date 查询时始终包含
        if initial != 0:
            if type in (AccountType.ASSET, AccountType.EXPENSE):
                opening_txn = Transaction(
                    id=f"TXN-OPEN-{acc_id}",
                    date=date.min,
                    debit_account_id=acc_id,
                    credit_account_id="SYS-OPENING-BALANCE",
                    amount=initial,
                    note=f"初始余额: {name}",
                    source="system",
                )
            else:
                opening_txn = Transaction(
                    id=f"TXN-OPEN-{acc_id}",
                    date=date.min,
                    debit_account_id="SYS-OPENING-BALANCE",
                    credit_account_id=acc_id,
                    amount=initial,
                    note=f"初始余额: {name}",
                    source="system",
                )
            self._transactions.append(opening_txn)
            self._execute_balance_update(opening_txn)

        return account

    def get_account(self, account_id: str) -> Account:
        """获取账户"""
        if account_id not in self._accounts:
            raise ValueError(f"账户不存在: {account_id}")
        return self._accounts[account_id]

    def get_accounts_by_type(self, type: AccountType) -> List[Account]:
        """按类型获取账户"""
        return [a for a in self._accounts.values() if a.type == type]

    def get_account_tree(self, root_id: Optional[str] = None) -> dict:
        """获取账户树"""
        children: Dict[Optional[str], List[Account]] = {}
        for acc in self._accounts.values():
            if acc.id == "SYS-OPENING-BALANCE":
                continue
            children.setdefault(acc.parent_id, []).append(acc)

        def build_node(acc: Account) -> dict:
            return {
                "id": acc.id,
                "name": acc.name,
                "type": acc.type.value,
                "balance": str(acc.balance),
                "children": [build_node(c) for c in children.get(acc.id, [])]
            }

        if root_id:
            return build_node(self._accounts[root_id])
        # 返回森林（多个根节点）
        roots = children.get(None, [])
        return {"roots": [build_node(r) for r in roots]}

    # ---------- 交易录入 ----------

    def record_transaction(
        self,
        debit_account_id: str,
        credit_account_id: str,
        amount,
        txn_date: Optional[date] = None,
        note: str = "",
        source: str = "manual",
        txn_id: Optional[str] = None,
    ) -> Transaction:
        """
        记录一笔交易（一借一贷）

        支持扩展为多借多贷：调用方多次调用，确保借方合计=贷方合计
        """
        amount = _to_decimal(amount)

        # 验证账户存在
        if debit_account_id not in self._accounts:
            raise ValueError(f"借方账户不存在: {debit_account_id}")
        if credit_account_id not in self._accounts:
            raise ValueError(f"贷方账户不存在: {credit_account_id}")
        if debit_account_id == credit_account_id:
            raise ValueError("借贷不能为同一账户")

        txn = Transaction(
            id=txn_id or f"TXN-{uuid.uuid4().hex[:8].upper()}",
            date=txn_date or date.today(),
            debit_account_id=debit_account_id,
            credit_account_id=credit_account_id,
            amount=amount,
            note=note,
            source=source,
        )
        self._transactions.append(txn)
        self._execute_balance_update(txn)
        return txn

    def _execute_balance_update(self, txn: Transaction):
        """根据账户类型更新余额"""
        amount = txn.amount
        debit_acc = self._accounts[txn.debit_account_id]
        credit_acc = self._accounts[txn.credit_account_id]
        if debit_acc.type in (AccountType.ASSET, AccountType.EXPENSE):
            debit_acc.balance += amount
        else:
            debit_acc.balance -= amount
        if credit_acc.type in (AccountType.LIABILITY, AccountType.INCOME, AccountType.EQUITY):
            credit_acc.balance += amount
        else:
            credit_acc.balance -= amount

        return txn

    def record_compound_transaction(
        self,
        entries: List[Tuple[str, str, Decimal]],  # [(debit_id, credit_id, amount), ...]
        txn_date: Optional[date] = None,
        note: str = "",
    ) -> List[Transaction]:
        """
        记录复合分录（多借多贷）

        自动验证借方合计 = 贷方合计
        """
        # 验证借贷平衡
        debit_total = Decimal("0")
        credit_total = Decimal("0")
        for debit_id, credit_id, amount in entries:
            amt = _to_decimal(amount)
            debit_total += amt
            credit_total += amt

        if debit_total != credit_total:
            raise ValueError(
                f"借贷不平衡: 借方 {debit_total} ≠ 贷方 {credit_total}"
            )

        txns = []
        for debit_id, credit_id, amount in entries:
            txn = self.record_transaction(
                debit_account_id=debit_id,
                credit_account_id=credit_id,
                amount=amount,
                txn_date=txn_date,
                note=note,
            )
            txns.append(txn)
        return txns

    # ---------- 余额查询 ----------

    def get_account_balance(self, account_id: str, as_of_date: Optional[date] = None) -> Decimal:
        """
        获取账户余额

        如果指定日期，则只计算该日期及之前的交易（含初始余额）。
        """
        if account_id not in self._accounts:
            raise ValueError(f"账户不存在: {account_id}")

        if as_of_date is None:
            return self._accounts[account_id].balance

        # 从 0 开始正向累加所有 <= as_of_date 的交易
        balance = Decimal("0")
        for txn in self._transactions:
            if txn.date <= as_of_date:
                if txn.debit_account_id == account_id:
                    debit_acc = self._accounts.get(txn.debit_account_id)
                    if debit_acc and debit_acc.type in (AccountType.ASSET, AccountType.EXPENSE):
                        balance += txn.amount
                    else:
                        balance -= txn.amount
                if txn.credit_account_id == account_id:
                    credit_acc = self._accounts.get(txn.credit_account_id)
                    if credit_acc and credit_acc.type in (AccountType.LIABILITY, AccountType.INCOME, AccountType.EQUITY):
                        balance += txn.amount
                    else:
                        balance -= txn.amount

        return balance.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # ---------- 试算平衡 ----------

    def get_trial_balance(self, as_of_date: Optional[date] = None) -> TrialBalance:
        """
        生成试算平衡表

        验证：所有账户借方余额合计 = 贷方余额合计
        """
        balances: List[AccountBalance] = []
        total_debit = Decimal("0")
        total_credit = Decimal("0")

        for acc in self._accounts.values():
            if acc.id == "SYS-OPENING-BALANCE":
                continue
            bal = self.get_account_balance(acc.id, as_of_date)

            # 根据账户类型判断正常方向
            if acc.type in (AccountType.ASSET, AccountType.EXPENSE):
                # 资产/费用类：借方余额为正
                if bal >= 0:
                    debit_bal = bal
                    credit_bal = Decimal("0")
                else:
                    debit_bal = Decimal("0")
                    credit_bal = -bal
            else:
                # 负债/收入/权益类：贷方余额为正
                if bal >= 0:
                    debit_bal = Decimal("0")
                    credit_bal = bal
                else:
                    debit_bal = -bal
                    credit_bal = Decimal("0")

            balances.append(AccountBalance(
                account_id=acc.id,
                account_name=acc.name,
                account_type=acc.type,
                debit_balance=debit_bal.quantize(Decimal("0.01")),
                credit_balance=credit_bal.quantize(Decimal("0.01")),
                net_balance=bal.quantize(Decimal("0.01")),
            ))

            total_debit += debit_bal
            total_credit += credit_bal

        total_debit = total_debit.quantize(Decimal("0.01"))
        total_credit = total_credit.quantize(Decimal("0.01"))

        return TrialBalance(
            date=as_of_date or date.today(),
            debit_total=total_debit,
            credit_total=total_credit,
            is_balanced=(total_debit == total_credit),
            accounts=balances,
        )

    # ---------- 对账 ----------

    def reconcile_account(
        self,
        account_id: str,
        external_statement: List[Tuple[date, str, Decimal]],  # [(date, description, amount), ...]
    ) -> ReconciliationResult:
        """
        对账：账户余额 vs 外部对账单

        external_statement 中的 amount：正数=借方发生，负数=贷方发生
        """
        if account_id not in self._accounts:
            raise ValueError(f"账户不存在: {account_id}")

        our_balance = self.get_account_balance(account_id)

        # 计算外部账单余额
        their_balance = Decimal("0")
        for _, _, amt in external_statement:
            their_balance += _to_decimal(amt)
        their_balance = their_balance.quantize(Decimal("0.01"))

        # 匹配交易
        our_txns = [
            txn for txn in self._transactions
            if txn.debit_account_id == account_id or txn.credit_account_id == account_id
        ]

        items: List[ReconciliationItem] = []

        # 简单匹配：按金额匹配
        matched_external = set()
        for txn in our_txns:
            matched = False
            for i, (ed, desc, ea) in enumerate(external_statement):
                if i in matched_external:
                    continue
                ea_dec = _to_decimal(ea)
                # 借方交易匹配正数，贷方交易匹配负数
                if txn.debit_account_id == account_id and ea_dec == txn.amount:
                    matched_external.add(i)
                    matched = True
                    break
                elif txn.credit_account_id == account_id and ea_dec == -txn.amount:
                    matched_external.add(i)
                    matched = True
                    break
            if not matched:
                items.append(ReconciliationItem(
                    date=txn.date,
                    description=txn.note or f"交易 {txn.id}",
                    amount=txn.amount if txn.debit_account_id == account_id else -txn.amount,
                    in_ours=True,
                    in_theirs=False,
                ))

        # 未匹配的外部项目
        for i, (ed, desc, ea) in enumerate(external_statement):
            if i not in matched_external:
                items.append(ReconciliationItem(
                    date=ed,
                    description=desc,
                    amount=_to_decimal(ea),
                    in_ours=False,
                    in_theirs=True,
                ))

        difference = (our_balance - their_balance).quantize(Decimal("0.01"))

        return ReconciliationResult(
            account_id=account_id,
            our_balance=our_balance,
            their_balance=their_balance,
            difference=difference,
            is_reconciled=(difference == 0),
            items=items,
        )

    # ---------- 工具方法 ----------

    def get_all_transactions(self) -> List[Transaction]:
        """获取所有交易"""
        return list(self._transactions)

    def get_all_accounts(self) -> List[Account]:
        """获取所有账户（不含系统账户）"""
        return [a for a in self._accounts.values() if a.id != "SYS-OPENING-BALANCE"]


# ========== 辅助函数 ==========

def _to_decimal(value) -> Decimal:
    """转换为 Decimal，避免浮点误差"""
    if isinstance(value, Decimal):
        return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
