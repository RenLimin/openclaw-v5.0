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


def raw_dir() -> Path:
    """ONES 复用脚本的默认 raw 目录。"""
    return _load().RAW_DEFAULT


def load_error() -> Optional[str]:
    """最近一次加载失败原因（用于显式留证）。"""
    return _load_error
