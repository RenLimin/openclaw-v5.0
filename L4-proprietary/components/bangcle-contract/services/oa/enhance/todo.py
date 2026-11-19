"""OA 757 待办发现（只读）— L4 自包含实现。

复用 ``ones-browser-export/scripts/oa_todo_dist.py`` 的**列表口径**逻辑
（``/api/ec/dev/table/datas`` 全量分页 + 当次页面 ``dataKey`` 捕获），
不跨层 import skill 脚本（分层红线：L4 对 skill 脚本无稳定 API 契约）。

口径说明：列表口径含历史流程定义的遗留单据，与树/计数口径不一致属**正常**
（见 docs/knowledge-base/oa-contract-review-workflow.md §七）。

前置：OA storage_state（``~/.openclaw/data/clm-oa-recon/state.json``）；
过期抛 ``OaSessionExpired``，由调用方 ``refresh_oa_session()`` 自愈。
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_STATE = Path.home() / ".openclaw" / "data" / "clm-oa-recon" / "state.json"
URL = "https://oa.bangcle.com/spa/workflow/index_mobx.jsp#/main/workflow/listDoing"
API = "/api/ec/dev/table/datas"

DEFAULT_WORKFLOW_ID = "757"
DEFAULT_WORKFLOW_NAME = "销售合同审核流程"


class OaSessionExpired(RuntimeError):
    """OA 会话失效（storage_state 过期）。"""


@dataclass
class TodoItem:
    """OA 待办单据（workflowid 维度）。"""

    request_id: str
    request_name: str
    workflow_id: str
    create_date: str = ""
    status: str = ""
    applicant: str = ""

    @staticmethod
    def from_raw(raw: Dict[str, Any]) -> "TodoItem":
        name = str(raw.get("request_name") or "")
        applicant = ""
        parts = name.split("-")
        if len(parts) >= 3:
            applicant = parts[1]
        return TodoItem(
            request_id=str(raw.get("requestid") or ""),
            request_name=name,
            workflow_id=str(raw.get("workflowid") or ""),
            create_date=str(raw.get("createdate") or ""),
            status=str(raw.get("status") or ""),
            applicant=applicant,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "request_name": self.request_name,
            "workflow_id": self.workflow_id,
            "create_date": self.create_date,
            "status": self.status,
            "applicant": self.applicant,
        }


def discover_todos(
    workflow_id: str = DEFAULT_WORKFLOW_ID,
    *,
    max_pages: int = 20,
    storage_state: Optional[Path] = None,
    headless: bool = True,
) -> List[TodoItem]:
    """发现指定 workflowid 的待办（列表口径，全量分页）。

    Args:
        workflow_id: OA workflowid（757 = 销售合同审核流程）。
        max_pages: 最大分页数。
        storage_state: Playwright storage_state 路径（默认侦察路径）。
        headless: 是否无头。

    Returns:
        命中该 workflowid 的 ``TodoItem`` 列表；无待办返回 ``[]``（不报错）。

    Raises:
        OaSessionExpired: OA 会话失效。
    """
    from playwright.sync_api import sync_playwright

    state = str(storage_state or DEFAULT_STATE)
    items: List[Dict[str, Any]] = []
    seen: set = set()
    data_key: Dict[str, Optional[str]] = {"v": None}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        try:
            ctx = browser.new_context(storage_state=state)
            page = ctx.new_page()

            def on_req(r):  # noqa: ANN001
                if API in r.url and r.post_data:
                    m = re.search(r"dataKey=([^&]+)", r.post_data)
                    if m:
                        data_key["v"] = m.group(1)

            def on_resp(r):  # noqa: ANN001
                if API in r.url:
                    try:
                        d = json.loads(r.text())
                    except Exception:  # noqa: BLE001
                        return
                    for it in d.get("datas", []):
                        rid = it.get("requestid")
                        if rid and rid not in seen:
                            seen.add(rid)
                            items.append(it)

            page.on("request", on_req)
            page.on("response", on_resp)
            page.goto(URL, wait_until="networkidle", timeout=60000)
            time.sleep(8)

            if "iam.bangcle.com" in page.url:
                raise OaSessionExpired(
                    "OA 会话过期：先 refresh_oa_session()（见 SKILL.md）"
                )

            dk = data_key["v"]
            for cur in range(2, max_pages + 1):
                if not dk:
                    break
                js = """
                async ({dk, cur}) => {
                  const r = await fetch('/api/ec/dev/table/datas', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/x-www-form-urlencoded'},
                    body: 'dataKey=' + dk + '&current=' + cur + '&sortParams=%5B%5D&'
                  });
                  return await r.text();
                }"""
                try:
                    d = json.loads(page.evaluate(js, {"dk": dk, "cur": cur}))
                    its = d.get("datas", [])
                except Exception:  # noqa: BLE001
                    break
                new = [i for i in its if i.get("requestid") not in seen]
                for i in new:
                    seen.add(i.get("requestid"))
                    items.append(i)
                if not its or not new:
                    break
        finally:
            browser.close()

    return [
        TodoItem.from_raw(i)
        for i in items
        if str(i.get("workflowid")) == str(workflow_id)
    ]
