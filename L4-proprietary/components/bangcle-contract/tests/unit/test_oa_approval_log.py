"""P4 单测：审批链读取器归一化 + OA 写连接器 + 定时对账（详设 §7）。

全程不触网、不开真浏览器：
- 黄金夹具 tests/fixtures/oa_log_882663.json 离线重放归一化；
- 浏览器 I/O 用 fake page / fake response 覆盖（base + loglist + 点击）；
- reconcile 用 fake reader 测四态。
"""
import json
import os
import sys

import pytest

COMPONENT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if COMPONENT_ROOT not in sys.path:
    sys.path.insert(0, COMPONENT_ROOT)

from services.oa.approval_log import (  # noqa: E402
    ApprovalChain,
    ApprovalLogReader,
    ApprovalLogUnavailable,
    build_approval_chain,
    normalize_approval_chain,
)
from contract_review.ontology_bridge.oa_connector import (  # noqa: E402
    OaWritebackConnector,
)
from ai_kb.ontology import CompensationUnavailable, SagaContext  # noqa: E402
from contract_review.ontology_bridge.reconcile import (  # noqa: E402
    derive_oa_state,
    reconcile,
)

FIXTURE = os.path.join(
    COMPONENT_ROOT, "tests", "fixtures", "oa_log_882663.json"
)


@pytest.fixture()
def golden():
    with open(FIXTURE, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------
# §7.1 归一化黄金夹具：10 条 + 关键记录
# ---------------------------------------------------------------
def test_normalize_golden_chain_10_entries(golden):
    chain = normalize_approval_chain(golden)
    assert isinstance(chain, ApprovalChain)
    assert chain.requestid == "882663"
    assert chain.workflowid == "757"
    assert len(chain.entries) == 10
    # entries 严格保持 OA 原始顺序（倒序）
    assert chain.entries[0].operator == "佟鑫"
    assert chain.entries[0].action == "抄送"


def _find(chain, operator, action):
    hits = [
        e for e in chain.entries
        if e.operator == operator and e.action == action
    ]
    assert hits, f"未找到 {operator}/{action}"
    return hits[0]


def test_golden_kan_approve(golden):
    chain = normalize_approval_chain(golden)
    e = _find(chain, "阚志刚", "批准")
    assert e.operator_id == "3"
    assert e.node == "分管总监"
    assert e.opinion.startswith("同意。")
    assert "来自iPhone客户端" in e.opinion
    # HTML 标签已去除
    assert "<" not in e.opinion


def test_golden_wang_return(golden):
    chain = normalize_approval_chain(golden)
    e = _find(chain, "王仙仙", "退回")
    assert e.operator_id == "364"
    assert e.opinion.startswith("请修改产品版本")


def test_golden_he_submit(golden):
    chain = normalize_approval_chain(golden)
    e = _find(chain, "何钰其", "提交")
    assert e.operator_id == "1625"
    assert e.node == "申请人"
    # &nbsp; 段落 → 单空格，空白被压缩
    assert "望批准" in e.opinion
    assert "  " not in e.opinion
    assert "&nbsp;" not in e.opinion


def test_chain_current_node_skips_cc(golden):
    chain = normalize_approval_chain(golden)
    cur = chain.current_node()
    # 首条是抄送，current_node 必须跳过抄送取「批准」
    assert cur.action == "批准"
    assert cur.operator == "佟鑫"
    d = chain.to_dict()
    assert d["entries"][0]["operator_id"] == "949"


def test_build_rejects_empty_loglist(golden):
    with pytest.raises(ApprovalLogUnavailable):
        build_approval_chain(
            golden["requestid"], golden["base_info"], []
        )


def test_opinion_normalizer_handles_nbsp():
    from services.oa.approval_log import normalize_opinion
    html = "<p>a&nbsp;b</p><p>\n\t c </p>"
    assert normalize_opinion(html) == "a b c"
    assert normalize_opinion(None) == ""


# ---------------------------------------------------------------
# §7.2 浏览器 I/O 用假 page / 假 response 覆盖，不触网
# ---------------------------------------------------------------
class FakeResponse:
    def __init__(self, url, payload):
        self._url = url
        self._payload = payload

    @property
    def url(self):
        return self._url

    def json(self):
        return self._payload


class FakeLocator:
    def __init__(self, page):
        self.page = page

    def click(self, timeout=None):
        # 点击「流转意见」后，页面补发 loglist XHR（模拟懒加载）
        self.page._emit(
            "https://oa.bangcle.com/api/workflow/getRequestLogList?ts=2",
            {"loglist": self.page.loglist},
        )


class FakePage:
    def __init__(self, base, loglist, *, current_url="https://oa.bangcle.com/workflow/request/ViewRequest.jsp?requestid=882663"):
        self.base = base
        self.loglist = loglist
        self._current_url = current_url
        self.handlers = []
        self.clicked = False

    def on(self, event, handler):
        assert event == "response"
        self.handlers.append(handler)

    def goto(self, url, wait_until=None, timeout=None):
        # 页面初始加载只发 base info（实测不点只有 base）
        self._emit(
            "https://oa.bangcle.com/api/workflow/getRequestLogBaseInfo",
            self.base,
        )

    @property
    def url(self):
        return self._current_url

    def get_by_text(self, text):
        assert text == "流转意见"
        return FakeLocator(self)

    def wait_for_timeout(self, ms):
        return None

    def _emit(self, url, payload):
        resp = FakeResponse(url, payload)
        for h in list(self.handlers):
            h(resp)


def test_reader_collect_with_fake_page(golden):
    reader = ApprovalLogReader(state_path="/tmp/fake-state.json")
    page = FakePage(golden["base_info"], golden["loglist_raw"])
    captured = reader._collect_from_page(page, "882663")
    assert captured["base"]["txStatus"] == "1"
    assert len(captured["loglist"]) == 10
    chain = build_approval_chain(
        "882663", captured["base"], captured["loglist"]
    )
    assert len(chain.entries) == 10


def test_reader_read_retries_once_on_session_expiry(golden, monkeypatch):
    reader = ApprovalLogReader(state_path="/tmp/fake-state.json")
    calls = {"n": 0}
    pages = [
        FakePage(None, None, current_url="https://oa.bangcle.com/login/Login.jsp"),
        FakePage(golden["base_info"], golden["loglist_raw"]),
    ]

    def fake_capture(rid):
        idx = calls["n"]
        calls["n"] += 1
        if idx == 0:
            from services.oa.approval_log import _SessionExpired
            raise _SessionExpired("登录页")
        return reader._collect_from_page(pages[1], rid)

    monkeypatch.setattr(reader, "_capture", fake_capture)
    monkeypatch.setattr(reader, "_refresh_session", lambda: True)

    chain = reader.read_approval_chain("882663")
    assert calls["n"] == 2
    assert len(chain.entries) == 10


def test_reader_session_expired_refresh_failed(monkeypatch):
    reader = ApprovalLogReader(state_path="/tmp/fake-state.json")
    from services.oa.approval_log import _SessionExpired

    monkeypatch.setattr(reader, "_capture",
                        lambda rid: (_ for _ in ()).throw(_SessionExpired("登录页")))
    monkeypatch.setattr(reader, "_refresh_session", lambda: False)
    with pytest.raises(ApprovalLogUnavailable):
        reader.read_approval_chain("882663")


def test_reader_empty_loglist_raises(golden):
    reader = ApprovalLogReader(state_path="/tmp/fake-state.json", timeout_ms=120)
    page = FakePage(golden["base_info"], [])
    # FakeLocator 会发空 loglist；收集器应在等待循环中超时报错
    with pytest.raises(ApprovalLogUnavailable):
        reader._collect_from_page(page, "882663")


# ---------------------------------------------------------------
# §7.3 OaWritebackConnector：dry-run apply / 真实写拒绝 / 补偿恒抛
# ---------------------------------------------------------------
def _ctx():
    return SagaContext()


def test_oa_connector_dry_run_apply_no_http():
    conn = OaWritebackConnector(dry_run=True)
    ctx = _ctx()
    payload = {"requestid": "882663", "action": "submit", "comment": "x"}
    ctx.payloads[conn.step_name] = payload
    conn.apply(ctx)  # 不发 HTTP：无任何网络代码路径
    result = ctx.results[conn.name]
    assert result["dry_run"] is True
    assert result["requestid"] == "882663"
    assert conn.name in ctx.steps


def test_oa_connector_dry_run_constructor_target():
    conn = OaWritebackConnector(
        dry_run=True, target={"requestid": "9", "action": "approve"}
    )
    ctx = _ctx()
    conn.apply(ctx)
    assert ctx.results[conn.name]["action"] == "approve"


def test_oa_connector_real_write_rejected():
    conn = OaWritebackConnector(dry_run=False)
    ctx = _ctx()
    ctx.payloads[conn.step_name] = {"requestid": "882663", "action": "submit"}
    with pytest.raises(RuntimeError, match="P4.2 写端点契约未闭合"):
        conn.apply(ctx)


def test_oa_connector_compensate_always_unavailable():
    conn = OaWritebackConnector(dry_run=True)
    ctx = _ctx()
    with pytest.raises(CompensationUnavailable, match="人工冲销工单"):
        conn.compensate(ctx)


def test_oa_connector_no_target_raises():
    conn = OaWritebackConnector(dry_run=True)
    with pytest.raises(ValueError):
        conn.apply(_ctx())


# ---------------------------------------------------------------
# §7.4 reconcile 四态（fake reader，只读不写）
# ---------------------------------------------------------------
class FakeReader:
    """按 requestid 返回预置 ApprovalChain 或抛 ApprovalLogUnavailable。"""

    def __init__(self, chains):
        self.chains = chains
        self.read_calls = []

    def read_approval_chain(self, rid):
        self.read_calls.append(str(rid))
        value = self.chains[str(rid)]
        if isinstance(value, Exception):
            raise value
        return value


def _chain(action, tx_status, node="商务"):
    from services.oa.approval_log import ApprovalEntry
    return ApprovalChain(
        requestid="x", workflowid="1", tx_status=tx_status,
        creator_node_id="1", viewer_user_id="1",
        entries=[ApprovalEntry(
            node=node, operator="某人", operator_id="1", dept="d",
            action=action, opinion="", date="2026-10-27", time="10:00:00",
            receivers="", log_id="1",
        )],
    )


def test_derive_oa_state_mapping():
    assert derive_oa_state(_chain("提交", "1")) == "review"
    assert derive_oa_state(_chain("批准", "1")) == "review"
    assert derive_oa_state(_chain("批准", "0")) == "approved"
    assert derive_oa_state(_chain("退回", "1", node="申请人")) == "draft"


def test_reconcile_four_kinds():
    chains = {
        "1": _chain("批准", "0"),       # approved
        "2": _chain("批准", "0"),       # approved（本地 review → oa_ahead）
        "3": _chain("提交", "1"),       # review（本地 approved → local_ahead）
        "4": ApprovalLogUnavailable("会话失效"),
    }
    local_states = {
        "1": "approved",
        "2": "review",
        "3": "approved",
        "4": "review",
    }
    diffs = reconcile(
        ["1", "2", "3", "4"],
        local_states=local_states,
        reader=FakeReader(chains),
    )
    by_id = {d.requestid: d for d in diffs}
    assert by_id["1"].kind == "in_sync"
    assert by_id["2"].kind == "oa_ahead"
    assert by_id["3"].kind == "local_ahead"
    assert by_id["4"].kind == "oa_unknown"
    assert by_id["4"].oa_state == "oa_unknown"


def test_reconcile_is_read_only():
    reader = FakeReader({"9": _chain("提交", "1")})
    diffs = reconcile(["9"], local_states={"9": "review"}, reader=reader)
    assert diffs[0].kind == "in_sync"
    assert reader.read_calls == ["9"]  # 只发生读
