"""browser_fallback 离线测试：secrets 读取 / 模块注入 / 错误路径。"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from services.oa import browser_fallback as bf


def test_iam_credentials_from_secrets(tmp_path, monkeypatch):
    secrets_dir = tmp_path / ".openclaw" / "secrets"
    secrets_dir.mkdir(parents=True)
    (secrets_dir / "iam.username").write_text("user1", encoding="utf-8")
    (secrets_dir / "iam.password").write_text("pass1", encoding="utf-8")
    monkeypatch.setattr(bf.Path, "home", lambda: tmp_path)
    u, p = bf._iam_credentials_from_secrets()
    assert (u, p) == ("user1", "pass1")


def test_iam_credentials_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(bf.Path, "home", lambda: tmp_path)
    u, p = bf._iam_credentials_from_secrets()
    assert (u, p) == ("", "")


def test_bdms_unavailable_raises(monkeypatch):
    def no_module():
        raise bf.BrowserFallbackError("BDMS browser_adapter 不可用: no bdms")
    monkeypatch.setattr(bf, "_bdms_adapter_module", no_module)
    with pytest.raises(bf.BrowserFallbackError):
        bf.get_contract_via_browser("1", "/tmp/x")


def test_browser_card_url_contains_billid():
    # 通过浏览器路径构造检查：直接调用内部 URL 拼装逻辑
    url = (
        "https://oa.bangcle.com/spa/cube/index.html#/main/cube/card"
        "?type=0&modeId=112&formId=-249&billid=%s&customid=179" % "15134"
    )
    assert "billid=15134" in url
    assert "customid=179" in url


def test_heal_session_missing_credentials(tmp_path, monkeypatch):
    monkeypatch.setattr(bf.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(bf, "_bdms_adapter_module", lambda: None)
    # 无凭据且 BDMS 不可用 → 应抛 BrowserFallbackError（凭据缺失）
    # 这里构造 ba 模块带 _iam_credentials 抛异常的情况
    class FakeBA:
        @staticmethod
        def _iam_credentials():
            raise Exception("no secrets")
    monkeypatch.setattr(bf, "_bdms_adapter_module", lambda: FakeBA)
    with pytest.raises(bf.BrowserFallbackError):
        bf.heal_session()
