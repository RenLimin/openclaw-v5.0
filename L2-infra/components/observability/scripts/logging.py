"""
结构化日志实现 (Layer 1)
遵循 OpenTelemetry GenAI semantic conventions
"""

import os
import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional

# 日志根目录
LOG_ROOT = "/Users/bangcle/.openclaw/workspace/logs/observability"
ERROR_LOG_ROOT = os.path.join(LOG_ROOT, "errors")

# 敏感字段列表（需要 redact）
SENSITIVE_FIELDS = {
    "api_key", "token", "secret", "password", "credential",
    "private_key", "access_token", "refresh_token",
}

def redact_sensitive(obj: Dict[str, Any], replaced: str = "[REDACTED]") -> Dict[str, Any]:
    """递归 redact 敏感字段"""
    result = {}
    for key, value in obj.items():
        lower_key = key.lower()
        if any(sf in lower_key for sf in SENSITIVE_FIELDS):
            result[key] = replaced
        elif isinstance(value, dict):
            result[key] = redact_sensitive(value, replaced)
        elif isinstance(value, list):
            result[key] = [
                redact_sensitive(item, replaced) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            result[key] = value
    return result

def get_daily_log_path() -> str:
    """获取今日日志文件路径"""
    today = datetime.now().strftime("%Y-%m-%d")
    return os.path.join(LOG_ROOT, f"{today}.jsonl")

def init_logging() -> None:
    """初始化日志目录"""
    os.makedirs(LOG_ROOT, exist_ok=True)
    os.makedirs(ERROR_LOG_ROOT, exist_ok=True)
    # 设置权限
    for path in [LOG_ROOT, ERROR_LOG_ROOT]:
        os.chmod(path, 0o700)

def log_event(
    level: str,
    component: str,
    event: str,
    trace_id: Optional[str] = None,
    span_id: Optional[str] = None,
    session_id: Optional[str] = None,
    attributes: Optional[Dict[str, Any]] = None,
) -> None:
    """记录一个结构化事件"""
    init_logging()
    
    timestamp = datetime.now().isoformat(timespec='milliseconds')
    attributes = attributes or {}
    # Redact 敏感数据
    safe_attributes = redact_sensitive(attributes)
    
    entry = {
        "timestamp": timestamp,
        "level": level.lower(),
        "component": component,
        "event": event,
        "trace_id": trace_id,
        "span_id": span_id,
        "session_id": session_id,
        "attributes": safe_attributes,
    }
    
    log_path = get_daily_log_path()
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    
    # 错误日志单独记录
    if level.lower() in ("error", "critical", "fatal"):
        error_path = os.path.join(
            ERROR_LOG_ROOT,
            f"{datetime.now().strftime('%Y-%m-%d')}-errors.jsonl"
        )
        with open(error_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    
    # 设置文件权限
    try:
        os.chmod(log_path, 0o600)
    except OSError:
        pass
