"""services.oa — 泛微 e-cology 9 / 建模引擎 Cube 集成（段 2b：P6）。

- cube.CubeClient             Cube 内部 REST（storage_state 会话，API 优先）
- browser_fallback            CDP + iframe#mainFrame 浏览器兜底（复用 BDMS）
- get_contract_with_fallback  统一入口：API 优先，浏览器兜底 + 会话自愈

合同原文为 OA 入站拉取，全程本地，不外发；凭据仅来自 ``~/.openclaw/secrets/``。
"""

from .cube import (
    CubeClient,
    CubeError,
    CubeAuthError,
    CubePermissionError,
    ContractData,
    AttachmentRef,
)
from .browser_fallback import (
    get_contract_via_browser,
    heal_session,
    BrowserFallbackError,
)
from .entry import get_contract_with_fallback

__all__ = [
    "CubeClient",
    "CubeError",
    "CubeAuthError",
    "CubePermissionError",
    "ContractData",
    "AttachmentRef",
    "get_contract_via_browser",
    "heal_session",
    "BrowserFallbackError",
    "get_contract_with_fallback",
]
