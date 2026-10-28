"""P1：SQLite 建表、写读、append-only 审计。"""

import sqlite3

import pytest

from repository.db import Repository, init_db, default_db_path


def test_init_db_creates_three_tables(tmp_path):
    db_path = str(tmp_path / "r.db")
    init_db(db_path)

    conn = sqlite3.connect(db_path)
    names = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    conn.close()
    assert {"reviews", "kb_matches", "audit_logs"} <= names


def test_init_db_idempotent(tmp_path):
    db_path = str(tmp_path / "r.db")
    init_db(db_path)
    # 再次初始化不报错
    init_db(db_path)


def test_default_db_path_under_data_dir():
    assert default_db_path().replace("\\", "/").endswith(
        "bangcle-contract/data/bangcle_contract.db"
    )


def test_add_review_and_get_review(tmp_path):
    repo = Repository(str(tmp_path / "r.db"))
    rid = repo.add_review(
        contract_ref="HT-001",
        source="upload",
        overall_risk="medium",
        satisfaction="partial",
        report_path="out/HT-001.md",
        rule_set_version="L3-v1.0",
    )
    assert isinstance(rid, int) and rid > 0

    record = repo.get_review(rid)
    assert record["contract_ref"] == "HT-001"
    assert record["source"] == "upload"
    assert record["overall_risk"] == "medium"
    assert record["satisfaction"] == "partial"
    assert record["report_path"] == "out/HT-001.md"
    assert record["rule_set_version"] == "L3-v1.0"
    assert record["created_at"]
    repo.close()


def test_get_review_missing_returns_none(tmp_path):
    repo = Repository(str(tmp_path / "r.db"))
    assert repo.get_review(99999) is None
    repo.close()


def test_add_kb_match_and_audit(tmp_path):
    repo = Repository(str(tmp_path / "r.db"))
    rid = repo.add_review("HT-002", "upload", "low", "satisfied")

    kid = repo.add_kb_match(
        review_id=rid,
        input_name="安全测评服务",
        matched_product="移动安全测评",
        matched_sku="SKU-1",
        score=0.92,
        alert=None,
    )
    assert kid > 0

    aid = repo.append_audit_log(
        review_id=rid, action="review_created", operator="tester",
        detail="创建审查",
    )
    assert aid > 0

    record = repo.get_review(rid)
    assert len(record["kb_matches"]) == 1
    assert record["kb_matches"][0]["matched_product"] == "移动安全测评"
    assert record["kb_matches"][0]["score"] == pytest.approx(0.92)
    assert len(record["audit_logs"]) == 1
    assert record["audit_logs"][0]["action"] == "review_created"
    repo.close()


def test_audit_logs_append_only(tmp_path):
    """审计表只允许 INSERT：Repository 无任何 update/delete 审计方法，
    且直接对 audit_logs 做 UPDATE/DELETE 不被仓储层支持。"""
    repo = Repository(str(tmp_path / "r.db"))

    # 仓储不暴露改/删审计的方法
    for forbidden in ("update_audit_log", "delete_audit_log",
                      "update_audit", "delete_audit"):
        assert not hasattr(repo, forbidden), f"禁止存在 {forbidden}"

    rid = repo.add_review("HT-003", "upload", "low", "satisfied")
    repo.append_audit_log(review_id=rid, action="a1", operator="u")
    repo.append_audit_log(review_id=rid, action="a2", operator="u")

    # 两条审计均保留、按 id 有序
    rows = repo.get_review(rid)["audit_logs"]
    assert [r["action"] for r in rows] == ["a1", "a2"]

    # 源码层面：对 audit_logs 的写操作只允许 INSERT
    import inspect
    source = inspect.getsource(__import__("repository.db", fromlist=["db"]))
    upper = source.upper()
    assert "INSERT INTO AUDIT_LOGS" in upper
    assert "UPDATE AUDIT_LOGS" not in upper
    assert "DELETE FROM AUDIT_LOGS" not in upper
    repo.close()


def test_foreign_key_enforced(tmp_path):
    """kb_matches 外键引用完整性开启（非法 review_id 应失败）。"""
    repo = Repository(str(tmp_path / "r.db"))
    with pytest.raises(sqlite3.IntegrityError):
        repo.add_kb_match(review_id=123456, input_name="幽灵标的")
    repo.close()
