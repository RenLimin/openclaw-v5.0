"""CSV 导入服务 — 智能分类 + 导入规则"""

import csv
import io
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional
from fin_l4.db.repositories import (
    ImportRuleRepository, CategoryRepository, AccountRepository,
    TransactionRepository, AuditLogRepository
)
from fin_l4.services.category_engine import CategoryEngine, CategoryRule


class ImportService:
    """CSV 导入 + 智能分类"""

    def __init__(self, conn):
        self.conn = conn
        self.rule_repo = ImportRuleRepository(conn)
        self.cat_repo = CategoryRepository(conn)
        self.account_repo = AccountRepository(conn)
        self.txn_repo = TransactionRepository(conn)
        self.audit = AuditLogRepository(conn)
        self._engine = None

    def _get_engine(self, family_id: str) -> CategoryEngine:
        """获取分类引擎（懒加载，混入用户规则）"""
        if self._engine is not None:
            return self._engine

        engine = CategoryEngine.default_rules()

        # 加载用户自定义规则
        user_rules = self.rule_repo.list_active(family_id)
        for rule in user_rules:
            engine.add_rule(CategoryRule(
                id=rule["id"],
                category_id=rule["category_id"],
                keywords=[kw.strip() for kw in rule["pattern"].split(",")],
                priority=rule.get("priority", 0) + 100,  # 用户规则优先
            ))

        self._engine = engine
        return engine

    def preview_csv(self, family_id: str, csv_content: str,
                    date_col: str = "date",
                    amount_col: str = "amount",
                    desc_col: str = "description") -> List[Dict]:
        """
        预览 CSV（不实际导入）
        返回每行的分类建议
        """
        engine = self._get_engine(family_id)
        reader = csv.DictReader(io.StringIO(csv_content))
        previews = []

        for row_num, row in enumerate(reader, start=2):
            date_str = row.get(date_col, "")
            amount_str = row.get(amount_col, "0")
            desc = row.get(desc_col, "")

            try:
                amount = Decimal(amount_str)
            except (InvalidOperation, ValueError):
                amount = Decimal("0")

            suggested_cat = engine.classify(desc, amount_str)
            cat = self.cat_repo.get(suggested_cat) if suggested_cat else None

            previews.append({
                "row": row_num,
                "date": date_str,
                "amount": amount_str,
                "description": desc,
                "suggested_category": suggested_cat,
                "category_name": cat["name"] if cat else "未分类",
                "type": "income" if amount > 0 else "expense" if amount < 0 else "zero",
            })

        return previews

    def import_csv(self, family_id: str, csv_content: str,
                   default_debit_id: str = None,
                   default_credit_id: str = None,
                   date_col: str = "date",
                   amount_col: str = "amount",
                   desc_col: str = "description",
                   category_col: str = "category") -> Dict:
        """
        执行 CSV 导入
        支持列映射 + 智能分类
        """
        engine = self._get_engine(family_id)
        reader = csv.DictReader(io.StringIO(csv_content))

        imported = 0
        errors = []
        categorized = 0

        for row_num, row in enumerate(reader, start=2):
            try:
                date_str = row.get(date_col, "").strip()
                amount_str = row.get(amount_col, "0").strip()
                desc = row.get(desc_col, "").strip()

                if not date_str or not amount_str:
                    errors.append(f"行 {row_num}: 缺少日期或金额")
                    continue

                amount = Decimal(amount_str)
                abs_amount = abs(amount)

                if abs_amount == 0:
                    continue

                # 智能分类
                cat_id = row.get(category_col, "").strip() or None
                if not cat_id:
                    cat_id = engine.classify(desc, amount_str)
                    if cat_id:
                        categorized += 1

                # 确定借贷账户
                if amount > 0:
                    # 收入：借=资产, 贷=收入
                    debit_id = default_debit_id or self._find_income_debit(family_id)
                    credit_id = default_credit_id or self._find_income_credit(family_id, cat_id)
                else:
                    # 支出：借=费用, 贷=资产
                    debit_id = default_debit_id or self._find_expense_debit(family_id, cat_id)
                    credit_id = default_credit_id or self._find_expense_credit(family_id)

                if not debit_id or not credit_id:
                    errors.append(f"行 {row_num}: 未配置默认账户映射")
                    continue

                # 只在 cat_id 是真实 DB category 时写入
                resolved_cat = None
                if cat_id and not cat_id.startswith("cat_"):
                    resolved_cat = cat_id

                self.txn_repo.create(
                    family_id=family_id,
                    date=date_str,
                    amount=str(abs_amount),
                    debit_account_id=debit_id,
                    credit_account_id=credit_id,
                    note=desc,
                    category_id=resolved_cat,
                    source="imported",
                )
                imported += 1

            except Exception as e:
                errors.append(f"行 {row_num}: {str(e)}")

        self.audit.log(
            family_id=family_id,
            user="system",
            action="import",
            entity_type="transaction",
            details={
                "imported": imported,
                "auto_categorized": categorized,
                "errors": len(errors),
            },
        )

        return {
            "imported": imported,
            "auto_categorized": categorized,
            "errors": errors,
        }

    def add_rule(self, family_id: str, pattern: str,
                 category_id: str, priority: int = 0) -> str:
        """添加导入规则"""
        return self.rule_repo.create(family_id, pattern, category_id, priority)

    def list_rules(self, family_id: str) -> List[Dict]:
        """列出导入规则"""
        return self.rule_repo.list_by_family(family_id)

    def _find_income_debit(self, family_id: str) -> Optional[str]:
        """找默认资产账户（银行）"""
        accounts = [a for a in self.account_repo.list_by_family(family_id) if a["type"] == "ASSET"]
        for acc in accounts:
            if "银行" in acc["name"] or "bank" in acc["name"].lower():
                return acc["id"]
        return accounts[0]["id"] if accounts else None

    def _find_income_credit(self, family_id: str, cat_id: str) -> Optional[str]:
        """找收入类账户"""
        accounts = [a for a in self.account_repo.list_by_family(family_id) if a["type"] == "INCOME"]
        return accounts[0]["id"] if accounts else None

    def _find_expense_debit(self, family_id: str, cat_id: str) -> Optional[str]:
        """找费用类账户"""
        accounts = [a for a in self.account_repo.list_by_family(family_id) if a["type"] == "EXPENSE"]
        return accounts[0]["id"] if accounts else None

    def _find_expense_credit(self, family_id: str) -> Optional[str]:
        """找默认资产账户（银行）"""
        return self._find_income_debit(family_id)
