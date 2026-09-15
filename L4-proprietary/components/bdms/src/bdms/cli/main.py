"""BDMS CLI —— 统一命令行入口（AI Agent 独立执行入口）。

设计目标：所有核心功能可通过 CLI 独立执行，不依赖 Web。

用法：
  bdms report generate 202608 [--mode auto|read|regenerate]
  bdms report export 202608 [--out PATH]
  bdms report list
  bdms revenue generate 202608 [--mode auto|read|regenerate]
  bdms revenue import 202608
  bdms revenue summary 202608
  bdms revenue compare 202606 --manual PATH   # 与手工报表对比
  bdms master-data legend list
  bdms dashboard show 202608
  bdms settings get
  bdms settings set KEY VALUE
  bdms web [--port 8800]
"""

import argparse
import json
import sys
from pathlib import Path

from bdms.core import db as _db


def _print_json(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


# ─── report 子命令 ───

def cmd_report(args) -> int:
    from ..modules.delivery_report.service import DeliveryReportService
    from ..modules.delivery_report.exporter import DeliveryReportExporter

    svc = DeliveryReportService()
    if args.action == "generate":
        r = svc.generate(args.month, args.mode)
        print(f"✅ {args.month} {r['action']} 完成: {r['total_rows']} 行")
        for sheet, n in r["sheets"].items():
            print(f"   {sheet}: {n}")
        return 0
    if args.action == "export":
        out = DeliveryReportExporter().export(args.month, args.out)
        print(f"✅ 导出: {out}")
        return 0
    if args.action == "list":
        for m in svc.list_months():
            print(f"   {m['month']}: {m.get('row_counts', '')}")
        return 0
    return 1


# ─── revenue 子命令 ───

def cmd_revenue(args) -> int:
    from ..modules.revenue.engine import RevenueEngineAdapter
    from ..modules.revenue.summary_engine import SummaryEngine

    if args.action == "import":
        a = RevenueEngineAdapter()
        r = a.import_source(args.month)
        _print_json(r)
        return 0
    if args.action == "generate":
        a = RevenueEngineAdapter()
        r = a.compute(args.month)
        for k, v in r.items():
            n = len(v) if isinstance(v, (list, dict)) else "?"
            print(f"   {k}: {n}")
        return 0
    if args.action == "summary":
        s = SummaryEngine()
        r = s.compute_summary(args.month)
        if "error" in r:
            print(f"❌ {r['error']}")
            return 1
        print(f"{'期间':<10}{'递延计划':>12}{'递延实际':>12}{'新签计划':>12}{'新签实际':>12}")
        for row in r["rows"]:
            c = row["categories"]
            print(f"{row['period']:<10}{c['递延']['plan']/10000:>12,.2f}"
                  f"{c['递延']['actual']/10000:>12,.2f}"
                  f"{c['新签']['plan']/10000:>12,.2f}"
                  f"{c['新签']['actual']/10000:>12,.2f}")
        return 0
    if args.action == "compare":
        s = SummaryEngine()
        mine = s.compute_summary(args.month)
        manual_path = Path(args.manual) if args.manual else None
        if not manual_path:
            print("需要 --manual 指定手工报表路径")
            return 1
        manual = s.read_manual_summary(manual_path)
        mrows = {r.get("period"): r for r in manual["rows"] if r.get("period")}

        # 同口径区间 = 手工报表生成当月及之前（以后月份只是当时预测，会随数据演进）
        cutoff = args.month  # 手工报表对应月份口径
        print(f"对比区间: 我方计算 vs 手工报表")
        print(f"  * 同口径区间 = {cutoff} 及之前；{cutoff} 之后为当时预测，数据已演进，不计入判定\n")

        ok, diff, skipped = 0, 0, 0
        for row in mine["rows"]:
            p = row["period"]
            m = mrows.get(p)
            if not m or p > cutoff:
                skipped += 1
                continue
            for cat, mkey in [("递延", "deferred"), ("新签", "new_sign"), ("合计", "total")]:
                op = row["categories"][cat]["plan"] / 10000
                oa = row["categories"][cat]["actual"] / 10000
                mp, ma = m[mkey]["plan"] or 0, m[mkey]["actual"] or 0
                match = abs(op - mp) < 0.01 and abs(oa - ma) < 0.01
                ok, diff = (ok + 1, diff) if match else (ok, diff + 1)
                flag = "OK" if match else "DIFF"
                print(f"{p} {cat:<5} 我{op:>10,.2f}/{oa:>10,.2f} "
                      f"手工{mp:>10,.2f}/{ma:>10,.2f} {flag}")
        print(f"\n结果: {ok} 匹配 / {diff} 差异 / {skipped} 月无基准")
        return 0 if diff == 0 else 2
    return 1


# ─── master-data 子命令 ───

def cmd_master_data(args) -> int:
    try:
        from ..modules.master_data.service import MasterDataService
    except ImportError:
        print("❌ 模块3（master_data）尚未完成")
        return 1
    svc = MasterDataService()
    if args.action == "list":
        types = svc.list_types() if hasattr(svc, "list_types") else []
        print(f"数据类型: {types}")
        if args.data_type:
            for r in svc.list_reference(args.data_type):
                print(f"   {r.get('code')}: {r.get('label')}")
        return 0
    return 1


# ─── dashboard 子命令 ───

def cmd_dashboard(args) -> int:
    try:
        from ..modules.dashboard.service import DashboardService
    except ImportError:
        print("❌ 模块4（dashboard）尚未完成")
        return 1
    svc = DashboardService()
    data = svc.get_dashboard(args.month)
    _print_json(data)
    return 0


# ─── settings 子命令 ───

def cmd_settings(args) -> int:
    try:
        from ..modules.settings.service import SettingsService
    except ImportError:
        print("❌ 模块5（settings）尚未完成")
        return 1
    svc = SettingsService()
    if args.action == "get":
        _print_json(svc.get_all())
        return 0
    if args.action == "set":
        r = svc.set(args.key, args.value)
        print(f"✅ {args.key} = {args.value}")
        return 0
    return 1


# ─── web 子命令 ───

def cmd_web(args) -> int:
    import uvicorn
    from ..web.main import app
    uvicorn.run(app, host=args.host, port=args.port)
    return 0


# ─── 初始化 ───

def cmd_init(args) -> int:
    _db.init_db()
    print(f"✅ DB 初始化: {_db.DB_PATH}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="bdms", description="BDMS 交付管理系统 CLI")
    sub = p.add_subparsers(dest="module", required=True)

    sub.add_parser("init", help="初始化 DB")

    # report
    rp = sub.add_parser("report", help="交付月报")
    rp.add_argument("action", choices=["generate", "export", "list"])
    rp.add_argument("month", nargs="?", default=None)
    rp.add_argument("--mode", default="auto", choices=["auto", "read", "regenerate"])
    rp.add_argument("--out", default=None)

    # revenue
    rv = sub.add_parser("revenue", help="确认收入")
    rv.add_argument("action", choices=["import", "generate", "summary", "compare"])
    rv.add_argument("month")
    rv.add_argument("--manual", default=None)
    rv.add_argument("--mode", default="auto")

    # master-data
    md = sub.add_parser("master-data", help="基础数据")
    md.add_argument("action", choices=["list"])
    md.add_argument("data_type", nargs="?", default=None)

    # dashboard
    db = sub.add_parser("dashboard", help="统计看板")
    db.add_argument("action", choices=["show"])
    db.add_argument("month")

    # settings
    st = sub.add_parser("settings", help="系统设定")
    st.add_argument("action", choices=["get", "set"])
    st.add_argument("key", nargs="?", default=None)
    st.add_argument("value", nargs="?", default=None)

    # web
    wb = sub.add_parser("web", help="启动 Web UI")
    wb.add_argument("--host", default="127.0.0.1")
    wb.add_argument("--port", type=int, default=8800)

    return p


HANDLERS = {
    "init": cmd_init,
    "report": cmd_report,
    "revenue": cmd_revenue,
    "master-data": cmd_master_data,
    "dashboard": cmd_dashboard,
    "settings": cmd_settings,
    "web": cmd_web,
}


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    # 确保 DB 就绪
    try:
        _db.init_db()
    except Exception:
        pass
    return HANDLERS[args.module](args)


if __name__ == "__main__":
    sys.exit(main())
