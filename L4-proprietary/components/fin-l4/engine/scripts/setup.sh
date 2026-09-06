#!/usr/bin/env bash
# FIN-L4 一键安装脚本
# 用法:
#   ./scripts/setup.sh     # 交互式安装
#   ./scripts/setup.sh -y  # 全自动安装（使用默认值）

set -euo pipefail

# ---------- 颜色 ----------
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${BLUE}[INFO]${NC} $*"; }
ok()    { echo -e "${GREEN}[ OK ]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
err()   { echo -e "${RED}[ERROR]${NC} $*" >&2; }
die()   { err "$*"; exit 1; }

# ---------- 参数 ----------
AUTO=0
for arg in "$@"; do
    case "$arg" in
        -y|--yes|--auto) AUTO=1 ;;
        -h|--help)
            echo "用法: $0 [-y|--yes]"
            echo "  -y, --yes    全自动安装，使用默认值"
            exit 0
            ;;
        *) die "未知参数: $arg" ;;
    esac
done

# ---------- 项目路径 ----------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_DIR}"

# ---------- 欢迎 ----------
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   🦞 FIN-L4 家庭理财管理系统              ║${NC}"
echo -e "${GREEN}║      一键安装向导  v1.0.0                   ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════╝${NC}"
echo ""
info "全本地 · 零外部依赖 · 私有化部署"
echo ""

# ---------- 依赖检查 ----------
info "检查系统依赖..."

DOCKER_OK=0
PYTHON_OK=0

if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    DOCKER_OK=1
    ok "Docker: 可用"
else
    warn "Docker: 未检测到或 daemon 未运行"
fi

if command -v python3 >/dev/null 2>&1; then
    PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    if python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3,12) else 1)'; then
        PYTHON_OK=1
        ok "Python: ${PY_VER} (满足 3.12+ 要求)"
    else
        warn "Python: ${PY_VER} (需要 3.12+，请升级)"
    fi
else
    err "Python3: 未找到"
fi

if [ "${DOCKER_OK}" = "0" ] && [ "${PYTHON_OK}" = "0" ]; then
    die "未检测到可用的 Docker 或 Python3，无法继续安装"
fi

echo ""

# ---------- 部署方式选择 ----------
if [ "${AUTO}" = "1" ]; then
    if [ "${DOCKER_OK}" = "1" ]; then
        DEPLOY_MODE="docker"
    else
        DEPLOY_MODE="bare"
    fi
    info "全自动模式: 自动选择 ${DEPLOY_MODE} 部署"
else
    if [ "${DOCKER_OK}" = "1" ]; then
        DEFAULT_MODE="docker"
        read -rp "选择部署方式 [docker/bare] (默认: docker): " input
        DEPLOY_MODE="${input:-docker}"
    else
        DEFAULT_MODE="bare"
        read -rp "选择部署方式 [bare] (默认: bare): " input
        DEPLOY_MODE="${input:-bare}"
    fi
fi

case "${DEPLOY_MODE}" in
    docker|bare) ;;
    *) die "无效的部署方式: ${DEPLOY_MODE}" ;;
esac

echo ""

# ---------- 端口配置 ----------
if [ "${AUTO}" = "1" ]; then
    FIN4_PORT="8500"
else
    read -rp "服务端口 (默认: 8500): " input
    FIN4_PORT="${input:-8500}"
fi
info "端口: ${FIN4_PORT}"

# ---------- 演示数据 ----------
if [ "${AUTO}" = "1" ]; then
    IMPORT_DATA="n"
else
    read -rp "是否导入演示数据？[y/N] (默认: N): " input
    IMPORT_DATA="${input:-n}"
fi

if [[ "${IMPORT_DATA}" =~ ^[Yy]$ ]]; then
    FIN4_IMPORT=1
    warn "将导入演示数据（首次体验推荐）"
else
    FIN4_IMPORT=0
    info "使用空数据库上线"
fi

echo ""

# ---------- 执行部署 ----------
info "开始部署 FIN-L4..."
echo ""

export FIN4_PORT
export FIN4_IMPORT

if [ "${DEPLOY_MODE}" = "docker" ]; then
    ./deploy.sh --docker
else
    ./deploy.sh --bare
fi

echo ""
ok "🎉 FIN-L4 部署完成！"
echo ""
echo "  🌐 访问地址:  http://localhost:${FIN4_PORT}"
echo ""
echo "  📖 操作手册:  docs/OPERATIONS.md"
echo "  🚀 架构说明:  docs/ARCHITECTURE.md"
echo ""
echo "  常用命令:"
echo "    make status   — 查看部署状态"
echo "    make stop   — 停止服务"
echo "    make logs   — 查看日志"
echo "    make backup — 数据备份"
echo ""
echo "  祝理财愉快！🦞"
echo ""
