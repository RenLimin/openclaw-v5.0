#!/usr/bin/env python3
"""系统全量健康检查脚本

L2 基础设施层 — 标准化健康检查流程。
覆盖：运行时、服务、资产、架构符合性、垃圾清理、备份状态。

用法：
  python3 L2-infra/scripts/system_full_audit.py          # 完整检查
  python3 L2-infra/scripts/system_full_audit.py --json   # JSON 输出
  python3 L2-infra/scripts/system_full_audit.py --quick   # 快速检查（仅关键项）
  python3 L2-infra/scripts/system_full_audit.py --cleanup # 清理已完成的子会话（需 agent 执行）
  python3 L2-infra/scripts/system_full_audit.py --purge-archived        # 删除已归档会话（默认 dry-run）
  python3 L2-infra/scripts/system_full_audit.py --purge-archived --yes  # 真正执行删除并写留痕 manifest
  python3 L2-infra/scripts/system_full_audit.py --restore-help <manifest.json>  # 从 manifest 解压归档 transcript

修订：2026-09-11 — 新增子会话清理检测（第 8 节）。
修订：2026-11-10 — 新增第 10 节「已归档会话检测」+ --purge-archived（留痕 manifest + 名称释放校验）
                    + --restore-help（解压 .deleted.zst 归档）。
"""

import argparse
import json
import os
import shlex
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

# 已归档会话删除（2026-11-10 新增）
AGENT_SESSIONS_DIR = Path.home() / ".openclaw" / "agents" / "main" / "sessions"
PURGE_LOG_DIR = WORKSPACE / "memory" / "session-purge-logs"
MAIN_SESSION_KEY = "agent:main:main"

# 已建资产自动登记（2026-11-10 新增）
ASSET_INVENTORY_DOC = DOCS_DIR / "01-asset-inventory.md"
ASSET_GENERATOR = WORKSPACE / "L2-infra" / "components" / "config" / "gen_asset_inventory.py"

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


# ---------------------------------------------------------------------------
# 已归档会话：检测 / 删除留痕 / 恢复辅助（第 10 节，2026-11-10）
# ---------------------------------------------------------------------------

def _gateway_list_sessions(agent_id: str = "main", limit: int = 500) -> dict:
    """通过 gateway RPC 列出会话（含已归档）。

    sessions.list 的 archived 参数：true=仅归档 / false=仅活行 / "all"=全部。
    CLI 输出首行带 'Gateway call:' 前缀，取第一个 '{' 之后解析。
    """
    params = json.dumps({"agentId": agent_id, "archived": "all", "limit": limit})
    rc, out, err = run(
        f"openclaw gateway call sessions.list --params {shlex.quote(params)}",
        timeout=30,
    )
    brace = out.find("{")
    if rc != 0 or brace < 0:
        raise RuntimeError(f"sessions.list RPC 失败: {err or out[:200]}")
    return json.loads(out[brace:])


def _archived_sessions(agent_id: str = "main") -> list[dict]:
    """返回已归档（archivedAt 非空）会话。"""
    data = _gateway_list_sessions(agent_id)
    sessions = data.get("sessions", [])
    return [s for s in sessions if s.get("archivedAt")]


def audit_archived_sessions() -> list[dict]:
    """10. 已归档会话检测 — 识别可安全删除（释放名称）的已归档会话。"""
    results = []
    try:
        archived = _archived_sessions()
    except RuntimeError as e:
        results.append(check("archived sessions", "⚠️", str(e)[:200]))
        return results

    if not archived:
        results.append(check("archived sessions", "✅", "无已归档会话"))
        return results

    results.append(check(
        "archived sessions", "⚠️",
        f"{len(archived)} 个已归档会话可用 --purge-archived 删除（删除后名称可复用）"
    ))
    for s in archived:
        label = s.get("label") or "(未命名)"
        results.append(check(
            f"  archived · {label}", "📦",
            f"key={s.get('key')} | status={s.get('status') or 'none'} | sessionId={s.get('sessionId')}"
        ))
    return results


def _find_deleted_archive(session_id: str) -> str | None:
    """在 agent sessions 目录定位某 session 的 .deleted.zst 归档文件名。"""
    if not AGENT_SESSIONS_DIR.exists():
        return None
    matches = sorted(
        AGENT_SESSIONS_DIR.glob(f"{session_id}.jsonl.deleted.*.zst"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return matches[0].name if matches else None


def purge_archived_sessions(apply: bool, agent_id: str = "main") -> int:
    """删除已归档会话。apply=False 为 dry-run（默认）。

    红线：只删 archivedAt 非空；永不删 main 会话；running 不删。
    删除后写 append-only manifest（含业务名 + 归档文件双指针），并校验名称释放。
    """
    try:
        archived = _archived_sessions(agent_id)
    except RuntimeError as e:
        print(f"❌ {e}")
        return 1

    targets = []
    for s in archived:
        key = s.get("key", "")
        if key == MAIN_SESSION_KEY or key.endswith(":main"):
            continue  # main 会话永久保护
        if s.get("status") == "running":
            continue  # 运行中的不删
        targets.append(s)

    print(f"已归档会话 {len(archived)} 个，符合删除条件 {len(targets)} 个：")
    for s in targets:
        print(f"  - {s.get('label') or '(未命名)'} | {s.get('key')} | status={s.get('status') or 'none'}")

    if not apply:
        print("\n🔍 dry-run — 未做任何更改。加 --yes 真正执行删除。")
        return 0

    if not targets:
        print("\n无需删除。")
        return 0

    keys = [s["key"] for s in targets]
    quoted = " ".join(shlex.quote(k) for k in keys)
    rc, out, err = run(
        f"openclaw sessions delete {quoted} --agent {shlex.quote(agent_id)} --yes --json",
        timeout=120,
    )
    brace = out.find("{")
    envelope = {}
    if brace >= 0:
        try:
            envelope = json.loads(out[brace:])
        except json.JSONDecodeError:
            pass
    if rc != 0:
        print(f"❌ sessions delete 失败: {err or out[:400]}")
        return 1

    rpc_results = {r.get("key"): r for r in envelope.get("results", [])}

    # 组装 manifest 条目（删除后定位 .deleted.zst 归档）
    entries = []
    for s in targets:
        sid = s.get("sessionId", "")
        archive_file = _find_deleted_archive(sid)
        r = rpc_results.get(s.get("key"), {})
        entries.append({
            "key": s.get("key"),
            "label": s.get("label"),  # 业务名：系统归档表不含此字段，manifest 独有
            "sessionId": sid,
            "priorStatus": s.get("status"),
            "archivedAt": s.get("archivedAt"),
            "purgedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
            "deleteResult": r.get("status") if r else None,
            "archiveFile": archive_file,
            "archiveRecoverable": archive_file is not None,
        })

    PURGE_LOG_DIR.mkdir(parents=True, exist_ok=True)
    manifest_path = PURGE_LOG_DIR / f"purge-{datetime.now().strftime('%Y%m%dT%H%M%S')}.json"
    manifest = {
        "manifestVersion": 1,
        "agentId": agent_id,
        "purgedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "sessionsDir": str(AGENT_SESSIONS_DIR),
        "entries": entries,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))

    # ---- 删除后校验：会话行消失 + 名称释放 + 归档可读 ----
    remaining = _gateway_list_sessions(agent_id).get("sessions", [])
    remaining_keys = {s.get("key") for s in remaining}
    live_labels = {s.get("label") for s in remaining if not s.get("archivedAt")}

    print("\n删除结果：")
    ok_all = True
    for e in entries:
        gone = e["key"] not in remaining_keys
        name_freed = e["label"] is None or e["label"] not in live_labels
        archived_ok = e["archiveRecoverable"]
        ok = gone and name_freed and archived_ok
        ok_all = ok_all and ok
        print(f"  {'✅' if gone else '❌'} 行已删除: {e['label'] or e['key']}")
        print(f"     {'✅' if name_freed else '❌'} 名称已释放（新会话可同名）")
        print(f"     {'✅' if archived_ok else '❌'} 归档留存: {e['archiveFile'] or '未找到'}")

    print(f"\n📝 留痕 manifest: {manifest_path}")
    print("   恢复归档 transcript: --restore-help " + str(manifest_path))
    print("   注：无官方 undelete；行级会话恢复需走 OpenClaw 备份还原。")
    return 0 if ok_all else 2


def restore_help(manifest_path: str) -> int:
    """按 manifest 将 .deleted.zst 归档解压为可读 .jsonl transcript。"""
    path = Path(manifest_path)
    if not path.exists():
        print(f"❌ manifest 不存在: {path}")
        return 1
    manifest = json.loads(path.read_text())

    rc, zstd_path, _ = run("which zstd")
    if rc != 0:
        print("❌ 未找到 zstd，无法解压 .zst 归档（brew install zstd）")
        return 1

    out_dir = PURGE_LOG_DIR / "restored"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"从 manifest 恢复 {len(manifest.get('entries', []))} 个归档 transcript：")
    for e in manifest.get("entries", []):
        archive = e.get("archiveFile")
        if not archive:
            print(f"  ⚠️ {e.get('label')}: 无 archiveFile 记录")
            continue
        src = AGENT_SESSIONS_DIR / archive
        if not src.exists():
            print(f"  ❌ {e.get('label')}: 归档文件不存在 {src}")
            continue
        dest = out_dir / f"{e['sessionId']}.jsonl"
        rc, _, err = run(f"zstd -d -f -q -o {shlex.quote(str(dest))} {shlex.quote(str(src))}")
        if rc != 0:
            print(f"  ❌ {e.get('label')}: 解压失败 {err}")
            continue
        size = dest.stat().st_size
        print(f"  ✅ {e.get('label') or e['sessionId']} -> {dest} ({size} bytes)")

    print("\n注：解压产物为只读 transcript（可查阅/取证）；恢复为可交互 live 会话需走备份还原。")
    return 0


def audit_asset_registration() -> list[dict]:
    """11. 已建资产登记检测 — 全盘发现 vs 资产清单文档漂移。"""
    results = []
    if not ASSET_GENERATOR.exists():
        results.append(check("asset registration", "❌", f"生成器不存在: {ASSET_GENERATOR}"))
        return results

    # 生成器 --check：当前清单文档是否与实时系统状态一致
    rc, out, err = run(f"python3 {ASSET_GENERATOR} --check", timeout=60)
    if rc == 0:
        results.append(check("asset inventory drift", "✅", "资产清单与已建资产一致，无漂移"))
        return results

    # 漂移：解析已发现组件，指出磁盘上「已建成但未登记」的量
    rc2, disc_out, _ = run(
        "python3 -c \"import sys; sys.path.insert(0,'" + str(ASSET_GENERATOR.parent) + "');"
        "import gen_asset_inventory as g; "
        "import json; print(json.dumps([i['rel'] for _,i in g.discover_completed_components()]))\"",
        timeout=60,
    )
    n_discovered = "?"
    try:
        n_discovered = str(len(json.loads(disc_out)))
    except (json.JSONDecodeError, TypeError):
        pass
    results.append(check(
        "asset inventory drift", "⚠️",
        f"资产清单已过期（全盘已建成 {n_discovered} 个组件）。运行 --register-assets 重新登记"
    ))
    results.append(check(
        "  register hint", "📝",
        f"python3 L2-infra/scripts/system_full_audit.py --register-assets"
    ))
    return results


def register_assets() -> int:
    """按架构文档约定，将全盘已建成资产重新登记进资产清单文档。"""
    if not ASSET_GENERATOR.exists():
        print(f"❌ 生成器不存在: {ASSET_GENERATOR}")
        return 1
    print("全盘扫描已建设完成资产并重新登记至资产清单...")
    rc, out, err = run(f"python3 {ASSET_GENERATOR}", timeout=90)
    print(out or err)
    if rc != 0:
        print(f"❌ 登记失败: {err}")
        return 1

    # 二次校验漂移归零
    rc2, check_out, _ = run(f"python3 {ASSET_GENERATOR} --check", timeout=60)
    if rc2 == 0:
        print("\n✅ 已登记完成，资产清单漂移归零。")
        print(f"   文档: {ASSET_INVENTORY_DOC}")
        return 0
    print("\n⚠️ 登记后仍有漂移，请人工核对。")
    return 2


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
    parser.add_argument("--purge-archived", action="store_true",
                        help="删除已归档会话（默认 dry-run，加 --yes 真正执行）")
    parser.add_argument("--yes", action="store_true", help="--purge-archived 时真正执行删除")
    parser.add_argument("--restore-help", metavar="MANIFEST", help="从 manifest 解压 .deleted.zst 归档 transcript")
    parser.add_argument("--register-assets", action="store_true",
                        help="全盘扫描已建成资产并重新登记至资产清单文档")
    args = parser.parse_args()

    # --restore-help 模式：解压归档
    if args.restore_help:
        sys.exit(restore_help(args.restore_help))

    # --register-assets 模式：全盘已建资产重新登记
    if args.register_assets:
        sys.exit(register_assets())

    # --purge-archived 模式：删除已归档会话（留痕 manifest）
    if args.purge_archived:
        sys.exit(purge_archived_sessions(apply=args.yes))

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
        ("10. 已归档会话检测", audit_archived_sessions),
        ("11. 已建资产登记检测", audit_asset_registration),
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
