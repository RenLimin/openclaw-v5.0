#!/usr/bin/env python3
"""
scheduler-guard/audit.py — 调度资产审计

用途：
  核对 manifest.yaml 中登记的每个「自动」脚本是否真的被 launchd/cron 调度。
  输出结构化 JSON + 人类可读报告，供自动处置/人工 review。

背景：
  2026-11-08 — check_quota_and_restore.py 写好但从未被调度，
  只出现在 memory 文档里，导致 deepseek 余额耗尽后永久卡死。
  同类问题不止一处（16 个"自动"脚本仅 1 个被调度）。
  本脚本是「脚本交付 ≠ 机制交付」的系统性防线。

用法：
  python3 audit.py                # 审计并输出报告
  python3 audit.py --json         # 仅输出 JSON
  python3 audit.py --fix          # 对 unscheduled 项生成 plist 草稿（不自动加载）
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import yaml

MANIFEST = Path(__file__).parent / "manifest.yaml"
# 允许用环境变量覆盖 LaunchAgents 目录（供测试/预演用；生产不设置即为默认值）
LAUNCHAGENTS_DIR = Path(
    os.environ.get("SCHEDULER_GUARD_LAUNCHAGENTS_DIR",
                    str(Path.home() / "Library" / "LaunchAgents"))
)


def load_manifest() -> dict:
    return yaml.safe_load(MANIFEST.read_text())


def get_loaded_jobs() -> dict:
    """返回 launchctl list 中已加载的 job（label -> 状态）。"""
    try:
        out = subprocess.run(
            ["launchctl", "list"], capture_output=True, text=True, timeout=10
        ).stdout
    except Exception:
        return {}
    jobs = {}
    for line in out.splitlines()[1:]:  # 跳过表头
        parts = line.split("\t")
        if len(parts) >= 3:
            pid, last_exit, label = parts[0], parts[1], parts[2]
            jobs[label] = {"pid": pid, "last_exit": last_exit}
    return jobs


def get_plist_scripts() -> dict:
    """扫描所有 LaunchAgent plist，返回 {脚本名: plist路径}。"""
    mapping = {}
    if not LAUNCHAGENTS_DIR.exists():
        return mapping
    for plist in LAUNCHAGENTS_DIR.glob("*.plist"):
        try:
            out = subprocess.run(
                ["plutil", "-extract", "ProgramArguments", "json", "-o", "-", str(plist)],
                capture_output=True, text=True, timeout=5,
            ).stdout
            args = json.loads(out) if out.strip() else []
            for a in args:
                if isinstance(a, str) and a.endswith((".py", ".sh")):
                    mapping.setdefault(Path(a).name, str(plist))
                # 处理 bash -c "exec ... script.py" 形式
                elif isinstance(a, str) and ".py" in a:
                    for tok in a.split():
                        if tok.endswith((".py", ".sh")):
                            mapping.setdefault(Path(tok).name, str(plist))
        except Exception:
            continue
    return mapping


# ─── plist 卫生检查（2026-11-25 事故沉淀）──────────────────────────────
# 背景：
#   ① launchd 裸环境 PATH 不含 /opt/homebrew/bin，脚本内 subprocess.run(
#      ["openclaw"/"colima"]）直接 FileNotFoundError，两个定时任务静默失败；
#   ② 重构后遗留的 plist 副本引用已不存在的路径（workspace/model-scheduling），
#      不报错、不生效，属“看似已调度”的假象。
# 因此：每个 plist 必须显式声明 EnvironmentVariables.PATH，且引用的脚本路径必须真实存在。

def plist_metadata(plist_path: Path) -> dict:
    """读取 plist 的 ProgramArguments / EnvironmentVariables；解析失败返回 {'error': ...}"""
    meta = {"args": [], "env": {}}
    for key, out_key in (("ProgramArguments", "args"), ("EnvironmentVariables", "env")):
        try:
            out = subprocess.run(
                ["plutil", "-extract", key, "json", "-o", "-", str(plist_path)],
                capture_output=True, text=True, timeout=5,
            ).stdout
            if out.strip():
                meta[out_key] = json.loads(out)
        except Exception as e:
            return {"error": f"{key} 解析失败: {e}"}
    return meta


def _referenced_paths(args: list) -> list[str]:
    """从 ProgramArguments 中提取被引用的脚本路径（仅追踪 .py/.sh/.mjs）。

    兼容两种写法：
      - 直接路径元素：["/opt/homebrew/bin/python3", "/path/x.py"]
      - bash -c 合成串：["bash","-c","source ~/.zshenv; exec /opt/homebrew/bin/python3 /path/x.py"]
    """
    refs = []
    for a in args or []:
        if not isinstance(a, str):
            continue
        for tok in ([a] if a.startswith("/") else a.split()):
            if tok.startswith("/") and tok.endswith((".py", ".sh", ".mjs")):
                refs.append(tok)
    return refs


def _path_via_wrapper(plist_path: Path, args: list) -> bool:
    """判断是否由 OpenClaw service-env wrapper 注入 PATH（合法形态）。

    网关 plist 的形态：ProgramArguments[1] = .../service-env/<label>-env-wrapper.sh，
    且对应 .env 文件内含 `export PATH=`（wrapper 会 source 它）。
    这类由 openclaw gateway install 托管的服务不适用自维护 plist 规则。
    """
    svc_dir = Path.home() / ".openclaw" / "service-env"
    if len(args) < 2:
        return False
    wrapper = str(args[1])
    if "-env-wrapper.sh" not in wrapper:
        return False
    label = Path(plist_path).stem  # ai.openclaw.gateway
    env_file = svc_dir / f"{label}.env"
    if not env_file.is_file():
        return False
    try:
        return "export PATH=" in env_file.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return False


def check_plist_hygiene(plists=None) -> list[dict]:
    """检查 plist 卫生：PATH 声明 + 引用路径存在性。返回问题列表（空=干净）。"""
    targets = list(plists) if plists is not None else sorted(
        LAUNCHAGENTS_DIR.glob("ai.openclaw.*.plist")
    )
    problems = []
    for p in targets:
        meta = plist_metadata(p)
        if meta.get("error"):
            problems.append({"plist": p.name, "kind": "unparsable", "detail": meta["error"]})
            continue
        env = meta.get("env") or {}
        if not env.get("PATH") and not _path_via_wrapper(p, meta.get("args", [])):
            problems.append({
                "plist": p.name, "kind": "missing_path_env",
                "detail": "EnvironmentVariables.PATH 未声明（launchd 裸环境无 /opt/homebrew/bin，"
                          "subprocess 调外部 CLI 会 FileNotFoundError）",
            })
        for rp in _referenced_paths(meta.get("args", [])):
            if not Path(rp).exists():
                problems.append({
                    "plist": p.name, "kind": "stale_reference",
                    "detail": f"引用的脚本路径不存在: {rp}",
                })
    return problems


def audit() -> dict:
    manifest = load_manifest()
    loaded = get_loaded_jobs()
    plist_scripts = get_plist_scripts()

    results = []
    for entry in manifest.get("entries", []):
        script = entry["script"]
        script_name = Path(script).name
        declared_status = entry.get("status", "unscheduled")
        declared_plist = entry.get("plist")

        # 实际检测
        actual_plist = plist_scripts.get(script_name)
        is_loaded = any(
            actual_plist and Path(actual_plist).stem in label
            for label in loaded
        ) if actual_plist else False

        # 状态判定
        if actual_plist and is_loaded:
            actual_status = "scheduled"
        elif actual_plist:
            actual_status = "plist_exists_not_loaded"
        elif declared_status == "manual_only":
            # manual_only: 声明为手动/被其他调度覆盖，无需 plist
            actual_status = "manual_only"
        else:
            actual_status = "unscheduled"

        # 一致性：声明与实际相符，或声明 manual_only（允许无 plist）
        consistent = (declared_status == actual_status) or (
            declared_status == "manual_only"
        )

        results.append({
            "script": script,
            "script_name": script_name,
            "declared_status": declared_status,
            "declared_plist": declared_plist,
            "actual_status": actual_status,
            "actual_plist": actual_plist,
            "loaded": is_loaded,
            "consistent": consistent,
            "note": entry.get("note", ""),
        })

    hygiene = check_plist_hygiene()

    return {
        "total": len(results),
        "scheduled": sum(1 for r in results if r["actual_status"] == "scheduled"),
        "unscheduled": sum(1 for r in results if r["actual_status"] == "unscheduled"),
        "plist_not_loaded": sum(1 for r in results if r["actual_status"] == "plist_exists_not_loaded"),
        "inconsistent": sum(1 for r in results if not r["consistent"]),
        "hygiene_problems": hygiene,
        "results": results,
    }


def main():
    parser = argparse.ArgumentParser(description="调度资产审计")
    parser.add_argument("--json", action="store_true", help="仅输出 JSON")
    parser.add_argument("--fix", action="store_true", help="对 unscheduled 项生成 plist 草稿")
    args = parser.parse_args()

    report = audit()

    # 门禁语义（对 --json 与报告模式一致生效）：有问题即非零退出。
    # 定时任务 ai.openclaw.scheduler-guard 用 `--json > audit-latest.json`，
    # 若此处无条件 return 0，则 launchctl last_exit 永远为 0，门禁形同虚设。
    blocking = bool(report.get("hygiene_problems")) \
        or report["inconsistent"] > 0 \
        or report["unscheduled"] > 0

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 1 if blocking else 0

    print("=" * 60)
    print("调度资产审计报告")
    print("=" * 60)
    print(f"总计: {report['total']} | 已调度: {report['scheduled']} | "
          f"未调度: {report['unscheduled']} | plist未加载: {report['plist_not_loaded']} | "
          f"不一致: {report['inconsistent']}")
    print()

    hyg = report.get("hygiene_problems") or []
    if hyg:
        print("⚠️  plist 卫生问题（PATH 缺失 / 引用失效）:")
        for h in hyg:
            print(f"  [{h['kind']}] {h['plist']}: {h['detail']}")
        print()
    else:
        print("✅ plist 卫生检查通过（PATH 已声明、引用路径均存在）\n")

    for r in report["results"]:
        icon = "✅" if r["actual_status"] == "scheduled" else "❌"
        print(f"{icon} {r['script_name']}")
        print(f"   声明: {r['declared_status']} | 实际: {r['actual_status']}")
        if r["actual_plist"]:
            print(f"   plist: {r['actual_plist']}")
        if r["note"]:
            print(f"   备注: {r['note']}")
        print()

    if args.fix:
        print("=" * 60)
        print("生成 plist 草稿（未自动加载）")
        print("=" * 60)
        for r in report["results"]:
            if r["actual_status"] == "unscheduled":
                plist_name = f"ai.openclaw.{r['script_name'].replace('.py','').replace('.sh','')}.plist"
                print(f"\n# {r['script_name']} → ~/Library/LaunchAgents/{plist_name}")
                print(f"# 脚本: {r['script']}")
                print(f"# 备注: {r['note']}")

    # 与上方同一套判定，避免两条路径口径不一
    return 1 if blocking else 0


if __name__ == "__main__":
    sys.exit(main())
