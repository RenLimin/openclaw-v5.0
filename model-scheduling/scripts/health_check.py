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
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = REPO_ROOT / "config"
USAGE_FILE = CONFIG_DIR / "usage.json"


def get_openclaw_config(path: str) -> dict:
    """只读获取 openclaw.json。"""
    result = subprocess.run(
        ["openclaw", "config", "get", path],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        return {}
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {}


def _resolve_api_key(provider_conf: dict) -> str:
    """解析 apiKey，支持 SecretRef(file source)。"""
    api_key = provider_conf.get("apiKey", "")
    if isinstance(api_key, dict) and api_key.get("source") == "file":
        # SecretRef file source: 从 ~/.openclaw/secrets/ 读取
        provider = api_key.get("provider", "")
        # 尝试多种文件名拼法
        secrets_dir = Path.home() / ".openclaw" / "secrets"
        for fname in [f"{provider}", f"{provider}.apiKey", f"{provider.replace('key', '')}.apiKey"]:
            fpath = secrets_dir / fname
            if fpath.exists():
                return fpath.read_text().strip()
        return ""  # 找不到文件
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
            return {
                "status": "healthy",
                "latency_ms": latency_ms,
                "last_checked": datetime.now(timezone.utc).isoformat(),
            }
        else:
            return {
                "status": "degraded",
                "latency_ms": latency_ms,
                "http_code": status_code,
                "last_checked": datetime.now(timezone.utc).isoformat(),
            }
    except urllib.error.HTTPError as e:
        latency_ms = int((time.monotonic() - start) * 1000)
        return {
            "status": "error",
            "latency_ms": latency_ms,
            "http_code": e.code,
            "error": str(e)[:100],
            "last_checked": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        latency_ms = int((time.monotonic() - start) * 1000)
        return {
            "status": "unreachable",
            "latency_ms": latency_ms,
            "error": str(e)[:100],
            "last_checked": datetime.now(timezone.utc).isoformat(),
        }


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

    # 2. 逐个探测
    print("[2/3] 探测 provider 健康状态 ...")
    health = {}
    for pid, pconf in providers.items():
        result = ping_provider(pid, pconf)
        health[pid] = result
        status_icon = {"healthy": "✅", "degraded": "⚠️", "error": "❌", "unreachable": "❌"}.get(result["status"], "?")
        print(f"  [{pid}] {status_icon} {result['status']} ({result['latency_ms']}ms)")

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


if __name__ == "__main__":
    main()
