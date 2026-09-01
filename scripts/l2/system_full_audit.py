#!/usr/bin/env python3
"""系统全量健康检查脚本

L2 基础设施层 — 标准化健康检查流程。
覆盖：运行时、服务、资产、架构符合性、垃圾清理、备份状态。

用法：
  python3 scripts/l2/system_full_audit.py          # 完整检查
  python3 scripts/l2/system_full_audit.py --json   # JSON 输出
  python3 scripts/l2/system_full_audit.py --quick   # 快速检查（仅关键项）

已验证 2026-09-01。
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

WORKSPACE = Path(__file__).parent.parent.parent.parent
DATA_DIR = Path.home() / ".openclaw" / "data"
BACKUP_DIR = Path.home() / ".openclaw" / "backups"
DOCS_DIR = WORKSPACE / "docs" / "architecture"
L4_SCRIPTS = WORKSPACE / "scripts" / "l4" / "delivery_center"


def run(cmd: str, timeout: int = 15) -> tuple[int, str, str]:
    """执行 shell 命令"""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"
    except Exception as e:
        return -1, "", str(e)


def check(name: str, status: str, detail: str) -> dict:
    """记录检查项"""
    return {"name": name, "status": status, "detail": detail}


def section(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f" {title}")
    print(f"{'=' * 60}")


def audit_system_status() -> list[dict]:
    """1. 系统状态检测"""
    results = []

    # openclaw status
    rc, out, _ = run("openclaw status 2>&1 | head -20")
    if rc == 0:
        results.append(check("openclaw status", "✅", "Gateway 运行中"))
    else:
        results.append(check("openclaw status", "❌", out[:200]))

    # gateway status
    rc, out, _ = run("openclaw gateway status 2>&1 | head -10")
    if "running" in out.lower() or "ok" in out.lower():
        results.append(check("gateway", "✅", "Gateway 健康"))
    else:
        results.append(check("gateway", "⚠️", out[:200]))

    # channels
    rc, out, _ = run("openclaw channels list --all 2>&1 | grep -i wecom")
    if rc == 0 and "OK" in out:
        results.append(check("wecom channel", "✅", "WeCom 已启用"))
    else:
        results.append(check("wecom channel", "⚠️", out[:200]))

    # cron
    rc, out, _ = run("openclaw cron list --all 2>&1")
    if rc == 0:
        lines = out.split("\n")
        error_count = sum(1 for l in lines if "error" in l.lower())
        if error_count > 0:
            results.append(check("cron tasks", "⚠️", f"{error_count} 个任务异常"))
        else:
            results.append(check("cron tasks", "✅", "全部正常"))
    else:
        results.append(check("cron tasks", "❌", out[:200]))

    return results


def audit_services() -> list[dict]:
    """2. 系统各服务状态检测"""
    results = []

    # LaunchAgent
    rc, out, _ = run("launchctl list | grep openclaw")
    if rc == 0 and out:
        results.append(check("LaunchAgent", "✅", out[:200]))
    else:
        results.append(check("LaunchAgent", "⚠️", "未检测到 openclaw 服务"))

    # model-scheduling
    rc, out, _ = run("launchctl list | grep model-scheduling")
    if rc == 0 and out:
        results.append(check("model-scheduling", "✅", "运行中"))
    else:
        results.append(check("model-scheduling", "⚠️", "未运行"))

    # 进程
    rc, out, _ = run("ps aux | grep -i 'openclaw' | grep -v grep | wc -l")
    if rc == 0 and int(out) > 0:
        results.append(check("processes", "✅", f"{out} 个进程"))
    else:
        results.append(check("processes", "❌", "无进程"))

    return results


def audit_assets() -> list[dict]:
    """3. 自研资产状态检测"""
    results = []

    # L2 DESIGN.md
    design_dir = DOCS_DIR / "components"
    if design_dir.exists():
        count = len(list(design_dir.rglob("DESIGN.md")))
        results.append(check("L2 DESIGN.md", "✅", f"{count} 个组件"))
    else:
        results.append(check("L2 DESIGN.md", "⚠️", f"目录不存在: {design_dir}"))

    # L4 Python files
    if L4_SCRIPTS.exists():
        count = len(list(L4_SCRIPTS.rglob("*.py")))
        results.append(check("L4 Python files", "✅", f"{count} 个文件"))
    else:
        results.append(check("L4 Python files", "⚠️", f"目录不存在: {L4_SCRIPTS}"))

    # 配置文件
    config_dir = L4_SCRIPTS / "config"
    if config_dir.exists():
        count = len(list(config_dir.glob("*.json")))
        results.append(check("config files", "✅", f"{count} 个配置"))
    else:
        results.append(check("config files", "⚠️", f"目录不存在: {config_dir}"))

    # 数据库
    db_path = DATA_DIR / "bdms.db"
    if db_path.exists():
        rc, out, _ = run(f"sqlite3 {db_path} '.tables'")
        if rc == 0:
            tables = out.split()
            results.append(check("database tables", "✅", f"{len(tables)} 个表"))

            # 关键表行数
            rc, out, _ = run(
                f"sqlite3 {db_path} \"SELECT 'oa_contracts', COUNT(*) FROM oa_contracts "
                f"UNION ALL SELECT 'revenue_vouchers', COUNT(*) FROM revenue_vouchers "
                f"UNION ALL SELECT 'acceptance_vouchers', COUNT(*) FROM acceptance_vouchers;\""
            )
            if rc == 0:
                results.append(check("database rows", "✅", out.replace("\n", ", ")))
    else:
        results.append(check("database", "❌", f"数据库不存在: {db_path}"))

    # 知识库
    rc, out, _ = run(f"python3 {WORKSPACE}/scripts/kb_index.py --stats 2>/dev/null | head -5")
    if rc == 0 and out:
        results.append(check("knowledge base", "✅", out[:200]))
    else:
        results.append(check("knowledge base", "⚠️", "kb_index 不可用"))

    return results


def audit_official_compliance() -> list[dict]:
    """4. 官方文档适配性检测"""
    results = []

    # tools.profile
    rc, out, _ = run("openclaw config get tools.profile 2>/dev/null")
    if rc == 0:
        results.append(check("tools.profile", "✅", out.strip()))

    # tools.alsoAllow
    rc, out, _ = run("openclaw config get tools.alsoAllow 2>/dev/null")
    if rc == 0:
        results.append(check("tools.alsoAllow", "✅", out.strip()[:200]))

    # memory search
    rc, out, _ = run("openclaw config get memory.search.provider 2>/dev/null")
    if rc == 0:
        results.append(check("memory.search", "✅", out.strip()))

    return results


def audit_architecture_compliance() -> list[dict]:
    """5. 系统架构文档符合性检测"""
    results = []

    # ADR
    rc, out, _ = run(
        f"find {DOCS_DIR}/../knowledge-base/by-category/project-experience/adr -name '*.md' | wc -l"
    )
    if rc == 0:
        results.append(check("ADR count", "✅", f"{out.strip()} 篇"))

    # EXP
    rc, out, _ = run(
        f"find {DOCS_DIR}/../knowledge-base/by-category/project-experience/correct -name '*.md' | wc -l"
    )
    if rc == 0:
        results.append(check("EXP count", "✅", f"{out.strip()} 篇"))

    # 架构文档版本
    rc, out, _ = run(f"grep '文档版本' {DOCS_DIR}/00-system-architecture.md | head -1")
    if rc == 0:
        results.append(check("architecture doc", "✅", out.strip()[:100]))

    return results


def audit_garbage() -> list[dict]:
    """6. 垃圾清理检测"""
    results = []

    # 僵尸进程
    rc, out, _ = run("ps aux | grep 'defunct' | grep -v grep | wc -l")
    if rc == 0 and int(out) == 0:
        results.append(check("zombie processes", "✅", "无僵尸进程"))
    else:
        results.append(check("zombie processes", "⚠️", f"{out} 个僵尸进程"))

    # .trash
    trash_dir = WORKSPACE / ".trash"
    if trash_dir.exists():
        rc, out, _ = run(f"du -sh {trash_dir}")
        results.append(check(".trash", "⚠️", f"存在 ({out.split()[0]})"))
    else:
        results.append(check(".trash", "✅", "已清理"))

    # 临时文件
    rc, out, _ = run(f"find {DATA_DIR} -name '*.tmp' -o -name '*.bak' 2>/dev/null | wc -l")
    if rc == 0:
        count = int(out)
        if count == 0:
            results.append(check("temp files", "✅", "无临时文件"))
        else:
            results.append(check("temp files", "⚠️", f"{count} 个临时文件"))

    return results


def audit_backups() -> list[dict]:
    """7. 备份状态检查"""
    results = []

    # memory-snapshot
    snap_dir = BACKUP_DIR / "memory-snapshot"
    if snap_dir.exists():
        rc, out, _ = run(f"ls -lt {snap_dir} 2>/dev/null | head -3")
        if rc == 0 and out:
            results.append(check("memory-snapshot", "✅", out.split("\n")[0][:100]))
        else:
            results.append(check("memory-snapshot", "⚠️", "目录为空"))
    else:
        results.append(check("memory-snapshot", "❌", "目录不存在"))

    # git
    rc, out, _ = run(f"git -C {WORKSPACE} log --oneline -3")
    if rc == 0:
        results.append(check("git latest", "✅", out.replace("\n", " | ")))

    return results


def main():
    parser = argparse.ArgumentParser(description="BDMS 系统全量健康检查")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    parser.add_argument("--quick", action="store_true", help="快速检查（仅关键项）")
    args = parser.parse_args()

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    all_results = {
        "timestamp": now,
        "sections": {},
    }

    sections = [
        ("1. 系统状态检测", audit_system_status),
        ("2. 系统各服务状态检测", audit_services),
        ("3. 自研资产状态检测", audit_assets),
        ("4. 官方文档适配性检测", audit_official_compliance),
        ("5. 系统架构文档符合性检测", audit_architecture_compliance),
        ("6. 垃圾清理检测", audit_garbage),
        ("7. 备份状态检查", audit_backups),
    ]

    if args.quick:
        sections = sections[:3]  # 只检查前 3 项

    for title, func in sections:
        if not args.json:
            section(title)
        results = func()
        all_results["sections"][title] = results

        if not args.json:
            for r in results:
                print(f"  {r['status']} {r['name']}: {r['detail']}")

    if args.json:
        print(json.dumps(all_results, ensure_ascii=False, indent=2))

    # 统计
    total = sum(len(v) for v in all_results["sections"].values())
    errors = sum(1 for v in all_results["sections"].values() for r in v if r["status"] == "❌")
    warnings = sum(1 for v in all_results["sections"].values() for r in v if r["status"] == "⚠️")

    if not args.json:
        print(f"\n{'=' * 60}")
        print(f" 检查完成: {total} 项, ❌ {errors} 个错误, ⚠️ {warnings} 个警告")
        print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
