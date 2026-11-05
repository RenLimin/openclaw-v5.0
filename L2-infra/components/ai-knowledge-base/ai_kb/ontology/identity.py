"""IdentityService — P1 权威身份层.

依据 DESIGN-DETAIL-operational-ontology-v1.0 §2.1 / §3.1：
- 稳定权威主键（canonical_key）+ 跨源别名解析
- 软归并（merged_into + alias 转移），可审计、可回滚
- CWA（封闭世界假设）：resolve 命中即"存在"，未命中即"不存在"（返回 None）
- 运营对象 / 语料对象分离：object_type 白名单由 domain 配置驱动
"""
import json
import sqlite3
from typing import Optional, List, Dict, Any, Union, Mapping, Collection

from ..db import AIKB


def is_operational_object_type(
    domain_code: str,
    object_type: str,
    whitelist: Optional[Mapping[str, Collection[str]]],
) -> bool:
    """判定某 domain 下的 object_type 是否属于运营对象（封闭世界白名单）。

    白名单由 domain 配置驱动（装配期注入），形如::

        {"contract-domain": {"contract"}, "product-domain": {"product", "sku"}}

    规则：
    - whitelist 为 None：未配置白名单，不做封闭世界限制（返回 True）；
    - domain 已显式声明：仅集合内类型返回 True，支持 "*" 通配；
    - domain 未声明：默认放行，避免误伤新 domain。

    语料对象（document/chunk/qa 等）不在白名单内，不享受 CWA 身份保证。
    """
    if whitelist is None:
        return True
    types = whitelist.get(domain_code)
    if types is None:
        return True
    if "*" in types:
        return True
    return object_type in types


class IdentityService:
    """权威身份服务，依赖注入 AIKB 实例。"""

    def __init__(
        self,
        db: AIKB,
        object_type_whitelist: Optional[Mapping[str, Collection[str]]] = None,
    ):
        self.db = db
        self.object_type_whitelist = object_type_whitelist

    # --- 内部辅助 ---
    def _resolve_domain_id(self, domain: Union[int, str]) -> int:
        """接受 domain id（int）或 domain code（str）。"""
        if isinstance(domain, int):
            return domain
        cursor = self.db.execute("SELECT id FROM domain WHERE code = ?", (domain,))
        row = cursor.fetchone()
        if row is None:
            raise ValueError(f"domain not found: {domain}")
        return row[0]

    def _domain_code(self, domain_id: int) -> Optional[str]:
        cursor = self.db.execute("SELECT code FROM domain WHERE id = ?", (domain_id,))
        row = cursor.fetchone()
        return row[0] if row else None

    def _check_object_type(self, domain_id: int, object_type: str) -> None:
        domain_code = self._domain_code(domain_id)
        if not is_operational_object_type(domain_code, object_type, self.object_type_whitelist):
            raise ValueError(
                f"object_type '{object_type}' is not an operational object "
                f"in domain '{domain_code}' (CWA whitelist)"
            )

    def _get_identity(self, identity_id: int) -> Optional[sqlite3.Row]:
        cursor = self.db.execute(
            "SELECT * FROM ont_identity WHERE id = ?", (identity_id,)
        )
        return cursor.fetchone()

    # --- 公开 API（详设 §3.1）---
    def register_identity(
        self,
        domain: Union[int, str],
        object_type: str,
        canonical_key: str,
        sor: str,
        display_name: Optional[str] = None,
    ) -> int:
        """建权威身份。UNIQUE(domain_id, object_type, canonical_key)
        冲突时抛 sqlite3.IntegrityError。canonical_key 一经 commit 不可变。
        """
        domain_id = self._resolve_domain_id(domain)
        self._check_object_type(domain_id, object_type)

        now = self.db.get_now()
        cursor = self.db.execute("""
        INSERT INTO ont_identity
            (domain_id, object_type, canonical_key, system_of_record,
             display_name, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, 'active', ?, ?)
        """, (domain_id, object_type, canonical_key, sor, display_name, now, now))
        self.db.commit()
        return cursor.lastrowid

    def add_alias(
        self,
        identity_id: int,
        source_system: str,
        source_key: str,
        confidence: Optional[float] = None,
    ) -> int:
        """绑定跨源标识。UNIQUE(source_system, source_key)
        冲突时抛 sqlite3.IntegrityError。
        """
        if self._get_identity(identity_id) is None:
            raise ValueError(f"identity not found: {identity_id}")

        now = self.db.get_now()
        cursor = self.db.execute("""
        INSERT INTO ont_identity_alias
            (identity_id, source_system, source_key, confidence, created_at)
        VALUES (?, ?, ?, ?, ?)
        """, (identity_id, source_system, source_key, confidence, now))
        self.db.commit()
        return cursor.lastrowid

    def resolve(self, source_system: str, source_key: str) -> Optional[int]:
        """按 (源, 键) 解析权威 identity。

        CWA 边界：命中即"存在"，未命中即"不存在"（封闭世界），返回 None，
        调用方据此可拒绝操作。merge 后 alias 已转移，故自然解析到吸收方；
        另对 merged_into 指针做防御性跟随。
        """
        cursor = self.db.execute("""
        SELECT i.id, i.merged_into
        FROM ont_identity_alias a
        JOIN ont_identity i ON i.id = a.identity_id
        WHERE a.source_system = ? AND a.source_key = ?
        """, (source_system, source_key))
        row = cursor.fetchone()
        if row is None:
            return None
        # 防御性跟随软归并链（正常路径 alias 已在 merge 时转移）
        seen = set()
        identity_id, merged_into = row[0], row[1]
        while merged_into is not None and identity_id not in seen:
            seen.add(identity_id)
            identity_id = merged_into
            target = self._get_identity(identity_id)
            merged_into = target["merged_into"] if target else None
        return identity_id

    def merge(
        self,
        from_id: int,
        into_id: int,
        actor: str,
    ) -> Dict[str, Any]:
        """软归并：from_id 并入 into_id。

        动作：
        - from 方 status='merged'、merged_into=into_id（不物理删除，可回滚）；
        - from 方全部 alias 转移到 into 方；
        - 与 into 方重复的 (source_system, source_key) 属于同一身份的冗余
          别名，先删除以满足 UNIQUE(source_system, source_key)；
        - 返回决策记录占位 dict。

        P3 起归并经 DecisionService.record 实写 ont_decision_record
        （result='allowed'，change_set 记录 status/merged_into 变更与
        alias 转移/去重明细，evidence 记录 actor），并在 kb_audit_log
        details 中关联 decision_record_id（归并无提案，proposal_id 为空）。
        ont_decision_record 表不存在（未迁移 v10）时回退为占位记录，
        保持 P1 单测环境向后兼容。
        """
        if from_id == into_id:
            raise ValueError("cannot merge an identity into itself")

        src = self._get_identity(from_id)
        dst = self._get_identity(into_id)
        if src is None:
            raise ValueError(f"identity not found: {from_id}")
        if dst is None:
            raise ValueError(f"identity not found: {into_id}")
        if src["status"] == "merged" or src["merged_into"] is not None:
            raise ValueError(f"identity {from_id} is already merged")
        if dst["status"] != "active" or dst["merged_into"] is not None:
            raise ValueError(f"merge target {into_id} is not an active identity")

        # 找出与吸收方重复的源键，删除被归并方上的冗余 alias
        dup_cursor = self.db.execute("""
        SELECT a.source_system AS source_system, a.source_key AS source_key
        FROM ont_identity_alias a
        WHERE a.identity_id = ?
          AND EXISTS (
              SELECT 1 FROM ont_identity_alias b
              WHERE b.identity_id = ?
                AND b.source_system = a.source_system
                AND b.source_key = a.source_key
          )
        """, (from_id, into_id))
        dropped = [dict(r) for r in dup_cursor.fetchall()]
        for d in dropped:
            self.db.execute("""
            DELETE FROM ont_identity_alias
            WHERE identity_id = ? AND source_system = ? AND source_key = ?
            """, (from_id, d["source_system"], d["source_key"]))

        # alias 转移
        self.db.execute(
            "UPDATE ont_identity_alias SET identity_id = ? WHERE identity_id = ?",
            (into_id, from_id),
        )

        # 软归并指针
        now = self.db.get_now()
        self.db.execute("""
        UPDATE ont_identity
        SET status = 'merged', merged_into = ?, updated_at = ?
        WHERE id = ?
        """, (into_id, now, from_id))
        self.db.commit()

        # P3：经 DecisionService 实写决策对象；表未建（P1-only 环境）则回退占位。
        try:
            from .decision import DecisionService

            decisions = DecisionService(self.db)
            change_set = {
                "applied": True,
                "merge": {
                    "from_id": from_id,
                    "into_id": into_id,
                    "status_change": {"from": "active", "to": "merged"},
                    "merged_into": into_id,
                    "aliases_transferred": True,
                    "dropped_duplicate_aliases": dropped,
                },
            }
            evidence = {
                "actor": actor,
                "dropped_duplicate_aliases": dropped,
                "from": {"id": from_id, "canonical_key": src["canonical_key"]},
                "into": {"id": into_id, "canonical_key": dst["canonical_key"]},
            }
            record_id = decisions.record(
                src["domain_id"], "identity_merge",
                [src["canonical_key"], dst["canonical_key"]],
                actor, "human",
                change_set=change_set,
                rationale=f"identity merge {from_id} -> {into_id}",
                evidence=evidence,
                result="allowed",
            )
            # audit details 关联决策记录（归并无 proposal_id）
            self.db.add_audit_log(
                operation_type="ont_identity_merge", user_id=actor,
                object_type=src["object_type"], object_id=from_id,
                risk_level="low", action_taken="merge",
                details=json.dumps({
                    "proposal_id": None,
                    "decision_record_id": record_id,
                    "from_id": from_id,
                    "into_id": into_id,
                }, ensure_ascii=False),
            )
            return {
                "kind": "identity_merge",
                "from_id": from_id,
                "into_id": into_id,
                "actor": actor,
                "dropped_duplicate_aliases": dropped,
                "decision_record_id": record_id,
                "ts": now,
            }
        except sqlite3.OperationalError:
            # ont_decision_record 尚未迁移（如仅启用 P1 的环境）：回退占位。
            return {
                "kind": "identity_merge_placeholder",
                "from_id": from_id,
                "into_id": into_id,
                "actor": actor,
                "dropped_duplicate_aliases": dropped,
                "ts": now,
            }

    def list_identities(
        self,
        domain: Union[int, str],
        object_type: str,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """管理/联调用：按 domain + object_type 列身份，可按 status 过滤。"""
        domain_id = self._resolve_domain_id(domain)
        sql = """
        SELECT * FROM ont_identity
        WHERE domain_id = ? AND object_type = ?
        """
        params: List[Any] = [domain_id, object_type]
        if status is not None:
            sql += " AND status = ?"
            params.append(status)
        sql += " ORDER BY id"
        cursor = self.db.execute(sql, tuple(params))
        return [dict(r) for r in cursor.fetchall()]
