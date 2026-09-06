#!/usr/bin/env bash
# L2 工具策略审计
#
# 核心命题: 「允许」≠「可用」。tools.profile/allow/deny 只治理授权边界，
#           不保证工具真能干活。本脚本同时检查两者。
#
# 用法: bash scripts/tool_policy_audit.sh
# 退出码: 0=健康, 1=发现问题
#
# 设计: docs/architecture/components/tool-policy/DESIGN.md
# ADR:  docs/knowledge-base/by-category/project-experience/adr/ADR-202608-008-tool-policy-governance.md

set -uo pipefail
cd "$(git rev-parse --show-toplevel 2>/dev/null || echo "$HOME/.openclaw/workspace")"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
log_ok()   { echo -e "${GREEN}✅${NC} $*"; }
log_warn() { echo -e "${YELLOW}⚠️${NC} $*"; }
log_err()  { echo -e "${RED}❌${NC} $*"; }
log_step() { echo -e "${BLUE}▶${NC} $*"; }

problems=0

echo "════════════════════════════════════════════"
echo " L2 工具策略审计"
echo "════════════════════════════════════════════"
echo ""

# --------------------------------------------------------------------------
# 1. 策略配置
# --------------------------------------------------------------------------
log_step "策略配置"
TOOLS_JSON="$(openclaw config get tools 2>/dev/null || echo '{}')"
printf '%s\n' "$TOOLS_JSON" | sed 's/^/    /'

TOOLS_TMP="$(mktemp)"; printf '%s' "$TOOLS_JSON" > "$TOOLS_TMP"
trap 'rm -f "$TOOLS_TMP"' EXIT
PROFILE="$(python3 -c "
import json,sys
try: print((json.load(open(sys.argv[1])) or {}).get('profile','<unset>'))
except Exception: print('<parse-error>')
" "$TOOLS_TMP" 2>/dev/null)"

case "$PROFILE" in
    coding|messaging|minimal) log_ok "profile=$PROFILE（非 full，符合最小权限）" ;;
    full)  log_err "profile=full — 违反最小权限原则"; problems=$((problems+1)) ;;
    *)     log_warn "profile=$PROFILE（未显式设置，依赖默认值）" ;;
esac
echo ""

# --------------------------------------------------------------------------
# 2. allow / alsoAllow 冲突（config 校验会拒绝，提前抓）
# --------------------------------------------------------------------------
log_step "allow / alsoAllow 冲突检查"
python3 - "$TOOLS_TMP" <<'PY'
import json, sys
try:
    t = json.load(open(sys.argv[1])) or {}
except Exception as e:
    print(f"  ? 无法解析 tools 配置: {e}"); sys.exit(0)
bad = 0
def check(scope, name):
    global bad
    if isinstance(scope, dict) and "allow" in scope and "alsoAllow" in scope:
        print(f"  ❌ {name}: allow 与 alsoAllow 并存 — config 校验会拒绝")
        bad += 1
check(t, "tools")
for pid, cfg in (t.get("byProvider") or {}).items():
    check(cfg, f"tools.byProvider.{pid}")
for sid, cfg in (t.get("toolsBySender") or {}).items():
    check(cfg, f"tools.toolsBySender.{sid}")
if not bad:
    print("  ✅ 无冲突（同 scope 内 allow/alsoAllow 互斥）")
sys.exit(1 if bad else 0)
PY
[[ $? -ne 0 ]] && problems=$((problems+1))
echo ""

# --------------------------------------------------------------------------
# 3. 技能可用性 —— 「允许但不可用」的主要来源
# --------------------------------------------------------------------------
log_step "技能可用性（allowed-but-broken）"
SKILLS_OUT="$(openclaw skills check 2>&1)"
# 只取 "Missing requirements:" 之后、含 "(...)" 依赖说明的行；排除 Tip/空行
if MISSING="$(printf '%s\n' "$SKILLS_OUT" \
        | sed -n '/^Missing requirements:/,$p' \
        | grep -E '\((anyBins|bins|env|config):' )"; then
    COUNT="$(printf '%s\n' "$MISSING" | grep -c . )"
    log_warn "$COUNT 个技能允许但缺依赖（静默失败风险）"
    printf '%s\n' "$MISSING" | sed 's/^/    /' | head -15
    echo "    修复: openclaw doctor --fix  (禁用不可用技能，减少误调用)"
    problems=$((problems+1))
else
    log_ok "所有允许的技能均可用"
fi
echo ""

# --------------------------------------------------------------------------
# 4. memory_search 真实状态 ★ 静默降级重点
# --------------------------------------------------------------------------
log_step "memory_search 真实能力（静默降级检查）"
python3 - <<'PY'
import json, os, sqlite3, subprocess, sys

# memory.search.provider 配置
r = subprocess.run(["openclaw","config","get","memory.search"],
                   capture_output=True, text=True)
if r.returncode != 0 or "not found" in (r.stdout + r.stderr):
    prov = "openai (默认)"
else:
    try:
        prov = (json.loads(r.stdout) or {}).get("provider", "openai (默认)")
    except Exception:
        prov = "openai (默认)"
print(f"  配置 provider: {prov}")

# 判断该 provider 的凭据是否存在
degraded, reason = False, ""
if "openai" in str(prov):
    if os.environ.get("OPENAI_API_KEY"):
        print("  ✅ OPENAI_API_KEY 已设置")
    else:
        r2 = subprocess.run(["openclaw","config","get","models.providers.openai.apiKey"],
                            capture_output=True, text=True)
        has = r2.returncode == 0 and r2.stdout.strip() not in ("", "null")
        if has:
            print("  ✅ models.providers.openai.apiKey 已配置")
        else:
            degraded = True
            reason = "OPENAI_API_KEY 与 models.providers.openai.apiKey 均未配置"
elif prov == "local":
    # 实测校验：插件已装 + 模型文件存在且完整 + 未误设 modelPath
    import subprocess as sp, os
    ok = True
    pl = sp.run(["openclaw","plugins","list"], capture_output=True, text=True).stdout
    if "llama" in pl.lower():
        print("  ✅ llama-cpp provider 插件已加载")
    else:
        print("  ❌ llama-cpp provider 插件未加载 —— provider=local 会失败"); ok = False

    # 插件按此固定文件名在缓存目录查找（见 dist/index.js L26）
    EXPECT = os.path.expanduser("~/.node-llama-cpp/models/hf_ggml-org_embeddinggemma-300m-qat-Q8_0.gguf")
    if os.path.exists(EXPECT):
        sz = os.path.getsize(EXPECT)
        with open(EXPECT, "rb") as f:
            magic = f.read(4)
        if magic == b"GGUF":
            print(f"  ✅ 模型存在且有效 ({sz/1048576:.0f} MB, GGUF magic OK)")
        else:
            print(f"  ❌ 模型文件损坏（magic={magic!r}，应为 GGUF）"); ok = False
    else:
        print(f"  ❌ 模型缺失: {EXPECT}")
        print("     HuggingFace 在本网络不可达，用镜像下载（文件名必须一致）:")
        print("     curl -L -o hf_ggml-org_embeddinggemma-300m-qat-Q8_0.gguf \\")
        print("       https://hf-mirror.com/ggml-org/embeddinggemma-300m-qat-q8_0-GGUF/resolve/main/embeddinggemma-300m-qat-Q8_0.gguf")
        ok = False

    # modelPath 绝对路径会导致索引身份与 gateway 永久不匹配（ADR-009 §7.1 坑 2）
    r3 = sp.run(["openclaw","config","get","memory.search.local.modelPath"],
                capture_output=True, text=True)
    mp = r3.stdout.strip().strip('"')
    if r3.returncode == 0 and mp and mp != "null" and "not found" not in (r3.stdout+r3.stderr):
        print(f"  ⚠️  已设 local.modelPath={mp}")
        print("     绝对路径会造成索引身份与 gateway 不匹配（ADR-009 §7.1 坑 2）")
        print("     修复: openclaw config unset memory.search.local.modelPath && openclaw memory index --force")
        ok = False
    else:
        print("  ✅ 未设 modelPath（用默认 hf: 标识，索引身份一致）")

    if not ok:
        sys.exit(1)
    sys.exit(0)

if degraded:
    print(f"  ❌ 语义检索不可用 → 静默降级为 keyword-only")
    print(f"     原因: {reason}")
    print(f"     影响: 系统指令强制要求先 memory_search，但它不报错，只是召回变差")
    print(f"           中文同义表述召回尤其受损")
    print(f"     修复选项（见 DESIGN.md 问题 B）:")
    print(f"       1. 本地 GGUF（零 API 成本，推荐）:")
    print(f"          openclaw plugins install @openclaw/llama-cpp-provider")
    print(f"          + memory.search.provider=local")
    print(f"       2. 配置 OPENAI_API_KEY")
    print(f"       3. 显式接受关键词模式（记录降级，不假装有语义检索）")
    sys.exit(1)
sys.exit(0)
PY
[[ $? -ne 0 ]] && problems=$((problems+1))
echo ""

# --------------------------------------------------------------------------
# 5. 媒体工具 provider
# --------------------------------------------------------------------------
log_step "媒体工具 provider"
if openclaw config get agents.defaults.mediaModels >/dev/null 2>&1; then
    log_ok "mediaModels 已配置"
else
    echo "    · mediaModels 未配置 → image_generate/music_generate/video_generate"
    echo "      在 coding profile 内但不会出现（官方预期行为，非故障）"
    log_ok "无需处理（当前无媒体生成需求）"
fi
echo ""

# --------------------------------------------------------------------------
# 6. plugin 工具解锁状态
# --------------------------------------------------------------------------
log_step "plugin 工具解锁状态"
python3 - "$TOOLS_TMP" <<'PY'
import json, sys
try:
    t = json.load(open(sys.argv[1])) or {}
except Exception:
    t = {}
also = t.get("alsoAllow") or []
if also:
    print(f"  alsoAllow 已解锁 {len(also)} 项: {', '.join(also)}")
else:
    print("  alsoAllow 为空")
print("  提示: plugin 工具在 coding profile 下可能默认 deny（EXP-20260821-001）")
print("        新增 plugin 后用 openclaw plugins inspect <id> 确认，勿假设自动可用")
PY
echo ""

# --------------------------------------------------------------------------
echo "════════════════════════════════════════════"
if [[ $problems -eq 0 ]]; then
    log_ok "工具策略审计通过"
    exit 0
fi
log_warn "发现 $problems 类问题（详见 docs/architecture/components/tool-policy/DESIGN.md）"
echo ""
echo "关键区分:"
echo "  denied              = 策略拒绝，明确失败（低危）"
echo "  allowed-but-broken  = 策略允许但缺依赖，静默失败（高危）★"
echo "  allowed-and-working = 真实可用"
exit 1
