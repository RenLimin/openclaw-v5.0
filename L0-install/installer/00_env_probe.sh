#!/usr/bin/env bash
# Step 00: 环境检测
# 检测 OS/arch/CPU/内存/磁盘/网络/Node/Python/权限
# 输出: env-report.json

set -euo pipefail

L0_ROOT="$1"
RUNTIME="$2"
ENV_REPORT="$3"
VERIFY_REPORT="$4"
DRY_RUN="$5"

# 收集信息
OS_TYPE=$(uname -s)
OS_ARCH=$(uname -m)
OS_KERNEL=$(uname -r)

# macOS 版本
if [ "$OS_TYPE" = "Darwin" ]; then
    OS_VERSION=$(sw_vers -productVersion 2>/dev/null || echo "unknown")
    OS_NAME="macOS"
else
    OS_VERSION=$(cat /etc/os-release 2>/dev/null | grep -E '^VERSION=' | cut -d= -f2 | tr -d '"' || echo "unknown")
    OS_NAME=$(cat /etc/os-release 2>/dev/null | grep -E '^NAME=' | cut -d= -f2 | tr -d '"' || echo "Linux")
fi

# CPU
CPU_CORES=$(sysctl -n hw.ncpu 2>/dev/null || nproc 2>/dev/null || echo "unknown")
CPU_MODEL=$(sysctl -n machdep.cpu.brand_string 2>/dev/null || grep -m1 'model name' /proc/cpuinfo 2>/dev/null | cut -d: -f2 | xargs || echo "unknown")

# 内存
TOTAL_MEM_MB=$(sysctl -n hw.memsize 2>/dev/null | awk '{print int($1/1024/1024)}' || free -m 2>/dev/null | awk '/^Mem:/{print $2}' || echo "unknown")

# 磁盘（当前目录所在磁盘）
DISK_FREE_KB=$(df -k . 2>/dev/null | awk 'NR==2 {print $4}' || echo "unknown")
DISK_TOTAL_KB=$(df -k . 2>/dev/null | awk 'NR==2 {print $2}' || echo "unknown")

# 网络（检测能否访问常用域名）
NETWORK_OK="false"
if curl -s --connect-timeout 3 https://registry.npmjs.org >/dev/null 2>&1; then
    NETWORK_OK="true"
fi

# Node.js
NODE_VERSION=$(node --version 2>/dev/null || echo "not_installed")
NPM_VERSION=$(npm --version 2>/dev/null || echo "not_installed")

# Python
PYTHON_VERSION=$(python3 --version 2>/dev/null | cut -d' ' -f2 || echo "not_installed")
PIP_VERSION=$(pip3 --version 2>/dev/null | cut -d' ' -f2 || echo "not_installed")

# Git
GIT_VERSION=$(git --version 2>/dev/null | cut -d' ' -f3 || echo "not_installed")

# Docker
DOCKER_VERSION=$(docker --version 2>/dev/null | cut -d' ' -f3 | tr -d ',' || echo "not_installed")

# 当前用户权限
CURRENT_USER=$(whoami)
IS_SUDO="false"
if sudo -n true 2>/dev/null; then
    IS_SUDO="true"
fi

# 生成 JSON 报告
cat > "$ENV_REPORT" <<JSON
{
  "timestamp": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "os": {
    "type": "${OS_TYPE}",
    "name": "${OS_NAME}",
    "version": "${OS_VERSION}",
    "arch": "${OS_ARCH}",
    "kernel": "${OS_KERNEL}"
  },
  "cpu": {
    "cores": ${CPU_CORES},
    "model": "${CPU_MODEL}"
  },
  "memory": {
    "total_mb": ${TOTAL_MEM_MB}
  },
  "disk": {
    "free_kb": ${DISK_FREE_KB},
    "total_kb": ${DISK_TOTAL_KB}
  },
  "network": {
    "npm_registry_reachable": ${NETWORK_OK}
  },
  "runtimes": {
    "node": {
      "version": "${NODE_VERSION}",
      "satisfies_min": $(if [ "$NODE_VERSION" != "not_installed" ] && [[ "$NODE_VERSION" =~ ^v([0-9]+)\. ]]; then major="${BASH_REMATCH[1]}"; [ "$major" -ge 20 ] && echo "true" || echo "false"; else echo "false"; fi)
    },
    "npm": {
      "version": "${NPM_VERSION}"
    },
    "python": {
      "version": "${PYTHON_VERSION}",
      "satisfies_min": $(if [ "$PYTHON_VERSION" != "not_installed" ] && [[ "$PYTHON_VERSION" =~ ^([0-9]+)\.([0-9]+) ]]; then major="${BASH_REMATCH[1]}"; minor="${BASH_REMATCH[2]}"; [ "$major" -gt 3 ] || ([ "$major" -eq 3 ] && [ "$minor" -ge 10 ]) && echo "true" || echo "false"; else echo "false"; fi)
    },
    "pip": {
      "version": "${PIP_VERSION}"
    },
    "git": {
      "version": "${GIT_VERSION}"
    },
    "docker": {
      "version": "${DOCKER_VERSION}"
    }
  },
  "permissions": {
    "current_user": "${CURRENT_USER}",
    "sudo": ${IS_SUDO}
  },
  "l0_version": "1.0"
}
JSON

echo "环境检测完成 → ${ENV_REPORT}"

# 关键检查：Node >= 20
if [[ "$NODE_VERSION" =~ ^v([0-9]+)\. ]]; then
    major="${BASH_REMATCH[1]}"
    if [ "$major" -lt 20 ]; then
        echo "⚠️  Node.js 版本 ${NODE_VERSION} 低于最低要求 20.x"
        echo "   请升级 Node.js 后重试"
        exit 1
    fi
else
    echo "⚠️  Node.js 未安装"
    echo "   请先安装 Node.js >= 20"
    exit 1
fi

echo "✅ 环境检测通过"
