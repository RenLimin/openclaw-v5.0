#!/usr/bin/env python3
"""模型注册表同步:从 openclaw.json 读取已有 provider/models,写入 config/models.yaml。

设计约束:
  - 只读访问 openclaw.json(通过 `openclaw config get`),绝不写入
  - 外部文件 config/models.yaml 是 model-scheduling 的主来源
  - 支持 --dry-run 预览,默认先 dry-run 再确认执行
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent  # model-scheduling/
CONFIG_DIR = REPO_ROOT / "config"
MODELS_FILE = CONFIG_DIR / "models.yaml"


def get_openclaw_config(path: str) -> dict:
    """只读获取 openclaw.json 的指定路径。"""
    result = subprocess.run(
        ["openclaw", "config", "get", path],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"  ⚠️  config get {path} 失败: {result.stderr.strip()[:100]}")
        return {}
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        print(f"  ⚠️  config get {path} 返回非 JSON: {result.stdout[:100]}")
        return {}


def fetch_all_models() -> list[dict]:
    """从 openclaw.json 提取所有 provider 和 model 信息。"""
    providers_config = get_openclaw_config("models")
    providers = providers_config.get("providers", {})

    models = []
    for provider_id, pconf in providers.items():
        base_url = pconf.get("baseUrl", "")
        api = pconf.get("api", "openai-completions")
        for m in pconf.get("models", []):
            models.append({
                "provider": provider_id,
                "id": m["id"],
                "name": m.get("name", m["id"]),
                "api": m.get("api", api),
                "base_url": base_url,
                "context_window": m.get("contextWindow", 0),
                "max_tokens": m.get("maxTokens", 0),
                "input_types": m.get("input", ["text"]),
                "reasoning": m.get("reasoning", False),
                "cost": m.get("cost", {"input": 0, "output": 0}),
                "status": "active",  # active / disabled / exhausted
                "tags": [],  # 用户自定义标签,如 "coding", "cheap", "fast"
            })
    return models


def generate_yaml(models: list[dict]) -> str:
    """生成 YAML 格式的手册(不用 PyYAML,手写以确保格式可控)。"""
    lines = [
        "# 模型注册表 — model-scheduling",
        "# 此文件由 sync_models.py 从 openclaw.json 自动同步,也可手动编辑",
        "# 修改此文件不会影响 openclaw.json(只用于 model-scheduling 路由决策)",
        "#",
        "# status: active | disabled | exhausted",
        "# tags: coding | reasoning | cheap | fast | image | embedding",
        "#",
        f"# 生成时间: {subprocess.run(['date', '+%Y-%m-%dT%H:%M:%S%z'], capture_output=True, text=True).stdout.strip()}",
        f"# 模型总数: {len(models)}",
        "",
        "models:",
    ]

    # 按 provider 分组
    by_provider: dict[str, list[dict]] = {}
    for m in models:
        by_provider.setdefault(m["provider"], []).append(m)

    for provider_id, pmodels in by_provider.items():
        lines.append(f"  # Provider: {provider_id}")
        for m in pmodels:
            lines.append(f'  - id: "{provider_id}/{m["id"]}"')
            lines.append(f'    provider: "{provider_id}"')
            lines.append(f'    model_id: "{m["id"]}"')
            lines.append(f'    name: "{m["name"]}"')
            lines.append(f'    context_window: {m["context_window"]}')
            lines.append(f'    max_tokens: {m["max_tokens"]}')
            lines.append(f'    input_types: {json.dumps(m["input_types"])}')
            lines.append(f'    reasoning: {str(m["reasoning"]).lower()}')
            lines.append(f'    cost_input: {m["cost"].get("input", 0)}')
            lines.append(f'    cost_output: {m["cost"].get("output", 0)}')
            lines.append(f'    status: "{m["status"]}"')
            lines.append(f'    tags: {json.dumps(m["tags"])}')
            lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="同步 openclaw.json 模型到 model-scheduling 注册表")
    parser.add_argument("--dry-run", action="store_true", help="预览但不写入")
    parser.add_argument("--force", action="store_true", help="跳过确认直接写入")
    args = parser.parse_args()

    print("=== 模型注册表同步 ===")
    print()

    # 1. 读取 openclaw.json(只读)
    print("[1/4] 读取 openclaw.json models.providers ...")
    models = fetch_all_models()
    print(f"  发现 {len(models)} 个模型")

    if not models:
        print("  ❌ 未发现任何模型,退出")
        sys.exit(1)

    # 2. 生成 YAML
    print("[2/4] 生成 YAML ...")
    yaml_content = generate_yaml(models)

    # 3. 检查现有文件(如有)
    if MODELS_FILE.exists():
        existing = MODELS_FILE.read_text(encoding="utf-8")
        if existing.strip() == yaml_content.strip():
            print("[3/4] ✅ 文件内容一致,无需更新")
            return
        print("[3/4] 文件已存在且内容不同,将更新")
    else:
        print("[3/4] 文件不存在,将创建")

    # 4. 写入或预览
    if args.dry_run:
        print("[4/4] --dry-run 模式,预览内容(前 30 行):")
        print("---")
        for line in yaml_content.splitlines()[:30]:
            print(f"  {line}")
        print("---")
        print(f"  完整内容: {len(yaml_content)} 字节")
        return

    if not args.force:
        print("[4/4] 确认写入? (y/N): ", end="")
        if input().strip().lower() != "y":
            print("  已取消")
            return

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    MODELS_FILE.write_text(yaml_content, encoding="utf-8")
    print(f"[4/4] ✅ 已写入 {MODELS_FILE}")
    print()
    print("=== 同步完成 ===")


if __name__ == "__main__":
    main()
