#!/usr/bin/env bash
# 系统异常统一扫描 — 调用 Python 脚本
set -uo pipefail

WORKSPACE="/Users/bangcle/.openclaw/workspace"
cd "$WORKSPACE" || { echo "ERROR: cannot cd to workspace"; exit 1; }

# 调用 Python 扫描脚本（重构后新路径；用系统 python3，venv 已随计划移除）
python3 "$WORKSPACE/L2-infra/scripts/error_handler/scan_errors.py"
