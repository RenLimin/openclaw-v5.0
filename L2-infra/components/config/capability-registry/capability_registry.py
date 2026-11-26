#!/usr/bin/env python3
"""能力注册表引擎 — 查询已建能力 + 防重复建设门禁。

定位：让**任何会话**动手前先查到「能力是否已建成、权威入口在哪」。
配套数据：`registry.yaml`（唯一权威索引，人工维护）。

用法:
    # 可发现性
    capability_registry.py --query ones
    capability_registry.py --query oa
    capability_registry.py --list
    capability_registry.py --json
    capability_registry.py --explain <capability_id>

    # 门禁（扫描新增/改动脚本，判定是否重复建设）
    capability_registry.py --check                      # 扫工作树改动
    capability_registry.py --check --staged             # 只扫暂存区（pre-commit 用）
    capability_registry.py --check --all                # 扫全部高危目录

设计约束:
  - 只读注册表；门禁只报告不自动改文件
  - 判定依据：文件名家族正则 + supersedes 路径 + 同名脚本
  - 命中即指出**权威入口**，让 agent 有路可走（不是只报错）
  - 白名单 allow 显式登记，避免误伤一次性合法脚本
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path

import yaml

# 本文件在 L2-infra/components/config/capability-registry/ 下 → 需上溯 5 层到仓库根
REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
REGISTRY = Path(__file__).resolve().parent / "registry.yaml"


# -----------------------------------------------------------

@dataclass
class Capability:
    id: str
    name: str
    layer: str
    interfaces: list[str] = field(default_factory=list)
    entry: list[str] = field(default_factory=list)
    notes: str = ""
    supersedes: list[str] = field(default_factory=list)
    ssot: str = ""
    state_file: str = ""
    cdp: str = ""
    profile: str = ""
    auth: str = ""
    # 可执行健康探针（health gate）：entry 声称可用但探针失败 = 阻断提交。
    # 只登记**离线、无副作用、状态感知**的探针（如 `status --probe`）。
    health: list[str] = field(default_factory=list)
    # 新增资产强制要求 health 探针；确无稳定入口时填豁免理由（可审计，不得留空绕过）。
    health_exempt: str = ""


@dataclass
class Registry:
    version: int
    updated: str
    high_risk_dirs: list[str]
    duplicate_family_patterns: list[str]
    capabilities: list[Capability]
    allow: list[dict]
    # 显式豁免登记的范围（如 L1 运行时适配层）：不参与覆盖率/生命周期口径，
    # 但在报告中显性声明，避免后续会话把边界当缺口重复排查。
    scope_exemptions: list[dict] = field(default_factory=list)


def load_registry(path: Path = REGISTRY) -> Registry:
    if not path.is_file():
        sys.exit(f"注册表不存在: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    caps = [Capability(**{k: v for k, v in c.items() if k in Capability.__dataclass_fields__})
            for c in raw.get("capabilities", [])]
    return Registry(
        version=int(raw.get("version", 0)),
        updated=str(raw.get("updated", "")),
        high_risk_dirs=list(raw.get("high_risk_dirs", [])),
        duplicate_family_patterns=list(raw.get("duplicate_family_patterns", [])),
        capabilities=caps,
        allow=list(raw.get("allow", [])),
        scope_exemptions=list(raw.get("scope_exemptions", [])),
    )


# -----------------------------------------------------------

def match_score(cap: Capability, term: str) -> int:
    """粗排打分：命中 id/name/interfaces/notes。"""
    t = term.lower().strip()
    if not t:
        return 0
    score = 0
    if t == cap.id.lower():
        score += 100
    elif cap.id.lower().startswith(t):
        score += 60
    elif t in cap.id.lower():
        score += 50
    if t in cap.name.lower():
        score += 40
    for iface in cap.interfaces:
        if t == iface.lower():
            score += 30
        elif t in iface.lower():
            score += 10
    if t in cap.notes.lower():
        score += 5
    # 下划线/连字符归一（ones_export ↔ ones export）
    norm = re.sub(r"[-_]", " ", t)
    if norm and norm in cap.name.lower():
        score += 20
    return score


def query(reg: Registry, term: str) -> list[tuple[int, Capability]]:
    scored = [(match_score(c, term), c) for c in reg.capabilities]
    return sorted([x for x in scored if x[0] > 0], key=lambda x: -x[0])


def render_cap(cap: Capability, verbose: bool = False) -> str:
    lines = [f"[{cap.layer}] {cap.id} — {cap.name}"]
    for e in cap.entry:
        lines.append(f"    入口: {e}")
    if cap.ssot:
        lines.append(f"    SSOT: {cap.ssot}")
    if cap.state_file:
        lines.append(f"    状态: {cap.state_file}")
    if cap.cdp:
        lines.append(f"    CDP:  {cap.cdp}  profile: {cap.profile}")
    if verbose and cap.notes:
        lines.append(f"    说明: {cap.notes}")
    if verbose and cap.supersedes:
        lines.append(f"    已取代: {', '.join(Path(p).name for p in cap.supersedes)}")
    return "\n".join(lines)


# -----------------------------------------------------------

def _git_changed_files(staged: bool = False) -> list[str]:
    """取改动文件（相对仓库根）。staged=True 取暂存区。"""
    args = ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"] if staged else \
           ["git", "diff", "HEAD", "--name-only", "--diff-filter=ACMR"]
    try:
        out = subprocess.run(args, cwd=REPO_ROOT, capture_output=True, text=True, timeout=60)
    except (subprocess.TimeoutExpired, OSError):
        return []
    if out.returncode != 0:
        return []
    return [ln for ln in out.stdout.splitlines() if ln.strip()]


def _scan_all_files(reg: Registry) -> list[str]:
    """扫高危目录下所有 .py。"""
    files: list[str] = []
    for rel in reg.high_risk_dirs:
        base = REPO_ROOT / rel
        if not base.is_dir():
            continue
        files += [str(p.relative_to(REPO_ROOT)) for p in base.rglob("*.py")]
    return sorted(files)


def _is_allowed(reg: Registry, rel: str) -> str | None:
    for item in reg.allow:
        if str(item.get("path", "")) == rel:
            return str(item.get("reason", ""))
    return None


def detect_duplicates(reg: Registry, files: list[str]) -> list[dict]:
    """判定重复建设嫌疑。返回 [{file, reason, suggestion}]。"""
    patterns = [re.compile(p, re.I) for p in reg.duplicate_family_patterns]
    hits: list[dict] = []
    for rel in files:
        name = Path(rel).name
        reason = ""
        suggestion = ""
        for pat in patterns:
            if pat.search(name):
                reason = f"命中重复家族正则 `{pat.pattern}`"
                break
        if not reason:
            continue
        # 找最贴切的能力 → 给出权威入口
        stem = re.sub(r"^\d{6}[-_]?", "", name)
        term = re.sub(r"\.py$", "", stem)
        term = re.sub(r"^(re_?export|export|refetch|auto_refetch|diag|login|selftest)_?", "", term)
        # 剥日期/版本尾缀（_202609 / _2026_09 / _v2 / _20260920）
        term = re.sub(r"[_-]?(\d{4}[_-]?\d{2}|\d{6,8}|v\d+)$", "", term)
        term = re.sub(r"[_-]+(all|fixed|with_reset|missing|poc_abnormal|single|abnormal_osascript)$", "", term)
        term = term.strip("_- ")
        best = query(reg, term)
        if not best:
            # 回退 1：用原始 stem 再试（保留信息）
            best = query(reg, re.sub(r"\.py$", "", stem))
        if not best:
            # 回退 2：从原始文件名抽关键词（ones / iam / oa / sso / browser）
            keywords = [k for k in ("iam", "ones", "oa", "sso", "browser", "todo", "ledger")
                         if k in name.lower()]
            for kw in keywords:
                cand = query(reg, kw)
                if cand:
                    best = cand
                    break
        if best:
            cap = best[0][1]
            suggestion = f"{cap.id}: {cap.entry[0] if cap.entry else '(见注册表)'}"
        allowed = _is_allowed(reg, rel)
        hits.append({
            "file": rel,
            "reason": reason,
            "suggestion": suggestion,
            "allowed": allowed,
        })
    return hits


# -----------------------------------------------------------

def cmd_query(args, reg: Registry) -> int:
    results = query(reg, args.query)
    if not results:
        print(f"未命中能力: {args.query}")
        print("提示: 先跑 `--list` 看全量；确认能力缺失后才允许新建。")
        return 1
    print(f"命中 {len(results)} 个能力 — {args.query}")
    print()
    for score, cap in results:
        print(render_cap(cap, verbose=args.verbose))
        print()
    return 0


def cmd_list(args, reg: Registry) -> int:
    print(f"能力注册表 v{reg.version}（{reg.updated}）— 共 {len(reg.capabilities)} 项")
    print()
    by_layer: dict[str, list[Capability]] = {}
    for c in reg.capabilities:
        by_layer.setdefault(c.layer, []).append(c)
    for layer in sorted(by_layer):
        print(f"### {layer}")
        for c in by_layer[layer]:
            print(f"- `{c.id}` — {c.name}")
            if args.verbose and c.entry:
                print(f"    {c.entry[0]}")
        print()
    return 0


def cmd_explain(args, reg: Registry) -> int:
    for c in reg.capabilities:
        if c.id == args.id:
            print(render_cap(c, verbose=True))
            return 0
    print(f"未知能力 id: {args.id}")
    return 1


# ── 覆盖率校验：所有组件/skill 是否都已登记 ──

def _discover_assets(root: Path | None = None) -> dict[str, list[str]]:
    """扫描资产目录名，**口径唯一来源是 enumerate_assets()**。

    历史问题：本函数曾自造 iterdir() 匹配规则（只看 . 开头），与
    enumerate_assets() 的 ASSET_EXCLUDED_NAMES（含 .deprecated）不一致——
    这正是「两套口径长期说谎」的病根（事故 2026-11-25/26）。现仅做形状转换。
    返回 {"components": [...], "skills": [...]}（目录名，已排序去重）。
    """
    rows = enumerate_assets(root=root)
    return {
        kind: sorted({d.name for _, k, d in rows if k == kind})
        for kind in ("components", "skills")
    }


def _registered_names(reg: Registry) -> set[str]:
    """注册表已覆盖的资产名（能力 id 去掉 skill- 前缀后的目录名）。"""
    names = set()
    for c in reg.capabilities:
        if c.id.startswith("skill-"):
            names.add(c.id[len("skill-"):])
        else:
            names.add(c.id)
    return names


def _cap_by_asset_name(reg: Registry) -> dict[str, Capability]:
    """资产目录名 → 能力条目（与 _registered_names 同口径：去掉 skill- 前缀）。"""
    out: dict[str, Capability] = {}
    for c in reg.capabilities:
        name = c.id[len("skill-"):] if c.id.startswith("skill-") else c.id
        out.setdefault(name, c)
    return out


def cmd_coverage(args, reg: Registry) -> int:
    assets = _discover_assets()
    registered = _registered_names(reg)

    unreg_comp = [c for c in assets["components"] if c not in registered]
    unreg_skill = [s for s in assets["skills"] if s not in registered]

    total = len(assets["components"]) + len(assets["skills"])
    covered = total - len(unreg_comp) - len(unreg_skill)
    pct = (covered / total * 100) if total else 0

    print(f"能力覆盖率: {covered}/{total} ({pct:.1f}%)")
    print(f"  组件 {len(assets['components'])} 个 / skill {len(assets['skills'])} 个")
    print(f"  注册表能力条目: {len(reg.capabilities)}")
    # 显性声明范围边界：L1 运行时适配层不参与能力登记（ADR-202608-001）。
    # 不列出来，后续会话会把这 4 个目录当「未登记缺口」重复排查。
    if reg.scope_exemptions:
        print(f"  范围豁免（不参与登记口径）: {len(reg.scope_exemptions)}")
        for x in reg.scope_exemptions:
            reason = (x.get("reason") or "").strip()
            print(f"     ↳ {x.get('path')}：{reason}" if reason else f"     ↳ {x.get('path')}")

    if unreg_comp or unreg_skill:
        print()
        print("❌ 未登记资产（动手前会被误判为「能力缺失」→ 重复建设）:")
        for c in unreg_comp:
            print(f"  [组件] {c}")
        for s in unreg_skill:
            print(f"  [skill] {s}")
        print()
        print("处理: 在 registry.yaml 补条目（entry 必须可直接调用），")
        print("      或确认为废弃资产后从目录移除。")
        return 1

    print("\n✅ 全部组件与 skill 均已登记，无覆盖缺口。")
    return 0


# ── 注册表自校验：entry 可执行性 + 文档闭环（业界 fitness function）──

_ENTRY_PATH_RE = re.compile(r"(L[234]-[a-z-]+/[A-Za-z0-9_./-]+)")

# health 探针单条超时（秒）。探针必须离线、无副作用；超时即视为失败（fail-closed）。
HEALTH_TIMEOUT = float(os.environ.get("REGISTRY_HEALTH_TIMEOUT", "60"))


def _run_health_probe(cmd: str, timeout: float) -> tuple[bool, str]:
    """执行一条 health 探针命令。返回 (ok, 摘要)。

    约束：只在仓库根执行；超时/无法执行均判失败（不静默放行）。
    """
    try:
        proc = subprocess.run(
            cmd, shell=True, cwd=REPO_ROOT,
            capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return False, f"探针超时（>{timeout:.0f}s）"
    except OSError as exc:
        return False, f"无法执行: {exc}"
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    tail = (out or err).splitlines()[-1] if (out or err) else ""
    return proc.returncode == 0, tail[:200]


def _entry_paths(entry: str) -> list[str]:
    """从一条 entry 描述里抽出仓库相对路径（去掉占位符/参数）。"""
    out = []
    for m in _ENTRY_PATH_RE.finditer(entry):
        p = m.group(1).rstrip(".")
        if ".." in p:
            continue
        out.append(p)
    return out


def cmd_validate(args, reg: Registry) -> int:
    """校验注册表自身质量（防止「声称可调用但路径不存在」的孤儿 entry）。

    对应业界实践：
      - Backstage catalog validation（实体字段必填 + 引用完整性）
      - Archgate fitness function（决策文档 + 可执行规则双表达）
    """
    problems: list[str] = []
    checked = 0

    for c in reg.capabilities:
        if not c.entry:
            problems.append(f"{c.id}: 缺 entry")
            continue
        for e in c.entry:
            if "见文档" in e or re.search(r"见 [A-Za-z]", e):
                problems.append(f"{c.id}: entry 不可执行 → {e}")
                continue
            paths = _entry_paths(e)
            for p in paths:
                checked += 1
                if not (REPO_ROOT / p).exists():
                    problems.append(f"{c.id}: 路径不存在 → {p}\n      (原 entry: {e})")

    print(f"注册表自校验: 检查 {checked} 条 entry 路径")
    if problems:
        print()
        print(f"❌ 发现 {len(problems)} 个问题（孤儿 entry 会让后续会话调用失败）:")
        for p in problems:
            print(f"  • {p}")
        print()
        print("处理: 修正 registry.yaml 中对应 entry 为真实路径；")
        print("      路径确已废弃 → 更新 entry 或移除该能力条目。")
        return 1

    # ── health 探针：entry 路径存在 ≠ 能力可用（可调用性硬指标）──
    # 只执行显式登记在 `health:` 的离线探针；超时/无法执行均 fail-closed。
    if getattr(args, "skip_health", False):
        print("⏭️  已跳过 health 探针（--skip-health）")
        return 0

    probed = 0
    failed: list[str] = []
    for c in reg.capabilities:
        for h in getattr(c, "health", []) or []:
            probed += 1
            ok, tail = _run_health_probe(h, HEALTH_TIMEOUT)
            if ok:
                print(f"  ✅ {c.id}: {tail}")
            else:
                failed.append(f"{c.id}: 探针失败 → {h}\n      ({tail})")
                print(f"  ❌ {c.id}: {tail}")

    if failed:
        print()
        print(f"❌ {len(failed)}/{probed} 条 health 探针失败（能力不可调用）:")
        for f in failed:
            print(f"  • {f}")
        print()
        print("处理: 修复能力使其可用，或修正 health 探针命令；")
        print("      确属环境依赖（需网络/登录态）→ 从 health 移除，改用 entry + notes 说明。")
        return 1

    print(f"✅ 全部 entry 路径真实存在（{checked} 条），health 探针通过（{probed} 条）。")
    return 0


# ── 资产生命周期闭环：设计 → 验收 文档门禁（业界 DoD / ADR Guard / OWASP shift-left）──

def _asset_docs(asset_dir: Path) -> dict:
    """检查单个资产目录的设计/验收文档（递归 docs/ 子目录，排除缓存）。

    仓库惯例：部分资产把文档放在根级，部分放在 docs/ 子目录；
    只扫根级会把 docs/ 下的 DESIGN/PRD/VERIFICATION 误判为缺失。
    """
    design: list[str] = []
    verify: list[str] = []
    if not asset_dir.is_dir():
        return {"design": design, "verify": verify}
    for dirpath, dirnames, filenames in os.walk(asset_dir):
        depth = len(Path(dirpath).relative_to(asset_dir).parts)
        if depth > 2:
            dirnames[:] = []
            continue
        dirnames[:] = [x for x in dirnames if x not in (".git", "node_modules", "__pycache__", ".pytest_cache", ".deprecated")]
        for fn in filenames:
            n = fn.upper()
            rel = f"{Path(dirpath).relative_to(asset_dir)}/{fn}"
            if re.match(r"^(DESIGN|PRD|SKILL)", n):
                design.append(rel)
            elif n.startswith("VERIFICATION"):
                verify.append(rel)
    return {"design": design, "verify": verify}


def _iter_asset_dirs(root: Path | None = None) -> list[tuple[str, str, Path]]:
    base_root = root or REPO_ROOT
    out = []
    for layer in ("L2-infra", "L3-business", "L4-proprietary"):
        for kind in ("components", "skills"):
            base = base_root / layer / kind
            if not base.is_dir():
                continue
            for d in sorted(base.iterdir()):
                if is_real_asset_dir(d):
                    out.append((layer, kind, d))
    return out


# ── 对外公共枚举 API（单一事实源）──
#
# 任何「盘点有哪些资产」的场景（健康检查、全量审计、覆盖率、生命周期）都必须走这里，
# 禁止各脚本自造 iterdir/glob 匹配规则（事故 2026-11-25：health_check 与本表两套
# 口径导致长期误报；2026-11-26：system_full_audit §3 裸 iterdir 又把 .deprecated 算进组件）。
ASSET_EXCLUDED_NAMES = (".git", "node_modules", "__pycache__", ".pytest_cache",
                       ".mypy_cache", ".deprecated", "dist")


def is_real_asset_dir(p: Path) -> bool:
    """是否为「真实资产目录」。

    判定必须过 ASSET_EXCLUDED_NAMES——此前只查 `.`/`__` 前缀，导致
    node_modules/dist 等被算成资产（常量定义了却无人引用 = 两套口径）。
    """
    return (p.is_dir()
            and not p.name.startswith((".", "__"))
            and p.name not in ASSET_EXCLUDED_NAMES)


def enumerate_assets(kind: str | None = None, root: Path | None = None) -> list[tuple[str, str, Path]]:
    """返回 [(layer, kind, Path)]；kind ∈ {'components', 'skills'} 或 None=全部。

    root：扫描根（默认仓库根）；调用方（如隔离测试/审计脚本）可显式指定。
    """
    return [x for x in _iter_asset_dirs(root) if kind is None or x[1] == kind]


def _new_asset_dirs() -> set[str]:
    """从暂存区推断**真正新增**的资产目录（layer/kind/name）。

    判定：路径前缀在 HEAD 中不存在。已存在于 HEAD 的资产（哪怕本次改了很多文件）
    不算新资产，避免误伤并行会话对存量资产的正常改动。
    """
    dirs = set()
    for f in _git_changed_files(staged=True):
        m = re.match(r"^(L[234]-[a-z-]+)/(components|skills)/([^/]+)/", f)
        if not m:
            continue
        key = f"{m.group(1)}/{m.group(2)}/{m.group(3)}"
        probe = subprocess.run(
            ["git", "cat-file", "-e", f"HEAD:{key}"],
            cwd=REPO_ROOT, capture_output=True,
        )
        if probe.returncode == 0:
            continue  # 已存在于 HEAD → 存量资产，不是新增
        dirs.add(key)
    return dirs


def cmd_lifecycle(args, reg: Registry) -> int:
    """资产生命周期闭环报告：调研/设计文档 + 验收文档。

    对应业界实践：
      - Definition of Done（DoD）：每个交付物统一质量门槛，文档闭环是其中一项
      - ADR Guard：被监视路径变更时若无决策记录则 fail（此处=新增资产无设计文档）
      - OWASP shift-left：最早的门禁在提交时，而非数天后的评审
    """
    new_only = bool(getattr(args, "new_only", False))
    new_keys = _new_asset_dirs()
    new_dirs = new_keys if new_only else set()

    rows = []
    for layer, kind, d in _iter_asset_dirs():
        key = f"{layer}/{kind}/{d.name}"
        if new_only and key not in new_dirs:
            continue
        info = _asset_docs(d)
        rows.append({"key": key, "name": d.name, "kind": kind, **info})

    if not rows:
        print("✅ 本次无新增资产目录（无需文档闭环检查）")
        return 0

    no_design = [r for r in rows if not r["design"]]
    no_verify = [r for r in rows if r["design"] and not r["verify"]]

    print(f"资产生命周期检查（{len(rows)} 个资产，模式={'新增' if new_only else '全量'}）")
    print(f"  设计/调研文档: {len(rows) - len(no_design)}/{len(rows)}")
    print(f"  验收文档: {len(rows) - len(no_verify)}/{len(rows)}")
    # 显性声明豁免范围，避免把 L1 适配层误判为「缺文档」。
    if reg.scope_exemptions:
        print(f"  范围豁免（不计入上述分母）: {len(reg.scope_exemptions)}")

    if no_design:
        print()
        print("❌ 缺设计/调研文档（违反「禁止跳过设计文档直接写代码」红线）:")
        for r in no_design:
            print(f"  • {r['key']}")
    if no_verify:
        print()
        print("⚠️  缺验收文档（VERIFICATION*.md；建议补，不阻断）:")
        for r in no_verify:
            print(f"  • {r['key']}")

    if no_design and getattr(args, "require_design", False):
        print()
        print("处理: 先补 DESIGN.md/PRD.md/SKILL.md（含调研来源与业界最佳实践引用），")
        print("      再提交；或确属废弃资产 → 从目录移除。")
        return 1

    if no_design:
        print()
        print("⚠️  存在缺设计文档的资产（提醒，不阻断本次提交）")

    # ── 可调用性探针：新增资产默认必须有 health 探针（或显式豁免理由）──
    # 「已登记 ≠ 被触发即可用」：新增资产若只写 entry 不写探针，等于把
    # 「重复探索入口」留给后续会话。门禁强制登记；豁免必须写理由（可审计）。
    if getattr(args, "require_health", False) and not getattr(args, "skip_health_requirement", False):
        by_name = _cap_by_asset_name(reg)
        have, exempt, missing = 0, [], []
        for key in sorted(new_keys):
            cap = by_name.get(key.split("/", 2)[2])
            if cap is None:
                continue  # 未登记由 --coverage 负责
            reason = (getattr(cap, "health_exempt", "") or "").strip()
            if cap.health:
                have += 1
            elif reason:
                exempt.append(f"{key}（{reason}）")
            else:
                missing.append(key)
        total = have + len(exempt) + len(missing)
        if total:
            print(f"  可调用性探针: {have}/{total}" + (f"（豁免 {len(exempt)}）" if exempt else ""))
            for e in exempt:
                print(f"     ↳ 豁免 {e}")
        if missing:
            print()
            print("❌ 新增资产缺可调用性探针（health）—— entry 存在 ≠ 能力可用:")
            for m in missing:
                print(f"  • {m}")
            print()
            print("处理: 在 registry.yaml 该条目补 health: [<离线/只读/无副作用探针命令>]，")
            print("      或补 health_exempt: \"理由\"（纯文档/无稳定入口等），")
            print("      应急跳过: --lifecycle --require-health --skip-health-requirement。")
            return 1
    return 0


def cmd_check(args, reg: Registry) -> int:
    if args.staged:
        files = _git_changed_files(staged=True)
        mode = "staged"
    elif args.all:
        files = _scan_all_files(reg)
        mode = "all"
    else:
        files = _git_changed_files(staged=False)
        mode = "working-tree"

    files = [f for f in files if f.endswith(".py")]
    hits = detect_duplicates(reg, files)
    blocked = [h for h in hits if not h["allowed"]]
    allowed_hits = [h for h in hits if h["allowed"]]

    if not hits:
        print(f"✅ 防重复建设检查通过（扫描 {len(files)} 个 .py，模式={mode}）")
        return 0

    print(f"⚠️  防重复建设检查（模式={mode}，扫描 {len(files)} 个 .py）")
    for h in blocked:
        print(f"  ❌ {h['file']}")
        print(f"     原因: {h['reason']}")
        if h["suggestion"]:
            print(f"     改用: {h['suggestion']}")
    for h in allowed_hits:
        print(f"  ℹ️  {h['file']}（白名单: {h['allowed']}）")
    print()
    if blocked:
        print("处理方式: 复用上方权威入口；确需新建 → 先补 registry.yaml 条目，")
        print("          或把该脚本登记到 allow 并写明理由。不要直接提交重复脚本。")
        return 1
    print("✅ 命中项均为白名单，放行。")
    return 0


# -----------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="能力注册表：查询已建能力 + 防重复建设门禁")
    ap.add_argument("--query", help="按关键词查能力（如 ones / oa / browser）")
    ap.add_argument("--list", action="store_true", help="列出全部能力")
    ap.add_argument("--explain", dest="id", help="查看单个能力详情")
    ap.add_argument("--check", action="store_true", help="防重复建设检查")
    ap.add_argument("--coverage", action="store_true", help="覆盖率校验：所有组件/skill 是否已登记")
    ap.add_argument("--validate", action="store_true", help="注册表自校验：entry 路径存在性 + health 探针可调用性")
    ap.add_argument("--lifecycle", action="store_true", help="资产生命周期：设计/验收文档闭环")
    ap.add_argument("--new-only", action="store_true", help="配合 --lifecycle：只查本次新增资产")
    ap.add_argument("--require-design", action="store_true", help="配合 --lifecycle：缺设计文档即阻断")
    ap.add_argument("--require-health", action="store_true", help="配合 --lifecycle：新增资产必须有 health 探针或显式豁免理由")
    ap.add_argument("--skip-health-requirement", action="store_true", help="配合 --lifecycle：跳过新增资产探针强制要求（应急）")
    ap.add_argument("--skip-health", action="store_true", help="配合 --validate：跳过 health 探针（仅验路径）")
    ap.add_argument("--staged", action="store_true", help="只扫暂存区（配 pre-commit）")
    ap.add_argument("--all", action="store_true", help="扫全部高危目录")
    ap.add_argument("--verbose", "-v", action="store_true", help="显示说明/入口细节")
    ap.add_argument("--json", action="store_true", help="结构化输出（--query/--list 时生效）")
    args = ap.parse_args(argv)

    reg = load_registry()

    if args.query:
        results = query(reg, args.query)
        if args.json:
            print(json.dumps([asdict(c) for _, c in results], ensure_ascii=False, indent=2))
            return 0 if results else 1
        return cmd_query(args, reg)
    if args.list:
        if args.json:
            print(json.dumps([asdict(c) for c in reg.capabilities], ensure_ascii=False, indent=2))
            return 0
        return cmd_list(args, reg)
    if args.id:
        return cmd_explain(args, reg)
    if args.check:
        return cmd_check(args, reg)
    if args.coverage:
        return cmd_coverage(args, reg)
    if args.validate:
        return cmd_validate(args, reg)
    if args.lifecycle:
        return cmd_lifecycle(args, reg)

    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
