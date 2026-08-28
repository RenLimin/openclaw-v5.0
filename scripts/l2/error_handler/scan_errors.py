#!/usr/bin/env bash
# 错误扫描 — 检查所有 cron job 的最近运行状态
set -uo pipefail

WORKSPACE="/Users/bangcle/.openclaw/workspace"
cd "$WORKSPACE" || { echo "ERROR: cannot cd to workspace"; exit 1; }

# 获取所有 cron ID
job_ids=$(openclaw cron list --all 2>/dev/null | awk '{print $1}' | grep -E "^[0-9a-f]{8}-" || true)

failed=""
count=0

for job_id in $job_ids; do
  # 获取最近 3 次运行状态
  run_statuses=$(openclaw cron runs --id "$job_id" --limit 3 2>/dev/null | grep '"status"' | head -3)
  
  has_error=$(echo "$run_statuses" | grep -c '"error"' 2>/dev/null || echo "0")
  
  if [ "$has_error" -gt 0 ] 2>/dev/null; then
    job_name=$(openclaw cron get "$job_id" 2>/dev/null | grep '"name"' | head -1 | sed 's/.*"name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/')
    [ -z "$job_name" ] && job_name="$job_id"
    failed="${failed}  - ${job_name}: ${has_error} errors\n"
    count=$((count + 1))
  fi
done

if [ "$count" -gt 0 ]; then
  printf "⚠️ 发现 %d 个 cron 有错误:\n%b" "$count" "$failed"
else
  echo "✅ 无错误"
fi
