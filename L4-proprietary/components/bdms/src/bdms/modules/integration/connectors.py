# 🔒 NO_TOKEN — 纯代码，零 AI 依赖
"""I-01~I-04 浏览器/API 类连接器骨架。

对齐 DESIGN-DETAIL-INTEGRATION-v2.1.md §6.1-6.4。
浏览器自动化（osascript/Playwright）依赖运行环境与登录态，
本文件提供完整接口骨架 + 数据口径定义，实际抓取逻辑在 Phase 8 Web UI
联调时按环境实测补齐（macOS osascript 已在 ONES 数据导出中验证可用）。
"""
from __future__ import annotations

import subprocess
import sys
from typing import Any, Dict, List

from .base import BaseConnector, ConnectorRegistry


def _browser_available() -> bool:
    """macOS osascript 可用性检查。"""
    if sys.platform != "darwin":
        return False
    try:
        subprocess.run(["osascript", "-e", 'return "ok"'],
                       capture_output=True, timeout=5)
        return True
    except Exception:
        return False


@ConnectorRegistry.register
class OnesConnector(BaseConnector):
    """I-01: ONES 连接器 — 浏览器自动化 CSV 导出。

    数据口径（黄金基准）:
    - 签约合同导出: ~15,682 行 × 55 列
    - POC&提前实施: ~4,270 行 × 55 列
    - 异常项目处置: ~352 行 × 55 列
    """

    name = "ones"
    data_source = "ONES 项目管理"
    target_modules = ["delivery_report", "project_management"]
    auth_type = "browser_cookie"
    default_frequency = "manual"

    def authenticate(self) -> bool:
        """认证 = 浏览器登录态检查。"""
        return _browser_available()

    def fetch(self, filter_id: str = "", month: str = "", **params) -> List[Dict]:
        """导出 ONES 数据（浏览器自动化）。

        实际实现: osascript 控制 Chrome 打开 ONES → 导出 CSV → 读文件。
        当前: 返回空（待 Web UI 联调时实测补齐）。
        """
        # 浏览器自动化导出流程（macOS osascript 已验证）
        # 具体实现依赖 ONES 登录态，Phase 8 联调补齐
        return []

    def normalize(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """ONES CSV 列 → 标准字段。"""
        return raw.get("data", raw)


@ConnectorRegistry.register
class OaConnector(BaseConnector):
    """I-02: OA 连接器 — 浏览器自动化页面抓取（合同信息）。"""

    name = "oa"
    data_source = "OA 系统"
    target_modules = ["contract_management"]
    auth_type = "browser_cookie"
    default_frequency = "manual"

    def authenticate(self) -> bool:
        return _browser_available()

    def fetch(self, contract_type: str = "", date_range: str = "",
              **params) -> List[Dict]:
        return []

    def normalize(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        return raw.get("data", raw)


@ConnectorRegistry.register
class TimesheetConnector(BaseConnector):
    """I-03: 工时门户连接器 — 浏览器自动化 Excel 导出。"""

    name = "timesheet"
    data_source = "工时填报门户"
    target_modules = ["profit_management"]
    auth_type = "browser_cookie"
    default_frequency = "monthly"

    def authenticate(self) -> bool:
        return _browser_available()

    def fetch(self, project_id: str = "", month: str = "", **params) -> List[Dict]:
        return []

    def normalize(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        return raw.get("data", raw)


@ConnectorRegistry.register
class WecomDocConnector(BaseConnector):
    """I-04: 企微文档连接器 — API → 浏览器 → 本机导入三级降级。"""

    name = "wecom_doc"
    data_source = "企业微信文档"
    target_modules = ["delivery_report"]
    auth_type = "api_token"
    default_frequency = "manual"

    # 降级链: API → 浏览器 → 本机导入
    FALLBACK_CHAIN = ["api", "browser", "local_file"]

    def authenticate(self) -> bool:
        """API token 可用性（无 token 时走降级链）。"""
        return True  # 总是可用（走降级链）

    def fetch(self, doc_type: str = "", date_range: str = "",
              file_path: str = "", **params) -> List[Dict]:
        """三级降级获取。file_path 提供时直接走本机导入。"""
        if file_path:
            # 降级到 local_import
            from .local_import_connector import LocalImportConnector
            lc = LocalImportConnector(db_path=self.db_path)
            return lc.fetch(file_path=file_path)
        return []

    def normalize(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        return raw.get("data", raw)
