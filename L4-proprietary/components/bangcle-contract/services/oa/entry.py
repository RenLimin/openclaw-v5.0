"""统一入口 — DETAIL §4.4 / VERIFICATION TC-OA-01~04。

get_contract_with_fallback(billid, out_dir)：
1. API 优先（CubeClient，storage_state 会话）
2. 会话失效（CubeAuthError）→ IAM 自愈（heal_session）→ 重试一次
3. API 仍失败（权限/网络/附件不可构造）→ 浏览器兜底（get_contract_via_browser）
4. 权限错误明确报"账号权限"，绝不伪造数据
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

from .cube import (
    CubeClient,
    CubeAuthError,
    CubePermissionError,
    CubeError,
    ContractData,
)
from .browser_fallback import (
    get_contract_via_browser,
    heal_session,
    BrowserFallbackError,
)


def _to_dict(data: Any) -> Dict[str, Any]:
    """兼容 ContractData 与 dict 两种返回形态。"""
    if isinstance(data, dict):
        return data
    if isinstance(data, ContractData):
        return data.to_dict()
    raise BrowserFallbackError("get_contract 返回类型异常: %r" % type(data))


def get_contract_with_fallback(
    billid: Any,
    out_dir: os.PathLike,
    storage_state: Optional[os.PathLike] = None,
    *,
    heal_once: bool = True,
) -> Dict[str, Any]:
    """拉取合同卡片：API 优先，自动降级浏览器兜底 + 会话自愈。"""
    client = CubeClient(storage_state=storage_state)

    # 1) API 优先
    try:
        data = client.get_contract(billid)
        return _finalize(client, data, out_dir)
    except CubeAuthError:
        pass  # 进入自愈
    except CubePermissionError:
        raise  # 权限阻塞，不伪造
    except CubeError:
        # 网络/非 JSON/附件不可构造 → 浏览器兜底
        return get_contract_via_browser(billid, out_dir, storage_state=storage_state)

    # 2) 会话自愈 + 重试一次
    if heal_once and heal_session():
        client.reload_session()
        try:
            data = client.get_contract(billid)
            result = _finalize(client, data, out_dir)
            result["session_healed"] = True
            return result
        except CubePermissionError:
            raise
        except CubeError as e:
            raise BrowserFallbackError("自愈后仍失败: %s" % e) from e
    raise BrowserFallbackError("会话失效且自愈失败")


def _finalize(client, data, out_dir) -> Dict[str, Any]:
    """结构化结果 + 附件落盘（可确定 URL 的；失败项带 error 不阻断）。"""
    result = _to_dict(data)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    local = []
    for ref in data.attachments if isinstance(data, ContractData) else []:
        try:
            path = client.download_attachment(ref, out)
            local.append({"name": ref.name, "local_path": str(path)})
        except CubeError as e:
            local.append({"name": ref.name, "error": str(e)})
    result["attachments_local"] = local
    result["fallback"] = False
    return result
