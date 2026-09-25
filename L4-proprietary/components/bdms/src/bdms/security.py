"""BDMS 网络安全管理 — 内外网访问控制 + Token 鉴权。

功能：
  1. 外网访问开关（默认关闭）— 关闭后拒绝所有非 localhost 请求
  2. 内网访问开关（默认开启）— 关闭后仅 localhost 可访问
  3. Token 鉴权 — 所有页面/API 需携带有效 Token
  4. Token 管理 — 生成/轮换/禁用，无需管理员权限
"""

import os
import uuid
import hashlib
import secrets
import json
from pathlib import Path
from typing import Optional
from datetime import datetime, timedelta
from functools import wraps

from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse

# ─── 配置文件路径 ───
# 指向项目根目录下的 data/security.json（与 dbms.db 同目录）
SECURITY_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "security.json"


def _load_config() -> dict:
    """加载安全配置。"""
    if SECURITY_CONFIG_PATH.exists():
        with open(SECURITY_CONFIG_PATH, "r") as f:
            return json.load(f)
    return {}


def _save_config(config: dict) -> None:
    """保存安全配置。"""
    SECURITY_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SECURITY_CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    # 设置文件权限为仅所有者可读写（Unix）
    try:
        os.chmod(SECURITY_CONFIG_PATH, 0o600)
    except Exception:
        pass


# ─── 默认配置 ───

DEFAULT_CONFIG = {
    "allow_external": False,       # 外网访问开关（默认关闭）
    "allow_internal": True,        # 内网访问开关（默认开启）
    "token_auth_enabled": True,    # Token 鉴权开关（默认开启）
    "tokens": {},                  # Token 列表：{token_str: {"label": str, "created_at": str, "expires_at": str}}
    "created_at": datetime.now().isoformat(),
}


def init_security() -> dict:
    """初始化安全配置（首次启动时调用）。"""
    config = _load_config()
    if not config:
        config = dict(DEFAULT_CONFIG)
        # 生成初始 admin Token
        token = generate_token("admin")
        config["tokens"] = {
            token: {
                "label": "admin",
                "created_at": datetime.now().isoformat(),
                "expires_at": None,  # 永不过期
            }
        }
        _save_config(config)
    return config


def generate_token(label: str = "user", expires_days: Optional[int] = None) -> str:
    """生成新的访问 Token。

    Args:
        label: Token 标签（用于标识）
        expires_days: 过期天数（None = 永不过期）

    Returns:
        Token 字符串
    """
    token = secrets.token_urlsafe(32)
    config = _load_config()

    expires_at = None
    if expires_days:
        expires_at = (datetime.now() + timedelta(days=days)).isoformat()

    config.setdefault("tokens", {})
    config["tokens"][token] = {
        "label": label,
        "created_at": datetime.now().isoformat(),
        "expires_at": expires_at,
    }
    _save_config(config)
    return token


def revoke_token(token: str) -> bool:
    """撤销指定 Token。"""
    config = _load_config()
    if token in config.get("tokens", {}):
        del config["tokens"][token]
        _save_config(config)
        return True
    return False


def list_tokens() -> list[dict]:
    """列出所有 Token（不含 Token 本身）。"""
    config = _load_config()
    result = []
    for token, meta in config.get("tokens", {}).items():
        result.append({
            "label": meta.get("label", ""),
            "created_at": meta.get("created_at", ""),
            "expires_at": meta.get("expires_at", ""),
            "token_preview": token[:8] + "..." + token[-4:],
        })
    return result


def is_token_valid(token: str) -> bool:
    """检查 Token 是否有效。"""
    config = _load_config()
    tokens = config.get("tokens", {})
    if token not in tokens:
        return False
    meta = tokens[token]
    expires_at = meta.get("expires_at")
    if expires_at:
        try:
            expiry = datetime.fromisoformat(expires_at)
            if datetime.now() > expiry:
                return False
        except ValueError:
            pass
    return True



# ═══════════════════════════════════════════════════════════════
# 角色与权限系统（RBAC）
#
# 统一角色体系，跨 7 个模块复用。
# 角色编码与 DESIGN-DETAIL 各模块 §角色与权限 一致。
# ═══════════════════════════════════════════════════════════════


# ─── 角色定义 ───

class Role:
    """角色编码常量。"""
    SALES = "sales"                  # 销售
    SALES_MANAGER = "sales_manager"  # 销售经理/部门经理
    PM = "pm"                        # 项目经理
    PMO = "pmo"                      # PMO
    TECH = "tech"                    # 交付技术部
    LEGAL = "legal"                  # 法务
    GM = "gm"                        # 高管
    ADMIN = "admin"                  # 管理员
    SUPER_ADMIN = "super_admin"      # 超级管理员


ROLE_LABELS = {
    Role.SALES: "销售",
    Role.SALES_MANAGER: "部门经理",
    Role.PM: "项目经理",
    Role.PMO: "PMO",
    Role.TECH: "交付技术部",
    Role.LEGAL: "法务",
    Role.GM: "高管",
    Role.ADMIN: "管理员",
    Role.SUPER_ADMIN: "超级管理员",
}


# ─── 权限定义 ───
# 格式：<module>.<action>
# 例：contract.create, project.view, dashboard.edit_field

class Permission:
    """权限编码常量（按模块分组）。"""

    # ── 合同管理 ──
    CONTRACT_CREATE = "contract.create"
    CONTRACT_EDIT_DRAFT = "contract.edit_draft"
    CONTRACT_SUBMIT = "contract.submit"
    CONTRACT_APPROVE_L1 = "contract.approve_l1"
    CONTRACT_APPROVE_L2 = "contract.approve_l2"
    CONTRACT_APPROVE_L3 = "contract.approve_l3"
    CONTRACT_APPROVE_L4 = "contract.approve_l4"
    CONTRACT_SIGN = "contract.sign"
    CONTRACT_ARCHIVE = "contract.archive"
    CONTRACT_SCAN_RISKS = "contract.scan_risks"
    CONTRACT_GENERATE_DOCX = "contract.generate_docx"
    CONTRACT_VIEW_ALL = "contract.view_all"
    CONTRACT_VIEW_OWN = "contract.view_own"
    CONTRACT_EXPORT = "contract.export"
    CONTRACT_OA_FETCH = "contract.oa_fetch"
    CONTRACT_WECOM_APPROVAL = "contract.wecom_approval"

    # ── 项目管理 ──
    PROJECT_CREATE = "project.create"
    PROJECT_START = "project.start"
    PROJECT_SUBMIT_DELIVERY = "project.submit_delivery"
    PROJECT_ACCEPT = "project.accept"
    PROJECT_TRANSFER_AFTERSALES = "project.transfer_aftersales"
    PROJECT_CLOSE = "project.close"
    PROJECT_CANCEL = "project.cancel"
    PROJECT_REACTIVATE = "project.reactivate"
    PROJECT_VIEW_ALL = "project.view_all"
    PROJECT_VIEW_OWN = "project.view_own"
    PROJECT_EDIT = "project.edit"

    # ── 售后/工单 ──
    TICKET_ASSIGN = "ticket.assign"
    TICKET_RESOLVE = "ticket.resolve"
    TICKET_VIEW_ALL = "ticket.view_all"

    # ── 风险管理 ──
    RISK_REPORT = "risk.report"
    RISK_RESOLVE = "risk.resolve"
    RISK_VIEW_ALL = "risk.view_all"

    # ── 交付月报 ──
    DELIVERY_GENERATE = "delivery.generate"
    DELIVERY_EXPORT = "delivery.export"
    DELIVERY_VALIDATE = "delivery.validate"
    DELIVERY_VIEW = "delivery.view"

    # ── 确收分析 ──
    REVENUE_IMPORT = "revenue.import"
    REVENUE_GENERATE = "revenue.generate"
    REVENUE_EXPORT = "revenue.export"
    REVENUE_EDIT_MANUAL = "revenue.edit_manual"
    REVENUE_VALIDATE = "revenue.validate"
    REVENUE_VIEW = "revenue.view"

    # ── 利润管理 ──
    PROFIT_VIEW = "profit.view"
    PROFIT_SUBMIT_TIMESHEET = "profit.submit_timesheet"
    PROFIT_APPROVE_TIMESHEET = "profit.approve_timesheet"
    PROFIT_IMPORT_TRAVEL = "profit.import_travel"
    PROFIT_SYNC_REVENUE = "profit.sync_revenue"
    PROFIT_ALERT_RESOLVE = "profit.alert_resolve"

    # ── 驾驶舱 ──
    DASHBOARD_VIEW = "dashboard.view"
    DASHBOARD_EDIT_FIELD = "dashboard.edit_field"
    DASHBOARD_EDIT_FIELD_AMOUNT = "dashboard.edit_field_amount"  # 金额±10%
    DASHBOARD_EDIT_ALL_FIELDS = "dashboard.edit_all_fields"
    DASHBOARD_VIEW_CREATE = "dashboard.view_create"
    DASHBOARD_VIEW_MANAGE = "dashboard.view_manage"

    # ── 数据集成 ──
    INTEGRATION_SYNC = "integration.sync"
    INTEGRATION_CONFIGURE = "integration.configure"
    INTEGRATION_VIEW_LOGS = "integration.view_logs"
    INTEGRATION_RETRY = "integration.retry"

    # ── 系统级 ──
    SYSTEM_USER_MANAGE = "system.user_manage"
    SYSTEM_CONFIG = "system.config"
    SYSTEM_DELETE = "system.delete"        # 物理删除/归档


# ─── 权限矩阵 ───
# key: permission_code, value: set of role codes
# 基于各 DESIGN-DETAIL 的权限矩阵汇总

PERMISSION_MATRIX: dict[str, set[str]] = {
    # ── 合同管理 ──
    Permission.CONTRACT_CREATE:            {Role.SALES, Role.SALES_MANAGER, Role.ADMIN, Role.SUPER_ADMIN},
    Permission.CONTRACT_EDIT_DRAFT:        {Role.SALES, Role.SALES_MANAGER, Role.ADMIN, Role.SUPER_ADMIN},
    Permission.CONTRACT_SUBMIT:            {Role.SALES, Role.SALES_MANAGER, Role.ADMIN, Role.SUPER_ADMIN},
    Permission.CONTRACT_APPROVE_L1:        {Role.SALES_MANAGER, Role.ADMIN, Role.SUPER_ADMIN},
    Permission.CONTRACT_APPROVE_L2:        {Role.LEGAL, Role.ADMIN, Role.SUPER_ADMIN},
    Permission.CONTRACT_APPROVE_L3:        {Role.PMO, Role.ADMIN, Role.SUPER_ADMIN},
    Permission.CONTRACT_APPROVE_L4:        {Role.GM, Role.ADMIN, Role.SUPER_ADMIN},
    Permission.CONTRACT_SIGN:              {Role.SALES, Role.SALES_MANAGER, Role.ADMIN, Role.SUPER_ADMIN},
    Permission.CONTRACT_ARCHIVE:           {Role.ADMIN, Role.SUPER_ADMIN},
    Permission.CONTRACT_SCAN_RISKS:        {Role.SALES, Role.SALES_MANAGER, Role.LEGAL, Role.ADMIN, Role.SUPER_ADMIN},
    Permission.CONTRACT_GENERATE_DOCX:     {Role.SALES, Role.SALES_MANAGER, Role.ADMIN, Role.SUPER_ADMIN},
    Permission.CONTRACT_VIEW_ALL:          {Role.SALES_MANAGER, Role.LEGAL, Role.PMO, Role.GM, Role.ADMIN, Role.SUPER_ADMIN},
    Permission.CONTRACT_VIEW_OWN:          {Role.SALES, Role.SALES_MANAGER, Role.ADMIN, Role.SUPER_ADMIN},
    Permission.CONTRACT_EXPORT:            {Role.SALES_MANAGER, Role.LEGAL, Role.PMO, Role.ADMIN, Role.SUPER_ADMIN},
    Permission.CONTRACT_OA_FETCH:          {Role.ADMIN, Role.SUPER_ADMIN},
    Permission.CONTRACT_WECOM_APPROVAL:    {Role.SALES_MANAGER, Role.LEGAL, Role.PMO, Role.GM, Role.ADMIN, Role.SUPER_ADMIN},

    # ── 项目管理 ──
    Permission.PROJECT_CREATE:             {Role.PM, Role.PMO, Role.ADMIN, Role.SUPER_ADMIN},
    Permission.PROJECT_START:              {Role.PM, Role.PMO, Role.ADMIN, Role.SUPER_ADMIN},
    Permission.PROJECT_SUBMIT_DELIVERY:    {Role.PM, Role.PMO, Role.TECH, Role.ADMIN, Role.SUPER_ADMIN},
    Permission.PROJECT_ACCEPT:             {Role.PMO, Role.ADMIN, Role.SUPER_ADMIN},
    Permission.PROJECT_TRANSFER_AFTERSALES:{Role.PMO, Role.ADMIN, Role.SUPER_ADMIN},
    Permission.PROJECT_CLOSE:              {Role.PMO, Role.ADMIN, Role.SUPER_ADMIN},
    Permission.PROJECT_CANCEL:             {Role.ADMIN, Role.SUPER_ADMIN},
    Permission.PROJECT_REACTIVATE:         {Role.ADMIN, Role.SUPER_ADMIN},
    Permission.PROJECT_VIEW_ALL:           {Role.PMO, Role.GM, Role.ADMIN, Role.SUPER_ADMIN},
    Permission.PROJECT_VIEW_OWN:           {Role.PM, Role.PMO, Role.ADMIN, Role.SUPER_ADMIN},
    Permission.PROJECT_EDIT:               {Role.PM, Role.PMO, Role.ADMIN, Role.SUPER_ADMIN},

    # ── 售后/工单 ──
    Permission.TICKET_ASSIGN:              {Role.PMO, Role.ADMIN, Role.SUPER_ADMIN},
    Permission.TICKET_RESOLVE:             {Role.PMO, Role.TECH, Role.ADMIN, Role.SUPER_ADMIN},
    Permission.TICKET_VIEW_ALL:            {Role.PMO, Role.ADMIN, Role.SUPER_ADMIN},

    # ── 风险管理 ──
    Permission.RISK_REPORT:                {Role.PM, Role.PMO, Role.TECH, Role.ADMIN, Role.SUPER_ADMIN},
    Permission.RISK_RESOLVE:               {Role.PM, Role.PMO, Role.TECH, Role.ADMIN, Role.SUPER_ADMIN},
    Permission.RISK_VIEW_ALL:              {Role.PMO, Role.GM, Role.ADMIN, Role.SUPER_ADMIN},

    # ── 交付月报 ──
    Permission.DELIVERY_GENERATE:          {Role.PMO, Role.ADMIN, Role.SUPER_ADMIN},
    Permission.DELIVERY_EXPORT:            {Role.PMO, Role.ADMIN, Role.SUPER_ADMIN},
    Permission.DELIVERY_VALIDATE:          {Role.PMO, Role.ADMIN, Role.SUPER_ADMIN},
    Permission.DELIVERY_VIEW:              {Role.PMO, Role.GM, Role.ADMIN, Role.SUPER_ADMIN},

    # ── 确收分析 ──
    Permission.REVENUE_IMPORT:             {Role.PMO, Role.ADMIN, Role.SUPER_ADMIN},
    Permission.REVENUE_GENERATE:           {Role.PMO, Role.ADMIN, Role.SUPER_ADMIN},
    Permission.REVENUE_EXPORT:             {Role.PMO, Role.ADMIN, Role.SUPER_ADMIN},
    Permission.REVENUE_EDIT_MANUAL:        {Role.PMO, Role.ADMIN, Role.SUPER_ADMIN},
    Permission.REVENUE_VALIDATE:           {Role.PMO, Role.ADMIN, Role.SUPER_ADMIN},
    Permission.REVENUE_VIEW:               {Role.PMO, Role.GM, Role.ADMIN, Role.SUPER_ADMIN},

    # ── 利润管理 ──
    Permission.PROFIT_VIEW:                {Role.PMO, Role.GM, Role.ADMIN, Role.SUPER_ADMIN},
    Permission.PROFIT_SUBMIT_TIMESHEET:    {Role.PM, Role.TECH, Role.PMO, Role.ADMIN, Role.SUPER_ADMIN},
    Permission.PROFIT_APPROVE_TIMESHEET:   {Role.PMO, Role.ADMIN, Role.SUPER_ADMIN},
    Permission.PROFIT_IMPORT_TRAVEL:       {Role.PMO, Role.ADMIN, Role.SUPER_ADMIN},
    Permission.PROFIT_SYNC_REVENUE:        {Role.PMO, Role.ADMIN, Role.SUPER_ADMIN},
    Permission.PROFIT_ALERT_RESOLVE:       {Role.PMO, Role.ADMIN, Role.SUPER_ADMIN},

    # ── 驾驶舱 ──
    Permission.DASHBOARD_VIEW:             {Role.PMO, Role.GM, Role.ADMIN, Role.SUPER_ADMIN, Role.SALES_MANAGER},
    Permission.DASHBOARD_EDIT_FIELD:       {Role.PM, Role.PMO, Role.ADMIN, Role.SUPER_ADMIN},
    Permission.DASHBOARD_EDIT_FIELD_AMOUNT:{Role.PMO, Role.ADMIN, Role.SUPER_ADMIN},
    Permission.DASHBOARD_EDIT_ALL_FIELDS:  {Role.ADMIN, Role.SUPER_ADMIN},
    Permission.DASHBOARD_VIEW_CREATE:      {Role.PMO, Role.ADMIN, Role.SUPER_ADMIN},
    Permission.DASHBOARD_VIEW_MANAGE:      {Role.ADMIN, Role.SUPER_ADMIN},

    # ── 数据集成 ──
    Permission.INTEGRATION_SYNC:           {Role.PMO, Role.ADMIN, Role.SUPER_ADMIN},
    Permission.INTEGRATION_CONFIGURE:      {Role.ADMIN, Role.SUPER_ADMIN},
    Permission.INTEGRATION_VIEW_LOGS:      {Role.PMO, Role.ADMIN, Role.SUPER_ADMIN},
    Permission.INTEGRATION_RETRY:          {Role.PMO, Role.ADMIN, Role.SUPER_ADMIN},

    # ── 系统级 ──
    Permission.SYSTEM_USER_MANAGE:         {Role.SUPER_ADMIN},
    Permission.SYSTEM_CONFIG:              {Role.SUPER_ADMIN},
    Permission.SYSTEM_DELETE:              {Role.ADMIN, Role.SUPER_ADMIN},
}


# ─── Token → 角色映射 ───
# 每个 Token 可绑定一个或多个角色
# 存储在 security.json 的 tokens.[token].roles 字段


def get_token_roles(token: str) -> list[str]:
    """获取 Token 绑定的角色列表。

    Args:
        token: Bearer Token

    Returns:
        角色编码列表（空列表表示无角色）
    """
    config = _load_config()
    token_info = config.get("tokens", {}).get(token, {})
    roles = token_info.get("roles", [])
    # super_admin 自动拥有所有权限（在 check_permission 中特殊处理）
    return roles if isinstance(roles, list) else []


def set_token_roles(token: str, roles: list[str]) -> bool:
    """设置 Token 的角色。

    Args:
        token: Bearer Token
        roles: 角色编码列表

    Returns:
        是否成功
    """
    config = _load_config()
    if token not in config.get("tokens", {}):
        return False
    config["tokens"][token]["roles"] = roles
    _save_config(config)
    return True


# ─── 权限检查 ───


def has_permission(roles: list[str], permission: str) -> bool:
    """检查角色列表是否拥有指定权限。

    超级管理员（super_admin）拥有所有权限。

    Args:
        roles: 角色编码列表
        permission: 权限编码

    Returns:
        True = 有权限
    """
    if not roles:
        return False

    # super_admin 拥有所有权限
    if Role.SUPER_ADMIN in roles:
        return True

    # admin 拥有大部分业务权限，但不含系统级 user_manage/config
    if Role.ADMIN in roles:
        if permission.startswith("system.") and permission not in {Permission.SYSTEM_DELETE}:
            return False
        return True

    allowed_roles = PERMISSION_MATRIX.get(permission, set())
    return any(role in allowed_roles for role in roles)


def has_permission_token(token: str, permission: str) -> bool:
    """通过 Token 检查权限。

    Args:
        token: Bearer Token
        permission: 权限编码

    Returns:
        True = 有权限
    """
    if not is_token_valid(token):
        return False
    roles = get_token_roles(token)
    return has_permission(roles, permission)


def require_permission(permission: str):
    """FastAPI 依赖注入：权限检查装饰器工厂。

    使用方式：
        @app.get("/contracts")
        def list_contracts(request: Request, _=Depends(require_permission(Permission.CONTRACT_VIEW_ALL))):
            ...

    Raises:
        HTTPException(403): 无权限
    """
    from fastapi import Depends, HTTPException

    def checker(request: Request):
        # 从请求中获取 token
        token = None
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
        if not token:
            token = request.cookies.get("bdms_token", "")

        if not has_permission_token(token or "", permission):
            raise HTTPException(
                status_code=403,
                detail=f"无权限: {permission}",
            )
        return True

    return Depends(checker)


def list_role_permissions(role: str) -> list[str]:
    """列出指定角色拥有的所有权限。

    Args:
        role: 角色编码

    Returns:
        权限编码列表
    """
    if role == Role.SUPER_ADMIN:
        return list(PERMISSION_MATRIX.keys())

    perms = []
    for perm, roles in PERMISSION_MATRIX.items():
        if role in roles:
            perms.append(perm)
    return perms


def list_all_roles() -> list[dict]:
    """列出所有角色及其说明。

    Returns:
        [{code, label, permission_count}] 列表
    """
    result = []
    for code, label in ROLE_LABELS.items():
        result.append({
            "code": code,
            "label": label,
            "permission_count": len(list_role_permissions(code)),
        })
    return result


# ─── FastAPI 中间件 ───

async def security_middleware(request: Request, call_next):
    """安全中间件：内外网访问控制 + Token 鉴权。"""
    config = _load_config()

    # 如果没有任何配置，先初始化
    if not config:
        config = init_security()

    client_host = request.client.host if request.client else "127.0.0.1"

    # ── 1. 外网访问控制 ──
    # 标准化 localhost 地址（处理 IPv4-mapped IPv6 ::ffff:127.0.0.1 等情况）
    def _is_localhost(host):
        h = host.lower()
        return (
            h == "127.0.0.1"
            or h == "::1"
            or h == "localhost"
            or h.startswith("::ffff:127.")  # IPv4-mapped IPv6
            or h == "::ffff:7f00:1"         # ::ffff:127.0.0.1 缩写
        )

    def _is_private(host):
        return (
            host.startswith("10.")
            or host.startswith("172.16.")
            or host.startswith("172.17.")
            or host.startswith("172.18.")
            or host.startswith("172.19.")
            or host.startswith("172.2") and host[6:7].isdigit()  # 172.20-29
            or host.startswith("172.30.")
            or host.startswith("172.31.")
            or host.startswith("192.168.")
        )

    is_localhost = _is_localhost(client_host)
    is_private = _is_private(client_host)
    is_external = not is_localhost and not is_private

    if is_external and not config.get("allow_external", False):
        return JSONResponse(
            status_code=403,
            content={"error": "外网访问已关闭。请在 BDMS 设置中开启外网访问。"},
        )

    # ── 2. 内网访问控制 ──
    if not is_localhost and not config.get("allow_internal", True):
        return JSONResponse(
            status_code=403,
            content={"error": "内网访问已关闭。仅 localhost 可访问。"},
        )

    # ── 3. Token 鉴权 ──
    if config.get("token_auth_enabled", True):
        # 排除白名单路径
        whitelist = ["/api/health", "/login", "/static"]
        path = request.url.path
        if not any(path.startswith(w) for w in whitelist):
            # 从 Header / Cookie / Query 获取 Token
            token = None
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header[7:]
            if not token:
                token = request.cookies.get("bdms_token")
            if not token:
                token = request.query_params.get("token")

            if not token or not is_token_valid(token):
                if path.startswith("/api/"):
                    return JSONResponse(
                        status_code=401,
                        content={"error": "未授权。请提供有效的访问 Token。"},
                    )
                # 页面请求重定向到登录页
                from fastapi.responses import RedirectResponse
                return RedirectResponse(url="/login", status_code=302)

    response = await call_next(request)
    return response


# ─── 登录页 ───

LOGIN_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>BDMS 登录</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: #0f172a; color: #e2e8f0;
            display: flex; align-items: center; justify-content: center;
            min-height: 100vh;
        }
        .login-box {
            background: #1e293b; border-radius: 16px; padding: 3rem;
            width: 100%; max-width: 420px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.4);
        }
        .logo { text-align: center; margin-bottom: 2rem; }
        .logo img { height: 48px; }
        h1 { text-align: center; font-size: 1.5rem; margin-bottom: 0.5rem; }
        .subtitle { text-align: center; color: #94a3b8; margin-bottom: 2rem; font-size: 0.9rem; }
        label { display: block; font-weight: 600; margin-bottom: 0.5rem; font-size: 0.9rem; }
        input[type="password"] {
            width: 100%; padding: 0.75rem 1rem; border-radius: 8px;
            border: 1px solid #334155; background: #0f172a; color: #e2e8f0;
            font-size: 1rem; margin-bottom: 1.5rem;
        }
        input:focus { outline: none; border-color: #1a56db; }
        button {
            width: 100%; padding: 0.75rem; border-radius: 8px;
            background: #1a56db; color: white; border: none;
            font-size: 1rem; font-weight: 600; cursor: pointer;
        }
        button:hover { background: #3b7bf6; }
        .error { color: #f87171; text-align: center; margin-top: 1rem; font-size: 0.85rem; }
        .hint { color: #64748b; text-align: center; margin-top: 1.5rem; font-size: 0.8rem; }
    </style>
</head>
<body>
    <div class="login-box">
        <div class="logo">
            <img src="/static/app/img/logo-white.png" alt="Bangcle" onerror="this.style.display='none'">
        </div>
        <h1>BDMS</h1>
        <p class="subtitle">交付管理系统</p>
        <form method="POST" action="/login">
            <label>访问 Token</label>
            <input type="password" name="token" placeholder="输入 Bearer Token" autofocus required>
            <button type="submit">登 录</button>
        </form>
        <p class="hint">Token 由管理员在 BDMS 设置中生成</p>
    </div>
</body>
</html>
"""


def get_login_html() -> str:
    return LOGIN_HTML
