#!/usr/bin/env bash
# Step 05: 快照入库
# 首装成功后打快照（配置 + 凭据索引 + 适配层版本），存 ~/.openclaw/snapshots/l0-install/

set -euo pipefail

L0_ROOT="$1"
RUNTIME="$2"
ENV_REPORT="$3"
VERIFY_REPORT="$4"
DRY_RUN="$5"

SNAPSHOT_DIR="${HOME}/.openclaw/snapshots/l0-install"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
SNAP_NAME="final-${RUNTIME}-${TIMESTAMP}"
SNAP_PATH="${SNAPSHOT_DIR}/${SNAP_NAME}"

echo "创建安装完成快照..."
echo "快照目录: ${SNAP_PATH}"

if [ "$DRY_RUN" = "true" ]; then
    echo "[dry-run] would create snapshot at ${SNAP_PATH}"
    exit 0
fi

mkdir -p "$SNAP_PATH"

# 1. 配置快照（脱敏）
if command -v openclaw &>/dev/null; then
    echo "  - 保存配置快照..."
    openclaw config get --all > "$SNAP_PATH/config.json" 2>/dev/null || true
    
    # 脱敏：替换敏感字段值（仅保留 key，value 替换为 ***）
    # （openclaw config get 对 SecretRef 已经会 redact，这里做双重保险）
    if [ -f "$SNAP_PATH/config.json" ]; then
        python3 -c "
import json, re, sys
with open('$SNAP_PATH/config.json') as f:
    data = f.read()
# 简单脱敏：匹配常见敏感 key
sensitive_keys = ['apiKey', 'api_key', 'token', 'secret', 'password', 'privateKey']
for key in sensitive_keys:
    data = re.sub(r'\"' + key + r'\"\\s*:\\s*\"[^\"]*\"', '\"' + key + '\": \"***\"', data)
with open('$SNAP_PATH/config.json', 'w') as f:
    f.write(data)
print('  配置快照已脱敏')
" 2>/dev/null || true
    fi
fi

# 2. 凭据索引（不含值，仅元信息）
if [ -d "${HOME}/.openclaw/secrets" ]; then
    echo "  - 保存凭据索引..."
    ls -la "${HOME}/.openclaw/secrets/" > "$SNAP_PATH/credential-index.txt" 2>/dev/null || true
    # 只记录文件名和大小，不记录内容
    find "${HOME}/.openclaw/secrets" -type f -exec stat -f "%N %z %p" {} \; > "$SNAP_PATH/credential-file-list.txt" 2>/dev/null || true
fi

# 3. 适配层版本
echo "  - 保存适配层版本..."
ADAPTER_DIR="${L0_ROOT}/../L1-runtime/adapters/${RUNTIME}"
if [ -d "$ADAPTER_DIR" ]; then
    # 记录适配层文件列表和大小
    find "$ADAPTER_DIR" -type f -name "*.py" -exec stat -f "%N %z" {} \; > "$SNAP_PATH/adapter-file-list.txt" 2>/dev/null || true
fi

# 4. 环境报告副本
if [ -f "$ENV_REPORT" ]; then
    cp "$ENV_REPORT" "$SNAP_PATH/env-report.json"
fi

# 5. 验证报告副本
if [ -f "$VERIFY_REPORT" ]; then
    cp "$VERIFY_REPORT" "$SNAP_PATH/verify-report.json"
fi

# 6. 快照 manifest
cat > "$SNAP_PATH/manifest.json" <<MEOF
{
  "type": "l0-install-final",
  "runtime": "${RUNTIME}",
  "timestamp": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "l0_version": "1.0",
  "snapshot_path": "${SNAP_PATH}"
}
MEOF

# 清理超过 5 份的旧 final 快照
# shellcheck disable=SC2012
ls -1dt "${SNAPSHOT_DIR}"/final-* 2>/dev/null | tail -n +6 | xargs -r rm -rf

echo ""
echo "✅ 快照已保存: ${SNAP_PATH}"
echo "   包含: 配置快照 + 凭据索引 + 适配层清单 + 环境/验证报告"
exit 0
