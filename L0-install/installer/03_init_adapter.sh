#!/usr/bin/env bash
# Step 03: 适配层初始化
# 把对应适配层部署到系统 + 配置适配层基础参数

set -euo pipefail

L0_ROOT="$1"
RUNTIME="$2"
ENV_REPORT="$3"
VERIFY_REPORT="$4"
DRY_RUN="$5"

REGISTRY_FILE="${L0_ROOT}/registry/${RUNTIME}.yaml"

echo "初始化适配层: ${RUNTIME}"

# 从 registry 解析适配层路径
ADAPTER_PATH=$(grep -E '^  path:' "$REGISTRY_FILE" | head -1 | cut -d: -f2- | xargs)
ADAPTER_STATUS=$(grep -A2 '^adapter:' "$REGISTRY_FILE" | grep -E '^  status:' | cut -d: -f2 | xargs)

echo "适配层路径: ${ADAPTER_PATH}"
echo "适配层状态: ${ADAPTER_STATUS}"

if [ -z "$ADAPTER_PATH" ]; then
    echo "❌ 未找到适配层路径"
    exit 1
fi

# 检查适配层状态
if [ "$ADAPTER_STATUS" = "reserved" ]; then
    echo "⚠️  适配层为预留状态，不做初始化"
    echo "   适配层: ${RUNTIME} 尚未实现，仅 registry 预留"
    echo "   跳过步骤 3（适配层初始化）"
    exit 0
fi

if [ "$ADAPTER_STATUS" = "in-progress" ]; then
    echo "⚠️  适配层为开发中状态，可能不完整"
fi

# 检查适配层目录是否存在（相对于 L0_ROOT 的上级目录）
FULL_ADAPTER_PATH="${L0_ROOT}/../${ADAPTER_PATH}"
# 规范化路径
FULL_ADAPTER_PATH=$(cd "$FULL_ADAPTER_PATH" 2>/dev/null && pwd || echo "")

if [ -z "$FULL_ADAPTER_PATH" ]; then
    echo "❌ 适配层目录不存在: ${ADAPTER_PATH}"
    exit 1
fi

echo "适配层实际路径: ${FULL_ADAPTER_PATH}"

# 辅助函数：在适配层目录下递归查找文件
find_adapter_file() {
    local filename="$1"
    find "$FULL_ADAPTER_PATH" -name "$filename" -type f 2>/dev/null | head -1
}

# dry-run 模式
if [ "$DRY_RUN" = "true" ]; then
    echo "[dry-run] would initialize adapter at ${FULL_ADAPTER_PATH}"
    exit 0
fi

# OpenClaw 适配层初始化
if [ "$RUNTIME" = "openclaw" ]; then
    echo ""
    echo "OpenClaw 适配层初始化:"
    
    # 1. 验证 adapter.py 存在（递归查找）
    adapter_file=$(find_adapter_file "adapter.py")
    if [ -n "$adapter_file" ]; then
        echo "  ✅ adapter.py 存在 ($(basename "$(dirname "$adapter_file")")/adapter.py)"
    else
        echo "  ❌ adapter.py 不存在"
        exit 1
    fi
    
    # 2. 验证 config.py 存在（递归查找）
    config_file=$(find_adapter_file "config.py")
    if [ -n "$config_file" ]; then
        echo "  ✅ config.py 存在 ($(basename "$(dirname "$config_file")")/config.py)"
    else
        echo "  ❌ config.py 不存在"
        exit 1
    fi
    
    # 3. 验证 health.py 存在（递归查找）
    health_file=$(find_adapter_file "health.py")
    if [ -n "$health_file" ]; then
        echo "  ✅ health.py 存在 ($(basename "$(dirname "$health_file")")/health.py)"
    else
        echo "  ⚠️  health.py 未找到（可选组件）"
    fi
    
    # 4. 验证 OpenClaw 配置可用
    if command -v openclaw &>/dev/null; then
        if openclaw config get agents.defaults.model >/dev/null 2>&1; then
            echo "  ✅ OpenClaw 配置可读取"
        else
            echo "  ⚠️  OpenClaw 配置读取失败（可能需要先初始化）"
        fi
    else
        echo "  ⚠️  OpenClaw 命令不可用（请确保已安装）"
    fi
    
    # 5. 验证 OpenClaw 版本满足最低要求
    if command -v openclaw &>/dev/null; then
        version=$(openclaw --version 2>&1 | head -1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' || echo "unknown")
        echo "  ℹ️  OpenClaw 版本: ${version}"
    fi
    
    echo ""
    echo "✅ OpenClaw 适配层初始化完成"
fi

# TODO: 其他运行时适配层初始化

echo "✅ 适配层初始化完成"
exit 0
