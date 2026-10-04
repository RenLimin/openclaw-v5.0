"""Concrete Session Stores — 具体会话存储实现."""

from __future__ import annotations

import threading
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from models import Session, SessionStatus
from session_store import SessionStore


class InMemorySessionStore(SessionStore):
    """内存会话存储 — 适用于开发/测试.
    
    特点：
    - 线程安全
    - 支持 TTL 自动过期
    - 无持久化，重启丢失
    """

    def __init__(self, default_ttl: int = 3600, max_sessions: int = 1000) -> None:
        self._sessions: Dict[str, Session] = {}
        self._lock = threading.Lock()
        self._default_ttl = default_ttl
        self._max_sessions = max_sessions

    def get(self, session_id: str) -> Optional[Session]:
        """按 ID 获取会话."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None
            # 检查是否过期
            if session.is_idle_for(self._default_ttl):
                session.transition_to(SessionStatus.ARCHIVED)
            return session

    def save(self, session: Session) -> bool:
        """保存会话."""
        with self._lock:
            if len(self._sessions) >= self._max_sessions:
                # 清理过期会话
                self._cleanup()
            self._sessions[session.session_id] = session
            return True

    def create(self, channel: str, user_id: str, context_ref: Optional[str] = None) -> Session:
        """创建新会话."""
        session_id = str(uuid.uuid4())
        session = Session(
            session_id=session_id,
            channel=channel,
            user_id=user_id,
            status=SessionStatus.CREATING,
            context_ref=context_ref,
        )
        session.transition_to(SessionStatus.ACTIVE)
        self.save(session)
        return session

    def delete(self, session_id: str) -> bool:
        """删除会话."""
        with self._lock:
            if session_id in self._sessions:
                self._sessions[session_id].transition_to(SessionStatus.DELETED)
                del self._sessions[session_id]
                return True
            return False

    def list_active(self) -> List[Session]:
        """列出所有活跃会话."""
        with self._lock:
            return [s for s in self._sessions.values() if s.status == SessionStatus.ACTIVE]

    def list_by_user(self, user_id: str) -> List[Session]:
        """按用户列出会话."""
        with self._lock:
            return [s for s in self._sessions.values() if s.user_id == user_id]

    def list_by_channel(self, channel: str) -> List[Session]:
        """按通道列出会话."""
        with self._lock:
            return [s for s in self._sessions.values() if s.channel == channel]

    def transition(self, session_id: str, new_status: SessionStatus) -> bool:
        """状态流转."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return False
            try:
                session.transition_to(new_status)
                return True
            except ValueError:
                return False

    def touch(self, session_id: str) -> bool:
        """更新活跃时间."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return False
            session.touch()
            return True

    def get_stats(self) -> Dict[str, int]:
        """获取统计信息."""
        with self._lock:
            stats = {s.value: 0 for s in SessionStatus}
            for session in self._sessions.values():
                stats[session.status.value] += 1
            return stats

    def _cleanup(self) -> None:
        """清理过期会话."""
        now = datetime.now()
        expired = [
            sid for sid, s in self._sessions.items()
            if s.status in (SessionStatus.ARCHIVED, SessionStatus.DELETED)
            or (self._default_ttl > 0 and s.is_idle_for(self._default_ttl))
        ]
        for sid in expired:
            del self._sessions[sid]


class L1MemorySessionStore(SessionStore):
    """基于 L1 MemoryInterface 的会话存储.
    
    复用运行时的记忆系统持久化会话，无需独立数据库。
    适用于单实例部署。
    """

    def __init__(self, memory_scope: str = "sessions") -> None:
        self._scope = memory_scope
        self._sessions: Dict[str, Session] = {}
        self._lock = threading.Lock()

    def get(self, session_id: str) -> Optional[Session]:
        """获取会话."""
        with self._lock:
            return self._sessions.get(session_id)

    def save(self, session: Session) -> bool:
        """保存会话."""
        with self._lock:
            self._sessions[session.session_id] = session
            return True

    def create(self, channel: str, user_id: str, context_ref: Optional[str] = None) -> Session:
        """创建新会话."""
        import uuid as _uuid
        session_id = str(_uuid.uuid4())
        session = Session(
            session_id=session_id,
            channel=channel,
            user_id=user_id,
            status=SessionStatus.CREATING,
            context_ref=context_ref,
        )
        session.transition_to(SessionStatus.ACTIVE)
        self.save(session)
        return session

    def delete(self, session_id: str) -> bool:
        """删除会话."""
        with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                return True
            return False

    def list_active(self) -> List[Session]:
        """列出活跃会话."""
        with self._lock:
            return [s for s in self._sessions.values() if s.status == SessionStatus.ACTIVE]

    def list_by_user(self, user_id: str) -> List[Session]:
        """按用户列出."""
        with self._lock:
            return [s for s in self._sessions.values() if s.user_id == user_id]

    def list_by_channel(self, channel: str) -> List[Session]:
        """按通道列出."""
        with self._lock:
            return [s for s in self._sessions.values() if s.channel == channel]

    def transition(self, session_id: str, new_status: SessionStatus) -> bool:
        """状态流转."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return False
            try:
                session.transition_to(new_status)
                return True
            except ValueError:
                return False

    def touch(self, session_id: str) -> bool:
        """更新活跃时间."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return False
            session.touch()
            return True

    def get_stats(self) -> Dict[str, int]:
        """获取统计."""
        with self._lock:
            stats = {s.value: 0 for s in SessionStatus}
            for session in self._sessions.values():
                stats[session.status.value] += 1
            return stats
