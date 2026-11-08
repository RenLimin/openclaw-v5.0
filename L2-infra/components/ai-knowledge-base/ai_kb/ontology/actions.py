"""ActionRegistry — P2 动力学层 + 注册中心.

依据 DESIGN-DETAIL-operational-ontology-v1.0 §2.2 / §3.2：
- action_type / function_def 两张注册表（migration v9）
- register_* 仅装配期可调（结构/数据通道分离，见 AssemblyGate）；
  MCP/REST 运行路径下调用 register 抛 RuntimeError
- handler_ref 采用 'module_path:callable' 格式，用 importlib 惰性加载；
  模块/属性不存在时 fail-fast（注册后 validate_function_handler 即拒绝）
- 写路径校验函数必须 deterministic=1（validate_function_handler(..., for_write=True)）

本模块与 identity.py 保持独立，不反向依赖 identity 包内其他模块。
"""
import importlib
import json
import sqlite3
from contextlib import contextmanager
from typing import Any, Dict, List, Optional, Union

from ..db import AIKB

# function_def.kind 合法取值（详设 §2.2）
def _iter_precondition_refs(precondition: Any) -> List[Dict[str, str]]:
    """从 precondition JSON 提取 function 引用（kind, fn）。

    形态（与 guardrails/output_guard.py 约定一致）：
    - {"fn": "a"} / {"function": "a"} → precondition(rule)；
    - {"state_machine": "b"} → state_machine；
    - 列表 [{"fn": "a"}, {"kind": "state_machine", "fn": "b"}]。
    """
    if not precondition:
        return []
    if isinstance(precondition, list):
        refs: List[Dict[str, str]] = []
        for item in precondition:
            if not isinstance(item, dict):
                continue
            fn_name = item.get("fn") or item.get("function")
            if fn_name:
                refs.append({"kind": item.get("kind", "precondition"), "fn": fn_name})
        return refs
    if isinstance(precondition, dict):
        refs = []
        fn_name = precondition.get("fn") or precondition.get("function")
        if fn_name:
            refs.append({"kind": "precondition", "fn": fn_name})
        if precondition.get("state_machine"):
            refs.append({"kind": "state_machine", "fn": precondition["state_machine"]})
        return refs
    return []


_FUNCTION_KINDS = {"rule", "state_machine", "risk", "compute"}
# action_type.required_approval 合法取值
_APPROVAL_LEVELS = {"none", "auto", "human"}
# handler_ref 格式：'module_path:callable'（模块路径支持属性链，如 pkg.mod:obj.method）
_HANDLER_SEP = ":"


class AssemblyGate:
    """装配上下文开关（结构/数据通道分离的最小实现）。

    意图：注册表描述的是"系统结构"，只允许在 CLI / 装配脚本启动阶段写入；
    Agent 运行期（MCP/REST 数据通道）严禁动态注册结构，防止运行数据污染
    结构定义。默认关闭（运行期），装配脚本用 ``AssemblyGate.assembly()``
    或直接 ``open()/close()`` 显式开启。

    刻意保持简单：进程内布尔开关，不做角色系统/持久化，不过度设计。
    """

    def __init__(self, open_by_default: bool = False) -> None:
        self._assembly_open = open_by_default

    def is_open(self) -> bool:
        return self._assembly_open

    def open(self) -> None:
        self._assembly_open = True

    def close(self) -> None:
        self._assembly_open = False

    def require_open(self) -> None:
        """register_* 入口守卫：运行期调用直接 RuntimeError。"""
        if not self._assembly_open:
            raise RuntimeError(
                "register_* is only allowed during assembly; "
                "ActionRegistry is in runtime mode (structure/data channel separation)"
            )

    @contextmanager
    def assembly(self):
        """显式开启一个装配上下文（with 块结束后恢复原状态）。"""
        prev = self._assembly_open
        self._assembly_open = True
        try:
            yield self
        finally:
            self._assembly_open = prev


def parse_handler_ref(handler_ref: str) -> tuple[str, str]:
    """拆分 'module_path:callable'。格式非法时 ValueError（fail-fast）。"""
    if not isinstance(handler_ref, str) or _HANDLER_SEP not in handler_ref:
        raise ValueError(
            f"invalid handler_ref {handler_ref!r}: expected 'module_path:callable'"
        )
    module_path, attr_path = handler_ref.split(_HANDLER_SEP, 1)
    if not module_path or not attr_path:
        raise ValueError(
            f"invalid handler_ref {handler_ref!r}: module and callable must be non-empty"
        )
    return module_path, attr_path


def load_handler(handler_ref: str) -> Any:
    """惰性加载 handler_ref 指向的可调用对象。

    - 模块不存在 / 属性链上任一属性不存在：ImportError / AttributeError
      （fail-fast，由调用方决定何时转成拒绝）
    - 解析到的对象不可调用：TypeError
    不在注册时 import，只在真正需要（validate / 显式校验）时加载，
    避免把 L3/L4 实现模块变成 L2 的导入期依赖。
    """
    module_path, attr_path = parse_handler_ref(handler_ref)
    module = importlib.import_module(module_path)
    obj: Any = module
    for attr in attr_path.split("."):
        obj = getattr(obj, attr)
    if not callable(obj):
        raise TypeError(f"handler_ref {handler_ref!r} resolved to a non-callable object")
    return obj


def _loads_json_field(value: Optional[str], field_name: str) -> Any:
    if value is None:
        return None
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSON stored in {field_name}: {exc}") from exc


class ActionRegistry:
    """动作/函数注册中心，依赖注入 AIKB 实例。

    domain 参数同时接受 domain id（int）或 domain code（str），
    处理风格与 identity.py 一致，但两模块互不依赖。
    """

    def __init__(self, db: AIKB, gate: Optional[AssemblyGate] = None) -> None:
        self.db = db
        # 默认运行期：register_* 全部拒绝。装配脚本须显式开启 gate。
        self.gate = gate if gate is not None else AssemblyGate(open_by_default=False)

    # --- 内部辅助 ---
    def _resolve_domain_id(self, domain: Union[int, str]) -> int:
        if isinstance(domain, int):
            return domain
        cursor = self.db.execute("SELECT id FROM domain WHERE code = ?", (domain,))
        row = cursor.fetchone()
        if row is None:
            raise ValueError(f"domain not found: {domain}")
        return row[0]

    @staticmethod
    def _validate_params_schema(params_schema: Any) -> str:
        """params_schema 接受 dict（序列化存储）或 JSON 字符串；必须含 type=object。"""
        if isinstance(params_schema, dict):
            text = json.dumps(params_schema, ensure_ascii=False)
        elif isinstance(params_schema, str):
            # 提前解析一次，拒绝坏 JSON
            json.loads(params_schema)
            text = params_schema
        else:
            raise ValueError("params_schema must be a dict or JSON string")
        return text

    @staticmethod
    def _validate_optional_json(value: Any, field_name: str) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        if isinstance(value, str):
            json.loads(value)
            return value
        raise ValueError(f"{field_name} must be a dict/list or JSON string")

    # --- 结构通道：仅装配期（§3.2）---
    def register_action_type(
        self,
        domain: Union[int, str],
        name: str,
        object_type: str,
        params_schema: Union[str, Dict[str, Any]],
        precondition: Union[str, Dict[str, Any], None] = None,
        required_approval: str = "none",
        writeback_target: Optional[str] = None,
        version: int = 1,
    ) -> int:
        """注册动作类型 → action_type id。

        装配期调用；UNIQUE(domain_id, name, version) 冲突抛
        sqlite3.IntegrityError。
        """
        self.gate.require_open()
        domain_id = self._resolve_domain_id(domain)
        if required_approval not in _APPROVAL_LEVELS:
            raise ValueError(
                f"required_approval must be one of {sorted(_APPROVAL_LEVELS)}, "
                f"got {required_approval!r}"
            )
        schema_text = self._validate_params_schema(params_schema)
        precondition_text = self._validate_optional_json(precondition, "precondition")

        now = self.db.get_now()
        cursor = self.db.execute("""
        INSERT INTO ont_action_type
            (domain_id, name, object_type, params_schema, precondition,
             required_approval, writeback_target, version, status,
             created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
        """, (domain_id, name, object_type, schema_text, precondition_text,
              required_approval, writeback_target, version, now, now))
        self.db.commit()
        return cursor.lastrowid

    def register_function(
        self,
        domain: Union[int, str],
        name: str,
        kind: str,
        handler_ref: str,
        io_schema: Union[str, Dict[str, Any], None] = None,
        deterministic: bool = True,
        version: int = 1,
    ) -> int:
        """注册函数定义 → function_def id。

        装配期调用；UNIQUE(domain_id, name, version) 冲突抛
        sqlite3.IntegrityError。注册只校验 handler_ref 格式（语法层），
        真正的模块加载由 validate_function_handler 惰性执行。
        """
        self.gate.require_open()
        domain_id = self._resolve_domain_id(domain)
        if kind not in _FUNCTION_KINDS:
            raise ValueError(
                f"kind must be one of {sorted(_FUNCTION_KINDS)}, got {kind!r}"
            )
        # 语法 fail-fast：格式不对不允许落库
        parse_handler_ref(handler_ref)
        io_schema_text = self._validate_optional_json(io_schema, "io_schema")

        now = self.db.get_now()
        cursor = self.db.execute("""
        INSERT INTO ont_function_def
            (domain_id, name, kind, handler_ref, io_schema, deterministic,
             version, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
        """, (domain_id, name, kind, handler_ref, io_schema_text,
              1 if deterministic else 0, version, now, now))
        self.db.commit()
        return cursor.lastrowid

    # --- 多写回步骤（P4）---
    def register_writeback_steps(
        self,
        action_type_id: int,
        steps: List[Dict[str, Any]],
    ) -> None:
        """为动作注册【有序】多写回步骤（P4 Saga）。

        装配期调用；steps 每项 {"seq", "connector_key", "payload_schema?"}。
        seq 从 1 起连续；connector_key 由 ProposalService.connectors 解析，
        注册期不做存在性校验（连接器由装配方注入）。同一动作重复注册
        覆盖旧步骤（先删后插，事务内）。
        """
        self.gate.require_open()
        if not steps:
            raise ValueError("steps must not be empty")
        seqs = [int(st.get("seq")) for st in steps]
        if seqs != list(range(1, len(steps) + 1)):
            raise ValueError(
                f"seq must be contiguous from 1: got {seqs}"
            )
        now = self.db.get_now()
        try:
            self.db.execute(
                "DELETE FROM ont_writeback_step WHERE action_type_id = ?",
                (action_type_id,),
            )
            for st in steps:
                payload = self._validate_optional_json(
                    st.get("payload_schema"), "payload_schema"
                )
                self.db.execute("""
                INSERT INTO ont_writeback_step
                    (action_type_id, seq, connector_key, payload_schema, created_at)
                VALUES (?, ?, ?, ?, ?)
                """, (action_type_id, st["seq"], st["connector_key"],
                      payload, now))
            self.db.commit()
        except Exception:
            self.db.conn.rollback()
            raise

    def list_writeback_steps(self, action_type_id: int) -> List[Dict[str, Any]]:
        """读通道：动作的多写回步骤（按 seq 排序）；无则空表。"""
        rows = self.db.execute(
            "SELECT * FROM ont_writeback_step WHERE action_type_id = ? "
            "ORDER BY seq", (action_type_id,),
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            if d.get("payload_schema"):
                try:
                    d["payload_schema"] = json.loads(d["payload_schema"])
                except json.JSONDecodeError:
                    pass
            out.append(d)
        return out

    # --- 装配期绑定校验（P3 T6：precondition → function）---
    def validate_action_bindings(
        self,
        domain: Union[int, str],
        *,
        name: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """装配期末校验：action_type.precondition 引用的 function 必须存在
        且 deterministic=1；state_machine 引用必须 kind='state_machine'。

        - domain 下全部动作（或指定 name 的全部版本）逐一校验；
        - 未注册 / 非 deterministic / kind 不符 → ValueError（fail-fast，
          装配不闭合）；
        - 返回每个动作的绑定清单 [{action, version, refs[]}]，供装配脚本
          与测试断言。
        """
        domain_id = self._resolve_domain_id(domain)
        if name is not None:
            rows = self.db.execute("""
            SELECT * FROM ont_action_type
            WHERE domain_id = ? AND name = ?
            ORDER BY version
            """, (domain_id, name)).fetchall()
        else:
            rows = self.db.execute("""
            SELECT * FROM ont_action_type
            WHERE domain_id = ? ORDER BY name, version
            """, (domain_id,)).fetchall()

        reports: List[Dict[str, Any]] = []
        for row in rows:
            action = dict(row)
            refs: List[Dict[str, str]] = []
            precondition = _loads_json_field(action.get("precondition"), "precondition")
            for step in _iter_precondition_refs(precondition):
                fn = self.get_function(domain_id, step["fn"])
                label = f"action {action['name']} v{action['version']}"
                if fn is None:
                    raise ValueError(
                        f"{label} references unregistered function "
                        f"{step['fn']!r} ({step['kind']})"
                    )
                if int(fn["deterministic"]) != 1:
                    raise ValueError(
                        f"{label} references non-deterministic function "
                        f"{step['fn']!r}; write-path bindings must be deterministic"
                    )
                if step["kind"] == "state_machine" and fn["kind"] != "state_machine":
                    raise ValueError(
                        f"{label} binds {step['fn']!r} as state_machine but "
                        f"function kind={fn['kind']!r}"
                    )
                refs.append(step)
            reports.append({
                "action": action["name"],
                "version": action["version"],
                "refs": refs,
            })
        return reports

    # --- handler 惰性加载 / 校验（T2.3）---
    def validate_function_handler(
        self,
        domain: Union[int, str],
        name: str,
        *,
        version: Optional[int] = None,
        for_write: bool = False,
    ) -> Any:
        """注册后校验：惰性 import handler_ref 并返回可调用对象。

        - 找不到函数定义：ValueError
        - 模块不存在 / 属性不存在 / 不可调用：抛出底层异常
          （ImportError / AttributeError / TypeError），即"坏 handler 被拒"
        - for_write=True 时，deterministic=0 的函数禁止用于写校验路径
        此方法为读路径操作，任何时期均可调用。
        """
        fn = self.get_function(domain, name, version=version)
        if for_write and int(fn["deterministic"]) != 1:
            raise ValueError(
                f"function {name!r} is non-deterministic and cannot be used "
                f"on a write/validation path"
            )
        return load_handler(fn["handler_ref"])

    # --- 读通道：运行期可用（§3.2）---
    def get_action(
        self,
        domain: Union[int, str],
        name: str,
        *,
        version: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """按 domain+name 读动作类型；默认取最高版本。"""
        domain_id = self._resolve_domain_id(domain)
        if version is None:
            cursor = self.db.execute("""
            SELECT * FROM ont_action_type
            WHERE domain_id = ? AND name = ?
            ORDER BY version DESC, id DESC LIMIT 1
            """, (domain_id, name))
        else:
            cursor = self.db.execute("""
            SELECT * FROM ont_action_type
            WHERE domain_id = ? AND name = ? AND version = ?
            """, (domain_id, name, version))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_function(
        self,
        domain: Union[int, str],
        name: str,
        *,
        version: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """按 domain+name 读函数定义；默认取最高版本。"""
        domain_id = self._resolve_domain_id(domain)
        if version is None:
            cursor = self.db.execute("""
            SELECT * FROM ont_function_def
            WHERE domain_id = ? AND name = ?
            ORDER BY version DESC, id DESC LIMIT 1
            """, (domain_id, name))
        else:
            cursor = self.db.execute("""
            SELECT * FROM ont_function_def
            WHERE domain_id = ? AND name = ? AND version = ?
            """, (domain_id, name, version))
        row = cursor.fetchone()
        return dict(row) if row else None

    def list_actions(self, domain: Union[int, str]) -> List[Dict[str, Any]]:
        """MCP 工具发现用：列出 domain 下全部动作类型（含函数清单）。

        同名多版本时每个版本各占一行，按 name、version 排序。
        JSON 字段（params_schema/precondition）反序列化后返回，
        解析失败时保留原字符串并在 *_raw 之外不额外造字段。
        """
        domain_id = self._resolve_domain_id(domain)
        cursor = self.db.execute("""
        SELECT * FROM ont_action_type
        WHERE domain_id = ?
        ORDER BY name, version
        """, (domain_id,))
        actions: List[Dict[str, Any]] = []
        for row in cursor.fetchall():
            item = dict(row)
            item["params_schema"] = _loads_json_field(item["params_schema"], "params_schema")
            item["precondition"] = _loads_json_field(item.get("precondition"), "precondition")
            actions.append(item)
        return actions

    def list_functions(self, domain: Union[int, str]) -> List[Dict[str, Any]]:
        """MCP 工具发现用：列出 domain 下全部 status=active 的函数定义。

        与 list_actions 对称：按 domain_id 过滤、仅返回 active；
        io_schema 反序列化后返回。按 name、version 排序。
        """
        domain_id = self._resolve_domain_id(domain)
        cursor = self.db.execute("""
        SELECT * FROM ont_function_def
        WHERE domain_id = ? AND status = 'active'
        ORDER BY name, version
        """, (domain_id,))
        functions: List[Dict[str, Any]] = []
        for row in cursor.fetchall():
            item = dict(row)
            item["io_schema"] = _loads_json_field(item["io_schema"], "io_schema")
            functions.append(item)
        return functions
