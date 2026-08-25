"""
追踪实现 (Layer 2)
步骤级 span / 因果链 / trace replay
"""

import uuid
import threading
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime

from .logging import log_event

@dataclass
class Span:
    span_id: str
    name: str
    start_time: datetime
    end_time: Optional[datetime] = None
    attributes: Dict[str, Any] = field(default_factory=dict)
    children: List["Span"] = field(default_factory=list)

@dataclass
class Trace:
    trace_id: str
    session_id: str
    start_time: datetime
    end_time: Optional[datetime] = None
    root_spans: List[Span] = field(default_factory=list)
    attributes: Dict[str, Any] = field(default_factory=dict)

# 线程本地存储，保存当前 trace/span
_local = threading.local()

def _get_current_trace() -> Optional[Trace]:
    return getattr(_local, 'current_trace', None)

def _get_current_span() -> Optional[Span]:
    return getattr(_local, 'current_span', None)

def get_current_trace() -> Optional[Trace]:
    """获取当前线程的当前 trace"""
    return _get_current_trace()

def start_trace(session_id: str, attributes: Optional[Dict[str, Any]] = None) -> Trace:
    """开始一个新 trace（对应一次会话）"""
    trace = Trace(
        trace_id=str(uuid.uuid4()),
        session_id=session_id,
        start_time=datetime.now(),
        attributes=attributes or {},
    )
    setattr(_local, 'current_trace', trace)
    log_event(
        level="info",
        component="observability",
        event="session_start",
        trace_id=trace.trace_id,
        session_id=session_id,
        attributes=attributes,
    )
    return trace

def end_trace(trace: Trace, attributes: Optional[Dict[str, Any]] = None) -> None:
    """结束一个 trace"""
    trace.end_time = datetime.now()
    if attributes:
        trace.attributes.update(attributes)
    
    # 计算统计
    total_spans = 0
    def count_spans(spans):
        nonlocal total_spans
        total_spans += len(spans)
        for s in spans:
            count_spans(s.children)
    count_spans(trace.root_spans)
    
    log_event(
        level="info",
        component="observability",
        event="session_end",
        trace_id=trace.trace_id,
        session_id=trace.session_id,
        attributes={
            "duration_ms": int((trace.end_time - trace.start_time).total_seconds() * 1000),
            "total_spans": total_spans,
            **(attributes or {}),
        },
    )
    
    # 清理线程本地
    if _get_current_trace() is trace:
        delattr(_local, 'current_trace')
        if hasattr(_local, 'current_span'):
            delattr(_local, 'current_span')

def start_span(name: str, attributes: Optional[Dict[str, Any]] = None) -> Span:
    """开始一个新 span（对应一个步骤：model call / tool call 等）"""
    trace = _get_current_trace()
    if trace is None:
        # 如果没有当前 trace，创建一个隐式 trace
        trace = start_trace("unknown-session")
    
    parent_span = _get_current_span()
    span = Span(
        span_id=str(uuid.uuid4()),
        name=name,
        start_time=datetime.now(),
        attributes=attributes or {},
    )
    
    if parent_span is not None:
        parent_span.children.append(span)
    else:
        trace.root_spans.append(span)
    
    setattr(_local, 'current_span', span)
    
    # 记录开始事件
    log_event(
        level="debug",
        component="observability",
        event=f"{name}_start",
        trace_id=trace.trace_id,
        span_id=span.span_id,
        session_id=trace.session_id,
        attributes=attributes,
    )
    
    return span

def end_span(span: Span, attributes: Optional[Dict[str, Any]] = None) -> None:
    """结束一个 span"""
    span.end_time = datetime.now()
    if attributes:
        span.attributes.update(attributes)
    
    trace = _get_current_trace()
    if trace:
        duration_ms = int((span.end_time - span.start_time).total_seconds() * 1000)
        log_event(
            level="info" if span.attributes.get("error") is None else "error",
            component="observability",
            event=f"{span.name}_end",
            trace_id=trace.trace_id,
            span_id=span.span_id,
            session_id=trace.session_id,
            attributes={
                "duration_ms": duration_ms,
                **(attributes or {}),
            },
        )
    
    # 恢复父 span
    trace = _get_current_trace()
    if trace:
        # 重置当前 span 为父 span
        # 如果是 root span，清空
        pass
