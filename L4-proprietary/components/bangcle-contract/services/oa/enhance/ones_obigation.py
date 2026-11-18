"""R1 — 客户/最终用户履约义务核查（只读）。

数据源优先级（Rex 2026-11-18 拍板）：
  1. **ONES 实时**（GraphQL，主数据源）—— 任务 ``status.name`` 为实时状态
  2. BDMS 交付月报（202606 月度快照，**仅用于定位项目编码**，其聚合状态列不作结论）

判定（基于 ONES 实时任务状态）：
  正常 = 已完成 / 交付邮件已归档 / 客户确认版验收单 / 验收文件已归档
  提示 = 实施未开始 / 义务已拆分（项目整体未完成）
  异常 = 应交未交 / 交付异常 / 应验未验 / 验收异常 / 应结未结
"""
from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from . import ones_client

OBLIGATION_ISSUE_TYPE = "项目履约义务"

_NORMAL = ("已完成", "交付邮件已归档", "客户确认版验收单", "验收文件已归档")
_HINT = ("实施未开始", "义务已拆分")
_ABNORMAL = ("应交未交", "交付异常", "应验未验", "验收异常", "应结未结")

_BDMS_DB_CANDIDATES = (
    "L4-proprietary/components/bdms/data/bdms.db",
)
_BDMS_TABLE = "dr_sheet_row"


class ObligationError(RuntimeError):
    """R1 核查失败（显式报错，不静默伪造）。"""


@dataclass
class ObligationRecord:
    project_code: str
    project_name: str
    project_status: str
    task_number: str
    task_name: str
    status: str
    owner: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_code": self.project_code,
            "project_name": self.project_name,
            "project_status": self.project_status,
            "task_number": self.task_number,
            "task_name": self.task_name,
            "status": self.status,
            "owner": self.owner,
        }


@dataclass
class ProjectObligations:
    project_code: str
    project_name: str
    project_status: str
    records: List[ObligationRecord] = field(default_factory=list)

    @property
    def statuses(self) -> List[str]:
        seen: List[str] = []
        for r in self.records:
            if r.status and r.status not in seen:
                seen.append(r.status)
        return seen

    @property
    def verdict(self) -> str:
        sts = {r.status for r in self.records}
        if sts & set(_ABNORMAL):
            return "异常"
        if sts & set(_HINT):
            return "提示"
        if sts & set(_NORMAL):
            return "正常"
        return "未知"


@dataclass
class R1Result:
    projects: List[ProjectObligations] = field(default_factory=list)
    verdict: str = "未知"
    queried_at: str = ""
    missing: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    data_source: str = "ONES 实时（GraphQL）+ BDMS 202606（仅项目编码定位）"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "projects": [
                {
                    "project_code": p.project_code,
                    "project_name": p.project_name,
                    "project_status": p.project_status,
                    "statuses": p.statuses,
                    "verdict": p.verdict,
                    "records": [r.to_dict() for r in p.records],
                }
                for p in self.projects
            ],
            "verdict": self.verdict,
            "queried_at": self.queried_at,
            "missing": list(self.missing),
            "notes": list(self.notes),
            "data_source": self.data_source,
        }


def _bdms_path() -> Optional[Path]:
    """逐层向上找 BDMS 库（只读定位用）。"""
    here = Path(__file__).resolve()
    for base in here.parents:
        for rel in _BDMS_DB_CANDIDATES:
            p = base / rel
            if p.exists():
                return p
    return None


def locate_project_codes(end_user: str, customer: str = "") -> List[str]:
    """用 BDMS 交付月报（202606 快照，只读）按最终用户/客户名定位 SSXM 项目编码。

    仅定位，不取状态（状态以 ONES 实时为准）。
    """
    db = _bdms_path()
    if db is None:
        raise ObligationError("未找到 BDMS 库（项目编码定位不可用）")
    codes: List[str] = []
    con = sqlite3.connect("file:%s?mode=ro" % db, uri=True)
    try:
        cur = con.cursor()
        cur.execute(
            "SELECT data FROM %s WHERE sheet='签约'" % _BDMS_TABLE
        )
        for (data,) in cur.fetchall():
            try:
                row = json.loads(data)
            except json.JSONDecodeError:
                continue
            eu = str(row.get("最终用户名称") or "")
            cu = str(row.get("客户名称") or "")
            if end_user and end_user not in eu:
                continue
            if customer and customer not in cu:
                continue
            for key in ("项目编号", "统计项目编号"):
                code = str(row.get(key) or "").strip()
                if code.startswith("SSXM-") and code not in codes:
                    codes.append(code)
    finally:
        con.close()
    return codes


def _query_project(code: str) -> Optional[ProjectObligations]:
    proj = ones_client.project_by_code(code)
    if not proj:
        return None
    uuid = proj.get("uuid") or ""
    name = proj.get("name") or ""
    try:
        status = ones_client.project_status(uuid)
    except Exception:
        status = ""
    tasks = ones_client.project_tasks(uuid)
    records: List[ObligationRecord] = []
    for t in tasks:
        if (t.get("issueType") or {}).get("name") != OBLIGATION_ISSUE_TYPE:
            continue
        records.append(
            ObligationRecord(
                project_code=code,
                project_name=name,
                project_status=status,
                task_number=str(t.get("number") or ""),
                task_name=str(t.get("name") or ""),
                status=str((t.get("status") or {}).get("name") or ""),
                owner=str((t.get("owner") or {}).get("name") or ""),
            )
        )
    return ProjectObligations(
        project_code=code, project_name=name,
        project_status=status, records=records,
    )


def check_obligations(
    *,
    end_user: str,
    customer: str = "",
    product_codes: Sequence[str] = (),
    project_codes: Sequence[str] = (),
) -> R1Result:
    """R1 主入口：核查客户/最终用户履约义务（ONES 实时）。

    Args:
        end_user: 最终用户名称（主）。
        customer: 客户名称（辅，可空）。
        product_codes: 本单产品编码（仅记录，用于报告标注命中）。
        project_codes: 已知 SSXM 编码；为空则用 BDMS 定位。
    """
    result = R1Result(queried_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    codes = [c for c in project_codes if str(c).startswith("SSXM-")]
    if not codes:
        try:
            codes = locate_project_codes(end_user, customer)
        except ObligationError as exc:
            result.missing.append("bdms_locate: %s" % exc)
    if not codes:
        result.missing.append("project_not_found（end_user=%s）" % end_user)
        result.verdict = "未知"
        return result

    for code in codes:
        try:
            proj = _query_project(code)
        except Exception as exc:  # noqa: BLE001 - 单项目失败降级
            result.missing.append("ones_query: %s (%s)" % (code, exc))
            continue
        if proj is None:
            result.missing.append("ones_project_not_found: %s" % code)
            continue
        result.projects.append(proj)

    if not result.projects:
        result.verdict = "未知"
        return result

    order = {"异常": 3, "提示": 2, "正常": 1, "未知": 0}
    result.verdict = max(
        (p.verdict for p in result.projects), key=lambda v: order.get(v, 0)
    )
    if product_codes:
        result.notes.append(
            "本单产品编码 %s 已纳入核对范围（ONES 实时状态见上）"
            % ", ".join(product_codes)
        )
    return result
