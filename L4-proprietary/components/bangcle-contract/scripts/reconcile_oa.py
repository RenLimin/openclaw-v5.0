#!/usr/bin/env python3
"""reconcile_oa — OA 审批流对账可调度 runner（P4.4，详设 §5）。

用途：被 cron 每日调度（也可人工直接跑），只读比对
「L4 本地合同状态」与「泛微 OA 真实审批流状态」，输出四态偏差报告。

数据链（全部只读）：
    contracts.oa_billid
      → CubeClient.get_contract(billid).main_fields["合同审批流程→"] = requestid
      → ApprovalLogReader.read_approval_chain(requestid) = 真实审批链
      → reconcile() 四态比对（in_sync / oa_ahead / local_ahead / oa_unknown）

保证：
- 全程只读，不写任何业务表、不触发 OA 写操作；
- 单个合同失败（无 billid / 读不到卡片 / 读不到审批链）不中断整批，
  分别降级标记（no_billid / no_requestid / oa_unknown）；
- 产出两份落盘：
    memory/oa-reconcile-latest.json   最新机读结果（供其他任务/审计）
  并向 stdout 打印 JSON 摘要（供 cron run history / 人工查看）。

用法：
    python3 scripts/reconcile_oa.py                 # 全量对账所有合同
    python3 scripts/reconcile_oa.py --contract-id 5 # 只对单个合同
    python3 scripts/reconcile_oa.py --quiet         # 只落盘，stdout 精简
退出码：0=执行成功（即使有偏差）；2=整体执行异常（非单合同降级）。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from datetime import datetime

# 组件根：scripts/ -> bangcle-contract/
HERE = os.path.dirname(os.path.abspath(__file__))
COMPONENT_ROOT = os.path.dirname(HERE)
if COMPONENT_ROOT not in sys.path:
    sys.path.insert(0, COMPONENT_ROOT)

# workspace 根（memory/ 在其下）：components -> L4-proprietary -> workspace
WORKSPACE_ROOT = os.path.abspath(
    os.path.join(COMPONENT_ROOT, "..", "..", "..")
)

# OA 合同卡片中保存审批 requestid 的主字段显示名
REQUESTID_FIELD = "合同审批流程→"

# 落盘报告路径
LATEST_REPORT = os.path.join(
    WORKSPACE_ROOT, "memory", "oa-reconcile-latest.json"
)


def _resolve_requestid(cube, billid: str):
    """billid → requestid，返回 (requestid|None, error|None)。只读。"""
    try:
        card = cube.get_contract(billid)
    except Exception as exc:  # noqa: BLE001 - 单合同降级，不中断整批
        return None, "card_read_failed: %s" % type(exc).__name__
    rid = (card.main_fields or {}).get(REQUESTID_FIELD)
    rid = (rid or "").strip()
    if not rid:
        return None, "requestid_field_missing"
    return rid, None


def run_reconcile(contract_id=None, *, reader=None, cube=None):
    """执行对账，返回 (report_dict, per_item_statuses)。纯只读。

    reader/cube 可注入 fake（测试用）。
    """
    from repository.db import Repository, default_db_path
    from services.oa.cube import CubeClient
    from contract_review.ontology_bridge.reconcile import reconcile

    cube = cube if cube is not None else CubeClient()
    started = datetime.now().isoformat()

    with Repository(default_db_path()) as repo:
        if contract_id is not None:
            row = repo.get_contract_row(int(contract_id))
            contracts = [row] if row is not None else []
        else:
            contracts = repo.list_contracts()

    # 第一阶段：解析每个合同的 billid → requestid
    # plan: [{contract_id, contract_no, local_state, billid, requestid?, skip?, skip_reason?}]
    plan = []
    for row in contracts:
        item = {
            "contract_id": row.get("id"),
            "contract_no": row.get("contract_no"),
            "local_state": row.get("status"),
            "billid": (row.get("oa_billid") or "").strip(),
        }
        if not item["billid"]:
            item["skip"] = True
            item["skip_reason"] = "no_billid"
        else:
            rid, err = _resolve_requestid(cube, item["billid"])
            if rid is None:
                item["skip"] = True
                item["skip_reason"] = err or "no_requestid"
            else:
                item["requestid"] = rid
        plan.append(item)

    # 第二阶段：对成功解析出 requestid 的合同批量只读对账
    active = [p for p in plan if not p.get("skip")]
    requestids = [p["requestid"] for p in active]
    local_states = {
        p["requestid"]: (p["local_state"] or "") for p in active
    }
    diffs = reconcile(
        requestids, local_states=local_states, reader=reader
    )
    diff_by_rid = {d.requestid: d for d in diffs}

    # 汇总每个合同的最终状态
    items = []
    counts = {
        "in_sync": 0, "oa_ahead": 0, "local_ahead": 0,
        "oa_unknown": 0, "no_billid": 0, "no_requestid": 0,
    }
    for p in plan:
        if p.get("skip"):
            kind = "no_billid" if p["skip_reason"] == "no_billid" else "no_requestid"
            counts[kind] = counts.get(kind, 0) + 1
            items.append({
                "contract_id": p["contract_id"],
                "contract_no": p["contract_no"],
                "billid": p["billid"],
                "requestid": None,
                "local_state": p["local_state"],
                "oa_state": None,
                "kind": kind,
                "detail": p["skip_reason"],
            })
            continue
        d = diff_by_rid.get(p["requestid"])
        kind = d.kind if d else "oa_unknown"
        counts[kind] = counts.get(kind, 0) + 1
        items.append({
            "contract_id": p["contract_id"],
            "contract_no": p["contract_no"],
            "billid": p["billid"],
            "requestid": p["requestid"],
            "local_state": p["local_state"],
            "oa_state": d.oa_state if d else "oa_unknown",
            "kind": kind,
        })

    report = {
        "generated_at": datetime.now().isoformat(),
        "started_at": started,
        "scope": "contract_id=%s" % contract_id if contract_id is not None else "all",
        "total_contracts": len(plan),
        "reconciled": len(active),
        "counts": counts,
        # 是否存在需要人工关注的偏差（in_sync 之外的任何态）
        "attention_required": [
            i for i in items if i["kind"] != "in_sync"
        ],
        "items": items,
    }
    return report


def write_report(report: dict) -> None:
    os.makedirs(os.path.dirname(LATEST_REPORT), exist_ok=True)
    tmp = LATEST_REPORT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, LATEST_REPORT)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="OA 审批流只读对账 runner")
    parser.add_argument("--contract-id", default=None, help="只对单个合同 id 对账")
    parser.add_argument("--quiet", action="store_true", help="精简 stdout")
    args = parser.parse_args(argv)

    try:
        report = run_reconcile(contract_id=args.contract_id)
    except Exception as exc:  # noqa: BLE001 - 整体异常：打印并返非零
        print(json.dumps({
            "status": "error",
            "error": type(exc).__name__,
            "message": str(exc),
            "trace": traceback.format_exc(),
        }, ensure_ascii=False))
        return 2

    write_report(report)

    if args.quiet:
        summary = {
            "generated_at": report["generated_at"],
            "total_contracts": report["total_contracts"],
            "reconciled": report["reconciled"],
            "counts": report["counts"],
            "attention": len(report["attention_required"]),
            "report": LATEST_REPORT,
        }
    else:
        summary = report
        summary["report_path"] = LATEST_REPORT
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
