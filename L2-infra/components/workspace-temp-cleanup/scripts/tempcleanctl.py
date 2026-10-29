#!/usr/bin/env python3
"""tempcleanctl — workspace 临时资产清理 CLI (INFRA-CLN-001).

只删"已标记"的临时资产（registry .openclaw-temp.json 或命名约定），
删除只走 /usr/bin/trash，默认 dry-run。未标记一律不碰。
"""
from __future__ import annotations
import argparse, json, subprocess, sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

DEFAULT_TTL = {"intermediate": 7, "ledger": 30}
CONVENTION_DIRS = {"tmp", "scratch", "analysis_output"}
CONVENTION_SUBDIR = "scripts/tmp"
REGISTRY_NAME = ".openclaw-temp.json"

EXIT_OK, EXIT_ERR, EXIT_EXPIRED, EXIT_VERIFY = 0, 1, 2, 3


@dataclass
class Candidate:
    path: Path
    kind: str
    ttl_days: int
    created: date
    mtime: date
    size_bytes: int
    source: str
    age_days: int
    expired: bool


def find_root(start: Path | None = None) -> Path:
    cur = (start or Path.cwd()).resolve()
    for p in [cur, *cur.parents]:
        if (p / ".git").is_dir() or (p / REGISTRY_NAME).exists():
            return p
    return cur


def trash_available() -> bool:
    import shutil
    return bool(shutil.which("trash")) or Path("/usr/bin/trash").exists()


def load_registry(root: Path, registry: Path | None):
    """返回 (entries, error)。无文件=空列表；非法=error。fail-closed。"""
    path = registry or (root / REGISTRY_NAME)
    if not path.exists():
        return [], None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        return [], f"registry 非法 JSON: {e}"
    if not isinstance(data, dict) or data.get("version") != 1:
        return [], "registry 缺少 version=1"
    entries = data.get("entries")
    if not isinstance(entries, list):
        return [], "registry.entries 必须是数组"
    return entries, None


def parse_date(s, fallback: date) -> date:
    if not s:
        return fallback
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return fallback


def dir_latest_mtime(p: Path) -> float:
    latest = p.stat().st_mtime
    if p.is_dir():
        for child in p.rglob("*"):
            if child.is_symlink():
                continue
            try:
                latest = max(latest, child.stat().st_mtime)
            except OSError:
                pass
    return latest


def dir_size(p: Path) -> int:
    if p.is_file():
        return p.stat().st_size
    total = 0
    for child in p.rglob("*"):
        if child.is_symlink():
            continue
        try:
            if child.is_file():
                total += child.stat().st_size
        except OSError:
            pass
    return total


def resolve_inside(root: Path, rel: str) -> Path | None:
    """防越界：结果必须在 root 内。"""
    target = (root / rel).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError:
        return None
    return target


def build_candidate(target: Path, kind: str, ttl_days: int,
                    created: date, source: str, today: date) -> Candidate:
    mts = dir_latest_mtime(target)
    mtime = datetime.fromtimestamp(mts).date()
    origin = max(created, mtime)
    age = (today - origin).days
    return Candidate(
        path=target, kind=kind, ttl_days=ttl_days, created=created,
        mtime=mtime, size_bytes=dir_size(target), source=source,
        age_days=age, expired=age > ttl_days,
    )


def collect(root: Path, registry: Path | None, today: date):
    """返回 (candidates, error)。"""
    cands: dict[str, Candidate] = {}
    entries, err = load_registry(root, registry)
    if err:
        return [], err

    # registry 优先
    for e in entries:
        if not isinstance(e, dict) or not e.get("path"):
            continue
        target = resolve_inside(root, e["path"])
        if target is None or not target.exists():
            continue
        kind = e.get("kind", "intermediate")
        ttl = int(e.get("ttl_days", DEFAULT_TTL.get(kind, 7)))
        created = parse_date(e.get("created"),
                            datetime.fromtimestamp(target.stat().st_mtime).date())
        cands[str(target)] = build_candidate(target, kind, ttl, created,
                                             "registry", today)

    # convention：顶层约定目录 + scripts/tmp + *-tmp/*.tmp
    conv_paths: set[Path] = set()
    for name in CONVENTION_DIRS:
        p = root / name
        if p.exists():
            conv_paths.add(p)
    stmp = root / CONVENTION_SUBDIR
    if stmp.exists():
        conv_paths.add(stmp)
    for p in root.glob("*-tmp"):
        if p.is_dir() and not p.is_symlink():
            conv_paths.add(p)
    for p in root.glob("*.tmp"):
        conv_paths.add(p)

    for target in conv_paths:
        key = str(target.resolve())
        if key in cands:
            continue
        created = datetime.fromtimestamp(target.stat().st_mtime).date()
        cands[key] = build_candidate(target, "intermediate",
                                     DEFAULT_TTL["intermediate"],
                                     created, "convention", today)
    return list(cands.values()), None


def fmt_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}GB"


def print_report(cands: list[Candidate], as_json: bool) -> None:
    if as_json:
        print(json.dumps([{
            "path": str(c.path), "kind": c.kind, "ttl_days": c.ttl_days,
            "age_days": c.age_days, "size": c.size_bytes,
            "source": c.source, "expired": c.expired,
        } for c in cands], ensure_ascii=False, indent=1))
        return
    if not cands:
        print("（无临时资产）")
        return
    print(f"{'状态':<6}{'年龄':>4} {'TTL':>4} {'大小':>8}  来源        路径")
    for c in sorted(cands, key=lambda x: (not x.expired, x.path)):
        flag = "过期" if c.expired else "保留"
        print(f"{flag:<6}{c.age_days:>3}d {c.ttl_days:>3}d "
              f"{fmt_size(c.size_bytes):>8}  {c.source:<10} {c.path}")


def cmd_dry_run(root, reg, as_json):
    cands, err = collect(root, reg, date.today())
    if err:
        print(f"错误: {err}", file=sys.stderr)
        return EXIT_ERR
    print_report(cands, as_json)
    return EXIT_EXPIRED if any(c.expired for c in cands) else EXIT_OK


def cmd_list(root, reg, as_json):
    cands, err = collect(root, reg, date.today())
    if err:
        print(f"错误: {err}", file=sys.stderr)
        return EXIT_ERR
    print_report(cands, as_json)
    return EXIT_OK


def cmd_clean(root, reg, yes: bool):
    if not yes:
        print("拒绝执行：clean 需要显式 --yes（可先 dry-run 预览）",
              file=sys.stderr)
        return EXIT_ERR
    if not trash_available():
        print("错误: trash 不可用，绝不 fallback 永久删除，已中止",
              file=sys.stderr)
        return EXIT_ERR
    cands, err = collect(root, reg, date.today())
    if err:
        print(f"错误: {err}", file=sys.stderr)
        return EXIT_ERR
    expired = [c for c in cands if c.expired]
    deleted, failed = [], []
    for c in expired:
        r = subprocess.run(["trash", str(c.path)], capture_output=True, text=True)
        (deleted if r.returncode == 0 else failed).append(c.path)
    for p in deleted:
        print(f"🗑  trashed {p}")
    for p in failed:
        print(f"✗ failed  {p}", file=sys.stderr)
    print(f"删除 {len(deleted)}，失败 {len(failed)}")
    # 退出码：有成功删除=0；全失败=1
    return EXIT_OK if deleted or not expired else (EXIT_ERR if failed else EXIT_OK)


def cmd_verify(root, reg):
    problems = []
    if not trash_available():
        problems.append("trash 缺失（/usr/bin/trash）")
    entries, err = load_registry(root, reg)
    if err:
        problems.append(err)
    gi = root / ".gitignore"
    needed = ["analysis_output/"]
    if gi.exists():
        text = gi.read_text(encoding="utf-8")
        for n in needed:
            if n not in text:
                problems.append(f".gitignore 未覆盖 {n}")
    else:
        problems.append(".gitignore 不存在")
    if problems:
        for p in problems:
            print(f"✗ {p}", file=sys.stderr)
        return EXIT_VERIFY
    print("✓ trash 可用 / registry 合法 / gitignore 已覆盖临时区")
    return EXIT_OK


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="tempcleanctl",
                                 description="workspace 临时资产清理 (INFRA-CLN-001)")
    ap.add_argument("--root", type=Path, default=None)
    ap.add_argument("--registry", type=Path, default=None)
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("dry-run"); d.add_argument("--json", action="store_true")
    l = sub.add_parser("list"); l.add_argument("--json", action="store_true")
    c = sub.add_parser("clean"); c.add_argument("--yes", action="store_true")
    sub.add_parser("verify")
    args = ap.parse_args(argv)
    root = find_root(args.root)

    if args.cmd == "dry-run":
        return cmd_dry_run(root, args.registry, args.json)
    if args.cmd == "list":
        return cmd_list(root, args.registry, args.json)
    if args.cmd == "clean":
        return cmd_clean(root, args.registry, args.yes)
    if args.cmd == "verify":
        return cmd_verify(root, args.registry)
    return EXIT_ERR


if __name__ == "__main__":
    sys.exit(main())
