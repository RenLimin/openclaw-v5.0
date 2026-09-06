#!/usr/bin/env bash
# Provider 健康探测
set -uo pipefail

status_output=$(openclaw status 2>&1)

if echo "$status_output" | grep -q "error\|failed\|down"; then
  echo "⚠️ 发现 Provider 异常"
  echo "$status_output" | grep -i "error\|failed\|down"
else
  echo "✅ 全部 Provider 正常"
fi
