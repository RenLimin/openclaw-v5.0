"""处置分级策略（L0-L3 安全红线）。

契约见 DESIGN-DETAIL-system-governor-v1.0.md §2.3。
核心原则：
- L0 可逆自愈 / L1 可回滚文件操作：--apply 下执行，否则记 planned。
- L2 需确认 / L3 禁止自动：永不自动执行，记 needs-human / 不动作。
"""
from __future__ import annotations

from .models import Finding

# 档位常量
AUTO = "auto"           # L0 可逆自愈
FILE = "file"           # L1 可回滚文件操作
CONFIRM = "confirm"     # L2 需人工确认
FORBIDDEN = "forbidden" # L3 禁止自动

# 每个 finding 可由 lane 适配器显式声明档位（放在 evidence 前缀约定键里，
# 或由 policy 按 item 规则表推断）。v1.0 采用「规则表 + 显式覆盖」。
# 规则表：item 前缀 → 默认档位
_ITEM_TIER: dict[str, str] = {
    # Lane A — 可逆自愈
    "llm_timeout": AUTO,
    "cron_retry": AUTO,
    "quota_restore": AUTO,
    "compaction_retry": AUTO,
    "pending_recovery": AUTO,
    # Lane A/B — 服务拉起（guardian 常驻自动，governor 只聚合）
    "service_down": AUTO,
    # 配置/key 类 — 需人工
    "provider_key_format": CONFIRM,
    "provider_config": CONFIRM,
    "plugin_channel": CONFIRM,
    "doctor_fix": CONFIRM,
    # Lane C — 文件操作
    "temp_clean": FILE,
    "archive": FILE,
    # Lane D — 只读
    "task_inventory": CONFIRM,  # 只读盘点，无写动作
}

DEFAULT_TIER = CONFIRM  # 未知项默认需人工，宁可停手


def tier_for(finding: Finding) -> str:
    """返回 finding 的处置档位。"""
    # Lane D 是纯只读盘点，任何条目都不产生写动作（与 Lane C 的 archive 文件
    # 动作前缀 "archive" 撞名，故按 lane 隔离，优先判定）。
    if finding.lane == "D":
        return CONFIRM
    # 显式覆盖：适配器可在 evidence 中附 "tier=<X>" 前缀
    for line in finding.evidence.splitlines():
        line = line.strip()
        if line.startswith("tier="):
            t = line.split("=", 1)[1].strip()
            if t in (AUTO, FILE, CONFIRM, FORBIDDEN):
                return t
    for prefix, tier in _ITEM_TIER.items():
        if finding.item.startswith(prefix):
            return tier
    return DEFAULT_TIER


def resolve_status(finding: Finding, apply: bool) -> str:
    """根据档位与 apply 标志，决定 finding 落账状态。"""
    tier = tier_for(finding)
    if tier == FORBIDDEN:
        return "open"                 # 记录但永不动作
    if tier == CONFIRM:
        return "needs-human"
    if apply:
        return "auto-fixed"           # L0/L1 在 apply 下执行
    return "planned"                  # dry-run：仅计划


def will_write(finding: Finding, apply: bool) -> bool:
    """该 finding 在本次 run 是否会产生写动作。"""
    tier = tier_for(finding)
    return apply and tier in (AUTO, FILE)
