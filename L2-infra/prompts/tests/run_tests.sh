#!/usr/bin/env bash
# 应答契约校验器黄金基准（fail-closed 自保护）。
# 合规样例必须 exit 0 (PASS)；违规样例必须非 0 (BLOCK)。
# 任一不符 -> 本脚本 exit 1，pre-commit 阻断。
set -u
cd "$(git rev-parse --show-toplevel 2>/dev/null || echo "$(cd "$(dirname "$0")/../../.." && pwd)")"
CHECKER="L2-infra/prompts/tools/check_answer_contract.py"
FX="L2-infra/prompts/tests/fixtures"
fail=0

assert_pass() {
    python3 "$CHECKER" "$1" >/dev/null 2>&1
    local code=$?
    if [ $code -eq 0 ]; then echo "✅ PASS-as-expected: $(basename "$1")"; else
        echo "❌ $(basename "$1") 应 PASS 却 BLOCK(exit $code)"; fail=1; fi
}
assert_block() {
    python3 "$CHECKER" "$1" >/dev/null 2>&1
    local code=$?
    if [ $code -ne 0 ]; then echo "✅ BLOCK-as-expected: $(basename "$1")"; else
        echo "❌ $(basename "$1") 应 BLOCK 却放行(exit 0) — 门禁失效!"; fail=1; fi
}

assert_pass  "$FX/good-report.md"
assert_pass  "$FX/good-degraded.md"
assert_block "$FX/bad-no-timestamp.md"
assert_block "$FX/bad-silent-degrade.md"

if [ $fail -ne 0 ]; then
    echo "❌ 应答契约黄金基准失败 — 校验器/契约改动破坏了门禁"
    exit 1
fi
echo "✅ 应答契约黄金基准通过（2 PASS / 2 BLOCK 符合预期）"

# --- 运行时守卫单测（hooks/answer-contract-guard）---
# 仅当 hooks/answer-contract-guard/ 或 prompts 相关被改动时触发。
if git diff --cached --name-only --diff-filter=ACMR 2>/dev/null | grep -qE "hooks/answer-contract-guard/|prompts/"; then
    echo "🔄 answer-contract-guard 有改动，运行单测..."
    if node hooks/answer-contract-guard/test.mjs >/dev/null 2>&1; then
        echo "✅ answer-contract-guard 单测通过"
    else
        echo "❌ answer-contract-guard 单测失败 — hook 判定被改坏"
        fail=1
    fi
fi
