"""浏览器自动化兜底 — DETAIL §4.4（复用 BDMS，不重造）。

触发场景（get_contract_with_fallback 内部判断）：
- Cube REST 403 / 非 JSON / 网络异常
- 附件 URL 不可构造（懒加载/加密传输）
- 会话失效且 storage_state 无法重建

实现：引用 BDMS browser_adapter（CDP 复用登录态 Chrome / IAM headless 重登），
在 Cube 卡片 iframe#mainFrame 内提取字段与附件。凭据只读 ~/.openclaw/secrets/。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional


class BrowserFallbackError(RuntimeError):
    """浏览器兜底失败（含账号权限、无凭据、无 CDP 等）。"""


def _bdms_adapter_module():
    """sys.path 注入 BDMS 适配器并返回模块（只引用，不复制）。"""
    candidates = [
        os.path.join(
            Path(__file__).resolve().parents[3],   # bangcle-contract
            "bdms", "src",
        ),
    ]
    for c in candidates:
        if os.path.isdir(c) and c not in os.sys.path:
            os.sys.path.insert(0, c)
    try:
        from bdms.modules.integration.adapters import browser_adapter as ba
        return ba
    except Exception as e:  # noqa: BLE001
        raise BrowserFallbackError("BDMS browser_adapter 不可用: %s" % e) from e


def _iam_credentials_from_secrets() -> tuple:
    """从 ~/.openclaw/secrets/iam.username / iam.password 读取。"""
    base = Path.home() / ".openclaw" / "secrets"
    u = base / "iam.username"
    p = base / "iam.password"
    username = u.read_text(encoding="utf-8").strip() if u.exists() else ""
    password = p.read_text(encoding="utf-8").strip() if p.exists() else ""
    return username, password


# OA 会话探针：侦察期记录的真实 billid（仅用于验证会话有效性，非业务数据）
OA_PROBE_BILLID = "15134"
# 换票后 ecology 会话 cookie 名（泛微 e-cology 9 实测）
ECOLOGY_SESSION_COOKIE = "ecology_JSessionid"
# storage_state 落盘位置（与 cube.DEFAULT_STORAGE_STATE 一致）
OA_STORAGE_STATE = Path.home() / ".openclaw" / "data" / "clm-oa-recon" / "state.json"


def refresh_oa_session(timeout: float = 60.0) -> bool:
    """真实建立 OA ecology 会话：IAM 登录 → 点应用卡片换票 → 落盘 storage_state。

    2026-10-29 实测（memory/2026-10-27 侦察结论的工程化）：
    - 直导 OA / 跨 context 注入 cookie 都不能建立 ecology 会话；
    - 必须 IAM headless 登录后，在 home 页点击「OA协同办公平台」应用卡片
      触发 SSO 换票，OA 才会下发 ecology_JSessionid；
    - 换票后把 context cookies 落盘为 storage_state，CubeClient 即可复用。

    诚实性：
    - 落盘前用 CubeClient（读 storage_state）对探针 billid 做 checkCardRight，
      HTTP 200 + status 非 false 才算成功；否则返回 False，绝不假报成功。

    Returns:
        True 会话已建立且验证通过 / False 失败（无凭据、登录失败、换票失败）
    """
    ba = _bdms_adapter_module()
    try:
        try:
            username, password = ba._iam_credentials()
        except Exception:  # noqa: BLE001
            username, password = _iam_credentials_from_secrets()
        if not username or not password:
            raise BrowserFallbackError("IAM 凭据缺失（secrets 未配置）")

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise BrowserFallbackError(
                "Playwright 不可用（pip install playwright && playwright install chromium）")

        env = {**os.environ, "NO_PROXY": "*", "no_proxy": "*"}
        iam_base = getattr(ba, "IAM_BASE", "https://iam.bangcle.com")

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, env=env)
            try:
                context = browser.new_context()
                page = context.new_page()
                page.goto(iam_base + "/#/login", timeout=60000)
                page.wait_for_load_state("networkidle", timeout=30000)
                page.wait_for_timeout(5000)
                page.locator("input[type=text]").first.fill(username)
                page.locator("input[type=password]").first.fill(password)
                page.locator("button").nth(1).click()
                page.wait_for_timeout(3000)
                captcha = page.locator(
                    "input[placeholder*=验证码],input[placeholder*=captcha]")
                if captcha.count() > 0:
                    code = ba._fetch_iam_captcha()
                    if not code:
                        return False  # 取码失败，不消耗重试
                    captcha.first.fill(code)
                    page.locator("button").nth(1).click()

                # 登录结果以 DOM 为准（IAM SPA hash 不切 #/home 的竞态，实测）
                if not _wait_for(lambda: _iam_home_dom(page), timeout=timeout):
                    return False

                page.wait_for_timeout(6000)
                # 点「OA协同办公平台」应用卡片换票（JS handler 需 dispatchEvent）
                clicked = _click_oa_app_card(page)
                if not clicked:
                    return False
                page.wait_for_timeout(12000)

                # 等 ecology cookie 出现
                if not _wait_for(lambda: _has_ecology_cookie(context), timeout=25):
                    return False

                # 落盘 storage_state
                OA_STORAGE_STATE.parent.mkdir(parents=True, exist_ok=True)
                OA_STORAGE_STATE.write_text(
                    json.dumps({"cookies": context.cookies(), "origins": []}),
                    encoding="utf-8")

                # 用 CubeClient 走真实读路径验证会话有效性（不打印 cookie）
                return _verify_oa_session()
            finally:
                browser.close()
    except BrowserFallbackError:
        raise
    except Exception as e:  # noqa: BLE001
        raise BrowserFallbackError("OA 会话建立异常: %s" % e) from e


def heal_session() -> bool:
    """会话自愈（与 get_contract_with_fallback 契约一致）：真实重建 OA 会话。

    Returns:
        True 自愈成功（会话已落盘且验证通过）/ False 失败
    """
    return refresh_oa_session()


def _wait_for(pred, timeout: float = 60.0) -> bool:
    import time
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            if pred():
                return True
        except Exception:  # noqa: BLE001
            pass
        time.sleep(2)
    return False


def _iam_home_dom(page) -> bool:
    """IAM home 判定：内容含 任立民/首页 且 120 字符内无"登录"（不看 URL hash）。"""
    try:
        text = page.evaluate(
            "function(){return document.body?document.body.innerText.slice(0,400):''}")
    except Exception:  # noqa: BLE001
        return False
    return ("任立民" in text or "首页" in text) and "登录" not in text[:120]


def _click_oa_app_card(page) -> bool:
    """在 IAM home 点击「OA协同办公平台」应用卡片（ES5 脚本，dispatchEvent 触发 handler）。"""
    try:
        return bool(page.evaluate("""function(){
          var all=document.querySelectorAll('div,span,li,a');
          for(var i=0;i<all.length;i++){
            var e=all[i];
            var t=(e.innerText||'').trim();
            if(t.indexOf('OA协同办公平台')>=0){
              var ev=new MouseEvent('click',{bubbles:true,cancelable:true,view:window});
              e.dispatchEvent(ev);
            }
          }
          return true;
        }"""))
    except Exception:  # noqa: BLE001
        return False


def _has_ecology_cookie(context) -> bool:
    try:
        for c in context.cookies():
            if c.get("name") == ECOLOGY_SESSION_COOKIE:
                return True
    except Exception:  # noqa: BLE001
        pass
    return False


def _verify_oa_session() -> bool:
    """CubeClient 读 storage_state 对探针 billid 做 checkCardRight，验证真实可用。"""
    try:
        from .cube import CubeClient, CubeAuthError, CubePermissionError, CubeError
        client = CubeClient(timeout=15)
        resp = client.check_card_right(OA_PROBE_BILLID)
        return isinstance(resp, dict) and resp.get("status") is not False
    except (CubeAuthError, CubePermissionError, CubeError):
        return False
    except Exception:  # noqa: BLE001
        return False


def get_contract_via_browser(billid: Any, out_dir: os.PathLike,
                             storage_state: Optional[os.PathLike] = None) -> Dict[str, Any]:
    """浏览器兜底拉取：CDP 复用登录态 Chrome → Cube 卡片 iframe#mainFrame。

    Args:
        billid: 建模记录主键
        out_dir: 附件落盘目录
        storage_state: Playwright storage_state（未提供用默认侦察路径）

    Returns:
        {"billid", "main_fields", "attachments": [{"name","local_path"}], "fallback": True}

    Raises:
        BrowserFallbackError: CDP 不可用 / 页面无卡片 / 权限不足
    """
    ba = _bdms_adapter_module()
    adapter = None
    try:
        adapter = ba.BrowserAdapter(headless=False)
        adapter.__enter__()
        adapter.launch()  # 尝试 CDP；失败则内部兜底启动新 Chrome
        # 导航 Cube 卡片（SPA hash 路由；BDMS 提供 navigate 与 iframe 内定位）
        card_url = (
            "https://oa.bangcle.com/spa/cube/index.html#/main/cube/card"
            "?type=0&modeId=112&formId=-249&billid=%s&customid=179" % billid
        )
        adapter.navigate(card_url, wait_network_idle=True)
        # 等待 mainFrame 出现并提取文本/字段（ES5 兼容脚本由 BDMS evaluate 执行）
        frame_js = (
            "(function(){"
            "  var f = document.getElementById('mainFrame');"
            "  if (!f) { return {ok:false, err:'no mainFrame'}; }"
            "  var d = f.contentDocument;"
            "  if (!d) { return {ok:false, err:'no frame doc'}; }"
            "  return {ok:true, text: d.body ? d.body.innerText.substring(0,20000) : ''};"
            "})()"
        )
        result = adapter.evaluate(frame_js)
        if not result or result.get("ok") is not True:
            raise BrowserFallbackError(
                "Cube 卡片未加载（%s）" % (result.get("err") if result else "无响应")
            )
        text = result.get("text", "")
        if "登录" in text[:500] or "超时" in text[:500]:
            raise BrowserFallbackError("浏览器会话失效，需重登")

        attachments = []
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        # 附件：BDMS 不提供通用下载；这里把正文文本落盘作为可追溯产物，
        # 附件二进制走 CubeClient.download_attachment（REST 会话）或人工确认。
        txt_path = out / ("billid_%s_card.txt" % billid)
        txt_path.write_text(text, encoding="utf-8")

        return {
            "billid": str(billid),
            "main_fields": {},
            "attachments": [{"name": txt_path.name, "local_path": str(txt_path)}],
            "card_text_snippet": text[:2000],
            "fallback": True,
        }
    except BrowserFallbackError:
        raise
    except Exception as e:  # noqa: BLE001
        raise BrowserFallbackError("浏览器兜底失败: %s" % e) from e
    finally:
        if adapter is not None:
            try:
                adapter.__exit__(None, None, None)
            except Exception:  # noqa: BLE001
                pass
