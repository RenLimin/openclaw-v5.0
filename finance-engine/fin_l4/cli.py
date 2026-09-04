"""CLI 入口 — finctl 命令行工具"""

import click
import json
from fin_l4.db import init_db, get_db


def _get_conn():
    return get_db()


@click.group()
@click.option('--db', default=None, help='数据库路径')
@click.pass_context
def cli(ctx, db):
    """FIN-L4 家庭理财管理 CLI"""
    ctx.ensure_object(dict)
    init_db(db)
    ctx.obj['conn'] = get_db(db)


# ========== 家庭 ==========

@cli.group()
def family():
    """家庭管理"""
    pass


@family.command('create')
@click.option('--name', required=True, help='家庭名称')
@click.option('--currency', default='CNY', help='币种')
@click.pass_context
def family_create(ctx, name, currency):
    from fin_l4.db.repositories import FamilyRepository
    repo = FamilyRepository(ctx.obj['conn'])
    family_id = repo.create(name, currency)
    click.echo(f"已创建家庭: {family_id}")


@family.command('list')
@click.pass_context
def family_list(ctx):
    from fin_l4.db.repositories import FamilyRepository
    repo = FamilyRepository(ctx.obj['conn'])
    families = repo.list_all()
    for f in families:
        click.echo(f"{f['id']}: {f['name']} ({f['currency']})")


# ========== 账户 ==========

@cli.group()
def account():
    """账户管理"""
    pass


@account.command('create')
@click.option('--code', required=True, help='科目代码')
@click.option('--name', required=True, help='账户名称')
@click.option('--type', 'acc_type', required=True, help='账户类型')
@click.option('--balance', default='0', help='期初余额')
@click.pass_context
def account_create(ctx, code, name, acc_type, balance):
    from fin_l4.services.account_svc import AccountService
    svc = AccountService(ctx.obj['conn'])
    result = svc.create_account(family_id="default", code=code, name=name, type=acc_type, opening_balance=balance)
    click.echo(f"已创建账户: {result['id']}")


@account.command('list')
@click.pass_context
def account_list(ctx):
    from fin_l4.services.account_svc import AccountService
    svc = AccountService(ctx.obj['conn'])
    accounts = svc.list_accounts("default")
    for acc in accounts:
        balance = svc.get_balance(acc['id'])
        click.echo(f"{acc['code']}  {acc['name']:20s}  {acc['type']:10s}  ¥{balance}")


@account.command('trial-balance')
@click.pass_context
def trial_balance(ctx):
    from fin_l4.services.account_svc import AccountService
    svc = AccountService(ctx.obj['conn'])
    result = svc.get_trial_balance("default")
    click.echo(f"借方合计: ¥{result['debit_total']}")
    click.echo(f"贷方合计: ¥{result['credit_total']}")
    click.echo(f"平衡: {'✅' if result['is_balanced'] else '❌'}")


# ========== 记账 ==========

@cli.group()
def txn():
    """记账"""
    pass


@txn.command('add')
@click.option('--debit', required=True, help='借方账户ID')
@click.option('--credit', required=True, help='贷方账户ID')
@click.option('--amount', required=True, help='金额')
@click.option('--date', 'txn_date', default=None, help='日期 (YYYY-MM-DD)')
@click.option('--note', default=None, help='摘要')
@click.pass_context
def txn_add(ctx, debit, credit, amount, txn_date, note):
    from datetime import date as date_mod
    from fin_l4.services.txn_svc import TransactionService
    svc = TransactionService(ctx.obj['conn'])
    result = svc.record(family_id="default", date_str=txn_date or str(date_mod.today()),
                        amount=amount, debit_account_id=debit, credit_account_id=credit, note=note)
    click.echo(f"已记录: {result['id']}")


@txn.command('list')
@click.option('--limit', default=20, help='条数')
@click.pass_context
def txn_list(ctx, limit):
    from fin_l4.services.txn_svc import TransactionService
    svc = TransactionService(ctx.obj['conn'])
    txns = svc.list_transactions("default", limit=limit)
    for t in txns:
        click.echo(f"{t['date']}  ¥{t['amount']:>12s}  {t.get('note', '')}")


# ========== 预算 ==========

@cli.group()
def budget():
    """预算管理"""
    pass


@budget.command('set')
@click.option('--category-id', required=True, help='分类ID')
@click.option('--month', required=True, help='月份 (YYYY-MM)')
@click.option('--amount', required=True, help='预算金额')
@click.pass_context
def budget_set(ctx, category_id, month, amount):
    from fin_l4.services.budget_svc import BudgetService
    svc = BudgetService(ctx.obj['conn'])
    result = svc.set_budget("default", category_id, month, amount)
    click.echo(f"预算已设置: {result['status']}")


@budget.command('status')
@click.option('--month', default=None, help='月份 (YYYY-MM)')
@click.pass_context
def budget_status(ctx, month):
    from fin_l4.services.budget_svc import BudgetService
    svc = BudgetService(ctx.obj['conn'])
    overview = svc.get_overview("default", month or "")
    click.echo(f"预算总览 ({overview['month']}):")
    click.echo(f"  总预算: ¥{overview['total_budget']}")
    click.echo(f"  已支出: ¥{overview['total_spent']}")
    click.echo(f"  剩余:   ¥{overview['total_remaining']}")


# ========== 贷款 ==========

@cli.group()
def loan():
    """贷款管理"""
    pass


@loan.command('create')
@click.option('--name', required=True, help='贷款名称')
@click.option('--principal', required=True, help='本金')
@click.option('--rate', required=True, help='年利率 (如 0.035)')
@click.option('--term', required=True, type=int, help='期限(月)')
@click.option('--method', default='equal_payment', help='还款方式')
@click.pass_context
def loan_create(ctx, name, principal, rate, term, method):
    from fin_l4.services.loan_svc import LoanService
    svc = LoanService(ctx.obj['conn'])
    result = svc.create_loan(family_id="default", name=name, principal=principal,
                             annual_rate=rate, term_months=term, method=method)
    click.echo(f"已创建贷款: {result['id']}")


@loan.command('list')
@click.pass_context
def loan_list(ctx):
    from fin_l4.services.loan_svc import LoanService
    svc = LoanService(ctx.obj['conn'])
    loans = svc.list_loans("default")
    for loan in loans:
        click.echo(f"{loan['id'][:8]}  {loan['name']:20s}  ¥{loan['principal']}  {loan['annual_rate']}  {loan['term_months']}月")


@loan.command('schedule')
@click.argument('loan_id')
@click.pass_context
def loan_schedule(ctx, loan_id):
    from fin_l4.services.loan_svc import LoanService
    svc = LoanService(ctx.obj['conn'])
    schedule = svc.get_schedule(loan_id)
    click.echo(f"{'期数':>4}  {'还款额':>12}  {'本金':>12}  {'利息':>12}  {'剩余本金':>12}")
    click.echo("-" * 60)
    for entry in schedule[:12]:
        click.echo(f"{entry['period']:>4}  ¥{entry['payment']:>10}  ¥{entry['principal']:>10}  ¥{entry['interest']:>10}  ¥{entry['remaining_balance']:>10}")
    if len(schedule) > 12:
        click.echo(f"... 共 {len(schedule)} 期")


@loan.command('summary')
@click.argument('loan_id')
@click.pass_context
def loan_summary(ctx, loan_id):
    from fin_l4.services.loan_svc import LoanService
    svc = LoanService(ctx.obj['conn'])
    s = svc.get_summary(loan_id)
    click.echo(f"贷款: {s['name']}")
    click.echo(f"  月供: ¥{s['monthly_payment']}")
    click.echo(f"  总利息: ¥{s['total_interest']}")
    click.echo(f"  剩余本金: ¥{s['remaining_balance']}")
    click.echo(f"  已还期数: {s['paid_periods']}")
    click.echo(f"  剩余期数: {s['remaining_periods']}")


# ========== 保险 ==========

@cli.group()
def insurance():
    """保险管理"""
    pass


@insurance.command('create')
@click.option('--number', required=True, help='保单号')
@click.option('--name', required=True, help='产品名称')
@click.option('--type', 'ins_type', required=True, help='险种类型')
@click.option('--premium', required=True, help='年缴保费')
@click.option('--sum-assured', required=True, help='保额')
@click.option('--start-date', required=True, help='生效日期')
@click.pass_context
def insurance_create(ctx, number, name, ins_type, premium, sum_assured, start_date):
    from fin_l4.services.insurance_svc import InsuranceService
    svc = InsuranceService(ctx.obj['conn'])
    result = svc.create_policy(family_id="default", policy_number=number, product_name=name,
                               policy_type=ins_type, annual_premium=premium, sum_assured=sum_assured,
                               start_date=start_date)
    click.echo(f"已创建保单: {result['id']}")


@insurance.command('list')
@click.pass_context
def insurance_list(ctx):
    from fin_l4.services.insurance_svc import InsuranceService
    svc = InsuranceService(ctx.obj['conn'])
    policies = svc.list_policies("default")
    for p in policies:
        click.echo(f"{p['id'][:8]}  {p['product_name']:20s}  {p['policy_type']:15s}  ¥{p['annual_premium']:>8}  ¥{p['sum_assured']:>10}  {p['status']}")


# ========== 投资 ==========

@cli.group()
def portfolio():
    """投资管理"""
    pass


@portfolio.command('create')
@click.option('--name', required=True, help='组合名称')
@click.pass_context
def portfolio_create(ctx, name):
    from fin_l4.services.portfolio_svc import PortfolioService
    svc = PortfolioService(ctx.obj['conn'])
    result = svc.create_portfolio(family_id="default", name=name)
    click.echo(f"已创建组合: {result['id']}")


@portfolio.command('list')
@click.pass_context
def portfolio_list(ctx):
    from fin_l4.services.portfolio_svc import PortfolioService
    svc = PortfolioService(ctx.obj['conn'])
    portfolios = svc.list_portfolios("default")
    for p in portfolios:
        click.echo(f"{p['id'][:8]}  {p['name']:20s}  {p.get('base_currency', 'CNY')}")


@portfolio.command('buy')
@click.argument('portfolio_id')
@click.option('--type', 'asset_type', required=True, help='资产类型')
@click.option('--name', required=True, help='资产名称')
@click.option('--code', default='', help='资产代码')
@click.option('--shares', required=True, help='数量')
@click.option('--price', required=True, help='买入价')
@click.pass_context
def portfolio_buy(ctx, portfolio_id, asset_type, name, code, shares, price):
    from fin_l4.services.portfolio_svc import PortfolioService
    svc = PortfolioService(ctx.obj['conn'])
    result = svc.buy(portfolio_id, asset_type, name, code, shares, price)
    click.echo(f"已买入: {result['id']}")


@portfolio.command('performance')
@click.argument('portfolio_id')
@click.pass_context
def portfolio_performance(ctx, portfolio_id):
    from fin_l4.services.portfolio_svc import PortfolioService
    svc = PortfolioService(ctx.obj['conn'])
    result = svc.get_performance(portfolio_id)
    click.echo(f"组合: {result['portfolio_id']}")
    click.echo(f"  总市值: ¥{result['total_value']}")
    click.echo(f"  总成本: ¥{result['total_cost']}")
    click.echo(f"  总盈亏: ¥{result['total_gain']}")
    click.echo(f"  收益率: {result['total_return_pct']}%")
    click.echo(f"  持仓数: {result['holdings']}")


# ========== 报表 ==========

@cli.group()
def report():
    """报表"""
    pass


@report.command('balance-sheet')
@click.pass_context
def report_balance_sheet(ctx):
    from fin_l4.services.report_svc import ReportService
    svc = ReportService(ctx.obj['conn'])
    result = svc.balance_sheet("default")
    click.echo("=" * 50)
    click.echo("资产负债表")
    click.echo(f"日期: {result['date']}")
    click.echo("=" * 50)
    click.echo(f"\n资产:")
    for item in result['assets']:
        click.echo(f"  {item['name']:20s}  ¥{item['balance']}")
    click.echo(f"  {'合计':20s}  ¥{result['total_assets']}")
    click.echo(f"\n负债:")
    for item in result['liabilities']:
        click.echo(f"  {item['name']:20s}  ¥{item['balance']}")
    click.echo(f"  {'合计':20s}  ¥{result['total_liabilities']}")
    click.echo(f"\n净值: ¥{result['net_worth']}")
    click.echo(f"平衡: {'✅' if result['is_balanced'] else '❌'}")


@report.command('income')
@click.pass_context
def report_income(ctx):
    from fin_l4.services.report_svc import ReportService
    svc = ReportService(ctx.obj['conn'])
    result = svc.income_summary("default")
    click.echo("=" * 50)
    click.echo("收支汇总")
    click.echo("=" * 50)
    click.echo(f"\n收入:")
    for item in result['income']:
        click.echo(f"  {item['name']:20s}  ¥{item['amount']}")
    click.echo(f"  {'合计':20s}  ¥{result['total_income']}")
    click.echo(f"\n支出:")
    for item in result['expenses']:
        click.echo(f"  {item['name']:20s}  ¥{item['amount']}")
    click.echo(f"  {'合计':20s}  ¥{result['total_expenses']}")
    click.echo(f"\n净结余: ¥{result['net']}")


@report.command('cashflow')
@click.pass_context
def report_cashflow(ctx):
    from fin_l4.services.report_svc import ReportService
    svc = ReportService(ctx.obj['conn'])
    result = svc.cashflow_monthly("default")
    click.echo("=" * 40)
    click.echo("月度现金流")
    click.echo("=" * 40)
    for item in result:
        click.echo(f"{item['month']}  收: ¥{item['income']:>10}  支: ¥{item['expense']:>10}")


# ========== 利率 ==========

@cli.group()
def rate():
    """利率管理"""
    pass


@rate.command('sync')
@click.pass_context
def rate_sync(ctx):
    from fin_l4.services.rate_svc import RateService
    svc = RateService(ctx.obj['conn'])
    result = svc.sync_rates()
    click.echo("同步完成:")
    for item in result.get('lpr', []):
        click.echo(f"  LPR {item['term']}: {item['rate']} ({item['date']})")
    if result.get('errors'):
        click.echo("错误:")
        for err in result.get('errors', []):
            click.echo(f"  ❌ {err}")


@rate.command('latest')
@click.option('--type', default='LPR', help='利率类型')
@click.option('--term', default=None, help='期限')
@click.pass_context
def rate_latest(ctx, type, term):
    from fin_l4.services.rate_svc import RateService
    svc = RateService(ctx.obj['conn'])
    result = svc.get_latest(type, term)
    if result:
        click.echo(f"{result['rate_type']} {result.get('term', '')}: {result['rate']} ({result.get('effective_date', '')})")
    else:
        click.echo("无数据")


# ========== 导出 ==========

@cli.group()
def export():
    """报表导出"""
    pass


@export.command('balance-sheet')
@click.option('--output', default='balance_sheet.xlsx', help='输出文件')
@click.pass_context
def export_balance_sheet(ctx, output):
    from fin_l4.services.export_svc import ExportService
    svc = ExportService(ctx.obj['conn'])
    data = svc.export_balance_sheet_excel("default")
    with open(output, 'wb') as f:
        f.write(data)
    click.echo(f"已导出: {output} ({len(data)} bytes)")


@export.command('transactions')
@click.option('--output', default='transactions.xlsx', help='输出文件')
@click.pass_context
def export_transactions(ctx, output):
    from fin_l4.services.export_svc import ExportService
    svc = ExportService(ctx.obj['conn'])
    data = svc.export_transactions_excel("default")
    with open(output, 'wb') as f:
        f.write(data)
    click.echo(f"已导出: {output} ({len(data)} bytes)")


@export.command('report')
@click.option('--output', default='financial_report.docx', help='输出文件')
@click.pass_context
def export_report(ctx, output):
    from fin_l4.services.export_svc import ExportService
    svc = ExportService(ctx.obj['conn'])
    data = svc.export_financial_report_word("default")
    with open(output, 'wb') as f:
        f.write(data)
    click.echo(f"已导出: {output} ({len(data)} bytes)")


# ========== 建议 ==========

@cli.group()
def advise():
    """理财建议"""
    pass


@advise.command('health')
@click.option('--income', required=True, help='月收入')
@click.option('--expenses', required=True, help='月支出')
@click.option('--age', default=30, type=int)
@click.pass_context
def advise_health(ctx, income, expenses, age):
    from fin_l4.services.advise_svc import AdviseService
    svc = AdviseService(ctx.obj['conn'])
    result = svc.health_check("default", income, expenses, age=age)
    click.echo(f"财务健康评分: {result['health_score']}")
    click.echo(f"总结: {result['summary']}")
    if 'allocation' in result:
        click.echo(f"配置建议: {result['allocation']}")
    if 'debt_plan' in result:
        click.echo(f"债务计划: {result['debt_plan']}")


# ========== 入口 ==========

if __name__ == '__main__':
    cli()
