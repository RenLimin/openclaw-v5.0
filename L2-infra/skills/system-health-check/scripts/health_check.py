#!/usr/bin/env python3
"""系统全量健康检查脚本。

用法:
    python3 health_check.py [--json] [--brief] [--skip category] [--only category]

退出码: 0=全过, 1=有失败, 2=脚本出错
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from datetime import datetime, timezone, timedelta

WORKSPACE = Path(__file__).resolve().parents[4]  # scripts/ → system-health-check/ → skills/ → L2-infra/ → workspace/
TZ = timezone(timedelta(hours=8))

# ─── 工具函数 ───

def run_cmd(cmd, timeout=30, cwd=None):
    """运行命令，返回 (returncode, stdout, stderr)"""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
            timeout=timeout, cwd=str(cwd or WORKSPACE)
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"
    except Exception as e:
        return 1, "", str(e)


class HealthCheck:
    def __init__(self):
        self.checks = []
        self.start_time = datetime.now(TZ)

    def add(self, category, name, status, detail=""):
        self.checks.append({
            "category": category,
            "name": name,
            "status": status,  # pass / fail / warn / skip
            "detail": detail
        })

    @property
    def summary(self):
        s = {"total": len(self.checks), "passed": 0, "failed": 0, "warn": 0, "skipped": 0}
        for c in self.checks:
            if c["status"] == "pass":
                s["passed"] += 1
            elif c["status"] == "fail":
                s["failed"] += 1
            elif c["status"] == "warn":
                s["warn"] += 1
            elif c["status"] == "skip":
                s["skipped"] += 1
        return s

    # ─── 各类检查 ───

    def check_gateway(self):
        """检查 Gateway 运行状态"""
        rc, out, err = run_cmd("openclaw status 2>&1 | head -20")
        if rc == 0 and "Gateway" in out:
            # 提取 pid
            import re
            m = re.search(r"pid (\d+)", out)
            pid = m.group(1) if m else "unknown"
            self.add("gateway", "gateway-running", "pass", f"pid {pid}")
        else:
            self.add("gateway", "gateway-running", "fail", err or "gateway not running")

        # 版本
        rc, out, _ = run_cmd("openclaw --version")
        if rc == 0:
            self.add("gateway", "gateway-version", "pass", out.strip())
        else:
            self.add("gateway", "gateway-version", "fail", "cannot get version")

    def check_channels(self):
        """检查通道状态"""
        rc, out, _ = run_cmd("openclaw channels list 2>&1")
        if rc != 0:
            self.add("channels", "channel-list", "fail", "cannot list channels")
            return
        self.add("channels", "channel-list", "pass")

        # WeCom 必须正常
        if "WeCom" in out and "configured" in out:
            self.add("channels", "wecom-status", "pass", "configured & enabled")
        else:
            self.add("channels", "wecom-status", "warn", "WeCom not configured")

    def check_model_scheduling(self):
        """检查模型调度服务"""
        # 进程存在
        rc, out, _ = run_cmd("ps aux | grep proxy.py | grep -v grep")
        if rc == 0 and out:
            import re
            m = re.search(r"(\d+).*proxy.py", out)
            pid = m.group(1) if m else "unknown"
            self.add("model-scheduling", "proxy-process", "pass", f"pid {pid}")
        else:
            self.add("model-scheduling", "proxy-process", "fail", "proxy.py not running")

        # 健康端点
        rc, out, _ = run_cmd("curl -s -m 5 http://127.0.0.1:3000/health")
        if rc == 0 and "status" in out:
            try:
                data = json.loads(out)
                self.add("model-scheduling", "proxy-health", "pass",
                        f"requests={data.get('requests',0)}, errors={data.get('errors',0)}")
            except json.JSONDecodeError:
                self.add("model-scheduling", "proxy-health", "warn", "response not JSON")
        else:
            self.add("model-scheduling", "proxy-health", "fail", "health endpoint unreachable")

        # 配置文件存在
        config_dir = WORKSPACE / "L2-infra" / "components" / "model-scheduling" / "config"
        # 也可能在 model-scheduling/config/ 下（旧路径）
        if not config_dir.exists():
            alt = WORKSPACE / "L2-infra" / "components" / "model-scheduling" / "config"
            if alt.exists():
                config_dir = alt
        for f in ["models.yaml", "routing.yaml", "providers.yaml"]:
            if (config_dir / f).exists():
                self.add("model-scheduling", f"config-{f}", "pass")
            else:
                self.add("model-scheduling", f"config-{f}", "fail", f"{f} missing")

    def check_components(self):
        """检查 L2 组件完整性"""
        l2_dir = WORKSPACE / "L2-infra" / "components"
        if not l2_dir.exists():
            self.add("components", "l2-dir", "fail", "L2 components dir missing")
            return

        components = [d.name for d in l2_dir.iterdir() if d.is_dir()]
        self.add("components", "l2-count", "pass", f"{len(components)} components")

        # 检查每个组件是否有 DESIGN.md
        missing_design = []
        for comp in components:
            design = l2_dir / comp / "DESIGN.md"
            if not design.exists():
                missing_design.append(comp)

        if missing_design:
            self.add("components", "design-docs", "warn",
                    f"missing DESIGN.md: {', '.join(missing_design)}")
        else:
            self.add("components", "design-docs", "pass",
                    f"all {len(components)} components have DESIGN.md")

    def check_cron(self):
        """检查 Cron 任务状态"""
        rc, out, _ = run_cmd("openclaw cron list 2>&1")
        if rc != 0:
            self.add("cron", "cron-list", "fail", "cannot list cron jobs")
            return

        lines = out.strip().split("\n")
        jobs = [l for l in lines if l.strip() and not l.startswith("ID") and not l.startswith("─")]
        self.add("cron", "cron-count", "pass", f"{len(jobs)} jobs")

        # 检查是否有失败的
        failed = [l for l in jobs if "fail" in l.lower() or "error" in l.lower() or "timeout" in l.lower()]
        if failed:
            self.add("cron", "cron-health", "warn",
                    f"{len(failed)} jobs with failures")
        else:
            self.add("cron", "cron-health", "pass", "all jobs ok")

    def check_tests(self):
        """运行业务测试"""
        # DMS
        dms_test = WORKSPACE / "L3-business" / "components" / "dms-framework" / "tests"
        if dms_test.exists():
            rc, out, _ = run_cmd(
                "python3 -m pytest L3-business/components/dms-framework/tests/ -q 2>&1 | tail -1",
                timeout=120
            )
            if rc == 0 and "passed" in out:
                self.add("tests", "dms-tests", "pass", out.strip())
            else:
                self.add("tests", "dms-tests", "fail", out.strip() or "test failed")
        else:
            self.add("tests", "dms-tests", "skip", "dms-framework tests not found")

        # FIN-L4
        fin_test = WORKSPACE / "L4-proprietary" / "components" / "fin-l4" / "tests"
        if fin_test.exists():
            rc, out, _ = run_cmd(
                "python3 -m pytest L4-proprietary/components/fin-l4/tests/ -q 2>&1 | tail -1",
                timeout=60
            )
            if rc == 0 and "passed" in out:
                self.add("tests", "fin-l4-tests", "pass", out.strip())
            else:
                self.add("tests", "fin-l4-tests", "fail", out.strip() or "test failed")
        else:
            self.add("tests", "fin-l4-tests", "skip", "fin-l4 tests not found")

    def check_secrets(self):
        """检查凭据安全"""
        rc, out, _ = run_cmd("openclaw secrets audit 2>&1")
        if rc != 0:
            self.add("secrets", "audit", "warn", "secrets audit command failed")
            return

        # 统计 plaintext 数量
        import re
        plaintext_match = re.search(r"plaintext[=: ]*(\d+)", out, re.IGNORECASE)
        if plaintext_match:
            count = int(plaintext_match.group(1))
            status = "pass" if count <= 7 else "warn"  # 7 个已知合理场景
            detail = f"{count} plaintext entries"
            self.add("secrets", "plaintext-count", status, detail)
        else:
            self.add("secrets", "audit", "pass", "audit ran")

    def check_git(self):
        """检查 Git 仓库状态"""
        # 是否在 git 仓库
        rc, out, _ = run_cmd("git rev-parse --is-inside-work-tree")
        if rc != 0 or out.strip() != "true":
            self.add("git", "repo", "fail", "not a git repo")
            return
        self.add("git", "repo", "pass")

        # 当前分支
        rc, out, _ = run_cmd("git branch --show-current")
        if rc == 0:
            self.add("git", "branch", "pass", out.strip())

        # 工作区是否干净
        rc, out, _ = run_cmd("git status --short")
        if rc == 0:
            if not out.strip():
                self.add("git", "working-tree", "pass", "clean")
            else:
                files = len(out.strip().split("\n"))
                self.add("git", "working-tree", "warn",
                        f"{files} uncommitted files")

        # 与远程同步
        rc, out, _ = run_cmd("git fetch origin 2>&1 && git status -sb 2>&1")
        if rc == 0 and "ahead" in out:
            self.add("git", "remote-sync", "warn", "local ahead of remote")
        elif rc == 0 and "behind" in out:
            self.add("git", "remote-sync", "warn", "local behind remote")
        else:
            self.add("git", "remote-sync", "pass", "in sync with origin")

    # ─── 运行所有检查 ───

    def run_all(self, skip_categories=None, only_categories=None):
        skip = set(skip_categories or [])
        only = set(only_categories or [])

        checks = [
            ("gateway", self.check_gateway),
            ("channels", self.check_channels),
            ("model-scheduling", self.check_model_scheduling),
            ("components", self.check_components),
            ("cron", self.check_cron),
            ("tests", self.check_tests),
            ("secrets", self.check_secrets),
            ("git", self.check_git),
        ]

        for cat, func in checks:
            if cat in skip:
                continue
            if only and cat not in only:
                continue
            try:
                func()
            except Exception as e:
                self.add(cat, f"{cat}-error", "fail", str(e)[:200])


def print_human(hc, brief=False):
    s = hc.summary
    print()
    print("=== 系统健康检查报告 ===")
    print(f"时间: {hc.start_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print(f"总检查项: {s['total']} | ✅ 通过: {s['passed']} | ⚠️  警告: {s['warn']} | ❌ 失败: {s['failed']} | ⏭️  跳过: {s['skipped']}")
    print()

    if brief:
        return

    # 按类别分组输出
    current_cat = ""
    for c in hc.checks:
        if c["category"] != current_cat:
            current_cat = c["category"]
            print(f"[{current_cat}]")
        icon = {"pass": "✅", "fail": "❌", "warn": "⚠️ ", "skip": "⏭️ "}.get(c["status"], "?")
        detail = f" — {c['detail']}" if c["detail"] else ""
        print(f"  {icon} {c['name']}{detail}")
    print()


def main():
    parser = argparse.ArgumentParser(description="系统全量健康检查")
    parser.add_argument("--json", action="store_true", help="输出 JSON 格式")
    parser.add_argument("--brief", action="store_true", help="只输出摘要")
    parser.add_argument("--skip", action="append", default=[], help="跳过某类检查")
    parser.add_argument("--only", action="append", default=[], help="只跑某类检查")
    args = parser.parse_args()

    hc = HealthCheck()

    try:
        hc.run_all(skip_categories=args.skip, only_categories=args.only)
    except Exception as e:
        print(f"检查运行失败: {e}", file=sys.stderr)
        sys.exit(2)

    if args.json:
        result = {
            "timestamp": hc.start_time.isoformat(),
            "summary": hc.summary,
            "checks": hc.checks
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_human(hc, brief=args.brief)

    # 退出码
    s = hc.summary
    if s["failed"] > 0:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
