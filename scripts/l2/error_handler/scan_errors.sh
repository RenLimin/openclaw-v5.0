#!/usr/bin/env bash
# 错误扫描 — 检查所有 cron job 的最近运行状态
# 发现 error/failed 状态则输出告警
set -euo pipefail

cd /Users/bangcle/.openclaw/workspace

# 获取所有 cron 的运行记录
runs_json=$(openclaw cron list --all 2>/dev/null | while IFS= read -r line; do
  # 提取 job ID（第一列）
  job_id=$(echo "$line" | awk "{print \$1}")
  # 跳过非 UUID 行
  echo "$job_id" | grep -qE "^[0-9a-f]{8}-" || continue
  echo "$job_id"
done)

failed=""
count=0

for job_id in $runs_json; do
  # 获取最近 3 次运行
  run_info=$(openclaw cron runs --id "$job_id" --limit 3 2>/dev/null | grep -E status: | head -3)
  
  has_error=$(echo "$run_info" | grep -c error 2>/dev/null || echo "0")
  
  if [ "$has_error" -gt 0 ] 2>/dev/null; then
    job_name=$(openclaw cron get "$job_id" 2>/dev/null | grep name | head -1 | sed "s/.*\"name\": *\"\\([^\"]*\\)\".*/\\1/")
    [ -z "$job_name" ] && job_name="$job_id"
    failed="${failed}${job_name}: ${has_error} errors\n"
    count=$((count + 1))
  fi
done

if [ "$count" -gt 0 ]; then
  printf "⚠️ 发现 %d 个 cron 有错误:\n%b" "$count" "$failed"
else
  echo "✅ 无错误"
fi
