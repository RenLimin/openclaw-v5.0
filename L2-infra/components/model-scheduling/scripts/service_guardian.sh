#!/bin/sh
# service_guardian.sh — Gateway ↔ 自定义服务生命周期同步守护
# 
# 设计：
#   - 纯 POSIX sh，零依赖，OpenClaw 升级不破坏
#   - launchd KeepAlive 托管，进程挂了自动拉起
#   - 每 3 秒检查 Gateway health，同步启停自定义服务
#   - 状态文件供外部监控读取
#
# Rex 拍板：2026-08-26，方案 B 升级版（替代 cron 轮询）

set -eu

# ─── 配置 ──────────────────────────────────────
GATEWAY_HEALTH="http://127.0.0.1:18789/health"
CHECK_INTERVAL=3
STATE_FILE="${HOME}/.openclaw/workspace/model-scheduling/logs/guardian_state.json"
LOG_FILE="${HOME}/.openclaw/workspace/model-scheduling/logs/guardian.log"
MAX_LOG_SIZE=524288  # 512KB

# 自定义服务列表（未来新增在此追加）
# 格式: label|plist_path|check_port
SERVICES="ai.openclaw.model-scheduling|${HOME}/.openclaw/workspace/model-scheduling/LaunchAgent/ai.openclaw.model-scheduling.plist|3000"

# ─── 工具函数 ──────────────────────────────────
log() {
    ts=$(date '+%Y-%m-%d %H:%M:%S')
    line="[${ts}] $1"
    echo "$line"
    # 轮转
    if [ -f "$LOG_FILE" ] && [ "$(stat -f%z "$LOG_FILE" 2>/dev/null || echo 0)" -gt "$MAX_LOG_SIZE" ]; then
        mv "$LOG_FILE" "${LOG_FILE}.1"
    fi
    echo "$line" >> "$LOG_FILE" 2>/dev/null || true
}

check_gateway() {
    code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 2 "$GATEWAY_HEALTH" 2>/dev/null || echo "000")
    [ "$code" = "200" ]
}

is_loaded() {
    label="$1"
    launchctl list 2>/dev/null | grep -q "\t${label}$"
}

is_running() {
    label="$1"
    pid=$(launchctl list 2>/dev/null | grep "\t${label}$" | awk '{print $1}')
    [ "$pid" != "-" ] && [ "$pid" != "" ] && [ "$pid" -gt 0 ] 2>/dev/null
}

is_port_listening() {
    port="$1"
    lsof -i ":${port}" -sTCP:LISTEN -t >/dev/null 2>&1
}

load_service() {
    label="$1"
    plist="$2"
    la_path="${HOME}/Library/LaunchAgents/${label}.plist"
    
    # 确保 plist 在 LaunchAgents 目录
    if [ ! -f "$la_path" ] || ! diff -q "$plist" "$la_path" >/dev/null 2>&1; then
        cp "$plist" "$la_path"
        chmod 644 "$la_path"
        log "已更新 plist: $label"
    fi
    
    if is_loaded "$label"; then
        return 0
    fi
    
    launchctl bootstrap "gui/$(id -u)" "$la_path" 2>/dev/null && {
        log "已加载服务: $label"
        return 0
    } || {
        log "加载失败: $label" >&2
        return 1
    }
}

unload_service() {
    label="$1"
    la_path="${HOME}/Library/LaunchAgents/${label}.plist"
    
    if ! is_loaded "$label"; then
        return 0
    fi
    
    launchctl bootout "gui/$(id -u)" "$la_path" 2>/dev/null && {
        log "已卸载服务: $label"
        return 0
    } || {
        # 兜底：直接杀
        pid=$(launchctl list 2>/dev/null | grep "\t${label}$" | awk '{print $1}')
        if [ "$pid" != "-" ] && [ "$pid" != "" ]; then
            kill -9 "$pid" 2>/dev/null || true
            log "兜底杀进程: $label (PID $pid)"
        fi
        return 0
    }
}

write_state() {
    gateway_state="$1"
    cat > "$STATE_FILE" <<EOF
{
  "timestamp": "$(date -u '+%Y-%m-%dT%H:%M:%SZ')",
  "gateway": ${gateway_state},
  "services": [
EOF
    first=1
    echo "$SERVICES" | tr ' ' '\n' | while IFS='|' read -r label plist port; do
        [ -z "$label" ] && continue
        if is_running "$label"; then
            status="running"
        elif is_loaded "$label"; then
            status="loaded"
        else
            status="stopped"
        fi
        if [ "$first" -eq 1 ]; then
            first=0
        else
            echo "," >> "$STATE_FILE"
        fi
        printf '    {"label": "%s", "status": "%s", "port": %s}' "$label" "$status" "$port" >> "$STATE_FILE"
    done
    cat >> "$STATE_FILE" <<EOF

  ]
}
EOF
}

# ─── 主循环 ────────────────────────────────────
log "========================================="
log "Service Guardian 守护进程启动 (PID $$)"
log "检查间隔: ${CHECK_INTERVAL}s"
log "========================================="

prev_gateway=""
consecutive_failures=0

while true; do
    if check_gateway; then
        consecutive_failures=0
        if [ "$prev_gateway" != "alive" ]; then
            log "✅ Gateway 恢复"
            prev_gateway="alive"
        fi
        
        # Gateway 活着 → 确保服务也活着
        echo "$SERVICES" | tr ' ' '\n' | while IFS='|' read -r label plist port; do
            [ -z "$label" ] && continue
            if ! is_running "$label"; then
                log "⚠️ $label 未运行，拉起..."
                load_service "$label" "$plist" || true
                sleep 1
                if is_running "$label"; then
                    log "✅ $label 已拉起"
                else
                    log "❌ $label 拉起失败"
                fi
            fi
        done
    else
        consecutive_failures=$((consecutive_failures + 1))
        if [ "$prev_gateway" != "dead" ]; then
            log "⛔ Gateway 停止 (连续 ${consecutive_failures} 次)"
            prev_gateway="dead"
        fi
        
        # Gateway 死了 → 停掉自定义服务
        echo "$SERVICES" | tr ' ' '\n' | while IFS='|' read -r label plist port; do
            [ -z "$label" ] && continue
            if is_loaded "$label"; then
                log "⛔ Gateway 停止，卸载 $label"
                unload_service "$label" || true
            fi
        done
    fi
    
    write_state "$([ "$prev_gateway" = "alive" ] && echo "true" || echo "false")"
    
    sleep "$CHECK_INTERVAL"
done
