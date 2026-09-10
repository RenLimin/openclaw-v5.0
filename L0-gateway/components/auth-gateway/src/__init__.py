"""Auth Gateway — 认证网关组件（骨架）。"""

from models import Identity, AuthRequest, AuthResult, AuthStatus
from auth_provider import AuthProvider, RateLimiter

__all__ = ["Identity", "AuthRequest", "AuthResult", "AuthStatus", "AuthProvider", "RateLimiter"]
