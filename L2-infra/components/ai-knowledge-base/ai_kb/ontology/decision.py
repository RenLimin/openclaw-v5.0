"""DecisionService — P3 决策对象（详设 §2.3 / §3.4）.

- record：写 ont_decision_record（commit 内调用 / 人工直录 / identity.merge）
- replay：按对象回放决策链（学习/审计视角）
- stats：决策语料统计（后续风险规则迭代/微调用）

与 kb_audit_log 的分工：audit_log 记"发生过的操作"（运维/安全），
decision_record 记"做了什么决策及其依据"（业务/学习）；两者经
proposal_id 关联。
"""
import json
from typing import Any, Dict, List, Optional, Union

from ..db import AIKB

# result 合法取值（详设 §2.3）
_RESULTS = {"allowed", "rejected", "compensated"}
# actor_kind 合法取值
_ACTOR_KINDS = {"human", "agent"}


class DecisionService:
    """决策对象服务，依赖注入 AIKB 实例。"""

    def __init__(self, db: AIKB) -> None:
        self.db = db

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
    def _dump_json(value: Any, field_name: str, *, allow_none: bool = False) -> Optional[str]:
        if value is None:
            if allow_none:
                return None
            raise ValueError(f"{field_name} must not be None")
        if isinstance(value, str):
            # 提前解析，拒绝坏 JSON
            json.loads(value)
            return value
        return json.dumps(value, ensure_ascii=False)

    # --- 公开 API（详设 §3.4）---
    def record(
        self,
        domain: Union[int, str],
        action_type: str,
        object_refs: Union[str, List[Any]],
        actor_id: str,
        actor_kind: str,
        change_set: Union[str, Dict[str, Any]],
        *,
        proposal_id: Optional[int] = None,
        rationale: Optional[str] = None,
        evidence: Union[str, Dict[str, Any], None] = None,
        result: str = "allowed",
        token_fingerprint: Optional[str] = None,
    ) -> int:
        """写一条决策记录 → decision_record id。

        result: allowed | rejected | compensated。
        object_refs/change_set 必填（NOT NULL）；evidence 可空。
        本方法只做插入与 commit，调用方负责外层事务语义
        （ProposalService.commit 在同一事务内调用，故这里不自行 commit
        由调用方通过 autocommit 参数控制——为保持简单，本方法默认提交；
        commit 事务内改用 record_no_commit）。
        """
        return self._record(
            domain, action_type, object_refs, actor_id, actor_kind,
            change_set, proposal_id=proposal_id, rationale=rationale,
            evidence=evidence, result=result, do_commit=True,
            token_fingerprint=token_fingerprint,
        )

    def record_no_commit(
        self,
        domain: Union[int, str],
        action_type: str,
        object_refs: Union[str, List[Any]],
        actor_id: str,
        actor_kind: str,
        change_set: Union[str, Dict[str, Any]],
        *,
        proposal_id: Optional[int] = None,
        rationale: Optional[str] = None,
        evidence: Union[str, Dict[str, Any], None] = None,
        result: str = "allowed",
        token_fingerprint: Optional[str] = None,
    ) -> int:
        """同 record，但不自行 commit（供 ProposalService.commit 单事务内调用）。"""
        return self._record(
            domain, action_type, object_refs, actor_id, actor_kind,
            change_set, proposal_id=proposal_id, rationale=rationale,
            evidence=evidence, result=result, do_commit=False,
            token_fingerprint=token_fingerprint,
        )

    def _record(
        self,
        domain: Union[int, str],
        action_type: str,
        object_refs: Union[str, List[Any]],
        actor_id: str,
        actor_kind: str,
        change_set: Union[str, Dict[str, Any]],
        *,
        proposal_id: Optional[int],
        rationale: Optional[str],
        evidence: Union[str, Dict[str, Any], None],
        result: str,
        do_commit: bool,
        token_fingerprint: Optional[str] = None,
    ) -> int:
        if result not in _RESULTS:
            raise ValueError(f"result must be one of {sorted(_RESULTS)}, got {result!r}")
        if actor_kind not in _ACTOR_KINDS:
            raise ValueError(
                f"actor_kind must be one of {sorted(_ACTOR_KINDS)}, got {actor_kind!r}"
            )
        if not action_type:
            raise ValueError("action_type must not be empty")
        if not actor_id:
            raise ValueError("actor_id must not be empty")

        domain_id = self._resolve_domain_id(domain)
        object_refs_text = self._dump_json(object_refs, "object_refs")
        change_set_text = self._dump_json(change_set, "change_set")
        evidence_text = self._dump_json(evidence, "evidence", allow_none=True)

        now = self.db.get_now()
        cursor = self.db.execute("""
        INSERT INTO ont_decision_record
            (proposal_id, domain_id, action_type, object_refs, actor_id,
             actor_kind, rationale, change_set, evidence, result,
             token_fingerprint, ts)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (proposal_id, domain_id, action_type, object_refs_text, actor_id,
              actor_kind, rationale, change_set_text, evidence_text, result,
              token_fingerprint, now))
        record_id = cursor.lastrowid
        if do_commit:
            self.db.commit()
        return record_id

    def replay(
        self,
        domain: Union[int, str],
        object_type: str,
        canonical_key: str,
        since: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """按对象回放决策链。

        object_refs 中的元素支持两种形态：
        - 纯字符串 canonical_key；
        - 对象 {"object_type": ..., "canonical_key": ...}。
        回放时在 Python 侧反逐条过滤（JSON 数组形态不固定，不依赖
        SQLite json1 函数，保证可移植）。
        """
        domain_id = self._resolve_domain_id(domain)
        sql = "SELECT * FROM ont_decision_record WHERE domain_id = ?"
        params: List[Any] = [domain_id]
        if since is not None:
            sql += " AND ts >= ?"
            params.append(since)
        sql += " ORDER BY id"
        rows = self.db.execute(sql, tuple(params)).fetchall()

        chain: List[Dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            try:
                refs = json.loads(item["object_refs"])
            except (TypeError, json.JSONDecodeError):
                continue
            if _refs_contain(refs, object_type, canonical_key):
                item["object_refs"] = refs
                item["change_set"] = _safe_json(item["change_set"])
                item["evidence"] = _safe_json(item["evidence"])
                chain.append(item)
        return chain

    def stats(
        self,
        domain: Union[int, str],
        action_type: Optional[str] = None,
        result: Optional[str] = None,
        since: Optional[str] = None,
    ) -> Dict[str, Any]:
        """决策语料统计：总量 + 按 result / action_type 分组。"""
        domain_id = self._resolve_domain_id(domain)
        where = ["domain_id = ?"]
        params: List[Any] = [domain_id]
        if action_type is not None:
            where.append("action_type = ?")
            params.append(action_type)
        if result is not None:
            if result not in _RESULTS:
                raise ValueError(f"result must be one of {sorted(_RESULTS)}")
            where.append("result = ?")
            params.append(result)
        if since is not None:
            where.append("ts >= ?")
            params.append(since)
        where_sql = " AND ".join(where)

        total = self.db.execute(
            f"SELECT COUNT(*) FROM ont_decision_record WHERE {where_sql}",
            tuple(params),
        ).fetchone()[0]

        by_result_rows = self.db.execute(
            f"SELECT result, COUNT(*) AS cnt FROM ont_decision_record "
            f"WHERE {where_sql} GROUP BY result",
            tuple(params),
        ).fetchall()
        by_result = {r["result"]: r["cnt"] for r in by_result_rows}

        by_action_rows = self.db.execute(
            f"SELECT action_type, COUNT(*) AS cnt FROM ont_decision_record "
            f"WHERE {where_sql} GROUP BY action_type ORDER BY cnt DESC",
            tuple(params),
        ).fetchall()
        by_action = {r["action_type"]: r["cnt"] for r in by_action_rows}

        return {
            "domain_id": domain_id,
            "total": total,
            "by_result": by_result,
            "by_action_type": by_action,
        }

    def get(self, record_id: int) -> Optional[Dict[str, Any]]:
        """按 id 读单条决策记录（含反序列化 JSON 字段）。"""
        row = self.db.execute(
            "SELECT * FROM ont_decision_record WHERE id = ?", (record_id,)
        ).fetchone()
        if row is None:
            return None
        item = dict(row)
        item["object_refs"] = _safe_json(item["object_refs"])
        item["change_set"] = _safe_json(item["change_set"])
        item["evidence"] = _safe_json(item["evidence"])
        return item


# --- 模块级辅助 ---

def _safe_json(value: Optional[str]) -> Any:
    if value is None:
        return None
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return value


def _refs_contain(refs: Any, object_type: str, canonical_key: str) -> bool:
    if not isinstance(refs, list):
        return False
    for ref in refs:
        if isinstance(ref, str):
            if ref == canonical_key:
                return True
        elif isinstance(ref, dict):
            if ref.get("canonical_key") != canonical_key:
                continue
            # 形态带 object_type 时要求同时匹配；不带则只匹配 key
            ref_type = ref.get("object_type")
            if ref_type is None or ref_type == object_type:
                return True
    return False
