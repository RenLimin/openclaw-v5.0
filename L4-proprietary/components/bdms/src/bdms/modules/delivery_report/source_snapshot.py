"""原始数据源快照 —— 生成月报时把"本次实际使用"的源文件永久归档到 workspace。

设计要点
--------
- **复用现有路径解析**：ONES 三类走 ``core.paths.find_ones_file``（含月份回退），
  确收对比表走 ``paths.find_revenue_source``，交接 CSV 走
  ``engine._resolve_csv``。归档的永远是引擎本次真正读到的文件，不按月份名臆造。
- **永久落盘**：文件放 ``data/source_snapshots/<month>/``（data/ 已被 .gitignore
  排除，故不提交 GitHub）。同名文件再次归档时若内容变化，旧版自动移入
  ``history/<timestamp>__<name>``，绝不覆盖丢失。
- **可追溯**：写 ``MANIFEST.json``（源路径、字节数、SHA256、归档时间）。
- **best-effort**：归档失败不阻断月报生成（由调用方捕获异常）。
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ─────────────────────────────────────────────────────────
#  路径
# ─────────────────────────────────────────────────────────

def _default_snapshot_root() -> Path:
    from bdms.core import paths
    return paths.DATA_DIR / "source_snapshots"


# ─────────────────────────────────────────────────────────
#  源文件解析（与引擎读取口径一致）
# ─────────────────────────────────────────────────────────

def resolve_source_files(month: str) -> List[Tuple[str, Path]]:
    """返回本次生成实际命中的源文件 [(category, path), ...]。

    缺失的源不列入（返回空 DataFrame 的分支本就无文件）。
    category: ones / revenue / handoff。
    """
    from bdms.core import paths
    from bdms.modules.delivery_report import engine

    out: List[Tuple[str, Path]] = []

    # ONES 三类（find_ones_file 内部含月份回退）
    for kind in ("sign", "poc", "exception"):
        p = paths.find_ones_file(month, kind)
        if p is not None:
            out.append(("ones", p))

    # 确收差异分析对比表
    rev = paths.find_revenue_source(month)
    if rev is not None:
        out.append(("revenue", rev))

    # 确收 / 验收 交接 CSV
    for kind in ("revenue", "acceptance"):
        p = engine._resolve_csv(month, kind)
        if p is not None:
            out.append(("handoff", p))

    return out


# ─────────────────────────────────────────────────────────
#  Hash
# ─────────────────────────────────────────────────────────

def _sha256(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for blk in iter(lambda: f.read(chunk), b""):
            h.update(blk)
    return h.hexdigest()


# ─────────────────────────────────────────────────────────
#  归档
# ─────────────────────────────────────────────────────────

def archive_sources(month: str,
                    snapshot_root: Optional[Path] = None,
                    sources: Optional[List[Tuple[str, Path]]] = None
                    ) -> Dict:
    """把当月源文件归档到 workspace（幂等；内容变化时旧版进 history/）。

    Returns
    -------
    {"month", "snapshot_dir", "archived": [...], "history": [...]}
    """
    root = Path(snapshot_root) if snapshot_root else _default_snapshot_root()
    snap_dir = root / month
    history_dir = snap_dir / "history"
    snap_dir.mkdir(parents=True, exist_ok=True)

    if sources is None:
        sources = resolve_source_files(month)

    archived: List[Dict] = []
    moved_history: List[str] = []
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")

    for category, src in sources:
        src = Path(src)
        if not src.exists():
            archived.append({"category": category, "source": str(src),
                             "error": "SOURCE_MISSING"})
            continue

        dst = snap_dir / src.name
        new_hash = _sha256(src)

        # 永久保护：已存在且内容不同 → 旧版转 history/
        if dst.exists() and _sha256(dst) != new_hash:
            history_dir.mkdir(exist_ok=True)
            keep = history_dir / f"{stamp}__{src.name}"
            shutil.copy2(dst, keep)
            moved_history.append(keep.name)

        shutil.copy2(src, dst)
        archived.append({
            "category": category,
            "source": str(src),
            "archived": dst.name,
            "bytes": dst.stat().st_size,
            "sha256": new_hash,
        })

    manifest = {
        "report_month": month,
        "archived_at": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "purpose": "原始数据源永久备查（本地落盘，.gitignore 排除，不提交 GitHub）",
        "files": archived,
        "history": moved_history,
    }
    (snap_dir / "MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    return {"month": month, "snapshot_dir": str(snap_dir),
            "archived": archived, "history": moved_history}
