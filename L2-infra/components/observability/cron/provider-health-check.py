#!/usr/bin/env python3
"""
cron 脚本：provider 健康探测
- 跑在 main session（host 层），有网络、有 CLI，可以真正探测 provider API 连通性
- 结果写入 model-scheduling/config/usage.json
- 连续失败 3 次记录到 memory/YYYY-MM-DD.md
"""

import sys
import os
import subprocess
from datetime import datetime

# 切换到 workspace 根目录
os.chdir("/Users/bangcle/.openclaw/workspace")

# 执行健康检查脚本（带 --force 跳过交互式确认）
print("=== 开始 provider 健康探测 ===")
result = subprocess.run(
    [sys.executable, "model-scheduling/scripts/health_check.py", "--force"],
    capture_output=False,
    check=False
)

print(f"\n=== 健康探测完成，exit code: {result.returncode} ===")

# 记录到 memory
today = datetime.now().strftime("%Y-%m-%d")
memory_path = f"memory/{today}.md"
if os.path.exists(memory_path):
    with open(memory_path, "a", encoding="utf-8") as f:
        f.write(f"\n## 🩺 Provider 健康探测 ({datetime.now().strftime('%Y-%m-%d %H:%M')})\n")
        f.write(f"- 退出码: {result.returncode}\n")
        if result.returncode != 0:
            f.write("- 状态: 异常，请检查日志\n")
        else:
            f.write("- 状态: 正常\n")
    print(f"已记录结果到 {memory_path}")

sys.exit(result.returncode)
