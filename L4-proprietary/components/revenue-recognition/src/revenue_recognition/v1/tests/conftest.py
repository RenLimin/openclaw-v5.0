"""Shared fixtures for revenue-recognition tests."""

import sqlite3
import tempfile
import os
import pytest
from pathlib import Path


@pytest.fixture
def tmp_db_path():
    """Create a temporary database file and yield its path."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield Path(path)
    os.unlink(path)


@pytest.fixture
def tmp_db_conn(tmp_db_path):
    """Return an initialized in-memory-like connection with schema."""
    from revenue_recognition.v1.db import init_db, get_connection
    init_db(tmp_db_path)
    conn = get_connection(tmp_db_path)
    yield conn
    conn.close()


@pytest.fixture
def engine_with_data(tmp_db_path):
    """Create an engine with pre-populated test data."""
    from revenue_recognition.v1.db import init_db
    from revenue_recognition.v1.engine import RevenueEngine

    init_db(tmp_db_path)

    # Insert test data
    conn = sqlite3.connect(str(tmp_db_path))
    conn.execute("""
        INSERT INTO budget_exec (
            category, contract_no, contract_no_cal, customer, end_user,
            sign_subject, archive_month, perf_id_budget, perf_detail_budget,
            perf_id, rev_method, perf_amount, rev_prior, rev_future,
            no_plan, unrev_prior, unrev_adj, plan_start, plan_end, plan_done,
            m202601, m202602, m202603, m202604, m202605, m202606,
            m202607, m202608, m202609, m202610, m202611, m202612,
            year_est, h1_plan, h1_actual, h1_ahead, h1_behind,
            a202601, a202602, a202603, a202604, a202605, a202606,
            disappear_2026, disappear_future, disappear_note, rebuild_perf
        ) VALUES (
            '新签', 'C001', 'C001', '客户A', '最终用户A',
            '签约主体A', '202601', 'P001', '履约明细1',
            'P001', '时段法', 100000.0, 50000.0, 50000.0,
            0, 50000.0, 50000.0, '2026-01-01', '2026-12-31', '2026-06-30',
            8333.33, 8333.33, 8333.33, 8333.33, 8333.33, 8333.33,
            8333.33, 8333.33, 8333.33, 8333.33, 8333.33, 8333.52,
            100000.0, 50000.0, 50000.0, 10000.0, 5000.0,
            8333.33, 8333.33, 8333.33, 8333.33, 8333.33, 8333.38,
            0, 0, NULL, NULL
        )
    """)
    conn.execute("""
        INSERT INTO budget_exec (
            category, contract_no, contract_no_cal, customer, end_user,
            sign_subject, archive_month, perf_id_budget, perf_detail_budget,
            perf_id, rev_method, perf_amount, rev_prior, rev_future,
            no_plan, unrev_prior, unrev_adj, plan_start, plan_end, plan_done,
            m202601, m202602, m202603, m202604, m202605, m202606,
            m202607, m202608, m202609, m202610, m202611, m202612,
            year_est, h1_plan, h1_actual, h1_ahead, h1_behind,
            a202601, a202602, a202603, a202604, a202605, a202606,
            disappear_2026, disappear_future, disappear_note, rebuild_perf
        ) VALUES (
            '递延', 'C002', 'C002', '客户B', '最终用户B',
            '签约主体B', '202601', 'P002', '履约明细2',
            'P002', '时点法', 200000.0, 100000.0, 100000.0,
            0, 100000.0, 100000.0, '2026-01-01', '2026-12-31', '2026-06-30',
            16666.67, 16666.67, 16666.67, 16666.67, 16666.67, 16666.67,
            16666.67, 16666.67, 16666.67, 16666.67, 16666.67, 16666.65,
            200000.0, 100000.0, 100000.0, 20000.0, 10000.0,
            16666.67, 16666.67, 16666.67, 16666.67, 16666.67, 16666.65,
            5000.0, 0, '合同部分终止', '重拆1'
        )
    """)
    conn.execute("""
        INSERT INTO budget_exec (
            category, contract_no, contract_no_cal, customer, end_user,
            sign_subject, archive_month, perf_id_budget, perf_detail_budget,
            perf_id, rev_method, perf_amount, rev_prior, rev_future,
            no_plan, unrev_prior, unrev_adj, plan_start, plan_end, plan_done,
            m202601, m202602, m202603, m202604, m202605, m202606,
            m202607, m202608, m202609, m202610, m202611, m202612,
            year_est, h1_plan, h1_actual, h1_ahead, h1_behind,
            a202601, a202602, a202603, a202604, a202605, a202606,
            disappear_2026, disappear_future, disappear_note, rebuild_perf
        ) VALUES (
            '新签', 'C003', 'C003', '客户C', '最终用户C',
            '签约主体C', '202602', 'P003', '履约明细3',
            'P003', '时段法', 150000.0, 75000.0, 75000.0,
            0, 75000.0, 75000.0, '2026-02-01', '2026-12-31', '2026-06-30',
            12500.0, 12500.0, 12500.0, 12500.0, 12500.0, 12500.0,
            12500.0, 12500.0, 12500.0, 12500.0, 12500.0, 12500.0,
            150000.0, 75000.0, 75000.0, 15000.0, 7500.0,
            12500.0, 12500.0, 12500.0, 12500.0, 12500.0, 12500.0,
            0, 0, NULL, NULL
        )
    """)
    conn.commit()
    conn.close()

    engine = RevenueEngine(db_path=tmp_db_path)
    return engine


@pytest.fixture
def engine_with_plan_data(tmp_db_path):
    """Create an engine with plan_draft test data."""
    from revenue_recognition.v1.db import init_db
    from revenue_recognition.v1.engine import RevenueEngine

    init_db(tmp_db_path)

    conn = sqlite3.connect(str(tmp_db_path))
    conn.execute("""
        INSERT INTO plan_draft (
            note, init_est_date, est_date, contract_no, archive_month,
            contract_no2, prod_seq, perf_id, budget_perf_id, dept,
            contract_name, customer, end_user, contract_note, ops_note,
            tax_rate, sign_date, contract_start, contract_end,
            service_months, contract_type, version_type, gift,
            prod_category, prod_name, perf_detail, std_prod_name,
            rev_subject, tax_subject, price_basis, accept_type,
            accept_term, payment_term, rev_method, no_exec_reason,
            qty_unit, qty, contract_amount, confirm_amount,
            perf_amount, plan_perf_amount, rev_before_2025,
            rev_2026_future, plan_disappear, disappear_reason
        ) VALUES (
            '说明1', '2026-06-30', '2026-06-30', 'C001', '202601',
            'C001', '1', 'P001', 'P001', '部门A',
            '合同名称1', '客户A', '最终用户A', '备注1', '操作备注1',
            0.06, '2025-01-15', '2025-01-01', '2026-12-31',
            24, '标准', 'V1', '否',
            '安全服务', '产品名称1', '履约明细1', '标准产品1',
            '收入科目1', '税金科目1', '价格依据1', '验收单',
            '验收条款1', '收款节奏1', '时段法', NULL,
            '次', 10, 100000.0, 100000.0,
            100000.0, 100000.0, 50000.0,
            50000.0, 0, NULL
        )
    """)
    conn.commit()
    conn.close()

    engine = RevenueEngine(db_path=tmp_db_path)
    return engine
