"""ONES GraphQL 客户端（只读复用层）。

复用权威源 ``L4-proprietary/skills/ones-browser-export/scripts/oa_workflow_ones.py``
的 ``gql`` / ``project_by_code`` / ``project_tasks``（经 Chrome 页面上下文 XHR，绕开直连 token 过期）。

不重写 ONES 自动化（红线：复用既有能力）。本模块只做**加载 + 薄封装**。
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

# 权威源 skill 脚本（相对本组件定位，避免写死 parents[N]）
_HERE = Path(__file__).resolve()
# .../bangcle-contract/services/oa/enhance/ones_client.py
_COMPONENT_ROOT = _HERE.parents[3]          # bangcle-contract/
_REPO_ROOT = _COMPONENT_ROOT.parents[2]      # workspace 根（L4-proprietary/components/bangcle-contract → 上两级）
_ONES_SCRIPT = (
    _REPO_ROOT
    / "L4-proprietary"
    / "skills"
    / "ones-browser-export"
    / "scripts"
    / "oa_workflow_ones.py"
)

_module = None
_load_error: Optional[str] = None


def _load() -> Any:
    """懒加载权威源脚本为模块（import 期无副作用，仅定义常量/函数）。"""
    global _module, _load_error
    if _module is not None:
        return _module
    if not _ONES_SCRIPT.exists():
        _load_error = "未找到 ONES 复用脚本: %s" % _ONES_SCRIPT
        raise RuntimeError(_load_error)
    try:
        spec = importlib.util.spec_from_file_location("oa_workflow_ones_reuse", _ONES_SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        sys.modules["oa_workflow_ones_reuse"] = mod
        spec.loader.exec_module(mod)
        _module = mod
        return _module
    except Exception as exc:  # noqa: BLE001 - 显式转译，不静默
        _load_error = "ONES 复用脚本加载失败: %s" % exc
        raise RuntimeError(_load_error) from exc


def project_by_code(code: str) -> Optional[Dict[str, str]]:
    """按项目编号 SSXM-* 定位项目（返回 {uuid, name}）。"""
    return _load().project_by_code(code)


def project_tasks(uuid: str) -> List[Dict[str, Any]]:
    """取项目下全部任务（含 status / issueType / owner）。"""
    return _load().project_tasks(uuid)


def project_status(uuid: str) -> str:
    """取项目状态名（复用脚本内同款 GraphQL）。"""
    mod = _load()
    r = mod.gql(
        'query { project(key:"project-%s") { status{name} } }' % uuid
    )
    return (
        (((r.get("data") or {}).get("project") or {}).get("status") or {}).get("name")
        or ""
    )


def project_pm(uuid: str) -> tuple[str, str]:
    """参考项目对应项目经理（Rex 2026-11-20 口径：履约义务/项目记录对应的负责人）。

    ONES 项目对象 owner 恒为「管理员」（无 PM 语义）；任务 ``_2jEz2XG9`` 实测全空。
    实测可用字段：任务 ``owner`` 与 ``assign``。取数优先级：
      ① 履约义务（issueType=项目履约义务）任务的 owner/assign
      ② 项目记录类（项目信息/项目管理）任务的 owner/assign
    同一项目多人时取出现次数最多者（并列取字典序），并记录依据。
    返回 (姓名, 依据)；无则 ("", "")，不伪造。
    """
    mod = _load()
    q = ('query { tasks(filter:{project_in:["%s"]}) { name owner{name} assign{name} '
         'issueType{name} } }' % uuid)
    r = mod.gql(q)
    tasks = (r.get("data") or {}).get("tasks") or []
    if not tasks:
        return "", ""
    from collections import Counter
    ob_c = Counter()
    rec_c = Counter()

    def _pick(persons: Counter) -> str:
        persons.pop("", None)
        persons.pop("管理员", None)
        persons.pop("流程自动化", None)
        if not persons:
            return ""
        top = max(persons.values())
        return sorted(k for k, v in persons.items() if v == top)[0]

    for t in tasks:
        it = (t.get("issueType") or {}).get("name") or ""
        who = (t.get("assign") or {}).get("name") or (t.get("owner") or {}).get("name") or ""
        if not who or who in ("管理员", "流程自动化"):
            continue
        if it == "项目履约义务":
            ob_c[who] += 1
        elif it in ("项目信息", "项目管理", "项目记录"):
            rec_c[who] += 1
    if ob_c:
        return _pick(ob_c), "履约义务任务负责人（%s）" % "、".join(
            "%s×%d" % (k, v) for k, v in ob_c.most_common())
    if rec_c:
        return _pick(rec_c), "项目记录任务负责人（%s）" % "、".join(
            "%s×%d" % (k, v) for k, v in rec_c.most_common())
    return "", ""


def raw_dir() -> Path:
    """ONES 复用脚本的默认 raw 目录。"""
    return _load().RAW_DEFAULT


def load_error() -> Optional[str]:
    """最近一次加载失败原因（用于显式留证）。"""
    return _load_error


def license_period(tasks: list[dict]) -> tuple[str, str]:
    """从【云端】license/授权/维保任务描述取授权区间（复用权威源脚本，含中文日期）。

    返回 (规范化区间, 证据任务号)；无记录返回 ("", "")，不伪造。
    """
    return _load().license_period(tasks)


def search_projects(name_match: str) -> list[dict]:
    """按项目名模糊搜索（复用权威源脚本 gql）。

    仅作候选定位；调用方须自行做精确包含校验，禁止用宽泛匹配下结论。
    """
    mod = _load()
    r = mod.gql('query { projects(filter:{name_match:"%s"}) { uuid name } }' % name_match)
    return (r.get("data") or {}).get("projects") or []
