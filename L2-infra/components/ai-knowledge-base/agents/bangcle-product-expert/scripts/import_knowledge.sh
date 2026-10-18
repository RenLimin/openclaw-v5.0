#!/bin/bash
# Bangcle 产品专家 Agent - 产品知识导入脚本
# 直接从源目录导入所有支持的文档格式（md/txt/doc/docx/pdf）
# 用法: ./import_knowledge.sh [db_path] [source_dir]
set -e

SB="$(cd "$(dirname "$0")/../../../.." && pwd)"
DB_PATH="${1:-$SB/instances/bangcle-products/data/bangcle-products.db}"
SRC_DIR="${2:-/Users/bangcle/Bangcle Workspace/07. Bangcle Prod}"

echo "=== 导入产品知识到 bangcle-products 实例 ==="
echo "源目录: $SRC_DIR"
echo "DB路径: $DB_PATH"
echo ""

# 计数统计
TOTAL=$(find "$SRC_DIR" -type f \( -iname "*.md" -o -iname "*.txt" -o -iname "*.doc" -o -iname "*.docx" -o -iname "*.pdf" \) | wc -l | tr -d ' ')
COUNT=0
SUCCESS=0
FAIL=0

echo "发现 $TOTAL 篇文档，开始导入..."
echo ""

while IFS= read -r file; do
  COUNT=$((COUNT + 1))
  output=$(python3 "$SB/ai-kb" ingest upload \
    --db-path "$DB_PATH" \
    --domain-code bangcle-products \
    --file "$file" 2>&1)
  if echo "$output" | grep -q '"success": true'; then
    SUCCESS=$((SUCCESS + 1))
  else
    FAIL=$((FAIL + 1))
    echo "  ❌ 失败: $(basename "$file")"
  fi
  if [ $((COUNT % 50)) -eq 0 ]; then
    echo "  进度: $COUNT/$TOTAL (成功 $SUCCESS / 失败 $FAIL)"
  fi
done < <(find "$SRC_DIR" -type f \( -iname "*.md" -o -iname "*.txt" -o -iname "*.doc" -o -iname "*.docx" -o -iname "*.pdf" \) | sort)

echo ""
echo "✅ 导入完成: 总计 $COUNT | 成功 $SUCCESS | 失败 $FAIL"
echo ""
echo "=== 实例统计 ==="
python3 "$SB/ai-kb" instance stats \
  --code bangcle-products \
  --db-path "$DB_PATH"
