#!/usr/bin/env bash
# model-scheduling 会话集成初始化
#
# 功能: 在 openclaw.json 中注册 model-scheduling 专用 agent 配置
# 约束: 仅首次运行一次,后续模型切换通过 sessions.patch(不写配置)
#
# 设计:
#   - 注册 4 个专用 agent(coding/research/reasoning/chat)
#   - 每个 agent 绑定 model-scheduling 推荐的 fallback chain
#   - 运行时通过 sessions_send 或 sessions.patch 切换
#   - 不修改现有 main agent 配置

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${SCRIPT_DIR}"  # model-scheduling/
CONFIG_DIR="${REPO_ROOT}/config"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1m'; BLUE='\033[0;34m'; NC='\033[0m'
log_ok()   { echo -e "${GREEN}✅${NC} $*"; }
log_warn() { echo -e "${YELLOW}⚠️${NC} $*"; }
log_err()  { echo -e "${RED}❌${NC} $*"; }
log_step() { echo -e "${BLUE}▶${NC} $*"; }

DRY_RUN=false
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=true

echo "════════════════════════════════════════════"
echo " model-scheduling 会话集成初始化"
echo "════════════════════════════════════════════"
echo ""

if $DRY_RUN; then
    echo "  --dry-run 模式,仅预览,不写入"
    echo ""
fi

# ─── Step 1: 确认路由规则 ───
log_step "[1/4] 确认路由规则 ..."

# fallback chain 来自 routing.yaml,这里硬编码(与 routing.yaml 保持一致)
log_ok "  coding:    ark-code-latest → deepseek-v4-flash → doubao-seed-2.0-lite"
log_ok "  research:  doubao-seed-2.1-turbo → ark-code-latest → doubao-seed-2.0-lite"
log_ok "  reasoning: deepseek-v4-flash → glm-5.3 → ark-code-latest"
log_ok "  chat:      doubao-seed-2.0-lite → ark-code-latest"

# ─── Step 2: 生成 patch 文件 ───
log_step "[2/4] 生成配置 patch ..."

PATCH_FILE=$(mktemp /tmp/ms-agents-patch-XXXXXX.json5)

# 用 python 生成合法 JSON5(避免 heredoc 转义问题)
python3 -c "
import json, sys
patch = {
    'agents': {
        'entries': {
            'ms-coding': {
                'name': 'ms-coding',
                'workspace': '/Users/bangcle/.openclaw/workspace',
                'model': {
                    'primary': 'coding-plan/ark-code-latest',
                    'fallbacks': ['coding-plan/deepseek-v4-flash', 'coding-plan/doubao-seed-2.0-lite']
                },
                'identity': {'name': 'ms-coding'}
            },
            'ms-research': {
                'name': 'ms-research',
                'workspace': '/Users/bangcle/.openclaw/workspace',
                'model': {
                    'primary': 'coding-plan/doubao-seed-2.1-turbo',
                    'fallbacks': ['coding-plan/ark-code-latest', 'coding-plan/doubao-seed-2.0-lite']
                },
                'identity': {'name': 'ms-research'}
            },
            'ms-reasoning': {
                'name': 'ms-reasoning',
                'workspace': '/Users/bangcle/.openclaw/workspace',
                'model': {
                    'primary': 'coding-plan/deepseek-v4-flash',
                    'fallbacks': ['coding-plan/glm-5.3', 'coding-plan/ark-code-latest']
                },
                'identity': {'name': 'ms-reasoning'}
            },
            'ms-chat': {
                'name': 'ms-chat',
                'workspace': '/Users/bangcle/.openclaw/workspace',
                'model': {
                    'primary': 'coding-plan/doubao-seed-2.0-lite',
                    'fallbacks': ['coding-plan/ark-code-latest']
                },
                'identity': {'name': 'ms-chat'}
            }
        }
    }
}
with open('${PATCH_FILE}', 'w') as f:
    json.dump(patch, f, indent=2)
"

log_ok "  patch 文件: ${PATCH_FILE}"

# ─── Step 3: dry-run 验证(验证 patch 文件合法性) ───
log_step "[3/4] dry-run 验证 ..."

if openclaw config patch --file "$PATCH_FILE" --dry-run 2>&1; then
    log_ok "  dry-run 通过"
else
    log_err "  dry-run 失败,已中止"
    rm -f "$PATCH_FILE"
    exit 1
fi

if $DRY_RUN; then
    echo ""
    echo "  patch 内容:"
    cat "$PATCH_FILE"
    echo ""
    rm -f "$PATCH_FILE"
    echo "  --dry-run 完成,未写入"
    exit 0
fi

# ─── Step 4: 正式写入 ───
log_step "[4/4] 确认写入? (y/N): "
read -r CONFIRM
if [[ "$CONFIRM" != "y" && "$CONFIRM" != "Y" ]]; then
    log_warn "  已取消"
    rm -f "$PATCH_FILE"
    exit 0
fi

if openclaw config patch --file "$PATCH_FILE" 2>&1; then
    log_ok "  已写入 openclaw.json"
else
    log_err "  写入失败"
    rm -f "$PATCH_FILE"
    exit 1
fi

rm -f "$PATCH_FILE"

# ─── 验证 ───
echo ""
log_step "验证写入结果 ..."

# 读回确认
for agent_id in ms-coding ms-research ms-reasoning ms-chat; do
    MODEL=$(openclaw config get "agents.entries.${agent_id}.model.primary" 2>/dev/null || echo "未设置")
    if [[ "$MODEL" != "未设置" ]]; then
        log_ok "  ${agent_id}: model=${MODEL}"
    else
        log_err "  ${agent_id}: 未找到"
    fi
done

# 验证 main agent 未被修改
MAIN_MODEL=$(openclaw config get agents.entries.main.model.primary 2>/dev/null)
log_ok "  main agent: model=${MAIN_MODEL}(未改变)"

echo ""
echo "════════════════════════════════════════════"
echo "  初始化完成"
echo ""
echo "  已注册 4 个 model-scheduling agent:"
echo "    ms-coding    → ark-code-latest + fallback"
echo "    ms-research  → doubao-seed-2.1-turbo + fallback"
echo "    ms-reasoning → deepseek-v4-flash + fallback"
echo "    ms-chat      → doubao-seed-2.0-lite + fallback"
echo ""
echo "  运行时切换方式:"
echo "    1. sessions_send → 路由到对应 agent"
echo "    2. sessions.patch → 实时切换模型(不写配置)"
echo ""
echo "  注意: 需要重启 gateway 后 agent 配置生效"
echo "════════════════════════════════════════════"
