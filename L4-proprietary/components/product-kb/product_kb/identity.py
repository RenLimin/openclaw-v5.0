"""P1 权威身份层：canonical_key 生成 + ProductIdentityService.

依据 DESIGN-DETAIL-identity-v1.0 §3/§4：
- canonical_key：NFKC + 去空白/标点 + 小写，版本号保留（实测 193 条 0 冲突）；
- 身份服务：register/add_alias/resolve/merge/list/get_by_product_id，
  算法对齐 L2 ont_identity IdentityService（v8）。
- CWA：resolve 命中即"存在"，未命中即"不存在"（返回 None）。
- 软归并：merged_into + alias 转移，不物理删，可回滚。
"""
import re
import json
import unicodedata
from typing import Optional, List, Dict, Any

from .db import ProductKBDB

# 去空白与标点（保留中文、字母、数字、版本号里的点）
_STRIP_RE = re.compile(r"[\s\-_（）()【】\[\]·,，。、:：;；!！?？'\"“”‘’/\\|]")


def canonical_key(name: str) -> str:
    """产品名 -> 稳定自然键。

    1. NFKC 全角→半角；
    2. 去空白/标点；
    3. 小写；
    4. 版本号保留（V4.0/V5.0 构成不同键）。
    """
    n = unicodedata.normalize("NFKC", name).lower()
    n = _STRIP_RE.sub("", n)
    return n


class ProductIdentityService:
    """权威身份服务，依赖注入 ProductKBDB。"""

    def __init__(self, db: ProductKBDB):
        self.db = db

    def _get(self, identity_id: int) -> Optional[Any]:
        return self.db.execute(
            "SELECT * FROM product_identity WHERE id = ?", (identity_id,)
        ).fetchone()

    def _audit(self, identity_id: int, op: str, actor: str,
               details: Dict[str, Any]) -> None:
        self.db.execute(
            """INSERT INTO identity_audit (identity_id, op, actor, details, ts)
               VALUES (?, ?, ?, ?, ?)""",
            (identity_id, op, actor,
             json.dumps(details, ensure_ascii=False), self.db.get_now()),
        )
        self.db.commit()

    # --- 写 ---
    def register(
        self,
        product_id: int,
        display_name: Optional[str] = None,
        canonical: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """建权威身份。canonical 默认由 display_name 规范化。

        UNIQUE(product_id) / UNIQUE(canonical_key) 冲突抛 sqlite3.IntegrityError。
        canonical_key 一经生成不可变。
        """
        name = display_name
        if name is None:
            row = self.db.execute(
                "SELECT name FROM product WHERE id = ?", (product_id,)
            ).fetchone()
            if row is None:
                raise ValueError(f"product not found: {product_id}")
            name = row["name"]
        key = canonical or canonical_key(name)
        now = self.db.get_now()
        cur = self.db.execute(
            """INSERT INTO product_identity
               (product_id, canonical_key, display_name, status, metadata,
                created_at, updated_at)
               VALUES (?, ?, ?, 'active', ?, ?, ?)""",
            (product_id, key, name,
             json.dumps(metadata, ensure_ascii=False) if metadata else None,
             now, now),
        )
        self.db.commit()
        return cur.lastrowid

    def add_alias(
        self,
        identity_id: int,
        source_system: str,
        source_key: str,
        confidence: Optional[float] = None,
    ) -> int:
        """绑定跨源标识。UNIQUE(source_system, source_key) 冲突抛 IntegrityError。"""
        if self._get(identity_id) is None:
            raise ValueError(f"identity not found: {identity_id}")
        cur = self.db.execute(
            """INSERT INTO product_alias
               (identity_id, source_system, source_key, confidence, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (identity_id, source_system, source_key, confidence,
             self.db.get_now()),
        )
        self.db.commit()
        return cur.lastrowid

    # --- 读（CWA） ---
    def resolve(self, source_system: str, source_key: str) -> Optional[int]:
        """(源, 键) -> 权威 product_id；未命中返回 None（封闭世界）。

        merge 后 alias 已转移，自然解析到吸收方；另防御性跟随 merged_into 链。
        """
        row = self.db.execute(
            """SELECT i.id, i.merged_into, i.product_id
               FROM product_alias a
               JOIN product_identity i ON i.id = a.identity_id
               WHERE a.source_system = ? AND a.source_key = ?""",
            (source_system, source_key),
        ).fetchone()
        if row is None:
            return None
        identity_id, merged_into, product_id = row["id"], row["merged_into"], row["product_id"]
        seen = set()
        while merged_into is not None and identity_id not in seen:
            seen.add(identity_id)
            target = self._get(merged_into)
            if target is None:
                break
            identity_id = target["id"]
            product_id = target["product_id"]
            merged_into = target["merged_into"]
        return product_id

    def get_by_product_id(self, product_id: int) -> Optional[Dict[str, Any]]:
        row = self.db.execute(
            "SELECT * FROM product_identity WHERE product_id = ?", (product_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_by_canonical(self, key: str) -> Optional[Dict[str, Any]]:
        row = self.db.execute(
            "SELECT * FROM product_identity WHERE canonical_key = ?", (key,)
        ).fetchone()
        return dict(row) if row else None

    def list(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM product_identity"
        params: tuple = ()
        if status is not None:
            sql += " WHERE status = ?"
            params = (status,)
        sql += " ORDER BY id"
        return [dict(r) for r in self.db.execute(sql, params).fetchall()]

    def list_aliases(self, identity_id: int) -> List[Dict[str, Any]]:
        return [dict(r) for r in self.db.execute(
            "SELECT * FROM product_alias WHERE identity_id = ? ORDER BY id",
            (identity_id,),
        ).fetchall()]

    # --- 软归并 ---
    def merge(self, from_id: int, into_id: int, actor: str) -> Dict[str, Any]:
        """from_id 并入 into_id（软归并，可回滚）。

        - from 方 status='merged' + merged_into；
        - 与 into 方重复的 (source_system, source_key) 删除以满足 UNIQUE；
        - 其余 alias 转移到 into 方；
        - 不物理删。返回归并明细。
        """
        if from_id == into_id:
            raise ValueError("cannot merge an identity into itself")
        src, dst = self._get(from_id), self._get(into_id)
        if src is None:
            raise ValueError(f"identity not found: {from_id}")
        if dst is None:
            raise ValueError(f"identity not found: {into_id}")
        if src["status"] == "merged" or src["merged_into"] is not None:
            raise ValueError(f"identity {from_id} is already merged")
        if dst["status"] != "active" or dst["merged_into"] is not None:
            raise ValueError(f"merge target {into_id} is not active")

        # 重复 alias 删除
        dups = [dict(r) for r in self.db.execute(
            """SELECT a.source_system, a.source_key FROM product_alias a
               WHERE a.identity_id = ?
                 AND EXISTS (SELECT 1 FROM product_alias b
                             WHERE b.identity_id = ?
                               AND b.source_system = a.source_system
                               AND b.source_key = a.source_key)""",
            (from_id, into_id),
        ).fetchall()]
        for d in dups:
            self.db.execute(
                """DELETE FROM product_alias
                   WHERE identity_id = ? AND source_system = ? AND source_key = ?""",
                (from_id, d["source_system"], d["source_key"]),
            )
        # alias 转移
        self.db.execute(
            "UPDATE product_alias SET identity_id = ? WHERE identity_id = ?",
            (into_id, from_id),
        )
        # 软归并
        now = self.db.get_now()
        self.db.execute(
            """UPDATE product_identity
               SET status = 'merged', merged_into = ?, updated_at = ?
               WHERE id = ?""",
            (into_id, now, from_id),
        )
        self.db.commit()
        self._audit(from_id, "merge", actor, {
            "into_id": into_id,
            "dropped_duplicate_aliases": dups,
        })
        return {
            "kind": "identity_merge",
            "from_id": from_id,
            "into_id": into_id,
            "actor": actor,
            "dropped_duplicate_aliases": dups,
            "ts": now,
        }

    def unmerge(self, identity_id: int, actor: str = 'system') -> Dict[str, Any]:
        """回滚一次软归并：恢复 status/merged_into，alias 转回。

        注意：merge 时删除的重复 alias 无法恢复（已在 merge 明细中记录）。
        """
        row = self._get(identity_id)
        if row is None:
            raise ValueError(f"identity not found: {identity_id}")
        if row["status"] != "merged" or row["merged_into"] is None:
            raise ValueError(f"identity {identity_id} is not merged")
        target = row["merged_into"]
        self.db.execute(
            """UPDATE product_identity
               SET status = 'active', merged_into = NULL,
                   updated_at = ? WHERE id = ?""",
            (self.db.get_now(), identity_id),
        )
        self.db.execute(
            "UPDATE product_alias SET identity_id = ? WHERE identity_id = ?",
            (identity_id, target),
        )
        self.db.commit()
        self._audit(identity_id, "unmerge", actor,
                    {"restored_from": target})
        return {"kind": "identity_unmerge", "identity_id": identity_id,
                "restored_from": target, "ts": self.db.get_now()}
