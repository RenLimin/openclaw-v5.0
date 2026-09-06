#!/usr/bin/env bash
# model-scheduling 一次性初始化脚本
#
# 设计约束:
#   - 仅首次部署或重建时运行
#   - 不修改 openclaw.json(除非显式注册 cron)
#   - 所有状态存储在 model-scheduling/config/ 外部文件中
#   - 支持 --dry-run 预览

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS_DIR="${REPO_ROOT}/scripts"
CONFIG_DIR="${REPO_ROOT}/config"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
log_ok()   { echo -e "${GREEN}✅${NC} $*"; }
log_warn() { echo -e "${YELLOW}⚠️${NC} $*"; }
log_err()  { echo -e "${RED}❌${NC} $*"; }
log_step() { echo -e "${BLUE}▶${NC} $*"; }

DRY_RUN=false
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=true

echo "════════════════════════════════════════════"
echo " model-scheduling 初始化"
echo "════════════════════════════════════════════"
echo ""

if $DRY_RUN; then
    echo "  --dry-run 模式,仅预览,不执行写入"
    echo ""
fi

# ─── Step 1: 验证依赖 ───
log_step "[1/5] 验证依赖 ..."

MISSING=0
for cmd in python3 openclaw; do
    if command -v "$cmd" >/dev/null 2>&1; then
        log_ok "  $cmd 可用"
    else
        log_err "  $cmd 未安装"
        MISSING=1
    fi
done

# 检查 Python yaml 模块
if python3 -c "import yaml" 2>/dev/null; then
    log_ok "  PyYAML 可用"
else
    log_warn "  PyYAML 未安装(将使用简易 YAML 解析)"
    log_warn "  建议: pip install pyyaml"
fi

if [[ "$MISSING" == "1" ]]; then
    log_err "缺少必要依赖,已中止"
    exit 1
fi

# ─── Step 2: 同步模型注册表 ───
log_step "[2/5] 同步模型注册表 ..."

if $DRY_RUN; then
    log_ok "  [dry-run] 将运行: python3 sync_models.py --dry-run"
else
    python3 "${SCRIPTS_DIR}/sync_models.py" --force
    log_ok "  模型注册表已同步"
fi

# ─── Step 3: 首次用量获取 ───
log_step "[3/5] 首次用量获取 ..."

if $DRY_RUN; then
    log_ok "  [dry-run] 将运行: python3 fetch_usage.py --dry-run"
else
    python3 "${SCRIPTS_DIR}/fetch_usage.py" --force
    log_ok "  用量信息已获取"
fi

# ─── Step 4: 首次健康探测 ───
log_step "[4/5] 首次健康探测 ..."

if $DRY_RUN; then
    log_ok "  [dry-run] 将运行: python3 health_check.py --dry-run"
else
    python3 "${SCRIPTS_DIR}/health_check.py" --force
    log_ok "  健康探测已完成"
fi

# ─── Step 5: 验证 ───
log_step "[5/5] 验证 ..."

if $DRY_RUN; then
    log_ok "  [dry-run] 跳过验证"
else
    # 验证文件存在
    for f in models.yaml routing.yaml usage.json; do
        if [[ -f "${CONFIG_DIR}/$f" ]]; then
            log_ok "  config/$f 存在"
        else
            log_err "  config/$f 缺失"
        fi
    done

    # 验证 openclaw.json 未被修改
    if command -v openclaw >/dev/null 2>&1; then
        # 简单验证:config get 能正常返回
        if openclaw config get agents.defaults.model.primary >/dev/null 2>&1; then
            log_ok "  openclaw.json 可读(未被破坏)"
        else
            log_err "  openclaw.json 读取失败"
        fi
    fi

    # 验证路由引擎
    if python3 "${SCRIPTS_DIR}/router.py" --task-type coding --json >/dev/null 2>&1; then
        log_ok "  路由引擎可用"
    else
        log_err "  路由引擎测试失败"
    fi
fi

echo ""
echo "════════════════════════════════════════════"
if $DRY_RUN; then
    echo "  dry-run 完成,未做任何写入"
else
    echo "  初始化完成"
    echo ""
    echo "  后续定期任务:"
    echo "    - 模型同步:每周一次(手动运行 sync_models.py)"
    echo "    - 用量获取:每周一次(手动运行 fetch_usage.py)"
    echo "    - 健康探测:每小时一次(手动运行 health_check.py)"
    echo "    - 路由决策:每次任务前(调用 router.py)"
fi
echo "════════════════════════════════════════════"
