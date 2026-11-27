"""一条链编排：发现 757 待办 → 捕获 → R1/R2 → 固定核查 → 标准审批备注。

只读：不提交/不审批/不退回/不转发；OA 写操作一律人工闸。
合同原文来源（按优先级）：
  1) 显式 ``--contract-file``（人工指定，最高优先）；
  2) **自动**从该单据 OA 表单附件下载（``attachment.fetch_contract_text``，
     复用已建立会话）——2026-11-27 Rex 规则：审核阶段必须基于合同原文做
     L2 核查与 R3 条款拆解，不得再以「附件取不到」为由整体转人工。
两者皆无 → L2 三项 fail-closed 转人工。

用法（CLI）:
  contractctl oa-approval [--raw-dir <dir>] [--contract-file <docx/txt>]
                         [--out-dir <dir>] [--requestid <rid>] [--no-discover]
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .checks import CheckResult, parse_body_fields, run_fixed_checks
from .oa_form import OrderForm, OrderFormError, parse_order_form
from .remark import render_remark
from .runner import run_enhance
from .attachment import fetch_contract_text
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
    history_delivery: Dict[str, Any] = field(default_factory=dict)
    clauses: Dict[str, Any] = field(default_factory=dict)
    risk_points: Dict[str, Any] = field(default_factory=dict)
    remark: str = ""
    degraded: List[str] = field(default_factory=list)
    error: Optional[str] = None
    attachment: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "form": self.form.to_dict() if self.form else None,
            "checks": [c.to_dict() for c in self.checks],
            "r1": self.r1,
            "r2": self.r2,
            "history_delivery": self.history_delivery,
            "clauses": self.clauses,
            "risk_points": self.risk_points,
            "remark": self.remark,
            "degraded": self.degraded,
            "error": self.error,
            "attachment": self.attachment,
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


def _party_mixing_warnings(pa: Dict[str, Any], pb: Dict[str, Any]) -> list:
    """检测主体字段跨方串用（防御性：L3 修好前会命中，修好后应为空）。

    口径：名称不同但 address/email/bank/account 任一字段两方同值 → 判定疑似串用。
    L4 只标注不修正（L4→L3 反向依赖禁止），交人工以原文核对。
    """
    if not pa or not pb or pa.get("name") == pb.get("name"):
        return []
    shared = [k for k in ("address", "email", "bank", "account")
              if pa.get(k) and pa.get(k) == pb.get(k)]
    if not shared:
        return []
    return ["主体字段疑似串用（上游抽取限制）：甲方/乙方 %s 字段相同=%r；"
            "仅作参考，须人工以原文核对" % (
                "/".join(shared),
                {k: (pa.get(k) or "")[:40] for k in shared})]


def _build_contract_review(contract_text: Optional[str]) -> Dict[str, Any]:
    """合同原文 → 条款拆解 + 风险点（L3 受控库，只读纯计算）。

    失败不中断主链：返回空结构 + ``degraded`` 原因（fail-closed）。
    """
    out: Dict[str, Any] = {
        "clauses": {"clauses": [], "missing_required": [],
                    "unsupported_categories": [], "stats": {}},
        "risk_points": {"points": [], "summary": {}, "overall_risk": "unknown",
                        "degraded": [], "rule_set_version": ""},
        "degraded": [],
        "warnings": [],
    }
    if not contract_text or not contract_text.strip():
        out["degraded"].append("NO_CONTRACT_TEXT")
        return out
    try:
        from contract_review.digitize import DigitizedText
        from contract_review import clause_extract as cex
        from contract_review import risk_points as rpt

        dig = DigitizedText(full_text=contract_text, method="txt")
        cl = cex.extract_clauses(contract_text)
        rp = rpt.build_risk_points(dig)
        out["clauses"] = cl
        out["risk_points"] = rp

        out["warnings"].extend(_party_mixing_warnings(cl.get("party_a") or {},
                                                      cl.get("party_b") or {}))
        if rp.get("degraded"):
            out["degraded"].extend(rp["degraded"])
        if cl.get("stats", {}).get("missing_required"):
            # 条款缺失不阻断审批，仅提示（low/missing）
            pass
    except Exception as exc:  # noqa: BLE001 — 单张失败不中断整批
        out["degraded"].append("CONTRACT_REVIEW: %s: %s" % (type(exc).__name__, exc))
    return out


def _render_contract_review_md(request_id: str, cr: Dict[str, Any],
                               contract_ref: str) -> str:
    """合同全文条款/风险点 Markdown 产物（含 ADR-035 溯源与质量信号）。"""
    from contract_review import report as rep

    clauses = cr.get("clauses") or {}
    rp = cr.get("risk_points") or {}
    _today = datetime.now().strftime("%Y-%m-%d")
    lines = [
        "# 合同全文审查（条款拆解 + 风险点）— %s" % request_id,
        "",
        "> 生成：%s；契约版本：ADR-035；归属：OA workflowid=757 单据 %s；"
        "数据基准：合同原文（用户提供）＋ L3 contract-management CHECK_RULES"
        "（rule_set=%s）" % (_today, request_id, rp.get("rule_set_version") or "未知"),
        "",
        "## 0. 溯源链",
        "- 来源：合同原文 `%s`（本地文件，不外发）" % contract_ref,
        "- 规则：L3 `contract_parser`（28 类条款）/ `risk_engine`（22 条 CHECK_RULES）"
        "＋ 必备条款缺失维度",
        "- 结论：条款 %s 类；风险点 %s 条（overall=%s）" % (
            (clauses.get("stats") or {}).get("extracted", "?"),
            len(rp.get("points") or []), rp.get("overall_risk", "unknown")),
        "",
        "## 1. 条款拆解",
        "",
        "### 1.1 已抽出条款",
        "",
        rep._clauses_table_md(clauses.get("clauses") or []),
        "",
        "### 1.2 必备条款缺失",
        "",
    ]
    missing = clauses.get("missing_required") or []
    if missing:
        lines.append("| 类别 | 法条 | 说明 |")
        lines.append("|---|---|---|")
        for m in missing:
            lines.append("| %s | %s | %s |" % (
                m.get("category", ""), m.get("law", "") or "-",
                m.get("description", "")))
    else:
        lines.append("> 未发现必备条款缺失（无提取器的类别不计入，见 §1.3）。")
    lines += ["", "### 1.3 未覆盖类别（无提取器，不参与缺失判定）", ""]
    uns = clauses.get("unsupported_categories") or []
    lines.append("> %s" % ("、".join(uns) if uns else "（无）"))
    lines += ["", "## 2. 风险点", "", rep._risk_points_table_md(rp.get("points") or []), ""]
    dg = cr.get("degraded") or []
    lines += ["## 3. 质量信号", ""]
    lines.append("- 整体风险：%s" % rp.get("overall_risk", "unknown"))
    lines.append("- 汇总：%s" % json.dumps(rp.get("summary") or {}, ensure_ascii=False))
    for w in (cr.get("warnings") or []):
        lines.append("- ⚠️ 抽取质量提示：%s" % w)
    if dg:
        lines.append("- ⚠️ 数据源降级：%s（结论可能过期，需人工复核）" % "、".join(dg))
    else:
        lines.append("- 数据源状态：全部可用，结论可复现")
    lines.append("- 法条均回溯 L3 受控库；条款缺失统一 low/missing，不阻断审批。")
    # ADR-035 时间戳（fail-closed 门禁要求）
    lines += [
        "",
        "> 【已验证 %s｜L3 contract-management 受控规则库】条款拆解 %s 类／"
        "风险点 %d 条（overall=%s，rule_set=%s）；证据=合同原文本地文件"
        "（不外发）。" % (
            _today, (clauses.get("stats") or {}).get("extracted", "?"),
            len(rp.get("points") or []), rp.get("overall_risk", "unknown"),
            rp.get("rule_set_version") or "未知"),
    ]
    return "\n".join(lines) + "\n"


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
            res.history_delivery = enhanced.get("history_delivery") or {}
            res.degraded = enhanced.get("degraded") or []

            # 4) 固定核查（L1 表单 + L2 原文）
            #    原文来源：显式 --contract-file > OA 表单附件自动下载
            body = _read_body(raw_dir, rid)
            contract_source = ""
            ctext = _read_contract_text(contract_file)
            if ctext:
                contract_source = str(contract_file)
            else:
                att = fetch_contract_text(raw_dir, rid, out_dir,
                                          storage_state=storage_state)
                res.attachment = att
                if att.get("found"):
                    ctext = att.get("text")
                    contract_source = att.get("path") or ""
                elif att.get("error"):
                    res.degraded = sorted(set(res.degraded) | {"ATTACHMENT"})
            res.checks = run_fixed_checks(form, body, ctext)

            # 4b) 合同原文 → 条款拆解 + 风险点（Rex 2026-11-24/11-27）
            cr = _build_contract_review(ctext)
            res.clauses = cr.get("clauses") or {}
            res.risk_points = cr.get("risk_points") or {}
            if cr.get("degraded"):
                res.degraded = sorted(set(res.degraded) | set(cr["degraded"]))
            if ctext:
                contract_ref = contract_source or "（未知来源）"
                (out_dir / ("contract-review-%s.md" % rid)).write_text(
                    _render_contract_review_md(rid, cr, contract_ref), encoding="utf-8")
                with open(out_dir / ("clauses-%s.json" % rid), "w", encoding="utf-8") as fh:
                    json.dump({"request_id": rid, **cr}, fh, ensure_ascii=False, indent=2)

            # 5) 标准备注
            res.remark = render_remark(form, res.checks, res.r1, res.r2,
                                       degraded=res.degraded,
                                       history_delivery=res.history_delivery,
                                       clauses=res.clauses,
                                       risk_points=res.risk_points,
                                       contract_text=bool(ctext),
                                       contract_source=contract_source)
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
        "risk_high": sum(1 for r in results
                         if (r.risk_points or {}).get("overall_risk") == "high"),
        "risk_medium": sum(1 for r in results
                           if (r.risk_points or {}).get("overall_risk") == "medium"),
        "risk_low": sum(1 for r in results
                        if (r.risk_points or {}).get("overall_risk") == "low"),
        "with_contract_text": sum(1 for r in results if r.clauses),
        "with_attachment_auto": sum(1 for r in results
                                    if (r.attachment or {}).get("found")),
        "attachment_failed": sum(1 for r in results
                                 if (r.attachment or {}).get("error")),
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
