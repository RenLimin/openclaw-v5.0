"""OA 会话探测工具（从 conftest 抽出，避免 tests 目录间 conftest.py 撞名）。"""
import json
import os

OA_STATE = os.path.expanduser("~/.openclaw/data/clm-oa-recon/state.json")


def oa_session_available() -> bool:
    """探测 OA storage_state 是否可用（文件存在 + 含 bangcle.com cookie）。"""
    if not os.path.isfile(OA_STATE):
        return False
    try:
        state = json.load(open(OA_STATE, encoding="utf-8"))
    except Exception:
        return False
    cookies = state.get("cookies", [])
    return any("bangcle.com" in (c.get("domain") or "") for c in cookies)
