"""Channel Router — 骨架测试。

验证 ABC 不可实例化、接口签名完整、数据模型序列化正确。
"""

import pytest
from datetime import datetime

# 确保 src 目录在 sys.path 中
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from models import InternalMessage, RouteTarget, SendResult, SendStatus, Attachment, IdentityRef, MessageDirection
from router import Router
from channel_adapter import ChannelAdapter


class TestModels:
    """数据模型测试。"""

    def test_internal_message_creation(self):
        sender = IdentityRef(user_id="u1", channel="test")
        msg = InternalMessage(
            message_id="m1",
            channel="test",
            sender=sender,
            session_id="s1",
            content="hello",
        )
        assert msg.message_id == "m1"
        assert msg.direction == MessageDirection.INBOUND
        assert isinstance(msg.timestamp, datetime)

    def test_internal_message_to_dict(self):
        sender = IdentityRef(user_id="u1", channel="test", display_name="Test")
        msg = InternalMessage(
            message_id="m1",
            channel="test",
            sender=sender,
            session_id="s1",
            content="hi",
        )
        d = msg.to_dict()
        assert d["message_id"] == "m1"
        assert d["sender"]["user_id"] == "u1"
        assert "timestamp" in d
        assert isinstance(d["attachments"], list)

    def test_route_target_creation(self):
        rt = RouteTarget(target_type="agent", target_id="main", agent_id="agent-1")
        assert rt.target_type == "agent"
        assert rt.agent_id == "agent-1"

    def test_send_result_ok_property(self):
        success = SendResult(status=SendStatus.SUCCESS, message_id="m1")
        failed = SendResult(status=SendStatus.FAILED, error_code="E001")
        assert success.ok is True
        assert failed.ok is False


class TestABCSkeleton:
    """ABC 抽象基类骨架测试。"""

    def test_router_cannot_be_instantiated(self):
        with pytest.raises(TypeError):
            Router()

    def test_channel_adapter_cannot_be_instantiated(self):
        with pytest.raises(TypeError):
            ChannelAdapter()

    def test_router_has_required_methods(self):
        methods = [
            "route_inbound", "route_outbound", "register_adapter",
            "unregister_adapter", "list_adapters", "get_adapter", "health_check"
        ]
        for m in methods:
            assert hasattr(Router, m), f"Router missing method: {m}"

    def test_channel_adapter_has_required_methods(self):
        methods = ["receive", "send", "to_internal", "from_internal", "health_check"]
        for m in methods:
            assert hasattr(ChannelAdapter, m), f"ChannelAdapter missing method: {m}"

    def test_attachment_model(self):
        att = Attachment(type="image", url="https://example.com/a.png", mime_type="image/png")
        assert att.type == "image"
        assert att.size_bytes is None
