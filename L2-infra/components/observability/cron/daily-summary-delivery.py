#!/usr/bin/env python3
"""
cron 脚本：每日观测摘要投递
- 生成每日摘要 → 投递到配置好的 WeCom 渠道
- 每天 23:50 执行，总结今日用量和系统状态
"""

import sys
import os
import subprocess
from datetime import datetime

# 切换到 workspace 根目录
os.chdir("/Users/bangcle/.openclaw/workspace")

# 生成每日摘要，捕获输出
print("=== 生成每日观测摘要 ===")
result = subprocess.run(
    [sys.executable, "L2-infra/components/observability/scripts/agent_observer.py", "--daily"],
    capture_output=True,
    text=True,
    check=False
)

summary = result.stdout
if result.returncode != 0:
    summary += "\n" + result.stderr
    print(f"⚠️ 生成过程异常，exit code: {result.returncode}")

print("\n=== 投递摘要到 WeCom ===")
# 使用 openclaw message 发送到 WeCom（渠道已配置，直接发送）
delivery_result = subprocess.run(
    [
        "openclaw", "message", "send",
        "--channel", "wecom",
        "--target", "user:1313",
        "--message", summary
    ],
    capture_output=False,
    check=False
)

print(f"\n=== 每日摘要投递完成，exit code: {delivery_result.returncode} ===")
sys.exit(delivery_result.returncode)
