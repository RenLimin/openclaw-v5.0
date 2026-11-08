"""L3 contract-management → L2 运营本体装配脚本（幂等）。

依据 DESIGN-DETAIL-contract-management-v1.0 §7.2：
- 注册 domain=bangcle-contract（不存在则创建）；
- 注册 7 个 deterministic function（handler_ref 指向 L3 core）；
- 注册 3 个 action type（submit/approve/reject_contract）；
- 装配期显式开启 AssemblyGate，结束关闭（结构/数据通道分离）；
- 幂等：已注册同名函数/动作则跳过（不覆盖版本，避免误升级）。

用法：
    python3 scripts/register_ontology_functions.py <db_path>
要求：sys.path 可解析 core 包（L3 组件根目录）与 ai_kb 包（L2）。
"""
import argparse
import os
import sys

# 组件根目录 = 本文件上两级（scripts/ → contract-management/）
COMPONENT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if COMPONENT_ROOT not in sys.path:
    sys.path.insert(0, COMPONENT_ROOT)

# L2 组件根目录 = workspace/L2-infra/components/ai-knowledge-base
_WORKSPACE = os.path.abspath(os.path.join(COMPONENT_ROOT, "..", "..", ".."))
_L2_ROOT = os.path.join(_WORKSPACE, "L2-infra", "components", "ai-knowledge-base")
if os.path.isdir(_L2_ROOT) and _L2_ROOT not in sys.path:
    sys.path.insert(0, _L2_ROOT)

from ai_kb.db import AIKB  # noqa: E402
from ai_kb.ontology import ActionRegistry, AssemblyGate  # noqa: E402

DOMAIN_NAME = "Bangcle Contract"
DOMAIN_CODE = "bangcle-contract"
DOMAIN_DESC = "L4 bangcle-contract 实例（合同审批运营对象）"

# handler_ref：'模块路径:callable'，L2 load_handler 惰性 import
_H = "contract_management.ontology_adapter:{}"

FUNCTIONS = [
    ("validate_submit_state", "rule", _H.format("validate_submit_state"), True),
    ("validate_approve_state", "rule", _H.format("validate_approve_state"), True),
    ("validate_reject_state", "rule", _H.format("validate_reject_state"), True),
    ("validate_sign_state", "rule", _H.format("validate_sign_state"), True),
    ("validate_archive_state", "rule", _H.format("validate_archive_state"), True),
    ("risk_scan", "risk", _H.format("risk_scan"), True),
    ("approval_level", "compute", _H.format("approval_level"), True),
    ("parse_contract_text", "compute", _H.format("parse_contract_text"), True),
    ("audit_contract_text", "compute", _H.format("audit_contract_text"), True),
]

_CONTRACT_STATES = [
    "draft", "review1", "review2", "review3",
    "approved", "signed", "archived", "rejected",
]

SUBMIT_SCHEMA = {
    "type": "object",
    "properties": {
        "contract_no": {"type": "string", "minLength": 1},
        "target_state": {"type": "string", "enum": _CONTRACT_STATES},
        "amount": {"type": "number", "minimum": 0},
    },
    "required": ["contract_no", "target_state"],
}

# P5.2: submit_to_oa 动作的 payload schema（写回 OA 流程所需字段）。
# requestid 为泛微 OA 流程单据 id；action 为 OA 节点动作（提交/批准/退回）；
# comment 为审批意见（可空）。写端点契约（P4.2）未闭合前连接器恒 dry-run。
OA_SCHEMA = {
    "type": "object",
    "properties": {
        "requestid": {"type": "string", "minLength": 1},
        "action": {"type": "string", "default": "提交"},
        "comment": {"type": "string"},
    },
    "required": ["requestid", "action"],
}

ACTION_TYPES = [
    ("submit_contract", SUBMIT_SCHEMA,
     {"fn": "validate_submit_state"}, "auto", None),
    ("approve_contract", SUBMIT_SCHEMA,
     {"fn": "validate_approve_state"}, "human", None),
    ("reject_contract", SUBMIT_SCHEMA,
     {"fn": "validate_reject_state"}, "human", None),
    ("submit_to_oa", OA_SCHEMA,
     None, "human", "oa_writeback"),
]


def register_all(db_path: str) -> dict:
    """执行装配；返回汇总。幂等：已存在项跳过。"""
    db = AIKB(db_path)
    db.init_db()
    db.init_ontology_identity_tables()
    db.init_ontology_kinetic_tables()
    db.init_ontology_proposal_tables()
    db.init_ontology_saga_tables()

    domain_id = db.get_or_create_domain(DOMAIN_NAME, DOMAIN_CODE, DOMAIN_DESC)
    gate = AssemblyGate()
    gate.open()
    reg = ActionRegistry(db, gate=gate)

    summary = {"domain_id": domain_id, "functions": [], "actions": []}

    for name, kind, ref, deterministic in FUNCTIONS:
        if reg.get_function(DOMAIN_CODE, name) is None:
            reg.register_function(
                DOMAIN_CODE, name, kind, ref, deterministic=deterministic,
            )
            summary["functions"].append(f"registered:{name}")
        else:
            summary["functions"].append(f"skipped(dup):{name}")

    for name, schema, precond, approval, target in ACTION_TYPES:
        if reg.get_action(DOMAIN_CODE, name) is None:
            action_type_id = reg.register_action_type(
                DOMAIN_CODE, name, "contract", schema,
                precondition=precond, required_approval=approval,
                writeback_target=target,
            )
            summary["actions"].append(f"registered:{name}")
        else:
            action_type_id = reg.get_action(DOMAIN_CODE, name)["id"]
            summary["actions"].append(f"skipped(dup):{name}")

        # P5.2: submit_to_oa 注册多步写回（连接器由装配方注入，
        # 注册期只记录 connector_key，运行期由 ProposalService.connectors 解析）。
        if name == "submit_to_oa":
            reg.register_writeback_steps(action_type_id, [
                {"seq": 1, "connector_key": "oa_writeback",
                 "payload_schema": OA_SCHEMA},
            ])
            summary["actions"].append(f"writeback_steps:submit_to_oa->oa_writeback")

    # 装配闭合校验：precondition 引用的函数必须存在且 deterministic=1
    bindings = reg.validate_action_bindings(DOMAIN_CODE)
    gate.close()

    db.commit()
    db.close()
    summary["bindings"] = bindings
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="L3 → L2 运营本体装配（幂等）")
    parser.add_argument("db_path", help="AIKB SQLite 数据库路径")
    args = parser.parse_args()
    summary = register_all(args.db_path)
    print(f"domain_id: {summary['domain_id']}")
    for f in summary["functions"]:
        print(f"  fn  {f}")
    for a in summary["actions"]:
        print(f"  act {a}")
    print(f"bindings validated: {len(summary['bindings'])} action types")


if __name__ == "__main__":
    main()
