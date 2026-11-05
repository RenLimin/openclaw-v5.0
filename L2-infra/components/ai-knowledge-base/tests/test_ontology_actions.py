"""Unit tests for P2 ActionRegistry (operational ontology §2.2 / §3.2).

Runs against a real temporary SQLite database (no mocks for the DB layer).
"""
import os
import sqlite3
import sys
import tempfile
import textwrap

import pytest

from ai_kb.db import AIKB
from ai_kb.ontology import ActionRegistry, AssemblyGate


@pytest.fixture()
def kb():
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    db = AIKB(db_path)
    db.init_db()
    db.init_ontology_identity_tables()
    db.init_ontology_kinetic_tables()
    db.get_or_create_domain("Test Domain", "test-domain", "Test")
    yield db
    db.close()
    os.unlink(db_path)


@pytest.fixture()
def gate():
    gate = AssemblyGate()
    gate.open()
    return gate


@pytest.fixture()
def registry(kb, gate):
    return ActionRegistry(kb, gate=gate)


PARAMS_SCHEMA = {
    "type": "object",
    "properties": {"contract_no": {"type": "string"}},
    "required": ["contract_no"],
}


# --- migration / DDL ---

def test_migration_v9_registered(kb):
    assert kb.get_current_migration_version() == 9
    cursor = kb.execute("SELECT name FROM kb_migration WHERE version = 9")
    assert cursor.fetchone()[0] == "operational_ontology_kinetic"


def test_kinetic_tables_idempotent(kb):
    kb.init_ontology_kinetic_tables()
    assert kb.get_current_migration_version() == 9


# --- register action_type ---

def test_register_action_type(registry):
    action_id = registry.register_action_type(
        "test-domain", "submit_contract", "contract",
        PARAMS_SCHEMA, precondition={"fn": "validate_submit_state"},
        required_approval="human", writeback_target="oa-connector",
    )
    assert action_id > 0
    action = registry.get_action("test-domain", "submit_contract")
    assert action["name"] == "submit_contract"
    assert action["object_type"] == "contract"
    assert action["required_approval"] == "human"
    assert action["writeback_target"] == "oa-connector"
    assert action["version"] == 1
    assert action["status"] == "active"
    assert action["domain_id"] > 0


def test_register_action_type_by_domain_id(registry):
    action_id = registry.register_action_type(
        1, "query_contract", "contract", PARAMS_SCHEMA,
    )
    assert action_id > 0
    assert registry.get_action(1, "query_contract")["name"] == "query_contract"


def test_register_action_type_bad_approval_rejected(registry):
    with pytest.raises(ValueError):
        registry.register_action_type(
            "test-domain", "submit_contract", "contract",
            PARAMS_SCHEMA, required_approval="bogus",
        )


def test_register_action_type_bad_schema_json_rejected(registry):
    with pytest.raises(ValueError):
        registry.register_action_type(
            "test-domain", "submit_contract", "contract", "{not-json",
        )


def test_duplicate_action_name_version_conflict(registry):
    registry.register_action_type(
        "test-domain", "submit_contract", "contract", PARAMS_SCHEMA,
    )
    with pytest.raises(sqlite3.IntegrityError):
        registry.register_action_type(
            "test-domain", "submit_contract", "contract", PARAMS_SCHEMA,
        )


def test_same_action_name_different_version_ok(registry):
    v1 = registry.register_action_type(
        "test-domain", "submit_contract", "contract", PARAMS_SCHEMA, version=1,
    )
    v2 = registry.register_action_type(
        "test-domain", "submit_contract", "contract", PARAMS_SCHEMA, version=2,
    )
    assert v1 != v2
    # 默认取最高版本
    assert registry.get_action("test-domain", "submit_contract")["version"] == 2
    assert registry.get_action("test-domain", "submit_contract", version=1)["version"] == 1


# --- register function ---

def test_register_function(registry):
    fn_id = registry.register_function(
        "test-domain", "validate_submit_state", "state_machine",
        "ai_kb.ontology.actions:load_handler",
        io_schema={"in": {}, "out": {"type": "object"}},
        deterministic=True,
    )
    assert fn_id > 0
    fn = registry.get_function("test-domain", "validate_submit_state")
    assert fn["kind"] == "state_machine"
    assert fn["deterministic"] == 1
    assert fn["version"] == 1
    assert fn["status"] == "active"


def test_register_function_bad_kind_rejected(registry):
    with pytest.raises(ValueError):
        registry.register_function(
            "test-domain", "bad", "nonsense",
            "ai_kb.ontology.actions:load_handler",
        )


def test_duplicate_function_name_version_conflict(registry):
    registry.register_function(
        "test-domain", "validate_submit_state", "rule",
        "ai_kb.ontology.actions:load_handler",
    )
    with pytest.raises(sqlite3.IntegrityError):
        registry.register_function(
            "test-domain", "validate_submit_state", "rule",
            "ai_kb.ontology.actions:load_handler",
        )


# --- get / list ---

def test_get_action_miss_returns_none(registry):
    assert registry.get_action("test-domain", "nope") is None


def test_get_function_miss_returns_none(registry):
    assert registry.get_function("test-domain", "nope") is None


def test_list_actions(registry):
    registry.register_action_type("test-domain", "a_action", "contract", PARAMS_SCHEMA)
    registry.register_action_type(
        "test-domain", "b_action", "contract", PARAMS_SCHEMA,
        precondition={"rule": "x"}, required_approval="auto",
    )
    actions = registry.list_actions("test-domain")
    assert [a["name"] for a in actions] == ["a_action", "b_action"]
    # JSON 字段已反序列化
    assert actions[0]["params_schema"]["type"] == "object"
    assert actions[1]["precondition"] == {"rule": "x"}


# --- handler 惰性加载 ---

def test_validate_function_handler_lazy_load_success(registry, tmp_path):
    # 在临时目录放一个真实模块，注册后才需要能 import
    pkg_dir = tmp_path / "fakehandlers"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text("")
    (pkg_dir / "validators.py").write_text(textwrap.dedent("""
        def validate_submit(ctx):
            return {"ok": True}
    """))
    sys.path.insert(0, str(tmp_path))
    try:
        fn_id = registry.register_function(
            "test-domain", "validate_submit", "rule",
            "fakehandlers.validators:validate_submit",
        )
        assert fn_id > 0
        handler = registry.validate_function_handler(
            "test-domain", "validate_submit", for_write=True
        )
        assert callable(handler)
        assert handler(None) == {"ok": True}
    finally:
        sys.path.remove(str(tmp_path))
        for mod in list(sys.modules):
            if mod == "fakehandlers" or mod.startswith("fakehandlers."):
                del sys.modules[mod]


def test_bad_handler_missing_module_rejected(registry):
    registry.register_function(
        "test-domain", "broken_module_fn", "rule",
        "no_such_module_xyz_42:some_callable",
    )
    with pytest.raises(ImportError):
        registry.validate_function_handler("test-domain", "broken_module_fn")


def test_bad_handler_missing_attr_rejected(registry):
    registry.register_function(
        "test-domain", "broken_attr_fn", "rule",
        "ai_kb.ontology.actions:no_such_callable_xyz",
    )
    with pytest.raises(AttributeError):
        registry.validate_function_handler("test-domain", "broken_attr_fn")


def test_bad_handler_ref_format_rejected_at_register(registry):
    with pytest.raises(ValueError):
        registry.register_function(
            "test-domain", "bad_format_fn", "rule", "not-a-handler-ref",
        )


def test_non_callable_handler_rejected(registry, tmp_path):
    pkg_dir = tmp_path / "fakehandlers2"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text("")
    (pkg_dir / "mod.py").write_text("JUST_A_VALUE = 42\n")
    sys.path.insert(0, str(tmp_path))
    try:
        registry.register_function(
            "test-domain", "non_callable_fn", "compute",
            "fakehandlers2.mod:JUST_A_VALUE",
        )
        with pytest.raises(TypeError):
            registry.validate_function_handler("test-domain", "non_callable_fn")
    finally:
        sys.path.remove(str(tmp_path))
        for mod in list(sys.modules):
            if mod == "fakehandlers2" or mod.startswith("fakehandlers2."):
                del sys.modules[mod]


# --- deterministic gate for write paths ---

def test_non_deterministic_function_blocked_for_write(registry):
    registry.register_function(
        "test-domain", "risky_guess", "risk",
        "ai_kb.ontology.actions:load_handler",
        deterministic=False,
    )
    with pytest.raises(ValueError, match="non-deterministic"):
        registry.validate_function_handler(
            "test-domain", "risky_guess", for_write=True
        )


def test_non_deterministic_function_allowed_for_read(registry):
    # 非写路径仍可惰性加载
    registry.register_function(
        "test-domain", "risky_guess", "risk",
        "ai_kb.ontology.actions:load_handler",
        deterministic=False,
    )
    handler = registry.validate_function_handler(
        "test-domain", "risky_guess", for_write=False
    )
    assert callable(handler)


# --- AssemblyGate: 结构/数据通道分离 ---

def test_assembly_gate_runtime_rejects_register(kb):
    runtime_registry = ActionRegistry(kb)  # 默认 gate 关闭
    assert runtime_registry.gate.is_open() is False
    with pytest.raises(RuntimeError):
        runtime_registry.register_action_type(
            "test-domain", "sneaky", "contract", PARAMS_SCHEMA,
        )
    with pytest.raises(RuntimeError):
        runtime_registry.register_function(
            "test-domain", "sneaky_fn", "rule",
            "ai_kb.ontology.actions:load_handler",
        )
    # 读路径在运行期仍然可用
    assert runtime_registry.list_actions("test-domain") == []
    assert runtime_registry.get_action("test-domain", "sneaky") is None


def test_assembly_gate_context_manager(kb):
    registry = ActionRegistry(kb)
    with registry.gate.assembly():
        assert registry.gate.is_open()
        action_id = registry.register_action_type(
            "test-domain", "assembled", "contract", PARAMS_SCHEMA,
        )
        assert action_id > 0
    # 退出装配上下文后恢复运行期
    assert registry.gate.is_open() is False
    with pytest.raises(RuntimeError):
        registry.register_action_type(
            "test-domain", "assembled2", "contract", PARAMS_SCHEMA,
        )


def test_explicit_gate_open_close(kb):
    registry = ActionRegistry(kb)
    registry.gate.open()
    fn_id = registry.register_function(
        "test-domain", "f", "rule", "ai_kb.ontology.actions:load_handler"
    )
    assert fn_id > 0
    registry.gate.close()
    with pytest.raises(RuntimeError):
        registry.register_function(
            "test-domain", "f2", "rule", "ai_kb.ontology.actions:load_handler"
        )
