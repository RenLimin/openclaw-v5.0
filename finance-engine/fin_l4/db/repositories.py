"""Repository 模式 — CRUD 操作封装"""

import json
import uuid
from typing import List, Optional, Dict, Any
from decimal import Decimal


def _uid() -> str:
    return str(uuid.uuid4())


class BaseRepository:
    """基类 Repository"""

    def __init__(self, conn, table: str):
        self.conn = conn
        self.table = table

    def _row_to_dict(self, row) -> Optional[Dict]:
        if row is None:
            return None
        return dict(row)

    def _rows_to_list(self, rows) -> List[Dict]:
        return [dict(r) for r in rows]


class FamilyRepository(BaseRepository):
    def __init__(self, conn):
        super().__init__(conn, "fin4_family")

    def create(self, name: str, currency: str = "CNY") -> str:
        uid = _uid()
        self.conn.execute(
            f"INSERT INTO {self.table} (id, name, currency) VALUES (?, ?, ?)",
            (uid, name, currency)
        )
        self.conn.commit()
        return uid

    def get(self, family_id: str) -> Optional[Dict]:
        row = self.conn.execute(
            f"SELECT * FROM {self.table} WHERE id = ?", (family_id,)
        ).fetchone()
        return self._row_to_dict(row)

    def list_all(self) -> List[Dict]:
        rows = self.conn.execute(f"SELECT * FROM {self.table}").fetchall()
        return self._rows_to_list(rows)


class AccountRepository(BaseRepository):
    def __init__(self, conn):
        super().__init__(conn, "fin4_accounts")

    def create(self, family_id: str, code: str, name: str, type: str,
               currency: str = "CNY", parent_id: str = None,
               opening_balance: str = "0") -> str:
        uid = _uid()
        self.conn.execute(
            f"INSERT INTO {self.table} (id, family_id, code, name, type, currency, parent_id, opening_balance) "
            f"VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (uid, family_id, code, name, type, currency, parent_id, opening_balance)
        )
        self.conn.commit()
        return uid

    def get(self, account_id: str) -> Optional[Dict]:
        row = self.conn.execute(
            f"SELECT * FROM {self.table} WHERE id = ?", (account_id,)
        ).fetchone()
        return self._row_to_dict(row)

    def list_by_family(self, family_id: str) -> List[Dict]:
        rows = self.conn.execute(
            f"SELECT * FROM {self.table} WHERE family_id = ? ORDER BY code",
            (family_id,)
        ).fetchall()
        return self._rows_to_list(rows)

    def get_balance(self, account_id: str) -> Decimal:
        """计算账户当前余额（期初 + 借贷差额）"""
        account = self.get(account_id)
        if not account:
            return Decimal("0")

        opening = Decimal(account["opening_balance"])

        # 借方总额
        debits = self.conn.execute(
            f"SELECT COALESCE(SUM(CAST(amount AS DECIMAL)), 0) as total "
            f"FROM fin4_transactions WHERE debit_account_id = ?",
            (account_id,)
        ).fetchone()["total"]

        # 贷方总额
        credits = self.conn.execute(
            f"SELECT COALESCE(SUM(CAST(amount AS DECIMAL)), 0) as total "
            f"FROM fin4_transactions WHERE credit_account_id = ?",
            (account_id,)
        ).fetchone()["total"]

        # 根据账户类型确定余额方向
        if account["type"] in ("ASSET", "EXPENSE"):
            return opening + Decimal(str(debits)) - Decimal(str(credits))
        else:
            return opening + Decimal(str(credits)) - Decimal(str(debits))


class TransactionRepository(BaseRepository):
    def __init__(self, conn):
        super().__init__(conn, "fin4_transactions")

    def create(self, family_id: str, date: str, amount: str,
               debit_account_id: str, credit_account_id: str,
               note: str = None, category_id: str = None,
               source: str = "manual") -> str:
        uid = _uid()
        self.conn.execute(
            f"INSERT INTO {self.table} (id, family_id, date, amount, note, category_id, "
            f"debit_account_id, credit_account_id, source) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (uid, family_id, date, amount, note, category_id,
             debit_account_id, credit_account_id, source)
        )
        self.conn.commit()
        return uid

    def list_by_family(self, family_id: str, account_id: str = None,
                       from_date: str = None, to_date: str = None,
                       limit: int = 100) -> List[Dict]:
        sql = f"SELECT * FROM {self.table} WHERE family_id = ?"
        params = [family_id]

        if account_id:
            sql += " AND (debit_account_id = ? OR credit_account_id = ?)"
            params.extend([account_id, account_id])
        if from_date:
            sql += " AND date >= ?"
            params.append(from_date)
        if to_date:
            sql += " AND date <= ?"
            params.append(to_date)

        sql += " ORDER BY date DESC, created_at DESC LIMIT ?"
        params.append(limit)

        rows = self.conn.execute(sql, params).fetchall()
        return self._rows_to_list(rows)

    def list_by_account(self, account_id: str) -> List[Dict]:
        rows = self.conn.execute(
            f"SELECT * FROM {self.table} "
            f"WHERE debit_account_id = ? OR credit_account_id = ? "
            f"ORDER BY date DESC",
            (account_id, account_id)
        ).fetchall()
        return self._rows_to_list(rows)


class CategoryRepository(BaseRepository):
    def __init__(self, conn):
        super().__init__(conn, "fin4_categories")

    def create(self, family_id: str, name: str, type: str,
               parent_id: str = None, color: str = None, icon: str = None) -> str:
        uid = _uid()
        self.conn.execute(
            f"INSERT INTO {self.table} (id, family_id, name, type, parent_id, color, icon) "
            f"VALUES (?, ?, ?, ?, ?, ?, ?)",
            (uid, family_id, name, type, parent_id, color, icon)
        )
        self.conn.commit()
        return uid

    def list_by_family(self, family_id: str) -> List[Dict]:
        rows = self.conn.execute(
            f"SELECT * FROM {self.table} WHERE family_id = ?",
            (family_id,)
        ).fetchall()
        return self._rows_to_list(rows)
    def get(self, category_id: str) -> Optional[Dict]:
        """按 ID 获取分类"""
        row = self.conn.execute(
            f"SELECT * FROM {self.table} WHERE id = ?",
            (category_id,)
        ).fetchone()
        return dict(row) if row else None




class BudgetRepository(BaseRepository):
    def __init__(self, conn):
        super().__init__(conn, "fin4_budgets")

    def upsert(self, family_id: str, category_id: str,
               month: str, amount: str) -> str:
        """创建或更新预算（按月+分类唯一）"""
        existing = self.conn.execute(
            f"SELECT id FROM {self.table} "
            f"WHERE family_id = ? AND category_id = ? AND start_date = ?",
            (family_id, category_id, month)
        ).fetchone()

        uid = _uid()
        if existing:
            self.conn.execute(
                f"UPDATE {self.table} SET amount = ? WHERE id = ?",
                (amount, existing["id"])
            )
            uid = existing["id"]
        else:
            self.conn.execute(
                f"INSERT INTO {self.table} (id, family_id, category_id, amount, period, start_date) "
                f"VALUES (?, ?, ?, ?, 'month', ?)",
                (uid, family_id, category_id, amount, month)
            )
        self.conn.commit()
        return uid

    def get(self, family_id: str, category_id: str, month: str) -> Optional[Dict]:
        row = self.conn.execute(
            f"SELECT * FROM {self.table} "
            f"WHERE family_id = ? AND category_id = ? AND start_date = ?",
            (family_id, category_id, month)
        ).fetchone()
        return dict(row) if row else None

    def list_by_family(self, family_id: str, month: str = None) -> List[Dict]:
        if month:
            rows = self.conn.execute(
                f"SELECT * FROM {self.table} WHERE family_id = ? AND start_date = ?",
                (family_id, month)
            ).fetchall()
        else:
            rows = self.conn.execute(
                f"SELECT * FROM {self.table} WHERE family_id = ?",
                (family_id,)
            ).fetchall()
        return self._rows_to_list(rows)


class ImportRuleRepository(BaseRepository):
    def __init__(self, conn):
        super().__init__(conn, "fin4_import_rules")

    def create(self, family_id: str, pattern: str,
               category_id: str = None, priority: int = 0) -> str:
        uid = _uid()
        self.conn.execute(
            f"INSERT INTO {self.table} (id, family_id, pattern, category_id, priority) "
            f"VALUES (?, ?, ?, ?, ?)",
            (uid, family_id, pattern, category_id, priority)
        )
        self.conn.commit()
        return uid

    def list_active(self, family_id: str) -> List[Dict]:
        rows = self.conn.execute(
            f"SELECT * FROM {self.table} "
            f"WHERE family_id = ? AND is_active = 1 "
            f"ORDER BY priority DESC",
            (family_id,)
        ).fetchall()
        return self._rows_to_list(rows)

    def list_by_family(self, family_id: str) -> List[Dict]:
        rows = self.conn.execute(
            f"SELECT * FROM {self.table} WHERE family_id = ? ORDER BY priority DESC",
            (family_id,)
        ).fetchall()
        return self._rows_to_list(rows)

    def set_active(self, rule_id: str, active: bool):
        self.conn.execute(
            f"UPDATE {self.table} SET is_active = ? WHERE id = ?",
            (1 if active else 0, rule_id)
        )
        self.conn.commit()

    def delete(self, rule_id: str):
        self.conn.execute(f"DELETE FROM {self.table} WHERE id = ?", (rule_id,))
        self.conn.commit()


class LoanRepository(BaseRepository):
    def __init__(self, conn):
        super().__init__(conn, "fin4_loans")

    def create(self, family_id: str, name: str, principal: str,
               annual_rate: str, term_months: int, method: str,
               start_date: str, extra_terms: dict = None) -> str:
        uid = _uid()
        self.conn.execute(
            f"INSERT INTO {self.table} (id, family_id, name, principal, annual_rate, "
            f"term_months, method, start_date, extra_terms) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (uid, family_id, name, principal, annual_rate, term_months,
             method, start_date, json.dumps(extra_terms) if extra_terms else None)
        )
        self.conn.commit()
        return uid

    def list_by_family(self, family_id: str) -> List[Dict]:
        rows = self.conn.execute(
            f"SELECT * FROM {self.table} WHERE family_id = ?",
            (family_id,)
        ).fetchall()
        return self._rows_to_list(rows)

    def get(self, loan_id: str) -> Optional[Dict]:
        row = self.conn.execute(
            f"SELECT * FROM {self.table} WHERE id = ?", (loan_id,)
        ).fetchone()
        return self._row_to_dict(row)

    def update_principal(self, loan_id: str, new_principal: str):
        self.conn.execute(
            f"UPDATE {self.table} SET principal = ? WHERE id = ?",
            (new_principal, loan_id)
        )
        self.conn.commit()

    def update_status(self, loan_id: str, status: str):
        self.conn.execute(
            f"UPDATE {self.table} SET status = ? WHERE id = ?",
            (status, loan_id)
        )
        self.conn.commit()


class InsuranceRepository(BaseRepository):
    def __init__(self, conn):
        super().__init__(conn, "fin4_insurance_policies")

    def update_status(self, policy_id: str, status: str):
        self.conn.execute(
            f"UPDATE {self.table} SET status = ? WHERE id = ?",
            (status, policy_id)
        )
        self.conn.commit()

    def create(self, family_id: str, product_name: str, policy_type: str,
               sum_assured: str, annual_premium: str, term_years: int,
               payment_years: int, insured_name: str = None,
               insured_age: int = None, insured_gender: str = None,
               start_date: str = None, extra_terms: dict = None) -> str:
        uid = _uid()
        self.conn.execute(
            f"INSERT INTO {self.table} (id, family_id, product_name, policy_type, "
            f"sum_assured, annual_premium, term_years, payment_years, "
            f"insured_name, insured_age, insured_gender, start_date, extra_terms) "
            f"VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (uid, family_id, product_name, policy_type, sum_assured,
             annual_premium, term_years, payment_years,
             insured_name, insured_age, insured_gender, start_date,
             json.dumps(extra_terms) if extra_terms else None)
        )
        self.conn.commit()
        return uid


    def list_by_family(self, family_id: str) -> List[Dict]:
        rows = self.conn.execute(
            f"SELECT * FROM {self.table} WHERE family_id = ?",
            (family_id,)
        ).fetchall()
        return self._rows_to_list(rows)

    def get(self, policy_id: str) -> Optional[Dict]:
        row = self.conn.execute(
            f"SELECT * FROM {self.table} WHERE id = ?", (policy_id,)
        ).fetchone()
        return self._row_to_dict(row)


class PortfolioRepository(BaseRepository):
    def __init__(self, conn):
        super().__init__(conn, "fin4_portfolios")

    def create(self, family_id: str, name: str, base_currency: str = "CNY") -> str:
        uid = _uid()
        self.conn.execute(
            f"INSERT INTO {self.table} (id, family_id, name, base_currency) VALUES (?, ?, ?, ?)",
            (uid, family_id, name, base_currency)
        )
        self.conn.commit()
        return uid

    def list_by_family(self, family_id: str) -> List[Dict]:
        rows = self.conn.execute(
            f"SELECT * FROM {self.table} WHERE family_id = ?",
            (family_id,)
        ).fetchall()
        return self._rows_to_list(rows)


class HoldingRepository(BaseRepository):
    def __init__(self, conn):
        super().__init__(conn, "fin4_holdings")

    def create(self, portfolio_id: str, asset_type: str, asset_name: str,
               asset_code: str, shares: str, cost_basis_price: str,
               current_price: str = None) -> str:
        uid = _uid()
        self.conn.execute(
            f"INSERT INTO {self.table} (id, portfolio_id, asset_type, asset_name, "
            f"asset_code, shares, cost_basis_price, current_price) "
            f"VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (uid, portfolio_id, asset_type, asset_name, asset_code,
             shares, cost_basis_price, current_price or cost_basis_price)
        )
        self.conn.commit()
        return uid

    def list_by_portfolio(self, portfolio_id: str) -> List[Dict]:
        rows = self.conn.execute(
            f"SELECT * FROM {self.table} WHERE portfolio_id = ?",
            (portfolio_id,)
        ).fetchall()
        return self._rows_to_list(rows)

    def update_price(self, holding_id: str, current_price: str):
        self.conn.execute(
            f"UPDATE {self.table} SET current_price = ?, updated_at = CURRENT_TIMESTAMP "
            f"WHERE id = ?",
            (current_price, holding_id)
        )
        self.conn.commit()


class RateSnapshotRepository(BaseRepository):
    def __init__(self, conn):
        super().__init__(conn, "fin4_rate_snapshots")

    def save(self, rate_type: str, rate: str, term: str = None,
             effective_date: str = None, source: str = None) -> str:
        uid = _uid()
        self.conn.execute(
            f"INSERT INTO {self.table} (id, rate_type, term, rate, effective_date, source) "
            f"VALUES (?, ?, ?, ?, ?, ?)",
            (uid, rate_type, term, rate, effective_date, source)
        )
        self.conn.commit()
        return uid

    def get_latest(self, rate_type: str, term: str = None) -> Optional[Dict]:
        sql = f"SELECT * FROM {self.table} WHERE rate_type = ?"
        params = [rate_type]
        if term:
            sql += " AND term = ?"
            params.append(term)
        sql += " ORDER BY effective_date DESC, fetched_at DESC LIMIT 1"
        row = self.conn.execute(sql, params).fetchone()
        return self._row_to_dict(row)

    def get_history(self, rate_type: str, term: str = None, limit: int = 50) -> List[Dict]:
        sql = f"SELECT * FROM {self.table} WHERE rate_type = ?"
        params = [rate_type]
        if term:
            sql += " AND term = ?"
            params.append(term)
        sql += " ORDER BY effective_date DESC LIMIT ?"
        params.append(limit)
        rows = self.conn.execute(sql, params).fetchall()
        return self._rows_to_list(rows)


class IntegrationRepository(BaseRepository):
    def __init__(self, conn):
        super().__init__(conn, "fin4_integrations")

    def create(self, family_id: str, name: str, link_type: str,
               url: str, username_hint: str = None, note: str = None) -> str:
        uid = _uid()
        self.conn.execute(
            f"INSERT INTO {self.table} (id, family_id, name, link_type, url, username_hint, note) "
            f"VALUES (?, ?, ?, ?, ?, ?, ?)",
            (uid, family_id, name, link_type, url, username_hint, note)
        )
        self.conn.commit()
        return uid

    def list_by_family(self, family_id: str) -> List[Dict]:
        rows = self.conn.execute(
            f"SELECT * FROM {self.table} WHERE family_id = ? ORDER BY link_type",
            (family_id,)
        ).fetchall()
        return self._rows_to_list(rows)

    def delete(self, integration_id: str):
        self.conn.execute(f"DELETE FROM {self.table} WHERE id = ?", (integration_id,))
        self.conn.commit()


class SecurityConfigRepository(BaseRepository):
    def __init__(self, conn):
        super().__init__(conn, "fin4_security_config")

    def get(self, family_id: str) -> Optional[Dict]:
        row = self.conn.execute(
            f"SELECT * FROM {self.table} WHERE family_id = ?", (family_id,)
        ).fetchone()
        return self._row_to_dict(row)

    def upsert(self, family_id: str, **kwargs):
        existing = self.get(family_id)
        if existing:
            sets = ", ".join(f"{k} = ?" for k in kwargs)
            values = list(kwargs.values()) + [family_id]
            self.conn.execute(f"UPDATE {self.table} SET {sets} WHERE id = ?", values)
        else:
            fields = ["family_id"] + list(kwargs.keys())
            placeholders = ", ".join(["?"] * len(fields))
            values = [family_id] + list(kwargs.values())
            self.conn.execute(
                f"INSERT INTO fin4_security_config (id, {', '.join(fields)}) "
                f"VALUES (?, {placeholders})",
                [_uid()] + values
            )
        self.conn.commit()


class AuditLogRepository(BaseRepository):
    def __init__(self, conn):
        super().__init__(conn, "fin4_audit_log")

    def log(self, family_id: str, user: str, action: str,
            entity_type: str = None, entity_id: str = None,
            details: dict = None, ip: str = None) -> str:
        uid = _uid()
        self.conn.execute(
            f"INSERT INTO {self.table} (id, family_id, user, action, entity_type, entity_id, details, ip) "
            f"VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (uid, family_id, user, action, entity_type, entity_id,
             json.dumps(details) if details else None, ip)
        )
        self.conn.commit()
        return uid

    def list_by_family(self, family_id: str, limit: int = 100) -> List[Dict]:
        rows = self.conn.execute(
            f"SELECT * FROM {self.table} WHERE family_id = ? ORDER BY created_at DESC LIMIT ?",
            (family_id, limit)
        ).fetchall()
        return self._rows_to_list(rows)
