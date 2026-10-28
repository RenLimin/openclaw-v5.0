"""获取（ingest）— 接收本地合同文件，校验类型，落本地暂存副本。

按 DESIGN-DETAIL-v1.0 §3 的 IngestedFile 数据契约。
本期不做网络获取（OA Cube 在后续段交付），只处理本地文件。
仅依赖标准库。
"""

from __future__ import annotations

import hashlib
import os
import shutil
from dataclasses import dataclass
from typing import Optional

# 允许的文件类型 -> 识别用后缀集合
SUPPORTED_EXTENSIONS = {
    "pdf": {".pdf"},
    "docx": {".docx"},
    "image": {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff", ".webp"},
}

VALID_SOURCES = ("upload", "wecom", "oa_cube")

# 组件级暂存目录
COMPONENT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_STAGING_DIR = os.path.join(COMPONENT_ROOT, "data", "staging")


class IngestError(ValueError):
    """获取阶段错误：文件不存在 / 类型不支持 / 来源非法等。"""


@dataclass
class IngestedFile:
    """合同文件获取结果（DETAIL §3）。"""

    source: str                       # "upload" | "wecom" | "oa_cube"
    original_name: str
    local_path: str
    file_type: str                    # "pdf" | "docx" | "image"
    oa_ref: Optional[str] = None      # OA 来源时承载 billid


def detect_file_type(path: str) -> str:
    """按扩展名判定文件类型，不支持时抛 IngestError。"""
    ext = os.path.splitext(path)[1].lower()
    for file_type, exts in SUPPORTED_EXTENSIONS.items():
        if ext in exts:
            return file_type
    raise IngestError(f"不支持的文件类型: {ext or '(无后缀)'} ({path})")


def _file_sha1(path: str) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def ingest_file(
    path: str,
    source: str = "upload",
    staging_dir: Optional[str] = None,
    oa_ref: Optional[str] = None,
) -> IngestedFile:
    """接收本地合同文件，校验并复制到本地暂存目录。

    Args:
        path: 本地合同文件路径。
        source: 来源标识（upload/wecom/oa_cube）。
        staging_dir: 暂存目录；默认组件 data/staging。
        oa_ref: OA 来源时的 billid 引用。

    Returns:
        IngestedFile

    Raises:
        IngestError: 文件不存在 / 来源非法 / 类型不支持 / 空文件。
    """
    if source not in VALID_SOURCES:
        raise IngestError(f"非法来源 source={source!r}，允许 {VALID_SOURCES}")
    if not os.path.isfile(path):
        raise IngestError(f"文件不存在: {path}")
    if os.path.getsize(path) == 0:
        raise IngestError(f"文件为空: {path}")

    file_type = detect_file_type(path)
    original_name = os.path.basename(path)

    target_dir = staging_dir or DEFAULT_STAGING_DIR
    os.makedirs(target_dir, exist_ok=True)

    # 以 内容哈希前缀 去重落盘，保证同文件重复获取幂等
    digest = _file_sha1(path)
    ext = os.path.splitext(original_name)[1].lower()
    staged_name = f"{digest[:16]}{ext}"
    local_path = os.path.join(target_dir, staged_name)

    if not os.path.exists(local_path) or \
            os.path.getsize(local_path) != os.path.getsize(path):
        shutil.copy2(path, local_path)

    return IngestedFile(
        source=source,
        original_name=original_name,
        local_path=local_path,
        file_type=file_type,
        oa_ref=oa_ref,
    )
