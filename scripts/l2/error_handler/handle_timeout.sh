#!/usr/bin/env bash
# LLM Request Timeout 自动处置
# 策略：检测超时 → 判断根因 → 自动修复 → 重试
set -uo pipefail

LOG_FILE="/Users/bangcle/.openclaw/workspace/memory/timeout-recovery.log"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

log() { echo "[$TIMESTAMP] $1" | tee -a "$LOG_FILE"; }

log "=== LLM Timeout Recovery ==="

# Step 1: 检测当前 Gateway 状态
log "[1] Checking gateway status..."
gw_status=$(openclaw status 2>&1)
if echo "$gw_status" | grep -qi "error\|failed\|down\|timeout"; then
    log "  Gateway issue detected"
    echo "$gw_status" | grep -i "error\|failed\|down\|timeout" | head -5
fi

# Step 2: 检查当前模型健康
log "[2] Checking model health..."
current_model=$(openclaw status 2>/dev/null | grep -i "model" | head -1)
log "  Current: $current_model"

# Step 3: 检查网络连通性（模型 provider）
log "[3] Checking provider connectivity..."
# 检查常用 provider endpoint
if curl -s --connect-timeout 5 https://api.longcat.chat/health >/dev/null 2>&1; then
    log "  LongCat: OK"
else
    log "  LongCat: UNREACHABLE"
fi

# Step 4: 检查会话上下文大小（超时常见根因）
log "[4] Checking session context..."
session_info=$(openclaw status 2>/dev/null | grep -i "session\|context\|token" | head -3)
log "  $session_info"

# Step 5: 自动修复 — 如果 Gateway 不健康则重启
log "[5] Auto-fix..."
if ! openclaw gateway status >/dev/null 2>&1; then
    log "  Gateway not responding, restarting..."
    openclaw gateway restart >>"$LOG_FILE" 2>&1
    sleep 5
    if openclaw gateway status >/dev/null 2>&1; then
        log "  ✅ Gateway restarted successfully"
    else
        log "  ❌ Gateway restart failed"
        exit 1
    fi
else
    log "  Gateway healthy, no restart needed"
fi

# Step 6: 记录恢复结果
log "[6] Recovery complete"
echo "✅ Timeout recovery executed at $TIMESTAMP"
