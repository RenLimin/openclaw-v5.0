#!/usr/bin/env python3
"""
服务健康检测 + 自动修复脚本。

用法:
    python3 service_health_check.py [all|服务名...] [选项]

选项:
    --fix              检测失败时自动尝试修复
    --output <file>    将结构化报告写入文件（JSON）
    --json             输出 JSON 到 stdout
    --brief            只输出摘要
    --list             列出所有已注册服务
    --config <path>    指定服务配置文件路径（默认同目录 ../config/services.json）
    --l1-only          只跑 L1 层检测（快速模式）

退出码:
    0 — 全部通过（或修复后全部通过）
    1 — 有失败项
    2 — 脚本本身出错

设计原则:
    - L1 端口/进程存活，L2 核心业务路径
    - 修复命令幂等
    - 报告结构化，方便接入告警
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

# ─── 常量 ───

DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "config" / "services.json"
TZ = timezone(timedelta(hours=8))

# 修复冷却记录：{service_name: last_fix_timestamp}
FIX_COOLDOWN = {}


# ─── 工具函数 ───

def run_cmd(cmd, timeout=30, shell=True):
    """运行命令，返回 (returncode, stdout, stderr, duration_ms)"""
    start = time.time()
    try:
        result = subprocess.run(
            cmd, shell=shell, capture_output=True, text=True,
            timeout=timeout
        )
        dur = int((time.time() - start) * 1000)
        return result.returncode, result.stdout.strip(), result.stderr.strip(), dur
    except subprocess.TimeoutExpired:
        dur = int((time.time() - start) * 1000)
        return 124, "", "timeout", dur
    except Exception as e:
        dur = int((time.time() - start) * 1000)
        return 1, "", str(e), dur


def http_check(url, expect_status=None, expect_contains=None, timeout=10):
    """HTTP 检测，返回 (ok, detail, duration_ms)"""
    start = time.time()
    try:
        req = Request(url, headers={"User-Agent": "service-health-check/1.0"})
        with urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            status = resp.status
    except HTTPError as e:
        dur = int((time.time() - start) * 1000)
        return False, f"HTTP {e.code}", dur
    except URLError as e:
        dur = int((time.time() - start) * 1000)
        return False, f"连接失败: {e.reason}", dur
    except Exception as e:
        dur = int((time.time() - start) * 1000)
        return False, f"请求异常: {e}", dur

    dur = int((time.time() - start) * 1000)

    # 检查状态码
    if expect_status and status not in expect_status:
        return False, f"状态码 {status} (期望 {expect_status})", dur

    # 检查响应内容
    if expect_contains and expect_contains not in body:
        preview = body[:200].replace("\n", " ")
        return False, f"响应不含 '{expect_contains}'，实际: {preview}", dur

    return True, f"HTTP {status} ({len(body)} bytes)", dur


def load_config(path):
    """加载服务配置"""
    if not Path(path).exists():
        print(f"错误: 配置文件不存在: {path}", file=sys.stderr)
        sys.exit(2)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        print(f"错误: 配置文件 JSON 格式错误: {e}", file=sys.stderr)
        sys.exit(2)


# ─── 核心检测逻辑 ───

class ServiceChecker:
    def __init__(self, config, fix=False, l1_only=False):
        self.config = config
        self.fix = fix
        self.l1_only = l1_only
        self.report = {
            "timestamp": datetime.now(TZ).isoformat(),
            "services": {},
            "summary": {"total": 0, "healthy": 0, "degraded": 0, "failed": 0, "fixed": 0}
        }

    def check_service(self, service_id):
        """检测单个服务，返回服务级状态: healthy / degraded / failed"""
        svc_cfg = self.config["services"].get(service_id)
        if not svc_cfg:
            return "failed"

        svc_result = {
            "name": svc_cfg["name"],
            "description": svc_cfg.get("description", ""),
            "priority": svc_cfg.get("priority", "normal"),
            "category": svc_cfg.get("category", "other"),
            "checks": {},
            "overall": "unknown",
            "fix_attempted": False,
            "fix_result": None,
            "total_duration_ms": 0
        }

        start_time = time.time()
        all_pass = True
        l1_pass = True

        for check_id, check_cfg in svc_cfg["checks"].items():
            # L1 only 模式跳过 L2
            if self.l1_only and check_id.startswith("l2_"):
                svc_result["checks"][check_id] = {
                    "status": "skip",
                    "label": check_cfg.get("label", check_id),
                    "detail": "L1-only 模式跳过"
                }
                continue

            ok, detail, dur = self._run_check(check_cfg)
            svc_result["checks"][check_id] = {
                "status": "pass" if ok else "fail",
                "label": check_cfg.get("label", check_id),
                "detail": detail,
                "duration_ms": dur
            }

            if not ok:
                all_pass = False
                if check_id.startswith("l1_"):
                    l1_pass = False

        svc_result["total_duration_ms"] = int((time.time() - start_time) * 1000)

        # 判定服务状态
        if all_pass:
            svc_result["overall"] = "healthy"
        elif l1_pass and not all_pass:
            svc_result["overall"] = "degraded"
        else:
            svc_result["overall"] = "failed"

        # 自动修复
        if self.fix and svc_result["overall"] in ("degraded", "failed"):
            svc_result["fix_attempted"] = True
            fix_ok, fix_detail = self._try_fix(service_id, svc_cfg)
            svc_result["fix_result"] = {"success": fix_ok, "detail": fix_detail}

            if fix_ok:
                # 修复后重测
                recheck_start = time.time()
                recheck_all_pass = True
                for check_id, check_cfg in svc_cfg["checks"].items():
                    if self.l1_only and check_id.startswith("l2_"):
                        continue
                    ok, detail, dur = self._run_check(check_cfg)
                    svc_result["checks"][check_id]["recheck_status"] = "pass" if ok else "fail"
                    svc_result["checks"][check_id]["recheck_detail"] = detail
                    if not ok:
                        recheck_all_pass = False

                svc_result["recheck_duration_ms"] = int((time.time() - recheck_start) * 1000)
                if recheck_all_pass:
                    svc_result["overall"] = "healthy"
                    svc_result["fixed"] = True
                    self.report["summary"]["fixed"] += 1

        self.report["services"][service_id] = svc_result
        return svc_result["overall"]

    def _run_check(self, check_cfg):
        """执行单个检测项，返回 (ok, detail, duration_ms)"""
        ctype = check_cfg["type"]
        timeout = check_cfg.get("timeout", 10)

        if ctype == "http":
            url = check_cfg.get("url", "")
            # 支持从命令动态获取 URL
            if not url and "url_from_command" in check_cfg:
                rc, out, _, _ = run_cmd(check_cfg["url_from_command"], timeout=5)
                if rc == 0 and out.strip():
                    base = out.strip().split("\n")[-1].strip()
                    path = check_cfg.get("path", "/")
                    if base.endswith("/") and path.startswith("/"):
                        url = base.rstrip("/") + path
                    else:
                        url = base + path
                else:
                    return False, f"无法获取 URL: {out[:100]}", 0

            if not url:
                return False, "未配置 URL", 0

            expect_status = check_cfg.get("expect_status")
            expect_contains = check_cfg.get("expect_contains")
            return http_check(url, expect_status=expect_status,
                            expect_contains=expect_contains, timeout=timeout)

        elif ctype == "command":
            cmd = check_cfg["command"]
            rc, out, err, dur = run_cmd(cmd, timeout=timeout)
            expect_contains = check_cfg.get("expect_contains", "")

            # 如果没有配置 expect_contains，只要返回码为 0 就算通过
            if not expect_contains:
                ok = rc == 0
                detail = f"exit={rc}" if ok else f"exit={rc}, {err[:200] or out[:200]}"
                return ok, detail, dur

            # 配置了 expect_contains，检查输出
            combined = out + "\n" + err
            if expect_contains in combined:
                return True, f"包含 '{expect_contains}' (exit={rc})", dur
            else:
                preview = combined[:200].replace("\n", " ")
                return False, f"输出不含 '{expect_contains}'，实际: {preview}", dur

        else:
            return False, f"未知检测类型: {ctype}", 0

    def _try_fix(self, service_id, svc_cfg):
        """尝试修复服务，返回 (success, detail)"""
        fix_cfg = svc_cfg.get("fix")
        if not fix_cfg:
            return False, "该服务未配置修复命令"

        # 冷却检查
        cooldown = fix_cfg.get("cooldown_seconds", 30)
        last_fix = FIX_COOLDOWN.get(service_id, 0)
        if time.time() - last_fix < cooldown:
            remaining = int(cooldown - (time.time() - last_fix))
            return False, f"修复冷却中，剩余 {remaining}s"

        cmd = fix_cfg["command"]
        label = fix_cfg.get("label", cmd[:50])
        max_attempts = fix_cfg.get("max_attempts", 1)

        for attempt in range(1, max_attempts + 1):
            print(f"  [修复 {service_id}] 第 {attempt}/{max_attempts} 次尝试: {label}",
                  file=sys.stderr)
            rc, out, err, dur = run_cmd(cmd, timeout=60)

            if rc == 0 or rc == 124:
                # 命令执行成功（或超时但可能已启动）
                # 等一下让服务起来
                wait_time = max(3, cooldown // 3)
                time.sleep(wait_time)

                FIX_COOLDOWN[service_id] = time.time()
                detail = f"修复命令执行成功 ({dur}ms)"
                if out.strip():
                    detail += f" | {out.strip()[:150]}"
                return True, detail
            else:
                detail = f"修复命令失败 (exit={rc}): {(err or out)[:200]}"
                if attempt < max_attempts:
                    time.sleep(2)

        FIX_COOLDOWN[service_id] = time.time()
        return False, detail

    def run(self, service_names):
        """运行指定服务的检测"""
        available = list(self.config["services"].keys())

        # 展开 all
        if "all" in service_names:
            target = available
        else:
            # 检查是否有不存在的服务
            target = []
            for name in service_names:
                if name not in self.config["services"]:
                    print(f"警告: 未知服务 '{name}'，已跳过。可用服务: {', '.join(available)}",
                          file=sys.stderr)
                else:
                    target.append(name)

        if not target:
            print("错误: 没有可检测的服务", file=sys.stderr)
            sys.exit(2)

        self.report["summary"]["total"] = len(target)

        for svc_id in target:
            status = self.check_service(svc_id)
            if status == "healthy":
                self.report["summary"]["healthy"] += 1
            elif status == "degraded":
                self.report["summary"]["degraded"] += 1
            elif status == "failed":
                self.report["summary"]["failed"] += 1

        return self.report


# ─── 输出格式化 ───

def print_human(report, brief=False):
    s = report["summary"]
    print()
    print("=" * 50)
    print("📊  服务健康检测报告")
    print("=" * 50)
    print(f"🕐  检测时间: {report['timestamp']}")
    print(f"📋  服务总数: {s['total']}")
    print(f"   ✅  健康: {s['healthy']}  ⚠️  降级: {s['degraded']}  ❌ 失败: {s['failed']}  🔧 已修复: {s['fixed']}")
    print()

    if brief:
        return

    for svc_id, svc in report["services"].items():
        status_icon = {
            "healthy": "✅",
            "degraded": "⚠️ ",
            "failed": "❌"
        }.get(svc["overall"], "❓")

        fix_tag = " [已修复]" if svc.get("fixed") else ""
        print(f"{status_icon} {svc['name']} ({svc_id}){fix_tag}")
        print(f"   优先级: {svc['priority']} | 分类: {svc['category']} | 耗时: {svc['total_duration_ms']}ms")

        for check_id, check in svc["checks"].items():
            icon = {"pass": "  ├─ ✅", "fail": "  ├─ ❌", "skip": "  ├─ ⏭️ "}.get(check["status"], "  ├─ ?")
            dur = f" ({check.get('duration_ms', 0)}ms)" if "duration_ms" in check else ""
            detail = f" — {check['detail']}" if check.get("detail") else ""
            print(f"{icon} {check['label']}{dur}{detail}")

            # 修复后的重测结果
            if "recheck_status" in check:
                re_icon = "✅" if check["recheck_status"] == "pass" else "❌"
                print(f"  │     ↳ 修复后重测: {re_icon} {check.get('recheck_detail', '')}")

        if svc.get("fix_attempted") and svc.get("fix_result"):
            fr = svc["fix_result"]
            icon = "✅" if fr["success"] else "❌"
            print(f"   🔧 修复结果: {icon} {fr['detail']}")

        print()

    # 总结
    if s["failed"] == 0 and s["degraded"] == 0:
        print("🎉 所有服务运行正常！")
    else:
        print(f"⚠️  存在异常服务：{s['failed']} 个失败，{s['degraded']} 个降级")
    print()


def print_services(config):
    """列出所有已注册服务"""
    print()
    print("已注册服务清单:")
    print("-" * 60)
    for sid, scfg in config["services"].items():
        checks = list(scfg["checks"].keys())
        l1_count = sum(1 for c in checks if c.startswith("l1_"))
        l2_count = sum(1 for c in checks if c.startswith("l2_"))
        has_fix = "✅" if scfg.get("fix") else "❌"
        print(f"  {sid:<30} {scfg['priority']:<8} L1×{l1_count} L2×{l2_count}  修复:{has_fix}")
        print(f"    └ {scfg.get('description', '')}")
    print()
    print(f"共 {len(config['services'])} 个服务")
    print()


# ─── 主入口 ───

def main():
    parser = argparse.ArgumentParser(
        description="服务健康检测 + 自动修复",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python3 service_health_check.py all                    # 检测所有服务
  python3 service_health_check.py openclaw-gateway       # 检测单个服务
  python3 service_health_check.py all --fix              # 检测并自动修复
  python3 service_health_check.py all --json             # JSON 输出
  python3 service_health_check.py all --l1-only          # 只跑 L1 快速检测
  python3 service_health_check.py --list                 # 列出所有服务
  python3 service_health_check.py all --output report.json  # 输出报告到文件
        """
    )
    parser.add_argument("services", nargs="*", default=["all"],
                        help="要检测的服务名（all 表示全部）")
    parser.add_argument("--fix", action="store_true", help="检测失败时自动修复")
    parser.add_argument("--output", metavar="FILE", help="将 JSON 报告写入文件")
    parser.add_argument("--json", action="store_true", help="输出 JSON 格式到 stdout")
    parser.add_argument("--brief", action="store_true", help="只输出摘要")
    parser.add_argument("--list", action="store_true", help="列出所有已注册服务")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG),
                        help=f"服务配置文件路径（默认: {DEFAULT_CONFIG}）")
    parser.add_argument("--l1-only", action="store_true", help="只跑 L1 层检测（快速模式）")
    args = parser.parse_args()

    # 加载配置
    config = load_config(args.config)

    # --list 模式
    if args.list:
        print_services(config)
        sys.exit(0)

    # 运行检测
    checker = ServiceChecker(config, fix=args.fix, l1_only=args.l1_only)

    try:
        report = checker.run(args.services)
    except KeyboardInterrupt:
        print("\n检测已中断", file=sys.stderr)
        sys.exit(2)
    except Exception as e:
        print(f"检测运行失败: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(2)

    # 输出文件
    if args.output:
        try:
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
            print(f"报告已写入: {args.output}", file=sys.stderr)
        except Exception as e:
            print(f"写入报告文件失败: {e}", file=sys.stderr)

    # stdout 输出
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_human(report, brief=args.brief)

    # 退出码
    s = report["summary"]
    if s["failed"] > 0:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
