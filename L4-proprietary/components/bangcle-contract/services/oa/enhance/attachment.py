"""OA 单据合同附件自动获取（只读）— 757 审批原文供给。

从 ``oa_workflow_ones.py --capture`` 落盘的 ``xhrs.json`` 中递归定位
``filedatas``（非空），用**已建立的 OA 会话**下载原文到本地，并抽取纯文本
供 L2 核查 / R3 条款拆解使用。

诚实性（fail-closed）：
- 无附件 / 会话失效 / 下载为空 → 返回 ``error``，绝不伪造原文；
- 下载字节需通过 magic 校验（docx=PK、doc=OLE2、pdf=%PDF）才采信。

口径修正（Rex 2026-11-27 实测）：
  旧注释称「757 单据合同附件 REST 下载无权限」——经 4 张真实单据实测，
  那是**会话过期**误判（返回登录跳转 HTML）。会话有效时 ``loadlink``
  可直接下载：886502 docx(PK, 25339B)、888194/888171/888166 doc(OLE2)。
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional


class AttachmentError(RuntimeError):
    """附件获取失败（无附件/会话失效/下载为空）。"""


def find_attachment_refs(xhrs_path: Path) -> List[Dict[str, str]]:
    """从 ``xhrs.json`` 递归收集全部非空 ``filedatas`` 文件引用（去重保序）。

    不写死字段名：实测 886502 在 ``maindata.field10461``，888194 等在
    ``detail_3.rowDatas[*].field10461``，位置随单据而变。
    """
    data = json.loads(Path(xhrs_path).read_text(encoding="utf-8", errors="replace"))
    found: List[Dict[str, str]] = []
    seen: set = set()

    def _collect(node: Any) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                if k == "filedatas" and isinstance(v, list) and v:
                    for f in v:
                        if not isinstance(f, dict):
                            continue
                        name = (f.get("filename") or "").strip()
                        link = (f.get("loadlink") or f.get("filelink") or "").strip()
                        key = (name, link, str(f.get("fileid") or ""))
                        if name and key not in seen:
                            seen.add(key)
                            found.append({"name": name, "url": link,
                                          "fileid": str(f.get("fileid") or "")})
                _collect(v)
        elif isinstance(node, list):
            for item in node:
                _collect(item)
        elif isinstance(node, str) and '"filedatas"' in node:
            # xhrs.json 的每个条目把响应体存成 JSON 字符串 → 需二次解析
            try:
                inner = json.loads(node)
            except Exception:  # noqa: BLE001
                return
            _collect(inner)

    _walk = _collect
    _collect(data)

    _walk(data)
    return found


def download_ref(ref: Dict[str, str], out_dir: Path, *,
                 storage_state: Optional[Path] = None,
                 base: str = "https://oa.bangcle.com") -> Path:
    """下载单个附件引用到 ``out_dir``，校验 magic 后返回路径。"""
    url = ref.get("url") or ""
    if not url:
        raise AttachmentError("附件无可构造 URL: %s" % ref.get("name"))
    full = url if url.startswith("http") else base + url

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / Path(ref["name"]).name

    sys_path = str(Path(__file__).resolve().parents[2])  # component root
    import sys
    if sys_path not in sys.path:
        sys.path.insert(0, sys_path)
    from services.oa.cube import CubeClient

    client = CubeClient(storage_state=storage_state)
    session = client._ensure_http()  # noqa: SLF001
    resp = session.get(full, timeout=60, allow_redirects=True)
    if resp.status_code >= 400:
        raise AttachmentError("下载 HTTP %s: %s" % (resp.status_code, ref.get("name")))
    body = resp.content
    if len(body) <= 0:
        raise AttachmentError("下载内容为空: %s" % ref.get("name"))
    magic = body[:6]
    ok = (magic[:4] == b"PK\x03\x04"           # docx/zip
          or magic[:4] == b"\xd0\xcf\x11\xe0"  # OLE2(.doc/.xls)
          or magic[:4] == b"%PDF"
          or len(body) > 50000)
    if not ok:
        raise AttachmentError(
            "下载内容非文档（疑似登录跳转/权限页）: %s head=%r" % (
                ref.get("name"), body[:40]))
    target.write_bytes(body)
    return target


def read_attachment_text(path: Path) -> Optional[str]:
    """抽取附件纯文本：docx→python-docx；doc→textutil(macOS)；pdf→pypdf。

    缺依赖/转换失败返回 None（转人工），不伪造。
    """
    suffix = Path(path).suffix.lower()
    if suffix == ".txt":
        return Path(path).read_text(encoding="utf-8", errors="replace")
    if suffix == ".docx":
        try:
            from contract_review.digitize import digitize
            return digitize(str(path), file_type="docx").full_text or None
        except Exception:  # noqa: BLE001
            return None
    if suffix == ".pdf":
        try:
            from contract_review.digitize import digitize
            return digitize(str(path), file_type="pdf").full_text or None
        except Exception:  # noqa: BLE001
            return None
    if suffix == ".doc":
        tool = shutil.which("textutil") or shutil.which("antiword") or shutil.which("catdoc")
        if not tool:
            return None
        try:
            proc = subprocess.run([tool, "-convert", "txt", "-stdout", str(path)],
                                  capture_output=True, timeout=60)
            if proc.returncode == 0 and proc.stdout.strip():
                return proc.stdout.decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            return None
        return None
    return None


def fetch_contract_text(raw_dir: Path, request_id: str, out_dir: Path, *,
                        storage_state: Optional[Path] = None) -> Dict[str, Any]:
    """自动取该单据的合同附件原文（只读）。

    Returns:
        ``{"found": bool, "path": str|None, "name": str|None, "text": str|None,
           "refs": int, "error": str|None}``
    """
    xhrs = Path(raw_dir) / request_id / "xhrs.json"
    if not xhrs.exists():
        return {"found": False, "path": None, "name": None, "text": None,
                "refs": 0, "error": "NO_XHRS"}
    refs = find_attachment_refs(xhrs)
    if not refs:
        return {"found": False, "path": None, "name": None, "text": None,
                "refs": 0, "error": None}

    att_dir = Path(out_dir) / "attachments" / request_id
    for ref in refs:
        try:
            path = download_ref(ref, att_dir, storage_state=storage_state)
        except Exception as exc:  # noqa: BLE001
            return {"found": False, "path": None, "name": ref.get("name"),
                    "text": None, "refs": len(refs), "error": "%s: %s" % (
                        type(exc).__name__, exc)}
        text = read_attachment_text(path)
        if text and text.strip():
            return {"found": True, "path": str(path), "name": ref.get("name"),
                    "text": text, "refs": len(refs), "error": None}
        return {"found": False, "path": str(path), "name": ref.get("name"),
                "text": None, "refs": len(refs),
                "error": "TEXT_EXTRACT_FAILED: %s" % ref.get("name")}
    return {"found": False, "path": None, "name": None, "text": None,
            "refs": len(refs), "error": None}
