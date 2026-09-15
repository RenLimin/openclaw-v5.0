#!/usr/bin/env python3
"""模型注册表同步:从 openclaw.json 读取已有 provider/models,写入 config/models.yaml。

设计约束:
  - 只读访问 openclaw.json(通过 `openclaw config get`),绝不写入
  - 外部文件 config/models.yaml 是 model-scheduling 的主来源
  - 支持 --dry-run 预览,默认先 dry-run 再确认执行
"""

import argparse
import re
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


def parse_yaml_ids(yaml_text: str) -> set[str]:
    """Naive YAML parser to extract all 'id: "..."' values (model IDs)."""
    ids = set()
    for line in yaml_text.splitlines():
        line = line.strip()
        if line.startswith("- id:"):
            # Extract quoted value
            m = re.match(r'- id:\s+"([^"]+)"', line)
            if m:
                ids.add(m.group(1))
    return ids


def extract_routing_model_ids(yaml_text: str) -> set[str]:
    """Extract all model IDs from fallback_chain entries in routing.yaml."""
    ids = set()
    in_fallback = False
    for line in yaml_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("fallback_chain:"):
            in_fallback = True
            continue
        if in_fallback:
            # fallback_chain entries start with "- " followed by quoted model ID
            if stripped.startswith("- \""):
                m = re.match(r'- "([^"]+)"', stripped)
                if m:
                    ids.add(m.group(1))
            elif stripped and not stripped.startswith("-") and not stripped.startswith("#"):
                # We've left the fallback_chain block
                in_fallback = False
            elif stripped == "":
                continue  # blank lines within block are OK
    return ids


def check_reference_integrity(models_file: Path, routing_file: Path, providers: dict) -> int:
    """Check that all models referenced in routing.yaml exist in models.yaml.

    Returns:
        0 if all references are valid
        1 if there are missing references (WARNING or ERROR)
    """
    print("[校验] 引用完整性检查 ...")

    if not routing_file.exists():
        print(f"  ⚠️  routing.yaml 不存在: {routing_file}")
        return 0  # nothing to check

    routing_text = routing_file.read_text(encoding="utf-8")
    routing_ids = extract_routing_model_ids(routing_text)

    if not models_file.exists():
        print(f"  ❌ models.yaml 不存在: {models_file}")
        return 1

    models_text = models_file.read_text(encoding="utf-8")
    model_ids = parse_yaml_ids(models_text)

    # Also include provider/model_id format from models.yaml
    # model_ids already has "provider/model_id" format from id field

    missing = routing_ids - model_ids

    if not missing:
        print(f"  ✅ 引用完整性检查通过 ({len(routing_ids)} 个引用全部有效)")
        return 0

    # Build set of known providers from openclaw.json
    known_providers = set(providers.keys())

    has_error = False
    warnings = []
    errors = []

    for mid in sorted(missing):
        provider = mid.split("/")[0] if "/" in mid else ""
        if provider in known_providers:
            # Provider exists in openclaw.json but model not in models.yaml
            # This means sync didn't pick it up — likely a real issue
            errors.append(mid)
            has_error = True
        else:
            # Provider not in openclaw.json at all — dead reference
            errors.append(mid)
            has_error = True

    for w in warnings:
        print(f"  ⚠️  WARNING: routing.yaml 引用但 models.yaml 中缺失: {w}")

    for e in errors:
        print(f"  ❌ ERROR: 死引用 — routing.yaml 引用但 models.yaml 和 openclaw.json 中均不存在: {e}")

    print()
    print(f"  汇总: {len(routing_ids)} 个引用, {len(model_ids)} 个已注册, {len(missing)} 个缺失")
    print(f"  结果: {'ERROR' if has_error else 'WARNING'}")

    return 1 if has_error else 0  # always return non-zero for any missing



def main():
    parser = argparse.ArgumentParser(description="同步 openclaw.json 模型到 model-scheduling 注册表")
    parser.add_argument("--dry-run", action="store_true", help="预览但不写入")
    parser.add_argument("--force", action="store_true", help="跳过确认直接写入")
    args = parser.parse_args()

    print("=== 模型注册表同步 ===")
    print()

    # 1. 读取 openclaw.json(只读)
    print("[1/4] 读取 openclaw.json models.providers ...")
    providers_config = get_openclaw_config("models").get("providers", {})
    models = fetch_all_models()
    print(f"  发现 {len(models)} 个模型")

    if not models:
        print("  ❌ 未发现任何模型,退出")
        sys.exit(1)

    # 2. 生成 YAML
    print("[2/4] 生成 YAML ...")
    yaml_content = generate_yaml(models)

    # 3. 检查现有文件(如有)——忽略生成时间行,只比较模型数据
    def _strip_timestamp(content: str) -> str:
        """移除生成时间行,用于判断模型数据是否真的变化了。"""
        return "\n".join(
            line for line in content.splitlines()
            if not line.startswith("# 生成时间:")
        ).strip()

    skip_write = False
    if MODELS_FILE.exists():
        existing = MODELS_FILE.read_text(encoding="utf-8")
        if _strip_timestamp(existing) == _strip_timestamp(yaml_content):
            print("[3/4] ✅ 模型数据未变化,跳过写入")
            skip_write = True
        else:
            print("[3/4] 模型数据有变化,将更新")
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
        # 继续执行引用完整性校验(只读)

    elif not skip_write:
        if not args.force:
            print("[4/4] 确认写入? (y/N): ", end="")
            if input().strip().lower() != "y":
                print("  已取消")
                return

        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        MODELS_FILE.write_text(yaml_content, encoding="utf-8")
        print(f"[4/4] ✅ 已写入 {MODELS_FILE}")

    # 引用完整性校验(始终执行)
    ROUTING_FILE = CONFIG_DIR / "routing.yaml"
    integrity_rc = check_reference_integrity(MODELS_FILE, ROUTING_FILE, providers_config)
    if integrity_rc != 0:
        print()
        print("=== 同步完成 (引用完整性问题) ===")
        sys.exit(integrity_rc)

    print()
    print("=== 同步完成 ===")


if __name__ == "__main__":
    main()
