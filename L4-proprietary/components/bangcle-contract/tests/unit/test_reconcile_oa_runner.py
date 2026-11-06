"""scripts/reconcile_oa runner 单元测试（P4.4，详设 §5）。

全程 fake cube / fake reader / 临时 DB，不触网、不开浏览器。
覆盖：
- 完整数据链：contract(oa_billid) → cube 卡片 requestid → reader 审批链 → 四态
- 降级：no_billid / 卡片读失败 / requestid 字段缺失
- 单合同 scope
"""
from __future__ import annotations

import os
import sys

import pytest

# 组件根注入
HERE = os.path.dirname(os.path.abspath(__file__))
COMPONENT_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
if COMPONENT_ROOT not in sys.path:
    sys.path.insert(0, COMPONENT_ROOT)

import importlib.util  # noqa: E402

_runner_path = os.path.join(COMPONENT_ROOT, "scripts", "reconcile_oa.py")
_spec = importlib.util.spec_from_file_location("reconcile_oa_runner", _runner_path)
runner = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(runner)
from services.oa.approval_log import ApprovalChain, ApprovalEntry  # noqa: E402


# ---------- fakes ----------

class _FakeCard:
    def __init__(self, fields):
        self.main_fields = fields


class _FakeCube:
    """billid → 卡片；billid 'ERR' 抛错模拟读卡片失败。"""

    def __init__(self, billid_fields):
        self._m = billid_fields

    def get_contract(self, billid):
        b = str(billid)
        if b == "ERR":
            raise RuntimeError("card boom")
        if b not in self._m:
            raise RuntimeError("unknown billid")
        return _FakeCard(self._m[b])


class _FakeReader:
    """requestid → ApprovalChain；'UX' 抛不可用。"""

    def __init__(self, chains):
        self._chains = chains

    def read_approval_chain(self, requestid):
        r = str(requestid)
        if r == "UX":
            from services.oa.approval_log import ApprovalLogUnavailable
            raise ApprovalLogUnavailable("unavailable")
        return self._chains[r]


def _entry(action="提交", tx=None):
    return ApprovalEntry(
        node="节点", operator="张三", operator_id="1", dept="部门",
        action=action, opinion="", date="2026-11-06", time="10:00",
        receivers="", log_id="99",
    )


def _chain(action="提交", tx_status="1"):
    return ApprovalChain(
        requestid="x", workflowid="w", tx_status=tx_status,
        creator_node_id="1", viewer_user_id="1",
        entries=[_entry(action)],
    )


@pytest.fixture
def tmp_db(monkeypatch, tmp_path):
    """建临时 contracts DB 并注入 runner 使用的 default_db_path。"""
    from repository import db as dbmod

    db_path = str(tmp_path / "test.db")
    with dbmod.Repository(db_path) as repo:
        # V2 schema
        for stmt in dbmod.SCHEMA_V2:
            repo._conn.execute(stmt)
        repo._conn.commit()

    monkeypatch.setattr(dbmod, "default_db_path", lambda: db_path)
    return db_path


def _add_contract(db_path, contract_no, status, billid):
    from datetime import datetime
    import sqlite3
    conn = sqlite3.connect(db_path)
    now = datetime.now().isoformat()
    conn.execute(
        "INSERT INTO contracts (contract_no,status,oa_billid,created_at,updated_at)"
        " VALUES (?,?,?,?,?)",
        (contract_no, status, billid, now, now),
    )
    conn.commit()
    conn.close()


def test_full_chain_in_sync(tmp_db):
    # 本地 review ↔ OA review（提交 + tx=1）→ in_sync
    _add_contract(tmp_db, "C1", "review", "B1")
    cube = _FakeCube({"B1": {"合同审批流程→": "R1"}})
    reader = _FakeReader({"R1": _chain("提交", "1")})
    report = runner.run_reconcile(reader=reader, cube=cube)
    assert report["total_contracts"] == 1
    assert report["reconciled"] == 1
    assert report["counts"]["in_sync"] == 1
    assert report["attention_required"] == []


def test_full_chain_oa_ahead_on_return(tmp_db):
    # 本地 review，但 OA 已退回 → draft → oa_ahead
    _add_contract(tmp_db, "C2", "review", "B2")
    cube = _FakeCube({"B2": {"合同审批流程→": "R2"}})
    reader = _FakeReader({"R2": _chain("退回", "1")})
    report = runner.run_reconcile(reader=reader, cube=cube)
    assert report["counts"]["oa_ahead"] == 1
    assert len(report["attention_required"]) == 1


def test_no_billid_degrades(tmp_db):
    _add_contract(tmp_db, "C3", "draft", "")
    cube = _FakeCube({})
    reader = _FakeReader({})
    report = runner.run_reconcile(reader=reader, cube=cube)
    assert report["reconciled"] == 0
    assert report["counts"]["no_billid"] == 1
    assert report["items"][0]["kind"] == "no_billid"


def test_card_read_failure_degrades(tmp_db):
    _add_contract(tmp_db, "C4", "review", "ERR")
    cube = _FakeCube({})
    reader = _FakeReader({})
    report = runner.run_reconcile(reader=reader, cube=cube)
    assert report["counts"]["no_requestid"] == 1
    assert "card_read_failed" in report["items"][0]["detail"]


def test_requestid_field_missing_degrades(tmp_db):
    _add_contract(tmp_db, "C5", "review", "B5")
    cube = _FakeCube({"B5": {"其他字段": "v"}})
    reader = _FakeReader({})
    report = runner.run_reconcile(reader=reader, cube=cube)
    assert report["counts"]["no_requestid"] == 1
    assert report["items"][0]["detail"] == "requestid_field_missing"


def test_reader_unavailable_becomes_oa_unknown(tmp_db):
    # billid/requestid 解析成功，但 reader 读不到审批链 → oa_unknown
    _add_contract(tmp_db, "C6", "review", "B6")
    cube = _FakeCube({"B6": {"合同审批流程→": "UX"}})
    reader = _FakeReader({})
    report = runner.run_reconcile(reader=reader, cube=cube)
    assert report["counts"]["oa_unknown"] == 1


def test_contract_id_scope(tmp_db):
    _add_contract(tmp_db, "C7", "review", "B7")
    _add_contract(tmp_db, "C8", "review", "B8")
    cube = _FakeCube({
        "B7": {"合同审批流程→": "R7"},
        "B8": {"合同审批流程→": "R8"},
    })
    reader = _FakeReader({
        "R7": _chain("提交", "1"),
        "R8": _chain("提交", "1"),
    })
    # 只对第一个（自增 id=1）
    report = runner.run_reconcile(contract_id=1, reader=reader, cube=cube)
    assert report["total_contracts"] == 1
    assert report["items"][0]["contract_no"] == "C7"


def test_mixed_batch_isolation(tmp_db):
    # 一个 in_sync、一个无 billid、一个读卡片失败，互不影响
    _add_contract(tmp_db, "OK", "review", "BOK")
    _add_contract(tmp_db, "NOBILL", "draft", "")
    _add_contract(tmp_db, "ERRC", "review", "ERR")
    cube = _FakeCube({"BOK": {"合同审批流程→": "ROK"}})
    reader = _FakeReader({"ROK": _chain("提交", "1")})
    report = runner.run_reconcile(reader=reader, cube=cube)
    assert report["total_contracts"] == 3
    assert report["counts"]["in_sync"] == 1
    assert report["counts"]["no_billid"] == 1
    assert report["counts"]["no_requestid"] == 1
