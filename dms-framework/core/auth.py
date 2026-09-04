"""
core/auth.py — JWT + API Key 双模式认证
FastAPI 依赖注入：get_current_user / require_api_key
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader, HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from core.saas import AuthProvider, AuthResult, TenantContext

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

def _get_config():
    """懒加载配置。"""
    from core.config import get_config
    return get_config()


def get_jwt_secret() -> str:
    return _get_config().jwt_secret


def get_jwt_algorithm() -> str:
    return _get_config().jwt_algorithm


def get_jwt_expire_hours() -> int:
    return _get_config().jwt_expire_hours


# 向后兼容的模块级变量
JWT_SECRET = "dms-framework-secret-change-in-production"
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 24

# ---------------------------------------------------------------------------
# 用户/Token 模型
# ---------------------------------------------------------------------------


class TokenData(BaseModel):
    """JWT payload 结构"""

    sub: str  # user_id
    tenant_id: str
    roles: list[str] = []
    permissions: list[str] = []
    exp: Optional[int] = None


class UserCredentials(BaseModel):
    username: str
    password: str


class ApiKeyCredentials(BaseModel):
    api_key: str


# ---------------------------------------------------------------------------
# 简易用户存储（L4 替换为数据库存储）
# ---------------------------------------------------------------------------

class InMemoryUserStore:
    """内存用户存储 — L3 验证用，L4 替换为数据库实现。

    密码格式: sha256(password + salt)
    """

    def __init__(self) -> None:
        self._users: dict[str, dict] = {}
        self._api_keys: dict[str, dict] = {}  # api_key -> {user_id, tenant_id, roles}

    def create_user(
        self,
        username: str,
        password: str,
        tenant_id: str = "system",
        roles: list[str] | None = None,
    ) -> str:
        """创建用户，返回 user_id。"""
        user_id = str(uuid.uuid4())
        salt = secrets.token_hex(16)
        pw_hash = hashlib.sha256(f"{password}{salt}".encode()).hexdigest()
        self._users[username] = {
            "user_id": user_id,
            "username": username,
            "password_hash": pw_hash,
            "salt": salt,
            "tenant_id": tenant_id,
            "roles": roles or ["user"],
        }
        return user_id

    def verify_password(self, username: str, password: str) -> Optional[dict]:
        """验证用户名密码，成功返回用户信息，失败返回 None。"""
        user = self._users.get(username)
        if not user:
            return None
        pw_hash = hashlib.sha256(f"{password}{user['salt']}".encode()).hexdigest()
        if not hmac.compare_digest(pw_hash, user["password_hash"]):
            return None
        return user

    def create_api_key(
        self,
        user_id: str,
        tenant_id: str,
        roles: list[str] | None = None,
        description: str = "",
    ) -> str:
        """创建 API Key，返回 key 字符串。"""
        raw_key = f"dms_{secrets.token_urlsafe(32)}"
        api_key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        self._api_keys[api_key_hash] = {
            "user_id": user_id,
            "tenant_id": tenant_id,
            "roles": roles or ["user"],
            "description": description,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        return raw_key

    def verify_api_key(self, api_key: str) -> Optional[dict]:
        """验证 API Key，成功返回 key 信息，失败返回 None。"""
        api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        return self._api_keys.get(api_key_hash)


# 全局实例
_user_store = InMemoryUserStore()


def get_user_store() -> InMemoryUserStore:
    """获取全局用户存储实例。"""
    return _user_store


# ---------------------------------------------------------------------------
# JWT 工具（纯 stdlib，无 PyJWT 依赖）
# ---------------------------------------------------------------------------

import base64
import json


def _base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _base64url_decode(data: str) -> bytes:
    padding = 4 - len(data) % 4
    if padding != 4:
        data += "=" * padding
    return base64.urlsafe_b64decode(data.encode("ascii"))


def _jwt_encode(payload: dict, secret: str) -> str:
    """简易 JWT 实现（HS256）。"""
    header = {"alg": JWT_ALGORITHM, "typ": "JWT"}
    header_b64 = _base64url_encode(json.dumps(header, separators=(",", ":")).encode())
    payload_b64 = _base64url_encode(json.dumps(payload, separators=(",", ":")).encode())
    signing_input = f"{header_b64}.{payload_b64}"
    signature = hmac.new(
        secret.encode(), signing_input.encode(), hashlib.sha256
    ).digest()
    sig_b64 = _base64url_encode(signature)
    return f"{signing_input}.{sig_b64}"


def _jwt_decode(token: str, secret: str) -> Optional[dict]:
    """简易 JWT 解码验证。"""
    parts = token.split(".")
    if len(parts) != 3:
        return None
    header_b64, payload_b64, sig_b64 = parts
    signing_input = f"{header_b64}.{payload_b64}"
    expected_sig = hmac.new(
        secret.encode(), signing_input.encode(), hashlib.sha256
    ).digest()
    actual_sig = _base64url_decode(sig_b64)
    if not hmac.compare_digest(expected_sig, actual_sig):
        return None
    try:
        payload = json.loads(_base64url_decode(payload_b64))
        # 检查过期
        exp = payload.get("exp")
        if exp and datetime.now(timezone.utc).timestamp() > exp:
            return None
        return payload
    except Exception:
        return None


# ---------------------------------------------------------------------------
# 认证 Provider 实现
# ---------------------------------------------------------------------------


class JWTAuthProvider(AuthProvider):
    """JWT + API Key 双模式认证提供者。"""

    def __init__(self, user_store: InMemoryUserStore | None = None) -> None:
        self._store = user_store or _user_store

    def authenticate(self, credentials: dict) -> AuthResult:
        """验证凭据。支持 password 和 api_key 两种模式。"""
        # API Key 模式
        if "api_key" in credentials:
            key_info = self._store.verify_api_key(credentials["api_key"])
            if key_info:
                return AuthResult(
                    success=True,
                    user_id=key_info["user_id"],
                    tenant_id=key_info["tenant_id"],
                    roles=key_info["roles"],
                )
            return AuthResult(success=False, error="Invalid API key")

        # 用户名密码模式
        if "username" in credentials and "password" in credentials:
            user = self._store.verify_password(credentials["username"], credentials["password"])
            if user:
                return AuthResult(
                    success=True,
                    user_id=user["user_id"],
                    tenant_id=user["tenant_id"],
                    roles=user["roles"],
                )
            return AuthResult(success=False, error="Invalid username or password")

        return AuthResult(success=False, error="No credentials provided")

    def authorize(self, user_id: str, resource: str, action: str) -> bool:
        """简易授权：默认全部放行。L4 实现细粒度权限。"""
        return True

    def get_tenant(self, user_id: str) -> str:
        return "system"


# ---------------------------------------------------------------------------
# FastAPI 安全依赖
# ---------------------------------------------------------------------------

_bearer_scheme = HTTPBearer(auto_error=False)
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Security(_bearer_scheme),
    api_key: str | None = Security(_api_key_header),
) -> TokenData:
    """FastAPI 依赖：从 Bearer Token 或 API Key 提取当前用户。

    优先 Bearer Token，其次 X-API-Key。
    """
    # 1. 尝试 Bearer Token
    if credentials and credentials.credentials:
        payload = _jwt_decode(credentials.credentials, get_jwt_secret())
        if payload:
            return TokenData(
                sub=payload["sub"],
                tenant_id=payload.get("tenant_id", "system"),
                roles=payload.get("roles", []),
                permissions=payload.get("permissions", []),
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    # 2. 尝试 API Key
    if api_key:
        key_info = _user_store.verify_api_key(api_key)
        if key_info:
            return TokenData(
                sub=key_info["user_id"],
                tenant_id=key_info["tenant_id"],
                roles=key_info["roles"],
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
    )


def create_access_token(
    user_id: str,
    tenant_id: str = "system",
    roles: list[str] | None = None,
    permissions: list[str] | None = None,
) -> str:
    """创建 JWT access token。"""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "tenant_id": tenant_id,
        "roles": roles or [],
        "permissions": permissions or [],
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=get_jwt_expire_hours())).timestamp()),
    }
    return _jwt_encode(payload, JWT_SECRET)
