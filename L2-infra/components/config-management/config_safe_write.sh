#!/usr/bin/env bash
# scripts/config_safe_write.sh — 统一安全写入通道
#
# 目的：所有自定义资产对 openclaw.json 的写入必须经过此脚本，
#       禁止直接调用 `openclaw config patch/set`（adapter.py 除外，其内部已实现同等保护）。
#
# 保护机制（基于 EXP-009/010/011 教训）：
#   1. 写入前自动保存回退点（带时间戳）
#   2. dry-run 预检
#   3. 写入 + validate
#   4. 深层读回验证
#   5. 失败自动回退
#
# 用法：
#   bash scripts/config_safe_write.sh '<json-patch>'
#   bash scripts/config_safe_write.sh --file patch.json5
#
# 示例：
#   bash scripts/config_safe_write.sh '{"agents":{"defaults":{"heartbeat":{"every":"30m"}}}}'

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1m'; BLUE='\033[0;34m'; NC='\033[0m'
log_ok()   { echo -e "${GREEN}✅${NC} $*"; }
log_err()  { echo -e "${RED}❌${NC} $*"; }
log_step() { echo -e "${BLUE}▶${NC} $*"; }
log_warn() { echo -e "${YELLOW}⚠️${NC} $*"; }

CONFIG="$HOME/.openclaw/openclaw.json"
BACKUP_DIR="$HOME/.openclaw/backups/config-safe-write"
mkdir -p "$BACKUP_DIR"

# ─── 解析输入 ───
PATCH_JSON=""
if [[ "${1:-}" == "--file" ]]; then
    [[ -f "${2:-}" ]] || { log_err "文件不存在: $2"; exit 1; }
    PATCH_JSON=$(cat "$2")
elif [[ -n "${1:-}" ]]; then
    PATCH_JSON="$1"
else
    log_err "用法: $0 '<json-patch>' 或 $0 --file patch.json"
    exit 1
fi

# ─── Step 1: 保存回退点 ───
log_step "[1/5] 保存回退点..."
TS=$(date +%Y%m%d%H%M%S)
ROLLBACK_FILE="$BACKUP_DIR/pre_write_${TS}.json"
cp "$CONFIG" "$ROLLBACK_FILE"
log_ok "  回退点: $ROLLBACK_FILE"

# ─── Step 2: dry-run ───
log_step "[2/5] dry-run 验证..."
if ! echo "$PATCH_JSON" | openclaw config patch --stdin --dry-run 2>&1; then
    log_err "  dry-run 失败，已中止（未做任何改动）"
    exit 1
fi
log_ok "  dry-run 通过"

# ─── Step 3: 写入 ───
log_step "[3/5] 写入配置..."
echo "$PATCH_JSON" | openclaw config patch --stdin
log_ok "  写入完成"

# ─── Step 4: validate ───
log_step "[4/5] 配置校验..."
if ! openclaw config validate 2>&1; then
    log_err "  校验失败！自动回退中..."
    cp "$ROLLBACK_FILE" "$CONFIG"
    log_ok "  已回退到: $ROLLBACK_FILE"
    exit 1
fi
log_ok "  校验通过"

# ─── Step 5: 读回确认 ───
log_step "[5/5] 读回确认..."
VERIFY_RESULT=$(python3 -c "
import json, subprocess, sys
patch = json.loads('''$PATCH_JSON''')
def extract_paths(obj, prefix=''):
    paths = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            full = f'{prefix}.{k}' if prefix else k
            paths.extend(extract_paths(v, full))
    elif prefix:
        paths.append(prefix)
    return paths
paths = extract_paths(patch)
ok = fail = 0
for p in paths[:20]:
    r = subprocess.run(['openclaw', 'config', 'get', p], capture_output=True, text=True)
    if r.returncode == 0:
        ok += 1
        print(f'  ✅ {p}')
    else:
        fail += 1
        print(f'  ❌ {p}')
print(f'\n  结果: {ok} ✅ / {fail} ❌')
sys.exit(1 if fail > 0 else 0)
" 2>&1)
echo "$VERIFY_RESULT"
if [[ $? -ne 0 ]]; then
    log_err "  读回验证失败！自动回退中..."
    cp "$ROLLBACK_FILE" "$CONFIG"
    log_ok "  已回退到: $ROLLBACK_FILE"
    exit 1
fi

echo ""
echo "════════════════════════════════════════════"
log_ok "安全写入完成"
log_warn "回退命令: cp $ROLLBACK_FILE $CONFIG && openclaw gateway restart"
echo "════════════════════════════════════════════"
