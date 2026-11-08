"""P4.4 定时对账（详设 §5）：OA 当前态 ↔ 本地决策记录。

只读对账：
- 通过依赖注入的 ApprovalLogReader 读 OA 审批链，不产生任何写；
- 只输出 ReconcileDiff 四态，由上层（cron/automations）报告 + 落审计；
- reader 抛 ApprovalLogUnavailable → oa_unknown（不自动重建、不伪造）。

四态：
- in_sync     本地预期态与 OA 当前态一致；
- oa_ahead    OA 已推进而本地未记录；
- local_ahead 本地记录已推进而 OA 未到该态；
- oa_unknown  OA 侧不可得（会话失效/端点变更/被拦截）。

对账永不自动触发写回——写永远走提案 + 授权。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from services.oa.approval_log import (
    ApprovalChain,
    ApprovalLogReader,
    ApprovalLogUnavailable,
)

# 四态常量
IN_SYNC = "in_sync"
OA_AHEAD = "oa_ahead"
LOCAL_AHEAD = "local_ahead"
OA_UNKNOWN = "oa_unknown"

# 状态推进序号：越大越靠后。本地 L3 态与 OA 推导态共用一把尺子。
STATE_ORDER = {
    "draft": 0,
    "review": 1,        # OA/在审（review1/review2… 统一视为在审）
    "review1": 1,
    "review2": 2,
    "approved": 3,
    "signed": 4,
    "archived": 5,
}

# 决策动作 → 本地预期态（P5.3：权威源统一到 DecisionService.replay）
ACTION_TO_STATE = {
    "approve_contract": "approved",
    "reject_contract": "draft",
    "submit_contract": "review",
    "submit_to_oa": "review",
}


def local_state_from_decisions(
    decisions: List[Dict[str, Any]],
    *,
    default: str = "",
) -> str:
    """从决策链取最近一条 committed 决策记录 → 本地预期态（P5.3）。

    decisions 为 DecisionService.replay 返回的决策链（按 id 升序）；
    取最后一条 result='allowed'（committed）记录的 action_type 映射：
    - approve_contract → 'approved'
    - reject_contract → 'draft'
    - submit_contract → 'review'
    - submit_to_oa → 'review'
    无 committed 记录（或全为 rejected/compensated）→ default。

    只读：不写任何状态，纯函数。
    """
    committed = [
        d for d in (decisions or [])
        if d.get("result") == "allowed"
    ]
    if not committed:
        return default
    latest = committed[-1]
    action_type = latest.get("action_type") or ""
    return ACTION_TO_STATE.get(action_type, default)


@dataclass
class ReconcileDiff:
    requestid: str
    local_state: str   # 本地决策记录的预期态
    oa_state: str      # ApprovalChain 反映的 OA 当前态
    kind: str          # in_sync | oa_ahead | local_ahead | oa_unknown


def derive_oa_state(chain: ApprovalChain) -> str:
    """从 ApprovalChain 的当前节点 / tx_status 推导 OA 状态。

    规则（保守、只依赖归一化模型，不臆造 OA 字典之外的语义）：
    - 最近一条真正流转记录 action == 退回 → draft（退回申请人）；
    - action == 批准 且 tx_status 表示流程办结（OA 实测 "0"=办结）→ approved；
    - 其余（提交/批准在途/批注）→ review（流程在审）。
    """
    current = chain.current_node()
    if current is None:
        return OA_UNKNOWN
    if current.action == "退回":
        return "draft"
    if current.action == "批准" and str(chain.tx_status) == "0":
        return "approved"
    # tx_status == "1"（在途/已办语义）下，提交、批准、批注都表示仍在审链路中
    return "review"


def _rank(state: str) -> Optional[int]:
    if not state:
        return None
    return STATE_ORDER.get(str(state).strip())


def _classify(local_state: str, oa_state: str) -> str:
    lr, rk = _rank(local_state), _rank(oa_state)
    if lr is None or rk is None:
        # 无法用统一尺子比较时，字符串相同才算一致；否则保守判 OA 超前?
        # 详设只定义四态：不可比 → 不伪造一致；按"非同步即偏差"，
        # 未知本地态不向上推断，保守归 local_ahead（本地持有未验证态）。
        return IN_SYNC if str(local_state) == str(oa_state) else LOCAL_AHEAD
    if lr == rk:
        return IN_SYNC
    return OA_AHEAD if rk > lr else LOCAL_AHEAD


def _classify_event(local_state: str, oa_state: str, chain: ApprovalChain) -> str:
    """在序号比较基础上感知「退回」回退事件。

    审批流不是单调线性的：退回让状态从 review 回到 draft，这是 OA 侧一个
    真实事件，而非"OA 落后"。OA 是权威副本，当 OA 当前节点动作为退回、
    而本地未同步到 draft，说明本地未收到退回事件（本地过期）→ oa_ahead；
    本地也已是 draft → in_sync。其余情形仍走序号比较。
    """
    current = chain.current_node()
    if current is not None and current.action == "退回":
        return IN_SYNC if str(local_state).strip() == "draft" else OA_AHEAD
    return _classify(local_state, oa_state)


def reconcile(
    requestids: List[str],
    *,
    local_states: Optional[Dict[str, Any]] = None,
    reader: Optional[ApprovalLogReader] = None,
) -> List[ReconcileDiff]:
    """对一组 requestid 执行只读对账。

    Args:
        requestids: OA 流程单据 id 列表。
        local_states: {requestid: 本地预期态}；缺项 local_state 记为空串。
        reader: 注入的 ApprovalLogReader（依赖注入，默认新建，测试传 fake）。

    只读不写：本函数不调用任何写接口，也不触发会话重建策略之外的动作。
    """
    local_states = local_states or {}
    reader = reader if reader is not None else ApprovalLogReader()

    diffs: List[ReconcileDiff] = []
    for rid in requestids:
        key = str(rid)
        local_state = str(local_states.get(key, ""))
        try:
            chain = reader.read_approval_chain(key)
        except ApprovalLogUnavailable:
            diffs.append(ReconcileDiff(
                requestid=key, local_state=local_state,
                oa_state=OA_UNKNOWN, kind=OA_UNKNOWN,
            ))
            continue
        except Exception:
            # 任何非契约异常同样降级 unknown，绝不伪造、绝不抛出中断整批对账
            diffs.append(ReconcileDiff(
                requestid=key, local_state=local_state,
                oa_state=OA_UNKNOWN, kind=OA_UNKNOWN,
            ))
            continue

        oa_state = derive_oa_state(chain)
        kind = _classify_event(local_state, oa_state, chain)
        diffs.append(ReconcileDiff(
            requestid=key, local_state=local_state,
            oa_state=oa_state, kind=kind,
        ))
    return diffs


__all__ = [
    "ReconcileDiff",
    "derive_oa_state",
    "reconcile",
    "local_state_from_decisions",
    "IN_SYNC",
    "OA_AHEAD",
    "LOCAL_AHEAD",
    "OA_UNKNOWN",
]
