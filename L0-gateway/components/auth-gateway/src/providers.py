"""Concrete Auth Providers — 具体认证提供者实现."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from auth_provider import AuthProvider
from models import AuthRequest, AuthResult, AuthStatus, Identity


class TokenAuthProvider(AuthProvider):
    """Bearer Token / JWT 认证.
    
    验证请求中的 token 字段，支持内存 token 存储。
    生产环境应替换为 JWT 验证或 OAuth introspection。
    """

    name = "token"

    def __init__(self, token_ttl: int = 3600) -> None:
        self._token_ttl = token_ttl
        # token → (user_id, expires_at)
        self._tokens: Dict[str, tuple[str, datetime]] = {}

    def issue_token(self, user_id: str, channel: str, roles: Optional[List[str]] = None) -> str:
        """签发一个 token."""
        token = hashlib.sha256(f"{user_id}:{channel}:{time.time()}:{uuid.uuid4()}".encode()).hexdigest()
        expires_at = datetime.now() + timedelta(seconds=self._token_ttl)
        self._tokens[token] = (user_id, expires_at)
        return token

    def verify(self, request: AuthRequest) -> AuthResult:
        """验证 token."""
        token = request.credentials.get("token", "")
        if not token:
            return AuthResult(
                status=AuthStatus.FAILED,
                error_code="MISSING_TOKEN",
                error_message="No token provided",
            )

        # 检查内存 token
        if token in self._tokens:
            user_id, expires_at = self._tokens[token]
            if datetime.now() > expires_at:
                del self._tokens[token]
                return AuthResult(
                    status=AuthStatus.EXPIRED,
                    error_code="TOKEN_EXPIRED",
                    error_message="Token has expired",
                )
            return AuthResult(
                status=AuthStatus.SUCCESS,
                identity=Identity(
                    user_id=user_id,
                    channel=request.channel,
                    roles=["authenticated"],
                    permissions=["message:send", "message:receive"],
                ),
            )

        return AuthResult(
            status=AuthStatus.FAILED,
            error_code="INVALID_TOKEN",
            error_message="Token not recognized",
        )

    def revoke(self, token: str) -> bool:
        """吊销 token."""
        if token in self._tokens:
            del self._tokens[token]
            return True
        return False

    def supports(self, auth_type: str) -> bool:
        return auth_type in ("token", "bearer", "jwt")

    def supported_types(self) -> List[str]:
        return ["token", "bearer", "jwt"]


class SignatureAuthProvider(AuthProvider):
    """签名认证 — 用于 WeCom / 钉钉等回调验证.
    
    验证请求签名，使用共享密钥 + 时间戳 + nonce 生成签名。
    """

    name = "signature"

    def __init__(self, secret: str = "") -> None:
        self._secret = secret

    def verify(self, request: AuthRequest) -> AuthResult:
        """验证签名."""
        signature = request.credentials.get("signature", "")
        timestamp = request.credentials.get("timestamp", "")
        nonce = request.credentials.get("nonce", "")

        if not signature or not timestamp:
            return AuthResult(
                status=AuthStatus.FAILED,
                error_code="MISSING_SIGNATURE",
                error_message="Signature or timestamp missing",
            )

        # 检查时间戳（5 分钟有效期）
        try:
            ts = float(timestamp)
            if abs(time.time() - ts) > 300:
                return AuthResult(
                    status=AuthStatus.EXPIRED,
                    error_code="SIGNATURE_EXPIRED",
                    error_message="Signature timestamp expired",
                )
        except (ValueError, TypeError):
            return AuthResult(
                status=AuthStatus.FAILED,
                error_code="INVALID_TIMESTAMP",
                error_message="Invalid timestamp format",
            )

        # 验证签名
        expected = self._compute_signature(timestamp, nonce)
        if not hmac.compare_digest(signature, expected):
            return AuthResult(
                status=AuthStatus.FAILED,
                error_code="INVALID_SIGNATURE",
                error_message="Signature mismatch",
            )

        return AuthResult(
            status=AuthStatus.SUCCESS,
            identity=Identity(
                user_id=request.sender_ref,
                channel=request.channel,
                roles=["webhook"],
                permissions=["message:send"],
            ),
        )

    def _compute_signature(self, timestamp: str, nonce: str) -> str:
        """计算签名."""
        raw = f"{self._secret}{timestamp}{nonce}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def supports(self, auth_type: str) -> bool:
        return auth_type == "signature"

    def supported_types(self) -> List[str]:
        return ["signature"]


class ApiKeyAuthProvider(AuthProvider):
    """API Key 认证."""

    name = "api_key"

    def __init__(self) -> None:
        # api_key → (user_id, roles, permissions)
        self._keys: Dict[str, tuple[str, List[str], List[str]]] = {}

    def register_key(self, api_key: str, user_id: str, roles: Optional[List[str]] = None, permissions: Optional[List[str]] = None) -> None:
        """注册 API Key."""
        self._keys[api_key] = (user_id, roles or ["api"], permissions or ["message:send"])

    def verify(self, request: AuthRequest) -> AuthResult:
        """验证 API Key."""
        api_key = request.credentials.get("api_key", "")
        if not api_key:
            return AuthResult(
                status=AuthStatus.FAILED,
                error_code="MISSING_API_KEY",
                error_message="No API key provided",
            )

        if api_key not in self._keys:
            return AuthResult(
                status=AuthStatus.FAILED,
                error_code="INVALID_API_KEY",
                error_message="API key not recognized",
            )

        user_id, roles, permissions = self._keys[api_key]
        return AuthResult(
            status=AuthStatus.SUCCESS,
            identity=Identity(
                user_id=user_id,
                channel=request.channel,
                roles=roles,
                permissions=permissions,
            ),
        )

    def revoke(self, api_key: str) -> bool:
        """吊销 API Key."""
        if api_key in self._keys:
            del self._keys[api_key]
            return True
        return False

    def supports(self, auth_type: str) -> bool:
        return auth_type == "api_key"

    def supported_types(self) -> List[str]:
        return ["api_key"]
