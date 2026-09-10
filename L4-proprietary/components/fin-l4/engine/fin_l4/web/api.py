"""REST API 路由"""

from fastapi import APIRouter, HTTPException, Request
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


# ========== 银行流水导入 ==========

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


# ----- 银行流水导入新 API -----

class ConfirmImportRequest(BaseModel):
    import_id: str
    adjustments: dict = {}  # {idx: {category_id: ...}}


@router.post("/import/preview")
async def preview_import(request: Request, source_type: str = "auto"):
    """预览银行流水导入结果（raw body 上传，文件名从 X-Filename header 取）"""
    from fin_l4.db import get_db
    from fin_l4.services.importer import TransactionImporter
    import tempfile, os

    body = await request.body()
    if not body:
        from fastapi import HTTPException
        raise HTTPException(400, "未上传文件")

    filename = request.headers.get("X-Filename", "import.csv")
    # URL decode
    from urllib.parse import unquote
    filename = unquote(filename)
    file_content = body

    conn = get_db()
    importer = TransactionImporter(conn)

    suffix = os.path.splitext(filename)[1] or ".csv"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
        f.write(file_content)
        tmp_path = f.name

    try:
        result = importer.preview_import("default", tmp_path, source_type)
        return {
            "import_id": result.import_id,
            "file_name": result.file_name,
            "detected_bank": result.detected_bank,
            "detected_bank_name": result.detected_bank_name,
            "format": result.format,
            "total_count": result.total_count,
            "valid_count": result.valid_count,
            "error_count": result.error_count,
            "duplicate_count": result.duplicate_count,
            "new_count": result.new_count,
            "transactions": result.transactions,
            "errors": result.errors,
            "confidence_stats": result.confidence_stats,
            "category_stats": result.category_stats,
        }
    finally:
        os.unlink(tmp_path)


@router.post("/import/do")
async def do_import(request: Request, source_type: str = "auto"):
    """直接执行银行流水导入（raw body 上传）"""
    from fin_l4.db import get_db
    from fin_l4.services.importer import TransactionImporter
    import tempfile, os

    body = await request.body()
    if not body:
        from fastapi import HTTPException
        raise HTTPException(400, "未上传文件")

    filename = request.headers.get("X-Filename", "import.csv")
    from urllib.parse import unquote
    filename = unquote(filename)
    file_content = body

    conn = get_db()
    importer = TransactionImporter(conn)

    suffix = os.path.splitext(filename)[1] or ".csv"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
        f.write(file_content)
        tmp_path = f.name

    try:
        result = importer.import_file("default", tmp_path, source_type)
        return {
            "import_id": result.import_id,
            "status": result.status,
            "total_count": result.total_count,
            "new_count": result.new_count,
            "duplicate_count": result.duplicate_count,
            "error_count": result.error_count,
            "high_confidence": result.high_confidence,
            "medium_confidence": result.medium_confidence,
            "low_confidence": result.low_confidence,
            "category_stats": result.category_stats,
            "errors": result.errors,
        }
    finally:
        os.unlink(tmp_path)


@router.post("/import/do")
async def do_import(
    file: "UploadFile" = None,
    source_type: str = "auto",
):
    """直接执行银行流水导入"""
    from fastapi import UploadFile, File, HTTPException, Form
    from fin_l4.db import get_db
    from fin_l4.services.importer import TransactionImporter
    import tempfile, os

    if file is None or not getattr(file, 'filename', None):
        raise HTTPException(400, "未上传文件")

    conn = get_db()
    importer = TransactionImporter(conn)

    content = await file.read()
    suffix = os.path.splitext(file.filename)[1] or ".csv"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
        f.write(content)
        tmp_path = f.name

    try:
        result = importer.import_file("default", tmp_path, source_type)
        return {
            "import_id": result.import_id,
            "status": result.status,
            "total_count": result.total_count,
            "new_count": result.new_count,
            "duplicate_count": result.duplicate_count,
            "error_count": result.error_count,
            "high_confidence": result.high_confidence,
            "medium_confidence": result.medium_confidence,
            "low_confidence": result.low_confidence,
            "category_stats": result.category_stats,
            "errors": result.errors,
        }
    finally:
        os.unlink(tmp_path)


@router.get("/import/banks")
def list_supported_banks():
    """列出支持的银行模板"""
    from fin_l4.services.importer import load_templates
    templates = load_templates()
    return [
        {"bank_id": t.bank_id, "bank_name": t.bank_name}
        for t in templates
    ]


@router.get("/import/history")
def import_history(limit: int = 20):
    """导入历史记录"""
    from fin_l4.db import get_db
    from fin_l4.services.importer import TransactionImporter
    conn = get_db()
    importer = TransactionImporter(conn)
    return importer.get_import_history("default", limit)


@router.post("/import/confirm")
def confirm_import_endpoint(req: ConfirmImportRequest):
    """确认导入（支持分类调整）"""
    from fin_l4.db import get_db
    from fin_l4.services.importer import TransactionImporter
    conn = get_db()
    importer = TransactionImporter(conn)
    result = importer.confirm_import(
        req.import_id, "default",
        adjustments=req.adjustments,
    )
    return {
        "import_id": result.import_id,
        "status": result.status,
        "total_count": result.total_count,
        "new_count": result.new_count,
        "duplicate_count": result.duplicate_count,
        "error_count": result.error_count,
        "high_confidence": result.high_confidence,
        "medium_confidence": result.medium_confidence,
        "low_confidence": result.low_confidence,
        "category_stats": result.category_stats,
        "errors": result.errors,
    }


# 分类规则 API

@router.get("/import/classification-rules")
def list_classification_rules():
    """列出所有分类规则"""
    from fin_l4.services.importer.classifier import RuleClassifier
    clf = RuleClassifier.default()
    return clf.list_rules()


# ========== M3 贷款详情 API ==========

@router.get("/loans/{loan_id}")
def api_loan_detail(loan_id: str):
    from fin_l4.db import get_db
    from fin_l4.services.loan_svc import LoanService
    conn = get_db()
    svc = LoanService(conn)
    loan = svc.repo.get(loan_id)
    schedule = svc.get_schedule(loan_id)
    summary = svc.get_summary(loan_id)
    return {"loan": loan, "schedule": schedule, "summary": summary}


@router.post("/loans/{loan_id}/prepay")
def api_loan_prepay(loan_id: str, body: dict = None):
    from fin_l4.db import get_db
    from fin_l4.services.loan_svc import LoanService
    amount = (body or {}).get("amount", "0")
    conn = get_db()
    svc = LoanService(conn)
    return svc.execute_prepay(loan_id, amount)


@router.post("/loans/{loan_id}/close")
def api_loan_close(loan_id: str):
    from fin_l4.db import get_db
    from fin_l4.services.loan_svc import LoanService
    conn = get_db()
    svc = LoanService(conn)
    return svc.close_loan(loan_id)


# ========== M3 保险详情 API ==========

@router.get("/insurance/{policy_id}")
def api_insurance_detail(policy_id: str):
    from fin_l4.db import get_db
    from fin_l4.services.insurance_svc import InsuranceService
    conn = get_db()
    svc = InsuranceService(conn)
    return svc.get_policy_detail(policy_id)


@router.post("/insurance/{policy_id}/surrender")
def api_insurance_surrender(policy_id: str):
    from fin_l4.db import get_db
    from fin_l4.services.insurance_svc import InsuranceService
    conn = get_db()
    svc = InsuranceService(conn)
    return svc.surrender_policy(policy_id)


@router.get("/insurance/coverage-gap")
def api_coverage_gap(family_id: str = "default", monthly_income: str = "35000"):
    from fin_l4.db import get_db
    from fin_l4.services.insurance_svc import InsuranceService
    conn = get_db()
    svc = InsuranceService(conn)
    return svc.get_coverage_gap(family_id, monthly_income)


# ========== M3 投资详情 API ==========

@router.get("/portfolios/{portfolio_id}")
def api_portfolio_detail(portfolio_id: str):
    from fin_l4.db import get_db
    from fin_l4.services.portfolio_svc import PortfolioService
    conn = get_db()
    svc = PortfolioService(conn)
    return {
        "performance": svc.get_performance(portfolio_id),
        "allocation": svc.get_allocation(portfolio_id),
        "rebalance": svc.get_rebalance(portfolio_id),
        "holdings": svc.get_holdings(portfolio_id),
    }


# ========== M4 导出 API ==========

@router.get("/export/balance-sheet")
def export_balance_sheet():
    from fin_l4.db import get_db
    from fin_l4.services.export_svc import ExportService
    conn = get_db()
    svc = ExportService(conn)
    data = svc.export_balance_sheet_excel("default")
    from fastapi.responses import Response
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=balance_sheet.xlsx"},
    )


@router.get("/export/transactions")
def export_transactions():
    from fin_l4.db import get_db
    from fin_l4.services.export_svc import ExportService
    conn = get_db()
    svc = ExportService(conn)
    data = svc.export_transactions_excel("default")
    from fastapi.responses import Response
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=transactions.xlsx"},
    )


@router.get("/export/report")
def export_report():
    from fin_l4.db import get_db
    from fin_l4.services.export_svc import ExportService
    conn = get_db()
    svc = ExportService(conn)
    data = svc.export_financial_report_word("default")
    from fastapi.responses import Response
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": "attachment; filename=financial_report.docx"},
    )


# ========== 仪表盘专用 API（v1） ==========

@router.get("/dashboard/overview")
def dashboard_overview(family_id: str = "default"):
    """总览数据：总资产、总负债、本月收入/支出/结余、储蓄率"""
    svc = _get_services()
    return svc["report"].dashboard_overview(family_id)


@router.get("/dashboard/categories")
def dashboard_categories(family_id: str = "default",
                        month: str = None,
                        type: str = None):
    """分类统计（支出/收入分类汇总）
    type: 'income' | 'expense' | None(全部)
    month: 'YYYY-MM'，默认本月
    """
    svc = _get_services()
    return svc["report"].category_summary(family_id, month, type)


@router.get("/dashboard/monthly-trend")
def dashboard_monthly_trend(family_id: str = "default", months: int = 12):
    """月度收支趋势（近 N 个月）"""
    svc = _get_services()
    return svc["report"].monthly_trend(family_id, months)


@router.get("/dashboard/budget")
def dashboard_budget(family_id: str = "default", month: str = None):
    """预算执行情况"""
    svc = _get_services()
    return svc["report"].budget_progress(family_id, month)


@router.get("/dashboard/investments")
def dashboard_investments(family_id: str = "default"):
    """投资组合持仓 + 收益"""
    svc = _get_services()
    return svc["report"].investment_summary(family_id)


@router.get("/dashboard/transactions")
def dashboard_transactions(family_id: str = "default", limit: int = 20):
    """最近交易记录（带分类名）"""
    svc = _get_services()
    return svc["report"].recent_transactions(family_id, limit)
