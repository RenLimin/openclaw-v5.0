"""services.oa.cube — 泛微 e-cology 9 建模引擎 Cube 内部 REST 客户端。

设计契约（DESIGN-DETAIL §4）：
- 用 Playwright ``storage_state`` 携带 ecology 会话（cookie），**不**走开放平台 token。
- 以卡片同款 query 调内部 REST（GET + JSON）：
  initDetail / mainFields / getDetailFields / innerTabs / checkCardRight。
- 仅做"带会话 GET + JSON 解析 + 附件字段引用提取 + 同会话下载"。

错误模型：
- CubeAuthError       会话失效（errorCode=002 / 401 / 登录超时）→ 触发会话自愈
- CubePermissionError 账号无卡片权限（403 / 无权）→ 明确阻塞，不伪造数据
- CubeError           其它异常

安全：凭据/会话仅来自文件；本模块不打印 cookie/验证码；附件下载为 OA 入站。
"""

from __future__ import annotations

import json
import os
import random
import re
import string
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import helpers as H
from .helpers import (
    OA_BASE,
    P_INIT_DETAIL,
    P_MAIN_FIELDS,
    P_DETAIL_FIELDS,
    P_INNER_TABS,
    P_CHECK_RIGHT,
)

# storage_state 默认位置（侦察产物；会话自愈也回写此处）
DEFAULT_STORAGE_STATE = (
    Path.home() / ".openclaw" / "data" / "clm-oa-recon" / "state.json"
)


# ---------------------------------------------------------------
# 错误类型
# ---------------------------------------------------------------

class CubeError(Exception):
    """Cube 调用通用错误。"""


class CubeAuthError(CubeError):
    """会话失效 / 未登录。"""


class CubePermissionError(CubeError):
    """账号无该卡片权限。"""


# ---------------------------------------------------------------
# 结构化数据
# ---------------------------------------------------------------

@dataclass
class AttachmentRef:
    """附件字段文件引用（来自建模上传字段）。"""

    name: str
    file_id: str = ""
    url: str = ""
    tablename: str = ""
    detail_key: str = ""
    field_id: str = ""
    local_path: str = ""
    raw: Any = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "file_id": self.file_id,
            "url": self.url,
            "tablename": self.tablename,
            "detail_key": self.detail_key,
            "field_id": self.field_id,
            "local_path": self.local_path,
        }


@dataclass
class ContractData:
    """Cube 合同卡片结构化结果。"""

    billid: str
    main_fields: Dict[str, str] = field(default_factory=dict)
    attachments: List[AttachmentRef] = field(default_factory=list)
    detail_tables: List[Dict[str, Any]] = field(default_factory=list)
    inner_tabs: List[Dict[str, Any]] = field(default_factory=list)
    right: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "billid": self.billid,
            "main_fields": self.main_fields,
            "attachments": [a.to_dict() for a in self.attachments],
            "detail_tables": self.detail_tables,
            "inner_tabs": self.inner_tabs,
            "right": self.right,
        }


# ---------------------------------------------------------------
# Cube 客户端
# ---------------------------------------------------------------

class CubeClient:
    """携带 storage_state 会话的 Cube 内部 REST 客户端。

    Args:
        storage_state: Playwright storage_state 文件路径（None 用默认侦察路径）
        base: OA 基址
        timeout: 单次请求超时（秒）
        layoutid: 卡片布局 id（实测 535）
    """

    def __init__(
        self,
        storage_state: Optional[os.PathLike] = None,
        *,
        base: str = OA_BASE,
        timeout: float = 20.0,
        layoutid: str = "535",
    ) -> None:
        self.storage_state_path = Path(
            storage_state if storage_state is not None else DEFAULT_STORAGE_STATE
        )
        self.base = base.rstrip("/")
        self.timeout = float(timeout)
        self.layoutid = str(layoutid)
        self._http = None
        self._state_mtime: Optional[float] = None

    # ---------- 会话 / HTTP ----------

    def _load_state(self) -> Dict[str, Any]:
        if not self.storage_state_path.exists():
            raise CubeAuthError(
                "storage_state 不存在: %s（需先 IAM 登录）" % self.storage_state_path
            )
        try:
            state = json.loads(
                self.storage_state_path.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError) as e:
            raise CubeAuthError("storage_state 不可读/损坏: %s" % e)
        if not state.get("cookies"):
            raise CubeAuthError("storage_state 无 cookie")
        return state

    def _ensure_http(self):
        """惰性构造携带会话 cookie 的 requests.Session（state 变更后自动重载）。"""
        import requests

        mtime = (
            self.storage_state_path.stat().st_mtime
            if self.storage_state_path.exists()
            else None
        )
        if self._http is not None and mtime == self._state_mtime:
            return self._http

        state = self._load_state()
        session = requests.Session()
        for c in state.get("cookies", []):
            domain = c.get("domain")
            if not domain or "bangcle.com" not in domain:
                continue
            try:
                session.cookies.set(
                    c.get("name", ""),
                    c.get("value", ""),
                    domain=domain.lstrip("."),
                    path=c.get("path", "/") or "/",
                )
            except Exception:
                # 个别异常 cookie 不影响整体会话
                continue
        self._http = session
        self._state_mtime = mtime
        return session

    def reload_session(self) -> None:
        """强制下次请求重新加载 storage_state（自愈成功后调用）。"""
        self._http = None
        self._state_mtime = None

    # ---------- 基础 GET ----------

    @staticmethod
    def _lenient_json_loads(text: str) -> Optional[Any]:
        """宽松 JSON：泛微 Cube 的 mainFields 等返回对象裸数字键 {1:"x"}。

        严格 json.loads 会失败；把对象数字键补引号后重试。
        Returns:
            解析结果 dict；仍失败返回 None（交由上层判登录页/错误）。
        """
        fixed = re.sub(r'([,{]\s*)(\d+)(\s*:)', r'\1"\2"\3', text)
        try:
            return json.loads(fixed)
        except ValueError:
            return None

    def _new_nonces(self) -> Dict[str, str]:
        key = "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(6))
        uuid = "".join(random.choice("0123456789ABCDEF") for _ in range(32))
        return {"_key": key, "uuid": uuid}

    def _get_json(self, path: str, query: Dict[str, Any]) -> Dict[str, Any]:
        session = self._ensure_http()
        url = self.base + path
        try:
            resp = session.get(url, params=query, timeout=self.timeout)
        except Exception as e:
            # 网络异常 / 连接错误：交由上层决定是否走浏览器兜底
            raise CubeError("Cube 请求异常 %s: %s" % (path, e))

        http_status = resp.status_code
        try:
            data = resp.json()
        except ValueError:
            # 泛微 Cube 宽松 JSON：对象裸数字键 {1:"x"} 不引号（实测 mainFields）
            data = CubeClient._lenient_json_loads(resp.text)
            if data is None:
                # 非 JSON：多为登录页 HTML
                if http_status in (401, 440):
                    raise CubeAuthError("会话失效 HTTP %s" % http_status)
                if http_status == 403:
                    raise CubePermissionError("账号无权限 HTTP 403")
                if "login" in resp.text[:2000].lower():
                    raise CubeAuthError("返回登录页（会话失效）")
                raise CubeError(
                    "非 JSON 响应 HTTP %s (%s)" % (http_status, path)
                )

        kind = H.classify_error(data, http_status)
        if kind == "auth":
            raise CubeAuthError(
                "会话失效: %s" % (data.get("msg") or data.get("errorCode"))
            )
        if kind == "permission":
            raise CubePermissionError(
                "账号无该卡片权限: %s" % (data.get("msg") or "403")
            )
        if kind == "error":
            raise CubeError(
                "Cube 返回错误: %s %s"
                % (data.get("errorCode", ""), data.get("msg", ""))
            )
        if not isinstance(data, dict):
            raise CubeError("Cube 响应结构异常")
        return data

    # ---------- 业务方法 ----------

    def get_contract(self, billid: Any) -> ContractData:
        """拉取合同卡片：结构化主字段 + 附件字段引用。

        Args:
            billid: 建模记录主键（无 requestid/docid）

        Returns:
            ContractData

        Raises:
            CubeAuthError / CubePermissionError / CubeError
        """
        billid_s = H._require_billid(billid)
        nonces = self._new_nonces()
        base_query = H.build_card_query(
            billid_s,
            key=nonces["_key"],
            uuid=nonces["uuid"],
            layoutid=self.layoutid,
        )

        # 1) initDetail：明细表结构
        init_detail = self._get_json(P_INIT_DETAIL, dict(base_query))
        tables = H.detail_tables(init_detail)

        # 2) mainFields：主字段
        main_obj = self._get_json(P_MAIN_FIELDS, dict(base_query))
        main_fields = H.extract_main_fields(main_obj)

        # 3) getDetailFields：各明细表数据（含上传/附件字段）
        attachments: List[AttachmentRef] = []
        detail_out: List[Dict[str, Any]] = []
        seen_att: set = set()
        for idx, (detail_key, tablename) in enumerate(tables):
            # groupid 推断：实测 dt8(detail_8/orderid8) 用 groupid=7（0 基组号）
            groupid = idx
            q = H.build_detail_query(
                billid_s,
                tablename,
                groupid,
                key=nonces["_key"],
                uuid=nonces["uuid"],
                layoutid=self.layoutid,
            )
            try:
                detail_json = self._get_json(P_DETAIL_FIELDS, q)
            except CubeError:
                # 单明细表失败不应阻断整体；记录占位继续
                detail_out.append(
                    {"detail_key": detail_key, "tablename": tablename, "error": True}
                )
                continue

            rows = detail_json.get("datas") if isinstance(detail_json, dict) else None
            rows = rows if isinstance(rows, list) else []
            detail_out.append(
                {
                    "detail_key": detail_key,
                    "tablename": tablename,
                    "row_count": len(rows),
                    "rows": rows,
                }
            )
            refs = H.extract_attachment_refs(rows)
            for ref in refs:
                att = AttachmentRef(
                    name=H.safe_filename(ref.get("name")),
                    file_id=ref.get("id", ""),
                    url=ref.get("url", ""),
                    tablename=tablename,
                    detail_key=detail_key,
                    raw=ref.get("raw"),
                )
                key_sig = (att.name, att.file_id, att.url, att.tablename)
                if key_sig not in seen_att:
                    seen_att.add(key_sig)
                    attachments.append(att)

        # 4) innerTabs：关联台账（失败不阻断）
        inner_tabs: List[Dict[str, Any]] = []
        try:
            tabs_obj = self._get_json(P_INNER_TABS, dict(base_query))
            inner_tabs = tabs_obj.get("innerTabs", []) if isinstance(tabs_obj, dict) else []
        except CubeError:
            inner_tabs = []

        return ContractData(
            billid=billid_s,
            main_fields=main_fields,
            attachments=attachments,
            detail_tables=detail_out,
            inner_tabs=inner_tabs,
        )

    def check_card_right(self, billid: Any) -> Dict[str, Any]:
        """查询当前账号对卡片的权限（checkCardRight）。"""
        billid_s = H._require_billid(billid)
        nonces = self._new_nonces()
        query = H.build_card_query(
            billid_s, key=nonces["_key"], uuid=nonces["uuid"], layoutid=self.layoutid
        )
        return self._get_json(P_CHECK_RIGHT, query)

    def download_attachment(
        self,
        ref: AttachmentRef,
        out_dir: os.PathLike,
        *,
        filename: Optional[str] = None,
    ) -> Path:
        """在同会话内下载附件到 ``out_dir``，字节数 > 0。

        Returns:
            落盘路径

        Raises:
            CubeError: 附件 URL 不可构造（触发浏览器兜底）或下载为空
        """
        url = H.build_download_url(
            {"id": ref.file_id, "url": ref.url, "name": ref.name},
            base=self.base,
        )
        if not url:
            raise CubeError(
                "附件 URL 不可构造（懒加载/加密传输），需浏览器兜底: %s" % ref.name
            )

        out_path = Path(out_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        name = H.safe_filename(filename or ref.name)
        target = _unique_path(out_path / name)

        session = self._ensure_http()
        try:
            with session.get(url, timeout=self.timeout, stream=True) as resp:
                if resp.status_code in (401, 440):
                    raise CubeAuthError("下载会话失效 HTTP %s" % resp.status_code)
                if resp.status_code == 403:
                    raise CubePermissionError("下载被拒 HTTP 403")
                if resp.status_code >= 400:
                    raise CubeError("下载失败 HTTP %s" % resp.status_code)
                written = 0
                with open(target, "wb") as fh:
                    for chunk in resp.iter_content(chunk_size=64 * 1024):
                        if chunk:
                            fh.write(chunk)
                            written += len(chunk)
        except CubeError:
            raise
        except Exception as e:
            raise CubeError("下载异常 %s: %s" % ref.name, e)

        if written <= 0 or target.stat().st_size <= 0:
            try:
                target.unlink()
            except OSError:
                pass
            raise CubeError("下载内容为空: %s" % ref.name)
        return target


def _unique_path(path: Path) -> Path:
    """若目标已存在，追加 (1)/(2)… 避免覆盖。"""
    if not path.exists():
        return path
    stem, suffix, parent = path.stem, path.suffix, path.parent
    i = 1
    while True:
        candidate = parent / ("%s (%d)%s" % (stem, i, suffix))
        if not candidate.exists():
            return candidate
        i += 1
