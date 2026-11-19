"""编排：读单据 → R1（ONES 实时）→ R2（概算卡片）→ 增强核查章节。

只读：不改任何 OA/ONES/BDMS 数据；失败降级不中断。
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Dict, List, Optional

from .oa_form import OrderForm, OrderFormError, parse_order_form
from .ones_obigation import R1Result, ObligationError, check_obligations
from .estimate import R2Result, check_estimate
from .verdict import render_enhance


def _r1_degraded(r1: R1Result) -> bool:
    """R1 未给出有效结论（verdict=未知）即视为数据源降级（fail-closed）。

    2026-11-19 实测缺陷：ONES 查询层整体失效（Chrome 关闭「允许 Apple 事件中的
    JavaScript」）时 ``project_by_code`` 全返回 None → R1 静默变「未知」，
    但 ``degraded`` 为空 → 备注无 ⚠️ 降级警告，违反「数据源不可用不得当作
    正常结果」红线。故：verdict=未知 必须显式降级，不得当作正常结论提交。
    """
    return r1.verdict == "未知"


def run_enhance(
    *,
    request_id: str,
    raw_dir: Path,
    storage_state: Optional[Path] = None,
    project_codes: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """端到端编排（只读）。

    Returns:
        {"request_id", "form", "r1", "r2", "markdown", "degraded": [...]}
    """
    degraded: List[str] = []

    form = parse_order_form(raw_dir, request_id)

    # R1：ONES 实时履约义务
    try:
        r1 = check_obligations(
            end_user=form.end_user,
            product_codes=form.product_codes,
            project_codes=project_codes or [],
        )
    except ObligationError as exc:
        r1 = R1Result()
        r1.missing.append("r1_error: %s" % exc)
        r1.verdict = "未知"
    if _r1_degraded(r1):
        degraded.append("R1")

    # R2：概算一致性
    r2 = R2Result(billid=form.estimate_billid)
    if not form.estimate_billid:
        r2.skipped = "no_billid"
        r2.missing.append("本单未填概算卡片 billid")
        r2.verdict = "未知"
        degraded.append("R2")
    else:
        r2 = check_estimate(billid=form.estimate_billid, items=form.items,
                            storage_state=storage_state)
        if r2.skipped:
            degraded.append("R2")

    md = render_enhance(form, r1, r2)
    return {
        "request_id": request_id,
        "form": form.to_dict(),
        "r1": r1.to_dict(),
        "r2": r2.to_dict(),
        "markdown": md,
        "degraded": degraded,
    }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="OA 销售合同审查增强（只读：履约义务+概算）")
    ap.add_argument("--requestid", required=True, help="OA requestid（如 886377）")
    ap.add_argument("--raw-dir", required=True, help="oa_workflow_ones.py --capture 的 raw 根")
    ap.add_argument("--storage-state", default=None, help="Playwright storage_state（可空）")
    ap.add_argument("--project-codes", nargs="*", default=None, help="SSXM 编码（可空，空则 BDMS 定位）")
    ap.add_argument("--out", default=None, help="Markdown 输出路径（默认 stdout）")
    args = ap.parse_args(argv)

    try:
        result = run_enhance(
            request_id=args.requestid,
            raw_dir=Path(args.raw_dir),
            storage_state=Path(args.storage_state) if args.storage_state else None,
            project_codes=args.project_codes,
        )
    except OrderFormError as exc:
        print("❌ %s" % exc)
        return 2

    md = result["markdown"]
    if args.out:
        Path(args.out).write_text(md, encoding="utf-8")
        print("✅ 增强核查已写入 %s（降级项: %s）" % (args.out, result["degraded"] or "无"))
    else:
        print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
