"""Auth Gateway — 骨架测试。"""

import pytest
from datetime import datetime, timedelta
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from models import Identity, AuthRequest, AuthResult, AuthStatus
from auth_provider import AuthProvider, RateLimiter


class TestIdentityModel:
    def test_identity_creation(self):
        id_ = Identity(user_id="u1", channel="test", roles=["user"])
        assert id_.user_id == "u1"
        assert id_.has_role("user") is True
        assert id_.has_role("admin") is False
        assert id_.is_expired() is False

    def test_identity_expired(self):
        past = datetime.now() - timedelta(hours=1)
        id_ = Identity(user_id="u1", channel="test", expires_at=past)
        assert id_.is_expired() is True

    def test_identity_permissions(self):
        id_ = Identity(user_id="u1", channel="test", permissions=["read", "write"])
        assert id_.has_permission("read") is True
        assert id_.has_permission("delete") is False

    def test_identity_to_dict(self):
        id_ = Identity(user_id="u1", channel="test")
        d = id_.to_dict()
        assert d["user_id"] == "u1"
        assert "authenticated_at" in d


class TestAuthModels:
    def test_auth_request(self):
        req = AuthRequest(auth_type="token", channel="test",
                          credentials={"token": "abc"}, sender_ref="u1")
        assert req.auth_type == "token"
        assert req.credentials["token"] == "abc"

    def test_auth_result_ok(self):
        id_ = Identity(user_id="u1", channel="test")
        result = AuthResult(status=AuthStatus.SUCCESS, identity=id_)
        assert result.ok is True

    def test_auth_result_failed(self):
        result = AuthResult(status=AuthStatus.FAILED, error_code="INVALID_TOKEN")
        assert result.ok is False
        assert result.error_code == "INVALID_TOKEN"


class TestABCSkeleton:
    def test_auth_provider_cannot_instantiate(self):
        with pytest.raises(TypeError):
            AuthProvider()

    def test_rate_limiter_cannot_instantiate(self):
        with pytest.raises(TypeError):
            RateLimiter()

    def test_auth_provider_has_methods(self):
        assert hasattr(AuthProvider, "verify")
        assert hasattr(AuthProvider, "supports")

    def test_rate_limiter_has_methods(self):
        for m in ["allow", "remaining", "reset_at", "reset"]:
            assert hasattr(RateLimiter, m), f"RateLimiter missing {m}"
