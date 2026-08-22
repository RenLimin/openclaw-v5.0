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
}
# 这些字段名即使命中上面的规则也**保留**原值（非敏感的容量/策略参数）
KEEP_KEYS = {"maxtokens", "keeprecenttokens", "maxtokensfield", "tokenbudget", "maxoutputtokens"}
REDACTED = "<REDACTED>"


def _norm(key: str) -> str:
    return key.lower().replace("_", "").replace("-", "")


def is_secret_key(key: str) -> bool:
    k = _norm(key)
    if k in KEEP_KEYS:
        return False
    return k in SECRET_KEYS


def redact(obj: Any) -> Any:
    """递归脱敏。保留结构与非敏感值，敏感值替换为 <REDACTED>。"""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if is_secret_key(k) and not isinstance(v, (dict, list)):
                out[k] = REDACTED if v not in (None, "") else v
            else:
                out[k] = redact(v)
        return out
    if isinstance(obj, list):
        return [redact(v) for v in obj]
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
