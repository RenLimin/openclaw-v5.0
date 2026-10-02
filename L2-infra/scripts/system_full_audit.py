#!/usr/bin/env python3
"""系统全量健康检查脚本

L2 基础设施层 — 标准化健康检查流程。
覆盖：运行时、服务、资产、架构符合性、垃圾清理、备份状态。

用法：
  python3 L2-infra/scripts/system_full_audit.py          # 完整检查
  python3 L2-infra/scripts/system_full_audit.py --json   # JSON 输出
  python3 L2-infra/scripts/system_full_audit.py --quick   # 快速检查（仅关键项）
  python3 L2-infra/scripts/system_full_audit.py --cleanup # 清理已完成的子会话（需 agent 执行）

修订：2026-09-11 — 新增子会话清理检测（第 8 节）。
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent.parent.parent / "workspace"
DATA_DIR = Path.home() / ".openclaw" / "data"
LOG_DIR = Path.home() / ".openclaw" / "logs"
BACKUP_DIR = Path.home() / ".openclaw" / "backups"
DOCS_DIR = WORKSPACE / "docs" / "architecture"
L4_COMPONENTS = WORKSPACE / "L4-proprietary" / "components"
KB_INDEX = WORKSPACE / "L2-infra" / "components" / "knowledge-base" / "kb_index.py"
KB_DIR = WORKSPACE / "docs" / "knowledge-base" / "by-category" / "project-experience"
ERROR_SCAN_JSON = WORKSPACE / "memory" / "error-scan-latest.json"
MODEL_SCHED_LOG = WORKSPACE / "L2-infra" / "components" / "model-scheduling" / "logs" / "model-scheduling.log"
MODEL_SCHED_ERR = WORKSPACE / "L2-infra" / "components" / "model-scheduling" / "logs" / "proxy.stderr.log"

# 验证路径存在（对齐 L3/L4 分层后的目录结构，ADR-026）
assert WORKSPACE.exists(), f"WORKSPACE 不存在: {WORKSPACE}"
assert DOCS_DIR.exists(), f"DOCS_DIR 不存在: {DOCS_DIR}"
assert L4_COMPONENTS.exists(), f"L4_COMPONENTS 不存在: {L4_COMPONENTS}"
assert KB_INDEX.exists(), f"KB_INDEX 不存在: {KB_INDEX}"


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
    if (
        rc == 0
        and out
        and "loaded" in out.lower()
        or "running" in out.lower()
        or "healthy" in out.lower()
        or "ok" in out.lower()
    ):
        results.append(check("gateway", "✅", "Gateway 健康 (LaunchAgent loaded)"))
    else:
        results.append(check("gateway", "⚠️", out[:200]))

    # channels
    rc, out, _ = run("openclaw channels list --all 2>&1 | grep -i wecom")
    if rc == 0 and out and ("enabled" in out.lower() or "OK" in out):
        results.append(check("wecom channel", "✅", "WeCom 已启用"))
    else:
        results.append(check("wecom channel", "⚠️", out[:200]))

    # cron 列表（仅作数量统计）
    rc, out, _ = run("openclaw cron list --all 2>&1")
    if rc == 0:
        lines = [l for l in out.split("\n") if l.strip() and not l.startswith("ID") and not l.startswith("-")]
        results.append(check("cron tasks", "✅", f"共 {len(lines)} 个任务"))
    else:
        results.append(check("cron tasks", "❌", out[:200]))

    # cron 执行质量 — 读取错误扫描脚本的输出（权威来源）
    if ERROR_SCAN_JSON.exists():
        try:
            with open(ERROR_SCAN_JSON) as f:
                scan_data = json.load(f)
            errors = scan_data.get("errors", [])
            healthy = scan_data.get("healthy", True)
            if errors:
                names = "; ".join(
                    f"{e.get('name','?')}(x{e.get('consecutive_failures', 1)})"
                    for e in errors[:3]
                )
                results.append(check(
                    "cron execution", "❌" if not healthy else "⚠️",
                    f"{len(errors)} 个任务连续失败: {names}"
                ))
            else:
                results.append(check("cron execution", "✅", "全部执行成功"))
        except (json.JSONDecodeError, Exception) as e:
            results.append(check("cron execution", "⚠️", f"扫描结果解析失败: {e}"))
    else:
        results.append(check("cron execution", "⚠️", "未找到 error-scan-latest.json，建议先跑 scan_errors.sh"))

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


def audit_model_provider_health() -> list[dict]:
    """4. 模型与 Provider 健康检测 — 扫 model-scheduling 日志中的失败"""
    results = []

    # model-scheduling proxy 是否在跑
    rc, out, _ = run("curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:3000/v1/models 2>/dev/null")
    if rc == 0 and out == "200":
        results.append(check("proxy endpoint", "✅", "model-scheduling proxy 响应正常 (:3000)"))
    else:
        results.append(check("proxy endpoint", "❌", f"proxy 不可达 (HTTP {out})"))

    # 最近 24h 模型请求错误统计
    if MODEL_SCHED_LOG.exists():
        rc, out, _ = run(
            f"grep -c '\\[ERROR\\]' {MODEL_SCHED_LOG} 2>/dev/null"
        )
        total_errors = int(out) if out.isdigit() else 0

        # 最近 1 小时的错误
        from datetime import timedelta
        one_hour_ago = (datetime.now() - timedelta(hours=1)).strftime("%Y-%m-%d %H")
        rc, out2, _ = run(
            f"grep '\\[ERROR\\]' {MODEL_SCHED_LOG} 2>/dev/null | grep -c '^{one_hour_ago}' 2>/dev/null || echo 0"
        )
        recent_errors = int(out2) if out2.isdigit() else 0

        # 取最近 5 条错误做详情
        rc, out3, _ = run(f"grep '\\[ERROR\\]' {MODEL_SCHED_LOG} 2>/dev/null | tail -3")
        detail = f"累计 {total_errors} 条 / 近1h {recent_errors} 条"

        if recent_errors == 0:
            results.append(check("model request errors", "✅", detail))
        elif recent_errors < 5:
            results.append(check("model request errors", "⚠️", detail))
        else:
            results.append(check("model request errors", "❌", detail))
    else:
        results.append(check("model request errors", "⚠️", f"日志不存在: {MODEL_SCHED_LOG}"))

    # 看门狗/僵尸日志检测
    if LOG_DIR.exists():
        zombie_logs = []
        for logfile in LOG_DIR.glob("*.log"):
            # 检查日志文件最后写入时间是否超过 7 天 + 里面全是相同错误
            rc, out, _ = run(f"wc -l < {logfile}")
            lines = int(out) if out.isdigit() else 0
            if lines > 1000:
                # 检查是不是同一条错误重复（死循环特征）
                rc, out, _ = run(f"sort -u {logfile} | wc -l")
                unique = int(out) if out.isdigit() else lines
                if unique < 5 and lines > 1000:
                    zombie_logs.append(f"{logfile.name}({lines}行/{unique}种)")

        if zombie_logs:
            results.append(check("zombie log files", "❌", f"疑似死循环日志: {', '.join(zombie_logs)}"))
        else:
            results.append(check("zombie log files", "✅", "无死循环日志"))
    else:
        results.append(check("zombie log files", "✅", "无 logs 目录"))

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

    # L4 Python files（对齐分层后的 components 目录，ADR-026）
    if L4_COMPONENTS.exists():
        count = sum(
            1
            for comp in L4_COMPONENTS.iterdir()
            if comp.is_dir()
            for _ in comp.rglob("*.py")
        )
        comps = sorted(c.name for c in L4_COMPONENTS.iterdir() if c.is_dir())
        results.append(check("L4 Python files", "✅", f"{count} 个文件 · 组件: {', '.join(comps)}"))
    else:
        results.append(check("L4 Python files", "⚠️", f"目录不存在: {L4_COMPONENTS}"))

    # 配置文件（各组件 config 目录，含深层 v1/v2）
    config_count = sum(
        len(list(cfg_dir.glob("*.json")))
        for comp in L4_COMPONENTS.iterdir()
        if comp.is_dir()
        for cfg_dir in comp.rglob("config")
        if cfg_dir.is_dir()
    )
    results.append(check("config files", "✅", f"{config_count} 个配置"))

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

    # 知识库（对齐重构后路径）
    rc, out, _ = run(f"python3 {KB_INDEX} --stats 2>/dev/null | head -5")
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
    adr_dir = KB_DIR / "adr"
    if adr_dir.exists():
        count = len(list(adr_dir.glob("*.md")))
        results.append(check("ADR count", "✅", f"{count} 篇"))
    else:
        results.append(check("ADR count", "⚠️", f"目录不存在: {adr_dir}"))

    # EXP
    exp_dir = KB_DIR / "correct"
    if exp_dir.exists():
        count = len(list(exp_dir.glob("*.md")))
        results.append(check("EXP count", "✅", f"{count} 篇"))
    else:
        results.append(check("EXP count", "⚠️", f"目录不存在: {exp_dir}"))

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

    # 临时文件（排除 ones_exports 备份目录）
    rc, out, _ = run(
        f"find {DATA_DIR} -name '*.tmp' -o -name '*.bak' 2>/dev/null "
        f"| grep -v ones_exports | wc -l"
    )
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


def audit_subagent_sessions() -> list[dict]:
    """8. 子会话状态检测 — 识别已完成/超时/失败的子会话"""
    results = []

    rc, out, _ = run(
        "openclaw sessions list --agent main --json --limit all 2>/dev/null"
    )
    if rc != 0 or not out:
        results.append(check("subagent sessions", "⚠️", "无法获取会话列表"))
        return results

    try:
        data = json.loads(out)
        sessions = data if isinstance(data, list) else data.get("sessions", [])
    except json.JSONDecodeError:
        results.append(check("subagent sessions", "⚠️", "会话列表 JSON 解析失败"))
        return results

    # 分类统计
    done_sessions = []
    timeout_sessions = []
    failed_sessions = []
    active_count = 0
    cron_count = 0

    for s in sessions:
        kind = s.get("kind", "")
        status = s.get("status", "")
        label = s.get("label", s.get("displayName", ""))
        key = s.get("key", "")

        if kind == "main":
            active_count += 1
            continue
        if kind == "cron":
            cron_count += 1
            continue

        if status in ("done", "killed"):
            done_sessions.append({"key": key, "label": label})
        elif status == "timeout":
            timeout_sessions.append({"key": key, "label": label})
        elif status == "failed":
            failed_sessions.append({"key": key, "label": label})
        elif status in ("running", "idle"):
            active_count += 1

    results.append(check(
        "active sessions", "✅",
        f"{active_count} 个活跃 (main + running subagent)"
    ))
    results.append(check(
        "cron sessions", "✅",
        f"{cron_count} 个 cron"
    ))

    if done_sessions:
        names = ", ".join(s["label"] for s in done_sessions)
        results.append(check(
            f"done/killed subagents", "⚠️",
            f"{len(done_sessions)} 个已完成待清理: {names}"
        ))
    else:
        results.append(check("done subagents", "✅", "无已完成子会话"))

    if timeout_sessions:
        names = ", ".join(s["label"] for s in timeout_sessions)
        results.append(check(
            f"timeout subagents", "⚠️",
            f"{len(timeout_sessions)} 个超时待清理: {names}"
        ))
    else:
        results.append(check("timeout subagents", "✅", "无超时子会话"))

    if failed_sessions:
        names = ", ".join(s["label"] for s in failed_sessions)
        results.append(check(
            f"failed subagents", "⚠️",
            f"{len(failed_sessions)} 个失败待清理: {names}"
        ))
    else:
        results.append(check("failed subagents", "✅", "无失败子会话"))

    return results


def get_cleanup_list() -> list[dict]:
    """返回需要清理的子会话列表（done + timeout + failed + killed，不含 cron 和 main）"""
    rc, out, _ = run("openclaw sessions list --agent main --json --limit all 2>/dev/null")
    if rc != 0 or not out:
        return []

    try:
        data = json.loads(out)
        sessions = data if isinstance(data, list) else data.get("sessions", [])
    except json.JSONDecodeError:
        return []

    cleanup = []
    for s in sessions:
        kind = s.get("kind", "")
        status = s.get("status", "")
        if kind in ("main", "cron"):
            continue
        if status in ("done", "timeout", "failed", "killed"):
            cleanup.append({
                "key": s.get("key", ""),
                "label": s.get("label", s.get("displayName", "")),
                "status": status,
            })
    return cleanup


def main():
    parser = argparse.ArgumentParser(description="BDMS 系统全量健康检查")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    parser.add_argument("--quick", action="store_true", help="快速检查（仅关键项）")
    parser.add_argument("--cleanup", action="store_true", help="输出待清理子会话 JSON（供 agent 执行删除）")
    args = parser.parse_args()

    # --cleanup 模式：仅输出待清理列表
    if args.cleanup:
        cleanup_list = get_cleanup_list()
        print(json.dumps(cleanup_list, ensure_ascii=False, indent=2))
        return

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    all_results = {
        "timestamp": now,
        "sections": {},
    }

    sections = [
        ("1. 系统状态检测", audit_system_status),
        ("2. 系统各服务状态检测", audit_services),
        ("3. 自研资产状态检测", audit_assets),
        ("4. 模型与 Provider 健康检测", audit_model_provider_health),
        ("5. 官方文档适配性检测", audit_official_compliance),
        ("6. 系统架构文档符合性检测", audit_architecture_compliance),
        ("7. 垃圾清理检测", audit_garbage),
        ("8. 备份状态检查", audit_backups),
        ("9. 子会话状态检测", audit_subagent_sessions),
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
