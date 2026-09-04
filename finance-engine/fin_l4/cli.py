"""CLI 入口 — finctl 命令行工具"""

import click
import json
from fin_l4.db import init_db, get_db
from fin_l4.services.account_svc import AccountService
from fin_l4.services.txn_svc import TransactionService
from fin_l4.services.loan_svc import LoanService
from fin_l4.services.report_svc import ReportService
from fin_l4.services.rate_svc import RateService


def _get_conn():
    """获取数据库连接"""
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
    """创建家庭"""
    from fin_l4.db.repositories import FamilyRepository
    repo = FamilyRepository(ctx.obj['conn'])
    family_id = repo.create(name, currency)
    click.echo(f"已创建家庭: {family_id}")


@family.command('show')
@click.pass_context
def family_show(ctx):
    """显示家庭信息"""
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
@click.option('--type', required=True, help='账户类型 (ASSET/LIABILITY/EQUITY/INCOME/EXPENSE)')
@click.option('--balance', default='0', help='期初余额')
@click.pass_context
def account_create(ctx, code, name, type, balance):
    """创建账户"""
    svc = AccountService(ctx.obj['conn'])
    result = svc.create_account(
        family_id="default",
        code=code,
        name=name,
        type=type,
        opening_balance=balance,
    )
    click.echo(f"已创建账户: {result['id']}")


@account.command('list')
@click.pass_context
def account_list(ctx):
    """列出账户"""
    svc = AccountService(ctx.obj['conn'])
    accounts = svc.list_accounts("default")
    for acc in accounts:
        balance = svc.get_balance(acc['id'])
        click.echo(f"{acc['code']}  {acc['name']:20s}  {acc['type']:10s}  ¥{balance}")


@account.command('balance')
@click.argument('account_id')
@click.pass_context
def account_balance(ctx, account_id):
    """查询账户余额"""
    svc = AccountService(ctx.obj['conn'])
    balance = svc.get_balance(account_id)
    click.echo(f"余额: ¥{balance}")


@account.command('trial-balance')
@click.pass_context
def trial_balance(ctx):
    """试算平衡"""
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
@click.option('--date', default=None, help='日期 (YYYY-MM-DD)')
@click.option('--note', default=None, help='摘要')
@click.pass_context
def txn_add(ctx, debit, credit, amount, date, note):
    """记一笔"""
    from datetime import date as date_mod
    svc = TransactionService(ctx.obj['conn'])
    result = svc.record(
        family_id="default",
        date_str=date or str(date_mod.today()),
        amount=amount,
        debit_account_id=debit,
        credit_account_id=credit,
        note=note,
    )
    click.echo(f"已记录: {result['id']}")


@txn.command('list')
@click.option('--account', default=None, help='账户ID')
@click.option('--limit', default=20, help='条数')
@click.pass_context
def txn_list(ctx, account, limit):
    """交易明细"""
    svc = TransactionService(ctx.obj['conn'])
    txns = svc.list_transactions("default", account_id=account, limit=limit)
    for t in txns:
        click.echo(f"{t['date']}  ¥{t['amount']:>12s}  {t.get('note', '')}")


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
    """创建贷款"""
    svc = LoanService(ctx.obj['conn'])
    result = svc.create_loan(
        family_id="default",
        name=name,
        principal=principal,
        annual_rate=rate,
        term_months=term,
        method=method,
    )
    click.echo(f"已创建贷款: {result['id']}")


@loan.command('list')
@click.pass_context
def loan_list(ctx):
    """列出贷款"""
    svc = LoanService(ctx.obj['conn'])
    loans = svc.list_loans("default")
    for loan in loans:
        click.echo(f"{loan['id'][:8]}  {loan['name']:20s}  ¥{loan['principal']}  {loan['annual_rate']}  {loan['term_months']}月")


@loan.command('schedule')
@click.argument('loan_id')
@click.pass_context
def loan_schedule(ctx, loan_id):
    """还款计划"""
    svc = LoanService(ctx.obj['conn'])
    schedule = svc.get_schedule(loan_id)
    click.echo(f"{'期数':>4}  {'还款额':>12}  {'本金':>12}  {'利息':>12}  {'剩余本金':>12}")
    click.echo("-" * 60)
    for entry in schedule[:12]:  # 显示前12期
        click.echo(f"{entry['period']:>4}  ¥{entry['payment']:>10}  ¥{entry['principal']:>10}  ¥{entry['interest']:>10}  ¥{entry['remaining_balance']:>10}")
    if len(schedule) > 12:
        click.echo(f"... 共 {len(schedule)} 期")


# ========== 报表 ==========

@cli.group()
def report():
    """报表"""
    pass


@report.command('balance-sheet')
@click.pass_context
def report_balance_sheet(ctx):
    """资产负债表"""
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
    """收支汇总"""
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


# ========== 利率 ==========

@cli.group()
def rate():
    """利率管理"""
    pass


@rate.command('sync')
@click.pass_context
def rate_sync(ctx):
    """同步利率"""
    svc = RateService(ctx.obj['conn'])
    result = svc.sync_rates()
    click.echo("同步完成:")
    for item in result.get('lpr', []):
        click.echo(f"  LPR {item['term']}: {item['rate']} ({item['date']})")
    for item in result.get('central_bank', []):
        click.echo(f"  央行利率: {item['rate']}")
    if result.get('errors'):
        click.echo("错误:")
        for err in result['errors']:
            click.echo(f"  ❌ {err}")


@rate.command('latest')
@click.option('--type', default='LPR', help='利率类型')
@click.option('--term', default=None, help='期限')
@click.pass_context
def rate_latest(ctx, type, term):
    """查询最新利率"""
    svc = RateService(ctx.obj['conn'])
    result = svc.get_latest(type, term)
    if result:
        click.echo(f"{result['rate_type']} {result.get('term', '')}: {result['rate']} ({result.get('effective_date', '')})")
    else:
        click.echo("无数据")


# ========== 入口 ==========

if __name__ == '__main__':
    cli()
