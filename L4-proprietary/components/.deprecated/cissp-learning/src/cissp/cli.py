#!/usr/bin/env python3
"""
CISSP 学习系统 CLI 入口

子命令：
  cissp plan          生成/查看学习计划
  cissp today         查看今日学习内容
  cissp quiz          答题练习
  cissp flashcard     速记卡模式
  cissp progress      查看学习进度
  cissp import        导入题库/知识点
  cissp stats         题库统计
"""

import argparse
import sys
import json
import os
from datetime import date, timedelta
from pathlib import Path

# 确保能 import 同级模块
sys.path.insert(0, str(Path(__file__).resolve().parent))


def cmd_plan(args):
    """生成/查看学习计划"""
    from cissp.planner import generate_plan, save_plan, get_plan

    if args.generate:
        start_date = date.fromisoformat(args.start) if args.start else None
        plan = generate_plan(
            start_date=start_date,
            weeks=args.weeks,
            weekday_hours=args.weekday_hours,
            weekend_hours=args.weekend_hours
        )
        save_plan(plan)
        print(f"✅ 已生成 {plan['meta']['total_weeks']} 周学习计划")
        print(f"   开始日期: {plan['meta']['start_date']}")
        print(f"   总时长: {plan['meta']['total_hours']}h "
              f"(工作日 {plan['meta']['weekday_hours']}h/天, "
              f"周末 {plan['meta']['weekend_hours']}h/天)")

        if args.show_weeks:
            _print_weeks(plan, args.show_weeks)
        return

    # 默认：查看计划
    plan = get_plan()
    if plan is None:
        print("暂无学习计划，使用 --generate 生成。")
        return

    print(f"📅 学习计划（{plan['meta']['total_weeks']} 周）")
    print(f"   开始: {plan['meta']['start_date']} | 总时长: {plan['meta']['total_hours']}h")
    print()
    _print_weeks(plan, args.week or 1)


def _print_weeks(plan, num_weeks):
    """打印前 N 周计划概览"""
    for w in plan["weeks"][:num_weeks]:
        print(f"第 {w['week']:2d} 周 ({w['start']} ~ {w['end']})")
        for d_str in w["days"]:
            d = plan["days"][d_str]
            weekend_mark = "☀️" if d["is_weekend"] else "  "
            domains = set(i["domain_name"] for i in d["items"])
            domain_str = "/".join(domains) if domains else "(无)"
            main_names = [i["main_name"] for i in d["items"][:2]]
            main_str = ", ".join(main_names)
            complete_mark = "✅" if d.get("completed") else "⬜"
            print(f"  {complete_mark} {d['date']} {weekend_mark} "
                  f"[{d['planned_hours']:>3}h] {domain_str}: {main_str[:40]}")
        print()


def cmd_today(args):
    """查看今日学习内容"""
    from cissp.planner import get_day_plan, generate_plan, save_plan, get_plan
    from cissp.daily_content import generate_daily_content, format_daily_content

    # 如果没有计划，先生成
    if get_plan() is None:
        print("暂无计划，正在生成新计划...")
        plan = generate_plan()
        save_plan(plan)

    target_date = args.date or date.today().isoformat()
    day_plan = get_day_plan(target_date)

    if day_plan is None:
        print(f"❌ 未找到 {target_date} 的学习计划")
        return

    content = generate_daily_content(day_plan)
    print(format_daily_content(content))


def cmd_quiz(args):
    """答题练习"""
    from cissp.question_bank import generate_quiz, record_mistake

    domain = args.domain
    count = args.count
    questions = generate_quiz(count=count, domain=domain)

    if not questions:
        print("❌ 没有符合条件的题目")
        return

    print(f"\n📝 CISSP 练习题（共 {len(questions)} 题）")
    if domain:
        print(f"   范围: 域 {domain}")
    print("   输入选项 A/B/C/D，q 退出\n")

    correct = 0
    answered = 0

    for i, q in enumerate(questions, 1):
        print(f"--- [{i}/{len(questions)}] ---")
        print(f"Q: {q['question']}")
        print()
        for opt in ['A', 'B', 'C', 'D']:
            if opt in q['options']:
                print(f"  {opt}. {q['options'][opt]}")
        print()

        try:
            ans = input("你的答案: ").strip().upper()
        except EOFError:
            break

        if ans == 'Q':
            break
        if ans not in ['A', 'B', 'C', 'D']:
            print("  ⚠️  无效输入，跳过")
            print()
            continue

        answered += 1
        is_correct = ans == q['answer']
        if is_correct:
            correct += 1
            print("  ✅ 正确！")
        else:
            print(f"  ❌ 错误。正确答案: {q['answer']}")
            record_mistake(q["id"], ans)

        if args.show_explanation or not is_correct:
            exp = q.get("explanation", "")
            if exp:
                print(f"  💡 解析: {exp}")
        print()

    print(f"📊 结果：{correct}/{answered} 正确", end="")
    if answered > 0:
        print(f" ({correct/answered*100:.1f}%)")
    else:
        print()


def cmd_flashcard(args):
    """速记卡模式"""
    from cissp.flashcard import generate_flashcards, format_flashcards, interactive_flashcards

    cards = generate_flashcards(
        domain_id=args.domain,
        count=args.count,
        mix=not args.concepts_only
    )

    if args.export:
        fmt = args.export_format or "text"
        output = format_flashcards(cards, format=fmt)
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(output)
            print(f"✅ 已导出 {len(cards)} 张速记卡到 {args.output}")
        else:
            print(output)
        return

    # 交互式
    interactive_flashcards(cards)


def cmd_progress(args):
    """查看学习进度"""
    from cissp.planner import get_plan
    from cissp.question_bank import load_mistakes

    plan = get_plan()
    mistakes = load_mistakes()

    print("📊 学习进度")
    print("=" * 40)

    if plan:
        days = plan["days"]
        total_days = len(days)
        completed_days = sum(1 for d in days.values() if d.get("completed"))
        pct = completed_days / total_days * 100 if total_days > 0 else 0
        print(f"  计划天数: {total_days}")
        print(f"  已完成: {completed_days} 天 ({pct:.1f}%)")

        # 本周进度
        today = date.today().isoformat()
        this_week = None
        for w in plan["weeks"]:
            if w["start"] <= today <= w["end"]:
                this_week = w
                break
        if this_week:
            week_done = sum(1 for d_str in this_week["days"]
                            if days.get(d_str, {}).get("completed"))
            week_total = len(this_week["days"])
            print(f"  本周进度: {week_done}/{week_total} 天")
    else:
        print("  (暂无计划)")

    print()
    print(f"  错题数: {mistakes['stats']['total_mistakes']}")
    by_domain = mistakes["stats"].get("by_domain", {})
    if by_domain:
        print("  按域分布:")
        for d in sorted(by_domain.keys(), key=lambda x: int(x) if x.isdigit() else 99):
            print(f"    域{d}: {by_domain[d]} 题")

    print()


def cmd_import(args):
    """导入题库"""
    from cissp.question_bank import import_questions

    file_path = args.file
    if not os.path.exists(file_path):
        print(f"❌ 文件不存在: {file_path}")
        return

    with open(file_path, encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, dict) and "questions" in data:
        data = data["questions"]

    source = args.source or "imported"
    added = import_questions(data, source_name=source)
    print(f"✅ 已导入 {added} 道题，来源: {source}")


def cmd_stats(args):
    """题库统计"""
    from cissp.question_bank import get_stats

    stats = get_stats()
    print(f"📚 题库统计")
    print("=" * 40)
    print(f"  总题数: {stats['total']}")
    print()
    print("  按域分布:")
    from cissp.planner import load_domains
    domains = load_domains()
    domain_names = {str(d["id"]): d["name"] for d in domains}
    for d in sorted(stats["by_domain"].keys(), key=lambda x: int(x) if x.isdigit() else 99):
        name = domain_names.get(d, "未知")
        cnt = stats["by_domain"][d]
        pct = cnt / stats["total"] * 100 if stats["total"] > 0 else 0
        bar = "█" * int(pct / 2) + "░" * (50 - int(pct / 2))
        print(f"    域{d} {name:<12} {cnt:>4} 题 [{bar}] {pct:5.1f}%")
    print()
    print("  按来源:")
    for s, c in stats["by_source"].items():
        print(f"    {s}: {c} 题")


def main():
    parser = argparse.ArgumentParser(
        prog="cissp",
        description="CISSP 学习系统 — 16 周备考规划 + 题库 + 速记卡",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  cissp plan --generate --start 2026-09-08
  cissp today
  cissp quiz --count 10 --domain 1
  cissp flashcard --domain 3 --count 20
  cissp progress
  cissp stats
        """
    )
    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # plan
    p_plan = subparsers.add_parser("plan", help="生成/查看学习计划")
    p_plan.add_argument("-g", "--generate", action="store_true", help="生成新计划")
    p_plan.add_argument("--start", type=str, help="开始日期 (YYYY-MM-DD)")
    p_plan.add_argument("--weeks", type=int, default=16, help="总周数 (默认 16)")
    p_plan.add_argument("--weekday-hours", type=float, default=1.0, help="工作日每日时长 (默认 1h)")
    p_plan.add_argument("--weekend-hours", type=float, default=3.0, help="周末每日时长 (默认 3h)")
    p_plan.add_argument("-w", "--week", type=int, default=1, help="显示前 N 周 (默认 1)")
    p_plan.add_argument("--show-weeks", type=int, default=0, help="生成后显示前 N 周")
    p_plan.set_defaults(func=cmd_plan)

    # today
    p_today = subparsers.add_parser("today", help="查看今日学习内容")
    p_today.add_argument("--date", type=str, help="指定日期 (YYYY-MM-DD)")
    p_today.set_defaults(func=cmd_today)

    # quiz
    p_quiz = subparsers.add_parser("quiz", help="答题练习")
    p_quiz.add_argument("-n", "--count", type=int, default=10, help="题目数量 (默认 10)")
    p_quiz.add_argument("-d", "--domain", type=int, help="指定域 ID (1-8)")
    p_quiz.add_argument("-e", "--show-explanation", action="store_true", help="总是显示解析")
    p_quiz.set_defaults(func=cmd_quiz)

    # flashcard
    p_fc = subparsers.add_parser("flashcard", help="速记卡模式")
    p_fc.add_argument("-n", "--count", type=int, default=20, help="卡片数量 (默认 20)")
    p_fc.add_argument("-d", "--domain", type=int, help="指定域 ID (1-8)")
    p_fc.add_argument("--concepts-only", action="store_true", help="仅概念卡（不含题目卡）")
    p_fc.add_argument("--export", action="store_true", help="导出为文件")
    p_fc.add_argument("--export-format", choices=["text", "anki", "json"], help="导出格式")
    p_fc.add_argument("-o", "--output", type=str, help="输出文件路径")
    p_fc.set_defaults(func=cmd_flashcard)

    # progress
    p_prog = subparsers.add_parser("progress", help="查看学习进度")
    p_prog.set_defaults(func=cmd_progress)

    # import
    p_imp = subparsers.add_parser("import", help="导入题库")
    p_imp.add_argument("file", help="JSON 文件路径")
    p_imp.add_argument("--source", type=str, help="来源标识")
    p_imp.set_defaults(func=cmd_import)

    # stats
    p_stats = subparsers.add_parser("stats", help="题库统计")
    p_stats.set_defaults(func=cmd_stats)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    args.func(args)


if __name__ == "__main__":
    main()
