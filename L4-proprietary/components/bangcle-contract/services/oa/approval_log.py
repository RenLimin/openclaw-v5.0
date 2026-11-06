"""P4.1 泛微 OA 审批链读取器（详设 DESIGN-DETAIL-palantir-p4-reader-v1.0 §3）。

读路径（Rex 已拍板）：真实浏览器驱动
  打开 ViewRequest.jsp?requestid=<id> → 点「流转意见」→
  监听 getRequestLogBaseInfo / getRequestLogList 响应 → 归一化。

不走纯 HTTP 重放：loglist 需表单页签发的签名令牌，裸 POST 会被
LoadRequestLogDataCmd 拦截。

本模块只做读 + 归一化，不写 OA、不持久化任何凭据。
归一化函数（normalize_approval_chain / build_approval_chain）可独立调用，
浏览器 I/O 与归一化解耦，便于黄金夹具离线重放（不触网）。
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# 与 browser_fallback 保持一致的默认会话落盘位置
DEFAULT_STATE_PATH = Path.home() / ".openclaw" / "data" / "clm-oa-recon" / "state.json"

VIEW_URL = "https://oa.bangcle.com/workflow/request/ViewRequest.jsp?requestid={rid}"
BASE_INFO_MARKER = "getRequestLogBaseInfo"
LOG_LIST_MARKER = "getRequestLogList"

# OA 不推进流程的动作（抄送不代表当前节点）
_NON_FLOW_ACTIONS = {"抄送"}


class ApprovalLogUnavailable(RuntimeError):
    """审批链不可得（会话失效、loglist 被拦截/为空、DOM 变更等）。

    上层（对账）据此降级 oa_unknown，不伪造审批链。
    """


class _SessionExpired(RuntimeError):
    """内部信号：浏览器被重定向到登录页（会话失效）。"""


@dataclass
class ApprovalEntry:
    node: str          # log_nodename，如「商务」「分管总监」
    operator: str      # displayname
    operator_id: str   # displayid（OA 工号，身份映射主键）
    dept: str          # displaydepname
    action: str        # operationname：提交/批准/退回/抄送/批注…
    opinion: str       # log_remarkHtml 去标签、压缩空白后的纯文本
    date: str          # log_operatedate
    time: str          # log_operatetime
    receivers: str     # receiveUser
    log_id: str        # logid


@dataclass
class ApprovalChain:
    requestid: str
    workflowid: str
    tx_status: str          # base.txStatus（OA 流程状态字典）
    creator_node_id: str    # base.creatorNodeId
    viewer_user_id: str     # base.userId
    entries: List[ApprovalEntry] = field(default_factory=list)

    def current_node(self) -> Optional[ApprovalEntry]:
        """OA 当前节点 = 原始顺序中第一条真正推进流程的记录。

        OA loglist 按时间倒序；首条可能是「抄送」（不流转），
        因此跳过抄送，返回第一条提交/批准/退回/批注；没有则回退首条。
        """
        for e in self.entries:
            if e.action not in _NON_FLOW_ACTIONS:
                return e
        return self.entries[0] if self.entries else None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d


def normalize_opinion(html: Any) -> str:
    """OA log_remarkHtml → 纯文本（详设 §3.3 固定规则）。

    1) &nbsp; 等 HTML 实体先按字面处理为空格（含 &nbsp;）；
    2) 去标签；
    3) 压缩所有空白为单空格并 strip。
    """
    if html is None:
        return ""
    text = str(html)
    # &nbsp; 是实体文本而非标签，固定规则之外先还原为普通空格
    text = text.replace("&nbsp;", " ")
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _s(value: Any) -> str:
    """OA 字段统一字符串化（userId 实测可能为 int）。"""
    if value is None:
        return ""
    return str(value)


def build_approval_chain(
    requestid: Any,
    base: Dict[str, Any],
    loglist: List[Dict[str, Any]],
    *,
    workflowid: Any = "",
) -> ApprovalChain:
    """从已捕获的 base info + loglist 原始结构归一化出 ApprovalChain。

    纯函数：不触网，可直接用黄金夹具重放。entries 严格保持 OA 原始顺序。
    """
    if not isinstance(base, dict):
        raise ApprovalLogUnavailable(
            f"requestid={requestid}: base info 不是对象: {type(base).__name__}"
        )
    if not isinstance(loglist, list):
        raise ApprovalLogUnavailable(
            f"requestid={requestid}: loglist 不是数组: {type(loglist).__name__}"
        )
    if not loglist:
        # 不伪造审批链：loglist 空（被拦截/无权限）直接报错
        raise ApprovalLogUnavailable(
            f"requestid={requestid}: loglist 为空（可能被签名拦截）"
        )

    entries = [
        ApprovalEntry(
            node=_s(raw.get("log_nodename")),
            operator=_s(raw.get("displayname")),
            operator_id=_s(raw.get("displayid")),
            dept=_s(raw.get("displaydepname")),
            action=_s(raw.get("operationname")),
            opinion=normalize_opinion(raw.get("log_remarkHtml")),
            date=_s(raw.get("log_operatedate")),
            time=_s(raw.get("log_operatetime")),
            receivers=_s(raw.get("receiveUser")),
            log_id=_s(raw.get("logid")),
        )
        for raw in loglist
    ]

    return ApprovalChain(
        requestid=_s(requestid),
        workflowid=_s(base.get("workflowid") or workflowid),
        tx_status=_s(base.get("txStatus")),
        creator_node_id=_s(base.get("creatorNodeId")),
        viewer_user_id=_s(base.get("userId")),
        entries=entries,
    )


def normalize_approval_chain(raw: Dict[str, Any]) -> ApprovalChain:
    """归一化入口（独立可调用）：输入原始 dict，输出 ApprovalChain。

    支持两种原始结构：
    A) 黄金夹具结构：
       {"requestid", "workflowid", "base_info", "loglist_raw"}
    B) 浏览器捕获结构：
       {"requestid", "base_info"(={base,loglist 两键})} —— 见 _capture
    """
    if not isinstance(raw, dict):
        raise ApprovalLogUnavailable(
            f"normalize_approval_chain: 输入不是 dict: {type(raw).__name__}"
        )
    requestid = raw.get("requestid")
    base = raw.get("base_info")
    loglist = raw.get("loglist_raw")

    captured = raw.get("captured")
    if captured is not None:
        # _capture 落盘式封装：{"base": {...}, "loglist": [...]}
        base = captured.get("base")
        loglist = captured.get("loglist")

    if not isinstance(base, dict) or not isinstance(loglist, list):
        raise ApprovalLogUnavailable(
            f"requestid={requestid}: 缺少 base_info / loglist_raw"
        )
    return build_approval_chain(
        requestid, base, loglist, workflowid=raw.get("workflowid") or ""
    )


class ApprovalLogReader:
    """真实浏览器驱动的审批链读取器（详设 §3.1/§3.2）。"""

    def __init__(
        self,
        state_path: Optional[str] = None,
        *,
        headless: bool = True,
        timeout_ms: int = 60000,
    ) -> None:
        self.state_path = state_path or str(DEFAULT_STATE_PATH)
        self.headless = headless
        self.timeout_ms = timeout_ms

    # -- 会话重建接缝（测试可 monkeypatch，绝不触网）--
    def _refresh_session(self) -> bool:
        from services.oa.browser_fallback import refresh_oa_session

        return bool(refresh_oa_session())

    # -- 浏览器捕获（可注入假 page 单测；真实路径在 _capture 内启动 Playwright）--
    def _collect_from_page(
        self, page: Any, requestid: str
    ) -> Dict[str, Any]:
        """在单个 page 上完成：注册响应监听 → 打开单据 → 点「流转意见」。

        返回 {"base": dict, "loglist": list}。
        该页可能发多次 getRequestLogList，取 loglist 非空的那条。
        """
        base_holder: Dict[str, Any] = {}
        list_holder: Dict[str, Any] = {"loglist": []}

        def on_response(response: Any) -> None:
            try:
                url = str(getattr(response, "url", ""))
            except Exception:  # noqa: BLE001
                return
            if BASE_INFO_MARKER in url:
                try:
                    data = response.json()
                except Exception:  # noqa: BLE001
                    return
                if isinstance(data, dict):
                    base_holder["data"] = data
            elif LOG_LIST_MARKER in url:
                try:
                    data = response.json()
                except Exception:  # noqa: BLE001
                    return
                if isinstance(data, dict) and data.get("loglist"):
                    list_holder["data"] = data
                    list_holder["loglist"] = data["loglist"]

        page.on("response", on_response)

        page.goto(VIEW_URL.format(rid=requestid), wait_until="networkidle",
                  timeout=self.timeout_ms)
        current_url = str(getattr(page, "url", ""))
        if "login" in current_url.lower() or "Login" in current_url:
            raise _SessionExpired(f"requestid={requestid}: 被重定向到登录页")

        # 审批日志懒加载：不点「流转意见」实测只拿得到 base
        page.get_by_text("流转意见").click(timeout=self.timeout_ms)

        deadline = time.monotonic() + self.timeout_ms / 1000.0
        while time.monotonic() < deadline:
            if "data" in base_holder and list_holder["loglist"]:
                break
            page.wait_for_timeout(100)
        else:
            raise ApprovalLogUnavailable(
                f"requestid={requestid}: 等待审批 XHR 超时 "
                f"(base={'yes' if 'data' in base_holder else 'no'}, "
                f"loglist={len(list_holder['loglist'])})"
            )

        if "data" not in base_holder:
            raise ApprovalLogUnavailable(
                f"requestid={requestid}: 未捕获 getRequestLogBaseInfo"
            )
        if not list_holder["loglist"]:
            raise ApprovalLogUnavailable(
                f"requestid={requestid}: getRequestLogList 为空（签名拦截?）"
            )
        return {"base": base_holder["data"], "loglist": list_holder["loglist"]}

    def _capture(self, requestid: str) -> Dict[str, Any]:
        """启动 Playwright 真实浏览器执行捕获（headless 默认 True）。"""
        from playwright.sync_api import sync_playwright

        if not os.path.exists(self.state_path):
            raise _SessionExpired(
                f"storage_state 不存在: {self.state_path}"
            )

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            try:
                context = browser.new_context(storage_state=self.state_path)
                page = context.new_page()
                try:
                    return self._collect_from_page(page, requestid)
                finally:
                    context.close()
            finally:
                browser.close()

    def read_approval_chain(self, requestid: Any) -> ApprovalChain:
        """读取并归一化审批链；会话失效自动重建一次、重试一次。

        仍失败抛 ApprovalLogUnavailable（上层降级 unknown，不伪造）。
        """
        rid = _s(requestid)
        try:
            captured = self._capture(rid)
        except _SessionExpired:
            if not self._refresh_session():
                raise ApprovalLogUnavailable(
                    f"requestid={rid}: 会话失效且自动重建失败"
                )
            try:
                captured = self._capture(rid)
            except ApprovalLogUnavailable:
                raise
            except Exception as exc:  # noqa: BLE001
                raise ApprovalLogUnavailable(
                    f"requestid={rid}: 重建会话后重试仍失败: {exc}"
                ) from exc
        except ApprovalLogUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ApprovalLogUnavailable(
                f"requestid={rid}: 审批链读取失败: {exc}"
            ) from exc

        return build_approval_chain(
            rid, captured["base"], captured["loglist"]
        )


__all__ = [
    "ApprovalEntry",
    "ApprovalChain",
    "ApprovalLogReader",
    "ApprovalLogUnavailable",
    "build_approval_chain",
    "normalize_approval_chain",
    "normalize_opinion",
]
