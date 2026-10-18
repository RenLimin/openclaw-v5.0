#!/bin/bash
# Bangcle 产品专家 Agent - 知识库实例初始化脚本
# 用法: ./init_instance.sh [db_path]
set -e

SB="$(cd "$(dirname "$0")/../.." && pwd)"
DB_PATH="${1:-$SB/instances/bangcle-products/data/bangcle-products.db}"
INSTANCE_DIR="$(dirname "$DB_PATH")"

echo "=== 初始化 Bangcle 产品知识库实例 ==="
echo "DB 路径: $DB_PATH"
mkdir -p "$INSTANCE_DIR"

# 使用 CLI 创建实例（product-kb 模板，自动注册内置模板）
python3 "$SB/ai-kb" instance create \
  --code bangcle-products \
  --name "Bangcle产品知识库" \
  --template product-kb \
  --db-path "$DB_PATH"

echo ""
echo "=== 验证实例 ==="
python3 "$SB/ai-kb" instance stats \
  --code bangcle-products \
  --db-path "$DB_PATH"

echo ""
echo "✅ 实例初始化完成"
echo "下一步: ./import_knowledge.sh"
