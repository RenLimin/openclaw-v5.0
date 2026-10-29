"""P8 §5：真实 OA 拉取（TC-OA-01~04），不 mock。

铁律：
- 真实拉取（TC-01/02/03）只用真实 storage_state；无有效会话 → skip 留证，绝不伪造。
- TC-OA-04（权限不足阻塞）在纯函数/编排层离线可测，**任何环境都必须跑**。
会话恢复：重跑 `contractctl oa-login`（IAM headless + IMAP 验证码）刷新 state.json。
"""
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
COMPONENT_ROOT = os.path.dirname(os.path.dirname(HERE))
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(COMPONENT_ROOT)))
L3_ROOT = os.path.join(REPO_ROOT, "L3-business", "components", "contract-management")
for p in (COMPONENT_ROOT, L3_ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

from oa_session import oa_session_available

# 侦察期记录的真实 billid（非敏感）
KNOWN_BILLID = "15134"

_LIVE_SKIP = pytest.mark.skipif(True, reason="placeholder")  # 运行时替换


def _live_session_works():
    """真实探测会话是否仍有效（不打印 cookie/正文）。"""
    if not oa_session_available():
        return False
    from services.oa.cube import CubeClient
    try:
        CubeClient(timeout=12).check_card_right(KNOWN_BILLID)  # 最轻只读
        return True
    except Exception:
        return False


_LIVE = _live_session_works()
_requires_live = pytest.mark.skipif(
    not _LIVE,
    reason="OA 会话失效/不可达（实测），跳过真实拉取，禁止伪 pass；"
           "重跑 `contractctl oa-login` 后即可真跑（TC-OA-01~03 留证）",
)


# ================= 真实拉取（需有效会话，失效则 skip） =================

@_requires_live
def test_tc_oa_01_api_fetches_contract_and_downloads(tmp_path):
    """TC-OA-01：API 路径取主字段 + 附件下载落盘字节>0。"""
    from services.oa.cube import CubeClient
    client = CubeClient(timeout=20)
    data = client.get_contract(KNOWN_BILLID)
    assert data.billid == KNOWN_BILLID
    assert isinstance(data.main_fields, dict)
    if data.attachments:                 # 有附件才断言下载；无附件属真实情况
        path = client.download_attachment(data.attachments[0], tmp_path)
        assert path.stat().st_size > 0


@_requires_live
def test_tc_oa_02_browser_fallback_on_forced_failure(tmp_path, monkeypatch):
    """TC-OA-02：注入 API CubeError → 统一入口自动降级浏览器兜底。"""
    from services.oa import entry
    from services.oa.cube import CubeClient, CubeError

    called = {"browser": False}

    def _fake_browser(billid, out_dir, storage_state=None):
        called["browser"] = True
        return {"billid": billid, "fallback": True,
                "attachments_local": [], "main_fields": {}}

    monkeypatch.setattr(entry, "get_contract_via_browser", _fake_browser)
    monkeypatch.setattr(
        CubeClient, "get_contract",
        lambda self, b: (_ for _ in ()).throw(CubeError("forced failure")))

    result = entry.get_contract_with_fallback(KNOWN_BILLID, tmp_path,
                                              heal_once=False)
    assert called["browser"] is True
    assert result.get("fallback") is True


@_requires_live
def test_tc_oa_03_session_self_heal_path(tmp_path, monkeypatch):
    """TC-OA-03：会话失效 → heal_session → reload → 重试（编排断言，不打印验证码）。"""
    from services.oa import entry
    from services.oa.cube import CubeClient, CubeAuthError, ContractData

    calls = {"heal": 0, "reload": 0, "retry": 0}
    monkeypatch.setattr(entry, "heal_session",
                        lambda: calls.__setitem__("heal", calls["heal"] + 1) or True)
    monkeypatch.setattr(CubeClient, "reload_session",
                        lambda self: calls.__setitem__("reload", calls["reload"] + 1))

    state = {"n": 0}

    def _get(self, b):
        if state["n"] == 0:
            state["n"] += 1
            raise CubeAuthError("登录超时")
        calls["retry"] += 1
        return ContractData(billid=b)

    monkeypatch.setattr(CubeClient, "get_contract", _get)
    result = entry.get_contract_with_fallback(KNOWN_BILLID, tmp_path)
    assert (calls["heal"], calls["reload"], calls["retry"]) == (1, 1, 1)
    assert result.get("session_healed") is True


# ================= TC-OA-04：权限阻塞（离线，任何环境必跑） =================

class TestPermissionBlockOffline:
    def test_permission_error_classified(self):
        from services.oa import helpers as H
        assert H.classify_error({"msg": "无权查看该卡片"}, 200) == "permission"
        assert H.classify_error({}, 403) == "permission"

    def test_entry_reraises_permission_without_fallback(self, monkeypatch, tmp_path):
        """权限错误：统一入口直接抛 CubePermissionError，绝不兜底/伪造。"""
        from services.oa import entry
        from services.oa.cube import CubeClient, CubePermissionError

        def _must_not_call(*a, **k):
            raise AssertionError("权限不足时不允许走浏览器兜底/伪造")

        monkeypatch.setattr(entry, "get_contract_via_browser", _must_not_call)
        monkeypatch.setattr(
            entry, "heal_session", lambda: False)  # 权限错也不允许自愈绕过
        monkeypatch.setattr(
            CubeClient, "get_contract",
            lambda self, b: (_ for _ in ()).throw(CubePermissionError("无权")))
        with pytest.raises(CubePermissionError):
            entry.get_contract_with_fallback(KNOWN_BILLID, tmp_path)
