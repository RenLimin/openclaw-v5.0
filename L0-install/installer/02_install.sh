#!/usr/bin/env bash
# Step 02: 运行时安装
# 根据 registry 的 install_command 安装运行时 + 依赖校验

set -euo pipefail

L0_ROOT="$1"
RUNTIME="$2"
ENV_REPORT="$3"
VERIFY_REPORT="$4"
DRY_RUN="$5"

REGISTRY_FILE="${L0_ROOT}/registry/${RUNTIME}.yaml"

echo "安装运行时: ${RUNTIME}"
echo "注册表文件: ${REGISTRY_FILE}"

if [ ! -f "$REGISTRY_FILE" ]; then
    echo "❌ 注册表文件不存在: ${REGISTRY_FILE}"
    exit 1
fi

# 从 registry 解析安装命令（简单 grep 解析）
INSTALL_CMD=$(grep -E '^  install_command:' "$REGISTRY_FILE" | cut -d: -f2- | xargs)
INSTALL_METHOD=$(grep -E '^  install_method:' "$REGISTRY_FILE" | cut -d: -f2 | xargs)

if [ -z "$INSTALL_CMD" ]; then
    echo "❌ 未找到 install_command"
    exit 1
fi

echo "安装方式: ${INSTALL_METHOD}"
echo "安装命令: ${INSTALL_CMD}"

# dry-run 模式
if [ "$DRY_RUN" = "true" ]; then
    echo "[dry-run] would execute: ${INSTALL_CMD}"
    exit 0
fi

# 检查是否已安装（如果已安装，跳过）
if [ "$RUNTIME" = "openclaw" ] && command -v openclaw &>/dev/null; then
    echo "ℹ️  OpenClaw 已安装: $(openclaw --version 2>&1)"
    echo "   跳过安装步骤"
    exit 0
fi

# 执行安装
echo ""
echo "执行安装命令..."
echo "$ ${INSTALL_CMD}"
echo ""

if eval "$INSTALL_CMD"; then
    echo ""
    echo "✅ 安装命令执行成功"
else
    echo ""
    echo "❌ 安装命令执行失败"
    echo "   请检查网络连接和权限设置"
    echo "   也可以手动安装后使用 --skip-verify 重新运行"
    exit 1
fi

# 验证安装
echo ""
echo "验证安装..."

if [ "$RUNTIME" = "openclaw" ]; then
    if command -v openclaw &>/dev/null; then
        echo "✅ openclaw 命令可用: $(openclaw --version 2>&1)"
    else
        echo "❌ openclaw 命令不可用"
        exit 1
    fi
fi

echo "✅ 运行时安装完成"
exit 0
