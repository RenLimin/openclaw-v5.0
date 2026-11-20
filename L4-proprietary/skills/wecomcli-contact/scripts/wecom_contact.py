#!/usr/bin/env python3
"""企业微信通讯录查询（只读）：按姓名/关键词检索成员 + 所属部门。

能力落点：L4-proprietary/skills/wecomcli-contact/（Rex 2026-11-20 批准重建）。
底层复用既有能力 ``bdms.core.wecom.wecom_cli_call``（不重写客户端）。

硬门禁（AGENTS.md 降级红线）：
  - 机器人未开通「通讯录」权限 → wecom-cli 返回 errcode 850002 → **显式降级**，
    输出「权限未开通」+ 授权链接，**禁止编造部门**。
  - 无凭据 / 二进制缺失 → 同样显式降级。

用法：
  wecom_contact.py --name 任立民
  wecom_contact.py --names 徐亚东 潘天功
  wecom_contact.py --json            # 原始 JSON
  wecom_contact.py --check           # 能力可用性探测
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# 复用 bdms 的 wecom-cli 调用封装（权威源，避免重写）
_REPO = Path(__file__).resolve()
for _base in _REPO.parents:
    if (_base / "AGENTS.md").exists():
        _BDMS_SRC = _base / "L4-proprietary/components/bdms/src"
        break
else:  # pragma: no cover
    _BDMS_SRC = Path("L4-proprietary/components/bdms/src")
if str(_BDMS_SRC) not in sys.path:
    sys.path.insert(0, str(_BDMS_SRC))

try:
    from bdms.core import wecom  # type: ignore
except Exception as exc:  # noqa: BLE001 - 显式降级，不静默
    print(json.dumps({"_error": "无法加载 bdms.core.wecom: %s" % exc}, ensure_ascii=False))
    raise SystemExit(2)

NO_AUTH_CODE = 850002


def _find_bin() -> str:
    """定位二进制（复用 bdms 逻辑）。"""
    return wecom._find_cli_bin() or ""


def check() -> int:
    """能力可用性探测（二进制 / 凭据 / 通讯录权限）。"""
    out = {"bin": _find_bin() or "【缺失】"}
    if not out["bin"] or not os.path.isfile(out["bin"]):
        out["status"] = "unavailable"
        out["reason"] = "未找到 wecom-cli 二进制"
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 2
    bid, sec = wecom._read_openclaw_credentials()
    out["credentials"] = bool(bid and sec)
    r = wecom.wecom_cli_call(["auth", "show"])
    raw = (r or {}).get("_raw_output", "") if isinstance(r, dict) else ""
    out["auth"] = "authorized" if "authorized" in raw else "未授权"
    # 实测一次通讯录权限
    probe = wecom.wecom_cli_call(["contact", "users", "search",
                                  "--keywords", "测试", "--search-mode", "list"])
    if isinstance(probe, dict) and probe.get("errcode") == NO_AUTH_CODE:
        out["contact"] = "no_permission"
        out["help_message"] = probe.get("help_message", "")
        out["status"] = "unavailable"
    elif isinstance(probe, dict) and "users" in probe:
        out["contact"] = "ok"
        out["status"] = "ok"
    else:
        out["contact"] = "unknown"
        out["status"] = "degraded"
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if out["status"] == "ok" else 1


def _fmt_user(u: dict) -> dict:
    """归一用户字段（schema: QueryUserOpenUserInfo）。"""
    deps = u.get("departments") or []
    dep_names = []
    for d in deps:
        if isinstance(d, dict):
            n = d.get("name") or d.get("department_name") or ""
            if n and n not in dep_names:
                dep_names.append(n)
        elif isinstance(d, str) and d and d not in dep_names:
            dep_names.append(d)
    return {
        "name": u.get("name") or "",
        "userid": u.get("userid") or "",
        "position": u.get("position") or "",
        "departments": dep_names,
    }


def query(names: list[str], as_json: bool = False) -> int:
    """按姓名检索成员 + 部门。"""
    if not _find_bin():
        print(json.dumps({"_error": "未找到 wecom-cli 二进制"}, ensure_ascii=False))
        return 2
    bid, sec = wecom._read_openclaw_credentials()
    if not (bid and sec):
        print(json.dumps({"_error": "无企微 botId/secret，无法调用"}, ensure_ascii=False))
        return 2
    results: list[dict] = []
    degraded: list[dict] = []
    for nm in names:
        r = wecom.wecom_cli_call(["contact", "users", "search",
                                  "--keywords", nm, "--search-mode", "list"])
        if not isinstance(r, dict):
            degraded.append({"name": nm, "reason": "调用失败（无响应）"})
            continue
        if r.get("errcode"):
            degraded.append({
                "name": nm,
                "errcode": r.get("errcode"),
                "errmsg": r.get("errmsg", ""),
                "help_message": r.get("help_message", ""),
            })
            continue
        users = [_fmt_user(u) for u in (r.get("users") or [])]
        results.append({"query": nm, "users": users})
    if as_json:
        print(json.dumps({"results": results, "degraded": degraded},
                         ensure_ascii=False, indent=2))
        return 0 if results else 1
    for block in results:
        print("### %s" % block["query"])
        if not block["users"]:
            print("  （无结果）")
        for u in block["users"]:
            deps = " / ".join(u["departments"]) or "【缺失】"
            print("  %s（userid=%s）部门：%s｜职务：%s"
                  % (u["name"], u["userid"] or "—", deps, u["position"] or "—"))
    for d in degraded:
        if d.get("errcode") == NO_AUTH_CODE:
            print("\n⚠️ 通讯录权限未开通（errcode 850002）")
            print(d.get("help_message", ""))
            print("→ 能力降级：需机器人在企微后台开通「通讯录」权限后重试；不编造部门。")
        else:
            print("\n⚠️ 查询降级：%s" % json.dumps(d, ensure_ascii=False))
    return 0 if results else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="企微通讯录查询（只读）")
    ap.add_argument("--name", help="单个姓名")
    ap.add_argument("--names", nargs="+", help="多个姓名")
    ap.add_argument("--json", action="store_true", dest="as_json", help="输出 JSON")
    ap.add_argument("--check", action="store_true", help="能力可用性探测")
    args = ap.parse_args()
    if args.check:
        return check()
    names = []
    if args.name:
        names.append(args.name)
    if args.names:
        names.extend(args.names)
    if not names:
        ap.error("需 --name 或 --names")
    return query(names, args.as_json)


if __name__ == "__main__":
    raise SystemExit(main())
