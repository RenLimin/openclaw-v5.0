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

# deepseek/longCat 模型在 fallback chain 中的位置定义
# longCat 的 key 通过 ~/.zshenv 注入 proxy 进程,proxy 可读(2026-10-12 实测),
# 配额恢复后可直接放回 fallback chain
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

# longCat 在 fallback chain 中的位置(大 ctx 兜底,保持在链末尾)
LONGCAT_FALLBACK_POSITIONS = {
    "coding": [(4, "longCat/LongCat-2.0", "L5: 超大 ctx 最终兜底 (1M)")],
    "reasoning": [(3, "longCat/LongCat-2.0", "L4: 超大 ctx 文本兜底 (1M)")],
    "research": [(2, "longCat/LongCat-2.0", "L3: 超大 ctx 最终兜底 (1M)")],
    "chat": [(4, "longCat/LongCat-2.0", "L5: 超大 ctx 最终兜底 (1M)")],
    "multimodal": [(4, "longCat/LongCat-2.0", "L5: 超大 ctx 最终兜底 (1M)")],
}

# 需检查配额的 provider + 模型
QUOTA_CHECK_TARGETS = [
    {"provider": "deepseek", "models": ["deepseek/deepseek-chat", "deepseek/deepseek-reasoner"]},
    {"provider": "longCat", "models": ["longCat/LongCat-2.0"]},
]


def load_yaml(path: Path) -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f)


def save_yaml(path: Path, data: dict):
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True)


def _get_api_key(provider: str) -> str:
    """获取 provider API key：环境变量 → ~/.zshenv → auth-profiles.json → openclaw.json。

    与 proxy.get_api_key 同源逻辑，保证探活/恢复判定一致。
    LaunchAgent 启动时 source ~/.zshenv，本脚本作为 cron 子进程时环境不继承，
    需手动解析 ~/.zshenv（key 形如 export LONGCAT_API_KEY=...）。
    """
    env_keys = {
        "deepseek": ["DEEPSEEK_API_KEY"],
        "longcat": ["LONGCAT_API_KEY", "LONGCAT_KEY"],
    }
    for k in env_keys.get(provider.lower(), []):
        v = os.environ.get(k, "")
        if v:
            return v

    # 解析 ~/.zshenv（cron 子进程不继承 LaunchAgent 环境）
    zshenv = Path.home() / ".zshenv"
    if zshenv.exists():
        try:
            for line in zshenv.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line.startswith("export "):
                    continue
                body = line[len("export "):].strip()
                if "=" not in body:
                    continue
                k, _, v = body.partition("=")
                v = v.strip().strip('"').strip("'")
                if k in env_keys.get(provider.lower(), []) and v:
                    return v
        except Exception:
            pass

    auth_file = Path.home() / ".openclaw" / "auth-profiles.json"
    if auth_file.exists():
        try:
            auth_data = json.loads(auth_file.read_text())
            for pid, pconf in auth_data.get("profiles", {}).items():
                if pid.lower().startswith(provider.lower()):
                    key = pconf.get("apiKey", "")
                    if key:
                        return key
        except Exception:
            pass

    config_path = Path.home() / ".openclaw" / "openclaw.json"
    if config_path.exists():
        try:
            ocfg = json.loads(config_path.read_text())
            pconf = ocfg.get("models", {}).get("providers", {}).get(provider, {})
            key = pconf.get("apiKey", "")
            if isinstance(key, str) and key and not key.startswith("secretref-"):
                return key
        except Exception:
            pass
    return ""


PROVIDER_BASE_URLS = {
    "deepseek": "https://api.deepseek.com/v1",
    "longcat": "https://api.longcat.chat/openai/v1",
}


def check_model_quota(model_id: str, provider: str) -> tuple[bool, str]:
    """发最小推理请求检查模型是否可用。返回: (is_available, message)。

    直连真实 provider 端点（不经 proxy）——proxy 手动路由失败后会回退到
    自动路由由其他模型兜底，导致 402 被误判为可用。
    背景: 2026-10-12 假阳性 — 3 个模型真实 402，走 proxy 全部误报"额度已恢复"。
    """
    base_url = PROVIDER_BASE_URLS.get(provider.lower(), "")
    if not base_url:
        return False, f"未知 provider: {provider}"
    api_key = _get_api_key(provider)
    if not api_key:
        return False, f"无法获取 {provider} API key"

    payload = {
        "model": model_id.split("/", 1)[-1],  # 直连 API 用 model_id（去掉 provider 前缀）
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 1,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
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


def restore_in_routing(routing: dict, positions: dict) -> list[str]:
    """把模型加回 routing.yaml 的 fallback chain。返回恢复的模型列表。"""
    restored = []

    for task_name, entries in positions.items():
        if task_name == "compaction_routing":
            fallback_chain = routing.get("compaction_routing", {}).get("fallback_chain", [])
            for pos, model_id, comment in entries:
                if model_id not in fallback_chain:
                    fallback_chain.insert(pos, model_id)
                    restored.append(f"compaction_routing: {model_id}")
            routing.setdefault("compaction_routing", {})["fallback_chain"] = fallback_chain
        else:
            task = routing.get("task_routing", {}).get(task_name)
            if task is None:
                continue
            fallback_chain = task.get("fallback_chain", [])
            for pos, model_id, comment in entries:
                if model_id not in fallback_chain:
                    fallback_chain.insert(pos, model_id)
                    restored.append(f"{task_name}[{pos}]: {model_id}")
            task["fallback_chain"] = fallback_chain

    return restored


def update_usage_health(provider: str, status: str, detail: str):
    """更新 usage.json 中 provider 的健康状态（proxy 路由实际读取的文件）。

    proxy 的 _get_provider_health() 以 usage.json health.status 为准:
    exhausted → degraded(链尾) / unreachable → 跳过。恢复配额后必须同步改回,
    否则 proxy 不重启的话状态会一直卡在 exhausted。
    """
    usage_path = Path(__file__).parent.parent / "config" / "usage.json"
    if not usage_path.exists():
        return
    try:
        usage = json.loads(usage_path.read_text())
    except Exception:
        usage = {}
    providers = usage.setdefault("providers", {})
    for pid, pdata in providers.items():
        if pid.lower() == provider.lower():
            pdata.setdefault("health", {})["status"] = status
            pdata["health"]["detail"] = detail
            pdata["health"]["last_checked"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S+00:00")
            break
    else:
        providers.setdefault(provider, {}).setdefault("health", {})
        providers[provider]["health"] = {
            "status": status,
            "detail": detail,
            "last_checked": datetime.now().strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        }
    usage_path.write_text(json.dumps(usage, indent=2, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description="检查 deepseek/longCat 额度并恢复 fallback chain")
    parser.add_argument("--dry-run", action="store_true", help="只检查不修改文件")
    args = parser.parse_args()

    # 1. 加载配置
    models_data = load_yaml(MODELS_YAML)
    routing_data = load_yaml(ROUTING_YAML)
    models = models_data.get("models", [])

    # 2. 找出所有 exhausted 的目标模型（以 usage.json 为准——proxy 的 402 标记只写这里）
    # 背景: 2026-10-12 — models.yaml 与 usage.json 长期不同步,
    #       恢复脚本只查 models.yaml 永远找不到 exhausted 目标。
    usage_path = Path(__file__).parent.parent / "config" / "usage.json"
    exhausted_providers = set()
    if usage_path.exists():
        try:
            usage = json.loads(usage_path.read_text())
            for pid, pdata in usage.get("providers", {}).items():
                if pdata.get("health", {}).get("status") == "exhausted":
                    exhausted_providers.add(pid.lower())
        except Exception as e:
            print(f"⚠️ 读取 usage.json 失败: {e}")

    target_providers = {t["provider"].lower() for t in QUOTA_CHECK_TARGETS}
    exhausted_models = [
        m for m in models
        if m.get("provider", "").lower() in target_providers
        and (m.get("provider", "").lower() in exhausted_providers
             or m.get("status") == "exhausted")
    ]

    if not exhausted_models:
        print("✅ 没有 exhausted 的 deepseek/longCat 模型，无需恢复")
        return

    print(f"发现 {len(exhausted_models)} 个 exhausted 的目标模型:")
    for m in exhausted_models:
        print(f"  - {m['id']}")

    # 3. 逐个检查额度
    recovered = []
    still_exhausted = []

    for m in exhausted_models:
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

        # 更新 usage.json（proxy 路由实际读取的健康状态）
        for m in recovered:
            if args.dry_run:
                print(f"  [DRY-RUN] 将 {m['provider']} health → healthy")
            else:
                update_usage_health(m["provider"], "healthy", "额度恢复 (check_quota_and_restore)")
                print(f"  ✅ {m['provider']} health → healthy")

        # 更新 routing.yaml
        restored_positions = []
        for m in recovered:
            provider = m.get("provider", "")
            positions = DEEPSEEK_FALLBACK_POSITIONS if provider.lower() == "deepseek" else LONGCAT_FALLBACK_POSITIONS
            restored_positions += restore_in_routing(routing_data, positions)
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
        print(f"\n⚠️ 所有目标模型仍不可用，保持 exhausted 状态")

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
