#!/usr/bin/env bash
# Step 01: 运行时选型
# 读取 registry，列出可选运行时，让用户选择
# 支持 --runtime 非交互模式

set -euo pipefail

L0_ROOT="$1"
RUNTIME="$2"
ENV_REPORT="$3"
VERIFY_REPORT="$4"
DRY_RUN="$5"

REGISTRY_DIR="${L0_ROOT}/registry"
SELECTED_FILE="${L0_ROOT}/.selected-runtime"

# 如果已指定 runtime，直接使用
if [ -n "$RUNTIME" ]; then
    echo "非交互模式，使用运行时: ${RUNTIME}"
    echo "$RUNTIME" > "$SELECTED_FILE"
    exit 0
fi

# 列出可选运行时
echo ""
echo "可选运行时:"
echo ""

i=0
runtimes=()
for f in "${REGISTRY_DIR}"/*.yaml; do
    if [ ! -f "$f" ]; then continue; fi
    name=$(basename "$f" .yaml)
    # 从 yaml 中读取基础信息（简单 grep 解析，不引入 yq 依赖）
    display_name=$(grep -E '^  display_name:' "$f" 2>/dev/null | cut -d: -f2 | xargs || echo "$name")
    category=$(grep -E '^  category:' "$f" 2>/dev/null | cut -d: -f2 | xargs || echo "")
    status=$(grep -A2 '^adapter:' "$f" | grep -E '^  status:' | cut -d: -f2 | xargs || echo "reserved")
    
    i=$((i + 1))
    runtimes+=("$name")
    
    # 状态标记
    status_mark="📋"
    if [ "$status" = "ready" ]; then
        status_mark="✅"
    elif [ "$status" = "in-progress" ]; then
        status_mark="🚧"
    fi
    
    printf "  %d) %s %-20s [%s] %s\n" "$i" "$status_mark" "$display_name" "$category" "$status"
done

echo ""
echo "请选择运行时 (1-$i): "
read -r choice

# 验证输入
if ! [[ "$choice" =~ ^[0-9]+$ ]] || [ "$choice" -lt 1 ] || [ "$choice" -gt "$i" ]; then
    echo "❌ 无效选择: $choice"
    exit 1
fi

selected="${runtimes[$((choice - 1))]}"
echo "选定运行时: ${selected}"
echo "$selected" > "$SELECTED_FILE"

exit 0
