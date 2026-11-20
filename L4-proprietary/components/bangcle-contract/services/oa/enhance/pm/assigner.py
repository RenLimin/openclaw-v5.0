"""PM 指派分流：按参考项目 PM 所属部门判定由任立民还是冯刚安排（v1.2 C5）。

口径（Rex 2026-11-20）：**按项目经理所属部门**区分指派：
  - 属于**交付中心（项目管理部）**序列 → 由**任立民**安排
  - 属于**区域/其他**序列 → 由**冯刚**安排
数据源：企业微信通讯录（`wecomcli-contact`，机器人需开通「通讯录」权限）。

降级（AGENTS.md 红线）：
  - 企微通讯录不可用（850002 未授权 / 二进制缺失）→ 返回 ``None``，
    由调用方回退 C1（OA 区域负责人/PM 口径），**不伪造部门、不猜测指派**。
"""
from __future__ import annotations

from typing import Optional

# 部门关键词 → 指派人的映射表（关键词命中部门名即归该序列）。
# ⚠️ 关键词需企微通讯录权限开通后用真实部门名校准；当前为**待确认**占位，
#    未命中任何关键词时返回 None（降级），不默认归某一方。
_DEPARTMENT_RULES = (
    # (关键词列表, 指派人, 序列说明)
    (("交付中心", "项目管理部", "项目交付"), "任立民", "交付中心（项目管理部）"),
    (("区域", "营销", "销售", "分公司"), "冯刚", "区域/营销序列"),
)


class AssignerUnavailable(RuntimeError):
    """企微通讯录不可用（显式留证）。"""


def departments_of(name: str) -> list[str]:
    """查企微通讯录取部门（复用 wecomcli-contact 脚本，不重写客户端）。

    返回部门名列表；不可用抛 AssignerUnavailable（由调用方降级）。
    """
    import json
    import subprocess
    import sys
    from pathlib import Path

    here = Path(__file__).resolve()
    skill_script = None
    for base in here.parents:
        cand = base / "L4-proprietary" / "skills" / "wecomcli-contact" / "scripts" / "wecom_contact.py"
        if cand.exists():
            skill_script = cand
            break
    if skill_script is None:
        raise AssignerUnavailable("未找到 wecomcli-contact 脚本")
    try:
        r = subprocess.run(
            [sys.executable, str(skill_script), "--name", name, "--json"],
            capture_output=True, text=True, timeout=90,
        )
    except Exception as exc:  # noqa: BLE001
        raise AssignerUnavailable("调用失败: %s" % exc) from exc
    try:
        data = json.loads(r.stdout)
    except Exception:  # noqa: BLE001
        raise AssignerUnavailable("返回非 JSON（可能 850002 未授权）")
    if data.get("degraded"):
        raise AssignerUnavailable("企微通讯录降级: %s"
                                  % (data["degraded"][0].get("help_message", "")[:80] or "不可用"))
    for block in data.get("results") or []:
        for u in block.get("users") or []:
            if (u.get("name") or "") == name:
                return list(u.get("departments") or [])
    return []


def assigner_for(pm: str) -> Optional[str]:
    """按 PM 姓名查部门 → 指派人（任立民/冯刚）。

    返回指派人姓名；**无法判定时返回 None**（调用方回退 C1），不伪造。
    """
    name = (pm or "").strip()
    if not name:
        return None
    try:
        deps = departments_of(name)
    except AssignerUnavailable:
        return None
    if not deps:
        return None
    joined = " / ".join(deps)
    for keywords, assigner, _label in _DEPARTMENT_RULES:
        if any(k in joined for k in keywords):
            return assigner
    return None
