#!/usr/bin/env bash
# 系统异常统一扫描 — 调用 Python 脚本
set -uo pipefail

WORKSPACE="/Users/bangcle/.openclaw/workspace"
cd "$WORKSPACE" || { echo "ERROR: cannot cd to workspace"; exit 1; }

# 调用 Python 扫描脚本
.venv-bdms/bin/python3 scripts/l2/error_handler/scan_errors.py
