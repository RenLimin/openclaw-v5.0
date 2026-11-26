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

# 复用能力注册表的资产文档判定（单一事实源）。
# 背景（事故 2026-11-25）：本脚本原先只查根级 DESIGN.md，导致
#   ① 放在 docs/ 或命名为 DESIGN-DETAIL-*/DESIGN-OUTLINE-* 的文档被误判缺失；
#   ② 把 .deprecated 这类非资产隐藏目录算进组件清单；
# 而 pre-commit 门禁（capability_registry --require-design）用的是另一套递归+前缀规则。
# 两套口径不一致 → 健康检查长期误报，门禁却放行。这里统一到 registry 的实现。
try:
    sys.path.insert(0, str(WORKSPACE / "L2-infra" / "components" / "config" / "capability-registry"))
    import capability_registry as _capreg
except Exception:
    _capreg = None

# ─── 工具函数 ───

def resolve_openclaw_bin():
    """外部 CLI 一律绝对路径（AGENTS.md §LaunchAgent PATH 红线，兜底候选）。"""
    import shutil
    for cand in (shutil.which("openclaw"), "/opt/homebrew/bin/openclaw",
                 str(Path.home() / ".openclaw" / "tmp" / "agent-cli" / "openclaw")):
        if cand and Path(cand).exists():
            return cand
    return "openclaw"


def parse_gateway_call_json(out):
    """解析 `openclaw gateway call ...` 输出中的 JSON。

    该命令会在 JSON 前打印一行 `Gateway call: <method>`，故按首个 `{` 起 raw_decode。
    解析失败返回 None（调用方据此降级为 skip，不误报）。
    """
    idx = (out or "").find("{")
    if idx < 0:
        return None
    try:
        obj, _ = json.JSONDecoder().raw_decode(out[idx:])
        return obj
    except (json.JSONDecodeError, ValueError):
        return None


def runtime_channel_probes(payload, channels=("wecom", "openclaw-weixin")):
    """把运行时通道状态转成探针结果 [(name, status, detail)]。

    事故（2026-11-26，wecom 稳定性审计）：原 wecom-status 只看
    `openclaw channels list` 的静态配置态，断开 1 小时仍报 pass——
    监控口径漏掉运行时连接。这里改用 `gateway call channels.status` 的
    running / lastError 判据。

    保守语义：
    - RPC 不可用（payload=None）→ skip，不误报；
    - 已配置且 running=true 且 lastError=null → pass；
    - running=false 或 lastError 非空 → fail。
    """
    if payload is None:
        return [("channels-runtime", "skip", "运行时状态 RPC 不可用（不据此判定）")]
    states = payload.get("channels") or {}
    results = []
    for ch in channels:
        st = states.get(ch)
        if st is None:
            results.append((f"{ch}-runtime", "warn", "运行时状态中无该通道"))
            continue
        if not st.get("configured"):
            results.append((f"{ch}-runtime", "warn", "未配置"))
            continue
        err = st.get("lastError")
        running = st.get("running")
        if running is False:
            results.append((f"{ch}-runtime", "fail", "configured 但 running=false"))
        elif err:
            results.append((f"{ch}-runtime", "fail", f"lastError={err}"))
        else:
            started = st.get("lastStartAt")
            extra = f", lastStartAt={started}" if started else ""
            results.append((f"{ch}-runtime", "pass", f"running=true{extra}"))
    return results


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

        # WeCom 静态配置态（配置口径，保留）
        if "WeCom" in out and "configured" in out:
            self.add("channels", "wecom-status", "pass", "configured & enabled")
        else:
            self.add("channels", "wecom-status", "warn", "WeCom not configured")

        # 运行时连接态（连接口径，2026-11-26 补：静态配置无法反映断连）
        rc, out, err = run_cmd(f'{resolve_openclaw_bin()} gateway call channels.status 2>&1',
                               timeout=30)
        payload = parse_gateway_call_json(out) if rc == 0 else None
        for name, status, detail in runtime_channel_probes(payload):
            self.add("channels", name, status, detail)

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
        """检查资产文档完整性。

        口径单一事实源 = capability_registry（见文件头说明）。这里只做**调用方**，
        不再自造枚举/匹配规则；registry 不可导入时显式 skip，避免降级成第二套口径。
        """
        if _capreg is None:
            self.add("components", "asset-docs", "skip",
                     "capability_registry 不可导入（无法判定，不据此报缺）")
            return

        try:
            rows = list(_capreg._iter_asset_dirs())
        except Exception as e:  # noqa: BLE001 - 降级而非崩溃
            self.add("components", "asset-docs", "skip", f"资产枚举失败：{e}")
            return

        total = len(rows)
        missing_design, missing_verify = [], []
        for layer, kind, d in rows:
            info = _capreg._asset_docs(d)
            key = f"{layer}/{kind}/{d.name}"
            if not info.get("design"):
                missing_design.append(key)
            if not info.get("verify"):
                missing_verify.append(key)

        # 豁免范围（L1 适配层）：非缺口，显性标注
        exempt = [x for x in getattr(_capreg.load_registry(), "scope_exemptions", [])]

        if missing_design:
            self.add("components", "design-docs", "warn",
                     f"missing design doc: {', '.join(missing_design)}")
        else:
            self.add("components", "design-docs", "pass",
                     f"all {total} assets have design doc")

        if missing_verify:
            self.add("components", "verification-docs", "warn",
                     f"{len(missing_verify)}/{total} 缺验收文档: {', '.join(missing_verify[:5])}")
        else:
            self.add("components", "verification-docs", "pass",
                     f"all {total} assets have verification doc")

        if exempt:
            self.add("components", "scope-exemptions", "pass",
                     f"{len(exempt)} 个显式豁免: {', '.join(x['path'].split('/')[-1] for x in exempt)}")

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
        # 口径：用隔离临时 index（免疫共享 .git/index 被并行会话写花造成的假警，
        # 见 AGENTS.md §共享 index 过期；2026-11-25 实测 272 假警即此因）
        try:
            sys.path.insert(0, str(WORKSPACE / "L2-infra" / "components" / "config"))
            from git_tree_status import working_tree_counts, format_summary
            counts = working_tree_counts(WORKSPACE)
        except Exception as e:  # noqa: BLE001 - 降级而非崩溃
            counts = {"error": str(e)}
        if counts.get("error"):
            self.add("git", "working-tree", "warn", f"状态不可用：{counts['error']}")
        elif counts["total"] == 0:
            self.add("git", "working-tree", "pass", "clean")
        else:
            self.add("git", "working-tree", "warn",
                    f"{counts['total']} uncommitted files（{format_summary(counts)}）")

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
