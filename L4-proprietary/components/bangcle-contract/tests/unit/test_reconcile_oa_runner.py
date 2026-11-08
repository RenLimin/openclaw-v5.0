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


class _FakeBridge:
    """P5.3: 按 contract_no 返回决策链；缺省抛异常模拟无决策源。

    decisions_map: contract_no → decisions list（DecisionService.replay 形态）。
    """

    def __init__(self, decisions_map):
        self._m = decisions_map

    def decision_chain(self, contract_no):
        c = str(contract_no)
        if c not in self._m:
            raise ValueError(f"no decision source: {c}")
        return self._m[c]


def _decision(action_type, result="allowed"):
    return {
        "action_type": action_type,
        "result": result,
        "actor_id": "sales",
        "actor_kind": "human",
    }


def test_full_chain_in_sync(tmp_db):
    # 本地决策链（submit_contract→review）↔ OA review（提交 + tx=1）→ in_sync
    _add_contract(tmp_db, "C1", "review", "B1")
    cube = _FakeCube({"B1": {"合同审批流程→": "R1"}})
    reader = _FakeReader({"R1": _chain("提交", "1")})
    bridge = _FakeBridge({"C1": [_decision("submit_contract")]})
    report = runner.run_reconcile(reader=reader, cube=cube, bridge=bridge)
    assert report["total_contracts"] == 1
    assert report["reconciled"] == 1
    assert report["counts"]["in_sync"] == 1
    assert report["attention_required"] == []
    assert report["items"][0]["source"] == "decision_chain"
    assert report["items"][0]["local_state"] == "review"


def test_full_chain_oa_ahead_on_return(tmp_db):
    # 本地决策链已 approved，但 OA 已退回 → draft → oa_ahead
    _add_contract(tmp_db, "C2", "review", "B2")
    cube = _FakeCube({"B2": {"合同审批流程→": "R2"}})
    reader = _FakeReader({"R2": _chain("退回", "1")})
    bridge = _FakeBridge({"C2": [_decision("approve_contract")]})
    report = runner.run_reconcile(reader=reader, cube=cube, bridge=bridge)
    assert report["counts"]["oa_ahead"] == 1
    assert len(report["attention_required"]) == 1


def test_no_billid_degrades(tmp_db):
    _add_contract(tmp_db, "C3", "draft", "")
    cube = _FakeCube({})
    reader = _FakeReader({})
    bridge = _FakeBridge({})
    report = runner.run_reconcile(reader=reader, cube=cube, bridge=bridge)
    assert report["reconciled"] == 0
    assert report["counts"]["no_billid"] == 1
    assert report["items"][0]["kind"] == "no_billid"


def test_card_read_failure_degrades(tmp_db):
    _add_contract(tmp_db, "C4", "review", "ERR")
    cube = _FakeCube({})
    reader = _FakeReader({})
    bridge = _FakeBridge({})
    report = runner.run_reconcile(reader=reader, cube=cube, bridge=bridge)
    assert report["counts"]["no_requestid"] == 1
    assert "card_read_failed" in report["items"][0]["detail"]


def test_requestid_field_missing_degrades(tmp_db):
    _add_contract(tmp_db, "C5", "review", "B5")
    cube = _FakeCube({"B5": {"其他字段": "v"}})
    reader = _FakeReader({})
    bridge = _FakeBridge({})
    report = runner.run_reconcile(reader=reader, cube=cube, bridge=bridge)
    assert report["counts"]["no_requestid"] == 1
    assert report["items"][0]["detail"] == "requestid_field_missing"


def test_reader_unavailable_becomes_oa_unknown(tmp_db):
    # billid/requestid 解析成功、决策链可用，但 reader 读不到审批链 → oa_unknown
    _add_contract(tmp_db, "C6", "review", "B6")
    cube = _FakeCube({"B6": {"合同审批流程→": "UX"}})
    reader = _FakeReader({})
    bridge = _FakeBridge({"C6": [_decision("submit_contract")]})
    report = runner.run_reconcile(reader=reader, cube=cube, bridge=bridge)
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
    bridge = _FakeBridge({
        "C7": [_decision("submit_contract")],
        "C8": [_decision("submit_contract")],
    })
    # 只对第一个（自增 id=1）
    report = runner.run_reconcile(contract_id=1, reader=reader, cube=cube,
                                  bridge=bridge)
    assert report["total_contracts"] == 1
    assert report["items"][0]["contract_no"] == "C7"


def test_mixed_batch_isolation(tmp_db):
    # 一个 in_sync、一个无 billid、一个读卡片失败，互不影响
    _add_contract(tmp_db, "OK", "review", "BOK")
    _add_contract(tmp_db, "NOBILL", "draft", "")
    _add_contract(tmp_db, "ERRC", "review", "ERR")
    cube = _FakeCube({"BOK": {"合同审批流程→": "ROK"}})
    reader = _FakeReader({"ROK": _chain("提交", "1")})
    bridge = _FakeBridge({"OK": [_decision("submit_contract")]})
    report = runner.run_reconcile(reader=reader, cube=cube, bridge=bridge)
    assert report["total_contracts"] == 3
    assert report["counts"]["in_sync"] == 1
    assert report["counts"]["no_billid"] == 1
    assert report["counts"]["no_requestid"] == 1


# ---------- P5.3：决策链推导本地预期态 ----------

def test_local_state_from_decisions_no_committed(tmp_db):
    # 无 committed 记录 → default
    from contract_review.ontology_bridge.reconcile import (
        local_state_from_decisions,
    )
    assert local_state_from_decisions([], default="") == ""
    assert local_state_from_decisions(
        [_decision("reject_contract", result="rejected")],
        default="draft",
    ) == "draft"


def test_local_state_from_decisions_reject_chain(tmp_db):
    # 最近 committed = reject_contract → draft
    from contract_review.ontology_bridge.reconcile import (
        local_state_from_decisions,
    )
    chain = [
        _decision("submit_contract"),   # review
        _decision("reject_contract"),   # draft（最新 committed）
    ]
    assert local_state_from_decisions(chain) == "draft"


def test_local_state_from_decisions_submit_then_approve(tmp_db):
    # submit → approve → approved
    from contract_review.ontology_bridge.reconcile import (
        local_state_from_decisions,
    )
    chain = [
        _decision("submit_contract"),
        _decision("approve_contract"),
    ]
    assert local_state_from_decisions(chain) == "approved"


def test_local_state_from_decisions_submit_to_oa(tmp_db):
    # submit_to_oa → review
    from contract_review.ontology_bridge.reconcile import (
        local_state_from_decisions,
    )
    chain = [_decision("submit_to_oa")]
    assert local_state_from_decisions(chain) == "review"


def test_runner_decision_chain_four_states(tmp_db):
    """runner 集成：fake bridge 决策链 → 四态输出正确。"""
    # draft（无决策）↔ OA 退回 → in_sync
    _add_contract(tmp_db, "D1", "draft", "BD1")
    # approved（决策链）↔ OA 退回 → oa_ahead
    _add_contract(tmp_db, "D2", "approved", "BD2")
    # review（submit_to_oa）↔ OA 在审 → in_sync
    _add_contract(tmp_db, "D3", "review", "BD3")
    # draft（决策链 reject）↔ OA 批准办结 → local_ahead? 实际 draft < approved → oa_ahead
    _add_contract(tmp_db, "D4", "draft", "BD4")
    cube = _FakeCube({
        "BD1": {"合同审批流程→": "RD1"},
        "BD2": {"合同审批流程→": "RD2"},
        "BD3": {"合同审批流程→": "RD3"},
        "BD4": {"合同审批流程→": "RD4"},
    })
    reader = _FakeReader({
        "RD1": _chain("退回", "1"),      # OA draft
        "RD2": _chain("退回", "1"),      # OA draft
        "RD3": _chain("提交", "1"),      # OA review
        "RD4": _chain("批准", "0"),      # OA approved
    })
    bridge = _FakeBridge({
        "D1": [],                          # 无决策 → default "" → 与 draft 不可比
        "D2": [_decision("approve_contract")],  # approved
        "D3": [_decision("submit_to_oa")],     # review
        "D4": [_decision("reject_contract")],  # draft
    })
    report = runner.run_reconcile(reader=reader, cube=cube, bridge=bridge)
    by_no = {i["contract_no"]: i for i in report["items"]}
    # D1: 无决策（local ""）；OA 退回事件 → 本地未同步 → oa_ahead
    assert by_no["D1"]["kind"] == "oa_ahead"
    # D2: local approved；OA 退回事件 → 本地未同步回 draft → oa_ahead
    assert by_no["D2"]["kind"] == "oa_ahead"
    # D3: local review vs OA review → in_sync
    assert by_no["D3"]["kind"] == "in_sync"
    # D4: local draft vs OA approved → oa_ahead
    assert by_no["D4"]["kind"] == "oa_ahead"
    # 全部来源 decision_chain
    assert all(i["source"] == "decision_chain" for i in report["items"])


def test_runner_no_decision_source_degrades(tmp_db):
    # 有 billid/requestid，但无决策链 → no_decision_source 降级，不中断整批
    _add_contract(tmp_db, "E1", "review", "BE1")
    _add_contract(tmp_db, "E2", "review", "BE2")
    cube = _FakeCube({
        "BE1": {"合同审批流程→": "RE1"},
        "BE2": {"合同审批流程→": "RE2"},
    })
    reader = _FakeReader({
        "RE1": _chain("提交", "1"),
        "RE2": _chain("提交", "1"),
    })
    bridge = _FakeBridge({"E2": [_decision("submit_contract")]})
    report = runner.run_reconcile(reader=reader, cube=cube, bridge=bridge)
    assert report["counts"]["no_decision_source"] == 1
    assert report["counts"]["in_sync"] == 1
    assert report["items"][0]["detail"] == "no_decision_source"
