#!/bin/bash
# run-visual-tests.sh — 运行所有视觉回归测试
# Usage: ./tests/run-visual-tests.sh [--update-golden]

set -euo pipefail

# 项目根目录
ROOT_DIR="/Users/bangcle/.openclaw/workspace"
TEST_DIR="${ROOT_DIR}/L2-infra/components/web-common/tests/visual"

# 默认不更新基准图
UPDATE_GOLDEN=false
if [[ "$*" == *"--update-golden"* ]]; then
    UPDATE_GOLDEN=true
fi

echo "=== 运行 web-common 视觉回归测试 ==="
echo

cd "${ROOT_DIR}"

# 运行 pytest
python3 -m pytest L2-infra/components/web-common/tests/visual -v

echo
if [ ${UPDATE_GOLDEN} = true ]; then
    echo "✅ 基准图已更新"
else
    echo "✅ 所有测试完成"
fi
