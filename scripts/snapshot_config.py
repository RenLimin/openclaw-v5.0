#!/usr/bin/env python3
"""把 ~/.openclaw/openclaw.json 脱敏后快照到 config-snapshots/，纳入版本控制。

动机: 配置文件不在 workspace git 内 → 变更无 diff、无回滚点、多轮操作会静默互相覆盖。
      2026-08-21 事故: agents.defaults.compaction.model 被后续操作覆盖丢失。
约定: docs/conventions/commit-and-config.md

用法:
    python3 scripts/snapshot_config.py            # 写入快照
    python3 scripts/snapshot_config.py --check    # 有未快照变更时退出码 1（供 hook 用）
    python3 scripts/snapshot_config.py --diff     # 显示当前配置 vs 上次快照

脱敏: 任何 key 名含 apiKey/token/secret/password/credential 的字段，值替换为 <REDACTED>。
      凭据本体仍只存在 ~/.openclaw/secrets/（600），绝不入库。
"""

from __future__ import annotations

import difflib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

CONFIG = Path.home() / ".openclaw" / "openclaw.json"
REPO = Path(__file__).resolve().parent.parent
SNAPSHOT = REPO / "config-snapshots" / "openclaw.json"

# 精确字段名匹配（小写、去下划线/连字符后）→ 值脱敏。
# 不用子串匹配：'maxTokens'/'keepRecentTokens' 含 'token' 但必须保留原值才能 diff。
SECRET_KEYS = {
    "apikey",
    "token",
    "accesstoken",
    "refreshtoken",
    "authtoken",
    "secret",
    "clientsecret",
    "password",
    "passwd",
    "credential",
    "credentials",
    "privatekey",
    "bearer",
    # 租户/实例绑定标识 — 本身非密钥，但会暴露归属，公开仓库不应出现。
    # 触发案例: 2026-08-22 WeCom channel 的 botId 进入公开仓库快照（ADR-007 §5 预判的风险）
    "botid",
    "corpid",
    "agentid",
    "appid",
    "clientid",
    "tenantid",
    "webhookurl",
    "chatid",
    "channelsecret",
    "signingsecret",
    "verificationtoken",
    "corpsecret",       # WeCom Agent mode
    "appsecret",
    "botsecret",
    "encodingaeskey",   # 企业微信回调加密
    "egressproxyurl",   # 可能含内网地址/认证信息
    "proxyurl",

    # 成员/会话归属标识（公开仓库需脱敏；ownerAllowFrom 由 pairing approve 自动写入）
    "ownerallowfrom",
    "allowfrom",
    "groupallowfrom",
    "userid",
    "openid",
    "toparty",
    "totag",
    "touser",
}
# 这些字段名即使命中上面的规则也**保留**原值（非敏感的容量/策略参数）
KEEP_KEYS = {"maxtokens", "keeprecenttokens", "maxtokensfield", "tokenbudget", "maxoutputtokens"}
REDACTED = "<REDACTED>"

# ── 第二道防线：值形态兜底 ──────────────────────────────────────────────
# 背景：2026-08-23 review 实测发现纯 key 名精确匹配漏 6/7。
# 漏网典型：env.GROQ_API_KEY（前缀命名）、mcpServers.args[] 里的 --key、
# baseUrl 里的 user:pass@、gateway.auth.headers.Authorization。
# 仓库为 public，一次「加个 MCP server」即可让凭据公开 → 必须有值形态兜底。
#
# 设计原则：key 名匹配（第一道）与值形态匹配（第二道）**并行**，任一命中即脱敏；
# 但 SecretRef 间接引用与已脱敏占位符必须放行，否则破坏快照可 diff 性。

# key 名**后缀/子串**匹配（补精确集合的漏）——先减 KEEP_KEYS 再判
SECRET_KEY_SUFFIXES = (
    "apikey", "secret", "token", "password", "passwd",
    "credential", "privatekey", "aeskey",
)

# 已是间接引用/占位符 → 放行（不是明文，脱了反而丢结构信息）
REF_MARKERS = (
    "${", "secretref", "file://", "op://", "env:", "vault:",
    "<redacted>", "__openclaw_redacted__", "secretref-managed",
)

# 明文凭据的形态特征（命中即脱，无论 key 名）
PLAIN_MARKERS = (
    "sk-", "sk_", "gsk_", "ghp_", "gho_", "github_pat_", "tvly-",
    "xoxb-", "xoxp-", "xapp-", "bearer ", "eyj",  # eyJ = JWT header
    "aki", "asia",  # 云厂商 AK 前缀（小写比对）
)

_URL_USERINFO = re.compile(r"^[a-z][a-z0-9+.-]*://[^/@\s]*:[^/@\s]+@", re.I)
_LONG_OPAQUE = re.compile(r"^[A-Za-z0-9_\-]{32,}$")
_HEXISH = re.compile(r"^[0-9a-f]{32,}$", re.I)


def _norm(key: str) -> str:
    return key.lower().replace("_", "").replace("-", "")


def is_secret_key(key: str) -> bool:
    k = _norm(key)
    if k in KEEP_KEYS:
        return False
    if k in SECRET_KEYS:
        return True
    # 后缀/子串兜底：覆盖 GROQ_API_KEY / MY_API_KEY / xxxClientSecret 等
    return any(k.endswith(sfx) or sfx in k for sfx in SECRET_KEY_SUFFIXES)


def looks_like_secret_value(val: Any) -> bool:
    """值形态兜底：无论 key 名如何，明文凭据形态即脱敏。

    放行间接引用与占位符，避免破坏 SecretRef 结构与快照 diff 能力。
    """
    if not isinstance(val, str):
        return False
    s = val.strip()
    if len(s) < 16:
        return False
    low = s.lower()
    # 已是引用/占位符 → 不是明文，放行
    if any(m in low for m in REF_MARKERS):
        return False
    # URL 里带 user:pass@
    if _URL_USERINFO.search(s):
        return True
    # 已知凭据前缀
    if any(low.startswith(m) or (" " in m and m in low) for m in PLAIN_MARKERS):
        return True
    # 纯 hex 长串（常见于 token/hash）
    if _HEXISH.match(s):
        return True
    # 长 opaque 串：必须同时含大小写或数字，且不含空格/斜杠/点（排除路径、句子、URL、版本号）
    if _LONG_OPAQUE.match(s):
        has_digit = any(c.isdigit() for c in s)
        has_alpha = any(c.isalpha() for c in s)
        return has_digit and has_alpha
    return False


def redact(obj: Any) -> Any:
    """递归脱敏。保留结构与非敏感值，敏感值替换为 <REDACTED>。"""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if is_secret_key(k):
                # 敏感键：标量直接脱敏；列表逐元素脱敏（如
                # ownerAllowFrom: ["wecom:1313"] 含成员归属标识）；
                # dict 仍递归，避免脱掉整个子树结构。
                if isinstance(v, list):
                    out[k] = [
                        REDACTED if isinstance(e, (str, int, float)) and e not in (None, "") else redact(e)
                        for e in v
                    ]
                elif isinstance(v, dict):
                    out[k] = redact(v)
                else:
                    out[k] = REDACTED if v not in (None, "") else v
            elif looks_like_secret_value(v):
                # 第二道防线：key 名不敏感，但值是明文凭据形态
                out[k] = REDACTED
            else:
                out[k] = redact(v)
        return out
    if isinstance(obj, list):
        # 列表元素也走值形态兜底（mcpServers.args 里的 --key <secret>）
        return [REDACTED if looks_like_secret_value(v) else redact(v) for v in obj]
    return obj


def render(data: Any) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False, sort_keys=False) + "\n"


def load_current() -> str:
    if not CONFIG.exists():
        sys.exit(f"配置文件不存在: {CONFIG}")
    with CONFIG.open(encoding="utf-8") as f:
        return render(redact(json.load(f)))


def main() -> int:
    args = set(sys.argv[1:])
    current = load_current()
    previous = SNAPSHOT.read_text(encoding="utf-8") if SNAPSHOT.exists() else ""

    if "--diff" in args:
        if current == previous:
            print("✅ 配置与上次快照一致")
            return 0
        diff = difflib.unified_diff(
            previous.splitlines(keepends=True),
            current.splitlines(keepends=True),
            fromfile="config-snapshots/openclaw.json (上次快照)",
            tofile="~/.openclaw/openclaw.json (当前, 已脱敏)",
        )
        sys.stdout.writelines(diff)
        return 1

    if "--check" in args:
        if current == previous:
            print("✅ 配置快照是最新的")
            return 0
        print("⚠️  配置有未快照的变更，运行: python3 scripts/snapshot_config.py")
        return 1

    if current == previous:
        print("✅ 配置快照已是最新，无需更新")
        return 0

    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT.write_text(current, encoding="utf-8")
    rel = SNAPSHOT.relative_to(REPO)
    action = "创建" if not previous else "更新"
    print(f"✅ 已{action}配置快照: {rel}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
