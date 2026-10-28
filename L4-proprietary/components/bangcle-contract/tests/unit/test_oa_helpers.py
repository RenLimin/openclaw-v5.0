"""services.oa 离线单测（纯函数，无需网络/会话）。"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from services.oa import helpers as H
from services.oa.cube import (
    CubeClient, CubeAuthError, CubePermissionError, CubeError,
)


# ---------- query 拼装 ----------
def test_build_card_query():
    q = H.build_card_query("15134", key="k1", uuid="u" * 32, layoutid="535")
    assert q["type"] == "0"
    assert q["modeId"] == "112"
    assert q["formId"] == "-249"
    assert q["billid"] == "15134"
    assert q["customid"] == "179"
    assert q["_key"] == "k1"
    assert q["uuid"] == "u" * 32
    assert q["layoutid"] == "535"


def test_require_billid_valid():
    assert H._require_billid("123") == "123"
    assert H._require_billid(123) == "123"


def test_require_billid_invalid():
    with pytest.raises(H.HelperError):
        H._require_billid("")
    with pytest.raises(H.HelperError):
        H._require_billid(None)


# ---------- URL ----------
def test_resolve_url():
    assert H.resolve_url("/api/x") == "https://oa.bangcle.com/api/x"
    assert H.resolve_url("https://oa.bangcle.com/api/x") == "https://oa.bangcle.com/api/x"


def test_build_download_url():
    # 带 url → 直接可用
    assert H.build_download_url({"url": "/weaver/FileDownload?fileid=9", "id": "9"}) \
        == "https://oa.bangcle.com/weaver/FileDownload?fileid=9"
    # 纯数字 id → 已知端点
    assert H.build_download_url({"id": "42", "name": "a.pdf"}) \
        == "https://oa.bangcle.com/weaver/weaver.file.FileDownload?fileid=42"
    # 不可确定 → None（触发浏览器兜底）
    assert H.build_download_url({"id": "", "url": "", "name": "x"}) is None


# ---------- 响应信封 ----------
def test_classify_error():
    assert H.classify_error({"errorCode": "002", "msg": "登录信息超时"}) == "auth"
    assert H.classify_error({"errorCode": "0", "msg": ""}) == "error"
    assert H.classify_error({"msg": "无权访问"}) == "permission"


def test_is_success_envelope():
    # Cube 成功信封以 status 键为准（实测，非 success 键）
    assert H.is_success_envelope({"status": True}) is True
    assert H.is_success_envelope({"status": "1"}) is True
    assert H.is_success_envelope({"errorCode": "0"}) is False
    assert H.is_success_envelope({"datas": []}) is True
    assert H.is_success_envelope({"errorCode": "002"}) is False


# ---------- 字段提取 ----------
def test_extract_main_fields():
    obj = {"fields": [{"fieldid": "f1", "fieldlabelname": "合同编号", "fieldvalue": "XSZS001"}]}
    assert H.extract_main_fields(obj) == {"合同编号": "XSZS001"}


def test_extract_attachment_refs():
    rows = [{"fileupload": [{"name": "合同.pdf", "fileid": "88", "downloadUrl": "/api/docs/file/download?fileid=88"}]}]
    refs = H.extract_attachment_refs(rows)
    assert len(refs) == 1
    assert refs[0]["name"] == "合同.pdf"
    assert refs[0]["id"] == "88"


def test_looks_like_filename():
    assert H.looks_like_filename("合同.pdf") is True
    assert H.looks_like_filename("http://x/a.pdf") is False
    assert H.looks_like_filename("选项一") is False


def test_safe_filename():
    assert H.safe_filename("a/b\\c:d.pdf") == "c_d.pdf"
    assert H.safe_filename("") == "attachment.bin"


# ---------- detail_tables ----------
def test_detail_tables_sorted_by_orderid():
    init = {"detailTable": {
        "detail_8": {"tablename": "uf_xsht_xxb_dt8", "orderid": 8},
        "detail_2": {"tablename": "uf_xsht_xxb_dt2", "orderid": 2},
    }}
    tables = H.detail_tables(init)
    assert tables == [("detail_2", "uf_xsht_xxb_dt2"), ("detail_8", "uf_xsht_xxb_dt8")]


# ---------- 错误类型 ----------
def test_error_types():
    assert issubclass(CubeAuthError, CubeError)
    assert issubclass(CubePermissionError, CubeError)


# ---------- entry 降级：API 失败 → 浏览器兜底（用 monkeypatch 验证路由） ----------
def test_entry_falls_back_on_cube_error(tmp_path, monkeypatch):
    import services.oa.entry as entry

    class FakeClient:
        def __init__(self, storage_state=None):
            pass

        def get_contract(self, billid):
            raise CubeError("网络异常")

        def download_attachment(self, ref, out):
            raise CubeError("no")

        def reload_session(self):
            pass

    def fake_browser(billid, out_dir, storage_state=None):
        return {"billid": str(billid), "fallback": True, "attachments": []}

    monkeypatch.setattr(entry, "CubeClient", FakeClient)
    monkeypatch.setattr(entry, "get_contract_via_browser", fake_browser)
    result = entry.get_contract_with_fallback("15134", tmp_path)
    assert result["fallback"] is True


def test_entry_heal_then_retry(tmp_path, monkeypatch):
    import services.oa.entry as entry

    class HealClient:
        def __init__(self, storage_state=None):
            self.calls = 0

        def get_contract(self, billid):
            self.calls += 1
            if self.calls == 1:
                raise CubeAuthError("会话失效")
            return {"billid": str(billid), "main_fields": {}}

        def download_attachment(self, ref, out):
            raise CubeError("no url")

        def reload_session(self):
            pass

    monkeypatch.setattr(entry, "CubeClient", HealClient)
    monkeypatch.setattr(entry, "heal_session", lambda: True)
    result = entry.get_contract_with_fallback("15134", tmp_path)
    assert result["session_healed"] is True
    assert result["fallback"] is False


def test_entry_permission_not_faked(tmp_path, monkeypatch):
    import services.oa.entry as entry

    class DenyClient:
        def __init__(self, storage_state=None):
            pass

        def get_contract(self, billid):
            raise CubePermissionError("账号无权限")

        def reload_session(self):
            pass

    monkeypatch.setattr(entry, "CubeClient", DenyClient)
    with pytest.raises(CubePermissionError):
        entry.get_contract_with_fallback("15134", tmp_path)


# ---------- 补测：build_detail_query / rest_url / 多形态提取 ----------
def test_build_detail_query():
    q = H.build_detail_query("15134", "uf_xsht_xxb_dt8", 7, key="k2", uuid="u" * 32, layoutid="535")
    assert q["tablename"] == "uf_xsht_xxb_dt8"
    assert q["groupid"] == "7"
    assert q["billid"] == "15134"
    assert q["modeId"] == "112"
    assert q["formId"] == "-249"
    assert q["customid"] == "179"


def test_rest_url():
    u = H.rest_url("/api/cube/new/card/mainFields", {"billid": "1"})
    assert u.startswith("https://oa.bangcle.com/api/cube/new/card/mainFields")
    assert "billid=1" in u


def test_extract_main_fields_datas_form():
    obj = {
        "datas": [{"field101": "XSZS001", "field102": "乙方"}],
        "fieldAttr": [{"fieldid": "101", "fieldlabelname": "合同编号"},
                      {"fieldid": "102", "fieldlabelname": "客户名称"}],
    }
    m = H.extract_main_fields(obj)
    assert m.get("合同编号") == "XSZS001"
    assert m.get("客户名称") == "乙方"


def test_extract_main_fields_fieldnnnn_form():
    obj = {"field7": {"name": "金额", "value": "10000"}}
    m = H.extract_main_fields(obj)
    assert m.get("金额") == "10000"


def test_extract_attachment_refs_no_false_positive():
    # 枚举选项 showname（无文件名/url）不应被提取
    rows = [{"field": [{"showname": "新签产品"}, {"showname": "维保服务"}]}]
    assert H.extract_attachment_refs(rows) == []


def test_extract_attachment_refs_dedup():
    rows = [
        {"f": [{"name": "a.pdf", "fileid": "1", "url": "/d?fileid=1"}]},
        {"f": [{"name": "a.pdf", "fileid": "1", "url": "/d?fileid=1"}]},
    ]
    refs = H.extract_attachment_refs(rows)
    assert len(refs) == 1


def test_build_download_url_http_absolute():
    assert H.build_download_url({"url": "https://cdn/x.pdf"}) == "https://cdn/x.pdf"
    assert H.build_download_url({"url": "", "id": "abc"}) is None  # 非数字 id 不可构造


def test_classify_error_http_statuses():
    assert H.classify_error({}, 401) == "auth"
    assert H.classify_error({}, 403) == "permission"
    assert H.classify_error({}, 500) == "error"
    assert H.classify_error({}, 200) is None
