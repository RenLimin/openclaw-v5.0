#!/usr/bin/env python3
"""模型发现 — 从火山 Coding Plan API 拉取最新模型列表,与 openclaw.json 对比差异。

功能:
  1. 从火山 API 获取最新模型列表(需要 API Key)
  2. 从 openclaw.json 读取当前已注册的 coding-plan 模型
  3. 对比差异,按类别分组输出报告
  4. 不自动修改任何配置文件

用法:
  python3 discover_models.py           # 输出人类可读报告
  python3 discover_models.py --json    # 输出结构化 JSON
  python3 discover_models.py --include-retiring  # 包含 Retiring 状态模型
"""

import argparse
import json
import os
import subprocess
import sys
import urllib.request
import urllib.error
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent  # model-scheduling/
CONFIG_DIR = REPO_ROOT / "config"

VOLCANO_API_URL = "https://ark.cn-beijing.volces.com/api/coding/v3/models"
REQUEST_TIMEOUT = 15  # 秒

# ─── 模型类别规则 ───
# 按模型 ID 中的关键词分类
CATEGORY_RULES = [
    ("embedding", ["embedding"]),
    ("vision", ["vision", "seedream", "seedance", "image", "gen2", "hitem3d", "seed3d", "hyper3d"]),
    ("video", ["seedance", "i2v", "t2v", "video"]),
    ("chat", ["doubao", "deepseek", "glm", "qwen", "mistral", "llama", "gpt", "claude", "gemini", "longcat", "router", "character", "translation", "evolving", "smart-router"]),
]

def classify_model(model_id: str) -> str:
    """根据模型 ID 分类。"""
    lower = model_id.lower()
    # embedding 优先级最高(因为有些 embedding 模型也包含 "doubao")
    for category, keywords in CATEGORY_RULES:
        for kw in keywords:
            if kw in lower:
                return category
    return "other"


def get_api_key() -> str:
    """从 auth-profiles.json 或环境变量获取 API Key。"""
    # 1. 环境变量
    for env_key in ["ARK_API_KEY", "VOLCENGINE_API_KEY", "CODING_PLAN_API_KEY"]:
        val = os.environ.get(env_key, "")
        if val:
            return val

    # 2. auth-profiles.json
    auth_file = Path.home() / ".openclaw" / "auth-profiles.json"
    if auth_file.exists():
        try:
            auth_data = json.loads(auth_file.read_text())
            for pid, pconf in auth_data.get("profiles", {}).items():
                if "coding" in pid.lower() or "ark" in pid.lower():
                    key = pconf.get("apiKey", "")
                    if key:
                        return key
        except Exception:
            pass

    # 3. .zshenv
    zshenv = Path.home() / ".zshenv"
    if zshenv.exists():
        for line in zshenv.read_text().splitlines():
            line = line.strip()
            if line.startswith("export ") and "=" in line:
                _, _, kv = line.partition("export ")
                key, _, val = kv.partition("=")
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key and val and key not in os.environ:
                    os.environ[key] = val
        for env_key in ["ARK_API_KEY", "VOLCENGINE_API_KEY", "CODING_PLAN_API_KEY"]:
            val = os.environ.get(env_key, "")
            if val:
                return val

    return ""


def fetch_volcano_models(api_key: str, include_retiring: bool = False) -> list[dict]:
    """从火山 API 获取模型列表。"""
    req = urllib.request.Request(
        VOLCANO_API_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="GET",
    )

    try:
        response = urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT)
        data = json.loads(response.read())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"火山 API HTTP {e.code}: {error_body[:300]}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"火山 API 网络错误: {e.reason}")
    except TimeoutError:
        raise RuntimeError(f"火山 API 超时 ({REQUEST_TIMEOUT}s)")

    if "error" in data:
        raise RuntimeError(f"火山 API 错误: {data['error']}")

    models = data.get("data", [])
    if not models:
        raise RuntimeError("火山 API 返回空模型列表")

    # 过滤:默认排除 Shutdown 和 Retiring
    if not include_retiring:
        models = [m for m in models if m.get("status", "") not in ("Shutdown", "Retiring")]

    return models


def get_openclaw_models() -> list[dict]:
    """从 openclaw.json 读取 coding-plan provider 的模型列表。"""
    result = subprocess.run(
        ["openclaw", "config", "get", "models"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"  ⚠️  openclaw config get 失败: {result.stderr.strip()[:100]}")
        return []

    try:
        config = json.loads(result.stdout)
    except json.JSONDecodeError:
        print(f"  ⚠️  openclaw config 返回非 JSON")
        return []

    providers = config.get("providers", {})
    coding_plan = providers.get("coding-plan", {})
    return coding_plan.get("models", [])


def build_report(
    volcano_models: list[dict],
    openclaw_models: list[dict],
) -> dict:
    """对比差异,生成结构化报告。"""
    # 提取 ID 集合
    volcano_ids = {m["id"] for m in volcano_models}
    openclaw_ids = {m["id"] for m in openclaw_models}

    new_ids = volcano_ids - openclaw_ids
    removed_ids = openclaw_ids - volcano_ids
    unchanged_ids = volcano_ids & openclaw_ids

    # 构建详细信息
    volcano_map = {m["id"]: m for m in volcano_models}
    openclaw_map = {m["id"]: m for m in openclaw_models}

    def model_info(model_id: str, source: str = "api") -> dict:
        if source == "api":
            m = volcano_map.get(model_id, {})
        else:
            m = openclaw_map.get(model_id, {})
        return {
            "id": model_id,
            "name": m.get("name", model_id),
            "status": m.get("status", "unknown"),
            "category": classify_model(model_id),
        }

    # 按类别分组
    new_by_cat: dict[str, list[dict]] = {}
    for mid in sorted(new_ids):
        info = model_info(mid, "api")
        new_by_cat.setdefault(info["category"], []).append(info)

    removed_by_cat: dict[str, list[dict]] = {}
    for mid in sorted(removed_ids):
        info = model_info(mid, "openclaw")
        removed_by_cat.setdefault(info["category"], []).append(info)

    unchanged_by_cat: dict[str, list[dict]] = {}
    for mid in sorted(unchanged_ids):
        info = model_info(mid, "api")
        unchanged_by_cat.setdefault(info["category"], []).append(info)

    return {
        "summary": {
            "volcano_total": len(volcano_ids),
            "openclaw_total": len(openclaw_ids),
            "new_count": len(new_ids),
            "removed_count": len(removed_ids),
            "unchanged_count": len(unchanged_ids),
        },
        "new_models": {
            "total": len(new_ids),
            "by_category": new_by_cat,
        },
        "removed_models": {
            "total": len(removed_ids),
            "by_category": removed_by_cat,
        },
        "unchanged_models": {
            "total": len(unchanged_ids),
            "by_category": unchanged_by_cat,
        },
    }


def print_report(report: dict):
    """输出人类可读报告。"""
    summary = report["summary"]
    print("=" * 60)
    print("  火山 Coding Plan — 模型发现报告")
    print("=" * 60)
    print()
    print(f"  火山 API 模型数:  {summary['volcano_total']}")
    print(f"  openclaw.json:   {summary['openclaw_total']}")
    print()

    # 新增模型
    new = report["new_models"]
    print(f"🆕 新增模型 ({new['total']})")
    print("-" * 40)
    if new["total"] == 0:
        print("  (无)")
    for cat, models in sorted(new["by_category"].items()):
        print(f"  [{cat}]")
        for m in models:
            print(f"    + {m['id']:50s} {m['name']}")
    print()

    # 下架模型
    removed = report["removed_models"]
    print(f"❌ 下架模型 ({removed['total']})")
    print("-" * 40)
    if removed["total"] == 0:
        print("  (无)")
    for cat, models in sorted(removed["by_category"].items()):
        print(f"  [{cat}]")
        for m in models:
            print(f"    - {m['id']:50s} {m['name']}")
    print()

    # 未变化
    unchanged = report["unchanged_models"]
    print(f"✅ 未变化 ({unchanged['total']})")
    print("-" * 40)
    for cat, models in sorted(unchanged["by_category"].items()):
        print(f"  [{cat}] {len(models)} 个")
        for m in models:
            print(f"    = {m['id']}")
    print()
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="模型发现 — 对比火山 API 与 openclaw.json 差异")
    parser.add_argument("--json", action="store_true", help="输出结构化 JSON")
    parser.add_argument("--include-retiring", action="store_true", help="包含 Retiring 状态模型")
    args = parser.parse_args()

    print("=== 模型发现 ===")
    print()

    # 1. 获取 API Key
    print("[1/3] 获取 API Key ...")
    api_key = get_api_key()
    if not api_key:
        print("  ❌ 无法获取 API Key (检查 auth-profiles.json 或环境变量 ARK_API_KEY)")
        sys.exit(1)
    print(f"  ✅ API Key: {api_key[:8]}...")

    # 2. 拉取火山 API 模型
    print(f"[2/3] 从火山 API 获取模型列表 ...")
    try:
        volcano_models = fetch_volcano_models(api_key, include_retiring=args.include_retiring)
    except RuntimeError as e:
        print(f"  ❌ {e}")
        sys.exit(1)
    print(f"  ✅ 获取到 {len(volcano_models)} 个模型" +
          (" (含 Retiring)" if args.include_retiring else ""))

    # 3. 读取 openclaw.json
    print("[3/3] 读取 openclaw.json ...")
    openclaw_models = get_openclaw_models()
    print(f"  ✅ openclaw.json 有 {len(openclaw_models)} 个 coding-plan 模型")

    # 4. 对比生成报告
    report = build_report(volcano_models, openclaw_models)

    print()

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_report(report)

    # 有新增或下架时返回 1(供 cron 判断是否需要通知)
    if report["summary"]["new_count"] > 0 or report["summary"]["removed_count"] > 0:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
