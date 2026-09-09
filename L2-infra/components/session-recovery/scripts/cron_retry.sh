#!/usr/bin/env bash
# 会话失败自动重试 — cron 入口
# 每 10 分钟跑一次，检测主会话是否失败 + 有未完成任务，是则自动唤醒
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$WORKSPACE"

python3 "$SCRIPT_DIR/check_and_retry.py" --apply
