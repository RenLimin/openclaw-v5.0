"""OA 合同原文提取 — 把已落盘的 OA 附件数字化为全文。

背景（2026-10-29 修复）：原 OA 审查只解析卡片主字段/摘要，合同附件原文
下载后未进入分析管线。本模块负责在附件仍在临时目录时读出全文；
调用方（contractctl）在读出后立即 rmtree 临时目录，做到即用即焚。

合同原文全程本地，不外发（DETAIL §2 安全红线）。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from .digitize import DigitizedText, DigitizeError, digitize

# 可进入全文管线的附件类型（与 digitize 支持范围一致）
_SUPPORTED_TYPES = ("pdf", "docx", "image")


def digitize_oa_data(data: Dict[str, Any]) -> Optional[DigitizedText]:
    """从 OA 拉取结果中已落盘的附件提取合同全文。

    依次数字化每个可用附件（pdf/docx/图片），拼接非空全文。
    浏览器兜底返回的 card.txt（非合同原文类型）会被跳过。

    Args:
        data: ``get_contract_with_fallback`` 返回的 dict，
            取 ``attachments_local``（API 路径）或 ``attachments``（兜底路径）。

    Returns:
        DigitizedText(method="oa_attachment")；无任何可用原文时返回 None，
        由调用方回退到卡片摘要 / 主字段文本。
    """
    attachments = data.get("attachments_local")
    if not attachments:
        attachments = data.get("attachments") or []

    parts = []
    confidences = []
    for att in attachments:
        if not isinstance(att, dict):
            continue
        path = att.get("local_path")
        if not path or att.get("error"):
            continue
        # 延迟导入避免模块循环（ingest 不依赖本模块，实际安全）
        from .ingest import IngestError, detect_file_type

        try:
            file_type = detect_file_type(path)
        except Exception:  # noqa: BLE001 — 不支持的附件类型直接跳过
            continue
        if file_type not in _SUPPORTED_TYPES:
            continue
        try:
            dt = digitize(path, file_type=file_type)
        except DigitizeError:
            continue
        if dt.full_text and dt.full_text.strip():
            parts.append(dt.full_text.strip())
            if dt.ocr_confidence is not None:
                confidences.append(dt.ocr_confidence)

    if not parts:
        return None

    return DigitizedText(
        full_text="\n\n".join(parts),
        method="oa_attachment",
        ocr_confidence=min(confidences) if confidences else None,
    )
