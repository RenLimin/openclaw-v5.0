"""仪表盘 API 测试 — 基于 FastAPI TestClient"""

import pytest
import sys
import os
import tempfile
from datetime import date, timedelta

# 必须在 import fin_l4 之前设置数据库目录
_test_db_dir = tempfile.mkdtemp(prefix='fin-dash-test-')
os.environ['FIN4_DB_DIR'] = _test_db_dir



@pytest.fixture(scope='module')
def client():
    """创建带测试数据的 FastAPI TestClient（module 级别，所有测试共享）"""
    from fin_l4.db import init_db
    from fin_l4.db.repositories import (
        FamilyRepository, AccountRepository, TransactionRepository,
        CategoryRepository, BudgetRepository, PortfolioRepository,
        HoldingRepository,
    )
    from fin_l4.web.main import app
    from fastapi.testclient import TestClient

    db_path = os.path.join(_test_db_dir, 'fin_l4.db')
    init_db(db_path)

    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    family_id = 'default'

    # 确保家庭存在
    conn.execute("INSERT OR IGNORE INTO fin4_family (id, name, currency) VALUES (?, ?, ?)",
                 (family_id, '测试家庭', 'CNY'))
    conn.commit()

    # 创建账户
    account_repo = AccountRepository(conn)
    accounts = {}
    acc_list = [
        ('CASH', '现金', 'ASSET'),
        ('BANK', '银行存款', 'ASSET'),
        ('CC', '信用卡', 'LIABILITY'),
        ('LOAN', '房贷', 'LIABILITY'),
        ('EQUITY', '初始权益', 'EQUITY'),
        ('SALARY', '工资收入', 'INCOME'),
        ('INV_INC', '投资收益', 'INCOME'),
        ('FOOD', '餐饮费', 'EXPENSE'),
        ('TRANSPORT', '交通费', 'EXPENSE'),
        ('HOUSING', '住房支出', 'EXPENSE'),
        ('SHOPPING', '购物费', 'EXPENSE'),
        ('INSURANCE', '保险费', 'EXPENSE'),
    ]
    for code, name, acc_type in acc_list:
        acc_id = account_repo.create(family_id, code, name, acc_type)
        accounts[code] = acc_id

    # 创建分类
    cat_repo = CategoryRepository(conn)
    categories = {}
    cat_list = [
        ('餐饮', 'expense', '#ef4444'),
        ('交通', 'expense', '#f97316'),
        ('住房', 'expense', '#f59e0b'),
        ('购物', 'expense', '#ec4899'),
        ('保险', 'expense', '#8b5cf6'),
        ('医疗', 'expense', '#f43f5e'),
        ('工资', 'income', '#10b981'),
        ('投资', 'income', '#06b6d4'),
    ]
    for name, cat_type, color in cat_list:
        cid = cat_repo.create(family_id, name, cat_type, color=color)
        categories[name] = cid

    # 创建交易（最近 3 个月）
    txn_repo = TransactionRepository(conn)
    today = date.today()

    # 收入交易
    for i in range(3):
        d = today - timedelta(days=30 * i + 5)
        txn_repo.create(
            family_id=family_id, date=str(d), amount='35000',
            debit_account_id=accounts['BANK'], credit_account_id=accounts['SALARY'],
            note=f'{d.month}月工资', category_id=categories['工资'], source='test',
        )
    txn_repo.create(
        family_id=family_id, date=str(today - timedelta(days=15)), amount='5000',
        debit_account_id=accounts['BANK'], credit_account_id=accounts['INV_INC'],
        note='投资收益', category_id=categories['投资'], source='test',
    )

    # 支出交易
    patterns = [
        (3, 'FOOD', '餐饮', 300, '餐饮'),
        (2, 'TRANSPORT', '交通', 200, '交通'),
        (1, 'HOUSING', '房租', 5000, '住房'),
        (2, 'SHOPPING', '购物', 800, '购物'),
        (1, 'INSURANCE', '保险费', 2000, '保险'),
    ]
    for month_offset in range(3):
        base_day = today - timedelta(days=30 * month_offset)
        for count, acc_code, note_prefix, avg_amt, cat_name in patterns:
            for i in range(count):
                d = base_day - timedelta(days=i * 7 + 1)
                amt = str(avg_amt + i * 50)
                txn_repo.create(
                    family_id=family_id, date=str(d), amount=amt,
                    debit_account_id=accounts[acc_code],
                    credit_account_id=accounts['BANK'],
                    note=f'{note_prefix}-{i}', category_id=categories[cat_name],
                    source='test',
                )

    # 设置预算
    budget_repo = BudgetRepository(conn)
    month_str = today.strftime('%Y-%m')
    budget_items = [
        ('餐饮', '3000'),
        ('交通', '1500'),
        ('住房', '5000'),
        ('购物', '2000'),
        ('保险', '2000'),
        ('医疗', '1000'),
    ]
    for cat_name, amount in budget_items:
        budget_repo.upsert(family_id, categories[cat_name], month_str, amount)

    # 创建投资组合
    port_repo = PortfolioRepository(conn)
    hold_repo = HoldingRepository(conn)
    pid = port_repo.create(family_id, '主投资组合', 'CNY')
    holdings = [
        ('stock', '贵州茅台', '600519', '10', '1800', '1950'),
        ('stock', '腾讯控股', '00700', '200', '350', '380'),
        ('fund', '易方达蓝筹', '005827', '5000', '2.0', '2.2'),
        ('bond', '国债ETF', '511010', '1000', '100', '102'),
    ]
    for h in holdings:
        hold_repo.create(pid, h[0], h[1], h[2], h[3], h[4], h[5])

    conn.commit()
    conn.close()

    # 把账户/分类 ID 存下来供测试使用
    client._test_accounts = accounts
    client._test_categories = categories

    with TestClient(app) as c:
        yield c

    # 清理（module 级别，所有测试跑完后执行一次）
    import shutil
    shutil.rmtree(_test_db_dir, ignore_errors=True)


# ========== 测试用例 ==========

class TestDashboardAPI:
    """仪表盘 API 测试"""

    def test_health(self, client):
        """健康检查返回 200"""
        resp = client.get('/health')
        assert resp.status_code == 200
        data = resp.json()
        assert data['status'] == 'ok'
        assert data['layer'] == 'L4'

    def test_overview_structure(self, client):
        """总览接口返回正确字段"""
        resp = client.get('/api/v1/dashboard/overview')
        assert resp.status_code == 200
        data = resp.json()
        required_fields = [
            'total_assets', 'total_liabilities', 'net_worth',
            'monthly_income', 'monthly_expense', 'monthly_savings',
            'savings_rate', 'debt_ratio', 'month',
        ]
        for f in required_fields:
            assert f in data, f'缺少字段: {f}'

    def test_overview_values_positive(self, client):
        """总览数据有正确的收入支出"""
        resp = client.get('/api/v1/dashboard/overview')
        data = resp.json()
        assert float(data['monthly_income']) > 0
        assert float(data['monthly_expense']) > 0
        savings_rate = float(data['savings_rate'])
        assert -100 < savings_rate < 1000

    def test_monthly_trend_count(self, client):
        """月度趋势至少返回 1 个月数据"""
        resp = client.get('/api/v1/dashboard/monthly-trend?months=12')
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_monthly_trend_structure(self, client):
        """月度趋势每条数据结构正确"""
        resp = client.get('/api/v1/dashboard/monthly-trend?months=12')
        data = resp.json()
        for item in data:
            assert 'month' in item
            assert 'income' in item
            assert 'expense' in item
            assert 'savings' in item
            assert len(item['month']) == 7
            assert item['month'][4] == '-'

    def test_categories_expense(self, client):
        """支出分类统计非空且结构正确"""
        resp = client.get('/api/v1/dashboard/categories?type=expense')
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) > 0
        first = data[0]
        assert 'category_id' in first
        assert 'category_name' in first
        assert 'type' in first
        assert 'amount' in first
        assert first['type'] == 'expense'

    def test_categories_income(self, client):
        """收入分类统计非空"""
        resp = client.get('/api/v1/dashboard/categories?type=income')
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) > 0
        assert data[0]['type'] == 'income'

    def test_categories_all(self, client):
        """全部分类包含收入和支出"""
        resp = client.get('/api/v1/dashboard/categories')
        data = resp.json()
        types = {item['type'] for item in data}
        assert 'income' in types
        assert 'expense' in types

    def test_budget_structure(self, client):
        """预算执行情况结构正确"""
        resp = client.get('/api/v1/dashboard/budget')
        assert resp.status_code == 200
        data = resp.json()
        assert 'total_budget' in data
        assert 'total_spent' in data
        assert 'statuses' in data
        assert isinstance(data['statuses'], list)
        assert len(data['statuses']) > 0

    def test_budget_status_item(self, client):
        """每条预算状态包含必要字段"""
        resp = client.get('/api/v1/dashboard/budget')
        data = resp.json()
        status = data['statuses'][0]
        required = ['category', 'budget', 'spent', 'remaining', 'usage_pct', 'status']
        for f in required:
            assert f in status, f'预算状态缺少字段: {f}'
        assert status['status'] in ('ok', 'warning', 'exceeded')

    def test_investments_structure(self, client):
        """投资组合结构正确"""
        resp = client.get('/api/v1/dashboard/investments')
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) > 0

    def test_investments_holdings(self, client):
        """投资组合包含持仓且收益计算正确"""
        resp = client.get('/api/v1/dashboard/investments')
        data = resp.json()
        portfolio = data[0]
        assert 'portfolio_name' in portfolio
        assert 'total_value' in portfolio
        assert 'total_gain' in portfolio
        assert 'total_gain_pct' in portfolio
        assert 'holdings' in portfolio
        assert len(portfolio['holdings']) > 0
        # 检查茅台：10 股 * (1950 - 1800) = 1500 收益
        mt = next((h for h in portfolio['holdings'] if h['asset_name'] == '贵州茅台'), None)
        assert mt is not None
        assert float(mt['gain']) == 1500.0
        assert float(mt['gain_pct']) > 0

    def test_recent_transactions_count(self, client):
        """最近交易列表返回正确数量"""
        resp = client.get('/api/v1/dashboard/transactions?limit=5')
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 5

    def test_recent_transactions_fields(self, client):
        """最近交易字段完整"""
        resp = client.get('/api/v1/dashboard/transactions?limit=3')
        data = resp.json()
        for t in data:
            assert 'id' in t
            assert 'date' in t
            assert 'amount' in t
            assert 'note' in t

    def test_create_transaction(self, client):
        """新增交易（快捷记账）"""
        acc_resp = client.get('/api/v1/accounts')
        accounts = acc_resp.json()
        bank_acc = next(a for a in accounts if a['code'] == 'BANK')
        food_acc = next(a for a in accounts if a['code'] == 'FOOD')

        resp = client.post('/api/v1/transactions', json={
            'date': str(date.today()),
            'amount': '88.88',
            'debit_account_id': food_acc['id'],
            'credit_account_id': bank_acc['id'],
            'note': '测试记账-仪表盘',
        })
        assert resp.status_code == 200
        result = resp.json()
        assert result['status'] == 'ok'
        assert 'id' in result

    def test_swagger_ui_accessible(self, client):
        """Swagger UI 可访问"""
        resp = client.get('/docs')
        assert resp.status_code == 200
        text = resp.text.lower()
        assert 'swagger' in text or 'openapi' in text

    def test_dashboard_page_renders(self, client):
        """仪表盘页面正常渲染且包含 ECharts"""
        resp = client.get('/')
        assert resp.status_code == 200
        assert '仪表盘' in resp.text
        assert 'echarts' in resp.text.lower()
