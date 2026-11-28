"""_MiniJSONSchema 组合关键字回归（P4 遗留 TODO 收口）。

覆盖 VERIFICATION-P4 §4.3 声明的待扩展项：$ref（本地 definitions/$defs 指针）、
oneOf / anyOf / allOf / not，以及布尔 schema 与深度上限防环。

定位：单元级，直接驱动校验器，不建 DB/ProposalService。
"""
import pytest

from ai_kb.guardrails.output_guard import _MiniJSONSchema


@pytest.fixture()
def v():
    return _MiniJSONSchema()


# --- $ref ---

def test_ref_definitions_pass(v):
    schema = {
        "type": "object",
        "properties": {"kind": {"$ref": "#/definitions/kind"}},
        "required": ["kind"],
        "definitions": {"kind": {"type": "string", "enum": ["a", "b"]}},
    }
    assert v.validate({"kind": "a"}, schema) == []


def test_ref_definitions_violation(v):
    schema = {
        "type": "object",
        "properties": {"kind": {"$ref": "#/definitions/kind"}},
        "definitions": {"kind": {"type": "string", "enum": ["a", "b"]}},
    }
    errs = v.validate({"kind": "z"}, schema)
    assert len(errs) == 1 and "enum" in errs[0] and "$.kind" in errs[0]


def test_ref_dollar_defs_and_nested_pointer(v):
    schema = {
        "$defs": {
            "amount": {"type": "number", "minimum": 0},
            "inner": {"$ref": "#/$defs/amount"},
        },
        "type": "object",
        "properties": {"n": {"$ref": "#/$defs/inner"}},
    }
    assert v.validate({"n": 5}, schema) == []
    assert v.validate({"n": -1}, schema)


def test_ref_unresolvable_is_error(v):
    schema = {"type": "object", "properties": {"x": {"$ref": "#/definitions/nope"}}}
    errs = v.validate({"x": 1}, schema)
    assert len(errs) == 1 and "cannot resolve" in errs[0]


def test_ref_external_url_rejected(v):
    """跨文件/URL 引用不支持 → fail-closed，不得静默放行。"""
    schema = {"$ref": "https://example.com/schema.json#/foo"}
    errs = v.validate({"x": 1}, schema)
    assert len(errs) == 1 and "cannot resolve" in errs[0]


def test_ref_cycle_depth_guard(v):
    """自引用 $ref 不得无限递归。"""
    schema = {"$ref": "#"}
    errs = v.validate(1, schema)
    assert errs and "nesting exceeds" in errs[0]


# --- oneOf / anyOf / allOf / not ---

def test_oneof_exactly_one_match(v):
    schema = {"oneOf": [{"type": "string"}, {"type": "integer"}]}
    assert v.validate("s", schema) == []
    assert v.validate(7, schema) == []


def test_oneof_zero_or_multi_match_is_error(v):
    schema = {"oneOf": [{"type": "string"}, {"minLength": 0}]}
    assert "oneOf matched 2" in " ".join(v.validate("s", schema))

    schema2 = {"oneOf": [{"type": "string"}, {"type": "integer"}]}
    assert "oneOf matched 0" in " ".join(v.validate(True, schema2))


def test_anyof_at_least_one(v):
    schema = {"anyOf": [{"type": "string"}, {"type": "integer"}]}
    assert v.validate("s", schema) == []
    assert v.validate(3, schema) == []
    assert "matches none of anyOf" in " ".join(v.validate([], schema))


def test_allof_accumulates_all_errors(v):
    schema = {
        "allOf": [
            {"type": "object", "required": ["a"]},
            {"type": "object", "required": ["b"], "additionalProperties": False},
        ]
    }
    msgs = " ".join(v.validate({"c": 1}, schema))
    assert "missing required property 'a'" in msgs
    assert "missing required property 'b'" in msgs
    assert "additional property 'c'" in msgs


def test_not_must_not_match(v):
    schema = {"not": {"type": "string"}}
    assert v.validate(1, schema) == []
    assert "must not match" in " ".join(v.validate("s", schema))


# --- 布尔 schema ---

def test_boolean_schema(v):
    assert v.validate("anything", True) == []
    errs = v.validate("anything", False)
    assert len(errs) == 1 and "always invalid" in errs[0]
