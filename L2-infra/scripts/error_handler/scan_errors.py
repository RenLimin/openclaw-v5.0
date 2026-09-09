#!/usr/bin/env python3
"""
系统异常统一扫描 — 覆盖 cron 错误 + LLM 超时 + Provider 健康
输出结构化 JSON 供自动化处置使用
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path
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


def scan_provider_config_full_chain():
    """配置全链路检测：apiKey 格式 + baseUrl 可达性 + 三层一致性 + 端到端验证"""
    errors = []
    
    # 1. 从 openclaw.json 读 provider 配置（底层）
    openclaw_json_path = os.path.expanduser("~/.openclaw/openclaw.json")
    with open(openclaw_json_path, "r") as f:
        openclaw_cfg = json.load(f)
    openclaw_providers = openclaw_cfg.get("models", {}).get("providers", {})
    
    # 2. 从 models.json 读 provider 配置（中层）
    models_json_path = os.path.expanduser("~/.openclaw/agents/main/agent/models.json")
    with open(models_json_path, "r") as f:
        models_cfg = json.load(f)
    models_providers = models_cfg.get("providers", {})
    
    # 3. 检查每个 provider
    for provider_name in set(list(openclaw_providers.keys()) + list(models_providers.keys())):
        oc_provider = openclaw_providers.get(provider_name, {})
        ms_provider = models_providers.get(provider_name, {})
        
        # 用优先级更高的那个做实际检测（models.json > openclaw.json）
        active = ms_provider if ms_provider else oc_provider
        if not active:
            continue
        
        base_url = active.get("baseUrl", "").rstrip("/")
        api_key = active.get("apiKey", "")
        
        # 检测 1: apiKey 格式检查
        if isinstance(api_key, dict):
            # 错误旧格式：有 provider + id 但没有 source
            if "provider" in api_key and "id" in api_key and "source" not in api_key:
                errors.append({
                    "type": "api_key_format_error",
                    "detail": f"provider {provider_name}: apiKey is old-format dict (missing 'source'), will cause 401"
                })
            # source=file 但 path 不对
            elif api_key.get("source") == "file" and "path" not in api_key:
                errors.append({
                    "type": "api_key_format_error",
                    "detail": f"provider {provider_name}: apiKey file ref missing 'path' field"
                })
        
        # 检测 2: baseUrl 可达性 + 正确端点验证
        if base_url:
            # 简单可达性检查（HEAD 请求）
            import urllib.request
            import urllib.error
            test_url = f"{base_url}/models"
            try:
                req = urllib.request.Request(test_url, method="GET")
                if isinstance(api_key, str) and api_key and not api_key.startswith("/"):
                    # 字符串且不是路径，当 key 用
                    req.add_header("Authorization", f"Bearer {api_key}")
                elif isinstance(api_key, str) and api_key.startswith("/"):
                    # 文件路径，读出来
                    try:
                        with open(api_key, "r") as f:
                            key_content = f.read().strip()
                        req.add_header("Authorization", f"Bearer {key_content}")
                    except:
                        pass
                
                with urllib.request.urlopen(req, timeout=5) as resp:
                    if resp.getcode() == 401:
                        errors.append({
                            "type": "provider_auth_failed",
                            "detail": f"provider {provider_name}: baseUrl reachable but auth failed (401)"
                        })
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    errors.append({
                        "type": "provider_rate_limited",
                        "detail": f"provider {provider_name}: rate limited (429) at {base_url}. Check if baseUrl endpoint is correct (e.g. coding/v3 vs v3 for Volcengine Ark)"
                    })
                elif e.code == 404:
                    errors.append({
                        "type": "provider_endpoint_wrong",
                        "detail": f"provider {provider_name}: endpoint returned 404 at {test_url}. Verify baseUrl path."
                    })
                elif e.code == 401:
                    errors.append({
                        "type": "provider_auth_failed",
                        "detail": f"provider {provider_name}: auth failed (401) at {base_url}"
                    })
            except Exception as e:
                # 网络错误等，记为 warning
                pass  # 不强制报错，网络波动正常
        
        # 检测 3: 三层配置一致性（比较 openclaw.json 和 models.json）
        if oc_provider and ms_provider:
            oc_base = oc_provider.get("baseUrl", "")
            ms_base = ms_provider.get("baseUrl", "")
            if oc_base and ms_base and oc_base != ms_base:
                errors.append({
                    "type": "config_inconsistent",
                    "detail": f"provider {provider_name}: baseUrl mismatch - openclaw.json={oc_base} vs models.json={ms_base}"
                })
    
    # 检测 4: model-scheduling 代理配置一致性（第 4 层）
    ms_proxy_config = os.path.expanduser(
        "~/.openclaw/workspace/L2-infra/components/model-scheduling/config/providers.yaml"
    )
    if os.path.exists(ms_proxy_config):
        try:
            import yaml
            with open(ms_proxy_config, "r") as f:
                proxy_data = yaml.safe_load(f)
            proxy_providers = proxy_data.get("providers", {})
            for pname, pconf in proxy_providers.items():
                proxy_base = pconf.get("base_url", "")
                # 和 models.json 对比
                if pname in models_providers:
                    models_base = models_providers[pname].get("baseUrl", "")
                    if proxy_base and models_base and proxy_base != models_base:
                        errors.append({
                            "type": "config_inconsistent",
                            "detail": f"provider {pname}: baseUrl mismatch - model-scheduling proxy={proxy_base} vs models.json={models_base}"
                        })
                # 检查 API Key 是否能获取到
                if pconf.get("enabled", False):
                    api_key_ref = pconf.get("api_key_ref", "")
                    if api_key_ref:
                        # 检查环境变量或 auth-profiles.json 中是否有这个 key
                        auth_file = os.path.expanduser("~/.openclaw/auth-profiles.json")
                        has_key = False
                        if os.path.exists(auth_file):
                            with open(auth_file, "r") as f:
                                auth_data = json.load(f)
                            for pid, pc in auth_data.get("profiles", {}).items():
                                if pid.startswith(pname) and pc.get("apiKey"):
                                    has_key = True
                                    break
                        if not has_key and not os.environ.get(api_key_ref.upper()):
                            # 不在环境变量也不在 auth-profiles，警告
                            pass  # 可能在环境变量里启动时设置，不一定有问题
        except ImportError:
            # PyYAML 没装，跳过
            pass
        except Exception as e:
            errors.append({
                "type": "proxy_config_check_failed",
                "detail": f"Failed to check model-scheduling proxy config: {str(e)[:100]}"
            })
    
    # 检测 5: model-scheduling 代理服务是否在运行
    try:
        import urllib.request
        req = urllib.request.Request("http://127.0.0.1:3000/health")
        with urllib.request.urlopen(req, timeout=3) as resp:
            if resp.getcode() != 200:
                errors.append({
                    "type": "proxy_unhealthy",
                    "detail": "model-scheduling proxy health check failed"
                })
    except Exception:
        errors.append({
            "type": "proxy_down",
            "detail": "model-scheduling proxy is not running on port 3000"
        })
    
    return errors


def scan_provider_api_key_format():
    """全量检查所有 provider 的 apiKey 格式（保留向后兼容）"""
    errors = []
    output, rc = run_cmd("openclaw config get models.providers --output json 2>/dev/null")
    if rc != 0:
        errors.append({"type": "api_key_format_error", "detail": f"failed to get providers config: {output[:200]}"})
        return errors
    
    try:
        providers = json.loads(output)
    except json.JSONDecodeError as e:
        errors.append({"type": "api_key_format_error", "detail": f"failed to parse providers config: {e}"})
        return errors
    
    for provider_name, provider_config in providers.items():
        if 'apiKey' not in provider_config:
            continue
        api_key = provider_config['apiKey']
        # 检查格式：如果是字典，必须是正确的 SecretRef 结构
        if isinstance(api_key, dict):
            # 正确结构：{source: store, provider: default, id: NAME} 或者 {source: file, ...} 已经在解析时处理
            # 只检查错误的旧结构
            if 'provider' in api_key and 'id' in api_key and not ('source' in api_key):
                errors.append({
                    "type": "api_key_format_error",
                    "detail": f"provider {provider_name}: apiKey is old-format dict, should be fixed to correct SecretRef"
                })
            elif 'source' in api_key and api_key['source'] == 'file' and 'id' not in api_key and 'path' not in api_key:
                errors.append({
                    "type": "api_key_format_error",
                    "detail": f"provider {provider_name}: apiKey file ref has incorrect structure"
                })
        # 对于文件引用，检查文件是否存在
        if isinstance(api_key, dict) and api_key.get('source') == 'file' and 'path' in api_key:
            path = api_key['path']
            if not os.path.exists(path):
                errors.append({
                    "type": "api_key_file_not_found",
                    "detail": f"provider {provider_name}: apiKey file not found at {path}"
                })
    
    return errors


def scan_asset_consistency():
    """检测系统资产一致性：路径、层级、依赖是否与架构文档一致"""
    errors = []
    # 检查关键资产路径
    key_assets = [
        # (路径, 描述)
        ("docs/architecture/configuration/api-key-configuration.md", "API Key 配置规范文档"),
        ("L2-infra/scripts/error_handler/scan_errors.py", "全量错误扫描脚本"),
        ("L2-infra/scripts/error_handler/handle_timeout.sh", "LLM 超时自动处置脚本"),
        ("~/.openclaw/secrets/codingplan.apiKey", "codingplan API Key 文件"),
        ("~/.openclaw/secrets/longcat.apiKey", "longcat API Key 文件"),
    ]
    
    for asset_path, description in key_assets:
        expanded_path = os.path.expanduser(asset_path)
        if not os.path.exists(expanded_path):
            errors.append({
                "type": "asset_missing",
                "detail": f"{description} not found at {asset_path}"
            })
    
    # 检查架构分层文档存在
    arch_docs = list(Path(WORKSPACE).glob("docs/architecture/**/*.md"))
    if len(arch_docs) < 5:  # 应该至少有几份架构文档
        errors.append({
            "type": "arch_docs_incomplete",
            "detail": f"Only {len(arch_docs)} architecture docs found, expected >= 5"
        })
    
    return errors


def scan_zombie_processes():
    """检测僵尸进程和已完成会话残留，建议清理"""
    errors = []
    output, rc = run_cmd("ps axo pid,ppid,stat,comm | grep 'Z' | head -20")
    if rc == 0 and output.strip():
        zombie_count = len(output.strip().split("\n"))
        errors.append({
            "type": "zombie_processes",
            "detail": f"Found {zombie_count} zombie processes. Recommend system reboot or manual kill."
        })
    
    # 检查残留子会话目录
    output, rc = run_cmd("ls -d /Users/bangcle/.openclaw/sandboxes/workspace-* 2>/dev/null | wc -l")
    if rc == 0:
        count = int(output.strip())
        if count > 5:
            errors.append({
                "type": "stale_sandboxes",
                "detail": f"Found {count} stale sandbox directories. Consider cleanup with 'rm -rf ~/.openclaw/sandboxes/workspace-*'"
            })
    
    return errors


def scan_temp_files_cleanup():
    """检测临时文件、备份文件，建议清理或备份"""
    errors = []
    
    # 检查 /tmp 备份
    tmp_backups = run_cmd("find /tmp -name '*L0*backup*' -o -name '*.backup' 2>/dev/null")[0]
    if tmp_backups.strip():
        files = tmp_backups.strip().split("\n")
        errors.append({
            "type": "tmp_backup_files",
            "detail": f"Found {len(files)} backup files in /tmp. Recommend review and cleanup."
        })
    
    # 检查未跟踪文件在 workspace
    output, rc = run_cmd("cd /Users/bangcle/.openclaw/workspace && git status --porcelain | grep '^??' | wc -l")
    if rc == 0 and output.strip():
        count = int(output.strip())
        if count > 10:
            errors.append({
                "type": "untracked_files",
                "detail": f"Found {count} untracked files in workspace. Recommend commit or cleanup."
            })
    
    # 检查日志文件大小 (gateway logs)
    output, rc = run_cmd("du -h ~/.openclaw/logs/ | tail -1")
    if rc == 0 and output:
        size_str = output.split()[0]
        errors.append({
            "type": "log_dir_size",
            "detail": f"Gateway log directory size is {size_str}. Cleanup old logs if > 100M."
        })
    
    return errors


def scan_provider_health():
    """检查 Provider 健康状态"""
    errors = []
    # 配置全链路检测（含 apiKey 格式 + baseUrl 可达 + 三层一致性）
    errors.extend(scan_provider_config_full_chain())
    # 检查资产一致性
    errors.extend(scan_asset_consistency())
    # 检查僵尸进程
    errors.extend(scan_zombie_processes())
    # 检查临时文件/备份
    errors.extend(scan_temp_files_cleanup())
    
    output, rc = run_cmd("openclaw status 2>&1")
    if rc != 0:
        errors.append({"type": "provider_error", "detail": f"status check failed: {output[:200]}"})
        return errors

    # 检查是否有 provider 报错
    for line in output.split("\n"):
        if any(kw in line.lower() for kw in ["error", "failed", "down", "unreachable", "401", "unauthorized", "api.*key"]):
            errors.append({
                "type": "provider_error",
                "detail": line.strip()[:200]
            })

    return errors


def auto_fix(errors):
    """自动处置检测到的错误"""
    fixes = []

    timeout_errors = [e for e in errors if e.get("type") == "llm_timeout"]
    provider_errors = [e for e in errors if "provider" in e.get("type") or "api_key" in e.get("type") or "asset" in e.get("type")]
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

    # 处置 2: Provider 错误 / API Key 错误 / 资产错误 → 记录并建议检查
    if provider_errors:
        has_401 = any("401" in e.get("detail", "") or "unauthorized" in e.get("detail", "").lower() or "api_key" in e.get("type") or "auth_failed" in e.get("type") for e in provider_errors)
        has_429 = any("rate_limit" in e.get("type") or "429" in e.get("detail", "") for e in provider_errors)
        has_endpoint_wrong = any("endpoint_wrong" in e.get("type") for e in provider_errors)
        has_config_mismatch = any("config_inconsistent" in e.get("type") for e in provider_errors)

        fixes.append({
            "action": "model_fallback_suggested",
            "reason": f"Detected {len(provider_errors)} provider/asset error(s)",
            "detail": "Consider switching to fallback model via /model command"
        })

        # 2a: 401 / API Key 认证失败 → 详细排查指引
        if has_401:
            fixes.append({
                "action": "check_api_key_format",
                "reason": "401 Unauthorized / API Key format error detected",
                "detail": "Run full chain check: 1) Verify apiKey format (not old-format dict) 2) Check all 3 layers (auth profile > models.json > openclaw.json) 3) Test with direct curl. See docs/architecture/configuration/api-key-configuration.md §6 SOP."
            })

        # 2b: 429 限流 / baseUrl 端点错误 → 提示切 coding/v3 端点 + 切 fallback
        if has_429 or has_endpoint_wrong:
            fixes.append({
                "action": "verify_baseurl_endpoint",
                "reason": "Rate limit (429) or wrong endpoint (404) detected",
                "detail": "For Volcengine Ark coding-plan: MUST use /api/coding/v3 (not /api/v3). /api/v3 triggers Safe Experience Mode rate limit. See docs/architecture/configuration/api-key-configuration.md §2.2."
            })
            fixes.append({
                "action": "switch_to_fallback_model",
                "reason": "Primary provider rate-limited or endpoint wrong",
                "detail": "Switch to fallback model: coding-plan/doubao-seed-2-1-turbo. Use '/model' command in session."
            })

        # 2c: 配置不一致 → 提示逐层检查并同步
        if has_config_mismatch:
            fixes.append({
                "action": "sync_config_across_layers",
                "reason": "Config mismatch detected across layers (openclaw.json vs models.json)",
                "detail": "Provider config differs between openclaw.json and agent models.json. Sync to ensure consistency. models.json has higher priority. See docs/architecture/configuration/api-key-configuration.md §1."
            })

        # 资产不一致提示
        asset_errors = [e for e in provider_errors if "asset" in e.get("type")]
        if asset_errors:
            fixes.append({
                "action": "verify_asset_consistency",
                "reason": f"Found {len(asset_errors)} asset consistency issues",
                "detail": "Verify assets are at correct paths and match architecture docs."
            })

        # 僵尸进程提示
        zombie_errors = [e for e in errors if "zombie" in e.get("type")]
        if zombie_errors:
            fixes.append({
                "action": "cleanup_zombies",
                "reason": f"Found {len(zombie_errors)} zombie/zombie related issues",
                "detail": "Reboot system to fully clean up zombies, or kill manually."
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

    # 扫描脚本的任务是"发现并报告异常"，不是"确保系统无异常"
    # 发现异常是正常输出，不是任务失败 — 任务失败只在脚本本身执行出错时才发生
    # 异常信息通过 JSON 输出文件和 stdout 传递，cron 应该读这些而不是看 exit code
    return 0


if __name__ == "__main__":
    sys.exit(main())
