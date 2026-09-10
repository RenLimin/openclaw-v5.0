"""
BDMS v2 CLI — 交付月报管理命令行工具

用法:
    python -m v2.cli.bdmsctl generate 2026-08
    python -m v2.cli.bdmsctl list
    python -m v2.cli.bdmsctl status <job_id>
    python -m v2.cli.bdmsctl summary <job_id>
    python -m v2.cli.bdmsctl migrate
    python -m v2.cli.bdmsctl serve [--port 8000]
"""

import sys
import os
import argparse
import time
from pathlib import Path

# 确保 v2 目录在 sys.path 中
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


def cmd_generate(args):
    """生成月报"""
    from services.report_service import generate_report_async, get_report_status

    month = args.month
    print(f"🚀 开始生成 {month} 月交付月报...")

    job_id = generate_report_async(month)
    print(f"   任务 ID: {job_id}")

    # 轮询等待完成
    if args.wait:
        print("   等待生成完成...")
        while True:
            job = get_report_status(job_id)
            if not job:
                print("❌ 任务不存在")
                return 1
            status = job["status"]
            progress = job.get("progress", 0)

            if status == "completed":
                print(f"✅ 生成完成！进度 100%")
                print(f"   文件: {job['file_path']}")
                return 0
            elif status == "failed":
                print(f"❌ 生成失败: {job.get('error_msg', '未知错误')}")
                return 1
            else:
                print(f"   生成中... {progress}% (状态: {status})")
                time.sleep(args.interval)
    else:
        print(f"   后台生成中，用 'bdmsctl status {job_id}' 查看进度")
        return 0


def cmd_list(args):
    """列出报告列表"""
    from services.report_service import list_reports

    reports = list_reports(limit=args.limit)
    if not reports:
        print("暂无报告")
        return 0

    print(f"{'ID':>4}  {'月份':<8}  {'状态':<10}  {'进度':>5}  {'创建时间':<20}  {'文件'}")
    print("-" * 90)
    for r in reports:
        fp = r.get("file_path") or "-"
        if fp and len(fp) > 40:
            fp = "..." + fp[-37:]
        print(f"{r['id']:>4}  {r['month']:<8}  {r['status']:<10}  {r.get('progress', 0):>4}%  {r['created_at']:<20}  {fp}")

    return 0


def cmd_status(args):
    """查看任务状态"""
    from services.report_service import get_report_status

    job = get_report_status(args.job_id)
    if not job:
        print(f"❌ 任务 {args.job_id} 不存在")
        return 1

    print(f"📋 任务 #{job['id']}")
    print(f"   月份:     {job['month']}")
    print(f"   状态:     {job['status']}")
    print(f"   进度:     {job.get('progress', 0)}%")
    print(f"   创建时间: {job['created_at']}")
    if job.get("updated_at"):
        print(f"   更新时间: {job['updated_at']}")
    if job.get("file_path"):
        print(f"   输出文件: {job['file_path']}")
    if job.get("error_msg"):
        print(f"   错误信息: {job['error_msg']}")

    return 0


def cmd_summary(args):
    """查看报告概要"""
    from services.report_service import get_report_summary

    result = get_report_summary(args.job_id)
    if not result:
        print(f"❌ 任务 {args.job_id} 不存在")
        return 1

    job = result["job"]
    sheets = result.get("sheets", [])

    print(f"📊 报告概要 #{job['id']} - {job['month']}")
    print(f"   状态: {job['status']}")
    print()

    if not sheets:
        print("   （无概要数据）")
        return 0

    for s in sheets:
        print(f"   📄 {s['sheet_name']} ({s['row_count']} 行)")
        metrics = s.get("summary", {}).get("top_metrics", [])
        if metrics:
            for m in metrics[:5]:
                val = m["value"]
                if isinstance(val, float):
                    val = f"{val:,.2f}"
                print(f"      • {m['label']}: {val}")
        print()

    return 0


def cmd_migrate(args):
    """v1 → v2 数据迁移"""
    from scripts.migrate_v1_to_v2 import migrate_all

    print("🔄 开始 v1 → v2 数据迁移...")
    result = migrate_all(dry_run=args.dry_run)

    if args.dry_run:
        print(f"   预检完成：将迁移 {result.get('contracts', 0)} 条合同、{result.get('hours', 0)} 条工时数据")
    else:
        print(f"✅ 迁移完成")
        print(f"   合同数据: {result.get('contracts', 0)} 条")
        print(f"   工时数据: {result.get('hours', 0)} 条")

    return 0


def cmd_serve(args):
    """启动 Web UI 服务"""
    import uvicorn
    from web.main import app

    print(f"🌐 启动 BDMS Web UI: http://localhost:{args.port}")
    print(f"   按 Ctrl+C 停止")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


def main():
    parser = argparse.ArgumentParser(
        prog="bdmsctl",
        description="BDMS v2 — 交付月报管理工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", help="可用命令")

    # generate
    p_gen = sub.add_parser("generate", help="生成交付月报")
    p_gen.add_argument("month", help="月份，格式 YYYY-MM")
    p_gen.add_argument("--wait", action="store_true", help="等待生成完成")
    p_gen.add_argument("--interval", type=int, default=2, help="轮询间隔（秒）")
    p_gen.set_defaults(func=cmd_generate)

    # list
    p_list = sub.add_parser("list", help="列出报告列表")
    p_list.add_argument("--limit", type=int, default=20, help="显示条数")
    p_list.set_defaults(func=cmd_list)

    # status
    p_status = sub.add_parser("status", help="查看任务状态")
    p_status.add_argument("job_id", type=int, help="任务 ID")
    p_status.set_defaults(func=cmd_status)

    # summary
    p_summary = sub.add_parser("summary", help="查看报告概要")
    p_summary.add_argument("job_id", type=int, help="任务 ID")
    p_summary.set_defaults(func=cmd_summary)

    # migrate
    p_mig = sub.add_parser("migrate", help="v1 → v2 数据迁移")
    p_mig.add_argument("--dry-run", action="store_true", help="预检模式，不实际迁移")
    p_mig.set_defaults(func=cmd_migrate)

    # serve
    p_serve = sub.add_parser("serve", help="启动 Web UI 服务")
    p_serve.add_argument("--host", default="127.0.0.1", help="监听地址")
    p_serve.add_argument("--port", type=int, default=8000, help="端口")
    p_serve.set_defaults(func=cmd_serve)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return 1

    return args.func(args) or 0


if __name__ == "__main__":
    sys.exit(main())
