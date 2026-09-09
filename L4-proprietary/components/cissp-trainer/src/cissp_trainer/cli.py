#!/usr/bin/env python3
"""
CISSP Trainer CLI

命令：
  cissp start    — 开始一轮练习
  cissp stats    — 查看学习统计
  cissp import   — 导入题库（YAML/JSON）
  cissp weak     — 列出薄弱知识点
  cissp init     — 初始化数据库 + 导入样例题
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# 确保包可以 import
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cissp_trainer.database import init_db, session_scope, DEFAULT_DB_PATH
from cissp_trainer.engine import (
    pick_questions, answer_question,
    get_overall_stats, get_domain_stats,
    get_weak_knowledge_points,
)
from cissp_trainer.importer import import_from_file
from cissp_trainer.models import DOMAIN_NAMES


# ── 子命令：init ─────────────────────────────────────────

def cmd_init(args):
    """初始化数据库"""
    db_path = args.db or DEFAULT_DB_PATH
    print(f"🗄  数据库路径: {db_path}")

    if args.drop:
        print("⚠️  drop-first 模式：将清空所有数据")

    init_db(db_path=db_path, drop_first=args.drop)
    print("✅ 数据库初始化完成")

    # 如果指定了样例题，导入
    if args.sample:
        sample_path = Path(__file__).resolve().parents[2] / "data" / "yaml" / "sample_questions.yaml"
        if sample_path.exists():
            with session_scope(db_path) as s:
                result = import_from_file(s, sample_path, source="sample")
                print(f"📚 导入样例题: +{result['added']} 新增, "
                      f"{result['updated']} 更新, {result['skipped']} 跳过")
        else:
            print(f"⚠️  样例题文件不存在: {sample_path}")


# ── 子命令：start ────────────────────────────────────────

def cmd_start(args):
    """开始一轮练习"""
    domain = args.domain
    count = args.count
    mode = args.mode or "random"

    with session_scope() as session:
        questions = pick_questions(
            session,
            count=count,
            domain=domain,
            difficulty=args.difficulty,
            mode=mode,  # type: ignore
        )

        if not questions:
            print("❌ 没有符合条件的题目")
            return

        mode_names = {
            "random": "随机练习",
            "review": "到期复习",
            "weak": "薄弱点强化",
            "exam": "模拟考试",
        }

        print(f"\n📝 CISSP 练习 — {mode_names.get(mode, mode)}（共 {len(questions)} 题）")
        if domain:
            print(f"   领域: 域{domain} {DOMAIN_NAMES.get(domain, '')}")
        if args.difficulty:
            print(f"   难度: {args.difficulty}")
        print("   输入选项 A/B/C/D，q 退出\n")

        correct = 0
        answered = 0
        total_time = 0

        for i, q in enumerate(questions, 1):
            print(f"--- [{i}/{len(questions)}] ---")
            print(f"[域{q.domain} · 难度{q.difficulty}] {q.stem}")
            print()

            # 显示选项
            opt_keys = sorted(q.options.keys())
            for opt in opt_keys:
                print(f"  {opt}. {q.options[opt]}")
            print()

            t0 = time.time()
            try:
                ans = input("你的答案: ").strip().upper()
            except (EOFError, KeyboardInterrupt):
                print("\n\n已中断。")
                break
            elapsed = int(time.time() - t0)
            total_time += elapsed

            if ans == 'Q':
                break
            if not ans:
                print("  ⚠️  空输入，跳过")
                print()
                continue

            answered += 1
            result = answer_question(session, q.id, ans, time_spent_sec=elapsed)

            if result["is_correct"]:
                correct += 1
                print(f"  ✅ 正确！({elapsed}s)")
            else:
                print(f"  ❌ 错误。正确答案: {result['correct_answer']} ({elapsed}s)")

            # 解析
            if args.explanation or not result["is_correct"]:
                if result.get("explanation"):
                    print(f"  💡 解析: {result['explanation']}")

            # 下次复习提示
            if mode == "review":
                print(f"  🔄 下次复习: {result['next_review_date']} "
                      f"(间隔 {result['interval_days']} 天, EF={result['efactor']})")
            print()

        # 汇总
        print("=" * 50)
        print(f"📊 结果：{correct}/{answered} 正确", end="")
        if answered > 0:
            acc = correct / answered * 100
            print(f" ({acc:.1f}%)  用时 {total_time}s", end="")
            if answered > 0:
                print(f"  平均 {total_time//answered}s/题", end="")
        print()
        if answered > 0 and correct / answered < 0.6:
            print("⚠️  正确率低于 60%，建议回顾相关知识点")


# ── 子命令：stats ────────────────────────────────────────

def cmd_stats(args):
    """查看统计"""
    with session_scope() as session:
        overall = get_overall_stats(session)
        domains = get_domain_stats(session)

    print("📊 学习统计")
    print("=" * 60)
    print(f"  📚 题库总量:       {overall['total_questions']} 题")
    print(f"  🧠 知识点数量:     {overall['total_knowledge_points']} 个")
    print(f"  ✍️  累计答题:       {overall['total_study_records']} 次")
    print(f"  ✅ 累计正确:       {overall['total_correct']} 次")
    print(f"  📈 总体正确率:     {overall['overall_accuracy']*100:.1f}%")
    print(f"  📅 今日答题:       {overall['today_studied']} 题 "
          f"(正确率 {overall['today_accuracy']*100:.1f}%)")
    print(f"  🔄 待复习:         {overall['due_review_count']} 题")
    print()

    print("  各领域表现:")
    print(f"  {'域':>2} {'名称':<14} {'题数':>5} {'答题数':>6} {'正确率':>8} {'知识点':>6}")
    print(f"  {'─'*2} {'─'*14} {'─'*5} {'─'*6} {'─'*8} {'─'*6}")
    for d in domains:
        bar_len = 20
        filled = int(d["accuracy"] * bar_len)
        bar = "█" * filled + "░" * (bar_len - filled)
        print(f"  {d['domain']:>2} {d['domain_name']:<14} "
              f"{d['question_count']:>5} {d['study_count']:>6} "
              f"{d['accuracy']*100:>6.1f}% {bar} "
              f"{d['knowledge_point_count']:>4}")
    print()


# ── 子命令：import ──────────────────────────────────────

def cmd_import(args):
    """导入题库"""
    file_path = args.file
    if not Path(file_path).exists():
        print(f"❌ 文件不存在: {file_path}")
        sys.exit(1)

    with session_scope() as session:
        result = import_from_file(
            session, file_path,
            source=args.source or "imported",
            skip_existing=not args.force_update,
        )

    print(f"📥 导入完成")
    print(f"   处理: {result['total_processed']} 题")
    print(f"   新增: {result['added']}")
    print(f"   更新: {result['updated']}")
    print(f"   跳过: {result['skipped']}")
    if result["errors"]:
        print(f"   错误: {len(result['errors'])}")
        for e in result["errors"][:5]:
            print(f"     - {e}")


# ── 子命令：weak ────────────────────────────────────────

def cmd_weak(args):
    """列出薄弱知识点"""
    with session_scope() as session:
        kps = get_weak_knowledge_points(
            session, top_n=args.top or 10, domain=args.domain
        )

        if not kps:
            print("ℹ️  暂无足够数据（每个知识点至少需要 2 次复习才会纳入排名）")
            print("   多做几轮题后再来看吧～")
            return

        # 在 session 内读取所有属性，避免 detached instance 错误
        kp_data = []
        for kp in kps:
            kp_data.append({
                "name": kp.name,
                "domain": kp.domain,
                "mastery_level": kp.mastery_level,
                "review_count": kp.review_count,
                "wrong_count": kp.wrong_count,
            })

    print(f"🎯 薄弱知识点 Top {len(kp_data)}")
    print("=" * 60)
    print(f"  {'#':>2} {'知识点':<25} {'域':>2} {'掌握度':>8} {'复习':>4} {'错误':>4}")
    print(f"  {'─'*2} {'─'*25} {'─'*2} {'─'*8} {'─'*4} {'─'*4}")

    for i, kp in enumerate(kp_data, 1):
        mastery_pct = kp["mastery_level"] * 100
        bar_len = 15
        filled = int(kp["mastery_level"] * bar_len)
        bar = "█" * filled + "░" * (bar_len - filled)
        print(f"  {i:>2} {kp['name']:<25} {kp['domain']:>2} "
              f"{bar} {mastery_pct:>5.1f}% "
              f"{kp['review_count']:>4} {kp['wrong_count']:>4}")

    print()
    print(f"💡 建议：使用 `cissp start --mode weak` 针对性强化薄弱知识点")


# ── main ─────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="cissp-trainer",
        description="CISSP 学习引擎 — 智能出题 + 间隔重复 + 薄弱点追踪",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  cissp init --sample                     # 初始化数据库 + 导入样例题
  cissp start --count 20                  # 随机 20 题
  cissp start --domain 1 --mode review    # 域1 到期复习
  cissp start --mode weak                 # 薄弱点强化
  cissp start --mode exam --count 100     # 模拟考试 100 题
  cissp stats                             # 查看统计
  cissp import questions.yaml             # 导入 YAML 题库
  cissp weak --top 15                     # Top 15 薄弱知识点
        """
    )
    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # init
    p_init = subparsers.add_parser("init", help="初始化数据库")
    p_init.add_argument("--sample", action="store_true", help="导入内置样例题")
    p_init.add_argument("--drop", action="store_true", help="先清空再初始化")
    p_init.add_argument("--db", type=str, help="指定数据库路径")
    p_init.set_defaults(func=cmd_init)

    # start
    p_start = subparsers.add_parser("start", help="开始一轮练习")
    p_start.add_argument("-n", "--count", type=int, default=10, help="题目数量 (默认 10)")
    p_start.add_argument("-d", "--domain", type=int, help="指定领域 (1-8)")
    p_start.add_argument("-l", "--difficulty", type=int, help="指定难度 (1-5)")
    p_start.add_argument("-m", "--mode", type=str,
                         choices=["random", "review", "weak", "exam"],
                         default="random", help="出题模式 (默认 random)")
    p_start.add_argument("-e", "--explanation", action="store_true",
                         help="总是显示解析（默认只在答错时显示）")
    p_start.set_defaults(func=cmd_start)

    # stats
    p_stats = subparsers.add_parser("stats", help="查看学习统计")
    p_stats.set_defaults(func=cmd_stats)

    # import
    p_imp = subparsers.add_parser("import", help="导入题库")
    p_imp.add_argument("file", help="题库文件 (.yaml/.yml/.json)")
    p_imp.add_argument("--source", type=str, help="来源标识")
    p_imp.add_argument("--force-update", action="store_true",
                       help="已存在的题目强制更新（默认跳过）")
    p_imp.set_defaults(func=cmd_import)

    # weak
    p_weak = subparsers.add_parser("weak", help="列出薄弱知识点")
    p_weak.add_argument("-n", "--top", type=int, default=10, help="显示前 N 个 (默认 10)")
    p_weak.add_argument("-d", "--domain", type=int, help="指定领域 (1-8)")
    p_weak.set_defaults(func=cmd_weak)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    args.func(args)


if __name__ == "__main__":
    main()
