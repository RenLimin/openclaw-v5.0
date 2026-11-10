"""services.oa.ledger — 按合同编号检索 Cube 台账并解析 billid（固化版）。

背景（2026-11-10 固化）：
- 能力已于 2026-11-10 14:40 生产验证（建行 PPT 15/15 合同：Cube 台账 modeId=112
  检索 → billid → loadlink 加密鉴权下载 → /tmp/ccb_contracts/<合同号>/）。
- 该管线此前只存在于 /tmp 临时脚本，未固化进组件；本模块将其沉淀为常驻能力。
- 复用 services.oa 既有组件（CubeClient / get_contract_with_fallback /
  browser_fallback.heal_session），不重造下载与会话逻辑。

流程：
  1) 会话预检（CubeClient check_card_right；失效可 heal_session 重建）
  2) Playwright 打开 Cube 台账检索页（modeId=112），按「合同编号」筛选，
     收集结果 → 解析 billid（href/onclick/文本多模式）
  3) 对 billid 调 get_contract_with_fallback 拉卡片 + 附件落盘
  4) 写 manifest.json（合同号→billid→文件清单）
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

# Cube 台账检索页（与 helpers 常量一致；formId/customid 见 helpers.py）
LEDGER_SEARCH_URL = (
    "https://oa.bangcle.com/spa/cube/index.html#/main/cube/search"
    "?modeId=112&formId=-249&customid=179"
)

# 会话 state 默认路径（与 cube.DEFAULT_STORAGE_STATE 一致）
DEFAULT_STORAGE_STATE = (
    Path.home() / ".openclaw" / "data" / "clm-oa-recon" / "state.json"
)

# 会话探针 billid（browser_fallback 同款，仅用于验证会话有效性）
PROBE_BILLID = "15134"


class LedgerError(RuntimeError):
    """台账检索/拉取失败。"""


# ---------------------------------------------------------------
# 纯函数：从 DOM/HTML 文本解析 billid（可离线单测）
# ---------------------------------------------------------------

_BILLID_RE = re.compile(r"(?:billid[=:\"'?\s]*|open(?:Card|Detail)?\s*\(['\"\s]*)(\d{1,18})", re.IGNORECASE)
_CONTRACT_NO_RE = re.compile(r"XSZS[-A-Za-z0-9]*", re.IGNORECASE)


def extract_billids(text: str) -> List[str]:
    """从任意 HTML 片段/JS 字符串提取 billid（去重保序）。

    覆盖 href（?billid=15134）、onclick（openCard(15134)）、JSON 等形态。
    """
    seen: List[str] = []
    for m in _BILLID_RE.finditer(text or ""):
        v = m.group(1)
        if v not in seen:
            seen.append(v)
    return seen


def parse_search_results(page_text: str) -> List[Dict[str, Any]]:
    """从台账检索结果（锚点）解析 [{contract_no, billid, title}]。

    - <a href="...billid=NNN" onclick="...">XSZS...</a>
    """
    results: List[Dict[str, Any]] = []
    seen: set = set()
    for a_m in re.finditer(
        r"<a[^>]*>(.*?)</a>", page_text or "", re.IGNORECASE | re.DOTALL
    ):
        a_tag = a_m.group(0)
        inner = re.sub(r"<[^>]+>", "", a_m.group(1)).strip()
        billids = extract_billids(a_tag)
        if not billids:
            continue
        billid = billids[0]
        no_m = _CONTRACT_NO_RE.search(inner)
        contract_no = no_m.group(0).upper() if no_m else inner[:40]
        key = (contract_no, billid)
        if key in seen:
            continue
        seen.add(key)
        results.append(
            {"contract_no": contract_no, "billid": billid, "title": inner[:80]}
        )
    return results


# ---------------------------------------------------------------
# 台账检索（Playwright，复用 storage_state 会话）
# ---------------------------------------------------------------

_FILL_JS = r"""
function(){
  var labs=[].slice.call(document.querySelectorAll('*')).filter(function(e){
    return e.children.length===0 && (e.innerText||'').trim()==='合同编号';
  });
  for(var i=0;i<labs.length;i++){
    var cur=labs[i];
    for(var k=0;k<5;k++){ if(cur.parentElement) cur=cur.parentElement; }
    var inp=cur? cur.querySelector('input') : null;
    if(inp){
      var setter=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;
      setter.call(inp,'__VALUE__');
      inp.dispatchEvent(new Event('input',{bubbles:true}));
      inp.dispatchEvent(new Event('change',{bubbles:true}));
      return true;
    }
  }
  return false;
}
"""

_COLLECT_JS = (
    "function(){"
    "var as=document.querySelectorAll('a');"
    "if(!as.length) return '';"
    "return [].map.call(as,function(a){return a.outerHTML.substring(0,300);}).join('\\n');"
    "}"
)


def search_billids(
    contract_no: str,
    storage_state: Optional[os.PathLike] = None,
    *,
    headless: bool = True,
    wait_ms: int = 8000,
) -> List[Dict[str, Any]]:
    """在 Cube 台账检索合同编号，返回 [{contract_no, billid, title}]。

    Raises:
        LedgerError: Playwright 不可用 / 会话失效（跳登录）/ 无结果
    """
    state = Path(storage_state) if storage_state else DEFAULT_STORAGE_STATE
    if not state.exists():
        raise LedgerError(
            "OA storage_state 不存在（%s）；先执行 contractctl oa-login" % state
        )

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise LedgerError(
            "Playwright 不可用（pip install playwright && playwright install chromium）"
        )

    env = {**os.environ, "NO_PROXY": "*", "no_proxy": "*"}
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=headless, env=env)
            try:
                ctx = browser.new_context(storage_state=str(state))
                pg = ctx.new_page()
                pg.goto(LEDGER_SEARCH_URL, timeout=60000)
                pg.wait_for_timeout(wait_ms)

                cur = pg.url
                if "iam.bangcle.com" in cur or "login" in cur.lower():
                    raise LedgerError(
                        "OA 会话已失效（跳转登录页）；先 contractctl oa-login 重建会话"
                    )

                filled = pg.evaluate(_FILL_JS.replace("__VALUE__", contract_no))
                if not filled:
                    # 兜底：首个文本输入框
                    try:
                        pg.locator(
                            "input[type=text],input:not([type])"
                        ).first.fill(contract_no)
                        filled = True
                    except Exception:  # noqa: BLE001
                        filled = False
                if not filled:
                    raise LedgerError(
                        "台账页未找到合同编号筛选框（DOM 变化，需人工复核）"
                    )

                pg.keyboard.press("Enter")
                pg.wait_for_timeout(6000)

                html = pg.evaluate(_COLLECT_JS)
                results = parse_search_results(html)
                if not results:
                    body = pg.evaluate(
                        "function(){return document.body?document.body.innerText.substring(0,30000):'';}"
                    )
                    for b in extract_billids(body)[:20]:
                        results.append(
                            {"contract_no": contract_no, "billid": b, "title": ""}
                        )
                return results
            finally:
                browser.close()
    except LedgerError:
        raise
    except Exception as e:  # noqa: BLE001
        raise LedgerError("台账检索异常: %s" % e) from e


# ---------------------------------------------------------------
# 完整拉取：合同号 → billid → 卡片 + 附件落盘
# ---------------------------------------------------------------

def fetch_contract_by_no(
    contract_no: str,
    out_dir: Optional[os.PathLike] = None,
    storage_state: Optional[os.PathLike] = None,
    *,
    heal_if_expired: bool = False,
) -> Dict[str, Any]:
    """按合同编号拉取合同原文/附件（台账检索 → billid → 复用既有拉取链路）。

    Args:
        contract_no: 合同编号（如 XSZS2609020659）
        out_dir: 落盘目录（默认 data/oa_contracts/<contract_no>）
        heal_if_expired: 会话失效时自动 heal_session（耗一次 IMAP 验证码）

    Returns:
        {"contract_no", "billid", "files": [...], "matched": [...],
         "manifest_path", "fallback", "session_healed"}

    Raises:
        LedgerError: 无会话 / 检索无结果 / 拉取失败
    """
    out = (
        Path(out_dir)
        if out_dir
        else Path(__file__).resolve().parents[1] / "data" / "oa_contracts" / contract_no
    )
    out.mkdir(parents=True, exist_ok=True)

    # 1) 会话预检（复用 CubeClient 探针）
    from .cube import CubeClient, CubeAuthError, CubePermissionError, CubeError
    client = CubeClient(storage_state=storage_state, timeout=15)
    try:
        client.check_card_right(PROBE_BILLID)
        session_ok = True
    except CubeAuthError:
        session_ok = False
    except (CubePermissionError, CubeError):
        session_ok = True  # 非会话问题，检索照走
    if not session_ok:
        if heal_if_expired:
            from .browser_fallback import heal_session
            if not heal_session():
                raise LedgerError(
                    "OA 会话失效且自愈失败；检查 secrets 或网络"
                )
            client.reload_session()
        else:
            raise LedgerError(
                "OA 会话已失效；先 contractctl oa-login（耗一次 IMAP 验证码）"
            )

    # 2) 台账检索 → billid
    matches = search_billids(contract_no, storage_state=storage_state)
    if not matches:
        raise LedgerError("台账检索无结果：%s" % contract_no)
    exact = [m for m in matches if m["contract_no"] == contract_no]
    chosen = exact or matches
    billid = chosen[0]["billid"]

    # 3) 拉卡片 + 附件（API→自愈→浏览器兜底 全链路）
    from .entry import get_contract_with_fallback
    data = get_contract_with_fallback(billid, out, storage_state=storage_state)

    # 4) manifest
    files = [
        {
            "name": f.get("name"),
            "local_path": f.get("local_path"),
            "error": f.get("error"),
        }
        for f in data.get("attachments_local", [])
    ]
    manifest = {
        "contract_no": contract_no,
        "billid": billid,
        "matched": chosen,
        "files": files,
        "fallback": data.get("fallback", False),
        "session_healed": data.get("session_healed", False),
        "fetched_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
    }
    mp = out / "manifest.json"
    mp.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    manifest["manifest_path"] = str(mp)
    return manifest
