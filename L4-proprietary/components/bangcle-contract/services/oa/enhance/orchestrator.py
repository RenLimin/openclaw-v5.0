"""一条链编排：发现 757 待办 → 捕获 → R1/R2 → 固定核查 → 标准审批备注。

只读：不提交/不审批/不退回/不转发；OA 写操作一律人工闸。
合同原文为可选输入（``--contract-file``）；未提供时 L2 核查项 fail-closed 转人工。

用法（CLI）:
  contractctl oa-approval [--raw-dir <dir>] [--contract-file <docx/txt>]
                         [--out-dir <dir>] [--requestid <rid>] [--no-discover]
"""
from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .checks import CheckResult, parse_body_fields, run_fixed_checks
from .oa_form import OrderForm, OrderFormError, parse_order_form
from .remark import render_remark
from .runner import run_enhance
from .todo import TodoItem, discover_todos

def _ws_root() -> Path:
    """workspace 根（含 AGENTS.md），兼容权威源与 sandbox 副本两种层级。"""
    here = Path(__file__).resolve()
    for base in here.parents:
        if (base / "AGENTS.md").exists():
            return base
    return here.parents[6]


# oa_workflow_ones.py（ones-browser-export skill 脚本）
_DEFAULT_ONES_SCRIPT = (
    _ws_root() / "L4-proprietary" / "skills" / "ones-browser-export"
    / "scripts" / "oa_workflow_ones.py"
)


@dataclass
class ApprovalResult:
    """单张单据的编排结果。"""

    request_id: str
    form: Optional[OrderForm] = None
    checks: List[CheckResult] = field(default_factory=list)
    r1: Dict[str, Any] = field(default_factory=dict)
    r2: Dict[str, Any] = field(default_factory=dict)
    remark: str = ""
    degraded: List[str] = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "form": self.form.to_dict() if self.form else None,
            "checks": [c.to_dict() for c in self.checks],
            "r1": self.r1,
            "r2": self.r2,
            "remark": self.remark,
            "degraded": self.degraded,
            "error": self.error,
        }


def _capture(rid: str, raw_dir: Path, ones_script: Path) -> None:
    """调用 ``oa_workflow_ones.py --capture`` 落盘单据 raw。"""
    subprocess.run(
        [sys.executable, str(ones_script), "--capture", rid, "--raw-dir", str(raw_dir)],
        check=True,
    )


def _read_body(raw_dir: Path, rid: str) -> str:
    p = raw_dir / rid / "body.txt"
    if not p.exists():
        return ""
    return p.read_text(encoding="utf-8", errors="replace")


def _read_contract_text(path: Optional[Path]) -> Optional[str]:
    """读合同原文（txt/docx）；不支持的类型返回 None（转人工）。"""
    if not path or not path.exists():
        return None
    suffix = path.suffix.lower()
    if suffix == ".txt":
        return path.read_text(encoding="utf-8", errors="replace")
    if suffix in (".docx", ".doc"):
        try:
            from contract_review.digitize import digitize, DigitizeError
            dt = digitize(str(path), file_type="docx")
            return dt.full_text or None
        except Exception:  # noqa: BLE001
            return None
    if suffix == ".pdf":
        try:
            from contract_review.digitize import digitize
            dt = digitize(str(path), file_type="pdf")
            return dt.full_text or None
        except Exception:  # noqa: BLE001
            return None
    return None


def run_approval(
    *,
    raw_dir: Path,
    out_dir: Optional[Path] = None,
    request_ids: Optional[List[str]] = None,
    contract_file: Optional[Path] = None,
    storage_state: Optional[Path] = None,
    ones_script: Optional[Path] = None,
    discover: bool = True,
    workflow_id: str = "757",
) -> Dict[str, Any]:
    """端到端编排（只读）。

    Args:
        raw_dir: ``oa_workflow_ones.py --capture`` 的 raw 根。
        out_dir: 备注/报告输出目录（默认 raw_dir 同级 ``oa-approval``）。
        request_ids: 显式指定 requestid（``discover=False`` 时必填）。
        contract_file: 合同原文（可选；docx/pdf/txt）。
        storage_state: OA storage_state（发现待办用）。
        ones_script: ``oa_workflow_ones.py`` 路径。
        discover: 是否先发现 757 待办。
        workflow_id: 目标 workflowid。

    Returns:
        ``{"todos": [...], "results": [...], "summary": {...}, "out_dir": "..."}``
    """
    raw_dir = Path(raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    out_dir = Path(out_dir) if out_dir else raw_dir.parent / "oa-approval"
    out_dir.mkdir(parents=True, exist_ok=True)
    ones_script = Path(ones_script) if ones_script else _DEFAULT_ONES_SCRIPT

    # 1) 发现待办 / 显式 rid
    todos: List[TodoItem] = []
    if request_ids:
        todos = [TodoItem(request_id=r, request_name="", workflow_id=workflow_id) for r in request_ids]
    elif discover:
        todos = discover_todos(workflow_id, storage_state=storage_state)

    results: List[ApprovalResult] = []
    for t in todos:
        rid = t.request_id
        res = ApprovalResult(request_id=rid)
        try:
            # 2) 捕获单据（raw 缺失才抓）
            if not (raw_dir / rid / "xhrs.json").exists():
                _capture(rid, raw_dir, ones_script)

            # 3) 解析表单 + R1/R2
            form = parse_order_form(raw_dir, rid)
            res.form = form
            enhanced = run_enhance(
                request_id=rid,
                raw_dir=raw_dir,
                storage_state=storage_state,
            )
            res.r1 = enhanced["r1"]
            res.r2 = enhanced["r2"]
            res.degraded = enhanced.get("degraded") or []

            # 4) 固定核查（L1 表单 + L2 原文）
            body = _read_body(raw_dir, rid)
            ctext = _read_contract_text(contract_file)
            res.checks = run_fixed_checks(form, body, ctext)

            # 5) 标准备注
            res.remark = render_remark(form, res.checks, res.r1, res.r2, degraded=res.degraded)
            (out_dir / ("remark-%s.md" % rid)).write_text(res.remark, encoding="utf-8")
        except OrderFormError as exc:
            res.error = "OrderFormError: %s" % exc
        except Exception as exc:  # noqa: BLE001 — 单张失败不中断整批
            res.error = "%s: %s" % (type(exc).__name__, exc)
        results.append(res)

    summary = {
        "total": len(results),
        "block": sum(1 for r in results if any(c.level == "block" for c in r.checks)),
        "warn": sum(1 for r in results if any(c.level == "warn" for c in r.checks)),
        "manual": sum(1 for r in results if any(c.level == "manual" for c in r.checks)),
        "error": sum(1 for r in results if r.error),
    }
    payload = {
        "todos": [t.to_dict() for t in todos],
        "results": [r.to_dict() for r in results],
        "summary": summary,
        "out_dir": str(out_dir),
    }
    (out_dir / "approval-summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload
