#!/usr/bin/env bash
# 仓库健康检查 — git status、未提交变更、大文件、过期分支
# 输出结构化报告，不自动修改任何东西
set -uo pipefail

WORKSPACE="/Users/bangcle/.openclaw/workspace"
cd "$WORKSPACE" || exit 1

OUTPUT_FILE="$WORKSPACE/memory/repo-health-latest.md"

{
  echo "# Repository Health Report"
  echo ""
  echo "Generated: $(date '+%Y-%m-%d %H:%M:%S')"
  echo ""

  # Git status
  echo "## Git Status"
  echo ""
  echo '```'
  git status --short 2>/dev/null || echo "Not a git repository"
  echo '```'
  echo ""

  # 未跟踪文件计数
  untracked=$(git status --porcelain 2>/dev/null | grep -c '^??' || echo 0)
  modified=$(git status --porcelain 2>/dev/null | grep -c '^ M' || echo 0)
  staged=$(git status --porcelain 2>/dev/null | grep -c '^M ' || echo 0)
  echo "## Change Summary"
  echo ""
  echo "- Modified (unstaged): $modified"
  echo "- Staged: $staged"
  echo "- Untracked: $untracked"
  echo ""

  # 大文件 (> 1MB)
  echo "## Large Files (>1MB, not in .git)"
  echo ""
  large_files=$(find . -type f -size +1M ! -path "*/.git/*" ! -path "*/node_modules/*" ! -path "*/.trash/*" ! -path "*/dreaming/*" ! -path "*/.dreams/*" ! -path "*/logs/*" 2>/dev/null | head -20)
  if [ -n "$large_files" ]; then
    echo "$large_files" | while IFS= read -r f; do
      size=$(du -h "$f" 2>/dev/null | cut -f1)
      echo "- $f ($size)"
    done
  else
    echo "No large files found."
  fi
  echo ""

  # 日志文件大小
  echo "## Log Directory Sizes"
  echo ""
  if [ -d "$WORKSPACE/L2-infra/components/model-scheduling/logs" ]; then
    du -sh L2-infra/components/model-scheduling/logs/ 2>/dev/null || true
  fi
  if [ -d ~/.openclaw/logs ]; then
    du -sh ~/.openclaw/logs/ 2>/dev/null || true
  fi
  echo ""

  # 上次提交
  echo "## Last Commit"
  echo ""
  echo '```'
  git log -1 --oneline 2>/dev/null || echo "No commits yet"
  echo '```'
  echo ""

  # 沙盒目录
  echo "## Sandbox / Temp Directories"
  echo ""
  sandbox_count=$(ls -d ~/.openclaw/sandboxes/workspace-* 2>/dev/null | wc -l | tr -d ' ')
  echo "- Stale sandboxes: $sandbox_count"
  echo ""

  echo "---"
  echo "Note: This report is read-only. Manual review required before cleanup."
} > "$OUTPUT_FILE"

echo "✅ Repo health report generated: $OUTPUT_FILE"
exit 0
