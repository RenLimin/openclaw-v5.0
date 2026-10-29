"""services.oa.helpers — 纯函数工具（无网络、无第三方依赖，可离线单测）。

职责：
- Cube 卡片/内部 REST 的 query 拼装
- OA 基址 + 相对路径解析
- Cube 响应信封识别（会话失效 / 权限 / 成功）
- 主字段与上传（附件）字段的结构化提取
- 附件下载 URL 构造（仅在可确定时构造，否则返回 None 触发浏览器兜底）

仅 ES5 约束针对浏览器 page.evaluate；本模块为 Python，不涉及。
"""

from __future__ import annotations

import re
import time
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlencode, urljoin

# --- 合同卡片固定参数（2026-10-27 实测，DESIGN-DETAIL §4.1） ---
OA_BASE = "https://oa.bangcle.com"
CUBE_TYPE = "0"
MODE_ID = "112"          # 合同建模 modeId
FORM_ID = "-249"         # 合同表单 formId
CUSTOMID = "179"         # 合同台账 customid
MAIN_TABLE = "uf_xsht_xxb"

# Cube 内部 REST 相对路径
P_INIT_DETAIL = "/api/cube/new/card/initDetail"
P_MAIN_FIELDS = "/api/cube/new/card/mainFields"
P_DETAIL_FIELDS = "/api/cube/new/card/getDetailFields"
P_INNER_TABS = "/api/cube/new/card/innerTabs"
P_CHECK_RIGHT = "/api/cube/new/card/checkCardRight"

# 会话失效 errorCode（实测 errorCode="002" msg="登录信息超时"）
AUTH_ERROR_CODES = {"002", "login", "loginTimeout", "sessionTimeout"}
# 权限相关关键词
PERMISSION_KEYWORDS = ("无权", "权限", "forbidden", "no right", "no permission")


class HelperError(ValueError):
    """纯函数入参错误。"""


# ---------------------------------------------------------------
# Query / URL 拼装
# ---------------------------------------------------------------

def build_card_query(
    billid: Any,
    *,
    key: str = "",
    uuid: str = "",
    layoutid: str = "",
    extra: Optional[Dict[str, Any]] = None,
    randomize: bool = True,
) -> Dict[str, str]:
    """构造与 Cube 卡片 URL 同款的 query（用于内部 REST）。

    与卡片保持一致：type/modeId/formId/billid/opentype/customid/viewfrom/
    _key/guid/uuid/layoutid/modedatastatus/__random__。

    Args:
        billid: 建模记录 ID（整数或纯数字字符串）
        key: 卡片 _key
        uuid: 卡片 uuid
        layoutid: 布局 id（实测 535）
        extra: 追加/覆盖项
        randomize: 是否附带 __random__ 毫秒时间戳

    Returns:
        有序的 str->str dict
    """
    billid = _require_billid(billid)
    query: Dict[str, str] = {
        "type": CUBE_TYPE,
        "modeId": MODE_ID,
        "formId": FORM_ID,
        "billid": billid,
        "opentype": "0",
        "customid": CUSTOMID,
        "viewfrom": "fromsearchlist",
        "_key": key or "",
        "guid": "card",
    }
    if uuid:
        query["uuid"] = uuid
    if layoutid:
        query["layoutid"] = str(layoutid)
    query["modedatastatus"] = ""
    if randomize:
        query["__random__"] = str(int(time.time() * 1000))
    if extra:
        for k, v in extra.items():
            query[k] = "" if v is None else str(v)
    return query


def build_detail_query(
    billid: Any,
    tablename: str,
    groupid: Any,
    *,
    key: str = "",
    uuid: str = "",
    layoutid: str = "",
    iseasy: Any = 0,
) -> Dict[str, str]:
    """构造 getDetailFields 的 query（卡片 query + tablename/groupid/iseasy）。"""
    if not tablename or not isinstance(tablename, str):
        raise HelperError("tablename 必填")
    query = build_card_query(
        billid, key=key, uuid=uuid, layoutid=layoutid
    )
    query["tablename"] = tablename
    query["groupid"] = str(groupid)
    query["iseasy"] = str(iseasy)
    return query


def rest_url(path: str, query: Dict[str, Any], base: str = OA_BASE) -> str:
    """拼接 Cube 内部 REST 绝对 URL（query 经 urlencode 编码）。"""
    if not path.startswith("/"):
        raise HelperError("path 必须以 / 开头")
    return base + path + "?" + urlencode(query)


def resolve_url(url_or_path: str, base: str = OA_BASE) -> str:
    """把相对路径解析为绝对 URL；已是绝对 URL 则原样返回。"""
    if not url_or_path:
        raise HelperError("空 url")
    return urljoin(base if base.endswith("/") else base + "/", url_or_path)


def _require_billid(billid: Any) -> str:
    s = str(billid).strip()
    if not s or not re.fullmatch(r"\d{1,18}", s):
        raise HelperError("billid 必须为正整数，收到: %r" % (billid,))
    return s


# ---------------------------------------------------------------
# Cube 响应信封识别
# ---------------------------------------------------------------

def is_success_envelope(obj: Any) -> bool:
    """判断 Cube JSON 是否为成功信封。

    成功特征（任一）：
    - 顶层 ``status`` 为 True/"1"/200，且无 errorCode
    - 不存在 status 字段但包含业务字段（datas/fields 等）
    """
    if not isinstance(obj, dict):
        return False
    if obj.get("errorCode") not in (None, "", "0"):
        return False
    status = obj.get("status")
    if status is None:
        # 无 status 字段，业务载荷型
        return any(k in obj for k in ("datas", "fields", "mainFields", "detailTable", "innerTabs"))
    return status is True or status == "1" or status == 1 or status == 200


def classify_error(obj: Any, http_status: int = 200) -> Optional[str]:
    """把 Cube 响应分类为 ``"auth"`` / ``"permission"`` / ``"error"`` / None。

    None 表示非错误（成功信封）。
    """
    if http_status in (401, 440):
        return "auth"
    if http_status == 403:
        return "permission"
    if not isinstance(obj, dict):
        return "error" if http_status >= 400 else None

    code = str(obj.get("errorCode", "") or "")
    msg = str(obj.get("msg", "") or obj.get("message", "") or "")
    if http_status >= 400:
        if code in AUTH_ERROR_CODES or "登录" in msg or "超时" in msg:
            return "auth"
        return "permission" if http_status == 403 else "error"

    # HTTP 200 但信封内 status=false 或 msg 带错误/权限关键词
    low_msg = msg.lower()
    if code or obj.get("status") is False or any(
        k in msg for k in PERMISSION_KEYWORDS
    ) or any(k in low_msg for k in ("forbidden", "no right", "no permission", "登录", "超时")):
        if code in AUTH_ERROR_CODES or "登录" in msg or "超时" in msg or "login" in msg.lower():
            return "auth"
        if any(k in msg for k in PERMISSION_KEYWORDS) or any(
            k in low_msg for k in ("forbidden", "no right", "no permission")
        ):
            return "permission"
        return "error"
    return None


# ---------------------------------------------------------------
# 主字段提取
# ---------------------------------------------------------------

def _field_display_name(field: Dict[str, Any]) -> str:
    for key in ("fieldlabelname", "showname", "label", "name", "title", "fieldlabel"):
        val = field.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def _scalar_value(field: Dict[str, Any]) -> Any:
    for key in ("fieldvalue", "value", "val", "showvalue", "text"):
        if key in field:
            return field[key]
    return None


def extract_main_fields(obj: Any) -> Dict[str, str]:
    """从 mainFields 响应提取 ``{字段显示名: 值}``。

    兼容多种实测可能形态：
    - {"fields":[{"fieldid","fieldlabelname","fieldvalue"...}]}
    - {"datas":[{"fieldNNNN": value, ...}], "fieldAttr":[...]}
    - {"fieldNNNN": {"name":label,"value":v}}
    """
    if not isinstance(obj, dict):
        return {}
    result: Dict[str, str] = {}

    fields = obj.get("fields")
    if isinstance(fields, list):
        for f in fields:
            if isinstance(f, dict):
                name = _field_display_name(f)
                if name:
                    result[name] = _to_text(_scalar_value(f))
        if result:
            return result
    if isinstance(fields, dict):
        # 实测 mainFields：{"fields": {"field32891": {...}, ...}}
        # 每个子对象含字段显示名与值（或 showname/值嵌在 browser 字段对象内）
        for fid, f in fields.items():
            if not isinstance(f, dict):
                continue
            name = _field_display_name(f)
            val = _scalar_value(f)
            if val is None:
                # 兼容 {"showname": ..., "value": {...}} 或浏览器字段对象
                val = f.get("showname")
                if isinstance(val, dict):
                    val = val.get("showvalue") or val.get("value") or ""
            if name:
                result[name] = _to_text(val)
        if result:
            return result

    # datas 行（字段 id -> 值），名称映射从 fieldAttr / fieldMap
    label_map = _field_label_map(obj)
    datas = obj.get("datas")
    if isinstance(datas, list) and datas:
        for row in datas:
            if isinstance(row, dict):
                for fid, val in row.items():
                    if not str(fid).startswith("field"):
                        continue
                    label = label_map.get(str(fid)) or str(fid)
                    result[label] = _to_text(val)
        if result:
            return result

    # fieldNNNN -> {name,value} 或直接值
    for k, v in obj.items():
        if not str(k).startswith("field") or k in ("fields",):
            continue
        if isinstance(v, dict):
            label = _field_display_name(v) or str(k)
            result[label] = _to_text(_scalar_value(v) if _scalar_value(v) is not None else v.get("showname"))
        else:
            result[str(k)] = _to_text(v)
    return result


def _field_label_map(obj: Dict[str, Any]) -> Dict[str, str]:
    label_map: Dict[str, str] = {}
    for container_key in ("fieldAttr", "fieldMap", "fields", "fieldAttrList"):
        container = obj.get(container_key)
        items: Iterable[Any]
        if isinstance(container, list):
            items = container
        elif isinstance(container, dict):
            items = (
                dict(__id=k, **v) if isinstance(v, dict) else {"__id": k, "name": v}
                for k, v in container.items()
            )
        else:
            continue
        for f in items:
            if not isinstance(f, dict):
                continue
            fid = str(f.get("fieldid", "") or f.get("id", "") or f.get("__id", ""))
            name = _field_display_name(f)
            if fid and name:
                label_map[fid] = name
                label_map["field" + fid] = name
    return label_map


# ---------------------------------------------------------------
# 附件（上传字段）提取
# ---------------------------------------------------------------

# 看起来像文件名的字符串（含扩展名）
_FILE_EXT_RE = re.compile(
    r"\.(pdf|docx?|xlsx?|pptx?|png|jpe?g|gif|bmp|zip|rar|7z|txt|ofd|wps)$",
    re.IGNORECASE,
)

_FILE_NAME_KEYS = ("name", "filename", "fileName", "showname", "showName", "title")
_FILE_ID_KEYS = ("fileid", "fileId", "id", "filedid", "docid", "docId", "fileid_real")
_FILE_URL_KEYS = (
    "downloadUrl",
    "downloadurl",
    "url",
    "href",
    "fileUrl",
    "fileurl",
    "path",
    "filePath",
    "serverpath",
)


def looks_like_filename(value: Any) -> bool:
    """判断字符串是否像带扩展名的文件名（不是 URL、不含路径分隔符）。"""
    if not isinstance(value, str):
        return False
    s = value.strip()
    if not s or "/" in s or s.startswith("http") or len(s) > 260:
        return False
    return bool(_FILE_EXT_RE.search(s))


def _as_file_ref(node: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """把 dict 识别为单个文件引用；非文件引用返回 None。"""
    name = _first_str(node, _FILE_NAME_KEYS)
    file_id = _first_str(node, _FILE_ID_KEYS)
    url = _first_str(node, _FILE_URL_KEYS)

    is_file = False
    if name and looks_like_filename(name):
        is_file = True
    if url and re.search(r"(FileDownload|imagefile|openimg|docs?/|download|encryptedTrans)", url, re.I):
        is_file = True
    # 形如 {id,name} 且 name 非纯枚举名（含扩展名或 url/id 齐全）
    if file_id and name and (url or looks_like_filename(name)):
        is_file = True
    if not is_file:
        return None
    return {
        "name": name or ("file-" + str(file_id or "")),
        "id": file_id or "",
        "url": url or "",
        "raw": node,
    }


def extract_attachment_refs(value: Any) -> List[Dict[str, Any]]:
    """递归遍历字段值，提取全部文件引用（去重保序）。

    入参可为：文件 dict / 文件 dict 列表 / 嵌套 dict / 文件名（str）。
    枚举 ``*options`` 列表里的 showname（无文件名、无 url）不会被误提取。
    """
    found: List[Dict[str, Any]] = []
    seen: set = set()

    def _add(ref: Dict[str, Any]) -> None:
        key = (ref.get("name"), ref.get("id"), ref.get("url"))
        if key not in seen:
            seen.add(key)
            found.append(ref)

    def _walk(node: Any) -> None:
        if isinstance(node, dict):
            ref = _as_file_ref(node)
            if ref:
                _add(ref)
                return
            for v in node.values():
                _walk(v)
        elif isinstance(node, list):
            for item in node:
                _walk(item)
        elif isinstance(node, str) and looks_like_filename(node):
            _add({"name": node.strip(), "id": "", "url": "", "raw": node})

    _walk(value)
    return found


def _first_str(node: Dict[str, Any], keys: Tuple[str, ...]) -> str:
    for k in keys:
        v = node.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


# 已知可确定的 e-cology 下载端点（按出现优先级）；仅在引用提供 id 时使用
_DOWNLOAD_TEMPLATES = (
    "/weaver/weaver.file.FileDownload?fileid={id}",
    "/api/docs/file/download?fileid={id}",
)


def build_download_url(ref: Dict[str, Any], base: str = OA_BASE) -> Optional[str]:
    """为单个文件引用构造可下载的绝对 URL。

    仅在**可确定**时返回：
    - 引用自带 url/downloadUrl/href（相对或绝对）
    - 引用自带可识别的 e-cology fileid 且命中已知端点

    无法确定（懒加载/仅业务 id/加密传输）时返回 None，由浏览器兜底。
    绝不猜测不可验证的 URL 导致下载到错误内容。
    """
    url = ref.get("url") if isinstance(ref, dict) else ""
    if url:
        if url.startswith("http://") or url.startswith("https://"):
            return url
        if url.startswith("/"):
            return resolve_url(url, base)
    file_id = ref.get("id") if isinstance(ref, dict) else ""
    if file_id and re.fullmatch(r"\d{1,18}", str(file_id)):
        # 默认使用 FileDownload 端点（e-cology 最通用）
        return resolve_url(_DOWNLOAD_TEMPLATES[0].format(id=file_id), base)
    return None


# ---------------------------------------------------------------
# 明细表 / 结构
# ---------------------------------------------------------------

def detail_tables(init_detail: Any) -> List[Tuple[str, str]]:
    """从 initDetail 提取 ``[(detail_key, tablename)]``，按 orderid 排序。"""
    if not isinstance(init_detail, dict):
        return []
    table = init_detail.get("detailTable")
    if not isinstance(table, dict):
        return []
    rows: List[Tuple[int, str, str]] = []
    for key, meta in table.items():
        if isinstance(meta, dict) and meta.get("tablename"):
            try:
                order = int(meta.get("orderid", 0))
            except (TypeError, ValueError):
                order = 0
            rows.append((order, str(key), str(meta["tablename"])))
    rows.sort(key=lambda r: (r[0], r[1]))
    return [(key, name) for _, key, name in rows]


# ---------------------------------------------------------------
# 杂项
# ---------------------------------------------------------------

_SAFE_NAME_RE = re.compile(r"[\\/:*?\"<>|\x00-\x1f]")


def safe_filename(name: str, default: str = "attachment.bin") -> str:
    """把任意来源名称净化为安全文件名（去路径、去非法字符）。"""
    base = str(name or "").replace("\\", "/").split("/")[-1].strip()
    base = _SAFE_NAME_RE.sub("_", base)
    base = base.strip(". ")
    return base or default


def _to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, list):
        # 引用型选择字段：取每项 name
        parts: List[str] = []
        for item in value:
            if isinstance(item, dict):
                parts.append(str(item.get("name") or item.get("showname") or ""))
            else:
                parts.append(str(item))
        return ", ".join(p for p in parts if p)
    if isinstance(value, dict):
        return str(value.get("name") or value.get("showname") or "")
    return str(value)
