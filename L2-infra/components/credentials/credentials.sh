#!/usr/bin/env bash
# L2 凭据管理 — 标准操作脚本
# 封装凭据的接入、轮换、撤销、审计四个操作
#
# 用法:
#   bash scripts/credentials.sh add <service> <type>     # 接入新凭据
#   bash scripts/credentials.sh rotate <service>          # 轮换凭据
#   bash scripts/credentials.sh revoke <service>          # 撤销凭据
#   bash scripts/credentials.sh audit                     # 审计所有凭据
#   bash scripts/credentials.sh check                     # 权限检查
#
# 参考: docs/architecture/components/credentials/DESIGN.md
# ADR: docs/knowledge-base/by-category/project-experience/adr/ADR-202608-005-credential-management.md

set -euo pipefail

SECRETS_DIR="${HOME}/.openclaw/secrets"
INDEX_FILE="${SECRETS_DIR}/INDEX.md"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_ok()   { echo -e "${GREEN}✅${NC} $*"; }
log_warn() { echo -e "${YELLOW}⚠️${NC} $*"; }
log_err()  { echo -e "${RED}❌${NC} $*"; }

# 确保目录存在
mkdir -p "$SECRETS_DIR"
chmod 700 "$SECRETS_DIR"

# --------------------------------------------------------------------------
# 接入
# --------------------------------------------------------------------------
cmd_add() {
    local service="${1:?用法: $0 add <service> <type>}"
    local type="${2:?用法: $0 add <service> <type> (token|apiKey|pem|json)}"
    local file="${SECRETS_DIR}/${service}.${type}"

    if [[ -f "$file" ]]; then
        log_err "凭据文件已存在: $file"
        echo "如需轮换，请使用: $0 rotate $service"
        return 1
    fi

    echo "请输入 ${service} 的 ${type} 值（输入完成后按 Ctrl+D）:"
    local value
    value=$(cat)

    if [[ -z "$value" ]]; then
        log_err "凭据值不能为空"
        return 1
    fi

    # 写入（无尾换行）
    printf '%s' "$value" > "$file"
    chmod 600 "$file"

    log_ok "凭据已创建: $file"
    echo ""
    echo "下一步:"
    echo "  1. 选择引用方式 A (SecretRef) 或 B (Credential helper)"
    echo "  2. 更新 INDEX.md: $INDEX_FILE"
    echo "  3. 如果是方式 A，注册 provider:"
    echo "     openclaw config set secrets.providers.${service}key \\"
    echo "       --provider-source file --provider-path $file --provider-mode singleValue"
}

# --------------------------------------------------------------------------
# 轮换
# --------------------------------------------------------------------------
cmd_rotate() {
    local service="${1:?用法: $0 rotate <service>}"
    local index_hit
    index_hit=$(grep "| ${service} |" "$INDEX_FILE" 2>/dev/null || true)

    if [[ -z "$index_hit" ]]; then
        log_warn "INDEX.md 中未找到 ${service} 的条目，请先执行: $0 add"
        return 1
    fi

    # 从 INDEX.md 提取文件名
    local filename
    filename=$(echo "$index_hit" | awk -F'|' '{print $3}' | xargs)
    local file="${SECRETS_DIR}/${filename}"

    if [[ ! -f "$file" ]]; then
        log_err "凭据文件不存在: $file"
        return 1
    fi

    echo "请输入 ${service} 的新 ${filename##*.} 值（输入完成后按 Ctrl+D）:"
    local value
    value=$(cat)

    if [[ -z "$value" ]]; then
        log_err "凭据值不能为空"
        return 1
    fi

    # 备份旧值（不暴露内容）
    local backup="${file}.bak.$(date +%Y%m%d%H%M%S)"
    cp "$file" "$backup"
    chmod 600 "$backup"

    # 写入新值
    printf '%s' "$value" > "$file"
    chmod 600 "$file"

    log_ok "凭据已轮换: $file"
    echo "  旧值备份: $backup（请确认新值可用后手动删除）"
}

# --------------------------------------------------------------------------
# 撤销
# --------------------------------------------------------------------------
cmd_revoke() {
    local service="${1:?用法: $0 revoke <service>}"
    local index_hit
    index_hit=$(grep "| ${service} |" "$INDEX_FILE" 2>/dev/null || true)

    if [[ -z "$index_hit" ]]; then
        log_warn "INDEX.md 中未找到 ${service} 的条目"
        return 1
    fi

    local filename
    filename=$(echo "$index_hit" | awk -F'|' '{print $3}' | xargs)
    local file="${SECRETS_DIR}/${filename}"

    echo -n "确认撤销 ${service} 的凭据？此操作不可逆 [y/N]: "
    read -r confirm
    if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
        echo "已取消"
        return 0
    fi

    if [[ -f "$file" ]]; then
        rm -f "$file"
        log_ok "凭据文件已删除: $file"
    else
        log_warn "凭据文件不存在: $file"
    fi

    echo ""
    echo "下一步:"
    echo "  1. 更新 INDEX.md（删除对应条目）"
    echo "  2. 如果是 SecretRef provider，注销:"
    echo "     openclaw config patch --stdin <<< '{\"secrets\":{\"providers\":{\"${service}key\":null}}}'"
}

# --------------------------------------------------------------------------
# 审计
# --------------------------------------------------------------------------
cmd_audit() {
    echo "🔍 凭据审计报告"
    echo "================"
    echo ""

    local total=0
    local ok=0
    local warn=0
    local errors=()

    while IFS= read -r file; do
        [[ -z "$file" ]] && continue
        [[ "$(basename "$file")" == ".DS_Store" ]] && continue
        [[ "$(basename "$file")" == "INDEX.md" ]] && continue
        [[ "$file" == *.bak.* ]] && continue

        total=$((total + 1))
        local perms
        perms=$(stat -f "%Lp" "$file" 2>/dev/null || stat -c "%a" "$file" 2>/dev/null)
        local size
        size=$(stat -f "%z" "$file" 2>/dev/null || stat -c "%s" "$file" 2>/dev/null)
        local basename
        basename=$(basename "$file")

        if [[ "$perms" == "600" ]]; then
            ok=$((ok + 1))
            log_ok "$basename (${perms}, ${size}B)"
        else
            warn=$((warn + 1))
            log_warn "$basename (${perms}, ${size}B) — 权限不是 600！"
            errors+=("$basename")
        fi
    done < <(find "$SECRETS_DIR" -maxdepth 1 -type f 2>/dev/null)

    echo ""
    echo "总计: $total | 正常: $ok | 异常: $warn"

    if [[ $warn -gt 0 ]]; then
        echo ""
        log_warn "以下凭据文件权限不是 600，请执行: chmod 600 ${errors[*]}"
        return 1
    fi

    return 0
}

# --------------------------------------------------------------------------
# 权限检查（轻量，给 cron 用）
# --------------------------------------------------------------------------
cmd_check() {
    local bad=0
    while IFS= read -r file; do
        [[ -z "$file" ]] && continue
        [[ "$(basename "$file")" == ".DS_Store" ]] && continue
        [[ "$(basename "$file")" == "INDEX.md" ]] && continue
        [[ "$file" == *.bak.* ]] && continue
        local perms
        perms=$(stat -f "%Lp" "$file" 2>/dev/null || stat -c "%a" "$file" 2>/dev/null)
        if [[ "$perms" != "600" ]]; then
            echo "PERM_VIOLATION: $file ($perms)"
            bad=$((bad + 1))
        fi
    done < <(find "$SECRETS_DIR" -maxdepth 1 -type f 2>/dev/null)

    if [[ $bad -gt 0 ]]; then
        echo "❌ 发现 $bad 个权限异常"
        return 1
    fi
    echo "✅ 所有凭据文件权限正常"
    return 0
}

# --------------------------------------------------------------------------
# 主入口
# --------------------------------------------------------------------------
case "${1:-}" in
    add)    shift; cmd_add "$@" ;;
    rotate) shift; cmd_rotate "$@" ;;
    revoke) shift; cmd_revoke "$@" ;;
    audit)  cmd_audit ;;
    check)  cmd_check ;;
    *)
        echo "用法: $0 {add|rotate|revoke|audit|check} [args]"
        echo ""
        echo "  add <service> <type>   — 接入新凭据"
        echo "  rotate <service>       — 轮换凭据"
        echo "  revoke <service>       — 撤销凭据"
        echo "  audit                  — 审计所有凭据"
        echo "  check                  — 权限检查（轻量）"
        exit 1
        ;;
esac
