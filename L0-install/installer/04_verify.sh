#!/usr/bin/env bash
# Step 04: 契约验证
# 调用契约测试 test_contract.py，输出验证报告

set -euo pipefail

L0_ROOT="$1"
RUNTIME="$2"
ENV_REPORT="$3"
VERIFY_REPORT="$4"
DRY_RUN="$5"

CONTRACT_TEST="${L0_ROOT}/contract/test_contract.py"

echo "契约验证: ${RUNTIME}"

if [ ! -f "$CONTRACT_TEST" ]; then
    echo "❌ 契约测试脚本不存在: ${CONTRACT_TEST}"
    exit 1
fi

# 检查 Python3
if ! command -v python3 &>/dev/null; then
    echo "❌ python3 不可用，跳过契约验证"
    exit 0
fi

# dry-run 模式
if [ "$DRY_RUN" = "true" ]; then
    echo "[dry-run] would run: python3 ${CONTRACT_TEST} --runtime ${RUNTIME} --output ${VERIFY_REPORT}"
    exit 0
fi

echo ""
echo "执行契约测试..."
echo "$ python3 ${CONTRACT_TEST} --runtime ${RUNTIME} --output ${VERIFY_REPORT}"
echo ""

set +e
python3 "$CONTRACT_TEST" --runtime "$RUNTIME" --output "$VERIFY_REPORT"
TEST_EXIT=$?
set -e

echo ""

if [ "$TEST_EXIT" -eq 0 ]; then
    echo "✅ 契约测试执行完成"
else
    echo "⚠️  契约测试部分失败 (exit code: ${TEST_EXIT})"
    echo "   详细信息请查看: ${VERIFY_REPORT}"
fi

# 输出摘要
if [ -f "$VERIFY_REPORT" ]; then
    echo ""
    echo "验证摘要:"
    python3 -c "
import json, sys
try:
    with open('$VERIFY_REPORT') as f:
        r = json.load(f)
    s = r.get('summary', {})
    print(f'  overall: {r.get(\"overall\", \"unknown\")}')
    print(f'  pass:  {s.get(\"pass\", 0)}')
    print(f'  fail:  {s.get(\"fail\", 0)}')
    print(f'  skip:  {s.get(\"skip\", 0)}')
    print()
    for t in r.get('tests', []):
        icon = '✅' if t['status'] == 'pass' else ('❌' if t['status'] == 'fail' else '⏭️ ')
        print(f'  {icon} {t[\"name\"]:<20} {t[\"status\"]}')
except Exception as e:
    print(f'  (无法解析报告: {e})')
" 2>/dev/null || true
fi

# P0：验证失败不强制阻断，只给警告
exit 0
