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
import subprocess
import sys
from pathlib import Path

import yaml

MANIFEST = Path(__file__).parent / "manifest.yaml"
LAUNCHAGENTS_DIR = Path.home() / "Library" / "LaunchAgents"


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

    return {
        "total": len(results),
        "scheduled": sum(1 for r in results if r["actual_status"] == "scheduled"),
        "unscheduled": sum(1 for r in results if r["actual_status"] == "unscheduled"),
        "plist_not_loaded": sum(1 for r in results if r["actual_status"] == "plist_exists_not_loaded"),
        "inconsistent": sum(1 for r in results if not r["consistent"]),
        "results": results,
    }


def main():
    parser = argparse.ArgumentParser(description="调度资产审计")
    parser.add_argument("--json", action="store_true", help="仅输出 JSON")
    parser.add_argument("--fix", action="store_true", help="对 unscheduled 项生成 plist 草稿")
    args = parser.parse_args()

    report = audit()

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0

    print("=" * 60)
    print("调度资产审计报告")
    print("=" * 60)
    print(f"总计: {report['total']} | 已调度: {report['scheduled']} | "
          f"未调度: {report['unscheduled']} | plist未加载: {report['plist_not_loaded']} | "
          f"不一致: {report['inconsistent']}")
    print()

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

    return 0


if __name__ == "__main__":
    sys.exit(main())
