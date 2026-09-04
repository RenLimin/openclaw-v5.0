"""FastAPI 主应用"""

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fin_l4.web.api import router
from decimal import Decimal
from fastapi.responses import HTMLResponse
from pathlib import Path

# 路径
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"

app = FastAPI(
    title="FIN-L4 家庭理财管理系统",
    version="0.1.0",
    description="本地优先的家庭理财管理",
)

# 静态文件
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# 模板
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """仪表盘首页"""
    from fin_l4.db import get_db
    from fin_l4.services.report_svc import ReportService
    from fin_l4.services.account_svc import AccountService
    
    conn = get_db()
    report_svc = ReportService(conn)
    account_svc = AccountService(conn)
    
    try:
        bs = report_svc.balance_sheet("default")
        net_worth = bs.get("net_worth", "0")
        total_assets = bs.get("total_assets", "0")
        total_liabilities = bs.get("total_liabilities", "0")
        
        # 资产负债率
        if total_assets != "0":
            ratio = (Decimal(total_liabilities) / Decimal(total_assets) * 100).quantize(Decimal("0.1"))
            debt_ratio = f"{ratio}%"
        else:
            debt_ratio = "--"
    except Exception:
        net_worth = "--"
        total_assets = "--"
        total_liabilities = "--"
        debt_ratio = "--"
    
    # 获取账户列表
    try:
        accounts_raw = account_svc.list_accounts("default")
        accounts = []
        for acc in accounts_raw:
            balance = account_svc.get_balance(acc["id"])
            if balance != 0:
                accounts.append({"name": acc["name"], "balance": str(balance)})
    except Exception:
        accounts = []
    
    # 获取最近交易
    try:
        txns = report_svc.conn.execute(
            "SELECT * FROM fin4_transactions WHERE family_id = ? ORDER BY date DESC LIMIT 10",
            ("default",)
        ).fetchall()
        transactions = [{"date": t["date"], "note": t.get("note", ""), "amount": t["amount"]} for t in txns]
    except Exception:
        transactions = []
    
    return templates.TemplateResponse(request, "dashboard.html", {
        "request": request,
        "active_page": "dashboard",
        "net_worth": net_worth,
        "total_assets": total_assets,
        "total_liabilities": total_liabilities,
        "debt_ratio": debt_ratio,
        "accounts": accounts,
        "transactions": transactions,
    })



@app.get("/budget", response_class=HTMLResponse)
async def budget_page(request: Request, month: str = None):
    """预算管理页"""
    from datetime import date
    from fin_l4.db import get_db
    from fin_l4.services.budget_svc import BudgetService

    if month is None:
        month = date.today().strftime("%Y-%m")

    conn = get_db()
    svc = BudgetService(conn)
    overview = svc.get_overview("default", month)

    return templates.TemplateResponse(request, "budget.html", {
        "request": request,
        "active_page": "budget",
        "month": month,
        "overview": overview,
    })


@app.get("/import", response_class=HTMLResponse)
async def import_page(request: Request):
    """CSV 导入页"""
    return templates.TemplateResponse(request, "import.html", {
        "request": request,
        "active_page": "import",
    })


app.include_router(router)


# ========== M3 贷款详情 ==========

@app.get("/loans", response_class=HTMLResponse)
async def loans_page(request: Request):
    """贷款列表页"""
    from fin_l4.db import get_db
    from fin_l4.services.loan_svc import LoanService
    conn = get_db()
    svc = LoanService(conn)
    loans = svc.list_loans("default")
    return templates.TemplateResponse(request, "loans.html", {
        "request": request, "active_page": "loans", "loans": loans,
    })


@app.get("/loans/{loan_id}", response_class=HTMLResponse)
async def loan_detail_page(request: Request, loan_id: str):
    """贷款详情页"""
    from datetime import date
    from fin_l4.db import get_db
    from fin_l4.services.loan_svc import LoanService
    conn = get_db()
    svc = LoanService(conn)
    loan = svc.repo.get(loan_id)
    schedule = svc.get_schedule(loan_id)
    summary = svc.get_summary(loan_id)
    return templates.TemplateResponse(request, "loan_detail.html", {
        "request": request, "active_page": "loans",
        "loan": loan, "schedule": schedule, "summary": summary,
        "today": str(date.today()), "prepay_result": None,
    })


@app.post("/loans/{loan_id}/prepay")
async def loan_prepay(request: Request, loan_id: str):
    """提前还款"""
    from datetime import date
    from fin_l4.db import get_db
    from fin_l4.services.loan_svc import LoanService
    form = await request.form()
    amount = form.get("amount", "0")
    conn = get_db()
    svc = LoanService(conn)
    result = svc.execute_prepay(loan_id, amount)
    loan = svc.repo.get(loan_id)
    schedule = svc.get_schedule(loan_id)
    summary = svc.get_summary(loan_id)
    return templates.TemplateResponse(request, "loan_detail.html", {
        "request": request, "active_page": "loans",
        "loan": loan, "schedule": schedule, "summary": summary,
        "today": str(date.today()), "prepay_result": result,
    })


@app.post("/loans/{loan_id}/close")
async def loan_close(request: Request, loan_id: str):
    """结清贷款"""
    from fin_l4.db import get_db
    from fin_l4.services.loan_svc import LoanService
    conn = get_db()
    svc = LoanService(conn)
    svc.close_loan(loan_id)
    from fastapi.responses import RedirectResponse
    return RedirectResponse("/loans", status_code=303)


# ========== M3 保险详情 ==========

@app.get("/insurance", response_class=HTMLResponse)
async def insurance_page(request: Request):
    """保险列表页"""
    from fin_l4.db import get_db
    from fin_l4.services.insurance_svc import InsuranceService
    conn = get_db()
    svc = InsuranceService(conn)
    policies = svc.list_policies("default")
    return templates.TemplateResponse(request, "insurance.html", {
        "request": request, "active_page": "insurance", "policies": policies,
    })


@app.get("/insurance/{policy_id}", response_class=HTMLResponse)
async def insurance_detail_page(request: Request, policy_id: str):
    """保单详情页"""
    from fin_l4.db import get_db
    from fin_l4.services.insurance_svc import InsuranceService
    conn = get_db()
    svc = InsuranceService(conn)
    policy = svc.get_policy_detail(policy_id)
    gaps = svc.get_coverage_gap("default")
    return templates.TemplateResponse(request, "insurance_detail.html", {
        "request": request, "active_page": "insurance",
        "policy": policy, "cash_value_table": policy.get("cash_value_table", []),
        "coverage_gap": None, "surrender_value": None,
    })


@app.post("/insurance/{policy_id}/surrender")
async def insurance_surrender(request: Request, policy_id: str):
    """退保"""
    from fin_l4.db import get_db
    from fin_l4.services.insurance_svc import InsuranceService
    conn = get_db()
    svc = InsuranceService(conn)
    result = svc.surrender_policy(policy_id)
    policy = svc.get_policy_detail(policy_id)
    return templates.TemplateResponse(request, "insurance_detail.html", {
        "request": request, "active_page": "insurance",
        "policy": policy, "cash_value_table": policy.get("cash_value_table", []),
        "coverage_gap": None, "surrender_value": result["cash_value"],
    })


@app.get("/insurance/coverage-gap", response_class=HTMLResponse)
async def coverage_gap_page(request: Request):
    """保障缺口分析页"""
    from fin_l4.db import get_db
    from fin_l4.services.insurance_svc import InsuranceService
    conn = get_db()
    svc = InsuranceService(conn)
    gaps = svc.get_coverage_gap("default")
    total_current = sum(float(g["current"]) for g in gaps)
    total_recommended = sum(float(g["recommended"]) for g in gaps)
    total_gap = sum(float(g["gap"]) for g in gaps)
    return templates.TemplateResponse(request, "coverage_gap.html", {
        "request": request, "active_page": "insurance",
        "gaps": gaps,
        "total_current": f"{total_current:,.2f}",
        "total_recommended": f"{total_recommended:,.2f}",
        "total_gap": f"{total_gap:,.2f}",
    })


# ========== M3 投资详情 ==========

@app.get("/portfolio", response_class=HTMLResponse)
async def portfolio_page(request: Request):
    """投资列表页"""
    from fin_l4.db import get_db
    from fin_l4.services.portfolio_svc import PortfolioService
    conn = get_db()
    svc = PortfolioService(conn)
    portfolios = svc.list_portfolios("default")
    return templates.TemplateResponse(request, "portfolio.html", {
        "request": request, "active_page": "portfolio", "portfolios": portfolios,
    })


@app.get("/portfolio/{portfolio_id}", response_class=HTMLResponse)
async def portfolio_detail_page(request: Request, portfolio_id: str):
    """组合详情页"""
    from fin_l4.db import get_db
    from fin_l4.services.portfolio_svc import PortfolioService
    conn = get_db()
    svc = PortfolioService(conn)
    performance = svc.get_performance(portfolio_id)
    allocation = svc.get_allocation(portfolio_id)
    rebalance = svc.get_rebalance(portfolio_id)
    holdings = svc.get_holdings(portfolio_id)

    # 计算持仓盈亏
    for h in holdings:
        gain = (float(h.get("current_price", 0) or 0) - float(h.get("cost_basis_price", 0) or 0)) * float(h.get("shares", 0) or 0)
        h["gain"] = f"{gain:,.2f}"

    return templates.TemplateResponse(request, "portfolio_detail.html", {
        "request": request, "active_page": "portfolio",
        "portfolio": {"id": portfolio_id, "name": ""},
        "performance": performance,
        "allocation": allocation.get("allocation", []),
        "rebalance": rebalance.get("suggestions", []),
        "holdings": holdings,
    })


@app.get("/health")
async def health():
    """健康检查"""
    return {"status": "ok", "version": "0.1.0", "layer": "L4"}


@app.get("/report", response_class=HTMLResponse)
async def report_page(request: Request):
    """报表页"""
    from fin_l4.db import get_db
    from fin_l4.services.report_svc import ReportService

    conn = get_db()
    report_svc = ReportService(conn)

    bs = report_svc.balance_sheet("default")
    income = report_svc.income_summary("default")
    cashflow = report_svc.monthly_cashflow("default")

    return templates.TemplateResponse(request, "reports.html", {
        "request": request, "active_page": "report",
        "balance_sheet": bs,
        "income_summary": income,
        "cashflow": cashflow,
    })


@app.get("/advise", response_class=HTMLResponse)
async def advise_page(request: Request):
    """理财建议页"""
    from fin_l4.db import get_db
    from fin_l4.services.advise_svc import AdviseService

    conn = get_db()
    advise_svc = AdviseService(conn)
    health = advise_svc.health_check("default", "35000", "20000")

    return templates.TemplateResponse(request, "advise.html", {
        "request": request, "active_page": "advise",
        "health": health,
    })
