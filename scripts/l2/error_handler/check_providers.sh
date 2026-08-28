#!/usr/bin/env bash
# Provider 健康探测 — 检查所有 AI provider 的连接状态
# 通过 openclaw 内置命令探测
set -euo pipefail

cd /Users/bangcle/.openclaw/workspace

# 获取 provider 列表
providers_json=$(openclaw status 2>&1 | grep -A 20 "Provider" || echo "")

if [ -z "$providers_json" ]; then
  echo "⚠️ 无法获取 provider 状态"
  exit 1
fi

# 检查每个 provider 状态
ok_count=0
fail_count=0
result=""

# 从 openclaw status 输出中提取 provider 状态
while IFS= read -r line; do
  # 跳过空行
  [ -z "$line" ] && continue
  
  if echo "$line" | grep -q "ok\|running\|active"; then
    ok_count=$((ok_count + 1))
  elif echo "$line" | grep -q "error\|failed\|down"; then
    fail_count=$((fail_count + 1))
    provider_name=$(echo "$line" | awk "{print \$1}")
    result="${result}  ❌ ${provider_name}\n"
  fi
done <<< "$providers_json"

if [ "$fail_count" -gt 0 ]; then
  printf "⚠️ 发现 %d 个 Provider 异常:\n%b" "$fail_count" "$result"
else
  echo "✅ 全部 ${ok_count} 个 Provider 正常"
fi
