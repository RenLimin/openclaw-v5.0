"""P7 对象级权限：mandatory markings + clearance（设计详设 §3）.

- MarkingDirectory：marking 注册 / 主体授予(强制过期) / 吊销 / 有效集合；
- PolicyEvaluator：读/写/审/MCP 共用的单一对象级评估器。

语义（来自 Palantir Markings + 四类来源调研）：
- mandatory AND：主体须持有对象上【全部】marking；
- clearance 四级，主体须 >= 对象；
- deny 优先 / fail-closed：元数据非法、marking 未注册一律拒；
- high-sensitivity marking 在 review/commit 层实时查 grant 表复查。

无第三方依赖，仅标准库。
"""
from __future__ import annotations

import datetime as _dt
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Union

from ..db import AIKB

CLEARANCE_LEVELS = ["public", "internal", "confidential", "restricted"]
MAX_GRANT_DAYS = 90

_SENSITIVITIES = {"normal", "high"}
_GRANT_SOURCES = {"directory", "manual", "ticket"}


class MarkingError(Exception):
    """marking 治理错误基类。"""


class MarkingNotFound(MarkingError):
    """引用了未注册的 marking code。"""


@dataclass(frozen=True)
class Decision:
    """对象级评估结论。reason/missing 仅供审计，不回显敏感字段值。"""

    allowed: bool
    reason: str = "allowed"
    missing: List[str] = field(default_factory=list)

    def __bool__(self) -> bool:  # 便于 if decision:
        return self.allowed


# ---------------------------------------------------------------
# MarkingDirectory
# ---------------------------------------------------------------

class MarkingDirectory:
    """marking 注册表 + 主体授予（依赖注入 AIKB）。"""

    def __init__(self, db: AIKB, max_grant_days: int = MAX_GRANT_DAYS) -> None:
        self.db = db
        self.max_grant_days = max_grant_days

    # --- 内部辅助 ---
    def _resolve_domain_id(self, domain: Union[int, str]) -> int:
        if isinstance(domain, int):
            return domain
        row = self.db.execute(
            "SELECT id FROM domain WHERE code = ?", (domain,)
        ).fetchone()
        if row is None:
            raise ValueError(f"domain not found: {domain}")
        return row[0]

    @staticmethod
    def _now(now: Optional[_dt.datetime] = None) -> _dt.datetime:
        return now or _dt.datetime.now()

    # --- 注册 ---
    def register(
        self,
        domain: Union[int, str],
        code: str,
        name: str,
        *,
        sensitivity: str = "normal",
        owner: Optional[str] = None,
    ) -> int:
        if not code:
            raise MarkingError("marking code must not be empty")
        if sensitivity not in _SENSITIVITIES:
            raise MarkingError(
                f"sensitivity must be one of {sorted(_SENSITIVITIES)}"
            )
        domain_id = self._resolve_domain_id(domain)
        ts = self.db.get_now()
        existing = self.db.execute(
            "SELECT id FROM ont_marking WHERE domain_id = ? AND code = ?",
            (domain_id, code),
        ).fetchone()
        if existing is not None:
            # 幂等：更新可变字段，不新增
            self.db.execute(
                "UPDATE ont_marking SET name=?, sensitivity=?, owner=? "
                "WHERE id=?",
                (name, sensitivity, owner, existing["id"]),
            )
            self.db.commit()
            return existing["id"]
        cursor = self.db.execute(
            "INSERT INTO ont_marking "
            "(domain_id, code, name, sensitivity, owner, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (domain_id, code, name, sensitivity, owner, ts),
        )
        self.db.commit()
        return cursor.lastrowid

    def get(
        self, domain: Union[int, str], code: str
    ) -> Optional[Dict[str, Any]]:
        domain_id = self._resolve_domain_id(domain)
        return self.db.execute(
            "SELECT * FROM ont_marking WHERE domain_id = ? AND code = ?",
            (domain_id, code),
        ).fetchone()

    def list(self, domain: Union[int, str]) -> List[Dict[str, Any]]:
        domain_id = self._resolve_domain_id(domain)
        rows = self.db.execute(
            "SELECT * FROM ont_marking WHERE domain_id = ? ORDER BY code",
            (domain_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    # --- 授予 / 吊销 ---
    def grant(
        self,
        domain: Union[int, str],
        code: str,
        subject: str,
        *,
        source: str,
        granted_by: Optional[str] = None,
        ttl_days: Optional[int] = None,
        now: Optional[_dt.datetime] = None,
    ) -> int:
        if not subject:
            raise MarkingError("subject must not be empty")
        if source not in _GRANT_SOURCES:
            raise MarkingError(
                f"source must be one of {sorted(_GRANT_SOURCES)}"
            )
        marking = self.get(domain, code)
        if marking is None:
            raise MarkingNotFound(f"marking not registered: {code}")

        # D1：强制 expires_at，且上限 max_grant_days
        ttl = self.max_grant_days if ttl_days is None else ttl_days
        if ttl <= 0:
            raise MarkingError("ttl_days must be positive")
        if ttl > self.max_grant_days:
            raise MarkingError(
                f"ttl_days {ttl} exceeds max {self.max_grant_days}"
            )
        current = self._now(now)
        granted_at = current
        expires_at = current + _dt.timedelta(days=ttl)

        existing = self.db.execute(
            "SELECT id FROM ont_marking_grant "
            "WHERE marking_id = ? AND subject = ?",
            (marking["id"], subject),
        ).fetchone()
        if existing is not None:
            # 幂等续期：刷新时间窗与来源
            self.db.execute(
                "UPDATE ont_marking_grant SET source=?, granted_at=?, "
                "expires_at=?, revoked_at=NULL, granted_by=? WHERE id=?",
                (source, granted_at.isoformat(), expires_at.isoformat(),
                 granted_by, existing["id"]),
            )
            self.db.commit()
            return existing["id"]
        cursor = self.db.execute(
            "INSERT INTO ont_marking_grant "
            "(marking_id, subject, source, granted_at, expires_at, "
            " revoked_at, granted_by) VALUES (?, ?, ?, ?, ?, NULL, ?)",
            (marking["id"], subject, source, granted_at.isoformat(),
             expires_at.isoformat(), granted_by),
        )
        self.db.commit()
        return cursor.lastrowid

    def revoke(
        self,
        domain: Union[int, str],
        code: str,
        subject: str,
        *,
        now: Optional[_dt.datetime] = None,
    ) -> None:
        marking = self.get(domain, code)
        if marking is None:
            raise MarkingNotFound(f"marking not registered: {code}")
        ts = self._now(now).isoformat()
        self.db.execute(
            "UPDATE ont_marking_grant SET revoked_at=? "
            "WHERE marking_id=? AND subject=? AND revoked_at IS NULL",
            (ts, marking["id"], subject),
        )
        self.db.commit()

    # --- 有效集合（实时查，过滤过期/吊销）---
    def active_markings(
        self,
        subject: str,
        *,
        domain: Union[int, str, None] = None,
        now: Optional[_dt.datetime] = None,
    ) -> Set[str]:
        current = self._now(now)
        sql = (
            "SELECT m.code AS code, g.expires_at AS expires_at, "
            "g.revoked_at AS revoked_at "
            "FROM ont_marking_grant g JOIN ont_marking m "
            "ON g.marking_id = m.id WHERE g.subject = ?"
        )
        params: List[Any] = [subject]
        if domain is not None:
            sql += " AND m.domain_id = ?"
            params.append(self._resolve_domain_id(domain))
        rows = self.db.execute(sql, tuple(params)).fetchall()
        active: Set[str] = set()
        for r in rows:
            if r["revoked_at"]:
                continue
            try:
                if _dt.datetime.fromisoformat(r["expires_at"]) < current:
                    continue
            except (TypeError, ValueError):
                continue  # 坏时间戳不授予（fail-closed）
            active.add(r["code"])
        return active

    def has_high_sensitivity(
        self, domain: Union[int, str], codes: Set[str]
    ) -> bool:
        if not codes:
            return False
        domain_id = self._resolve_domain_id(domain)
        placeholders = ",".join("?" for _ in codes)
        row = self.db.execute(
            f"SELECT COUNT(*) AS c FROM ont_marking "
            f"WHERE domain_id=? AND code IN ({placeholders}) "
            f"AND sensitivity='high'",
            [domain_id, *codes],
        ).fetchone()
        return row["c"] > 0


# ---------------------------------------------------------------
# PolicyEvaluator
# ---------------------------------------------------------------

class PolicyEvaluator:
    """单一对象级评估器：mandatory markings + clearance。"""

    def __init__(
        self,
        db: AIKB,
        directory: Optional[MarkingDirectory] = None,
        max_grant_days: int = MAX_GRANT_DAYS,
    ) -> None:
        self.db = db
        self.directory = directory or MarkingDirectory(db, max_grant_days)

    @staticmethod
    def _clearance_rank(value: Any) -> Optional[int]:
        if not isinstance(value, str) or value not in CLEARANCE_LEVELS:
            return None
        return CLEARANCE_LEVELS.index(value)

    @staticmethod
    def _extract_object_security(
        metadata: Any,
    ) -> Optional[Dict[str, Any]]:
        """从 metadata 提取 {markings, clearance}；非法返 None（fail-closed）。"""
        if metadata is None:
            return {"markings": [], "clearance": "internal"}
        if not isinstance(metadata, dict):
            return None
        markings = metadata.get("markings", [])
        if not isinstance(markings, list) or not all(
            isinstance(m, str) and m for m in markings
        ):
            return None
        perms = metadata.get("permissions") or {}
        if not isinstance(perms, dict):
            return None
        # D3：clearance 单字段；confidence_level 仅读别名
        clearance = perms.get("clearance")
        if clearance is None:
            clearance = perms.get("confidence_level", "internal")
        if clearance not in CLEARANCE_LEVELS:
            return None
        return {"markings": list(markings), "clearance": clearance}

    def evaluate(
        self,
        subject_claims: Dict[str, Any],
        object_metadata: Any,
        *,
        verb: str,
        domain: Union[int, str, None] = None,
        realtime: bool = False,
        now: Optional[_dt.datetime] = None,
    ) -> Decision:
        if not isinstance(subject_claims, dict):
            return Decision(False, "bad_subject")

        sec = self._extract_object_security(object_metadata)
        if sec is None:
            return Decision(False, "bad_metadata")

        # 1) clearance（claims 缺省 = internal，不提权）
        subject_clearance = subject_claims.get("clearance", "internal")
        s_rank = self._clearance_rank(subject_clearance)
        o_rank = self._clearance_rank(sec["clearance"])
        if s_rank is None or o_rank is None:
            return Decision(False, "bad_clearance")
        if s_rank < o_rank:
            return Decision(False, "clearance")

        # 2) markings AND（claims.markings 缺省 = 空集）
        claims_markings = subject_claims.get("markings", [])
        if not isinstance(claims_markings, list):
            return Decision(False, "bad_claims_markings")
        held = {m for m in claims_markings if isinstance(m, str)}
        required = set(sec["markings"])

        # 引用未注册 marking code => fail-closed（对象侧配置错误也拒）
        if domain is not None and required:
            registered = {m["code"] for m in self.directory.list(domain)}
            if not required <= registered:
                unknown = sorted(required - registered)
                return Decision(False, "unregistered_marking", unknown)

        missing = sorted(required - held)
        if missing:
            return Decision(False, f"missing_marking:{missing[0]}", missing)

        # 3) realtime 高敏复查（D2）
        if realtime and domain is not None and required:
            if self.directory.has_high_sensitivity(domain, required):
                live = self.directory.active_markings(
                    subject_claims.get("sub", ""), domain=domain, now=now
                )
                live_missing = sorted(required - live)
                if live_missing:
                    return Decision(
                        False,
                        f"realtime_revoked:{live_missing[0]}",
                        live_missing,
                    )
        return Decision(True, "allowed", [])

    def realtime_assert(
        self,
        subject: str,
        object_metadata: Any,
        *,
        domain: Union[int, str],
        now: Optional[_dt.datetime] = None,
    ) -> Decision:
        """commit 层高敏复查：只查 high-sensitivity marking 是否仍有效。

        clearance 已在 review 层验证过，这里不重复判；仅防
        review→commit 间隙内高敏授予被吊销/过期（D2 双保险）。
        无 marking / 非 high 敏 → 直接放行。
        """
        sec = self._extract_object_security(object_metadata)
        if sec is None:
            return Decision(False, "bad_metadata")
        required = set(sec["markings"])
        if not required:
            return Decision(True, "allowed", [])
        if not self.directory.has_high_sensitivity(domain, required):
            return Decision(True, "allowed", [])
        live = self.directory.active_markings(subject, domain=domain, now=now)
        missing = sorted(required - live)
        if missing:
            return Decision(False, f"realtime_revoked:{missing[0]}", missing)
        return Decision(True, "allowed", [])
