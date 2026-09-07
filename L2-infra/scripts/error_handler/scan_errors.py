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


def _parse_cron_list_table(output):
    """解析 `openclaw cron list --all` 的表格输出，返回 [{job_id, name, status, ...}]
    注意：表头可能有重名列（如 Agent ID 会拆成 Agent 和 ID 两列），所以用列索引去重。"""
    rows = []
    lines = output.strip().split("\n")
    if len(lines) < 2:
        return rows

    # 从表头确定各列位置
    header = lines[0]
    col_names = []
    col_positions = []  # (start_idx, end_idx_exclusive)
    seen_names = set()
    for m in re.finditer(r'\S+', header):
        name = m.group(0)
        # 重名处理：Agent ID 拆成的第二个 "ID" 会跟第一个 "ID" 冲突，加后缀
        if name in seen_names:
            name = f"{name}_dup"
        seen_names.add(name)
        col_names.append(name)
        col_positions.append([m.start(), None])
    # 每列的结束位置 = 下一列的起始位置；最后一列到行尾
    for idx in range(len(col_positions) - 1):
        col_positions[idx][1] = col_positions[idx + 1][0]
    if col_positions:
        col_positions[-1][1] = 999

    # 跳过分隔线行（含 --- 或全是空格+横线）
    data_start = 1
    if data_start < len(lines) and re.match(r'^[\s\-]+$', lines[data_start]):
        data_start += 1

    for line in lines[data_start:]:
        if not line.strip():
            continue
        row = {}
        for name, (start, end) in zip(col_names, col_positions):
            val = line[start:min(end, len(line))].strip()
            row[name] = val
        # 第一列就是 job ID（UUID 格式）
        first_col = row.get(col_names[0], "")
        if re.match(r'^[0-9a-f]{8}-', first_col):
            # 确保 "ID" 键指向正确的 job_id（防重名覆盖）
            row["ID"] = first_col
            rows.append(row)
    return rows


def scan_cron_errors():
    """扫描 cron job 错误（基于 cron list 的 status 列 + runs 详情）"""
    output, rc = run_cmd("openclaw cron list --all 2>/dev/null")
    if rc != 0:
        return [{"error": f"cron list failed: {output}"}]

    errors = []
    self_job_id = "e776e653-6fa0-48e4-8338-536af3ce1f0a"  # 错误扫描 cron 的 jobId
    known_resolved_ids = {
        "63927a5a-721d-45a5-aa5d-9b95357d9453",  # provider 健康探测(agent turn, 已删除)
    }
    # heartbeat 任务：no-route skipped / 瞬态 timeout 属预期行为，不作为异常源
    heartbeat_ids = {
        "5d833bb5-6dde-4eb7-ac77-0777546db953",  # heartbeat:main
        "1c133572-3b50-4e14-96c4-ef2f7054fe5a",  # heartbeat:ms-research
        "9fe434a8-9edf-49c0-8ab6-03525b1b4184",  # heartbeat:ms-coding
    }

    rows = _parse_cron_list_table(output)
    for row in rows:
        job_id = row.get("ID", "")
        if not job_id or job_id == self_job_id or job_id in known_resolved_ids or job_id in heartbeat_ids:
            continue

        name = row.get("Name", job_id)
        status = row.get("Status", "")

        # 规则 1: status 含 error / failed / timeout → 直接报异常
        is_error_status = bool(re.search(r'error|fail|timeout', status, re.IGNORECASE))

        # 规则 2: status 为 ok 但含连续失败计数（如 "error (3x)"）也报
        consecutive = 0
        m = re.search(r'\((\d+)x\)', status)
        if m:
            consecutive = int(m.group(1))

        # 规则 3: status 为 ok/running 也查 runs 历史，确认最近是否有连续失败
        if not is_error_status:
            fail_count, last_error = _count_recent_failures(job_id, limit=5)
            if fail_count >= 2:
                is_error_status = True
                consecutive = fail_count
                status = last_error or status

        if is_error_status and consecutive >= 2:
            errors.append({
                "job_id": job_id,
                "name": name,
                "type": "cron_error",
                "detail": f"status: {status} (连续 {consecutive} 次失败)",
                "consecutive_failures": consecutive
            })
        elif is_error_status:
            # 偶发 1 次失败，记为 warning 级别
            errors.append({
                "job_id": job_id,
                "name": name,
                "type": "cron_warning",
                "detail": f"status: {status} (单次失败，可能为瞬态)",
                "consecutive_failures": consecutive
            })

    return errors


def _count_recent_failures(job_id, limit=5):
    """统计最近 N 次运行中的**连续失败**次数（从最新往旧数，遇到成功即停），返回 (连续失败数, 最后一条错误信息)
    
    失败判定：status == "error" 才算真正的执行失败；status == "ok" 即使 completion=failed 也不算（可能是 delivery 等附属失败）
    """
    runs_output, rc = run_cmd(f"openclaw cron runs --id {job_id} --limit {limit} 2>/dev/null")
    if rc != 0 or not runs_output.strip():
        return 0, None

    try:
        data = json.loads(runs_output)
        entries = data.get("entries", [])
    except (json.JSONDecodeError, AttributeError):
        return 0, None

    consecutive = 0
    last_error = None
    for entry in entries:
        if entry.get("action") != "finished":
            continue  # running / skipped 等状态跳过，不中断连续计数
        status = entry.get("status", "")
        if status == "error":
            consecutive += 1
            if not last_error:
                last_error = entry.get("error", status)
        elif status == "ok":
            # 遇到成功，中断连续计数
            break
        # 其他 status（如 skipped）跳过，不中断
    return consecutive, last_error


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
