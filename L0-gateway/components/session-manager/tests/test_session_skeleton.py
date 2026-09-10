"""Session Manager — 骨架测试。"""

import pytest
from datetime import datetime
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from models import Session, SessionStatus, VALID_TRANSITIONS
from session_store import SessionStore


class TestSessionModel:
    def test_session_creation_defaults(self):
        s = Session(session_id="s1", channel="test", user_id="u1")
        assert s.status == SessionStatus.CREATING
        assert s.is_active() is False
        assert isinstance(s.created_at, datetime)
        assert s.metadata == {}

    def test_session_state_transition_valid(self):
        s = Session(session_id="s1", channel="test", user_id="u1")
        s.transition_to(SessionStatus.ACTIVE)
        assert s.status == SessionStatus.ACTIVE
        assert s.is_active() is True

    def test_session_state_transition_invalid(self):
        s = Session(session_id="s1", channel="test", user_id="u1")
        with pytest.raises(ValueError, match="Invalid session state"):
            s.transition_to(SessionStatus.ARCHIVED)

    def test_session_touch_updates_time(self):
        s = Session(session_id="s1", channel="test", user_id="u1")
        s.transition_to(SessionStatus.ACTIVE)
        s.status = SessionStatus.IDLE
        old_time = s.last_active_at
        import time; time.sleep(0.01)
        s.touch()
        assert s.last_active_at > old_time
        assert s.status == SessionStatus.ACTIVE

    def test_session_to_dict(self):
        s = Session(session_id="s1", channel="test", user_id="u1", title="Test Chat")
        d = s.to_dict()
        assert d["session_id"] == "s1"
        assert d["status"] == "creating"
        assert d["title"] == "Test Chat"
        assert "created_at" in d


class TestSessionStoreABC:
    def test_cannot_instantiate(self):
        with pytest.raises(TypeError):
            SessionStore()

    def test_has_required_methods(self):
        methods = ["get", "create", "update", "delete", "list_by_user",
                   "list_by_channel", "find_active", "cleanup_idle", "count"]
        for m in methods:
            assert hasattr(SessionStore, m), f"SessionStore missing method: {m}"

    def test_valid_transitions_coverage(self):
        """所有状态都应该出现在流转表中。"""
        for status in SessionStatus:
            assert status in VALID_TRANSITIONS, f"Missing transitions for {status}"
