#!/usr/bin/env bash
# 内存维护 — 整理 daily notes，把稳定的用户偏好和长期决策提炼到 USER.md / MEMORY.md
# 设计原则：只读 + 生成建议 + 写摘要文件，不自动修改 USER.md / MEMORY.md
set -uo pipefail

WORKSPACE="/Users/bangcle/.openclaw/workspace"
cd "$WORKSPACE" || exit 1

MEMORY_DIR="$WORKSPACE/memory"
OUTPUT_FILE="$MEMORY_DIR/memory-maintenance-latest.md"
DAYS_BACK=7

mkdir -p "$MEMORY_DIR"

{
  echo "# Memory Maintenance Report"
  echo ""
  echo "Generated: $(date '+%Y-%m-%d %H:%M:%S')"
  echo "Scope: Last $DAYS_BACK days of daily memory files"
  echo ""

  # 统计最近 7 天的 daily notes
  echo "## Daily Notes Summary"
  echo ""
  count=0
  total_lines=0
  for i in $(seq 0 $((DAYS_BACK - 1))); do
    date_str=$(date -v-${i}d '+%Y-%m-%d')
    file="$MEMORY_DIR/$date_str.md"
    if [ -f "$file" ]; then
      lines=$(wc -l < "$file")
      echo "- $date_str: $lines lines"
      count=$((count + 1))
      total_lines=$((total_lines + lines))
    fi
  done
  echo ""
  echo "Total: $count files, $total_lines lines"
  echo ""

  # 提取决策类内容（含 "决定" / "决策" / "ADR" / "结论"）
  echo "## Decisions & Conclusions (from last 7 days)"
  echo ""
  found=0
  for i in $(seq 0 $((DAYS_BACK - 1))); do
    date_str=$(date -v-${i}d '+%Y-%m-%d')
    file="$MEMORY_DIR/$date_str.md"
    if [ -f "$file" ]; then
      matches=$(grep -n -E "决定|决策|ADR|结论|约定|规则" "$file" 2>/dev/null | head -5)
      if [ -n "$matches" ]; then
        echo "### $date_str"
        echo "$matches" | while IFS= read -r line; do
          echo "- $line"
        done
        echo ""
        found=$((found + 1))
      fi
    fi
  done
  if [ "$found" -eq 0 ]; then
    echo "No major decisions found."
    echo ""
  fi

  # 提取用户偏好变化（含 "Always" / "Never" / "Prefer" 出现在 daily notes 中）
  echo "## Potential User Preference Updates"
  echo ""
  pref_found=0
  for i in $(seq 0 $((DAYS_BACK - 1))); do
    date_str=$(date -v-${i}d '+%Y-%m-%d')
    file="$MEMORY_DIR/$date_str.md"
    if [ -f "$file" ]; then
      matches=$(grep -n -E "^- (Always|Never|Prefer)|\*\*(Always|Never|Prefer)\*\*" "$file" 2>/dev/null | head -5)
      if [ -n "$matches" ]; then
        echo "### $date_str"
        echo "$matches" | while IFS= read -r line; do
          echo "- $line"
        done
        echo ""
        pref_found=$((pref_found + 1))
      fi
    fi
  done
  if [ "$pref_found" -eq 0 ]; then
    echo "No new preference directives detected in daily notes."
    echo ""
  fi

  # 文件大小健康检查
  echo "## File Health Check"
  echo ""

  user_md_size=$(wc -c < "$WORKSPACE/USER.md" 2>/dev/null || echo 0)
  memory_md_size=$(wc -c < "$WORKSPACE/MEMORY.md" 2>/dev/null || echo 0)
  echo "- USER.md: $user_md_size bytes"
  echo "- MEMORY.md: $memory_md_size bytes"
  echo ""

  if [ "$user_md_size" -gt 50000 ]; then
    echo "⚠️  USER.md exceeds 50KB, consider pruning outdated entries."
  fi
  if [ "$memory_md_size" -gt 100000 ]; then
    echo "⚠️  MEMORY.md exceeds 100KB, consider archiving old decisions."
  fi

  echo ""
  echo "---"
  echo "Note: This report is read-only. Manual review required before updating USER.md / MEMORY.md."
} > "$OUTPUT_FILE"

echo "✅ Memory maintenance report generated: $OUTPUT_FILE"
exit 0
