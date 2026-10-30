#!/usr/bin/env python3
"""交付质量反馈记录器：把 Rex 的问题反馈追加到 feedback.jsonl（默认 open）。

用法：
  record.py --domain project --dimension data_fidelity --severity high \
            --target SSXM-2026-0525-1294 --finding "类型误标为合同" \
            [--root-cause ...] [--corrective-action ...] [--status open] \
            [--tags t1,t2] [--session key]
  无 --finding 时从 stdin 读取。\n  默认记录后立即触发 review（事件驱动）；--no-review 仅记录。
"""
import argparse, json, sys, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FB = ROOT / "feedback.jsonl"
TZ = datetime.timezone(datetime.timedelta(hours=8))

VALID_DOMAIN = {"project", "contract", "product", "cross", "other"}
VALID_DIM = {"data_completeness", "data_fidelity", "calculation_logic",
             "missing_risk_analysis", "missing_context", "best_practice_gap",
             "sourcing", "format_presentation", "other"}
VALID_SEV = {"high", "medium", "low"}
VALID_STATUS = {"open", "corrected", "promoted", "wontfix"}


def next_id(now):
    day = now.strftime("%Y%m%d")
    n = 0
    if FB.exists():
        for line in FB.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("id", "").startswith(f"FB-{day}-"):
                n += 1
    return f"FB-{day}-{n+1:02d}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--domain", required=True, choices=sorted(VALID_DOMAIN))
    ap.add_argument("--dimension", required=True, choices=sorted(VALID_DIM))
    ap.add_argument("--severity", required=True, choices=sorted(VALID_SEV))
    ap.add_argument("--target", default="")
    ap.add_argument("--finding", default="")
    ap.add_argument("--root-cause", default="")
    ap.add_argument("--corrective-action", default="")
    ap.add_argument("--status", default="open", choices=sorted(VALID_STATUS))
    ap.add_argument("--reporter", default="gateway-owner")
    ap.add_argument("--session", default="")
    ap.add_argument("--tags", default="")
    ap.add_argument("--resolution", default="")
    ap.add_argument("--no-review", action="store_true", help="记录后不立即触发 review（批量导入用）")
    args = ap.parse_args()

    finding = args.finding.strip()
    if not finding:
        finding = sys.stdin.read().strip()
    if not finding:
        print("❌ finding 不能为空", file=sys.stderr)
        sys.exit(2)

    now = datetime.datetime.now(TZ)
    rec = {
        "id": next_id(now),
        "ts": now.isoformat(timespec="seconds"),
        "reporter": args.reporter,
        "source_session": args.session,
        "domain": args.domain,
        "target": args.target,
        "dimension": args.dimension,
        "severity": args.severity,
        "finding": finding,
        "root_cause": args.root_cause,
        "corrective_action": args.corrective_action,
        "status": args.status,
        "resolution": args.resolution,
        "tags": [t.strip() for t in args.tags.split(",") if t.strip()],
    }
    with FB.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"✅ 已记录 {rec['id']} [{rec['dimension']}/{rec['severity']}] → {FB}")

    # 事件驱动：每次反馈确认（记录）后立即跑一次 review 生成优化建议，不依赖 cron。
    if not args.no_review:
        import subprocess
        r = subprocess.run([sys.executable, str(ROOT / "review.py")],
                           capture_output=True, text=True)
        print(r.stdout.strip())
        if r.returncode != 0:
            print(r.stderr.strip(), file=sys.stderr)


if __name__ == "__main__":
    main()
