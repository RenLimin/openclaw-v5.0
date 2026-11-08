"""P7.1/P7.2 白盒单测：MarkingDirectory + PolicyEvaluator（DETAIL §6.1）。

覆盖：
- register 幂等（同 domain+code 重复不新增，更新可变字段）；
- grant 强制过期 / 90 天上限 / ttl<=0 拒 / 未注册 code 拒；
  grant 续期刷 revoked_at；revoke 后 active 不含；过期授予 active 不含；
- PolicyEvaluator：无 marking 只看 clearance；AND 缺标 deny（reason 标 code）；
  clearance 分级；claims 缺省 internal；坏 metadata/非数组 markings/
  未注册 code => fail-closed；
- realtime：claims 有标但 grant revoke/过期 => deny；normal 敏不实时、high 实时；
- realtime_assert：commit 层只复查 high 敏，非 high 放行，吊销即拒。

真实临时 SQLite；无第三方依赖。
"""
import datetime as dt
import os
import tempfile

import pytest

from ai_kb.db import AIKB
from ai_kb.ontology.markings import (
    CLEARANCE_LEVELS,
    MarkingDirectory,
    MarkingError,
    MarkingNotFound,
    PolicyEvaluator,
)

DOMAIN = "test-domain"


@pytest.fixture()
def kb():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    db = AIKB(path)
    db.init_db()
    db.init_ontology_marking_tables()
    db.get_or_create_domain("Test Domain", DOMAIN, "Test")
    yield db
    db.close()
    os.unlink(path)


@pytest.fixture()
def d(kb):
    return MarkingDirectory(kb)


@pytest.fixture()
def ev(kb, d):
    return PolicyEvaluator(kb, d)


def _claims(markings=(), clearance="internal", sub="agent:a"):
    return {"sub": sub, "markings": list(markings), "clearance": clearance}


# ---------------------------------------------------------------
# register
# ---------------------------------------------------------------

def test_register_and_get(d):
    mid = d.register(DOMAIN, "pii", "PII", sensitivity="high")
    got = d.get(DOMAIN, "pii")
    assert got["id"] == mid
    assert got["sensitivity"] == "high"


def test_register_idempotent_no_dup(d):
    m1 = d.register(DOMAIN, "pii", "PII")
    m2 = d.register(DOMAIN, "pii", "PII v2", sensitivity="high")
    assert m1 == m2
    assert len(d.list(DOMAIN)) == 1
    assert d.get(DOMAIN, "pii")["name"] == "PII v2"


def test_register_bad_sensitivity(d):
    with pytest.raises(MarkingError):
        d.register(DOMAIN, "x", "X", sensitivity="secret")


def test_register_empty_code(d):
    with pytest.raises(MarkingError):
        d.register(DOMAIN, "", "X")


# ---------------------------------------------------------------
# grant / revoke
# ---------------------------------------------------------------

def test_grant_unregistered_marking_denied(d):
    with pytest.raises(MarkingNotFound):
        d.grant(DOMAIN, "nope", "agent:a", source="directory", ttl_days=10)


def test_grant_over_max_days_denied(d):
    d.register(DOMAIN, "pii", "PII")
    with pytest.raises(MarkingError):
        d.grant(DOMAIN, "pii", "agent:a", source="directory", ttl_days=91)


def test_grant_zero_ttl_denied(d):
    d.register(DOMAIN, "pii", "PII")
    with pytest.raises(MarkingError):
        d.grant(DOMAIN, "pii", "agent:a", source="directory", ttl_days=0)


def test_grant_bad_source(d):
    d.register(DOMAIN, "pii", "PII")
    with pytest.raises(MarkingError):
        d.grant(DOMAIN, "pii", "agent:a", source="whisper", ttl_days=10)


def test_grant_default_ttl_within_max(d):
    d.register(DOMAIN, "pii", "PII")
    gid = d.grant(DOMAIN, "pii", "agent:a", source="directory")
    assert gid > 0
    assert "pii" in d.active_markings("agent:a", domain=DOMAIN)


def test_grant_renewal_clears_revoke(d):
    d.register(DOMAIN, "pii", "PII")
    d.grant(DOMAIN, "pii", "agent:a", source="directory", ttl_days=10)
    d.revoke(DOMAIN, "pii", "agent:a")
    assert d.active_markings("agent:a", domain=DOMAIN) == set()
    d.grant(DOMAIN, "pii", "agent:a", source="directory", ttl_days=10)
    assert "pii" in d.active_markings("agent:a", domain=DOMAIN)


def test_revoke_removes_active(d):
    d.register(DOMAIN, "pii", "PII")
    d.grant(DOMAIN, "pii", "agent:a", source="directory", ttl_days=10)
    d.revoke(DOMAIN, "pii", "agent:a")
    assert d.active_markings("agent:a", domain=DOMAIN) == set()


def test_expired_grant_not_active(d):
    d.register(DOMAIN, "pii", "PII")
    base = dt.datetime(2026, 1, 1)
    d.grant(DOMAIN, "pii", "agent:a", source="directory",
            ttl_days=10, now=base)
    assert d.active_markings("agent:a", domain=DOMAIN, now=base) == {"pii"}
    after = base + dt.timedelta(days=11)
    assert d.active_markings("agent:a", domain=DOMAIN, now=after) == set()


# ---------------------------------------------------------------
# PolicyEvaluator — clearance
# ---------------------------------------------------------------

def test_no_marking_clearance_ok(ev):
    md = {"permissions": {"clearance": "internal"}}
    assert ev.evaluate(_claims(clearance="internal"), md, verb="read",
                       domain=DOMAIN).allowed


def test_clearance_insufficient_denied(ev):
    md = {"permissions": {"clearance": "restricted"}}
    dec = ev.evaluate(_claims(clearance="internal"), md, verb="read",
                      domain=DOMAIN)
    assert not dec and dec.reason == "clearance"


def test_clearance_higher_subject_ok(ev):
    md = {"permissions": {"clearance": "public"}}
    assert ev.evaluate(_claims(clearance="restricted"), md, verb="read",
                       domain=DOMAIN).allowed


def test_claims_default_clearance_internal(ev):
    md = {}  # 对象无 permissions => 默认 internal
    dec = ev.evaluate({"sub": "a"}, md, verb="read", domain=DOMAIN)
    assert dec.allowed


# ---------------------------------------------------------------
# PolicyEvaluator — markings AND
# ---------------------------------------------------------------

def test_missing_marking_denied_with_code(ev, d):
    d.register(DOMAIN, "pii", "PII")
    md = {"markings": ["pii"], "permissions": {"clearance": "internal"}}
    dec = ev.evaluate(_claims(), md, verb="propose", domain=DOMAIN)
    assert not dec
    assert dec.reason == "missing_marking:pii"
    assert dec.missing == ["pii"]


def test_and_requires_all_markings(ev, d):
    d.register(DOMAIN, "pii", "PII")
    d.register(DOMAIN, "region-eu", "EU")
    md = {"markings": ["pii", "region-eu"],
          "permissions": {"clearance": "internal"}}
    dec = ev.evaluate(_claims(markings=["pii"]), md, verb="propose",
                      domain=DOMAIN)
    assert not dec and dec.missing == ["region-eu"]
    ok = ev.evaluate(_claims(markings=["pii", "region-eu"]), md,
                     verb="propose", domain=DOMAIN)
    assert ok.allowed


# ---------------------------------------------------------------
# PolicyEvaluator — fail-closed
# ---------------------------------------------------------------

def test_bad_metadata_non_dict(ev):
    assert not ev.evaluate(_claims(), "nonsense", verb="read", domain=DOMAIN)


def test_markings_not_list_fail_closed(ev):
    md = {"markings": "pii"}
    dec = ev.evaluate(_claims(markings=["pii"]), md, verb="read",
                      domain=DOMAIN)
    assert not dec and dec.reason == "bad_metadata"


def test_unregistered_marking_fail_closed(ev, d):
    # 对象引用了目录里没有的 code
    md = {"markings": ["ghost"], "permissions": {"clearance": "internal"}}
    dec = ev.evaluate(_claims(markings=["ghost"]), md, verb="read",
                      domain=DOMAIN)
    assert not dec and dec.reason == "unregistered_marking"


def test_bad_claims_markings_fail_closed(ev, d):
    d.register(DOMAIN, "pii", "PII")
    md = {"markings": ["pii"], "permissions": {"clearance": "internal"}}
    dec = ev.evaluate({"sub": "a", "markings": "pii"}, md, verb="read",
                      domain=DOMAIN)
    assert not dec


# ---------------------------------------------------------------
# realtime 高敏复查
# ---------------------------------------------------------------

def test_realtime_high_revoked_denied(ev, d):
    d.register(DOMAIN, "pii", "PII", sensitivity="high")
    d.grant(DOMAIN, "pii", "agent:a", source="directory", ttl_days=10)
    md = {"markings": ["pii"], "permissions": {"clearance": "internal"}}
    assert ev.evaluate(_claims(markings=["pii"]), md, verb="review",
                       domain=DOMAIN, realtime=True).allowed
    d.revoke(DOMAIN, "pii", "agent:a")
    dec = ev.evaluate(_claims(markings=["pii"]), md, verb="review",
                      domain=DOMAIN, realtime=True)
    assert not dec and dec.reason == "realtime_revoked:pii"


def test_realtime_normal_sensitivity_not_enforced(ev, d):
    d.register(DOMAIN, "pii", "PII", sensitivity="normal")
    # 不授予，只在 claims 里带；normal 敏不实时查 => 仅 claims 判定即可通过
    md = {"markings": ["pii"], "permissions": {"clearance": "internal"}}
    dec = ev.evaluate(_claims(markings=["pii"]), md, verb="review",
                      domain=DOMAIN, realtime=True)
    assert dec.allowed


# ---------------------------------------------------------------
# realtime_assert（commit 层）
# ---------------------------------------------------------------

def test_realtime_assert_high_revoked_denied(ev, d):
    d.register(DOMAIN, "pii", "PII", sensitivity="high")
    d.grant(DOMAIN, "pii", "agent:a", source="directory", ttl_days=10)
    md = {"markings": ["pii"], "permissions": {"clearance": "internal"}}
    assert ev.realtime_assert("agent:a", md, domain=DOMAIN).allowed
    d.revoke(DOMAIN, "pii", "agent:a")
    assert not ev.realtime_assert("agent:a", md, domain=DOMAIN).allowed


def test_realtime_assert_normal_passes_even_without_grant(ev, d):
    d.register(DOMAIN, "team-x", "X", sensitivity="normal")
    md = {"markings": ["team-x"], "permissions": {"clearance": "internal"}}
    # 非 high 敏，commit 层不复查 grant
    assert ev.realtime_assert("agent:a", md, domain=DOMAIN).allowed


def test_realtime_assert_no_marking_passes(ev):
    assert ev.realtime_assert("agent:a", {}, domain=DOMAIN).allowed


# ---------------------------------------------------------------
# confidence_level 读别名（D3 单字段合并）
# ---------------------------------------------------------------

def test_confidence_level_read_alias(ev):
    md = {"permissions": {"confidence_level": "confidential"}}
    ok = ev.evaluate(_claims(clearance="confidential"), md, verb="read",
                     domain=DOMAIN)
    assert ok.allowed
    low = ev.evaluate(_claims(clearance="internal"), md, verb="read",
                      domain=DOMAIN)
    assert not low
