"""ContractRegistry — 合同 → L2 运营对象登记（P1）。

依据 DESIGN-OUTLINE-contract-ontology-bridge-v1.0 §3/D1/D4：
- 合同先登记为 L2 运营对象（ont_identity，object_type=contract），
  之后才能经 Proposal Gate 执行 submit/approve/reject（CWA 前置）；
- canonical_key = canonical_contract_no(contract_no)（NFKC + 去空白标点 + 小写，
  保留编号语义；键一经生成不可变）；
- L4 contracts 表为 source of truth，L2 ont_identity 为运营索引/快照：
  metadata 内镜像 status/amount/title 等字段（供 L3 deterministic handler 读取）；
- 幂等：重复登记返回既有记录，不重建 L4 行、不重复建 identity。

依赖注入（方法内，不顶层 import，保持模块自包含）：
- L4 Repository（repository.db）
- L2 AIKB + IdentityService（ai_kb）
"""
from __future__ import annotations

import json
import os
import re
import sys
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------
# sys.path 注入（L4 组件根 + L2 ai-kb + L3 contract-management）
# ---------------------------------------------------------------

def _ensure_paths() -> None:
    """把组件根 / L2 ai-kb / L3 contract-management 加入 sys.path（幂等）。"""
    here = os.path.dirname(os.path.abspath(__file__))          # .../contract_review/ontology_bridge
    comp = os.path.dirname(os.path.dirname(here))              # .../bangcle-contract
    l4_components = os.path.dirname(comp)                      # .../components
    root = os.path.abspath(os.path.join(l4_components, "..", ".."))  # workspace root
    paths = [
        comp,
        os.path.join(root, "L2-infra", "components", "ai-knowledge-base"),
        os.path.join(root, "L3-business", "components", "contract-management"),
    ]
    for p in paths:
        if os.path.isdir(p) and p not in sys.path:
            sys.path.insert(0, p)


# ---------------------------------------------------------------
# canonical_key 规范化（D4）
# ---------------------------------------------------------------

_PUNCT_RE = re.compile(
    r"[\s\u3000，。；：、（）()【】\[\]\"'`~!@#$%^&*+=/\\|,.;:<>?{}_]+"
)


def canonical_contract_no(contract_no: str) -> str:
    """规范化合同编号 → canonical_key（幂等、不可变语义）。

    NFKC 全角转半角 → 去空白与常见标点 → 小写。保留字母/数字/连字符。
    示例：'HT-2026-001' → 'ht-2026-001'；'ＨＴ－２０２６－００１' → 'ht-2026-001'。
    """
    if contract_no is None:
        return ""
    s = unicodedata.normalize("NFKC", str(contract_no)).strip().lower()
    s = _PUNCT_RE.sub("", s)
    # 连字符保留（编号语义），但连续空白已在上一步清掉
    return s


# ---------------------------------------------------------------
# ContractRegistry
# ---------------------------------------------------------------

DOMAIN_CODE = "bangcle-contract"
OBJECT_TYPE = "contract"
SOR = "bangcle-contract"          # system_of_record：L4 bangcle-contract 组件


class ContractRegistry:
    """登记/查询合同运营对象（L4 表 + L2 ont_identity 双写，幂等）。"""

    def __init__(
        self,
        db_path: Optional[str] = None,
        ai_kb_path: Optional[str] = None,
    ) -> None:
        _ensure_paths()
        from repository.db import default_db_path

        self.db_path = db_path or default_db_path()
        # ai_kb 默认跟随 contract db（同目录 ai_kb.db），保证 CLI/脚本/测试
        # 传入自定义 db 时登记与查询落在同一库。
        self.ai_kb_path = ai_kb_path or os.path.join(
            os.path.dirname(self.db_path), "ai_kb.db",
        )

    # --- L2 辅助 ---
    def _ai_kb(self):
        """打开 AIKB 连接（init_db + ontology 表，幂等）。"""
        from ai_kb.db import AIKB
        ai = AIKB(self.ai_kb_path)
        ai.init_db()
        ai.init_ontology_tables()
        return ai

    def _domain_id(self, ai) -> int:
        return ai.get_or_create_domain(
            "Bangcle Contract", DOMAIN_CODE,
            "L4 bangcle-contract 实例（合同审批运营对象）",
        )

    def _find_identity(self, ai, domain_id: int, canonical: str) -> Optional[Dict[str, Any]]:
        row = ai.execute(
            "SELECT * FROM ont_identity "
            "WHERE domain_id = ? AND object_type = ? AND canonical_key = ?",
            (domain_id, OBJECT_TYPE, canonical),
        ).fetchone()
        return dict(row) if row else None

    # --- 登记 ---
    def register(
        self,
        contract_no: str,
        title: str = "",
        amount: float = 0.0,
        *,
        contract_type: str = "tech_service",
        party_a: str = "",
        party_b: str = "",
        effective_date: Optional[str] = None,
        expiry_date: Optional[str] = None,
        created_by: str = "contractctl",
    ) -> Dict[str, Any]:
        """登记合同为运营对象（幂等）。

        返回 {"contract_id", "identity_id", "canonical_key", "status", "created"}：
        - created=True：本次新建；False：既有记录（幂等重放）。
        流程：
          1) L4 contracts 表按 contract_no 查；无则建行（status=draft）；
          2) L2 ont_identity 按 canonical_key 查；无则 register_identity +
             add_alias(原始 contract_no) + 写 metadata 镜像；
          3) 返回双 id。
        """
        from repository.db import Repository

        canonical = canonical_contract_no(contract_no)
        if not canonical:
            raise ValueError(f"invalid contract_no: {contract_no!r}")

        created = False
        # 1) L4 行（幂等）
        with Repository(self.db_path) as repo:
            row = repo.get_contract_row_by_no(contract_no)
            if row is None:
                contract_id = repo.add_contract(
                    contract_no=contract_no, title=title,
                    contract_type=contract_type, party_a=party_a,
                    party_b=party_b, amount=float(amount),
                    status="draft", current_approver=None,
                    effective_date=effective_date, expiry_date=expiry_date,
                    extra=None, created_by=created_by,
                )
                created = True
            else:
                contract_id = row["id"]

        # 2) L2 identity（幂等）
        ai = self._ai_kb()
        try:
            domain_id = self._domain_id(ai)
            ident = self._find_identity(ai, domain_id, canonical)
            if ident is None:
                from ai_kb.ontology import IdentityService
                svc = IdentityService(ai)
                identity_id = svc.register_identity(
                    domain_id, OBJECT_TYPE, canonical, SOR,
                    display_name=title or contract_no,
                )
                # alias：原始合同编号（保留原样，供 resolve）
                svc.add_alias(identity_id, SOR, contract_no, confidence=1.0)
                # metadata 镜像（供 L3 handler 读 status/amount）
                now = ai.get_now()
                metadata = {
                    "status": "draft",
                    "contract_id": contract_id,
                    "contract_no": contract_no,
                    "title": title,
                    "amount": float(amount),
                    "contract_type": contract_type,
                    "source": SOR,
                    "applied_changes": [],
                    "registered_at": now,
                }
                ai.execute(
                    "UPDATE ont_identity SET metadata = ?, updated_at = ? WHERE id = ?",
                    (json.dumps(metadata, ensure_ascii=False), now, identity_id),
                )
                ai.commit()
                created = True
            else:
                identity_id = ident["id"]
        finally:
            ai.close()

        status = self._l4_status(contract_id)
        return {
            "contract_id": contract_id,
            "identity_id": identity_id,
            "contract_no": contract_no,
            "canonical_key": canonical,
            "status": status,
            "created": created,
        }

    # --- 查询 ---
    def resolve(self, contract_no: str) -> Optional[int]:
        """按合同编号解析 identity_id（alias 原始号 → canonical 兜底）。

        CWA：未登记返回 None（不抛异常，调用方据此拒绝操作）。
        """
        canonical = canonical_contract_no(contract_no)
        if not canonical:
            return None
        ai = self._ai_kb()
        try:
            domain_id = self._domain_id(ai)
            # 1) alias 精确（原始编号）
            row = ai.execute(
                "SELECT identity_id FROM ont_identity_alias "
                "WHERE source_system = ? AND source_key = ?",
                (SOR, contract_no),
            ).fetchone()
            if row is not None:
                return int(row[0])
            # 2) canonical 兜底（规范化编号）
            ident = self._find_identity(ai, domain_id, canonical)
            return ident["id"] if ident else None
        finally:
            ai.close()

    def get_identity(self, contract_no: str) -> Optional[Dict[str, Any]]:
        """返回 ont_identity 完整行（含反序列化 metadata）；未登记 None。"""
        identity_id = self.resolve(contract_no)
        if identity_id is None:
            return None
        ai = self._ai_kb()
        try:
            row = ai.execute(
                "SELECT * FROM ont_identity WHERE id = ?", (identity_id,)
            ).fetchone()
            if row is None:
                return None
            item = dict(row)
            if isinstance(item.get("metadata"), str):
                try:
                    item["metadata"] = json.loads(item["metadata"])
                except json.JSONDecodeError:
                    pass
            return item
        finally:
            ai.close()

    def is_registered(self, contract_no: str) -> bool:
        return self.resolve(contract_no) is not None

    # --- L4 状态辅助 ---
    def _l4_status(self, contract_id: int) -> Optional[str]:
        from repository.db import Repository
        with Repository(self.db_path) as repo:
            row = repo.get_contract_row(contract_id)
            return row["status"] if row else None

    def sync_metadata(
        self,
        contract_id: int,
        *,
        status: Optional[str] = None,
        fields: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """把 L4 最新状态/字段同步到 L2 metadata（保留 applied_changes）。

        供 connector/CLI 在写回后主动对齐；不存在 identity 时返回 None。
        """
        from repository.db import Repository

        with Repository(self.db_path) as repo:
            row = repo.get_contract_row(contract_id)
            if row is None:
                return None
            contract_no = row["contract_no"] or ""
        identity_id = self.resolve(contract_no)
        if identity_id is None:
            return None

        ai = self._ai_kb()
        try:
            ident = ai.execute(
                "SELECT metadata FROM ont_identity WHERE id = ?", (identity_id,)
            ).fetchone()
            md = {}
            if ident and ident["metadata"]:
                try:
                    md = json.loads(ident["metadata"])
                except json.JSONDecodeError:
                    md = {}
            if status is not None:
                md["status"] = status
            if fields:
                md.update(fields)
            now = ai.get_now()
            ai.execute(
                "UPDATE ont_identity SET metadata = ?, updated_at = ? WHERE id = ?",
                (json.dumps(md, ensure_ascii=False), now, identity_id),
            )
            ai.commit()
            return md
        finally:
            ai.close()

    def list_registered(self) -> List[Dict[str, Any]]:
        """列出全部已登记运营对象（L2 视角，含 metadata）。"""
        ai = self._ai_kb()
        try:
            domain_id = self._domain_id(ai)
            rows = ai.execute(
                "SELECT * FROM ont_identity "
                "WHERE domain_id = ? AND object_type = ? ORDER BY id",
                (domain_id, OBJECT_TYPE),
            ).fetchall()
            out = []
            for r in rows:
                item = dict(r)
                if isinstance(item.get("metadata"), str):
                    try:
                        item["metadata"] = json.loads(item["metadata"])
                    except json.JSONDecodeError:
                        pass
                out.append(item)
            return out
        finally:
            ai.close()
