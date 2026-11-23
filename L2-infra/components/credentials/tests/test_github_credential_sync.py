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


# --- scope 门禁（2026-11-23 事故：缺 workflow scope 导致反复 push 失败）---

class _FakeProc:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_fetch_scopes_parses_header(monkeypatch):
    """从 X-Oauth-Scopes 响应头解析 scope（大小写不敏感）。"""
    monkeypatch.setattr(ghsync, "_run_gh", lambda *a, **k: _FakeProc(
        stdout="HTTP/2.0 200 OK\nX-Oauth-Scopes: gist, repo, workflow\n\n{}"))
    ok, scopes, detail = ghsync.fetch_scopes()
    assert ok
    assert "workflow" in scopes
    assert detail == ""


def test_fetch_scopes_missing_header_fail_closed(monkeypatch):
    """响应无 scope 头 → 必须判为不可读（不能默认放行）。"""
    monkeypatch.setattr(ghsync, "_run_gh", lambda *a, **k: _FakeProc(
        stdout="HTTP/2.0 200 OK\nContent-Type: application/json\n\n{}"))
    ok, scopes, detail = ghsync.fetch_scopes()
    assert not ok
    assert scopes == []
    assert "无" in detail


def test_fetch_scopes_never_prints_token(monkeypatch):
    """scope 读取路径不得回显 token（只输出 scope 名）。"""
    monkeypatch.setattr(ghsync, "_run_gh", lambda *a, **k: _FakeProc(
        stdout="HTTP/2.0 200 OK\nX-Oauth-Scopes: gist, repo\n\n{}"))
    ok, scopes, _ = ghsync.fetch_scopes()
    assert ok and "gho_" not in " ".join(scopes)


def test_require_scope_missing_blocks(fake_home, monkeypatch, capsys):
    """缺指定 scope → 非零退出（fail-closed）。"""
    _write_token(ghsync.TOKEN_FILE)
    monkeypatch.setattr(ghsync, "check_gh_cli", lambda: (True, "ok"))
    monkeypatch.setattr(ghsync, "verify_token", lambda: (True, "RenLimin"))
    monkeypatch.setattr(ghsync, "fetch_scopes", lambda: (True, ["gist", "repo"], ""))
    rc = ghsync.main(["--check", "--require-scope", "workflow"])
    assert rc == 1
    out = capsys.readouterr().out
    assert "workflow" in out


def test_require_scope_present_ok(fake_home, monkeypatch):
    """含指定 scope → 放行。"""
    _write_token(ghsync.TOKEN_FILE)
    monkeypatch.setattr(ghsync, "check_gh_cli", lambda: (True, "ok"))
    monkeypatch.setattr(ghsync, "verify_token", lambda: (True, "RenLimin"))
    monkeypatch.setattr(ghsync, "fetch_scopes", lambda: (True, ["gist", "repo", "workflow"], ""))
    rc = ghsync.main(["--check", "--require-scope", "workflow"])
    assert rc == 0


def test_require_scope_unreadable_fail_closed(fake_home, monkeypatch):
    """要求 scope 但读不到 → 必须拒绝放行（不得因网络异常静默放过）。"""
    _write_token(ghsync.TOKEN_FILE)
    monkeypatch.setattr(ghsync, "check_gh_cli", lambda: (True, "ok"))
    monkeypatch.setattr(ghsync, "verify_token", lambda: (True, "RenLimin"))
    monkeypatch.setattr(ghsync, "fetch_scopes", lambda: (False, [], "响应中无 X-Oauth-Scopes 头"))
    rc = ghsync.main(["--check", "--require-scope", "workflow"])
    assert rc == 1
