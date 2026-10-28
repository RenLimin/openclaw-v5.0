#!/usr/bin/env python3
"""secret_scan 单测：高置信检出 + 赋值检出 + 占位符/代码放行 + 行号。"""
# secret-scan: allow-test-vectors  本文件是扫描器自身的检测向量集，含故意构造的假密钥
import importlib.util
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCAN = os.path.join(_HERE, "..", "secret-scan", "secret_scan.py")

_spec = importlib.util.spec_from_file_location("secret_scan", _SCAN)
ss = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ss)

no_allow = []


def _rules(findings):
    return sorted({f[2] for f in findings})


# ---------- 高置信：必须检出 ----------
def test_aws_key_detected():
    f = ss.scan_bytes(b"AKIAIOSFODNN7EXAMPLE", no_allow)
    assert "aws-access-key-id" in _rules(f)


def test_github_token_detected():
    tok = b"ghp_" + b"a" * 40
    assert "github-token" in _rules(ss.scan_bytes(tok, no_allow))


def test_google_api_key_detected():
    key = b"AIza" + b"A" * 35
    assert "google-api-key" in _rules(ss.scan_bytes(key, no_allow))


def test_jwt_detected():
    jwt = b"eyJ" + b"a" * 20 + b".eyJ" + b"b" * 20 + b".sig" + b"c" * 10
    assert "jwt" in _rules(ss.scan_bytes(jwt, no_allow))


def test_private_key_detected():
    pem = b"-----BEGIN RSA PRIVATE KEY-----\nAAAA\n"
    assert "private-key" in _rules(ss.scan_bytes(pem, no_allow))


def test_slack_token_detected():
    tok = b"xoxb-" + b"1" * 30
    assert "slack-token" in _rules(ss.scan_bytes(tok, no_allow))


# ---------- 赋值类：真实字面量检出 ----------
def test_password_assignment_double_quote():
    f = ss.scan_bytes(b'password = "Fak3-Pw-Xyz"', no_allow)
    assert "hardcoded-credential" in _rules(f)


def test_password_assignment_single_quote():
    f = ss.scan_bytes(b"password: 'hunter2xy'", no_allow)
    assert "hardcoded-credential" in _rules(f)


def test_apikey_camelcase_assignment():
    f = ss.scan_bytes(b'apiKey: "sk-live-abcdef123456"', no_allow)
    assert "hardcoded-credential" in _rules(f)


def test_json_secret_colon():
    f = ss.scan_bytes(b'"secret": "abcd1234wxyz5678"', no_allow)
    assert "hardcoded-credential" in _rules(f)


# ---------- 必须放行：占位符 / 代码引用，防误伤 ----------
def test_placeholder_change_in_production_ok():
    assert ss.scan_bytes(b'JWT_SECRET = "dev-secret-change-in-production"', no_allow) == []


def test_example_ok():
    assert ss.scan_bytes(b'api_key = "your-api-key-here-example"', no_allow) == []


def test_function_call_ok():
    assert ss.scan_bytes(b"token = create_access_token(data)", no_allow) == []


def test_attribute_lookup_ok():
    assert ss.scan_bytes(b'api_key = request.credentials.get("x")', no_allow) == []


def test_redacted_literal_ok():
    assert ss.scan_bytes(b'secret = "REDACTED_SECRET"', no_allow) == []


def test_secrets_module_ok():
    assert ss.scan_bytes(b"key = secrets.token_urlsafe(32)", no_allow) == []


def test_getenv_ok():
    assert ss.scan_bytes(b'password = os.getenv("DB_PASSWORD")', no_allow) == []


# ---------- 行号定位 ----------
def test_lineno_second_line():
    data = b"# header\npassword = \"Fak3-Pw-Xyz\"\n"
    f = ss.scan_bytes(data, no_allow)
    cred = [x for x in f if x[2] == "hardcoded-credential"]
    assert cred and cred[0][1] == 2


def test_mask_does_not_leak_full():
    masked = ss._mask(b"supersecretvalue")
    assert masked != "supersecretvalue"
    assert "***" in masked


# ---------- 白名单正则 ----------
def test_allow_pattern():
    import re
    allow = [re.compile(b"^company-")]
    assert ss.scan_bytes(b'password = "company-internal-thing"', allow) == []
    assert ss.scan_bytes(b'password = "other-internal-thing"', no_allow) != []


# ---------- 测试夹具白名单（测试目录内的明显假密码放行）----------
def test_testpass_in_test_dir_ok():
    f = ss.scan_bytes(
        b'json={"username": "testuser", "password": "testpass"}',
        no_allow, source="app/tests/test_api.py")
    assert f == []


def test_wrongpass_in_test_dir_ok():
    f = ss.scan_bytes(b'"password": "wrongpass"', no_allow,
                      source="tests/test_login.py")
    assert f == []


def test_same_password_in_non_test_dir_flagged():
    # 非测试目录，即便是 testpass 也不能默认放行
    f = ss.scan_bytes(b'password = "testpass1234"', no_allow,
                      source="src/prod.py")
    assert "hardcoded-credential" in _rules(f)


def test_realistic_secret_in_test_dir_still_flagged():
    # 测试目录里出现高熵真实样式密钥仍要报（不被夹具白名单放过）
    f = ss.scan_bytes(b'password = "sk-live-9f8e7d6c5b4a"', no_allow,
                      source="tests/test_x.py")
    assert "hardcoded-credential" in _rules(f)
