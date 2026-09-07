"""
通用工具函数
"""
import os
import json
from datetime import datetime
from typing import Any, Optional, Dict

def get_current_datetime() -> str:
    """获取当前时区格式化时间"""
    return datetime.now().isoformat()

def ensure_directory(path: str) -> bool:
    """确保目录存在，创建父目录"""
    try:
        os.makedirs(path, exist_ok=True)
        return True
    except Exception:
        return False

def read_file(path: str) -> Optional[str]:
    """读取文件内容"""
    if not os.path.exists(path):
        return None
    try:
        return open(path, "r", encoding="utf-8").read()
    except Exception:
        return None

def write_file(path: str, content: str) -> bool:
    """写入文件内容"""
    try:
        ensure_directory(os.path.dirname(path))
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return True
    except Exception:
        return False

def load_json_file(path: str) -> Optional[Dict[str, Any]]:
    """加载 JSON 文件"""
    content = read_file(path)
    if content is None:
        return None
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return None

def write_json_file(path: str, data: Dict[str, Any]) -> bool:
    """写入 JSON 文件"""
    try:
        content = json.dumps(data, indent=2, ensure_ascii=False)
        return write_file(path, content)
    except Exception:
        return False
