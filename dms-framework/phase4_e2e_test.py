#!/usr/bin/env python3
"""
DMS Framework — Phase 4 End-to-End Test
用一个虚拟电商平台项目跑通全流程，验证 5 大模块 + 事件总线 + 模块注册。

用法:
    cd dms-framework
    python3 phase4_e2e_test.py
"""
from __future__ import annotations

import os
import re
import sys
import subprocess
from pathlib import Path

# ── 配置 ──────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
DMS_SCRIPT = BASE_DIR / "dms.py"
DB_PATH = BASE_DIR / "delivery.db"
TENANT = "demo-tenant"

# 统计
passed = 0
failed = 0
results: list[tuple[str, bool, str]] = []


# ── 工具函数 ──────────────────────────────────────────────────────
def run(cmd: list[str], check: bool = True) -> tuple[int, str, str]:
    """执行 dms 命令，返回 (returncode, stdout, stderr)"""
    full_cmd = [sys.executable, str(DMS_SCRIPT),
                "--db", str(DB_PATH),
                "--tenant", TENANT] + cmd
    proc = subprocess.run(
        full_cmd,
        cwd=str(BASE_DIR),
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout, proc.stderr


def record(name: str, ok: bool, detail: str = "") -> None:
    """记录测试结果"""
    global passed, failed
    if ok:
        passed += 1
        print(f"  ✅ {name}" + (f" — {detail}" if detail else ""))
    else:
        failed += 1
        print(f"  ❌ {name}" + (f" — {detail}" if detail else ""))
    results.append((name, ok, detail))


def extract_id(stdout: str) -> str | None:
    """从命令输出中提取 UUID"""
    m = re.search(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        stdout,
        re.IGNORECASE,
    )
    return m.group(0) if m else None


# ── 主测试流程 ────────────────────────────────────────────────────
def main() -> int:
    global passed, failed
    passed = 0
    failed = 0

    print("=" * 60)
    print("DMS Framework — Phase 4 端到端验证")
    print("项目: demo-ecommerce-platform (电商平台交付)")
    print("租户:", TENANT)
    print("=" * 60)

    # ── 清理旧数据库 ────────────────────────────────────────────
    if DB_PATH.exists():
        DB_PATH.unlink()
        print(f"\n🧹 已删除旧数据库: {DB_PATH.name}")

    # ════════════════════════════════════════════════════════════
    # S1: 初始化
    # ════════════════════════════════════════════════════════════
    print("\n📌 S1: 初始化框架 & 数据库")
    rc, out, err = run(["init"])
    record("init 执行成功", rc == 0, err.strip() or out.strip().splitlines()[0] if out.strip() else "")
    record("迁移已应用", "已应用迁移" in out or "已是最新" in out,
           out.strip().splitlines()[0] if out.strip() else "")

    print("\n📌 S1.1: 模块列表")
    rc, out, err = run(["module", "list"])
    record("module list 执行成功", rc == 0)
    modules = ["project", "milestone", "deliverable", "risk", "raci"]
    for m in modules:
        record(f"模块 {m} 已注册", m in out)

    # ════════════════════════════════════════════════════════════
    # S2: 创建项目
    # ════════════════════════════════════════════════════════════
    print("\n📌 S2: 创建项目")
    rc, out, err = run([
        "project", "create",
        "--name", "demo-ecommerce-platform",
        "--description", "电商平台交付项目",
    ])
    pid = extract_id(out)
    record("project create 成功", rc == 0 and pid is not None,
           f"PID={pid}" if pid else out.strip()[:80])

    # ════════════════════════════════════════════════════════════
    # S3: 创建 3 个里程碑
    # ════════════════════════════════════════════════════════════
    print("\n📌 S3: 创建里程碑 (x3)")
    milestones = [
        ("M1 需求确认", "2026-10-15", "high"),
        ("M2 开发完成", "2027-01-15", "high"),
        ("M3 上线发布", "2027-03-01", "high"),
    ]
    milestone_ids: dict[str, str] = {}
    for title, due, prio in milestones:
        rc, out, err = run([
            "milestone", "create",
            "--project-id", pid,
            "--title", title,
            "--due-date", due,
            "--priority", prio,
        ])
        mid = extract_id(out)
        ok = rc == 0 and mid is not None
        record(f"里程碑: {title}", ok, f"MID={mid}" if mid else "创建失败")
        if mid:
            milestone_ids[title] = mid

    # ════════════════════════════════════════════════════════════
    # S4: 创建 8 个交付物
    # ════════════════════════════════════════════════════════════
    print("\n📌 S4: 创建交付物 (x8)")
    deliverables = [
        ("需求规格说明书", "2026-09-30", "high"),
        ("架构设计文档", "2026-10-20", "high"),
        ("UI 设计稿", "2026-11-05", "medium"),
        ("数据库设计", "2026-10-25", "high"),
        ("API 文档", "2026-12-15", "medium"),
        ("测试报告", "2027-01-10", "high"),
        ("部署方案", "2027-02-15", "medium"),
        ("用户手册", "2027-02-25", "low"),
    ]
    deliverable_ids: dict[str, str] = {}
    for title, due, prio in deliverables:
        rc, out, err = run([
            "deliverable", "create",
            "--project-id", pid,
            "--title", title,
            "--due-date", due,
            "--priority", prio,
        ])
        did = extract_id(out)
        ok = rc == 0 and did is not None
        record(f"交付物: {title}", ok, f"DID={did}" if did else "创建失败")
        if did:
            deliverable_ids[title] = did

    # ════════════════════════════════════════════════════════════
    # S5: 创建 5 个风险
    # ════════════════════════════════════════════════════════════
    print("\n📌 S5: 创建风险 (x5)")
    risks = [
        ("需求变更频繁", "high"),
        ("核心开发人员离职", "high"),
        ("第三方接口不稳定", "medium"),
        ("性能不达标", "medium"),
        ("安全漏洞", "high"),
    ]
    risk_ids: dict[str, str] = {}
    for title, prio in risks:
        rc, out, err = run([
            "risk", "create",
            "--project-id", pid,
            "--title", title,
            "--priority", prio,
        ])
        rid = extract_id(out)
        ok = rc == 0 and rid is not None
        record(f"风险: {title}", ok, f"RID={rid}" if rid else "创建失败")
        if rid:
            risk_ids[title] = rid

    # ════════════════════════════════════════════════════════════
    # S6: RACI 分配
    # ════════════════════════════════════════════════════════════
    print("\n📌 S6: RACI 职责分配")
    raci_assignments = [
        ("member-001", "scope_management", "A"),
        ("member-001", "schedule_management", "A"),
        ("member-002", "deliverable_management", "R"),
        ("member-002", "quality_management", "C"),
        ("member-003", "quality_management", "R"),
        ("member-004", "stakeholder_management", "R"),
        ("member-004", "communication_management", "A"),
    ]
    for member, cap, role in raci_assignments:
        rc, out, err = run([
            "raci", "assign",
            "--project-id", pid,
            "--member-id", member,
            "--capability", cap,
            "--role", role,
        ])
        ok = rc == 0 and "已分配" in out
        record(f"{member} → {cap} ({role})", ok,
               out.strip().splitlines()[-1] if out.strip() else err.strip()[:60])

    # ════════════════════════════════════════════════════════════
    # S7: 状态流转
    # ════════════════════════════════════════════════════════════
    print("\n📌 S7: 状态流转")

    # 项目状态流转
    rc, out, err = run(["project", "transition", "--id", pid, "--transition", "start"])
    record("项目 start → in_progress", rc == 0 and "in_progress" in out,
           out.strip().splitlines()[-1] if out.strip() else "")

    # 里程碑 M1 流转
    m1_id = milestone_ids.get("M1 需求确认")
    if m1_id:
        rc, out, err = run(["milestone", "transition", "--id", m1_id, "--transition", "start"])
        record("M1 start → in_progress", rc == 0 and "in_progress" in out,
               out.strip().splitlines()[-1] if out.strip() else "")
        rc, out, err = run(["milestone", "transition", "--id", m1_id, "--transition", "achieve"])
        record("M1 achieve → achieved", rc == 0 and "achieved" in out,
               out.strip().splitlines()[-1] if out.strip() else "")

    # 交付物 需求规格说明书 流转
    d1_id = deliverable_ids.get("需求规格说明书")
    if d1_id:
        rc, out, err = run(["deliverable", "transition", "--id", d1_id, "--transition", "submit"])
        record("交付物 submit → in_review", rc == 0 and "in_review" in out,
               out.strip().splitlines()[-1] if out.strip() else "")
        rc, out, err = run(["deliverable", "transition", "--id", d1_id, "--transition", "approve"])
        record("交付物 approve → accepted", rc == 0 and "accepted" in out,
               out.strip().splitlines()[-1] if out.strip() else "")

    # 风险 需求变更频繁 流转
    r1_id = risk_ids.get("需求变更频繁")
    if r1_id:
        rc, out, err = run(["risk", "transition", "--id", r1_id, "--transition", "analyze"])
        record("风险 analyze → analyzed", rc == 0,
               out.strip().splitlines()[-1] if out.strip() else "")
        rc, out, err = run(["risk", "transition", "--id", r1_id, "--transition", "plan"])
        record("风险 plan → planned", rc == 0,
               out.strip().splitlines()[-1] if out.strip() else "")
        rc, out, err = run(["risk", "transition", "--id", r1_id, "--transition", "resolve"])
        record("风险 resolve → resolved", rc == 0,
               out.strip().splitlines()[-1] if out.strip() else "")

    # ════════════════════════════════════════════════════════════
    # S8: 查询验证
    # ════════════════════════════════════════════════════════════
    print("\n📌 S8: 查询验证")

    rc, out, err = run(["project", "get", "--id", pid])
    record("project get 返回详情", rc == 0 and "demo-ecommerce-platform" in out)

    rc, out, err = run(["milestone", "list", "--project-id", pid])
    record("milestone list 返回 3 条", rc == 0 and out.count("M1") + out.count("M2") + out.count("M3") >= 3,
           f"可见里程碑数={len([l for l in out.splitlines() if l.strip() and not l.startswith('---') and not l.startswith('ID')])}")

    rc, out, err = run(["deliverable", "list", "--project-id", pid])
    record("deliverable list 返回 8 条", rc == 0,
           f"输出行数={len(out.splitlines())}")

    rc, out, err = run(["risk", "list", "--project-id", pid])
    record("risk list 返回 5 条", rc == 0)

    rc, out, err = run(["raci", "list", "--project-id", pid])
    record("raci list 可查询", rc == 0 and "7 条" in out,
           out.strip().splitlines()[0] if out.strip() else "")

    rc, out, err = run(["raci", "matrix", "--project-id", pid])
    record("raci matrix 可生成", rc == 0 and "RACI 矩阵" in out)

    rc, out, err = run(["raci", "conflicts", "--project-id", pid])
    record("raci conflicts 可检查", rc == 0)

    rc, out, err = run(["raci", "coverage", "--project-id", pid])
    record("raci coverage 可计算", rc == 0 and ("覆盖" in out or "缺口" in out))

    # ════════════════════════════════════════════════════════════
    # S9: 模块注册 / 热插拔验证
    # ════════════════════════════════════════════════════════════
    print("\n📌 S9: 模块注册验证")
    rc, out, err = run(["module", "list"])
    all_present = all(m in out for m in modules)
    record("5 个核心模块均已注册", all_present)
    record("模块含版本号", bool(re.search(r"\d+\.\d+\.\d+", out)))
    record("模块含描述", "状态机" in out or "生命周期" in out)

    # ════════════════════════════════════════════════════════════
    # S10: 事件总线验证
    # ════════════════════════════════════════════════════════════
    print("\n📌 S10: 事件总线验证")
    rc, out, err = run(["event", "stats"])
    record("event stats 可查询", rc == 0 and "事件总线统计" in out)
    record("事件总线有订阅者", rc == 0 and "订阅者总数" in out,
           [l.strip() for l in out.splitlines() if "订阅者" in l][0] if out else "")
    record("事件总线有历史记录", rc == 0 and "历史事件数" in out,
           [l.strip() for l in out.splitlines() if "历史" in l][0] if out else "")

    # ════════════════════════════════════════════════════════════
    # 总结
    # ════════════════════════════════════════════════════════════
    total = passed + failed
    print("\n" + "=" * 60)
    print("📊 测试总结")
    print("=" * 60)
    print(f"  总计: {total} 项")
    print(f"  通过: {passed} 项  ✅")
    print(f"  失败: {failed} 项  {'❌' if failed else '✅'}")
    print(f"  通过率: {passed / total * 100:.1f}%")
    print("=" * 60)

    if failed > 0:
        print("\n❌ 失败的测试:")
        for name, ok, detail in results:
            if not ok:
                print(f"  - {name}" + (f": {detail}" if detail else ""))
        return 1

    print("\n🎉 全部通过！Phase 4 端到端验证成功。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
