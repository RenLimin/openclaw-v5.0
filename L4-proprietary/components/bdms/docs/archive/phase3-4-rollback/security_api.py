"""BDMS Web API — 安全设置路由。"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/security", tags=["security"])


class ConfigUpdateRequest(BaseModel):
    allow_external: bool | None = None
    allow_internal: bool | None = None
    token_auth_enabled: bool | None = None


class TokenCreateRequest(BaseModel):
    label: str = "user"
    expires_days: int | None = None


@router.get("/config")
async def get_config():
    from bdms.security import _load_config
    config = _load_config()
    return {
        "allow_external": config.get("allow_external", False),
        "allow_internal": config.get("allow_internal", True),
        "token_auth_enabled": config.get("token_auth_enabled", True),
    }


@router.post("/config")
async def update_config(req: ConfigUpdateRequest):
    from bdms.security import _load_config, _save_config
    config = _load_config()
    if req.allow_external is not None:
        config["allow_external"] = req.allow_external
    if req.allow_internal is not None:
        config["allow_internal"] = req.allow_internal
    if req.token_auth_enabled is not None:
        config["token_auth_enabled"] = req.token_auth_enabled
    _save_config(config)
    return {"ok": True}


@router.get("/tokens")
async def list_tokens():
    from bdms.security import list_tokens
    return list_tokens()


@router.post("/tokens")
async def create_token(req: TokenCreateRequest):
    from bdms.security import generate_token
    token = generate_token(label=req.label, expires_days=req.expires_days)
    return {"token": token, "label": req.label}


@router.delete("/tokens/{token_preview}")
async def delete_token(token_preview: str):
    from bdms.security import _load_config, _save_config
    # 通过预览匹配撤销 Token
    config = _load_config()
    tokens = config.get("tokens", {})
    to_revoke = None
    for token in tokens:
        if token[:8] + "..." + token[-4:] == token_preview:
            to_revoke = token
            break
    if to_revoke:
        del tokens[to_revoke]
        _save_config(config)
        return {"ok": True}
    raise HTTPException(404, "Token 未找到")
