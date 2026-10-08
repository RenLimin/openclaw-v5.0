"""企微 API 适配器 — 通过企微开放平台 API 获取文档内容。

对齐 DESIGN-DETAIL-INTEGRATION-v2.1.md §6.4。
企微文档 API 需要 corpId + corpSecret + agentId。
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class WecomApiError(Exception):
    """企微 API 错误。"""
    pass


class WecomApiAdapter:
    """企微 API 适配器。

    通过企微开放平台 API 获取文档内容。
    需要凭据：corpId + corpSecret + agentId。
    """

    API_BASE = "https://qyapi.weixin.qq.com/cgi-bin"

    def __init__(self, corp_id: str = "", corp_secret: str = "", agent_id: str = ""):
        """
        Args:
            corp_id: 企业 ID
            corp_secret: 应用密钥
            agent_id: 应用 ID
        """
        self._corp_id = corp_id
        self._corp_secret = corp_secret
        self._agent_id = agent_id
        self._access_token = ""
        self._token_expires_at = 0.0

    def configure(self, corp_id: str, corp_secret: str, agent_id: str = "") -> None:
        """配置企微 API 凭据。"""
        self._corp_id = corp_id
        self._corp_secret = corp_secret
        self._agent_id = agent_id
        self._access_token = ""
        self._token_expires_at = 0.0

    def is_configured(self) -> bool:
        """检查是否已配置凭据。"""
        return bool(self._corp_id and self._corp_secret)

    def get_access_token(self) -> str:
        """获取 access_token（带缓存）。"""
        if self._access_token and time.time() < self._token_expires_at:
            return self._access_token

        if not self.is_configured():
            raise WecomApiError("企微 API 凭据未配置")

        import urllib.request
        import urllib.error

        url = (
            f"{self.API_BASE}/gettoken"
            f"?corpid={self._corp_id}&corpsecret={self._corp_secret}"
        )

        try:
            with urllib.request.urlopen(url, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if "access_token" in data:
                    self._access_token = data["access_token"]
                    self._token_expires_at = time.time() + data.get("expires_in", 7200) - 300
                    return self._access_token
                else:
                    raise WecomApiError(f"获取 token 失败: {data}")
        except urllib.error.URLError as e:
            raise WecomApiError(f"网络错误: {e}")
        except json.JSONDecodeError:
            raise WecomApiError("API 返回非 JSON 数据")

    def list_documents(self, doc_type: str = "", date_range: str = "") -> List[Dict]:
        """获取文档列表。

        企微 API 目前不直接支持文档列表查询，
        这里返回空列表，实际通过浏览器或本机导入获取。
        """
        # 企微 API 限制：文档 API 可能不支持直接列出
        # 降级：返回空列表，由调用方走浏览器或本机导入
        logger.warning("企微 API 不支持直接列出文档，返回空列表")
        return []

    def get_document_content(self, doc_id: str) -> Dict:
        """获取文档内容。

        企微 API 目前不直接支持获取文档内容，
        返回空内容，实际通过浏览器或本机导入获取。
        """
        logger.warning(f"企微 API 不支持直接获取文档内容: {doc_id}，返回空内容")
        return {}

    def get_status(self) -> Dict:
        """获取适配器状态。"""
        return {
            "configured": self.is_configured(),
            "has_token": bool(self._access_token),
            "token_expires_in": max(0, self._token_expires_at - time.time()),
        }
