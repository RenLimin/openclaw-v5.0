#!/bin/bash
# Bangcle 产品专家 Agent - 产品知识导入脚本
# 用法: ./import_knowledge.sh [db_path]
set -e

SB="$(cd "$(dirname "$0")/../.." && pwd)"
DB_PATH="${1:-$SB/instances/bangcle-products/data/bangcle-products.db}"
KNOWLEDGE_DIR="$(dirname "$0")/../knowledge"

echo "=== 导入产品知识到 bangcle-products 实例 ==="
echo "知识目录: $KNOWLEDGE_DIR"

COUNT=0
for file in "$KNOWLEDGE_DIR"/*.md; do
  echo ""
  echo "--- 导入: $(basename "$file") ---"
  python3 "$SB/ai-kb" ingest upload \
    --db-path "$DB_PATH" \
    --domain-code bangcle-products \
    --file "$file"
  COUNT=$((COUNT + 1))
done

echo ""
echo "✅ 导入完成: $COUNT 篇文档"
echo ""
echo "=== 验证 ==="
python3 "$SB/ai-kb" instance stats \
  --code bangcle-products \
  --db-path "$DB_PATH"
