#!/usr/bin/env bash
# 安装 git hooks 到 .git/hooks/
#
# .git/ 不受版本控制，clone 后 hook 会丢失。
# canonical 版本存放在 scripts/git-hooks/，本脚本负责安装。
#
# 用法:
#   bash scripts/install-hooks.sh          # 安装
#   bash scripts/install-hooks.sh --check  # 检查已安装的是否与 canonical 一致

set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

SRC_DIR="scripts/git-hooks"
DST_DIR=".git/hooks"

if [ ! -d "$SRC_DIR" ]; then
    echo "❌ 找不到 $SRC_DIR" >&2
    exit 1
fi

CHECK_ONLY=0
[ "${1:-}" = "--check" ] && CHECK_ONLY=1

drift=0
for src in "$SRC_DIR"/*; do
    [ -f "$src" ] || continue
    name="$(basename "$src")"
    dst="$DST_DIR/$name"

    if [ "$CHECK_ONLY" -eq 1 ]; then
        if [ ! -f "$dst" ]; then
            echo "⚠️  未安装: $name"
            drift=1
        elif ! cmp -s "$src" "$dst"; then
            echo "⚠️  已漂移: $name (与 $SRC_DIR/$name 不一致)"
            drift=1
        else
            echo "✅ $name 已安装且一致"
        fi
        continue
    fi

    install -m 700 "$src" "$dst"
    echo "✅ 已安装 $name → $dst"
done

if [ "$CHECK_ONLY" -eq 1 ]; then
    if [ "$drift" -eq 1 ]; then
        echo ""
        echo "运行 bash scripts/install-hooks.sh 修复"
        exit 1
    fi
    exit 0
fi

echo ""
echo "完成。hooks 行为见 docs/conventions/commit-and-config.md"
