#!/usr/bin/env python3
"""注册 model-scheduling 为 OpenClaw custom provider。

功能：
  在 openclaw.json 的 models.providers 里注册 model-scheduling provider，
  baseUrl 指向本地 proxy (127.0.0.1:3000)，model 列表只放一个伪 model "auto"。

  注册后，session model 设为 model-scheduling/auto 时：
  Gateway → proxy(127.0.0.1:3000) → 智能路由 + 跨 vendor fallback → 真实 provider

分层设计（与 OpenClaw 解耦）：
  - proxy 是标准 OpenAI-compatible endpoint，不依赖 OpenClaw 特有 API
  - 换运行时只要支持 OpenAI-compatible custom provider，proxy 代码零修改
  - proxy 内部路由逻辑（任务分类/fallback/健康检查）完全自包含

用法：
  python3 register_provider.py              # 注册（dry-run + 确认）
  python3 register_provider.py --force      # 跳过确认
  python3 register_provider.py --unregister  # 移除注册
  python3 register_provider.py --dry-run     # 只看不动
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

PROVIDER_CONFIG = {
    "baseUrl": "http://127.0.0.1:3000",
    "api": "openai-completions",
    "models": [
        {
            "id": "auto",
            "name": "Auto (Smart Routing)",
            "api": "openai-completions",
            "reasoning": False,
            "input": ["text", "image", "video"],
            "cost": {
                "input": 0,
                "output": 0,
                "cacheRead": 0,
                "cacheWrite": 0,
            },
            "contextWindow": 229376,
            "maxTokens": 131072,
        }
    ],
}


def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"  ❌ 命令失败: {' '.join(cmd)}")
        print(f"     stderr: {result.stderr.strip()[:200]}")
    return result


def get_openclaw_config(path: str) -> dict:
    result = run(["openclaw", "config", "get", path], check=False)
    if result.returncode != 0:
        return {}
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {}


def set_openclaw_config(path: str, value: dict) -> bool:
    payload = json.dumps(value)
    result = run(["openclaw", "config", "set", path, payload], check=False)
    return result.returncode == 0


def check_proxy_health() -> bool:
    """检查 proxy 是否在跑"""
    try:
        import urllib.request
        req = urllib.request.Request("http://127.0.0.1:3000/health", method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            return data.get("status") == "ok"
    except Exception:
        return False


def register(force: bool = False, dry_run: bool = False):
    print("=== 注册 model-scheduling 为 OpenClaw custom provider ===\n")

    # 1. 检查 proxy 健康
    print("[1/4] 检查 proxy 健康状态...")
    if check_proxy_health():
        print("  ✅ proxy (127.0.0.1:3000) 运行中")
    else:
        print("  ❌ proxy (127.0.0.1:3000) 未运行!")
        print("  请先启动 proxy: python3 scripts/proxy.py --port 3000")
        sys.exit(1)

    # 2. 读取当前 models.providers
    print("\n[2/4] 读取当前 models.providers...")
    providers = get_openclaw_config("models.providers")
    print(f"  当前 providers: {list(providers.keys())}")

    if "model-scheduling" in providers:
        existing = providers["model-scheduling"]
        if existing.get("baseUrl") == PROVIDER_CONFIG["baseUrl"]:
            print("  ℹ️  model-scheduling 已注册，配置一致，无需修改")
            return
        else:
            print("  ⚠️  model-scheduling 已注册但配置不同，将更新")

    # 3. dry-run 预览
    print("\n[3/4] 预览变更:")
    print(f"  操作: 注册 model-scheduling provider")
    print(f"  baseUrl: {PROVIDER_CONFIG['baseUrl']}")
    print(f"  models: {[m['id'] for m in PROVIDER_CONFIG['models']]}")

    if dry_run:
        print("\n  [dry-run] 未执行实际变更")
        return

    if not force:
        print("\n  确认注册? (y/n): ", end="")
        try:
            answer = input().strip().lower()
        except (EOFError, KeyboardInterrupt):
            answer = "n"
        if answer != "y":
            print("  已取消")
            return

    # 4. 写入配置
    print("\n[4/4] 写入 openclaw.json...")
    new_providers = {**providers, "model-scheduling": PROVIDER_CONFIG}
    if set_openclaw_config("models.providers", new_providers):
        print("  ✅ 注册成功!")
        print("\n  下一步:")
        print("  1. 重启 Gateway: openclaw gateway restart")
        print("  2. 切换 model: /model model-scheduling/auto")
        print("  3. 验证: 发消息看 proxy 日志里的路由路径")
    else:
        print("  ❌ 注册失败!")
        sys.exit(1)


def unregister(force: bool = False):
    print("=== 移除 model-scheduling provider 注册 ===\n")

    providers = get_openclaw_config("models.providers")
    if "model-scheduling" not in providers:
        print("  ℹ️  model-scheduling 未注册，无需移除")
        return

    print(f"  当前 providers: {list(providers.keys())}")
    print(f"  将移除: model-scheduling")

    if not force:
        print("\n  确认移除? (y/n): ", end="")
        try:
            answer = input().strip().lower()
        except (EOFError, KeyboardInterrupt):
            answer = "n"
        if answer != "y":
            print("  已取消")
            return

    del providers["model-scheduling"]
    if set_openclaw_config("models.providers", providers):
        print("  ✅ 移除成功!")
    else:
        print("  ❌ 移除失败!")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="注册/移除 model-scheduling 为 OpenClaw custom provider"
    )
    parser.add_argument("--force", action="store_true", help="跳过确认")
    parser.add_argument("--dry-run", action="store_true", help="只看不动")
    parser.add_argument("--unregister", action="store_true", help="移除注册")
    args = parser.parse_args()

    if args.unregister:
        unregister(force=args.force)
    else:
        register(force=args.force, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
