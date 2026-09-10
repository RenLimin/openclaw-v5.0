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
from cissp_trainer import learning_path as lp_module
from cissp_trainer import exam_engine as exam_mod
from cissp_trainer import knowledge_graph as kg_mod


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
            from cissp_trainer.importer import import_knowledge_graph_from_file
            with session_scope(db_path) as s:
                result = import_from_file(s, sample_path, source="sample")
                print(f"📚 导入样例题: +{result['added']} 新增, "
                      f"{result['updated']} 更新, {result['skipped']} 跳过")
                # 导入知识图谱预设
                kg_path = Path(__file__).resolve().parents[2] / "data" / "yaml" / "knowledge_graph.yaml"
                if kg_path.exists():
                    kg_result = import_knowledge_graph_from_file(s, kg_path)
                    print(f"🕸️  导入知识图谱: +{kg_result['added']} 条关系边")
                    if kg_result['errors']:
                        print(f"   错误: {len(kg_result['errors'])} 个")
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
  cissp path list                         # 列出学习路径
  cissp path start beginner               # 开始入门路径
  cissp path status                       # 当前路径进度
  cissp path today                        # 今日学习计划
  cissp exam start                        # 开始模拟考试
  cissp exam history                      # 考试历史
  cissp knowledge graph 1                 # 查看域1 知识图谱
  cissp knowledge prereq "安全模型"       # 查询知识点前置
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

    # ── path 子命令组 ────────────────────────────────────────
    p_path = subparsers.add_parser("path", help="学习路径规划")
    path_sub = p_path.add_subparsers(dest="path_cmd", help="路径操作")

    # path list
    p_path_list = path_sub.add_parser("list", help="列出可用学习路径")
    p_path_list.set_defaults(func=cmd_path_list)

    # path start
    p_path_start = path_sub.add_parser("start", help="开始一条学习路径")
    p_path_start.add_argument("slug", help="路径标识 (beginner/advanced/sprint)")
    p_path_start.set_defaults(func=cmd_path_start)

    # path status
    p_path_status = path_sub.add_parser("status", help="当前路径进度")
    p_path_status.set_defaults(func=cmd_path_status)

    # path today
    p_path_today = path_sub.add_parser("today", help="今日学习计划")
    p_path_today.set_defaults(func=cmd_path_today)

    # path recommend
    p_path_rec = path_sub.add_parser("recommend", help="根据当前水平推荐路径")
    p_path_rec.set_defaults(func=cmd_path_recommend)

    # ── exam 子命令组 ────────────────────────────────────────
    p_exam = subparsers.add_parser("exam", help="模拟考试")
    exam_sub = p_exam.add_subparsers(dest="exam_cmd", help="考试操作")

    # exam start
    p_exam_start = exam_sub.add_parser("start", help="开始一场模拟考试")
    p_exam_start.add_argument("-n", "--count", type=int, default=100, help="题目数量 (默认 100)")
    p_exam_start.add_argument("-t", "--time", type=int, default=180, help="考试时长分钟 (默认 180)")
    p_exam_start.add_argument("-d", "--domain", type=int, nargs="+", help="指定领域 (可多选)")
    p_exam_start.set_defaults(func=cmd_exam_start)

    # exam history
    p_exam_hist = exam_sub.add_parser("history", help="考试历史记录")
    p_exam_hist.add_argument("-n", "--limit", type=int, default=10, help="显示条数")
    p_exam_hist.set_defaults(func=cmd_exam_history)

    # exam detail
    p_exam_detail = exam_sub.add_parser("detail", help="查看某次考试详情")
    p_exam_detail.add_argument("exam_id", type=int, help="考试 ID")
    p_exam_detail.set_defaults(func=cmd_exam_detail)

    # ── knowledge 子命令组 ───────────────────────────────────
    p_know = subparsers.add_parser("knowledge", help="知识图谱")
    know_sub = p_know.add_subparsers(dest="know_cmd", help="图谱操作")

    # knowledge graph
    p_know_graph = know_sub.add_parser("graph", help="查看某领域知识图谱 (文本树)")
    p_know_graph.add_argument("domain", type=int, help="领域 ID (1-8)")
    p_know_graph.add_argument("--mermaid", action="store_true", help="输出 Mermaid 格式")
    p_know_graph.set_defaults(func=cmd_knowledge_graph)

    # knowledge prereq
    p_know_pre = know_sub.add_parser("prereq", help="查询知识点前置依赖")
    p_know_pre.add_argument("kp", help="知识点名称")
    p_know_pre.add_argument("-d", "--domain", type=int, help="领域 ID")
    p_know_pre.add_argument("--depth", type=int, default=3, help="递归深度 (默认 3)")
    p_know_pre.set_defaults(func=cmd_knowledge_prereq)

    # knowledge next
    p_know_next = know_sub.add_parser("next", help="推荐下一步学习的知识点")
    p_know_next.add_argument("kp", help="当前掌握的知识点")
    p_know_next.add_argument("-d", "--domain", type=int, help="领域 ID")
    p_know_next.set_defaults(func=cmd_knowledge_next)

    # knowledge impact
    p_know_impact = know_sub.add_parser("impact", help="分析薄弱点传播影响")
    p_know_impact.add_argument("kp", help="薄弱知识点")
    p_know_impact.add_argument("-d", "--domain", type=int, help="领域 ID")
    p_know_impact.set_defaults(func=cmd_knowledge_impact)

    # knowledge heatmap
    p_know_heat = know_sub.add_parser("heatmap", help="全领域掌握度热力图")
    p_know_heat.set_defaults(func=cmd_knowledge_heatmap)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    args.func(args)




# ═══════════════════════════════════════════════════════════
#  v2 子命令：学习路径
# ═══════════════════════════════════════════════════════════

def cmd_path_list(args):
    """列出学习路径"""
    with session_scope() as session:
        # 确保预设路径已初始化
        lp_module.init_preset_paths(session)
        paths = lp_module.list_paths(session)

    print("📚 可用学习路径")
    print("=" * 70)
    for p in paths:
        prereq = f" (前置: {', '.join(p['prerequisites'])})" if p["prerequisites"] else ""
        print(f"  🎯 {p['name']}")
        print(f"     标识: {p['slug']}{prereq}")
        print(f"     {p['description']}")
        print(f"     目标: {p['goal']}")
        print(f"     时长: {p['estimated_days']} 天  "
              f"每日 {p['daily_question_target']} 题  "
              f"难度 {p['difficulty_range']}  "
              f"{p['milestone_count']} 个里程碑")
        print()

    print(f"💡 使用 `cissp path start <标识>` 开始一条路径")


def cmd_path_start(args):
    """开始学习路径"""
    slug = args.slug
    with session_scope() as session:
        lp_module.init_preset_paths(session)
        result = lp_module.start_path(session, slug)

    if not result.get("success"):
        print(f"❌ {result.get('error', '启动失败')}")
        return

    path = result["path"]
    prog = result["progress"]
    print(f"✅ 已开始学习路径：{path['name']}")
    print()
    print(f"  📅 计划时长: {path['estimated_days']} 天")
    print(f"  🎯 每日目标: {path['daily_question_target']} 题")
    print(f"  📈 难度范围: {path['difficulty_min']}-{path['difficulty_max']}")
    print(f"  🏁 里程碑数: {path['milestone_count']} 个")
    print(f"  📆 预计完成: {prog['expected_end_date']}")
    print()
    print(f"💡 用 `cissp path today` 查看今日学习计划")


def cmd_path_status(args):
    """当前路径进度"""
    with session_scope() as session:
        status = lp_module.get_path_status(session)

    if not status:
        print("ℹ️  暂无进行中的学习路径")
        print("   使用 `cissp path list` 查看可用路径")
        return

    path = status["path"]
    prog = status["progress"]
    ms = status["current_milestone"]
    ms_status = status["milestone_status"]

    print(f"📊 学习路径进度 — {path['name']}")
    print("=" * 70)

    # 进度条
    pct = prog["completion_percent"]
    bar_len = 40
    filled = int(pct / 100 * bar_len)
    bar = "█" * filled + "░" * (bar_len - filled)
    print(f"  总进度: {bar} {pct:.1f}%")
    print(f"  开始日期: {prog['start_date']}  |  预计完成: {prog['expected_end_date']}")
    print(f"  累计答题: {prog['total_questions_done']} 题")
    print()

    print("  🏁 里程碑进度:")
    for m in ms_status:
        icon = "✅" if m["completed"] else "🔘"
        pct_ms = m["avg_mastery"] * 100
        threshold = m["threshold"] * 100
        doms = ", ".join(f"域{d}" for d in m["domains"])
        print(f"    {icon} {m['name']} ({doms})")
        print(f"       掌握度 {pct_ms:.1f}% / 目标 {threshold:.0f}%")
    print()

    if ms:
        print(f"  🎯 当前阶段: {ms['name']}")
        print(f"     {ms['description']}")


def cmd_path_today(args):
    """今日学习计划"""
    with session_scope() as session:
        plan = lp_module.generate_daily_plan(session)

    print(f"📅 今日学习计划 — {plan['date']}")
    print("=" * 70)

    if not plan.get("has_path"):
        print(f"  ℹ️  {plan['suggestion']}")
        rec = plan.get("recommended_path", {})
        if rec:
            print(f"  💡 推荐路径: {rec['recommended_slug']} — {rec['reason']}")
        return

    print(f"  📚 当前路径: {plan['path_name']}")
    print(f"  🎯 今日目标: {plan['daily_question_target']} 题")
    print(f"  🎮 练习模式: {plan['recommended_mode']} ({plan['recommended_mode_desc']})")
    print(f"  📍 当前里程碑: {plan['current_milestone']}")
    print(f"  📈 总进度: {plan['completion_percent']:.1f}%")
    print(f"  ⏳ 预计剩余: {plan['days_remaining_estimate']} 天")

    if plan.get("focus_knowledge_points"):
        print()
        print("  🔍 今日重点知识点:")
        for i, kp in enumerate(plan["focus_knowledge_points"], 1):
            print(f"     {i}. {kp}")

    if plan.get("tip"):
        print()
        print(f"  💡 {plan['tip']}")

    print()
    print(f"  ▶  开始练习: cissp start --mode {plan['recommended_mode']} "
          f"--count {plan['daily_question_target']}")


def cmd_path_recommend(args):
    """路径推荐"""
    with session_scope() as session:
        rec = lp_module.recommend_path(session)

    stats = rec["user_stats"]
    print("🎯 路径推荐")
    print("=" * 60)
    print(f"  📊 当前水平:")
    print(f"     累计答题: {stats['total_questions_answered']} 题")
    print(f"     总体正确率: {stats['overall_accuracy']*100:.1f}%")
    if stats["completed_paths"]:
        print(f"     已完成路径: {', '.join(stats['completed_paths'])}")
    print()
    print(f"  ✨ 推荐路径: {rec['recommended_slug']}")
    print(f"     原因: {rec['reason']}")
    if not rec["can_start"]:
        print(f"     ⚠️  需要先完成: {', '.join(rec['missing_prerequisites'])}")
    else:
        print(f"     ✅ 可以开始！用 `cissp path start {rec['recommended_slug']}` 启动")


# ═══════════════════════════════════════════════════════════
#  v2 子命令：模拟考试
# ═══════════════════════════════════════════════════════════

def cmd_exam_start(args):
    """开始模拟考试（交互式）"""
    count = args.count
    duration = args.time
    domains = args.domain

    with session_scope() as session:
        result = exam_mod.create_exam(
            session,
            question_count=count,
            duration_minutes=duration,
            domain_filter=domains,
        )
        if not result.get("success"):
            print(f"❌ {result.get('error', '创建考试失败')}")
            return

        exam_id = result["exam_id"]

        # 开始考试
        start_result = exam_mod.start_exam(session, exam_id)
        if not start_result.get("success"):
            print(f"❌ {start_result.get('error')}")
            return

        print(f"📝 模拟考试开始 — {result['title']}")
        print(f"   考试 ID: {exam_id}")
        print(f"   题目: {result['total_questions']} 题")
        print(f"   时长: {duration} 分钟")
        print(f"   操作: 输入选项 A/B/C/D 作答")
        print(f"         p 暂停  |  f 标记  |  q 交卷  |  #<num> 跳题")
        print()

        import time as _time
        answered = 0
        correct_count = 0
        total_time = 0

        while True:
            q_data = exam_mod.get_current_question(session, exam_id)
            if q_data is None:
                print("✅ 已答完所有题目")
                break

            idx = q_data["index"]
            total = q_data["total"]
            print(f"--- [{idx}/{total}] ---")
            print(f"[域{q_data['domain']} · 难度{q_data['difficulty']} "
                  f"· {q_data['question_type']}] {q_data['stem']}")
            print()

            opt_keys = sorted(q_data["options"].keys())
            for opt in opt_keys:
                marker = " ← 已答" if q_data.get("user_answer") == opt else ""
                print(f"  {opt}. {q_data['options'][opt]}{marker}")
            print()

            t0 = _time.time()
            try:
                ans = input("你的答案: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n\n已中断，考试已暂停。")
                exam_mod.pause_exam(session, exam_id)
                break
            elapsed = int(_time.time() - t0)
            total_time += elapsed

            if not ans:
                continue

            upper_ans = ans.upper()

            # 特殊指令
            if upper_ans == 'Q':
                confirm = input("确认交卷？(y/n): ").strip().upper()
                if confirm == 'Y':
                    break
                continue

            if upper_ans == 'P':
                pause_result = exam_mod.pause_exam(session, exam_id)
                print(f"⏸️  考试已暂停（剩余 {pause_result['time_remaining_sec']} 秒）")
                print(f"   下次用 `cissp exam resume {exam_id}` 继续")
                return

            if upper_ans == 'F':
                flag_result = exam_mod.flag_question(session, exam_id)
                print(f"  🏷️  已{'标记' if flag_result['flagged'] else '取消标记'}")
                continue

            # 跳题：#5 跳到第 5 题
            if ans.startswith('#'):
                try:
                    target = int(ans[1:]) - 1  # 转 0-based
                    goto_result = exam_mod.goto_question(session, exam_id, target)
                    if goto_result.get("success"):
                        continue
                    else:
                        print(f"  ⚠️  {goto_result.get('error')}")
                        continue
                except ValueError:
                    print("  ⚠️  无效题号")
                    continue

            # 正常作答
            if upper_ans[0] in 'ABCDEFT' or upper_ans.startswith(('TRUE', 'FALSE')):
                # 提取答案字母
                letter = upper_ans.split(',')[0].strip()
                ans_result = exam_mod.answer_current(
                    session, exam_id, upper_ans, time_spent_sec=elapsed
                )
                if not ans_result.get("success"):
                    print(f"  ❌ {ans_result.get('error')}")
                    continue

                answered += 1

                if ans_result.get("is_last"):
                    print("\n📋 已到最后一题")
                    confirm = input("现在交卷？(y/n): ").strip().upper()
                    if confirm == 'Y':
                        break

                if ans_result.get("status") in ("submitted", "timeout"):
                    # 时间到自动交卷
                    print("\n⏰ 时间到，自动交卷")
                    break
            else:
                print("  ⚠️  无效输入")

        # 交卷
        print("\n" + "=" * 60)
        print("📋 正在评分...")
        submit_result = exam_mod.submit_exam(session, exam_id)

    _print_exam_result(submit_result)


def _print_exam_result(result: dict):
    """打印考试结果"""
    if not result.get("success"):
        print(f"❌ {result.get('error')}")
        return

    print("\n" + "=" * 60)
    score = result["score"]
    passed = result["passed"]
    status_icon = "🎉" if passed else "❌"
    status_text = "通过" if passed else "未通过"

    print(f"  {status_icon} 考试结果: {status_text}")
    print(f"  📊 得分: {score:.1f} / 100  "
          f"(及格线 {result['pass_threshold']:.0f} 分)")
    print(f"  ✅ 正确: {result['total_correct']} / {result['total_questions']} 题")
    print(f"  ❌ 错题: {result['wrong_count']} 道")
    print()

    # 领域分数
    print("  各领域得分:")
    for ds in result.get("domain_scores", []):
        bar_len = 15
        filled = int(ds["score"] / 100 * bar_len)
        bar = "█" * filled + "░" * (bar_len - filled)
        flag = " ⚠️ 薄弱" if ds["score"] < 70 and ds["total"] >= 3 else ""
        print(f"    域{ds['domain']} {ds['domain_name']:<12} "
              f"{bar} {ds['score']:>5.1f}% "
              f"({ds['correct']}/{ds['total']}){flag}")

    # 薄弱领域
    weak = result.get("weak_domains", [])
    if weak:
        print()
        print("  ⚠️  薄弱领域:")
        for w in weak:
            print(f"     • 域{w['domain']} {w['domain_name']}: {w['score']:.1f}%")

    # 错题概览（前 5 道）
    wrong = result.get("wrong_questions", [])
    if wrong:
        print()
        print(f"  📝 错题解析（前 {min(5, len(wrong))} 题）:")
        for i, w in enumerate(wrong[:5], 1):
            print(f"     {i}. [{w['domain_name']}] {w['stem'][:50]}...")
            print(f"        你的答案: {w['user_answer']}  |  正确: {w['correct_answer']}")
            if w.get("explanation"):
                print(f"        解析: {w['explanation'][:60]}")

    print()
    print(f"  💡 查看完整错题: cissp exam detail {result['exam_id']}")
    print(f"  💡 查看考试历史: cissp exam history")


def cmd_exam_history(args):
    """考试历史"""
    with session_scope() as session:
        history = exam_mod.get_exam_history(session, limit=args.limit)
        curve = exam_mod.get_score_curve(session)

    if not history:
        print("ℹ️  暂无考试记录")
        print("   使用 `cissp exam start` 开始第一次模拟考试")
        return

    print("📜 考试历史记录")
    print("=" * 70)
    print(f"  {'#':>2} {'ID':>4} {'日期':<12} {'分数':>7} {'状态':>6} {'题数':>5} {'结果':>6}")
    print(f"  {'─'*2} {'─'*4} {'─'*12} {'─'*7} {'─'*6} {'─'*5} {'─'*6}")

    for i, e in enumerate(history, 1):
        score_str = f"{e['score']:.1f}" if e.get("score") is not None else "-"
        passed_str = "✅通过" if e.get("passed") else "❌未过"
        date_str = e["submitted_at"][:10] if e.get("submitted_at") else "-"
        status_map = {"submitted": "已交卷", "timeout": "超时"}
        status_str = status_map.get(e["status"], e["status"])
        print(f"  {i:>2} {e['exam_id']:>4} {date_str:<12} "
              f"{score_str:>7} {status_str:>6} "
              f"{e['total_questions']:>5} {passed_str:>6}")

    # 成绩趋势
    if len(curve) >= 2:
        print()
        print("📈 成绩趋势:")
        scores = [c["score"] for c in curve]
        avg = sum(scores) / len(scores)
        trend = scores[-1] - scores[0]
        trend_str = f"+{trend:.1f}" if trend >= 0 else f"{trend:.1f}"
        print(f"     共 {len(curve)} 次考试  |  平均分 {avg:.1f}  "
              f"|  趋势 {trend_str} 分")


def cmd_exam_detail(args):
    """考试详情"""
    with session_scope() as session:
        detail = exam_mod.get_exam_detail(session, args.exam_id)
        if not detail:
            print("❌ 考试不存在")
            return
        compare = exam_mod.compare_with_previous(session, args.exam_id)

    print(f"📋 考试详情 — {detail['title']}")
    print("=" * 70)
    print(f"  考试 ID: {detail['exam_id']}")
    print(f"  状态: {detail['status']}")
    print(f"  开始: {detail['started_at']}")
    print(f"  交卷: {detail['submitted_at']}")
    print()
    print(f"  得分: {detail['score']:.1f} 分  "
          f"({'通过' if detail['passed'] else '未通过'})")
    print(f"  正确: {detail['total_correct']} / {detail['total_questions']} 题")
    print()

    # 对比
    if compare and not compare.get("error"):
        if compare.get("previous"):
            prev = compare["previous"]
            print(f"  📊 对比上次（{prev['date']}，{prev['score']:.1f} 分）: "
                  f"{compare['change']:+.1f} 分 ({compare['trend']})")
            if compare.get("most_improved"):
                mi = compare["most_improved"]
                print(f"     进步最大: {mi['domain_name']} (+{mi['change']:.1f}%)")
            if compare.get("most_declined"):
                md = compare["most_declined"]
                print(f"     退步最大: {md['domain_name']} ({md['change']:.1f}%)")
        else:
            print(f"  📊 {compare.get('message', '')}")
        print()

    # 错题列表
    wrong = detail.get("wrong_questions", [])
    if wrong:
        print(f"  ❌ 错题列表（共 {len(wrong)} 题）:")
        for i, w in enumerate(wrong, 1):
            print(f"     {i}. [{w['domain_name']}] {w['stem'][:60]}")
            print(f"        你的: {w['user_answer']}  |  正确: {w['correct_answer']}")
            if w.get("explanation"):
                print(f"        解析: {w['explanation']}")
            print()


# ═══════════════════════════════════════════════════════════
#  v2 子命令：知识图谱
# ═══════════════════════════════════════════════════════════

def cmd_knowledge_graph(args):
    """查看知识图谱"""
    domain = args.domain
    if domain < 1 or domain > 8:
        print("❌ 领域 ID 必须在 1-8 之间")
        return

    with session_scope() as session:
        if args.mermaid:
            mermaid = kg_mod.to_mermaid(session, domain)
            print("```mermaid")
            print(mermaid)
            print("```")
        else:
            tree = kg_mod.to_text_tree(session, domain)
            print(tree)


def cmd_knowledge_prereq(args):
    """查询前置知识点"""
    kp_name = args.kp
    domain = args.domain
    depth = args.depth

    with session_scope() as session:
        prereqs = kg_mod.get_prerequisites(session, kp_name, domain, depth=depth)

    if not prereqs:
        print(f"ℹ️  未找到「{kp_name}」的前置知识点")
        print("   （可能知识点不存在，或尚未建立图谱关系）")
        return

    print(f"🔗 「{kp_name}」的前置依赖（深度 {depth}）")
    print("=" * 60)

    by_depth = {}
    for p in prereqs:
        d = p["depth"]
        by_depth.setdefault(d, []).append(p)

    for d in sorted(by_depth.keys()):
        print(f"  第 {d} 层:")
        for p in by_depth[d]:
            bar = _mastery_bar_short(p["mastery"])
            print(f"    • {p['name']}  (域{p['domain']}) "
                  f"{bar} {p['mastery']*100:.0f}%")


def cmd_knowledge_next(args):
    """推荐下一步学习的知识点"""
    kp_name = args.kp
    domain = args.domain

    with session_scope() as session:
        suggestions = kg_mod.suggest_next_kps(session, kp_name, domain)

    if not suggestions:
        print(f"ℹ️  暂时没有基于「{kp_name}」的后续学习建议")
        return

    print(f"🎯 掌握「{kp_name}」之后，可以学习:")
    print("=" * 60)
    for i, s in enumerate(suggestions, 1):
        bar = _mastery_bar_short(s["mastery"])
        print(f"  {i}. {s['name']}  (域{s['domain']})  "
              f"{bar} {s['mastery']*100:.0f}%")


def cmd_knowledge_impact(args):
    """分析薄弱点传播影响"""
    kp_name = args.kp
    domain = args.domain

    with session_scope() as session:
        result = kg_mod.analyze_weak_propagation(session, kp_name, domain)

    print(f"🌊 薄弱点传播分析 — 「{result.source_kp}」")
    print("=" * 60)

    if result.total_affected == 0:
        print("  暂无受影响的后继知识点")
        return

    print(f"  受影响知识点: {result.total_affected} 个")
    print()

    print(f"  {'#':>2} {'知识点':<25} {'域':>2} {'影响度':>7} {'距离':>5} {'掌握度':>7}")
    print(f"  {'─'*2} {'─'*25} {'─'*2} {'─'*7} {'─'*5} {'─'*7}")

    for i, kp in enumerate(result.affected_kps[:15], 1):
        impact_bar = "█" * int(kp["impact"] * 20)
        print(f"  {i:>2} {kp['name']:<25} {kp['domain']:>2} "
              f"{kp['impact']:>7.4f} {kp['distance']:>5} "
              f"{kp['mastery']*100:>6.1f}%")

    if result.total_affected > 15:
        print(f"  ... 还有 {result.total_affected - 15} 个受影响知识点")

    print()
    print("  💡 建议：先攻克源头薄弱点，再学后续知识点，事半功倍")


def cmd_knowledge_heatmap(args):
    """掌握度热力图"""
    with session_scope() as session:
        heatmap = kg_mod.mastery_heatmap(session)
    print(heatmap)


def _mastery_bar_short(mastery: float) -> str:
    """短掌握度条"""
    filled = int(mastery * 10)
    return "█" * filled + "░" * (10 - filled)



if __name__ == "__main__":
    main()
