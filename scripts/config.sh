#!/usr/bin/env bash
# L2 配置管理 — 标准操作脚本
# 把配置变更的四步流程固化成代码，杜绝跳过"读回确认"
#
# 用法:
#   bash scripts/config.sh audit             # 全面审计（快照/hook/校验/凭据引用）
#   bash scripts/config.sh snapshot          # 脱敏快照入库
#   bash scripts/config.sh diff              # 当前配置 vs 上次快照
#   bash scripts/config.sh apply <file>      # 四步流程: dry-run → apply → 读回 → 快照
#   bash scripts/config.sh probe <model> <n> # 实测模型 contextWindow
#
# 设计: docs/architecture/components/config/DESIGN.md
# ADR:  docs/knowledge-base/by-category/project-experience/adr/ADR-202608-007-config-management.md

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG_FILE="${HOME}/.openclaw/openclaw.json"
SNAPSHOT="${REPO_ROOT}/config-snapshots/openclaw.json"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
log_ok()   { echo -e "${GREEN}✅${NC} $*"; }
log_warn() { echo -e "${YELLOW}⚠️${NC} $*"; }
log_err()  { echo -e "${RED}❌${NC} $*"; }
log_step() { echo -e "${BLUE}▶${NC} $*"; }

cd "$REPO_ROOT"

# --------------------------------------------------------------------------
# audit — 全面审计
# --------------------------------------------------------------------------
cmd_audit() {
    local problems=0

    echo "════════════════════════════════════════════"
    echo " L2 配置管理审计"
    echo "════════════════════════════════════════════"
    echo ""

    # 1. 配置文件存在性与权限
    log_step "配置文件"
    if [[ -f "$CONFIG_FILE" ]]; then
        local perm
        perm="$(stat -f '%Lp' "$CONFIG_FILE" 2>/dev/null || stat -c '%a' "$CONFIG_FILE" 2>/dev/null)"
        log_ok "存在: $CONFIG_FILE (权限 $perm)"
        if [[ "$perm" != "600" ]]; then
            log_warn "权限非 600 — 含 gateway token，建议 chmod 600"
            problems=$((problems + 1))
        fi
    else
        log_err "配置文件不存在: $CONFIG_FILE"
        return 1
    fi
    echo ""

    # 2. schema 校验
    log_step "schema 校验"
    if openclaw config validate >/dev/null 2>&1; then
        log_ok "openclaw config validate 通过"
    else
        log_err "schema 校验失败，运行 openclaw config validate 查看详情"
        problems=$((problems + 1))
    fi
    echo ""

    # 3. 快照一致性（P1: 变更可追溯）
    log_step "配置快照"
    if [[ ! -f "$SNAPSHOT" ]]; then
        log_warn "快照不存在 — 运行: bash scripts/config.sh snapshot"
        problems=$((problems + 1))
    elif python3 scripts/snapshot_config.py --check >/dev/null 2>&1; then
        log_ok "快照与当前配置一致"
    else
        log_warn "配置有未快照的变更 — 运行: bash scripts/config.sh snapshot"
        problems=$((problems + 1))
    fi
    echo ""

    # 4. hook 漂移（P4）
    log_step "git hooks"
    if [[ -f scripts/install-hooks.sh ]]; then
        if bash scripts/install-hooks.sh --check >/dev/null 2>&1; then
            log_ok "hooks 已安装且与 canonical 版本一致"
        else
            log_warn "hooks 未安装或已漂移 — 运行: bash scripts/install-hooks.sh"
            problems=$((problems + 1))
        fi
    fi
    echo ""

    # 5. 凭据引用完整性（SecretRef 指向的文件是否存在）
    log_step "凭据引用"
    python3 - <<'PY'
import json, os, sys
cfg = os.path.expanduser("~/.openclaw/openclaw.json")
d = json.load(open(cfg))
provs = (d.get("secrets") or {}).get("providers") or {}
if not provs:
    print("  (无 SecretRef provider)")
    sys.exit(0)
bad = 0
for name, p in provs.items():
    path = p.get("path")
    if p.get("source") != "file" or not path:
        print(f"  ? {name}: source={p.get('source')} (非 file，跳过)")
        continue
    if os.path.isfile(path):
        mode = oct(os.stat(path).st_mode & 0o777)[2:]
        flag = "✅" if mode == "600" else "⚠️ "
        print(f"  {flag} {name} → {path} (权限 {mode})")
        if mode != "600":
            bad += 1
    else:
        print(f"  ❌ {name} → {path} (文件缺失)")
        bad += 1
sys.exit(1 if bad else 0)
PY
    # shellcheck disable=SC2181
    if [[ $? -ne 0 ]]; then problems=$((problems + 1)); fi
    echo ""

    # 6. 模型 contextWindow 声明概览（P3）
    log_step "模型 contextWindow 声明"
    python3 - <<'PY'
import json, os
d = json.load(open(os.path.expanduser("~/.openclaw/openclaw.json")))
for pname, p in (d.get("models") or {}).get("providers", {}).items():
    mods = p.get("models") or []
    if isinstance(mods, dict):
        mods = [{"id": k, **v} for k, v in mods.items()]
    for m in mods:
        cw = m.get("contextWindow")
        mt = m.get("maxTokens")
        mark = " " if cw else "?"
        print(f"  {mark} {pname}/{m.get('id'):<26} ctx={cw!s:>9}  maxOut={mt}")
PY
    echo ""

    echo "════════════════════════════════════════════"
    if [[ $problems -eq 0 ]]; then
        log_ok "审计通过，无问题"
        return 0
    fi
    log_warn "发现 $problems 个问题（见上）"
    return 1
}

# --------------------------------------------------------------------------
# snapshot / diff
# --------------------------------------------------------------------------
cmd_snapshot() {
    python3 scripts/snapshot_config.py
    if ! git diff --quiet -- config-snapshots/ 2>/dev/null || \
       [[ -n "$(git status --porcelain -- config-snapshots/ 2>/dev/null)" ]]; then
        echo ""
        log_warn "快照有变更，记得提交:"
        echo "    git add config-snapshots/ && git commit"
    fi
}

cmd_diff() { python3 scripts/snapshot_config.py --diff; }

# --------------------------------------------------------------------------
# apply — 四步流程固化（核心价值）
# --------------------------------------------------------------------------
cmd_apply() {
    local patch_file="${1:?用法: $0 apply <patch-file.json5>}"
    [[ -f "$patch_file" ]] || { log_err "patch 文件不存在: $patch_file"; return 1; }

    echo "════════════════════════════════════════════"
    echo " 配置变更四步流程"
    echo "════════════════════════════════════════════"
    echo ""
    echo "patch 内容:"
    sed 's/^/    /' "$patch_file"
    echo ""

    log_step "[1/4] dry-run 验证"
    if ! openclaw config patch --file "$patch_file" --dry-run; then
        log_err "dry-run 失败，已中止（未做任何改动）"
        return 1
    fi
    echo ""

    log_step "[2/4] 应用"
    openclaw config patch --file "$patch_file"
    echo ""

    log_step "[3/4] 读回确认 ★"
    if ! openclaw config validate; then
        log_err "校验失败！配置可能已损坏，检查 ~/.openclaw/openclaw.json.bak"
        return 1
    fi
    # 逐个读回 patch 中出现的顶层路径
    python3 - "$patch_file" <<'PY'
import json, re, subprocess, sys
raw = open(sys.argv[1]).read()
# 提取 json5 里的键路径（粗粒度：顶层两层）
keys = re.findall(r'^\s*([A-Za-z_][\w-]*)\s*:', raw, re.M)
seen, order = set(), []
for k in keys:
    if k not in seen:
        seen.add(k); order.append(k)
top = order[:2]
if not top:
    print("  (无法解析 patch 路径，跳过逐项读回)")
    sys.exit(0)
path = ".".join(top)
r = subprocess.run(["openclaw", "config", "get", path],
                   capture_output=True, text=True)
label = "✅" if r.returncode == 0 else "⚠️ "
print(f"  {label} openclaw config get {path}")
for line in (r.stdout or r.stderr).strip().splitlines()[:20]:
    print(f"      {line}")
PY
    echo ""

    log_step "[4/4] 快照入库"
    python3 scripts/snapshot_config.py
    echo ""

    log_ok "四步流程完成"
    echo ""
    log_warn "别忘了提交快照:"
    echo "    git add config-snapshots/ && git commit -m 'chore(config): <说明>'"
}

# --------------------------------------------------------------------------
# probe — 实测模型 contextWindow
# --------------------------------------------------------------------------
cmd_probe() {
    local model="${1:?用法: $0 probe <model-id> [token-count]}"
    local ntok="${2:-10}"
    log_step "实测 $model @ ~${ntok} tokens"
    python3 scripts/probe_context_window.py "$model" "$ntok"
    echo ""
    echo "提示: 二分探边界。400 + 'context window exceeded' = 真边界；"
    echo "      429 AccountRateLimitExceeded = 频率限制，等 60~75s 重试。"
    echo "      方法论见 EXP-20260822-004。"
}

# --------------------------------------------------------------------------
usage() {
    sed -n '2,14p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

main() {
    local cmd="${1:-}"
    shift || true
    case "$cmd" in
        audit)    cmd_audit "$@" ;;
        snapshot) cmd_snapshot "$@" ;;
        diff)     cmd_diff "$@" ;;
        apply)    cmd_apply "$@" ;;
        probe)    cmd_probe "$@" ;;
        ""|-h|--help|help) usage ;;
        *) log_err "未知命令: $cmd"; echo ""; usage; return 1 ;;
    esac
}

main "$@"
