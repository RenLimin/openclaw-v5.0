#!/usr/bin/env python3
"""
check_quota_and_restore.py — 检查 deepseek 额度是否恢复，恢复则放回 fallback chain

逻辑：
1. 读取 models.yaml，找出 status=exhausted 的 deepseek 模型
2. 对每个 exhausted 模型发最小推理请求（max_tokens=1）
3. 如果成功（200），标记为 active 并加回 fallback chain
4. 如果仍 402，保持 exhausted，等下次检查
5. 更新 routing.yaml 和 models.yaml

用法：python3 check_quota_and_restore.py [--dry-run]
"""

import sys
import os
import json
import yaml
import argparse
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

# 路径配置
BASE_DIR = Path(__file__).resolve().parent.parent
MODELS_YAML = BASE_DIR / "config" / "models.yaml"
ROUTING_YAML = BASE_DIR / "config" / "routing.yaml"
PROXY_URL = "http://127.0.0.1:3000/v1/chat/completions"

# deepseek 模型在 fallback chain 中的位置定义
# ⚠️ 注意: longCat 的 key 是 SecretRef，proxy 读不到，所以不放回 fallback chain
# longCat 仅通过 Gateway 直接调用
DEEPSEEK_FALLBACK_POSITIONS = {
    "coding": [
        (1, "deepseek/deepseek-chat", "L2: DeepSeek V3"),
    ],
    "reasoning": [
        (0, "deepseek/deepseek-reasoner", "L1: DeepSeek R1"),
    ],
    "research": [
        (1, "deepseek/deepseek-chat", "L2: DeepSeek V3"),
    ],
    "compaction_routing": [
        (0, "deepseek/deepseek-reasoner", "L0: DeepSeek R1"),
    ],
}


def load_yaml(path: Path) -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f)


def save_yaml(path: Path, data: dict):
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True)


def check_model_quota(model_id: str, provider: str) -> tuple[bool, str]:
    """
    发最小推理请求检查模型是否可用。
    返回: (is_available, message)
    """
    # 构造请求 — 用 proxy 转发
    payload = {
        "model": model_id,
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 1,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        PROXY_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            if "choices" in result:
                return True, "OK"
            else:
                return False, f"unexpected response: {json.dumps(result)[:100]}"
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            err_data = json.loads(body)
            err_msg = err_data.get("error", {}).get("message", str(err_data))
        except Exception:
            err_msg = body[:200]
        return False, f"HTTP {e.code}: {err_msg}"
    except Exception as e:
        return False, str(e)


def restore_deepseek_in_routing(routing: dict) -> list[str]:
    """
    把 deepseek 模型加回 routing.yaml 的 fallback chain。
    返回恢复的模型列表。
    """
    restored = []

    for task_name, positions in DEEPSEEK_FALLBACK_POSITIONS.items():
        if task_name == "compaction_routing":
            # compaction_routing 是特殊结构
            fallback_chain = routing.get("compaction_routing", {}).get("fallback_chain", [])
            for pos, model_id, comment in positions:
                # 检查是否已在 chain 中
                if model_id not in fallback_chain:
                    fallback_chain.insert(pos, model_id)
                    restored.append(f"compaction_routing: {model_id}")
            routing.setdefault("compaction_routing", {})["fallback_chain"] = fallback_chain
        else:
            task = routing.get("task_routing", {}).get(task_name)
            if task is None:
                continue
            fallback_chain = task.get("fallback_chain", [])
            for pos, model_id, comment in positions:
                # 检查是否已在 chain 中
                if model_id not in fallback_chain:
                    fallback_chain.insert(pos, model_id)
                    restored.append(f"{task_name}[{pos}]: {model_id}")
            task["fallback_chain"] = fallback_chain

    return restored


def update_models_status(models: list[dict], model_id: str, status: str):
    """更新 models.yaml 中指定模型的状态"""
    for m in models:
        if m.get("id") == model_id:
            m["status"] = status
            return True
    return False


def main():
    parser = argparse.ArgumentParser(description="检查 deepseek 额度并恢复 fallback chain")
    parser.add_argument("--dry-run", action="store_true", help="只检查不修改文件")
    args = parser.parse_args()

    # 1. 加载配置
    models_data = load_yaml(MODELS_YAML)
    routing_data = load_yaml(ROUTING_YAML)
    models = models_data.get("models", [])

    # 2. 找出所有 exhausted 的 deepseek 模型
    exhausted_deepseek = [
        m for m in models
        if m.get("provider") == "deepseek" and m.get("status") == "exhausted"
    ]

    if not exhausted_deepseek:
        print("✅ 没有 exhausted 的 deepseek 模型，无需恢复")
        return

    print(f"发现 {len(exhausted_deepseek)} 个 exhausted 的 deepseek 模型:")
    for m in exhausted_deepseek:
        print(f"  - {m['id']}")

    # 3. 逐个检查额度
    recovered = []
    still_exhausted = []

    for m in exhausted_deepseek:
        model_id = m["id"]
        print(f"\n检查 {model_id} ...")
        is_ok, msg = check_model_quota(model_id, m["provider"])
        if is_ok:
            print(f"  ✅ 额度已恢复！({msg})")
            recovered.append(m)
        else:
            print(f"  ❌ 仍不可用: {msg}")
            still_exhausted.append(m)

    # 4. 恢复逻辑
    if recovered:
        print(f"\n--- 恢复 {len(recovered)} 个模型 ---")

        # 更新 models.yaml
        for m in recovered:
            status_msg = f"active (额度恢复 {datetime.now().strftime('%Y-%m-%d %H:%M')})"
            if args.dry_run:
                print(f"  [DRY-RUN] 将 {m['id']} status → {status_msg}")
            else:
                update_models_status(models, m["id"], "active")
                print(f"  ✅ {m['id']} status → active")

        # 更新 routing.yaml
        restored_positions = restore_deepseek_in_routing(routing_data)
        if restored_positions:
            for pos in restored_positions:
                print(f"  ✅ 放回 fallback chain: {pos}")

        if not args.dry_run:
            save_yaml(MODELS_YAML, models_data)
            save_yaml(ROUTING_YAML, routing_data)
            print(f"\n✅ 配置已更新，proxy config_watcher 将在 ≤10s 内热加载")
        else:
            print(f"\n[DRY-RUN] 未写入文件")
    else:
        print(f"\n⚠️ 所有 deepseek 模型仍不可用，保持 exhausted 状态")

    # 5. 汇总
    print(f"\n=== 检查结果 ===")
    print(f"已恢复: {len(recovered)}")
    print(f"仍耗尽: {len(still_exhausted)}")
    if still_exhausted:
        print("耗尽模型:")
        for m in still_exhausted:
            print(f"  - {m['id']}")


if __name__ == "__main__":
    main()
