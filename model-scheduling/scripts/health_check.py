#!/usr/bin/env python3
"""网络健康探测:检测各 provider 的可用性和延迟。

设计约束:
  - 只读访问 openclaw.json
  - 外部文件 config/usage.json 更新健康状态
  - 轻量探测(发送最小请求,不消耗大量 token)
  - 支持 --dry-run 预览
"""

import argparse
import json
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = REPO_ROOT / "config"
USAGE_FILE = CONFIG_DIR / "usage.json"


def get_openclaw_config(path: str) -> dict:
    """只读获取 openclaw.json。
    
    直接读取文件而非 openclaw config get，因为后者对 apiKey 脱敏。
    """
    config_path = Path.home() / ".openclaw" / "openclaw.json"
    try:
        cfg = json.loads(config_path.read_text())
        # 按 path 路径提取子树
        parts = path.split(".")
        for part in parts:
            if isinstance(cfg, dict) and part in cfg:
                cfg = cfg[part]
            else:
                return {}
        return cfg if isinstance(cfg, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return {}


def _resolve_api_key(provider_conf: dict) -> str:
    """解析 apiKey，支持 SecretRef(file/env source)。"""
    import os
    api_key = provider_conf.get("apiKey", "")
    if isinstance(api_key, dict):
        source = api_key.get("source", "")
        if source == "file":
            # SecretRef file source: 从 ~/.openclaw/secrets/ 读取
            provider = api_key.get("provider", "")
            secrets_dir = Path.home() / ".openclaw" / "secrets"
            for fname in [f"{provider}", f"{provider}.apiKey", f"{provider.replace('key', '')}.apiKey"]:
                fpath = secrets_dir / fname
                if fpath.exists():
                    return fpath.read_text().strip()
            return ""  # 找不到文件
        elif source == "env":
            # SecretRef env source: 从环境变量读取
            env_var = api_key.get("id", "")
            return os.environ.get(env_var, "")
    return str(api_key) if api_key else ""


def ping_provider(provider_id: str, provider_conf: dict) -> dict:
    """轻量探测 provider 健康状态。"""
    base_url = provider_conf.get("baseUrl", "")
    api_key = _resolve_api_key(provider_conf)
    api_type = provider_conf.get("api", "openai-completions")

    if not base_url:
        return {"status": "no_base_url", "latency_ms": -1}

    # 使用 models 列表端点作为健康检查(轻量,不消耗 token)
    health_url = base_url.rstrip("/") + "/models"
    start = time.monotonic()
    try:
        req = urllib.request.Request(
            health_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="GET",
        )
        response = urllib.request.urlopen(req, timeout=10)
        latency_ms = int((time.monotonic() - start) * 1000)
        status_code = response.getcode()

        if status_code == 200:
            result = {
                "status": "healthy",
                "latency_ms": latency_ms,
                "last_checked": datetime.now(timezone.utc).isoformat(),
            }
        else:
            result = {
                "status": "degraded",
                "latency_ms": latency_ms,
                "http_code": status_code,
                "last_checked": datetime.now(timezone.utc).isoformat(),
            }
    except urllib.error.HTTPError as e:
        latency_ms = int((time.monotonic() - start) * 1000)
        result = {
            "status": "error",
            "latency_ms": latency_ms,
            "http_code": e.code,
            "error": str(e)[:100],
            "last_checked": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        latency_ms = int((time.monotonic() - start) * 1000)
        result = {
            "status": "unreachable",
            "latency_ms": latency_ms,
            "error": str(e)[:100],
            "last_checked": datetime.now(timezone.utc).isoformat(),
        }

    # ─── model ID 可用性验证 ───
    # 即使 /models 返回 200，配置的 model ID 也可能已下线（如火山 Ark 模型 ID 更新）
    # 对每个配置的 model 发最小推理请求（max_tokens=1），验证实际可用性
    models_list = provider_conf.get("models", [])
    if models_list and api_key:
        model_statuses = {}
        for model_def in models_list:
            model_id = model_def.get("id", "")
            if not model_id:
                continue
            # 跳过 embedding 模型（不支持 chat/completions）
            model_name = model_def.get("name", "")
            if any(kw in model_id.lower() or kw in model_name.lower() for kw in ["embedding", "vision"]):
                model_statuses[model_id] = {"status": "skipped", "reason": "embedding model"}
                continue
            # 发最小推理请求
            chat_url = base_url.rstrip("/") + "/chat/completions"
            try:
                body = json.dumps({
                    "model": model_id,
                    "messages": [{"role": "user", "content": "hi"}],
                    "max_tokens": 1,
                }).encode()
                req = urllib.request.Request(
                    chat_url,
                    data=body,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    method="POST",
                )
                resp = urllib.request.urlopen(req, timeout=15)
                model_statuses[model_id] = {
                    "status": "available",
                    "http_code": resp.getcode(),
                }
            except urllib.error.HTTPError as e:
                err_body = ""
                try:
                    err_body = e.read().decode()[:150]
                except Exception:
                    pass
                model_statuses[model_id] = {
                    "status": "unavailable",
                    "http_code": e.code,
                    "error": err_body,
                }
            except Exception as e:
                model_statuses[model_id] = {
                    "status": "unreachable",
                    "error": str(e)[:100],
                }
        result["models"] = model_statuses

    return result


def main():
    parser = argparse.ArgumentParser(description="网络健康探测")
    parser.add_argument("--dry-run", action="store_true", help="预览但不写入")
    parser.add_argument("--force", action="store_true", help="跳过确认")
    args = parser.parse_args()

    print("=== 网络健康探测 ===")
    print()

    # 1. 读取 openclaw.json(只读)
    print("[1/3] 读取 openclaw.json ...")
    providers_config = get_openclaw_config("models")
    providers = providers_config.get("providers", {})
    print(f"  发现 {len(providers)} 个 provider")

    # 跳过显式禁用的 provider（enabled: false）
    disabled_providers = [pid for pid, pconf in providers.items() if pconf.get("enabled") is False]
    if disabled_providers:
        for pid in disabled_providers:
            print(f"  ⏭️  跳过已禁用 provider: {pid}")
        providers = {pid: pconf for pid, pconf in providers.items() if pconf.get("enabled") is not False}

    # 2. 逐个探测（含 model ID 验证）
    print("[2/3] 探测 provider 健康状态（含 model ID 验证）...")
    health = {}
    for pid, pconf in providers.items():
        result = ping_provider(pid, pconf)
        health[pid] = result
        status_icon = {"healthy": "✅", "degraded": "⚠️", "error": "❌", "unreachable": "❌"}.get(result["status"], "?")
        print(f"  [{pid}] {status_icon} {result['status']} ({result['latency_ms']}ms)")
        # 打印 model ID 验证结果
        model_statuses = result.get("models", {})
        if model_statuses:
            for mid, mst in model_statuses.items():
                ms_icon = {"available": "  ✅", "unavailable": "  ❌", "skipped": "  ⏭️", "unreachable": "  ⚠️"}.get(mst["status"], "  ?")
                detail = ""
                if mst["status"] == "unavailable":
                    detail = f" (HTTP {mst.get('http_code', '?')}: {mst.get('error', '')[:60]})"
                print(f"    {ms_icon} {mid}{detail}")

    # 3. 写入或预览
    if args.dry_run:
        print("[3/3] --dry-run 模式,预览:")
        print(json.dumps(health, indent=2, ensure_ascii=False))
        return

    if not args.force:
        print("[3/3] 确认写入? (y/N): ", end="")
        if input().strip().lower() != "y":
            print("  已取消")
            return

    # 更新 usage.json 中的健康状态
    usage = {}
    if USAGE_FILE.exists():
        usage = json.loads(USAGE_FILE.read_text(encoding="utf-8"))

    for pid, h in health.items():
        if pid not in usage.get("providers", {}):
            usage.setdefault("providers", {})[pid] = {}
        usage["providers"][pid]["health"] = h

    usage["last_health_check"] = datetime.now(timezone.utc).isoformat()
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    USAGE_FILE.write_text(json.dumps(usage, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[3/3] ✅ 已更新 {USAGE_FILE}")
    print()
    print("=== 健康探测完成 ===")

    # 检查是否有 model ID 不可用。区分两类情况：
    # - 402/配额类错误（quota）: 预期内状态（provider 到期/欠费），警告但不触发失败
    # - 其他不可用: 真实异常，非零退出触发 cron failure alert
    unavailable_models = []
    quota_models = []
    for pid, h in health.items():
        for mid, mst in h.get("models", {}).items():
            if mst["status"] == "unavailable":
                if mst.get("http_code") == 402:
                    quota_models.append(f"{pid}/{mid}")
                else:
                    unavailable_models.append(f"{pid}/{mid}")
    if quota_models:
        print(f"\n⚠️  {len(quota_models)} 个 model ID 配额耗尽（预期内，不告警）:")
        for m in quota_models:
            print(f"  - {m}")
    if unavailable_models:
        print(f"\n⚠️  {len(unavailable_models)} 个 model ID 不可用:")
        for m in unavailable_models:
            print(f"  - {m}")
        sys.exit(1)


if __name__ == "__main__":
    main()
