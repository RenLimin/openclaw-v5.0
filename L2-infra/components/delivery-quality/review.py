#!/usr/bin/env python3
"""交付质量反馈定期 review：聚类 + 复发检测 + 升级建议，生成报告（只读，不自动改核心文件）。

用法：
  review.py                 # 生成 reviews/review-YYYYMMDD.md
  review.py --json          # 打印结构化结果
  review.py --days 14       # 只看近 N 天
"""
import argparse, json, datetime
from pathlib import Path
from collections import Counter, defaultdict

ROOT = Path(__file__).resolve().parent
FB = ROOT / "feedback.jsonl"
REVIEWS = ROOT / "reviews"
TZ = datetime.timezone(datetime.timedelta(hours=8))

# 复发阈值：同根因/同维度出现 >= N 次建议系统级升级
RECUR_THRESHOLD = 2


def load(days=None):
    recs = []
    if not FB.exists():
        return recs
    cutoff = None
    if days:
        cutoff = datetime.datetime.now(TZ) - datetime.timedelta(days=days)
    for line in FB.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if cutoff:
            try:
                t = datetime.datetime.fromisoformat(r["ts"])
                if t.tzinfo is None:
                    t = t.replace(tzinfo=TZ)
                if t < cutoff:
                    continue
            except (KeyError, ValueError):
                pass
        recs.append(r)
    return recs


def analyze(recs):
    by_dim = Counter(r.get("dimension", "?") for r in recs)
    by_domain = Counter(r.get("domain", "?") for r in recs)
    by_sev = Counter(r.get("severity", "?") for r in recs)
    by_status = Counter(r.get("status", "?") for r in recs)

    # 根因聚类（root_cause 非空才按根因，否则退回 dimension）
    clusters = defaultdict(list)
    for r in recs:
        key = (r.get("root_cause") or "").strip()
        key = key if key else f"[dimension:{r.get('dimension')}]"
        clusters[key].append(r)

    recurring = []
    for cause, items in clusters.items():
        if len(items) >= RECUR_THRESHOLD:
            open_items = [i for i in items if i.get("status") in ("open", "corrected")]
            if open_items:
                recurring.append((cause, items))
    recurring.sort(key=lambda x: -len(x[1]))

    open_fb = [r for r in recs if r.get("status") == "open"]
    # 高危单次项：high 严重度、根因未复发、且尚未系统升级——首次即提示评估，不等复发
    recurring_causes = {c for c, _ in recurring}
    high_singles = []
    for r in recs:
        if r.get("severity") != "high":
            continue
        if r.get("status") in ("promoted", "wontfix"):
            continue
        cause = (r.get("root_cause") or "").strip() or f"[dimension:{r.get('dimension')}]"
        if cause not in recurring_causes:
            high_singles.append(r)
    return {
        "total": len(recs),
        "by_dim": by_dim,
        "by_domain": by_domain,
        "by_sev": by_sev,
        "by_status": by_status,
        "clusters": clusters,
        "recurring": recurring,
        "open_fb": open_fb,
        "high_singles": high_singles,
    }


def suggest(cause, items):
    dims = {i.get("dimension") for i in items}
    sugg = []
    if dims & {"data_fidelity", "calculation_logic", "data_completeness"}:
        sugg.append("收紧 P2 域契约的『维度合格判据』并补一条确定性校验（checker）")
        sugg.append("为该口径加黄金 fixture（正例/反例）纳入 pre-commit")
    if dims & {"missing_risk_analysis", "missing_context"}:
        sugg.append("在对应 P2 契约把该维度列为必备章节，缺失即 checker BLOCK")
    if dims & {"best_practice_gap"}:
        sugg.append("把业界要素清单固化进 P2 契约/交付模板，形成结构骨架")
    if dims & {"sourcing"}:
        sugg.append("强化降级标注校验（已有 checker），补溯源链 fixture")
    if not sugg:
        sugg.append("人工 review 后决定 KB 沉淀或 wontfix")
    return sugg


def render(recs, a, days):
    now = datetime.datetime.now(TZ)
    L = []
    L.append("# 交付质量反馈 Review 报告\n")
    scope = f"近 {days} 天" if days else "全量"
    L.append(f"> 生成：{now.isoformat(timespec='seconds')} · 范围：{scope} · 共 {a['total']} 条\n")
    L.append("> 本报告只读，提出升级建议；是否改 P2 契约/技能/KB 需 Rex 拍板。")
    L.append("")
    L.append("**溯源链**：`feedback.jsonl（record.py 记录 Rex 反馈）→ review.py 读入聚类 → 本报告`。")
    L.append("【已验证 {d}|数据源：L2-infra/components/delivery-quality/feedback.jsonl】".format(d=now.strftime("%Y-%m-%d")))
    L.append("")


    L.append("\n## 1. 分布\n")
    L.append("- **按维度**：" + "，".join(f"{k} {v}" for k, v in a["by_dim"].most_common()))
    L.append("- **按业务域**：" + "，".join(f"{k} {v}" for k, v in a["by_domain"].most_common()))
    L.append("- **按严重度**：" + "，".join(f"{k} {v}" for k, v in a["by_sev"].most_common()))
    L.append("- **按状态**：" + "，".join(f"{k} {v}" for k, v in a["by_status"].most_common()))

    L.append("\n## 2. 复发项（同根因 ≥%d，建议系统级升级）\n" % RECUR_THRESHOLD)
    if not a["recurring"]:
        L.append("暂无达到复发阈值的根因（单条纠正暂不需要系统升级）。")
    for cause, items in a["recurring"]:
        L.append(f"\n### 🔁 {len(items)} 次 · {cause}")
        for i in items:
            L.append(f"- `{i.get('id')}` [{i.get('status')}] {i.get('finding','')[:80]}")
        L.append("\n**建议**：")
        for s in suggest(cause, items):
            L.append(f"  - {s}")

    L.append("\n## 2b. 高危单次项（high 严重度，首次即评估升级，不必等复发）\n")
    if not a["high_singles"]:
        L.append("无。")
    seen_cause = set()
    for r in a["high_singles"]:
        cause = (r.get("root_cause") or "").strip() or r.get("dimension")
        if cause in seen_cause:
            continue
        seen_cause.add(cause)
        L.append(f"- `{r.get('id')}` [{r.get('dimension')}] {r.get('finding','')[:80]}")
        for sg in suggest(cause, [r]):
            L.append(f"    - → {sg}")

    L.append("\n## 3. 待处理 open 反馈（%d）\n" % len(a["open_fb"]))
    if not a["open_fb"]:
        L.append("无。")
    for r in a["open_fb"]:
        L.append(f"- `{r.get('id')}` [{r.get('severity')}] {r.get('finding','')[:90]}")

    L.append("\n## 4. 全部条目状态跟踪\n")
    L.append("| ID | 域 | 维度 | 严重度 | 状态 | 摘要 |")
    L.append("|---|---|---|---|---|---|")
    for r in sorted(recs, key=lambda x: x.get("ts", ""), reverse=True):
        L.append("| {id} | {dom} | {dim} | {sev} | {st} | {f} |".format(
            id=r.get("id"), dom=r.get("domain"), dim=r.get("dimension"),
            sev=r.get("severity"), st=r.get("status"),
            f=r.get("finding", "")[:50].replace("|", "/")))
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=None)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    recs = load(args.days)
    a = analyze(recs)
    if args.json:
        out = {
            "total": a["total"],
            "by_dim": dict(a["by_dim"]),
            "recurring": [{"root_cause": c, "count": len(items),
                           "ids": [i.get("id") for i in items]}
                          for c, items in a["recurring"]],
            "open_count": len(a["open_fb"]),
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return
    if not recs:
        print("⚠️ feedback.jsonl 为空或无匹配记录")
        return
    REVIEWS.mkdir(exist_ok=True)
    now = datetime.datetime.now(TZ)
    out = REVIEWS / f"review-{now.strftime('%Y%m%d')}.md"
    out.write_text(render(recs, a, args.days), encoding="utf-8")
    print(f"✅ review 报告已生成：{out}")
    print(f"   共 {a['total']} 条 | 复发根因 {len(a['recurring'])} | 高危单次 {len(a['high_singles'])} | open {len(a['open_fb'])}")


if __name__ == "__main__":
    main()
