#!/bin/bash
# OA 产品中心文档增量同步 — 一键编排
#  1) 增量抓取（水位过滤 + 落盘 + 备份旧版 + manifest）
#  2) 扫描入库（path-first upsert：新增/replaced/unchanged）
#  3) 重建索引（build-index 只处理无 chunk 的文档）
#
# 用法:  scripts/oa_sync_pipeline.sh [--dry-run] [--since YYYY-MM-DD] [--no-advance]
# 状态:  ~/.openclaw/data/product-kb-oa-sync/state.json（水位/历史/manifest）
set -uo pipefail

COMPONENT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
KB_ROOT="${OA_KB_ROOT:-$HOME/Bangcle Workspace/07. Bangcle Prod}"
DB_PATH="${OA_KB_DB:-$COMPONENT_DIR/data/product_kb.db}"
SCRIPT_DIR="$COMPONENT_DIR/scripts"

EXTRA_ARGS=()
DRY_RUN=""
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN="--dry-run"; EXTRA_ARGS+=("$arg") ;;
    *) EXTRA_ARGS+=("$arg") ;;
  esac
done

echo "===== [1/3] OA 增量抓取 ====="
python3 "$SCRIPT_DIR/oa_incremental_sync.py" --root "$KB_ROOT" "${EXTRA_ARGS[@]}" || exit 1
if [ -n "$DRY_RUN" ]; then
  echo "（dry-run：跳过入库与索引）"
  exit 0
fi

echo
echo "===== [2/3] 扫描入库 ====="
python3 -m product_kb.cli --db "$DB_PATH" scan --root "$KB_ROOT" || exit 1

echo
echo "===== [3/3] 重建索引（增量） ====="
python3 -m product_kb.cli --db "$DB_PATH" build-index || exit 1

echo
echo "===== 完成 ====="
echo "水位: $(python3 -c "import json;print(json.load(open('$HOME/.openclaw/data/product-kb-oa-sync/state.json'))['watermark'])")"
