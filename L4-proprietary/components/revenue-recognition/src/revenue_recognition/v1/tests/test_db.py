"""Tests for revenue_recognition.v1.db module."""

import sqlite3
import pytest
from pathlib import Path
from revenue_recognition.v1 import db


class TestGetConnection:
    """Test get_connection function."""

    def test_returns_connection(self, tmp_db_path):
        conn = db.get_connection(tmp_db_path)
        assert isinstance(conn, sqlite3.Connection)
        conn.close()

    def test_row_factory_is_set(self, tmp_db_path):
        conn = db.get_connection(tmp_db_path)
        assert conn.row_factory == sqlite3.Row
        conn.close()

    def test_creates_parent_dir(self, tmp_db_path):
        conn = db.get_connection(tmp_db_path)
        assert tmp_db_path.parent.exists()
        conn.close()

    def test_default_path(self):
        conn = db.get_connection()
        assert isinstance(conn, sqlite3.Connection)
        conn.close()

    def test_wal_mode(self, tmp_db_path):
        conn = db.get_connection(tmp_db_path)
        result = conn.execute("PRAGMA journal_mode").fetchone()
        assert result[0] == "wal"
        conn.close()

    def test_foreign_keys_on(self, tmp_db_path):
        conn = db.get_connection(tmp_db_path)
        result = conn.execute("PRAGMA foreign_keys").fetchone()
        assert result[0] == 1
        conn.close()


class TestInitDb:
    """Test init_db function."""

    def test_creates_plan_draft_table(self, tmp_db_path):
        db.init_db(tmp_db_path)
        conn = db.get_connection(tmp_db_path)
        result = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='plan_draft'"
        ).fetchone()
        assert result is not None
        conn.close()

    def test_creates_budget_exec_table(self, tmp_db_path):
        db.init_db(tmp_db_path)
        conn = db.get_connection(tmp_db_path)
        result = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='budget_exec'"
        ).fetchone()
        assert result is not None
        conn.close()

    def test_plan_draft_has_columns(self, tmp_db_path):
        db.init_db(tmp_db_path)
        conn = db.get_connection(tmp_db_path)
        cols = [row[1] for row in conn.execute("PRAGMA table_info(plan_draft)").fetchall()]
        assert "contract_no" in cols
        assert "customer" in cols
        assert "perf_amount" in cols
        assert "rev_method" in cols
        conn.close()

    def test_budget_exec_has_columns(self, tmp_db_path):
        db.init_db(tmp_db_path)
        conn = db.get_connection(tmp_db_path)
        cols = [row[1] for row in conn.execute("PRAGMA table_info(budget_exec)").fetchall()]
        assert "category" in cols
        assert "contract_no" in cols
        assert "perf_amount" in cols
        assert "m202601" in cols
        assert "a202606" in cols
        conn.close()

    def test_creates_indexes(self, tmp_db_path):
        db.init_db(tmp_db_path)
        conn = db.get_connection(tmp_db_path)
        indexes = [row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
        ).fetchall()]
        assert "idx_plan_contract" in indexes
        assert "idx_budget_contract" in indexes
        conn.close()

    def test_idempotent(self, tmp_db_path):
        db.init_db(tmp_db_path)
        db.init_db(tmp_db_path)
        conn = db.get_connection(tmp_db_path)
        tables = [row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
        assert "plan_draft" in tables
        assert "budget_exec" in tables
        conn.close()

    def test_returns_path(self, tmp_db_path):
        result = db.init_db(tmp_db_path)
        assert result == tmp_db_path
