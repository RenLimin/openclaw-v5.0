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


def fetch_all_models(providers_config: dict) -> list[dict]:
    """从 openclaw.json 提取所有 provider 和 model 信息。"""
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


# ─── 引用完整性校验 ───
def check_referential_integrity(models_yaml: str) -> tuple[list[str], list[str]]:
    """校验 routing.yaml 的 fallback_chain 引用的模型在 models.yaml 中是否存在。
    
    返回: (warnings, errors)
      - warnings: routing.yaml 引用但 models.yaml 缺失(可能运行时动态解析)
      - errors: routing.yaml 引用但 models.yaml 和 openclaw.json providers 都缺失
    """
    warnings = []
    errors = []

    # 1. 从生成的 YAML 提取模型 ID 集合
    model_ids_in_yaml = set()
    for line in models_yaml.splitlines():
        line = line.strip()
        if line.startswith("- id:"):
            # 格式: - id: "provider/model_id"
            model_id = line.split(":", 1)[1].strip().strip('"').strip("'")
            model_ids_in_yaml.add(model_id)

    # 2. 读取 routing.yaml
    routing_file = CONFIG_DIR / "routing.yaml"
    if not routing_file.exists():
        warnings.append(f"routing.yaml 不存在 ({routing_file}),跳过引用完整性校验")
        return warnings, errors

    routing_content = routing_file.read_text(encoding="utf-8")
    # 手写解析:提取 fallback_chain 列表中的模型 ID
    referenced_ids = set()
    in_fallback_chain = False
    for line in routing_content.splitlines():
        stripped = line.strip()
        if "fallback_chain:" in stripped:
            in_fallback_chain = True
            continue
        if in_fallback_chain:
            if stripped.startswith("- "):
                # 提取引号中的模型 ID
                ref = stripped[2:].split("#")[0].strip().strip('"').strip("'")
                if ref:
                    referenced_ids.add(ref)
            elif stripped and not stripped.startswith("#"):
                # 遇到非列表项,退出 fallback_chain 模式
                in_fallback_chain = False

    # 3. 对比
    missing_in_yaml = referenced_ids - model_ids_in_yaml
    for model_id in sorted(missing_in_yaml):
        warnings.append(
            f"routing.yaml 引用 '{model_id}' 但 models.yaml 中不存在"
        )
        # 4. 检查 openclaw.json providers 是否也没有
        providers_config_str = subprocess.run(
            ["openclaw", "config", "get", "models.providers"],
            capture_output=True, text=True
        ).stdout
        try:
            providers_config = json.loads(providers_config_str)
            found_in_provider = False
            for _pid, pconf in providers_config.items():
                for m in pconf.get("models", []):
                    full_id = f"{_pid}/{m['id']}"
                    if full_id == model_id:
                        found_in_provider = True
                        break
                if found_in_provider:
                    break
            if not found_in_provider:
                errors.append(
                    f"'{model_id}' 在 models.yaml 和 openclaw.json providers 中都不存在"
                )
        except json.JSONDecodeError:
            warnings.append(f"无法解析 openclaw.json providers,跳过 {model_id} 的深度检查")

    return warnings, errors


def main():
    parser = argparse.ArgumentParser(description="同步 openclaw.json 模型到 model-scheduling 注册表")
    parser.add_argument("--dry-run", action="store_true", help="预览但不写入")
    parser.add_argument("--force", action="store_true", help="跳过确认直接写入")
    args = parser.parse_args()

    print("=== 模型注册表同步 ===")
    print()

    # 1. 读取 openclaw.json(只读)
    print("[1/4] 读取 openclaw.json models.providers ...")
    providers_config = get_openclaw_config("models")
    models = fetch_all_models(providers_config)
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

    if MODELS_FILE.exists():
        existing = MODELS_FILE.read_text(encoding="utf-8")
        if _strip_timestamp(existing) == _strip_timestamp(yaml_content):
            print("[3/4] ✅ 模型数据未变化,跳过写入")
            return
        print("[3/4] 模型数据有变化,将更新")
    else:
        print("[3/4] 文件不存在,将创建")

    # 4. 引用完整性校验(写入前)
    print("[4/4] 引用完整性校验 ...")
    ref_warnings, ref_errors = check_referential_integrity(yaml_content)
    for w in ref_warnings:
        print(f"  ⚠️  WARNING: {w}")
    for e in ref_errors:
        print(f"  ❌ ERROR: {e}")
    if ref_errors:
        print()
        print("  ❌ 引用完整性校验失败,存在无法解析的模型引用")
        print("  请修复 routing.yaml 或 openclaw.json 后再同步")
        sys.exit(2)
    if ref_warnings:
        print("  ⚠️  存在警告级别的引用缺失(可能运行时动态解析,不阻断)")
    if not ref_warnings and not ref_errors:
        print("  ✅ 引用完整性校验通过")

    # 5. 写入或预览
    if args.dry_run:
        print("[5/5] --dry-run 模式,预览内容(前 30 行):")
        print("---")
        for line in yaml_content.splitlines()[:30]:
            print(f"  {line}")
        print("---")
        print(f"  完整内容: {len(yaml_content)} 字节")
        return

    if not args.force:
        print("[5/5] 确认写入? (y/N): ", end="")
        if input().strip().lower() != "y":
            print("  已取消")
            return

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    MODELS_FILE.write_text(yaml_content, encoding="utf-8")
    print(f"[5/5] ✅ 已写入 {MODELS_FILE}")
    print()
    print("=== 同步完成 ===")


if __name__ == "__main__":
    main()
