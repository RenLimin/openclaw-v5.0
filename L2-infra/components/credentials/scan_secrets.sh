#!/usr/bin/env bash
# 凭据泄漏扫描 — 推送前强制检查
#
# 用法:
#   bash scripts/scan_secrets.sh              # 扫已 staged 的改动
#   bash scripts/scan_secrets.sh --range A..B # 扫指定 commit 区间
#
# 退出码: 0=干净, 1=发现疑似凭据
#
# 设计要点: 要求密钥前缀后**紧跟足够长度的实际字符**，避免文档里的
#           模式字面量（如 `ghp_` / `sk-*`）自我触发误报。
# 约定: docs/conventions/commit-and-config.md §1.5

set -uo pipefail
cd "$(git rev-parse --show-toplevel)"

RED='\033[0;31m'; GREEN='\033[0;32m'; NC='\033[0m'

MODE="staged"
RANGE=""
if [[ "${1:-}" == "--range" ]]; then
    MODE="range"; RANGE="${2:?用法: $0 --range <A..B>}"
fi

if [[ "$MODE" == "range" ]]; then
    DIFF="$(git diff "$RANGE")"
else
    DIFF="$(git diff --cached)"
fi

# 只看新增行，去掉 diff 元数据
ADDED="$(printf '%s\n' "$DIFF" | grep '^+' | grep -v '^+++')"

# 前缀后要求 >=16 位实际密钥字符 —— 文档里的 `ghp_` / `sk-*` 不会命中
PATTERNS=(
  'ark-[A-Za-z0-9_-]{16,}'
  'sk-[A-Za-z0-9_-]{16,}'
  'ghp_[A-Za-z0-9]{16,}'
  'gho_[A-Za-z0-9]{16,}'
  'github_pat_[A-Za-z0-9_]{16,}'
  'tvly-[A-Za-z0-9_-]{16,}'
  'AIza[A-Za-z0-9_-]{20,}'
  'xox[baprs]-[A-Za-z0-9-]{16,}'
  'Bearer [A-Za-z0-9._~+/-]{20,}'
  '-----BEGIN [A-Z ]*PRIVATE KEY-----'
  'aws_secret_access_key\s*=\s*[A-Za-z0-9/+=]{20,}'
  '"(apiKey|api_key|password|secret)"\s*:\s*"[^"<*][^"]{12,}"'
  # 归属标识（botId/corpId/appId 等）：非密钥但暴露租户归属，公开仓库不应出现
  '"(botId|corpId|agentId|appId|clientId|tenantId|chatId)"\s*:\s*"[^"<*][^"]{10,}"'
  # WeCom / 企业微信及同类 provider 的密钥字段
  '"(corpSecret|appSecret|botSecret|encodingAESKey|signingSecret|channelSecret)"\s*:\s*"[^"<*][^"]{8,}"'
)

hits=0
for pat in "${PATTERNS[@]}"; do
    if out="$(printf '%s\n' "$ADDED" | grep -nEi -e "$pat")"; then
        echo -e "${RED}❌ 疑似凭据${NC} (模式: $pat)"
        printf '%s\n' "$out" | sed 's/^/    /' | head -5
        hits=$((hits + 1))
    fi
done

echo ""
if [[ $hits -eq 0 ]]; then
    echo -e "${GREEN}✅ 未发现凭据泄漏${NC}"
    exit 0
fi
echo -e "${RED}发现 $hits 类疑似凭据 — 已中止${NC}"
echo "确认为误报时，用 git diff --cached 人工复核后再推送。"
exit 1
