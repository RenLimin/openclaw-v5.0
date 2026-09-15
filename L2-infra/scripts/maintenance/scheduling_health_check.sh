#!/bin/bash
# 调度健康巡检 — 每小时运行
# 合并: provider 健康探测 + model-scheduling proxy 健康检查
# 如果有异常自动尝试恢复，并通知 WeCom

set -euo pipefail

WORKSPACE="$(cd "$(dirname "$0")/../../.." && pwd)"
LOG_FILE="$WORKSPACE/L2-infra/components/model-scheduling/logs/health-check.log"

mkdir -p "$(dirname "$LOG_FILE")"

echo "=== 调度健康巡检 $(date '+%Y-%m-%d %H:%M:%S') ===" | tee -a "$LOG_FILE"

ERRORS=0

# 1. model-scheduling proxy 健康检查
echo "[1/3] 检查 model-scheduling proxy..." | tee -a "$LOG_FILE"
if curl -s -m 5 http://127.0.0.1:3000/health > /dev/null 2>&1; then
    echo "  ✅ proxy 健康" | tee -a "$LOG_FILE"
else
    echo "  ❌ proxy 不响应，尝试重启..." | tee -a "$LOG_FILE"
    # 尝试通过 launchctl 重启
    launchctl unload "$HOME/Library/LaunchAgents/ai.openclaw.model-scheduling.plist" 2>/dev/null || true
    sleep 2
    launchctl load "$HOME/Library/LaunchAgents/ai.openclaw.model-scheduling.plist" 2>/dev/null || true
    sleep 5
    if curl -s -m 5 http://127.0.0.1:3000/health > /dev/null 2>&1; then
        echo "  ✅ proxy 重启成功" | tee -a "$LOG_FILE"
    else
        echo "  ❌ proxy 重启失败" | tee -a "$LOG_FILE"
        ERRORS=$((ERRORS + 1))
    fi
fi

# 2. provider 健康探测（测试一次真实请求）
echo "[2/3] 探测模型 provider..." | tee -a "$LOG_FILE"
PROVIDER_OK=true
# 用最轻量的模型测试
TEST_RESPONSE=$(curl -s -m 30 -X POST http://127.0.0.1:3000/v1/chat/completions \
    -H "Content-Type: application/json" \
    -d '{"model": "model-scheduling/auto", "messages": [{"role": "user", "content": "Hi"}], "max_tokens": 5}' 2>/dev/null || true)
if echo "$TEST_RESPONSE" | grep -q '"choices"'; then
    echo "  ✅ provider 请求正常" | tee -a "$LOG_FILE"
else
    echo "  ⚠️  provider 请求异常: ${TEST_RESPONSE:0:200}" | tee -a "$LOG_FILE"
    PROVIDER_OK=false
fi

# 3. llama-cpp embedding 服务检查
echo "[3/3] 检查 llama-cpp embedding 服务..." | tee -a "$LOG_FILE"
if curl -s -m 5 http://127.0.0.1:19433/health > /dev/null 2>&1; then
    echo "  ✅ llama-cpp 健康" | tee -a "$LOG_FILE"
else
    echo "  ⚠️  llama-cpp 不响应（可能未启用）" | tee -a "$LOG_FILE"
fi

echo "" | tee -a "$LOG_FILE"
if [ $ERRORS -gt 0 ]; then
    echo "❌ 巡检完成，发现 $ERRORS 个错误" | tee -a "$LOG_FILE"
    exit 1
elif [ "$PROVIDER_OK" = false ]; then
    echo "⚠️  巡检完成，provider 有警告" | tee -a "$LOG_FILE"
    exit 0
else
    echo "✅ 巡检完成，全部正常" | tee -a "$LOG_FILE"
    exit 0
fi
