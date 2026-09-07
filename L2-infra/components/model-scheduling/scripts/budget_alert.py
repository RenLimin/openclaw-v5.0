#!/usr/bin/env python3
"""预算告警:检查各 provider 用量是否超过月度预算阈值,超过则发送告警。

设计说明:
  - 读取 config/budget.json 中的阈值配置
  - 读取 config/usage.json 中的用量数据
  - 超过阈值则通过配置的渠道发送告警
  - 支持 WeCom 告警(当前)和预留邮件告警
"""

import json
import subprocess
from pathlib import Path
from datetime import datetime, timezone

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = REPO_ROOT / "config"
BUDGET_CONFIG = CONFIG_DIR / "budget.json"
USAGE_FILE = CONFIG_DIR / "usage.json"


def load_config():
    """加载预算配置和用量数据。"""
    if not BUDGET_CONFIG.exists():
        return None, None, f"预算配置文件不存在: {BUDGET_CONFIG}"

    try:
        budget_conf = json.loads(BUDGET_CONFIG.read_text(encoding="utf-8"))
    except Exception as e:
        return None, None, f"读取预算配置失败: {str(e)}"

    if not USAGE_FILE.exists():
        return None, None, f"用量文件不存在: {USAGE_FILE}"

    try:
        usage_data = json.loads(USAGE_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        return None, None, f"读取用量数据失败: {str(e)}"

    return budget_conf, usage_data, None


def check_budget(budget_conf, usage_data):
    """检查各 provider 用量是否超过预算。返回超限列表。"""
    over_budget = []
    budget_providers = budget_conf.get("budget", {})
    usage_providers = usage_data.get("providers", {})

    for provider_id, budget in budget_providers.items():
        if not budget.get("enabled", True):
            continue

        threshold = budget.get("monthly_threshold", 0)
        if threshold <= 0:
            continue

        # TODO: 实际用量从用量 API 获取,当前框架预留
        # 现在框架已经搭好,等火山方舟开放用量 API 后补全用量获取逻辑
        # 当前先假设最近一次健康检查就能触发告警(占位逻辑)
        # 这里演示:如果 provider 不健康就触发告警
        provider_usage = usage_providers.get(provider_id, {})
        health = provider_usage.get("health", {})
        status = health.get("status", "healthy")

        # TODO: 替换为实际用量判断
        # 占位:演示用,不健康就告警
        # 实际替换为: if current_usage > threshold:
        if status != "healthy":
            over_budget.append({
                "provider": provider_id,
                "threshold": threshold,
                "current_status": status,
                "currency": budget.get("currency", "USD"),
            })

    return over_budget


def send_alert_wecom(target, message):
    """通过 WeCom 发送告警消息。"""
    cmd = [
        "openclaw",
        "message",
        "send",
        "--channel",
        "wecom",
        "--target",
        target,
        "--message",
        message,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0, result.stdout + result.stderr


def main():
    parser = argparse.ArgumentParser(description="模型调度预算告警检查")
    parser.add_argument("--dry-run", action="store_true", help="只检查不发送告警")
    args = parser.parse_args()

    print("=== 模型调度预算告警检查 ===")
    print()

    budget_conf, usage_data, err = load_config()
    if err:
        print(f"❌ {err}")
        sys.exit(1)

    over_budget = check_budget(budget_conf, usage_data)
    if not over_budget:
        print("✅ 所有 provider 用量在预算内")
        sys.exit(0)

    print(f"⚠️ 发现 {len(over_budget)} 个 provider 超限:\n")
    for item in over_budget:
        print(f"  • {item['provider']}: 阈值 {item['threshold']} {item['currency']}, 当前状态 {item['current_status']}")
    print()

    alert_conf = budget_conf.get("alert", {})
    if not alert_conf.get("enabled", False):
        print("ℹ️  告警已禁用，退出")
        sys.exit(0)

    # 构建告警消息
    now = datetime.now(timezone.utc).astimezone().isoformat(timespec="minutes")
    msg_lines = [
        "⚠️ **模型调度预算超限告警**",
        f"检查时间: {now}",
        "",
        "超限 provider:",
    ]
    for item in over_budget:
        msg_lines.append(
            f"- `{item['provider']}`: 月度阈值 {item['threshold']} {item['currency']}, 当前状态 {item['current_status']}"
        )
    message = "\n".join(msg_lines)

    if args.dry_run:
        print("--dry-run 模式，告警消息预览:")
        print()
        print(message)
        sys.exit(0)

    channel = alert_conf.get("channel", "wecom")
    if channel == "wecom":
        target = alert_conf.get("wecom_target", "user:1313")
        print(f"📤 发送 WeCom 告警到 {target} ...")
        ok, output = send_alert_wecom(target, message)
        if ok:
            print("✅ 告警发送成功")
        else:
            print(f"❌ 告警发送失败: {output[:200]}")
            sys.exit(1)
    else:
        print(f"⚠️  不支持的告警渠道: {channel}")
        sys.exit(1)

    print()
    print("=== 检查完成 ===")


if __name__ == "__main__":
    import argparse
    import sys
    main()
