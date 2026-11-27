"""R1b — 历史签约项目/合同交付问题盘点（只读）。

需求来源：Rex 2026-11-24「履约义务查找的重点是盘点历史签约项目/合同是否有
合同风险或缺失条款引起的交付问题（如，异常项目、未按合同约定完成项目交付验收）」。

数据源（单一权威，只读）：BDMS `dr_sheet_row` 月度快照
  - sheet=`异常项目`(17177 行) — 字段 `销售合同编号`/`异常项目-类别`/`项目异常内容`/
    `项目验收状态`/`状态`/`合同验收条款`
  - sheet=`签约`(17181 行)   — 字段 `履约项统计状态（即，财报-交付/确收状态）` /
    `项目验收状态（即，财报-验收状态）` / `异常项目对比`
  - sheet=`验收交接`          — 字段 `合同编号`/`是否合格`/`截至目前全部/部分验收`

判定（fail-closed，不伪造）：
  异常 = 命中「异常项目」表且 `异常项目-类别` 非空；或状态含 `交付异常`/`验收异常`
  关注 = 状态含 `应交未交`/`应验未验`；或验收交接 `是否合格=否`；或仅命中异常项目表
  正常 = 以上皆无
  库不可达 → degraded（显式报错，不静默当「无异常」）
"""
from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

_BDMS_DB_CANDIDATES = (
    "L4-proprietary/components/bdms/data/bdms.db",
)
_HOME_DB = "~/.openclaw/data/bdms.db"

_TABLE = "dr_sheet_row"
_SHEET_ABNORMAL = "异常项目"
_SHEET_SIGNED = "签约"
_SHEET_ACCEPT = "验收交接"

# 交付状态枚举（BDMS「履约项统计状态」列取值）
_ABNORMAL_STATES = {"2：应交未交", "3：交付异常", "5：应验未验", "6：验收异常"}
_SEVERE_KEYWORDS = ("交付异常", "验收异常")
_ATTENTION_KEYWORDS = ("应交未交", "应验未验")


class HistoryDeliveryError(RuntimeError):
    """历史交付盘点失败（显式报错，不静默伪造）。"""


@dataclass
class DeliveryIssue:
    sheet: str
    contract_no: str
    project_code: str
    end_user: str
    issue_type: str
    level: str            # 异常 | 关注
    status: str
    detail: str
    source_field: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sheet": self.sheet,
            "contract_no": self.contract_no,
            "project_code": self.project_code,
            "end_user": self.end_user,
            "issue_type": self.issue_type,
            "level": self.level,
            "status": self.status,
            "detail": self.detail,
            "source_field": self.source_field,
        }


# verdict 三态：正常 | 关注 | 异常 | 未收录（fail-closed：查无记录 ≠ 正常）
VERDICT_NORMAL = "正常"
VERDICT_UNMATCHED = "未收录"


@dataclass
class DeliveryResult:
    issues: List[DeliveryIssue] = field(default_factory=list)
    verdict: str = VERDICT_NORMAL
    queried_at: str = ""
    missing: List[str] = field(default_factory=list)
    data_source: str = "BDMS dr_sheet_row（202606 快照，只读）"
    match_basis: str = ""      # contract_no | end_user | none
    matched_rows: int = 0      # 快照中命中的行数（0 = 未收录）

    def to_dict(self) -> Dict[str, Any]:
        return {
            "issues": [i.to_dict() for i in self.issues],
            "verdict": self.verdict,
            "queried_at": self.queried_at,
            "missing": list(self.missing),
            "data_source": self.data_source,
            "match_basis": self.match_basis,
            "matched_rows": self.matched_rows,
        }


def _bdms_path() -> Optional[str]:
    """逐层向上找 BDMS 库（只读）。"""
    # 从组件目录向上找 workspace 根
    cur = os.path.dirname(os.path.abspath(__file__))
    for _ in range(10):
        for rel in _BDMS_DB_CANDIDATES:
            p = os.path.join(cur, rel)
            if os.path.exists(p):
                return p
        nxt = os.path.dirname(cur)
        if nxt == cur:
            break
        cur = nxt
    home = os.path.expanduser(_HOME_DB)
    return home if os.path.exists(home) else None


def _rows(con: sqlite3.Connection, sheet: str) -> List[Dict[str, Any]]:
    cur = con.cursor()
    cur.execute("SELECT data FROM %s WHERE sheet=?" % _TABLE, (sheet,))
    out: List[Dict[str, Any]] = []
    for (data,) in cur.fetchall():
        try:
            out.append(json.loads(data))
        except json.JSONDecodeError:
            continue
    return out


def _norm_contract_no(s: Any) -> str:
    return str(s or "").strip()


def _norm_end_user(s: Any) -> str:
    return str(s or "").strip()


def _issue_from_abnormal(row: Dict[str, Any]) -> Optional[DeliveryIssue]:
    cat = str(row.get("异常项目-类别") or "").strip()
    content = str(row.get("项目异常内容") or "").strip()
    status = str(row.get("状态") or "").strip()
    level = "异常" if (cat or any(k in status for k in _SEVERE_KEYWORDS)) else "关注"
    return DeliveryIssue(
        sheet=_SHEET_ABNORMAL,
        contract_no=_norm_contract_no(row.get("销售合同编号")),
        project_code=_project_code(row),
        end_user=_norm_end_user(row.get("最终用户名称") or row.get("客户名称")),
        issue_type=("异常项目-%s" % cat) if cat else "异常项目",
        level=level,
        status=status,
        detail=content or (str(row.get("异常影响情况") or "").strip()),
        source_field="异常项目-类别" if cat else "所属项目",
    )


def _project_code(row: Dict[str, Any]) -> str:
    proj = str(row.get("所属项目") or "")
    if "SSXM-" in proj:
        start = proj.index("SSXM-")
        seg = proj[start:].split("】")[0]
        return seg.strip()
    return str(row.get("项目编号") or "").strip()


def _issue_from_signed(row: Dict[str, Any]) -> Optional[DeliveryIssue]:
    st = str(row.get("履约项统计状态（即，财报-交付/确收状态）") or "").strip()
    accept = str(row.get("项目验收状态（即，财报-验收状态）") or "").strip()
    issue_type = ""
    level = ""
    if st in _ABNORMAL_STATES:
        label = st.split("：", 1)[-1]
        issue_type = label
        level = "异常" if any(k in label for k in _SEVERE_KEYWORDS) else "关注"
    elif accept and ("异常" in accept or "未验" in accept):
        issue_type = accept
        level = "异常" if "异常" in accept else "关注"
    if not issue_type:
        return None
    return DeliveryIssue(
        sheet=_SHEET_SIGNED,
        contract_no=_norm_contract_no(row.get("统计合同编号") or row.get("销售合同编号")),
        project_code=str(row.get("统计项目编号") or row.get("项目编号") or "").strip(),
        end_user=_norm_end_user(row.get("最终用户名称") or row.get("客户名称")),
        issue_type=issue_type,
        level=level,
        status=st or accept,
        detail=str(row.get("异常项目对比") or "").strip(),
        source_field="履约项统计状态" if st in _ABNORMAL_STATES else "项目验收状态",
    )


def _issue_from_accept(row: Dict[str, Any]) -> Optional[DeliveryIssue]:
    qualified = str(row.get("是否合格") or "").strip()
    partial = str(row.get("截至目前全部/部分验收") or "").strip()
    if qualified == "否":
        return DeliveryIssue(
            sheet=_SHEET_ACCEPT,
            contract_no=_norm_contract_no(row.get("合同编号") or row.get("合同编号1")),
            project_code="",
            end_user=_norm_end_user(row.get("客户名称")),
            issue_type="验收不合格",
            level="异常",
            status=qualified,
            detail=str(row.get("财务反馈") or "").strip(),
            source_field="是否合格",
        )
    if partial and "部分" in partial:
        return DeliveryIssue(
            sheet=_SHEET_ACCEPT,
            contract_no=_norm_contract_no(row.get("合同编号") or row.get("合同编号1")),
            project_code="",
            end_user=_norm_end_user(row.get("客户名称")),
            issue_type="部分验收未完成",
            level="关注",
            status=partial,
            detail="",
            source_field="截至目前全部/部分验收",
        )
    return None


def check_history_delivery(
    *,
    contract_no: str = "",
    end_user: str = "",
) -> DeliveryResult:
    """盘点历史交付问题（只读）。

    Args:
        contract_no: OA/合同编号（XSZS…，优先匹配）。
        end_user: 最终用户名称（兜底键）。Rex 2026-11-27：合同编号于归档时
            生成，OA 审核阶段常为空，故按最终用户匹配是正常入口。
    """
    result = DeliveryResult(
        queried_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )
    db = _bdms_path()
    if db is None:
        raise HistoryDeliveryError("未找到 BDMS 库（历史交付盘点不可用）")

    basis = ""
    cn = _norm_contract_no(contract_no)
    eu = _norm_end_user(end_user)
    if cn:
        basis = "contract_no"
    elif eu:
        basis = "end_user"
    if not basis:
        result.missing.append("no_key（contract_no/end_user 均空）")
        result.verdict = "未知"
        return result
    result.match_basis = basis

    seen_keys: set = set()
    con = sqlite3.connect("file:%s?mode=ro" % db, uri=True)
    try:
        for sheet, extractor in ((_SHEET_ABNORMAL, _issue_from_abnormal),
                                 (_SHEET_SIGNED, _issue_from_signed),
                                 (_SHEET_ACCEPT, _issue_from_accept)):
            try:
                rows = _rows(con, sheet)
            except sqlite3.Error as exc:
                result.missing.append("sheet_%s: %s" % (sheet, exc))
                continue
            for row in rows:
                if basis == "contract_no":
                    row_cn = _norm_contract_no(
                        row.get("销售合同编号") or row.get("统计合同编号")
                        or row.get("合同编号") or row.get("合同编号1"))
                    if not row_cn or row_cn != cn:
                        continue
                else:
                    row_eu = _norm_end_user(row.get("最终用户名称") or row.get("客户名称"))
                    if not row_eu or eu not in row_eu:
                        continue
                result.matched_rows += 1
                issue = extractor(row)
                if issue is not None:
                    # 去重：同 (sheet, level, issue_type, status, detail) 只留一条
                    # （BDMS 按履约项一行行存，同一异常会重复多行）
                    key = (issue.sheet, issue.level, issue.issue_type,
                           issue.status, issue.detail[:120])
                    if key not in seen_keys:
                        seen_keys.add(key)
                        result.issues.append(issue)
    finally:
        con.close()

    if result.matched_rows == 0:
        # fail-closed：查无记录不得当作「无异常」
        result.verdict = VERDICT_UNMATCHED
        result.missing.append(
            "bdms_unmatched（basis=%s, key=%s）：快照中无该合同/用户记录" % (
                basis, cn or eu))
        return result

    levels = {i.level for i in result.issues}
    if "异常" in levels:
        result.verdict = "异常"
    elif "关注" in levels:
        result.verdict = "关注"
    else:
        result.verdict = VERDICT_NORMAL
    return result
