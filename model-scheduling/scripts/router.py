#!/usr/bin/env python3
"""智能路由引擎:根据任务类型、用量、健康状态选择最优模型。

设计约束:
  - 只读访问 openclaw.json
  - 读 config/models.yaml + config/routing.yaml + config/usage.json
  - 输出推荐模型,不直接切换(切换由 cron 或 sessions.patch 执行)
  - 支持 --dry-run 预览路由决策
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = REPO_ROOT / "config"
MODELS_FILE = CONFIG_DIR / "models.yaml"
ROUTING_FILE = CONFIG_DIR / "routing.yaml"
USAGE_FILE = CONFIG_DIR / "usage.json"


def load_yaml_simple(path: Path) -> dict:
    """简易 YAML 解析(仅支持本项目的扁平结构,不用 PyYAML)。"""
    if not path.exists():
        return {}
    content = path.read_text(encoding="utf-8")
    # 用 json5 兼容格式: 将 YAML 的 key: value 转为 JSON
    # 这里用 python 的 yaml 如果可用,否则用简易解析
    try:
        import yaml
        return yaml.safe_load(content) or {}
    except ImportError:
        pass
    # 简易解析: 只提取 models 列表
    result = {"models": [], "task_routing": {}, "compress_rules": {}}
    current_model = None
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("#") or not line:
            continue
        if line == "models:":
            continue
        if line.startswith("- id:"):
            if current_model:
                result["models"].append(current_model)
            current_model = {"id": line.split('"')[1]}
        elif current_model and ":" in line:
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip().strip('"')
            try:
                current_model[key] = json.loads(val)
            except (json.JSONDecodeError, ValueError):
                current_model[key] = val
    if current_model:
        result["models"].append(current_model)
    return result


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


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


def classify_task(message: str) -> str:
    """简单任务分类(基于关键词)。

    未来可升级为 LLM 分类(调小模型做分类,成本极低)。
    """
    message_lower = message.lower()

    # 编码任务关键词
    coding_keywords = [
        "代码", "code", "函数", "function", "类", "class", "debug", "调试",
        "重构", "refactor", "修复", "fix", "bug", "编程", "programming",
        "git", "commit", "pull request", "pr ", "review", "审查",
        "python", "javascript", "typescript", "java", "go ", "rust",
        "sql", "api", "接口", "测试", "test", "部署", "deploy",
    ]
    for kw in coding_keywords:
        if kw in message_lower:
            return "coding"

    # 研究任务关键词
    research_keywords = [
        "搜索", "search", "研究", "research", "分析", "analyze",
        "比较", "compare", "总结", "summarize", "文档", "document",
        "网络", "web", "最新", "latest", "新闻", "news",
    ]
    for kw in research_keywords:
        if kw in message_lower:
            return "research"

    # 推理任务关键词
    reasoning_keywords = [
        "推理", "reasoning", "架构", "architecture", "设计", "design",
        "方案", "solution", "策略", "strategy", "决策", "decision",
        "深度", "deep", "复杂", "complex", "评估", "evaluate",
    ]
    for kw in reasoning_keywords:
        if kw in message_lower:
            return "reasoning"

    return "chat"


def select_model(task_type: str, models: list[dict], routing: dict, usage: dict) -> dict:
    """根据任务类型选择最优模型。"""
    task_routing = routing.get("task_routing", {})
    config = task_routing.get(task_type, task_routing.get("chat", {}))
    fallback_chain = config.get("fallback_chain", [])

    if not fallback_chain:
        # 没有配置 fallback chain,返回第一个 active 模型
        for m in models:
            if m.get("status") == "active":
                return m
        return models[0] if models else None

    # 按 fallback chain 顺序,选择第一个 active 且未耗尽的模型
    provider_usage = usage.get("providers", {})
    for model_ref in fallback_chain:
        # 在 models 中查找
        model = None
        for m in models:
            if m.get("id") == model_ref:
                model = m
                break
        if not model:
            continue
        if model.get("status") != "active":
            continue

        # 检查用量(如果 provider 已耗尽,跳过)
        provider = model.get("provider", "")
        pu = provider_usage.get(provider, {})
        if pu.get("status") == "exhausted":
            continue

        return model

    # 所有 fallback 都不可用,返回第一个 active
    for m in models:
        if m.get("status") == "active":
            return m
    return None


def select_compaction_model(main_model_id: str, models: list[dict], routing: dict, usage: dict) -> dict:
    """根据当前主会话模型选择最优压缩模型。
    
    策略: 同 provider → 最大上下文窗口 → fallback chain
    """
    compaction_routing = routing.get("compaction_routing", {})
    strategy = compaction_routing.get("strategy", "same_provider_largest_ctx")
    fallback_chain = compaction_routing.get("fallback_chain", [])
    
    # 找到主模型信息
    main_model = None
    for m in models:
        if m.get("id") == main_model_id:
            main_model = m
            break
    
    provider_usage = usage.get("providers", {})
    selected = None
    
    if strategy == "same_provider_largest_ctx" and main_model:
        main_provider = main_model.get("provider")
        # 收集同 provider 所有 active 且未耗尽的模型
        candidates = []
        for m in models:
            if m.get("provider") != main_provider:
                continue
            if m.get("status") != "active":
                continue
            provider = m.get("provider", "")
            pu = provider_usage.get(provider, {})
            if pu.get("status") == "exhausted":
                continue
            candidates.append(m)
        
        if candidates:
            # 按上下文窗口降序排序,选最大的
            candidates.sort(key=lambda x: x.get("context_window", 0), reverse=True)
            selected = candidates[0]
    
    # 如果同 provider 没找到,走全局 fallback chain
    if not selected and fallback_chain:
        for model_ref in fallback_chain:
            model = None
            for m in models:
                if m.get("id") == model_ref:
                    model = m
                    break
            if not model:
                continue
            if model.get("status") != "active":
                continue
            provider = model.get("provider", "")
            pu = provider_usage.get(provider, {})
            if pu.get("status") == "exhausted":
                continue
            selected = model
            break
    
    # 如果还是没找到,返回第一个 active 模型
    if not selected:
        for m in models:
            if m.get("status") == "active":
                selected = m
                break
    
    return selected


def main():
    parser = argparse.ArgumentParser(description="智能路由引擎")
    parser.add_argument("message", nargs="?", help="任务消息(用于分类)")
    parser.add_argument("--task-type", choices=["coding", "reasoning", "research", "chat", "embedding"],
                        help="直接指定任务类型(跳过自动分类)")
    parser.add_argument("--compaction-for", help="为指定主模型选择压缩模型")
    parser.add_argument("--dry-run", action="store_true", help="预览路由决策")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    args = parser.parse_args()

    print("=== 智能路由引擎 ===")
    print()

    # 1. 加载配置
    print("[1/3] 加载配置 ...")
    models = load_yaml_simple(MODELS_FILE).get("models", [])
    routing = load_yaml_simple(ROUTING_FILE)
    usage = load_json(USAGE_FILE)
    print(f"  模型: {len(models)} 个")
    print(f"  Provider 用量: {len(usage.get('providers', {}))} 个")

    # 2. 任务分类
    print("[2/3] 任务分类 ...")
    if args.task_type:
        task_type = args.task_type
    elif args.message:
        task_type = classify_task(args.message)
    else:
        task_type = "chat"
    print(f"  任务类型: {task_type}")

    # 3. 选择模型
    print("[3/3] 选择模型 ...")
    
    if args.compaction_for:
        # 为指定主模型选择压缩模型
        selected = select_compaction_model(args.compaction_for, models, routing, usage)
        if not selected:
            print("  ❌ 无可用压缩模型!")
            sys.exit(1)
        
        result = {
            "main_model": args.compaction_for,
            "selected_compaction_model": selected.get("id"),
            "provider": selected.get("provider"),
            "context_window": selected.get("context_window"),
            "reason": f"主模型 {args.compaction_for} → same provider → largest ctx → fallback",
        }
        
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(f"  主模型: {result['main_model']}")
            print(f"  推荐压缩模型: {result['selected_compaction_model']}")
            print(f"  Provider: {result['provider']}")
            print(f"  上下文窗口: {result['context_window']}")
            print(f"  原因: {result['reason']}")
    else:
        # 常规任务路由
        selected = select_model(task_type, models, routing, usage)
        if not selected:
            print("  ❌ 无可用模型!")
            sys.exit(1)
        
        result = {
            "task_type": task_type,
            "selected_model": selected.get("id"),
            "provider": selected.get("provider"),
            "context_window": selected.get("context_window"),
            "reason": f"任务类型 {task_type} → fallback chain 第 1 个可用模型",
        }
        
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(f"  推荐模型: {result['selected_model']}")
            print(f"  Provider: {result['provider']}")
            print(f"  上下文窗口: {result['context_window']}")
            print(f"  原因: {result['reason']}")

    print()
    print("=== 路由完成 ===")


if __name__ == "__main__":
    main()
