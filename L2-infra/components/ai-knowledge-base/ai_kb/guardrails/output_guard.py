"""OutputGuard — P3 动作输出侧接地（详设 §3.6）.

与 guardrails/output.py 的分工：
- output.py 管**回答文本**（反幻觉/脱敏）；
- output_guard.py 管**动作输出**（写治理）：validate_proposal 依次执行
  ABAC 权限 → 参数 JSON Schema → 前置条件（deterministic function）
  → 状态机约束（绑定 state_machine 类 function）。

Function handler 契约（由 L3/L4 装配期注入，详见 ontology/actions.py）：
- 可调用签名：handler(snapshot: dict, params: dict) -> result
- result 可为：
    bool
    {"ok": bool, "violations": [str|{"rule": ..., "message": ...}]}
    ["violation", ...]
  抛异常视为命中违规（fail-closed，违规内容取异常消息）。
handler 以调用者权限语义执行，只允许返回校验结果，禁止直接写库。
"""
import json
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

from ..permissions import PermissionChecker

if TYPE_CHECKING:  # 避免与 ai_kb.ontology 包 __init__ 形成循环导入
    from ..ontology.actions import ActionRegistry

# handler 惰性加载放在方法内（见 _run_function），模块加载期不导入 ontology 包

# 违规条目统一形态
Violation = Dict[str, Any]


class _MiniJSONSchema:
    """最小 JSON Schema 校验器（不引第三方依赖）。

    覆盖本期 params_schema 用到的关键字：type / required / properties /
    items / enum / minimum / maximum / minLength / maxLength /
    additionalProperties。够用即止，不追求完整草案。
    """

    _TYPE_MAP = {
        "object": dict,
        "array": list,
        "string": str,
        "integer": int,
        "number": (int, float),
        "boolean": bool,
        "null": type(None),
    }

    def validate(self, instance: Any, schema: Dict[str, Any], path: str = "$") -> List[str]:
        errors: List[str] = []
        if not isinstance(schema, dict):
            return errors

        expected = schema.get("type")
        if expected is not None:
            types = expected if isinstance(expected, list) else [expected]
            if not any(self._match_type(instance, t) for t in types):
                errors.append(f"{path}: expected type {expected}, got {type(instance).__name__}")
                # 类型不符，后续结构校验无意义
                return errors

        if "enum" in schema and instance not in schema["enum"]:
            errors.append(f"{path}: value {instance!r} not in enum {schema['enum']}")

        if isinstance(instance, str):
            if "minLength" in schema and len(instance) < schema["minLength"]:
                errors.append(f"{path}: length {len(instance)} < minLength {schema['minLength']}")
            if "maxLength" in schema and len(instance) > schema["maxLength"]:
                errors.append(f"{path}: length {len(instance)} > maxLength {schema['maxLength']}")

        if isinstance(instance, (int, float)) and not isinstance(instance, bool):
            if "minimum" in schema and instance < schema["minimum"]:
                errors.append(f"{path}: {instance} < minimum {schema['minimum']}")
            if "maximum" in schema and instance > schema["maximum"]:
                errors.append(f"{path}: {instance} > maximum {schema['maximum']}")

        if isinstance(instance, dict):
            required = schema.get("required", [])
            for key in required:
                if key not in instance:
                    errors.append(f"{path}: missing required property {key!r}")
            properties = schema.get("properties", {})
            for key, value in instance.items():
                if key in properties:
                    errors.extend(self.validate(value, properties[key], f"{path}.{key}"))
                elif schema.get("additionalProperties") is False:
                    errors.append(f"{path}: additional property {key!r} not allowed")

        if isinstance(instance, list) and "items" in schema:
            item_schema = schema["items"]
            for idx, item in enumerate(instance):
                errors.extend(self.validate(item, item_schema, f"{path}[{idx}]"))

        return errors

    @staticmethod
    def _match_type(instance: Any, type_name: str) -> bool:
        py_type = _MiniJSONSchema._TYPE_MAP.get(type_name)
        if py_type is None:
            return True
        # bool 是 int 子类：integer/number 不应接受 True/False
        if type_name in ("integer", "number") and isinstance(instance, bool):
            return False
        return isinstance(instance, py_type)


def normalize_violation(raw: Any, stage: str) -> Violation:
    """把 handler 返回的各种违规形态统一成 {stage, rule, message}。"""
    if isinstance(raw, dict):
        return {
            "stage": stage,
            "rule": raw.get("rule", stage),
            "message": raw.get("message", str(raw)),
        }
    return {"stage": stage, "rule": stage, "message": str(raw)}


def _iter_precondition_steps(precondition: Any) -> List[Dict[str, str]]:
    """解析 action_type.precondition JSON 为有序步骤。

    支持形态：
    - None / {} → 无前置步骤；
    - {"fn": "f"} → 单个 rule 类前置；
    - {"state_machine": "f"} → 单个状态机约束；
    - {"fn": "a", "state_machine": "b"} → 两步；
    - [{"fn": "a"}, {"kind": "state_machine", "fn": "b"}, ...]。
    """
    if precondition is None:
        return []
    if isinstance(precondition, list):
        steps: List[Dict[str, str]] = []
        for item in precondition:
            if not isinstance(item, dict):
                continue
            kind = item.get("kind", "precondition")
            fn_name = item.get("fn") or item.get("function")
            if fn_name:
                steps.append({"kind": kind, "fn": fn_name})
        return steps
    if isinstance(precondition, dict):
        steps = []
        if precondition.get("fn") or precondition.get("function"):
            steps.append({"kind": "precondition",
                          "fn": precondition.get("fn") or precondition.get("function")})
        if precondition.get("state_machine"):
            steps.append({"kind": "state_machine", "fn": precondition["state_machine"]})
        return steps
    return []


class OutputGuard:
    """动作输出校验链，依赖注入注册中心 / 权限检查器。"""

    def __init__(
        self,
        registry: "ActionRegistry",
        permission_checker: Optional[PermissionChecker] = None,
    ) -> None:
        self.registry = registry
        self.db = registry.db
        self.perms = permission_checker or PermissionChecker(self.db)
        self._schema_validator = _MiniJSONSchema()

    def validate_proposal(
        self,
        proposal: Dict[str, Any],
        caller_attrs: Dict[str, Any],
        *,
        fail_fast: bool = False,
    ) -> Dict[str, Any]:
        """校验提案，返回 {ok, violations[]}。

        顺序固定：ABAC → 参数 Schema → 前置条件 → 状态机。
        fail_fast=True 时命中首个阶段即返回；默认收集全部违规，
        便于一次性反馈学习。
        """
        violations: List[Violation] = []

        action = self._load_action_for_proposal(proposal)

        # 1) ABAC 权限
        violations.extend(self._check_abac(proposal, caller_attrs))
        if violations and fail_fast:
            return {"ok": False, "violations": violations}

        # 2) 参数 JSON Schema
        violations.extend(self._check_params_schema(proposal, action))
        if violations and fail_fast:
            return {"ok": False, "violations": violations}

        # 3)+4) 前置条件 / 状态机
        pre_steps = _iter_precondition_steps(action.get("precondition"))
        for step in pre_steps:
            stage = "state_machine" if step["kind"] == "state_machine" else "precondition"
            violations.extend(
                self._run_function(proposal, action, step["fn"], stage)
            )
            if violations and fail_fast:
                break

        return {"ok": len(violations) == 0, "violations": violations}

    # --- 各阶段 ---
    def _load_action_for_proposal(self, proposal: Dict[str, Any]) -> Dict[str, Any]:
        action_type_id = proposal.get("action_type_id")
        if action_type_id is None:
            raise ValueError("proposal missing action_type_id")
        row = self.db.execute(
            "SELECT * FROM ont_action_type WHERE id = ?", (action_type_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"action_type not found: {action_type_id}")
        action = dict(row)
        action["params_schema"] = _safe_json(action["params_schema"])
        action["precondition"] = _safe_json(action.get("precondition"))
        return action

    def _check_abac(
        self, proposal: Dict[str, Any], caller_attrs: Dict[str, Any]
    ) -> List[Violation]:
        snapshot = _ensure_obj(proposal.get("target_snapshot"), "target_snapshot")
        identities = snapshot.get("identities", [])
        denied: List[Violation] = []
        for ident in identities:
            metadata = ident.get("metadata")
            if isinstance(metadata, str):
                metadata = _safe_json(metadata)
            perms = None
            if isinstance(metadata, dict):
                perms = metadata.get("permissions")
            if isinstance(perms, (dict, list)):
                perms = json.dumps(perms, ensure_ascii=False)
            if not self.perms.can_access_doc(caller_attrs, perms):
                denied.append({
                    "stage": "abac",
                    "rule": "abac.denied",
                    "message": (
                        f"caller denied access to object "
                        f"{ident.get('object_type')}:{ident.get('canonical_key')}"
                    ),
                })
        return denied

    def _check_params_schema(
        self, proposal: Dict[str, Any], action: Dict[str, Any]
    ) -> List[Violation]:
        params = _ensure_obj(proposal.get("params"), "params")
        schema = action.get("params_schema") or {}
        errors = self._schema_validator.validate(params, schema)
        return [normalize_violation(e, "params_schema") for e in errors]

    def _run_function(
        self,
        proposal: Dict[str, Any],
        action: Dict[str, Any],
        function_name: str,
        stage: str,
    ) -> List[Violation]:
        # 读 function 定义：默认最高版本；写校验路径必须 deterministic=1
        fn_def = self.registry.get_function(action["domain_id"], function_name)
        if fn_def is None:
            return [normalize_violation(
                f"bound function {function_name!r} not found in registry", stage
            )]
        if int(fn_def["deterministic"]) != 1:
            return [normalize_violation(
                f"function {function_name!r} is non-deterministic and cannot be "
                f"used on a write/validation path", stage
            )]
        if stage == "state_machine" and fn_def["kind"] != "state_machine":
            return [normalize_violation(
                f"function {function_name!r} bound as state_machine but kind="
                f"{fn_def['kind']!r}", stage
            )]
        if stage == "precondition" and fn_def["kind"] not in ("rule", "state_machine"):
            return [normalize_violation(
                f"function {function_name!r} used as precondition but kind="
                f"{fn_def['kind']!r}", stage
            )]

        try:
            from ..ontology.actions import load_handler

            handler = load_handler(fn_def["handler_ref"])
            snapshot = _ensure_obj(proposal.get("target_snapshot"), "target_snapshot")
            params = _ensure_obj(proposal.get("params"), "params")
            raw_result = handler(snapshot, params)
        except Exception as exc:  # handler 抛错 = fail-closed 违规
            return [normalize_violation(
                f"{function_name} raised: {exc}", stage
            )]

        return self._normalize_handler_result(raw_result, stage, function_name)

    @staticmethod
    def _normalize_handler_result(
        raw_result: Any, stage: str, function_name: str
    ) -> List[Violation]:
        if raw_result is None:
            return []
        if isinstance(raw_result, bool):
            return [] if raw_result else [normalize_violation(
                f"{function_name} returned False", stage
            )]
        if isinstance(raw_result, list):
            return [normalize_violation(v, stage) for v in raw_result]
        if isinstance(raw_result, dict):
            ok = raw_result.get("ok", True)
            raw_violations = raw_result.get("violations", [])
            if ok and not raw_violations:
                return []
            return [normalize_violation(v, stage) for v in raw_violations] or [
                normalize_violation(f"{function_name} reported ok=false", stage)
            ]
        return [normalize_violation(str(raw_result), stage)]


def _safe_json(value: Optional[str]) -> Any:
    if value is None:
        return None
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return value


def _ensure_obj(value: Any, field_name: str) -> Dict[str, Any]:
    obj = _safe_json(value)
    if obj is None:
        return {}
    if not isinstance(obj, dict):
        raise ValueError(f"{field_name} must be a JSON object")
    return obj
