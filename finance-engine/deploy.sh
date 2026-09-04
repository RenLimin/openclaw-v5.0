#!/usr/bin/env bash
# FIN-L4 一键部署脚本 - 自动检测 Docker 环境,自行决定部署方式
#
# 用法:
#   ./deploy.sh              # 检测环境并部署(推荐)
#   ./deploy.sh --docker     # 强制 Docker 部署
#   ./deploy.sh --bare       # 强制裸机(systemd/launchd)部署
#   ./deploy.sh --status     # 查看当前部署状态
#   ./deploy.sh --stop       # 停止服务
#   ./deploy.sh --uninstall  # 卸载服务(保留数据)
#
# 环境变量:
#   FIN4_PORT      外部端口 (默认 8500)
#   FIN4_FAMILY_ID 家庭 ID   (默认 default)
#   FIN4_IMPORT    部署后导入演示数据 (1=是 0=否, 默认 0)

set -euo pipefail

# ---------- 配置 ----------
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="fin-l4"
PORT="${FIN4_PORT:-8500}"
FAMILY_ID="${FIN4_FAMILY_ID:-default}"
IMPORT_DATA="${FIN4_IMPORT:-0}"
VENV_DIR="${PROJECT_DIR}/.venv"
DATA_DIR="${FIN4_DB_DIR:-${HOME}/.fin-l4}"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
err()   { echo -e "${RED}[ERROR]${NC} $*" >&2; }
die()   { err "$*"; exit 1; }

# ---------- Docker 检测 ----------
DOCKER_OK=0
COMPOSE_CMD=""

detect_docker() {
    if command -v docker >/dev/null 2>&1; then
        if docker info >/dev/null 2>&1; then
            DOCKER_OK=1
            return 0
        fi
    fi
    DOCKER_OK=0
    return 1
}

detect_compose() {
    if docker compose version >/dev/null 2>&1; then
        COMPOSE_CMD="docker compose"
        return 0
    elif command -v docker-compose >/dev/null 2>&1; then
        COMPOSE_CMD="docker-compose"
        return 0
    fi
    COMPOSE_CMD=""
    return 1
}

# ---------- 状态 ----------
cmd_status() {
    if [ "${DOCKER_OK}" = "1" ]; then
        if docker ps -a --format '{{.Names}}' 2>/dev/null | grep -q "^${SERVICE_NAME}$"; then
            local state
            state=$(docker inspect -f '{{.State.Status}}' "${SERVICE_NAME}" 2>/dev/null || echo "unknown")
            info "Docker 部署: 容器 ${SERVICE_NAME} 状态 = ${state}"
            if [ "$state" = "running" ]; then
                info "访问: http://localhost:${PORT}"
            fi
            exit 0
        fi
        info "Docker 可用但未部署 ${SERVICE_NAME}"
    fi
    if [ -f "/etc/systemd/system/${SERVICE_NAME}.service" ] || [ -f "${HOME}/Library/LaunchAgents/com.finl4.web.plist" ]; then
        info "检测到系统服务定义 (裸机部署)"
        if command -v systemctl >/dev/null 2>&1; then
            systemctl --no-pager status "${SERVICE_NAME}" || true
        fi
        exit 0
    fi
    info "未检测到已部署的 FIN-L4"
    exit 0
}

# ---------- Docker 部署 ----------
deploy_docker() {
    info "检测到 Docker,使用容器化部署..."
    detect_compose || warn "未找到 compose,将使用 docker run 直接部署"

    info "构建镜像 fin-l4:latest..."
    docker build -t fin-l4:latest "${PROJECT_DIR}"

    if docker ps -a --format '{{.Names}}' 2>/dev/null | grep -q "^${SERVICE_NAME}$"; then
        info "停止旧容器 ${SERVICE_NAME}..."
        docker rm -f "${SERVICE_NAME}" >/dev/null 2>&1 || true
    fi

    if [ -n "${COMPOSE_CMD}" ]; then
        info "使用 ${COMPOSE_CMD} up -d --build 启动..."
        (
            cd "${PROJECT_DIR}"
            FIN4_PORT="${PORT}" FIN4_FAMILY_ID="${FAMILY_ID}" ${COMPOSE_CMD} up -d --build
        )
    else
        info "使用 docker run 启动..."
        docker run -d \
            --name "${SERVICE_NAME}" \
            --restart unless-stopped \
            -p "${PORT}:8500" \
            -e FIN4_HOST=0.0.0.0 \
            -e FIN4_PORT=8500 \
            -e FIN4_DB_DIR=/data \
            -e FIN4_FAMILY_ID="${FAMILY_ID}" \
            -v fin4_data:/data \
            fin-l4:latest
    fi

    info "等待服务启动..."
    for i in $(seq 1 20); do
        if curl -sf "http://127.0.0.1:${PORT}/" >/dev/null 2>&1; then
            info "OK 服务已就绪: http://localhost:${PORT}"
            return 0
        fi
        sleep 1
    done
    err "服务启动超时,查看日志: docker logs ${SERVICE_NAME}"
    return 1
}

# ---------- 裸机 (systemd/launchd) 部署 ----------
ensure_python_deps() {
    if [ -d "${VENV_DIR}" ]; then
        info "使用已有虚拟环境 ${VENV_DIR}"
    else
        info "创建虚拟环境..."
        python3 -m venv "${VENV_DIR}"
    fi
    "${VENV_DIR}/bin/pip" install --quiet --upgrade pip
    "${VENV_DIR}/bin/pip" install --quiet -r "${PROJECT_DIR}/fin_l4/requirements.txt"
}

deploy_bare() {
    info "未检测到 Docker 或 Docker 不可用,使用裸机部署..."

    ensure_python_deps

    mkdir -p "${DATA_DIR}"

    local PYTHON_BIN="${VENV_DIR}/bin/python"

    if command -v systemctl >/dev/null 2>&1; then
        info "检测到 systemd,创建系统服务..."
        local UNIT="/etc/systemd/system/${SERVICE_NAME}.service"
        if [ -w /etc/systemd/system ]; then
            cat > "${UNIT}" << SYSEOF
[Unit]
Description=FIN-L4 家庭理财管理系统
After=network.target

[Service]
Type=simple
User=${USER:-nobody}
WorkingDirectory=${PROJECT_DIR}
Environment=FIN4_HOST=127.0.0.1
Environment=FIN4_PORT=${PORT}
Environment=FIN4_DB_DIR=${DATA_DIR}
Environment=FIN4_FAMILY_ID=${FAMILY_ID}
ExecStart=${PYTHON_BIN} -m fin_l4.run_web
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
SYSEOF
            systemctl daemon-reload
            systemctl enable "${SERVICE_NAME}"
            systemctl restart "${SERVICE_NAME}"
            info "OK systemd 服务已启动: ${SERVICE_NAME}"
            info "访问: http://localhost:${PORT}"
        else
            warn "无权限写 /etc/systemd/system,改为前台启动(调试用)"
            warn "sudo ./deploy.sh --bare 可安装为系统服务"
            "${PYTHON_BIN}" -m fin_l4.run_web &
        fi
    elif [ "$(uname)" = "Darwin" ]; then
        info "macOS 环境,创建 launchd 服务..."
        local LAUNCH_AGENT="${HOME}/Library/LaunchAgents/com.finl4.web.plist"
        mkdir -p "$(dirname "${LAUNCH_AGENT}")"
        cat > "${LAUNCH_AGENT}" << PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.finl4.web</string>
    <key>ProgramArguments</key>
    <array>
        <string>${PYTHON_BIN}</string>
        <string>-m</string>
        <string>fin_l4.run_web</string>
    </array>
    <key>WorkingDirectory</key>
    <string>${PROJECT_DIR}</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>FIN4_HOST</key>
        <string>127.0.0.1</string>
        <key>FIN4_PORT</key>
        <string>${PORT}</string>
        <key>FIN4_DB_DIR</key>
        <string>${DATA_DIR}</string>
        <key>FIN4_FAMILY_ID</key>
        <string>${FAMILY_ID}</string>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
</dict>
</plist>
PLISTEOF
        launchctl unload "${LAUNCH_AGENT}" 2>/dev/null || true
        launchctl load "${LAUNCH_AGENT}"
        info "OK launchd 服务已加载: com.finl4.web"
        info "访问: http://localhost:${PORT}"
    else
        err "未识别的系统类型,请手动运行: python3 -m fin_l4.run_web"
        return 1
    fi
}

# ---------- 停止 ----------
cmd_stop() {
    if [ "${DOCKER_OK}" = "1" ]; then
        if docker ps -a --format '{{.Names}}' 2>/dev/null | grep -q "^${SERVICE_NAME}$"; then
            docker stop "${SERVICE_NAME}" >/dev/null 2>&1 && info "Docker 容器已停止"
        fi
    fi
    if command -v systemctl >/dev/null 2>&1; then
        systemctl stop "${SERVICE_NAME}" 2>/dev/null && info "systemd 服务已停止"
    fi
    if [ -f "${HOME}/Library/LaunchAgents/com.finl4.web.plist" ]; then
        launchctl unload "${HOME}/Library/LaunchAgents/com.finl4.web.plist" 2>/dev/null && info "launchd 服务已停止"
    fi
}

# ---------- 卸载 ----------
cmd_uninstall() {
    cmd_stop
    if [ "${DOCKER_OK}" = "1" ]; then
        docker rm -f "${SERVICE_NAME}" >/dev/null 2>&1 || true
        docker volume rm fin4_data >/dev/null 2>&1 || true
        info "已移除 Docker 容器与数据卷(数据已删除!)"
    fi
    if command -v systemctl >/dev/null 2>&1; then
        rm -f "/etc/systemd/system/${SERVICE_NAME}.service"
        systemctl daemon-reload
    fi
    [ -f "${HOME}/Library/LaunchAgents/com.finl4.web.plist" ] && rm -f "${HOME}/Library/LaunchAgents/com.finl4.web.plist"
    info "已移除服务定义(数据目录 ${DATA_DIR} 保留)"
}

# ---------- 导入演示数据 ----------
import_demo() {
    if [ "${IMPORT_DATA}" != "1" ]; then
        return 0
    fi
    info "导入演示数据..."
    if [ -x "${VENV_DIR}/bin/python" ]; then
        "${VENV_DIR}/bin/python" "${PROJECT_DIR}/fin_l4/load_demo_data.py"
    else
        python3 "${PROJECT_DIR}/fin_l4/load_demo_data.py"
    fi
    info "演示数据导入完成"
}

# ---------- 主入口 ----------
# 先做一次环境检测(供 --status 使用)
detect_docker

MODE="auto"
[ $# -gt 0 ] && MODE="$1"

case "${MODE}" in
    --status)      cmd_status ;;
    --stop)        cmd_stop ;;
    --uninstall)   cmd_uninstall ;;
    --docker)      deploy_docker ;;
    --bare)        deploy_bare ;;
    auto)
        if [ "${DOCKER_OK}" = "1" ]; then
            deploy_docker
        else
            deploy_bare
        fi
        ;;
    *)
        echo "用法: $0 [--status|--stop|--uninstall|--docker|--bare]"
        exit 1
        ;;
esac

# 导入演示数据(仅部署成功后)
if [ "${MODE}" = "auto" ] || [ "${MODE}" = "--docker" ] || [ "${MODE}" = "--bare" ]; then
    import_demo
fi

exit 0
