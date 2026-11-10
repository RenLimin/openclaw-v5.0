"""Phase 0 骨架测试：N1 guard + 状态机/检查点/HITL/恢复/幂等。"""
import pytest, os, tempfile
from runner.state import CheckpointStore, new_state
from runner.engine import Engine, HITL_STATES
from runner.steps import n1_guard, n2_collect, n4_parse, n5_compose, n7_render
from runner.steps.n1_guard import validate, GuardError


def make_engine(tmp):
    # N2 注入 fake，避免触发真实浏览器（真实取数在 E2E 验证）
    import tempfile as _tf, os as _os
    def _fake_ones(name):
        f = _os.path.join(tmp, "ones.csv"); open(f, "w").write("a,b\n1,2\n"); return f
    def _fake_oa(month, export_dir=None, headless=True):
        _os.makedirs(export_dir, exist_ok=True)
        f = _os.path.join(export_dir, "ledger.xlsx"); open(f, "wb").write(b"x")
        return {"file": f, "size": 1}
    n2_collect.set_fetchers(ones=_fake_ones, oa=_fake_oa)
    store = CheckpointStore(os.path.join(tmp, "cdi.db"))
    steps = {
        "N1_guard": n1_guard.run,
        "N2_collect": n2_collect.run,
        "N4_parse": n4_parse.run,
        "N5_compose": n5_compose.run,
        "N7_render": n7_render.run,
    }
    return Engine(store, steps)


GOOD = {"customer": "中国建设银行股份有限公司",
        "period": {"start": "2026-01-01", "end": "2026-11-01"},
        "audience": "internal"}


# ---------- N1 guard 校验 ----------
@pytest.mark.parametrize("field,mut", [
    ("empty_customer", lambda d: d.update(customer="")),
    ("bad_period",     lambda d: d.update(period={"start": "abc", "end": "def"})),
    ("reversed",       lambda d: d.update(period={"start": "2026-12-01", "end": "2026-01-01"})),
    ("bad_audience",   lambda d: d.update(audience="public")),
    ("bad_scope",      lambda d: d.update(scope={"hack": 1})),
])
def test_guard_rejects(field, mut):
    d = {**GOOD, "period": dict(GOOD["period"])}
    mut(d)
    with pytest.raises(GuardError):
        validate(d)


def test_guard_accepts_known():
    norm = validate(GOOD)
    assert norm["customerKnown"] is True
    assert norm["customer"] == "中国建设银行股份有限公司"


def test_guard_unknown_customer_warns_but_ok():
    d = {**GOOD, "customer": "某新客户"}
    norm = validate(d)
    assert norm["customerKnown"] is False


# ---------- 状态机 / HITL ----------
def test_full_flow_with_two_gates(tmp_path):
    eng = make_engine(str(tmp_path))
    st = eng.start("t1", validate(GOOD))
    # 自动跑到 gate1
    assert st["current_state"] == "N3_manifest_gate"
    st = eng.decide("t1", "gate1", "approve")
    assert st["current_state"] == "N6_sign_gate"
    st = eng.decide("t1", "gate2", "approve")
    assert st["current_state"] == "done"


def test_gate1_reject_back_to_collect(tmp_path):
    eng = make_engine(str(tmp_path))
    eng.start("t", validate(GOOD))
    st = eng.decide("t", "gate1", "reject")
    assert st["current_state"] == "N3_manifest_gate"  # 重跑 N2 后又停 gate1


def test_gate2_revise_back_to_compose(tmp_path):
    eng = make_engine(str(tmp_path))
    eng.start("t", validate(GOOD))
    eng.decide("t", "gate1", "approve")
    st = eng.decide("t", "gate2", "revise")
    assert st["current_state"] == "N6_sign_gate"


def test_checkpoint_persist_and_resume(tmp_path):
    db = os.path.join(str(tmp_path), "cdi.db")
    store = CheckpointStore(db)
    steps = {"N1_guard": n1_guard.run, "N2_collect": n2_collect.run,
             "N4_parse": n4_parse.run, "N5_compose": n5_compose.run,
             "N7_render": n7_render.run}
    eng = Engine(store, steps)
    eng.start("t", validate(GOOD))
    # 模拟全新引擎实例（进程重启）
    store2 = CheckpointStore(db)
    eng2 = Engine(store2, steps)
    st = eng2.get("t")
    assert st["current_state"] == "N3_manifest_gate"
    st = eng2.decide("t", "gate1", "skip")
    assert st["current_state"] == "N6_sign_gate"


def test_invalid_gate_decision(tmp_path):
    eng = make_engine(str(tmp_path))
    eng.start("t", validate(GOOD))
    with pytest.raises(ValueError):
        eng.decide("t", "gate1", "destroy")


def test_duplicate_start_rejected(tmp_path):
    eng = make_engine(str(tmp_path))
    eng.start("t", validate(GOOD))
    with pytest.raises(ValueError):
        eng.start("t", validate(GOOD))
