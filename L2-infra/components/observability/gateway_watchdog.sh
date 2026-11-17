#!/bin/bash
# gateway_watchdog.sh — 网关健康检查 + channel 恢复兜底
#
# 注意：gateway 主进程由 launchd 管理 (KeepAlive=true)，本脚本不直接重启 gateway。
# 本脚本做两件事：
#   1) 观测 gateway 进程与端口（端口从 openclaw.json 读取，默认 18789）
#   2) 调用 channel_recovery.py --recover（幂等，无异常时静默）
#
# 历史缺陷修复（2026-11-17）：
#   - 端口写死 3000（实际 18789）→ 改为读配置，避免假阳性
#   - LOG_FILE 为死变量（实际由 plist 重定向）→ 改为真实写入本组件日志

set -u

COMP_DIR="/Users/bangcle/.openclaw/workspace/L2-infra/components/observability"
LOG_FILE="${COMP_DIR}/logs/gateway-watchdog.log"
PYTHON="/opt/homebrew/bin/python3"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

mkdir -p "$(dirname "$LOG_FILE")"
log() { echo "[$TIMESTAMP] $*" >> "$LOG_FILE"; }

# 1) 进程存活（launchctl 为权威来源；pgrep 在本机不可靠，会假阴性）
GW_PID="$(launchctl list ai.openclaw.gateway 2>/dev/null | /usr/bin/awk -F'= ' '/"PID"/{print $2}' | tr -d ';')"
if [ -n "$GW_PID" ] && ps -p "$GW_PID" > /dev/null 2>&1; then
  log "OK: gateway process running (pid=$GW_PID)"
else
  log "WARN: gateway process not found (launchd should restart it)"
fi

# 2) 端口探针（读配置，失败回退 18789）
PORT="$($PYTHON - <<'PY' 2>/dev/null
import json, os
try:
    d = json.load(open(os.path.expanduser("~/.openclaw/openclaw.json")))
    print(int(d["gateway"]["port"]))
except Exception:
    print(18789)
PY
)"
PORT="${PORT:-18789}"
code="$(curl -s -m 5 -o /dev/null -w "%{http_code}" "http://127.0.0.1:${PORT}/healthz" 2>/dev/null)"
if [ "$code" = "200" ]; then
  log "OK: gateway port ${PORT} responding"
else
  log "WARN: gateway port ${PORT} not responding (http=${code:-none})"
fi

# 3) channel 恢复兜底（可用 OPENCLAW_WATCHDOG_RECOVERY=0 关闭）
if [ "${OPENCLAW_WATCHDOG_RECOVERY:-1}" = "1" ]; then
  "$PYTHON" "${COMP_DIR}/scripts/channel_recovery.py" --recover >> "$LOG_FILE" 2>&1 || true
fi
