"""REST API 路由"""

from fastapi import APIRouter, HTTPException
from typing import Dict, List, Optional
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1")


# ========== 请求模型 ==========

class CreateFamilyRequest(BaseModel):
    name: str
    currency: str = "CNY"


class CreateAccountRequest(BaseModel):
    code: str
    name: str
    type: str  # ASSET/LIABILITY/EQUITY/INCOME/EXPENSE
    currency: str = "CNY"
    parent_id: str = None
    opening_balance: str = "0"


class RecordTxnRequest(BaseModel):
    date: str
    amount: str
    debit_account_id: str
    credit_account_id: str
    note: str = None
    category_id: str = None


class CreateLoanRequest(BaseModel):
    name: str
    principal: str
    annual_rate: str
    term_months: int
    method: str = "equal_payment"
    start_date: str = None


class CreateInsuranceRequest(BaseModel):
    product_name: str
    policy_type: str
    sum_assured: str
    annual_premium: str
    term_years: int
    payment_years: int
    insured_name: str = None
    insured_age: int = None
    insured_gender: str = None


class CreatePortfolioRequest(BaseModel):
    name: str
    base_currency: str = "CNY"


class BuyHoldingRequest(BaseModel):
    asset_type: str
    asset_name: str
    asset_code: str
    shares: str
    price: str


class AddIntegrationRequest(BaseModel):
    name: str
    link_type: str  # bank/broker/fund/other
    url: str
    username_hint: str = None
    note: str = None


# ========== 服务实例获取 ==========

def _get_services():
    """获取服务实例（延迟导入避免循环）"""
    from fin_l4.db import get_db
    from fin_l4.services.account_svc import AccountService
    from fin_l4.services.txn_svc import TransactionService
    from fin_l4.services.loan_svc import LoanService
    from fin_l4.services.insurance_svc import InsuranceService
    from fin_l4.services.portfolio_svc import PortfolioService
    from fin_l4.services.report_svc import ReportService
    from fin_l4.services.advise_svc import AdviseService
    from fin_l4.services.rate_svc import RateService

    conn = get_db()
    return {
        "account": AccountService(conn),
        "txn": TransactionService(conn),
        "loan": LoanService(conn),
        "insurance": InsuranceService(conn),
        "portfolio": PortfolioService(conn),
        "report": ReportService(conn),
        "advise": AdviseService(conn),
        "rate": RateService(conn),
        "conn": conn,
    }


# ========== 家庭 ==========

@router.post("/families")
def create_family(req: CreateFamilyRequest):
    from fin_l4.db import get_db
    from fin_l4.db.repositories import FamilyRepository
    conn = get_db()
    repo = FamilyRepository(conn)
    family_id = repo.create(req.name, req.currency)
    return {"id": family_id, "name": req.name}


@router.get("/families")
def list_families():
    from fin_l4.db import get_db
    from fin_l4.db.repositories import FamilyRepository
    conn = get_db()
    repo = FamilyRepository(conn)
    return repo.list_all()


# ========== 账户 ==========

@router.post("/accounts")
def create_account(req: CreateAccountRequest):
    svc = _get_services()
    family_id = "default"  # TODO: 从 session 获取
    try:
        result = svc["account"].create_account(
            family_id=family_id,
            code=req.code,
            name=req.name,
            type=req.type,
            currency=req.currency,
            parent_id=req.parent_id,
            opening_balance=req.opening_balance,
        )
        return result
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/accounts")
def list_accounts():
    svc = _get_services()
    return svc["account"].list_accounts("default")


@router.get("/accounts/trial-balance")
def trial_balance():
    svc = _get_services()
    return svc["account"].get_trial_balance("default")


# ========== 交易 ==========

@router.post("/transactions")
def record_txn(req: RecordTxnRequest):
    svc = _get_services()
    try:
        return svc["txn"].record(
            family_id="default",
            date_str=req.date,
            amount=req.amount,
            debit_account_id=req.debit_account_id,
            credit_account_id=req.credit_account_id,
            note=req.note,
            category_id=req.category_id,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/transactions")
def list_transactions(account_id: str = None, from_date: str = None,
                     to_date: str = None, limit: int = 100):
    svc = _get_services()
    return svc["txn"].list_transactions("default", account_id, from_date, to_date, limit)


# ========== 贷款 ==========

@router.post("/loans")
def create_loan(req: CreateLoanRequest):
    svc = _get_services()
    try:
        return svc["loan"].create_loan(
            family_id="default",
            name=req.name,
            principal=req.principal,
            annual_rate=req.annual_rate,
            term_months=req.term_months,
            method=req.method,
            start_date=req.start_date,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/loans")
def list_loans():
    svc = _get_services()
    return svc["loan"].list_loans("default")


@router.get("/loans/{loan_id}/schedule")
def loan_schedule(loan_id: str):
    svc = _get_services()
    try:
        return svc["loan"].get_schedule(loan_id)
    except ValueError as e:
        raise HTTPException(404, str(e))


# ========== 保险 ==========

@router.post("/insurance")
def create_insurance(req: CreateInsuranceRequest):
    svc = _get_services()
    try:
        return svc["insurance"].add_policy(
            family_id="default",
            product_name=req.product_name,
            policy_type=req.policy_type,
            sum_assured=req.sum_assured,
            annual_premium=req.annual_premium,
            term_years=req.term_years,
            payment_years=req.payment_years,
            insured_name=req.insured_name,
            insured_age=req.insured_age,
            insured_gender=req.insured_gender,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/insurance")
def list_insurance():
    svc = _get_services()
    return svc["insurance"].list_policies("default")


# ========== 投资 ==========

@router.post("/portfolios")
def create_portfolio(req: CreatePortfolioRequest):
    svc = _get_services()
    return svc["portfolio"].create_portfolio("default", req.name, req.base_currency)


@router.get("/portfolios")
def list_portfolios():
    svc = _get_services()
    return svc["portfolio"].list_portfolios("default")


@router.post("/portfolios/{portfolio_id}/buy")
def buy_holding(portfolio_id: str, req: BuyHoldingRequest):
    svc = _get_services()
    try:
        return svc["portfolio"].buy(
            portfolio_id=portfolio_id,
            asset_type=req.asset_type,
            asset_name=req.asset_name,
            asset_code=req.asset_code,
            shares=req.shares,
            price=req.price,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/portfolios/{portfolio_id}/performance")
def portfolio_performance(portfolio_id: str):
    svc = _get_services()
    return svc["portfolio"].get_performance(portfolio_id)


@router.get("/portfolios/{portfolio_id}/allocation")
def portfolio_allocation(portfolio_id: str):
    svc = _get_services()
    return svc["portfolio"].get_allocation(portfolio_id)


# ========== 报表 ==========

@router.get("/reports/balance-sheet")
def balance_sheet():
    svc = _get_services()
    return svc["report"].balance_sheet("default")


@router.get("/reports/income")
def income_summary(from_date: str = None, to_date: str = None):
    svc = _get_services()
    return svc["report"].income_summary("default", from_date, to_date)


@router.get("/reports/cashflow")
def cashflow(months: int = 6):
    svc = _get_services()
    return svc["report"].cashflow_monthly("default", months)


# ========== 利率 ==========

@router.post("/rates/sync")
def sync_rates():
    svc = _get_services()
    return svc["rate"].sync_rates()


@router.get("/rates/latest")
def latest_rate(rate_type: str = "LPR", term: str = None):
    svc = _get_services()
    return svc["rate"].get_latest(rate_type, term)


@router.get("/rates/history")
def rate_history(rate_type: str = "LPR", term: str = None, limit: int = 50):
    svc = _get_services()
    return svc["rate"].get_history(rate_type, term, limit)


# ========== 外部系统链接 ==========

@router.post("/integrations")
def add_integration(req: AddIntegrationRequest):
    from fin_l4.db import get_db
    from fin_l4.db.repositories import IntegrationRepository
    conn = get_db()
    repo = IntegrationRepository(conn)
    integration_id = repo.create(
        family_id="default",
        name=req.name,
        link_type=req.link_type,
        url=req.url,
        username_hint=req.username_hint,
        note=req.note,
    )
    return {"id": integration_id}


@router.get("/integrations")
def list_integrations():
    from fin_l4.db import get_db
    from fin_l4.db.repositories import IntegrationRepository
    conn = get_db()
    repo = IntegrationRepository(conn)
    return repo.list_by_family("default")


# ========== 预算 ==========

class SetBudgetRequest(BaseModel):
    category_id: str
    month: str  # "2026-09"
    amount: str


@router.post("/budgets")
def set_budget(req: SetBudgetRequest):
    from fin_l4.db import get_db
    from fin_l4.services.budget_svc import BudgetService
    conn = get_db()
    svc = BudgetService(conn)
    return svc.set_budget("default", req.category_id, req.month, req.amount)


@router.get("/budgets")
def list_budgets(month: str = None):
    from datetime import date
    from fin_l4.db import get_db
    from fin_l4.services.budget_svc import BudgetService
    if month is None:
        month = date.today().strftime("%Y-%m")
    conn = get_db()
    svc = BudgetService(conn)
    return svc.list_budgets("default", month)


@router.get("/budgets/status")
def budget_status(month: str = None):
    from datetime import date
    from fin_l4.db import get_db
    from fin_l4.services.budget_svc import BudgetService
    if month is None:
        month = date.today().strftime("%Y-%m")
    conn = get_db()
    svc = BudgetService(conn)
    return svc.get_overview("default", month)


# ========== 导入 ==========

class ImportRuleRequest(BaseModel):
    pattern: str  # 逗号分隔关键词
    category_id: str
    priority: int = 0


@router.post("/import/rules")
def add_import_rule(req: ImportRuleRequest):
    from fin_l4.db import get_db
    from fin_l4.services.import_svc import ImportService
    conn = get_db()
    svc = ImportService(conn)
    rule_id = svc.add_rule("default", req.pattern, req.category_id, req.priority)
    return {"id": rule_id}


@router.get("/import/rules")
def list_import_rules():
    from fin_l4.db import get_db
    from fin_l4.services.import_svc import ImportService
    conn = get_db()
    svc = ImportService(conn)
    return svc.list_rules("default")
