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
    
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "active_page": "dashboard",
        "net_worth": net_worth,
        "total_assets": total_assets,
        "total_liabilities": total_liabilities,
        "debt_ratio": debt_ratio,
        "accounts": accounts,
        "transactions": transactions,
    })


app.include_router(router)

@app.get("/health")
async def health():
    """健康检查"""
    return {"status": "ok", "version": "0.1.0", "layer": "L4"}
