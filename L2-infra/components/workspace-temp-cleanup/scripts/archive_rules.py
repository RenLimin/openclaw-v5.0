"""归档规则引擎（纯逻辑，无 IO 副作用）。

契约见 DESIGN-DETAIL-system-governor-v1.0.md §3.3。
规则按「类型 + 体积 + 账龄」匹配；排除目录永不归档。
规则命中返回 RuleHit；不命中/排除返回 None。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# ── 阈值（可在后续版本外置配置）─────────────────────────────────────────
LARGE_PRODUCT_BYTES = 50 * 1024 * 1024   # R1: 50MB
INTERMEDIATE_AGE_DAYS = 30               # R2
BACKUP_AGE_DAYS = 90                     # R3

LARGE_EXTS = {".xlsx", ".pptx"}
INTERMEDIATE_DIR_NAMES = {"tmp", "scratch"}
INTERMEDIATE_EXTS = {".tmp", ".bak"}
BACKUP_SUFFIXES = (".backup",)
BACKUP_RE = __import__("re").compile(r"\.bak\.v\d+$")

# R4 排除：路径任一部分命中即永不归档
EXCLUDE_DIR_NAMES = {
    ".git", "node_modules", "__pycache__", ".archive", ".trash",
    "data", "memory",
}
EXCLUDE_FILE_NAMES = {"bdms.db"}
# output 当前周期产物不归档
PROTECTED_TOP_DIRS = {"output"}


@dataclass(frozen=True)
class RuleHit:
    rule_id: str            # "R1"|"R2"|"R3"
    reason: str             # 人读原因
    archive_subdir: str     # .archive 下的子目录：""/"intermediate"/"backup"


def _age_days(mtime_epoch: float, now_epoch: float) -> int:
    return int((now_epoch - mtime_epoch) / 86400)


def _is_excluded(path: Path, root: Path) -> bool:
    """R4：排除路径。返回 True = 永不归档。"""
    try:
        rel = path.relative_to(root)
    except ValueError:
        return True
    parts = rel.parts
    # 顶层受保护目录
    if parts and parts[0] in EXCLUDE_DIR_NAMES:
        return True
    for part in parts:
        if part in EXCLUDE_DIR_NAMES:
            return True
    if path.name in EXCLUDE_FILE_NAMES:
        return True
    # output 当前周期产物保护
    if parts and parts[0] in PROTECTED_TOP_DIRS:
        return True
    return False


def classify(path: Path, root: Path, *, mtime_epoch: float,
             size_bytes: int, now_epoch: float) -> RuleHit | None:
    """对单个文件/目录判定归档规则。不命中返回 None。

    调用方负责 stat（便于测试注入虚拟 mtime/size，不依赖真实文件）。
    """
    if _is_excluded(path, root):
        return None

    name = path.name
    suffix = path.suffix.lower()
    age = _age_days(mtime_epoch, now_epoch)

    # R3：历史备份（.backup / .bak.vN），账龄 > 90
    if name.endswith(BACKUP_SUFFIXES) or BACKUP_RE.search(name):
        if age > BACKUP_AGE_DAYS:
            return RuleHit("R3", f"历史备份 {name}，账龄 {age}d > {BACKUP_AGE_DAYS}d",
                           "backup")

    # R1：大体积产物（.xlsx/.pptx > 50MB）
    if suffix in LARGE_EXTS and size_bytes > LARGE_PRODUCT_BYTES:
        return RuleHit("R1",
                       f"大体积 {suffix} {size_bytes // 1024 // 1024}MB > 50MB",
                       "")

    # R2：过期中间件（tmp/scratch 目录内 或 .tmp/.bak），账龄 > 30
    rel_parts = path.relative_to(root).parts
    in_intermediate = bool(rel_parts and rel_parts[0] in INTERMEDIATE_DIR_NAMES)
    if in_intermediate or suffix in INTERMEDIATE_EXTS:
        if age > INTERMEDIATE_AGE_DAYS:
            return RuleHit("R2",
                           f"过期中间件 {name}，账龄 {age}d > {INTERMEDIATE_AGE_DAYS}d",
                           "intermediate")

    return None
