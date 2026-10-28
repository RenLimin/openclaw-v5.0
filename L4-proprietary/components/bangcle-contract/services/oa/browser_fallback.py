"""浏览器自动化兜底 — DETAIL §4.4（复用 BDMS，不重造）。

触发场景（get_contract_with_fallback 内部判断）：
- Cube REST 403 / 非 JSON / 网络异常
- 附件 URL 不可构造（懒加载/加密传输）
- 会话失效且 storage_state 无法重建

实现：引用 BDMS browser_adapter（CDP 复用登录态 Chrome / IAM headless 重登），
在 Cube 卡片 iframe#mainFrame 内提取字段与附件。凭据只读 ~/.openclaw/secrets/。
"""

from __future__ import annotations

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


def heal_session() -> bool:
    """会话自愈：BDMS IAM headless 登录（IMAP 验证码流程在 BDMS 内），
    成功后 BDMS 回写 cookie 池与 storage_state 供 CubeClient 复用。

    Returns:
        True 自愈成功 / False 失败（无凭据、登录失败）
    """
    ba = _bdms_adapter_module()
    try:
        # 优先复用 BDMS 凭据加载逻辑；失败则本地 secrets 读取
        try:
            username, password = ba._iam_credentials()
        except Exception:  # noqa: BLE001
            username, password = _iam_credentials_from_secrets()
        if not username or not password:
            raise BrowserFallbackError("IAM 凭据缺失（secrets 未配置）")
        ok = ba.login_iam(username, password)
        if not ok:
            return False
        # BDMS 登录后重写侦察 storage_state 位置，供 CubeClient 重新加载
        ba.set_cookie("oa.bangcle.com", ba.get_cookie("oa.bangcle.com") or "")
        return True
    except BrowserFallbackError:
        raise
    except Exception as e:  # noqa: BLE001
        raise BrowserFallbackError("IAM 自愈异常: %s" % e) from e


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
