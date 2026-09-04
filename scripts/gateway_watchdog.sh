#!/bin/bash
# gateway_watchdog.sh — 轻量网关健康检查
# 注意：gateway 主进程由 launchd 管理 (KeepAlive=true)
# 本脚本仅做健康状态观测，不负责重启

LOG_FILE="/Users/bangcle/.openclaw/logs/gateway-watchdog-cron.log"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

# 检查 gateway 进程是否存活
if pgrep -f "openclaw.*gateway" > /dev/null 2>&1; then
    echo "[$TIMESTAMP] OK: gateway process running"
else
    echo "[$TIMESTAMP] WARN: gateway process not found (launchd should restart it)"
fi

# 检查 gateway 端口响应 (默认 3000，可覆盖)
PORT=${OPENCLAW_PORT:-3000}
if curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:$PORT/health" 2>/dev/null | grep -qE "^(200|401|403|404)$"; then
    echo "[$TIMESTAMP] OK: gateway port $PORT responding"
else
    echo "[$TIMESTAMP] WARN: gateway port $PORT not responding"
fi
