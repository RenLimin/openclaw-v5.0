"""数据集成模块 v2.1 — 单元测试。

对齐 DESIGN-DETAIL-INTEGRATION-v2.1.md：
  1. 连接器注册表（注册/实例化/未注册拒绝）
  2. LocalImportConnector（CSV/Excel 读取 + 字段映射 + 校验）
  3. IntegrationService（同步 + 暂存 + 提升 + 频率 + 历史 + 重试）
  4. SyncResult 数据结构
"""

import sys
import pytest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

import pandas as pd

from bdms.core import db as _db
from bdms.modules.integration import (
    BaseConnector, ConnectorRegistry, SyncResult,
    IntegrationService, LocalImportConnector, OnesConnector,
)


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "test.db"
    _db.init_db(path)
    return path


@pytest.fixture
def svc(db_path):
    return IntegrationService(db_path=db_path)


# ─── 1. 注册表 ───

class TestRegistry:

    def test_builtin_connectors_registered(self):
        for name in ("ones", "oa", "timesheet", "wecom_doc", "local_import"):
            assert ConnectorRegistry.available(name), name

    def test_create_unknown(self):
        with pytest.raises(KeyError):
            ConnectorRegistry.create("bogus")

    def test_register_invalid_class(self):
        class NotAConnector:
            pass
        with pytest.raises(TypeError):
            ConnectorRegistry.register(NotAConnector)

    def test_register_missing_name(self):
        class NoName(BaseConnector):
            def authenticate(self): return True
            def fetch(self, **p): return []
            def normalize(self, raw): return raw
        with pytest.raises(ValueError):
            ConnectorRegistry.register(NoName)


# ─── 2. LocalImportConnector ───

class TestLocalImport:

    def test_fetch_csv(self, db_path, tmp_path):
        csv = tmp_path / "data.csv"
        csv.write_text("合同编号,金额\nC1,100\nC2,200\n")
        conn = LocalImportConnector(db_path=db_path)
        items = conn.fetch(file_path=str(csv))
        assert len(items) == 2
        assert items[0]["data"]["合同编号"] == "C1"

    def test_fetch_unsupported(self, db_path, tmp_path):
        f = tmp_path / "x.txt"
        f.write_text("x")
        conn = LocalImportConnector(db_path=db_path)
        with pytest.raises(ValueError):
            conn.fetch(file_path=str(f))

    def test_fetch_missing(self, db_path):
        conn = LocalImportConnector(db_path=db_path)
        with pytest.raises(FileNotFoundError):
            conn.fetch(file_path="/nonexistent/x.csv")

    def test_field_mapping(self, db_path, tmp_path):
        # 配置映射
        from bdms.core.db import get_connection
        conn_db = get_connection(db_path)
        conn_db.execute(
            "INSERT INTO int_field_mapping "
            "(connector_name, target_module, target_table, source_field, target_field, is_required) "
            "VALUES ('local_import', 'delivery_report', 'dr', '合同编号', 'contract_no', 1)")
        conn_db.commit()
        conn_db.close()

        csv = tmp_path / "m.csv"
        csv.write_text("合同编号,金额\nC1,100\n,200\n")  # 第二行合同号空
        conn = LocalImportConnector(db_path=db_path)
        items = conn.fetch(file_path=str(csv))

        n1 = conn.normalize(items[0])
        assert n1["contract_no"] == "C1"

        # 必填校验：第二行空 → error
        n2 = conn.normalize(items[1])
        errors = conn.validate(n2)
        assert any("contract_no" in e for e in errors)


# ─── 3. IntegrationService ───

class TestIntegrationService:

    def test_list_connectors(self, svc):
        connectors = svc.list_connectors()
        names = [c["name"] for c in connectors]
        assert "ones" in names and "local_import" in names
        assert all("status" in c for c in connectors)

    def test_sync_local_import(self, svc, db_path, tmp_path):
        csv = tmp_path / "s.csv"
        csv.write_text("合同编号,金额\nC1,100\nC2,200\n")
        result = svc.sync("local_import", file_path=str(csv))
        assert result["status"] == "success"
        assert result["total_fetched"] == 2
        assert result["batch_id"]

        # 暂存数据可查
        staging = svc.get_staging_data("local_import", result["batch_id"])
        assert len(staging) == 2
        assert staging[0]["status"] == "pending"

    def test_sync_history(self, svc, tmp_path):
        csv = tmp_path / "h.csv"
        csv.write_text("a,b\n1,2\n")
        svc.sync("local_import", file_path=str(csv))
        history = svc.get_sync_history("local_import")
        assert len(history) == 1
        assert history[0]["connector_name"] == "local_import"

    def test_promote_staging(self, svc, tmp_path):
        csv = tmp_path / "p.csv"
        csv.write_text("合同编号\nC1\nC2\n")
        result = svc.sync("local_import", file_path=str(csv))
        promoted = svc.promote_staging(
            "local_import", result["batch_id"],
            "delivery_report", "dr_sheet_row")
        assert promoted["promoted_count"] == 2
        assert promoted["error_count"] == 0

        # 提升后暂存变 processed
        pending = svc.get_staging_data(
            "local_import", result["batch_id"], status="pending")
        assert len(pending) == 0

    def test_frequency_config(self, svc):
        r = svc.configure_frequency("ones", "cron", cron_expr="0 2 * * *")
        assert r["schedule"] == "cron"
        cfg = svc.get_frequency_config("ones")
        assert cfg["cron_expr"] == "0 2 * * *"

    def test_frequency_validation(self, svc):
        with pytest.raises(ValueError):
            svc.configure_frequency("ones", "cron")  # 缺 cron_expr
        with pytest.raises(ValueError):
            svc.configure_frequency("ones", "event")  # 缺 triggers
        with pytest.raises(ValueError):
            svc.configure_frequency("ones", "bogus")

    def test_dead_letter(self, svc, db_path):
        svc.move_to_dead_letter("ones", "batch1", "src1", "超限失败", "network")
        letters = svc.get_dead_letters()
        assert len(letters) == 1
        assert letters[0]["error_type"] == "network"


# ─── 4. SyncResult ───

class TestSyncResult:

    def test_to_dict(self):
        r = SyncResult(
            connector_name="test", batch_id="b1", status="success",
            total_fetched=10, new_count=5)
        d = r.to_dict()
        assert d["connector_name"] == "test"
        assert d["total_fetched"] == 10
        assert "errors" in d
