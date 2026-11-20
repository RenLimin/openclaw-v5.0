#!/usr/bin/env python3
"""GitHub 凭据链路同步与自检。

背景（事故 2026-11-19 / 2026-11-20）：
  GitHub 凭据曾同时存在三条互不覆盖的链路 —— keychain（go-keyring-base64 包装格式，
  直接当 token 用会 401）、repo-local git credential helper（换 clone/worktree 即失效）、
  环境变量 GH_TOKEN（Gateway 进程环境里没有）。且**无任何自检**，导致新会话里
  `gh auth status` 失败 → agent 反复尝试 `gh auth login`（交互，必卡）或回退解包
  keychain → 反复要求重新登录。

单一事实来源（SSOT）：`~/.openclaw/secrets/github.token`（chmod 600，无尾换行）
派生目标：`~/.config/gh/hosts.yml`（gh CLI 读取，chmod 600）

用法:
    python3 github_credential_sync.py            # 同步 + 自检（幂等，无副作用风险）
    python3 github_credential_sync.py --check    # 只自检，不写任何文件
    python3 github_credential_sync.py --stdout   # 打印报告

退出码: 0 = 链路健康; 1 = 异常（修复命令见输出）

设计约束:
  - 永不打印 token 原文（只输出长度 / 前缀 / SHA-8）
  - 权限不符即拒绝同步（不复制一个权限过宽的 token）
  - gh 二进制用绝对路径兜底（PATH 缺失时仍可自检）
  - 失败可见：任何一步失败都显式输出，不静默降级
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

SECRETS_DIR = Path.home() / ".openclaw" / "secrets"
TOKEN_FILE = SECRETS_DIR / "github.token"
GH_CONFIG_DIR = Path.home() / ".config" / "gh"
HOSTS_FILE = GH_CONFIG_DIR / "hosts.yml"

# PATH 缺失时兜底（对齐 gen_asset_inventory.py 的 _resolve_bin 约定）
_GH_CANDIDATES = (
    Path("/opt/homebrew/bin/gh"),
    Path("/usr/local/bin/gh"),
    Path("/usr/bin/gh"),
)


def _resolve_gh() -> str | None:
    """解析 gh 可执行绝对路径（禁止裸命令名依赖 PATH）。"""
    found = shutil.which("gh")
    if found:
        return found
    for cand in _GH_CANDIDATES:
        if cand.is_file() and os.access(cand, os.X_OK):
            return str(cand)
    return None


def _perms(path: Path) -> str:
    try:
        return oct(path.stat().st_mode & 0o777)[2:]
    except OSError:
        return "?"


def _sha8(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]


def load_token() -> tuple[str | None, str]:
    """读取 SSOT token。返回 (token, error)。"""
    if not TOKEN_FILE.is_file():
        return None, f"token 文件不存在: {TOKEN_FILE}"
    perms = _perms(TOKEN_FILE)
    if perms != "600":
        return None, f"token 权限为 {perms}，期望 600（拒绝同步）"
    token = TOKEN_FILE.read_text(encoding="utf-8").strip()
    if not token:
        return None, "token 文件为空"
    return token, ""


def existing_login() -> str | None:
    """从现有 hosts.yml 读 user 字段（不读 token）。"""
    if not HOSTS_FILE.is_file():
        return None
    try:
        for line in HOSTS_FILE.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("user:"):
                return stripped.split(":", 1)[1].strip()
    except OSError:
        pass
    return None


def sync_hosts(token: str, login: str | None) -> str:
    """把 token 写入 ~/.config/gh/hosts.yml（chmod 600）。返回状态描述。"""
    GH_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    GH_CONFIG_DIR.chmod(0o700)
    user_line = f"    user: {login}\n" if login else ""
    content = (
        "github.com:\n"
        f"    oauth_token: {token}\n"
        f"{user_line}"
        "    git_protocol: https\n"
    )
    HOSTS_FILE.write_text(content, encoding="utf-8")
    HOSTS_FILE.chmod(0o600)
    return f"已写入 {HOSTS_FILE}（perms {_perms(HOSTS_FILE)}, token sha8={_sha8(token)}）"


def check_gh_cli() -> tuple[bool, str]:
    """本地自检：gh auth status（不依赖网络）。"""
    gh = _resolve_gh()
    if not gh:
        return False, "gh 二进制未找到（检查 /opt/homebrew/bin/gh）"
    try:
        proc = subprocess.run(
            [gh, "auth", "status"],
            capture_output=True, text=True, timeout=20,
        )
    except subprocess.TimeoutExpired:
        return False, "gh auth status 超时"
    out = (proc.stdout + proc.stderr).strip()
    return proc.returncode == 0, out


def verify_token() -> tuple[bool, str]:
    """联网校验 token 真实可用（gh api user）。"""
    gh = _resolve_gh()
    if not gh:
        return False, "gh 二进制未找到"
    try:
        proc = subprocess.run(
            [gh, "api", "user", "--jq", ".login"],
            capture_output=True, text=True, timeout=30,
        )
    except subprocess.TimeoutExpired:
        return False, "gh api user 超时（网络问题，不代表 token 失效）"
    if proc.returncode == 0:
        return True, proc.stdout.strip()
    return False, (proc.stderr or proc.stdout).strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="GitHub 凭据链路同步与自检")
    parser.add_argument("--check", action="store_true", help="只自检，不写文件")
    parser.add_argument("--stdout", action="store_true", help="打印报告")
    parser.add_argument("--login", default=None, help="hosts.yml 的 user 字段（默认读现有配置）")
    args = parser.parse_args(argv)

    token, err = load_token()
    if not token:
        print(f"❌ GitHub 凭据链路异常：{err}")
        print("   修复：把 token 写入 ~/.openclaw/secrets/github.token（chmod 600，无尾换行）")
        return 1

    print(f"✅ SSOT token 就位（{TOKEN_FILE}, perms {_perms(TOKEN_FILE)}, "
          f"len={len(token)}, sha8={_sha8(token)}）")

    login = args.login or existing_login()
    if not args.check:
        print(f"✅ {sync_hosts(token, login)}")
    else:
        print(f"ℹ️  --check 模式，未写 hosts.yml")

    ok_local, out_local = check_gh_cli()
    if ok_local:
        print("✅ gh CLI 登录态正常")
    else:
        print(f"❌ gh CLI 登录态异常：\n{out_local}")
        print("   修复：python3 L2-infra/components/credentials/github_credential_sync.py")

    ok_api, out_api = verify_token()
    if ok_api:
        print(f"✅ token 实测可用（github.com/{out_api}）")
    else:
        print(f"⚠️  token 联网校验未通过：{out_api}")

    if not ok_local:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
