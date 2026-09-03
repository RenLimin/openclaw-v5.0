#!/usr/bin/env python3
"""
系统异常统一扫描 — 覆盖 cron 错误 + LLM 超时 + Provider 健康
输出结构化 JSON 供自动化处置使用
"""
import json
import re
import subprocess
import sys
from datetime import datetime

WORKSPACE = "/Users/bangcle/.openclaw/workspace"
LOG_FILE = f"{WORKSPACE}/memory/error-scan-latest.json"


def run_cmd(cmd, timeout=15):
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )
        return result.stdout.strip(), result.returncode
    except subprocess.TimeoutExpired:
        return "TIMEOUT", -1
    except Exception as e:
        return str(e), -1


def scan_cron_errors():
    """扫描 cron job 错误"""
    output, rc = run_cmd("openclaw cron list --all 2>/dev/null")
    if rc != 0:
        return [{"error": f"cron list failed: {output}"}]

    errors = []
    # 自排除：获取当前 cron job 的 ID（通过环境变量或脚本路径识别）
    self_job_id = "e776e653-6fa0-48e4-8338-536af3ce1f0a"  # 错误扫描 cron 的 jobId
    # 已知已修复/已删除的 cron ID（不再报告）
    known_resolved_ids = {
        "63927a5a-721d-45a5-aa5d-9b95357d9453",  # provider 健康探测(agent turn, 已删除)
    }

    for line in output.split("\n"):
        parts = line.split()
        if not parts:
            continue
        job_id = parts[0]
        if not job_id.startswith(("a", "b", "c", "d", "e", "f")):
            continue
        # 排除自己和已知已修复的 cron
        if job_id == self_job_id:
            continue
        if job_id in known_resolved_ids:
            continue

        # 获取最近运行状态
        runs_output, _ = run_cmd(f"openclaw cron runs --id {job_id} --limit 3 2>/dev/null")
        # 只报告执行失败（exit code != 0），排除 delivery 失败和偶发网络问题
        # completionStatus=failed + exitCode!=0 才是真正的执行失败
        exec_fail_count = 0
        for entry_block in runs_output.split('"action": "finished"'):
            if '"exitCode": 0' in entry_block:
                continue  # 执行成功
            if '"exitCode"' in entry_block:
                # 有 exit code 且非 0
                m = re.search(r'"exitCode":\s*(\d+)', entry_block)
                if m and int(m.group(1)) != 0:
                    exec_fail_count += 1
        if exec_fail_count >= 2:
            # 获取 job 名称
            name_output, _ = run_cmd(f'openclaw cron get {job_id} 2>/dev/null | grep \'"name"\' | head -1')
            name = name_output.split(":")[-1].strip().strip('"').strip() if name_output else job_id
            errors.append({
                "job_id": job_id,
                "name": name,
                "type": "cron_error",
                "detail": f"recent runs contain {exec_fail_count} execution failures"
            })

    return errors


def scan_llm_timeouts():
    """扫描 LLM 超时错误（从 gateway 日志中检测）"""
    errors = []

    # 检查 gateway 日志中的超时
    log_output, rc = run_cmd(
        "ls -lt ~/.openclaw/logs/gateway*.log 2>/dev/null | head -1 | awk '{print $NF}'"
    )
    if rc == 0 and log_output:
        # 检查最近 100 行中的超时错误
        recent, _ = run_cmd(f"tail -100 {log_output} 2>/dev/null | grep -i 'timeout\\|LLM.*time\\|request.*time'")
        if recent:
            for line in recent.split("\n")[:5]:
                errors.append({
                    "type": "llm_timeout",
                    "detail": line.strip()[:200],
                    "source": "gateway_log"
                })

    return errors


def scan_provider_health():
    """检查 Provider 健康状态"""
    errors = []
    output, rc = run_cmd("openclaw status 2>&1")
    if rc != 0:
        errors.append({"type": "provider_error", "detail": f"status check failed: {output[:200]}"})
        return errors

    # 检查是否有 provider 报错
    for line in output.split("\n"):
        if any(kw in line.lower() for kw in ["error", "failed", "down", "unreachable"]):
            errors.append({
                "type": "provider_error",
                "detail": line.strip()[:200]
            })

    return errors


def auto_fix(errors):
    """自动处置检测到的错误"""
    fixes = []

    timeout_errors = [e for e in errors if e.get("type") == "llm_timeout"]
    provider_errors = [e for e in errors if e.get("type") == "provider_error"]
    cron_errors = [e for e in errors if e.get("type") == "cron_error"]

    # 处置 1: LLM 超时 → 重启 Gateway
    if timeout_errors:
        fixes.append({
            "action": "gateway_restart",
            "reason": f"Detected {len(timeout_errors)} LLM timeout(s)",
            "executed": False
        })
        # 实际执行重启
        rc = run_cmd("openclaw gateway restart 2>&1")[1]
        fixes[-1]["executed"] = True
        fixes[-1]["result"] = "success" if rc == 0 else f"failed (rc={rc})"

    # 处置 2: Provider 错误 → 记录并建议切换
    if provider_errors:
        fixes.append({
            "action": "model_fallback_suggested",
            "reason": f"Detected {len(provider_errors)} provider error(s)",
            "detail": "Consider switching to fallback model via /model command"
        })

    # 处置 3: Cron 错误 → 记录待人工处理
    if cron_errors:
        fixes.append({
            "action": "manual_review",
            "reason": f"Detected {len(cron_errors)} cron error(s)",
            "detail": "Run 'openclaw cron runs <id>' for details"
        })

    return fixes


def main():
    now = datetime.now().isoformat()
    print(f"=== System Error Scan ({now}) ===\n")

    # 扫描所有错误类型
    all_errors = []
    all_errors.extend(scan_cron_errors())
    all_errors.extend(scan_llm_timeouts())
    all_errors.extend(scan_provider_health())

    # 输出结果
    if all_errors:
        print(f"⚠️ 发现 {len(all_errors)} 个异常:\n")
        for err in all_errors:
            print(f"  [{err['type']}] {err.get('name', '')} — {err['detail'][:100]}")

        # 自动处置
        print(f"\n--- Auto-Fix ---")
        fixes = auto_fix(all_errors)
        for fix in fixes:
            status = "✅" if fix.get("executed") else "⚠️"
            print(f"  {status} {fix['action']}: {fix['reason']}")
            if "result" in fix:
                print(f"     Result: {fix['result']}")
    else:
        print("✅ 系统无异常")

    # 保存结构化结果
    result = {
        "timestamp": now,
        "errors": all_errors,
        "fixes": auto_fix(all_errors) if all_errors else [],
        "healthy": len(all_errors) == 0
    }
    try:
        with open(LOG_FILE, "w") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    return 0 if not all_errors else 1


if __name__ == "__main__":
    sys.exit(main())
