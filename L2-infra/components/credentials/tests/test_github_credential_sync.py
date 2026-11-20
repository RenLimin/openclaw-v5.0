"""GitHub 凭据链路同步脚本测试。

覆盖：token 读取 / 权限校验 / hosts.yml 同步 / 幂等 / 失败可见。
不联网、不读真实 token 内容（用临时目录夹具）。
"""
from __future__ import annotations

import importlib.util
import os
import stat
import sys
from pathlib import Path

import pytest

COMP_DIR = Path(__file__).resolve().parent.parent
SCRIPT = COMP_DIR / "github_credential_sync.py"

spec = importlib.util.spec_from_file_location("ghsync", SCRIPT)
ghsync = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(ghsync)


@pytest.fixture()
def fake_home(tmp_path, monkeypatch):
    """把 SSOT token 与 gh 配置目录重定向到临时目录。"""
    secrets = tmp_path / "secrets"
    secrets.mkdir()
    ghdir = tmp_path / "gh"
    ghdir.mkdir()
    monkeypatch.setattr(ghsync, "SECRETS_DIR", secrets)
    monkeypatch.setattr(ghsync, "TOKEN_FILE", secrets / "github.token")
    monkeypatch.setattr(ghsync, "GH_CONFIG_DIR", ghdir)
    monkeypatch.setattr(ghsync, "HOSTS_FILE", ghdir / "hosts.yml")
    return tmp_path


def _write_token(path: Path, value: str = "gho_" + "x" * 36) -> None:
    path.write_text(value, encoding="utf-8")
    path.chmod(0o600)


def test_load_token_ok(fake_home):
    _write_token(ghsync.TOKEN_FILE)
    token, err = ghsync.load_token()
    assert err == ""
    assert token and token.startswith("gho_")


def test_load_token_missing(fake_home):
    token, err = ghsync.load_token()
    assert token is None
    assert "不存在" in err


def test_load_token_bad_perms_refused(fake_home):
    """权限过宽的 token 必须被拒绝（防止复制泄露）。"""
    _write_token(ghsync.TOKEN_FILE)
    ghsync.TOKEN_FILE.chmod(0o644)
    token, err = ghsync.load_token()
    assert token is None
    assert "600" in err


def test_sync_hosts_idempotent(fake_home):
    _write_token(ghsync.TOKEN_FILE)
    token, _ = ghsync.load_token()
    ghsync.sync_hosts(token, "RenLimin")
    first = ghsync.HOSTS_FILE.read_text()
    ghsync.sync_hosts(token, "RenLimin")
    assert ghsync.HOSTS_FILE.read_text() == first


def test_sync_hosts_permissions(fake_home):
    _write_token(ghsync.TOKEN_FILE)
    token, _ = ghsync.load_token()
    ghsync.sync_hosts(token, "RenLimin")
    assert stat.S_IMODE(ghsync.HOSTS_FILE.stat().st_mode) == 0o600
    assert stat.S_IMODE(ghsync.GH_CONFIG_DIR.stat().st_mode) == 0o700


def test_sync_hosts_contains_no_plaintext_leak(fake_home):
    """hosts.yml 只含 token，不含其他敏感字段。"""
    _write_token(ghsync.TOKEN_FILE)
    token, _ = ghsync.load_token()
    ghsync.sync_hosts(token, "RenLimin")
    body = ghsync.HOSTS_FILE.read_text()
    assert "oauth_token:" in body
    assert "git_protocol: https" in body
    assert "password" not in body


def test_existing_login_reads_user_only(fake_home):
    ghsync.GH_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    ghsync.HOSTS_FILE.write_text(
        "github.com:\n    oauth_token: gho_secret\n    user: RenLimin\n",
        encoding="utf-8",
    )
    assert ghsync.existing_login() == "RenLimin"


def test_check_mode_writes_nothing(fake_home, monkeypatch, capsys):
    """--check 模式必须只读，不写 hosts.yml。"""
    _write_token(ghsync.TOKEN_FILE)
    called = {"sync": False}
    monkeypatch.setattr(ghsync, "sync_hosts", lambda *a, **k: called.__setitem__("sync", True) or "")
    monkeypatch.setattr(ghsync, "check_gh_cli", lambda: (True, "ok"))
    monkeypatch.setattr(ghsync, "verify_token", lambda: (True, "RenLimin"))
    rc = ghsync.main(["--check"])
    assert rc == 0
    assert called["sync"] is False
    assert not ghsync.HOSTS_FILE.exists()


def test_resolve_gh_absolute():
    """gh 解析必须返回绝对路径（不依赖 PATH 裸命令名）。"""
    found = ghsync._resolve_gh()
    if found is not None:
        assert Path(found).is_absolute()
