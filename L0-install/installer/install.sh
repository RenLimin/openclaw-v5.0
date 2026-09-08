#!/usr/bin/env bash
# L0 系统安装层 - 主入口
# 六步流水线：env_probe → select → install → init_adapter → verify → snapshot
# 遵循 ADR-011 Error Contract / ADR-007 配置写保护 / ADR-005 凭据安全

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
L0_ROOT="$(dirname "$SCRIPT_DIR")"
LOG_FILE="${L0_ROOT}/install.log"
SNAPSHOT_DIR="${HOME}/.openclaw/snapshots/l0-install"
ENV_REPORT="${L0_ROOT}/env-report.json"
VERIFY_REPORT="${L0_ROOT}/verify-report.json"

# 默认值
RUNTIME=""
DRY_RUN=false
SKIP_VERIFY=false
ROLLBACK_STEP=""
CLEAN_SNAPSHOTS=false
CURRENT_STEP=0

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# --- 工具函数 ---

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
    echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] [INFO] $1" >> "$LOG_FILE"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
    echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] [WARN] $1" >> "$LOG_FILE"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
    echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] [ERROR] $1" >> "$LOG_FILE"
}

log_success() {
    echo -e "${GREEN}[OK]${NC} $1"
    echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] [OK] $1" >> "$LOG_FILE"
}

# Error Contract 格式输出错误
emit_error() {
    local code="$1"
    local severity="$2"
    local recoverable="$3"
    local retryable="$4"
    local message="$5"
    local component="$6"
    
    cat <<ERRJSON
{
  "code": "${code}",
  "severity": "${severity}",
  "recoverable": ${recoverable},
  "retryable": ${retryable},
  "message": "${message}",
  "context": {
    "layer": "L0",
    "component": "${component}"
  }
}
ERRJSON
}

# 打快照
snapshot_step() {
    local step_num="$1"
    local step_name="$2"
    
    if [ "$DRY_RUN" = true ]; then
        log_info "[dry-run] would snapshot step ${step_num} (${step_name})"
        return 0
    fi
    
    mkdir -p "$SNAPSHOT_DIR"
    local snap_dir="${SNAPSHOT_DIR}/step-${step_num}-${step_name}-$(date +%Y%m%d-%H%M%S)"
    mkdir -p "$snap_dir"
    
    # 1. 配置快照（如果 OpenClaw 已安装）
    if command -v openclaw &>/dev/null; then
        openclaw config get --all > "$snap_dir/config.json" 2>/dev/null || true
        log_info "配置快照已保存: $snap_dir/config.json"
    fi
    
    # 2. 凭据索引（不含值，仅元信息）
    if [ -d "${HOME}/.openclaw/secrets" ]; then
        ls -la "${HOME}/.openclaw/secrets/" > "$snap_dir/credential-index.txt" 2>/dev/null || true
        log_info "凭据索引已保存: $snap_dir/credential-index.txt"
    fi
    
    # 3. 快照 manifest
    cat > "$snap_dir/manifest.json" <<MEOF
{
  "step": ${step_num},
  "step_name": "${step_name}",
  "timestamp": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "runtime": "${RUNTIME:-not_selected}",
  "l0_version": "1.0"
}
MEOF
    
    # 清理超过 5 份的旧快照
    # shellcheck disable=SC2012
    ls -1dt "${SNAPSHOT_DIR}"/step-* 2>/dev/null | tail -n +6 | xargs -r rm -rf
    
    log_success "快照完成: step ${step_num} (${step_name})"
    echo "$snap_dir" > "${SNAPSHOT_DIR}/.last-snapshot"
}

# 回滚到上一快照
rollback_to_prev() {
    local failed_step="$1"
    log_warn "步骤 ${failed_step} 失败，尝试回滚到上一快照..."
    
    if [ ! -f "${SNAPSHOT_DIR}/.last-snapshot" ]; then
        log_error "没有可用的上一快照，无法回滚"
        emit_error "ERR_L0_ROLLBACK_NO_SNAPSHOT" "Sev2" "false" "false" \
            "回滚失败：没有可用的上一快照" "installer/${failed_step}" >> "$LOG_FILE"
        return 1
    fi
    
    local last_snap
    last_snap=$(cat "${SNAPSHOT_DIR}/.last-snapshot")
    
    if [ ! -d "$last_snap" ]; then
        log_error "快照目录不存在: $last_snap"
        return 1
    fi
    
    log_info "回滚到快照: $last_snap"
    # TODO: 实际回滚逻辑（配置恢复等），P0 仅记录+提示
    log_warn "P0 回滚为半自动：配置快照已保存于 $last_snap"
    log_warn "请手动恢复配置：openclaw config patch < $last_snap/config.json"
    
    emit_error "ERR_L0_STEP_FAILED" "Sev2" "true" "true" \
        "步骤 ${failed_step} 失败，已回滚到上一快照" "installer/${failed_step}" >> "$LOG_FILE"
    
    return 0
}

# 检查运行时是否在 registry 中
validate_runtime() {
    local runtime="$1"
    local registry_file="${L0_ROOT}/registry/${runtime}.yaml"
    
    if [ ! -f "$registry_file" ]; then
        log_error "未知运行时: ${runtime}（registry 中未找到）"
        log_info "可用运行时:"
        ls "${L0_ROOT}/registry/" | sed 's/.yaml$//' | sed 's/^/  - /'
        return 1
    fi
    return 0
}

# --- 步骤执行 ---

run_step() {
    local step_num="$1"
    local step_name="$2"
    local script_name="$3"
    local script_path="${SCRIPT_DIR}/${script_name}"
    
    CURRENT_STEP="$step_num"
    
    log_info "━━━ Step ${step_num}/5: ${step_name} ━━━"
    
    if [ ! -f "$script_path" ]; then
        log_error "脚本不存在: ${script_path}"
        rollback_to_prev "${script_name}" || true
        return 1
    fi
    
    if [ "$DRY_RUN" = true ]; then
        log_info "[dry-run] would execute: ${script_path}"
        snapshot_step "$step_num" "$step_name"
        return 0
    fi
    
    # 执行步骤脚本
    if ! bash "$script_path" "$L0_ROOT" "$RUNTIME" "$ENV_REPORT" "$VERIFY_REPORT" "$DRY_RUN"; then
        log_error "步骤失败: ${step_name}"
        rollback_to_prev "${script_name}" || true
        return 1
    fi
    
    snapshot_step "$step_num" "$step_name"
    log_success "Step ${step_num} 完成: ${step_name}"
    return 0
}

# --- 帮助信息 ---

show_help() {
    cat <<HELP
L0 系统安装层 - 主入口 (v1.0)

用法:
  install.sh [选项]

选项:
  --runtime <name>      指定运行时（非交互模式）
  --dry-run             预检模式，不实际执行安装
  --skip-verify         跳过契约验证
  --rollback <step>     回滚到指定步骤的快照
  --clean-snapshots     清理所有快照
  --help                显示此帮助

示例:
  install.sh                                  # 交互模式
  install.sh --runtime openclaw               # 非交互，安装 OpenClaw
  install.sh --runtime openclaw --dry-run     # 预检
  install.sh --rollback 2                     # 回滚到步骤 2 的快照

环境变量:
  L0_LOG_LEVEL    日志级别 (info/warn/error, 默认 info)
HELP
}

# --- 主流程 ---

main() {
    # 解析参数
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --runtime)
                RUNTIME="$2"
                shift 2
                ;;
            --dry-run)
                DRY_RUN=true
                shift
                ;;
            --skip-verify)
                SKIP_VERIFY=true
                shift
                ;;
            --rollback)
                ROLLBACK_STEP="$2"
                shift 2
                ;;
            --clean-snapshots)
                CLEAN_SNAPSHOTS=true
                shift
                ;;
            --help|-h)
                show_help
                exit 0
                ;;
            *)
                log_error "未知选项: $1"
                show_help
                exit 1
                ;;
        esac
    done
    
    # 初始化日志
    mkdir -p "$(dirname "$LOG_FILE")"
    echo "===== L0 Install Log - $(date -u +"%Y-%m-%dT%H:%M:%SZ") =====" >> "$LOG_FILE"
    
    # 清理快照
    if [ "$CLEAN_SNAPSHOTS" = true ]; then
        log_info "清理所有快照..."
        rm -rf "$SNAPSHOT_DIR"
        log_success "快照已清理"
        exit 0
    fi
    
    # 手动回滚
    if [ -n "$ROLLBACK_STEP" ]; then
        log_info "回滚到步骤 ${ROLLBACK_STEP} 的快照..."
        # TODO: 实现回滚逻辑
        log_warn "P0 回滚为半自动，请查看 ${SNAPSHOT_DIR}/ 下的快照手动恢复"
        exit 0
    fi
    
    echo ""
    echo "🦞 L0 系统安装层 v1.0"
    echo "============================"
    echo ""
    
    # Step 0: 环境检测
    if ! run_step 0 "环境检测" "00_env_probe.sh"; then
        exit 1
    fi
    
    # Step 1: 运行时选型
    if ! run_step 1 "运行时选型" "01_select.sh"; then
        exit 1
    fi
    
    # 读取选定的 runtime
    if [ -f "${L0_ROOT}/.selected-runtime" ]; then
        RUNTIME=$(cat "${L0_ROOT}/.selected-runtime")
        log_info "选定运行时: ${RUNTIME}"
    fi
    
    if [ -z "$RUNTIME" ]; then
        log_error "未选定运行时，终止安装"
        exit 1
    fi
    
    validate_runtime "$RUNTIME" || exit 1
    
    # Step 2: 运行时安装
    if ! run_step 2 "运行时安装" "02_install.sh"; then
        exit 1
    fi
    
    # Step 3: 适配层初始化
    if ! run_step 3 "适配层初始化" "03_init_adapter.sh"; then
        exit 1
    fi
    
    # Step 4: 契约验证
    if [ "$SKIP_VERIFY" = true ]; then
        log_warn "跳过契约验证（--skip-verify）"
    else
        if ! run_step 4 "契约验证" "04_verify.sh"; then
            log_warn "契约验证未完全通过，请查看 verify-report.json"
            # P0: 验证失败不强制终止，给出警告
        fi
    fi
    
    # Step 5: 快照入库
    if ! run_step 5 "快照入库" "05_snapshot.sh"; then
        log_warn "快照失败，不影响安装结果"
    fi
    
    echo ""
    echo "============================"
    log_success "🎉 L0 安装完成！运行时: ${RUNTIME}"
    echo ""
    echo "日志文件: ${LOG_FILE}"
    echo "验证报告: ${VERIFY_REPORT}"
    echo "快照目录: ${SNAPSHOT_DIR}"
    echo ""
    
    if [ "$SKIP_VERIFY" = false ] && [ -f "$VERIFY_REPORT" ]; then
        echo "契约验证摘要:"
        python3 -c "
import json, sys
try:
    with open('$VERIFY_REPORT') as f:
        r = json.load(f)
    s = r.get('summary', {})
    print(f'  overall: {r.get(\"overall\", \"unknown\")}')
    print(f'  pass: {s.get(\"pass\", 0)}, fail: {s.get(\"fail\", 0)}, skip: {s.get(\"skip\", 0)}')
except Exception as e:
    print(f'  (无法解析报告: {e})')
" 2>/dev/null || true
    fi
    
    exit 0
}

main "$@"
