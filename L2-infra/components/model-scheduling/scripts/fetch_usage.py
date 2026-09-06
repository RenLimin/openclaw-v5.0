#!/usr/bin/env python3
"""用量追踪:从 provider API 获取用量信息,写入 config/usage.json。

设计约束:
  - 只读访问 openclaw.json(获取 provider 配置)
  - 外部文件 config/usage.json 存储用量状态
  - 各 provider 用量 API 不同,需分别适配
  - 支持 --dry-run 预览
"""

import argparse
import json
import subprocess
import sys
import urllib.request
import urllib.error
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


def fetch_volcengine_usage(provider_conf: dict) -> dict:
    """获取火山方舟用量。

    火山方舟用量 API:
    POST https://ark.cn-beijing.volces.com/api/coding/v3/dashboard/billing/overview
    """
    api_key = provider_conf.get("apiKey", "")
    base_url = provider_conf.get("baseUrl", "https://ark.cn-beijing.volces.com/api/coding/v3")

    # 尝试调用用量 API
    try:
        req = urllib.request.Request(
            f"{base_url}/dashboard/billing/overview",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="GET",
            data=None,
        )
        # 注意: 火山可能没有公开的用量 API,这里做容错处理
        # 实际使用时需根据火山文档调整
        return {
            "provider": "coding-plan",
            "status": "unknown",
            "note": "火山方舟用量 API 需根据官方文档配置",
            "last_checked": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        return {
            "provider": "coding-plan",
            "status": "error",
            "error": str(e)[:200],
            "last_checked": datetime.now(timezone.utc).isoformat(),
        }


def fetch_openai_usage(provider_conf: dict) -> dict:
    """获取 OpenAI 用量(预留)。"""
    return {
        "provider": "openai",
        "status": "not_implemented",
        "note": "OpenAI 用量 API 待实现",
    }


def fetch_usage_for_provider(provider_id: str, provider_conf: dict) -> dict:
    """根据 provider ID 分发到对应的用量获取函数。"""
    fetchers = {
        "coding-plan": fetch_volcengine_usage,
        "openai": fetch_openai_usage,
    }
    fetcher = fetchers.get(provider_id)
    if fetcher:
        return fetcher(provider_conf)
    return {
        "provider": provider_id,
        "status": "unsupported",
        "note": f"Provider {provider_id} 暂不支持用量获取",
    }


def main():
    parser = argparse.ArgumentParser(description="获取 provider 用量信息")
    parser.add_argument("--dry-run", action="store_true", help="预览但不写入")
    parser.add_argument("--force", action="store_true", help="跳过确认")
    args = parser.parse_args()

    print("=== 用量信息获取 ===")
    print()

    # 1. 读取 openclaw.json providers(只读)
    print("[1/3] 读取 openclaw.json models.providers ...")
    providers_config = get_openclaw_config("models")
    providers = providers_config.get("providers", {})
    print(f"  发现 {len(providers)} 个 provider: {', '.join(providers.keys())}")

    # 2. 逐个获取用量
    print("[2/3] 获取用量信息 ...")
    usage = {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "providers": {},
    }
    for pid, pconf in providers.items():
        print(f"  [{pid}] 获取中...")
        result = fetch_usage_for_provider(pid, pconf)
        usage["providers"][pid] = result
        print(f"  [{pid}] → {result['status']}")

    # 3. 写入或预览
    if args.dry_run:
        print("[3/3] --dry-run 模式,预览:")
        print(json.dumps(usage, indent=2, ensure_ascii=False))
        return

    if not args.force:
        print("[3/3] 确认写入? (y/N): ", end="")
        if input().strip().lower() != "y":
            print("  已取消")
            return

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    USAGE_FILE.write_text(json.dumps(usage, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[3/3] ✅ 已写入 {USAGE_FILE}")
    print()
    print("=== 用量获取完成 ===")


if __name__ == "__main__":
    main()
