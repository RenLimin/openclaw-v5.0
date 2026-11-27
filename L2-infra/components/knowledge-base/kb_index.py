#!/usr/bin/env python3
"""知识库索引器 — Markdown + frontmatter → 结构化数据。

ADR-003 阶段 2 工具链。同时是阶段 3 自建系统的解析内核（§4.4 子能力 1~4）。

设计约束（ADR-003 §4.3）：
    Markdown 是永久单一来源；本工具只读，产出可重建的索引/视图。
    绝不反向写内容文件（唯一例外：--emit-index 生成 INDEX.md，且它是纯派生视图）。

用法：
    kb_index.py --validate            # frontmatter schema 校验（含业务知识库）
    kb_index.py --stats               # 分布统计（含业务知识库维度分布）
    kb_index.py --query layer=L2 stage=manage
    kb_index.py --query dimension=project-management
    kb_index.py --tags                # tag 聚合
    kb_index.py --xref                # 交叉引用图（含业务 xref）
    kb_index.py --json                # 全量结构化输出
    kb_index.py --emit-index          # 重新生成 INDEX.md 的派生小节
    kb_index.py --export DIR          # 导出便携 bundle（子能力 6）
    kb_index.py --render FILE         # 渲染单篇人机协作视图（子能力 5）
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Sequence

try:
    import yaml
except ImportError:
    sys.exit("需要 PyYAML: pip3 install pyyaml")

REPO = Path(__file__).resolve().parent.parent.parent.parent
KB_ROOT = REPO / "docs" / "knowledge-base"
BUSINESS_KB_ROOT = KB_ROOT / "by-category" / "business"

# --- 业务知识库合法值 ---
VALID_DIMENSIONS = {
    "project-management", "contract-management", "after-sales", "implementation",
    "family-finance", "finance", "product-design", "system-architecture",
    "frontend-dev", "backend-dev", "testing", "devops-sre", "data-engineering",
    "security-engineering", "software-development", "methodology",
    "cross-border-ecommerce",
    "saas-development",
}
VALID_BUSINESS_CATEGORIES = {"industry-practice", "theoretical-knowledge", "project-experience"}
VALID_XREF_RELATIONS = {"implements", "extends", "referenced_by", "related", "depends_on"}

# --- 三维模型合法值（ADR-002）---
VALID_LAYERS = {"L0", "L1", "L2", "L3", "L4"}
VALID_STAGES = {"design", "develop", "manage"}
VALID_CATEGORIES = {"industry-practice", "theoretical-knowledge", "project-experience"}

# --- schema 别名归一 ---
# 实际文件里 schema 已漂移，归一化而非报错，避免工具比内容更严格反而没人用。
# 漂移事实本身由 --validate 的 drift 段报告。
LAYER_KEYS = ("layers", "layer")
CATEGORY_KEYS = ("category", "kind")
# ADR 主键别名：早期 ADR 用 `adr_id`，后规范为 `id`。
# 不消歧会让这 3 份真实存在的 ADR 在 --validate 里报「缺 id」，
# 进而被引用它们的文档报成「引用了不存在的 ID」（2026-11-27 Q-6 实测）。
ID_KEYS = ("id", "adr_id")

# type 值归一：experience-card 与 experience 混用
TYPE_ALIASES = {
    "experience-card": "experience",
    "experience": "experience",
    "adr": "adr",
    "library-item": "library-item",
    "kb-article": "kb-article",
}

ID_PATTERN = re.compile(r"\b((?:EXP|ADR|LIB)-[0-9]{6,8}-[0-9]{3})\b")
# 「EXP-xxx 之类/等/形如」是占位举例，不是真引用。不排除会把未来日期的示例 ID 报成断链。
PLACEHOLDER_RE = re.compile(
    r"((?:EXP|ADR|LIB)-[0-9]{6,8}-[0-9]{3})\s*(?:\u4e4b\u7c7b|\u7b49\u7c7b|\u7b49|\u5f62\u5982|\u8fd9\u6837|\u7c7b\u4f3c|or similar|e\.g\.)"
)
FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*(?:\n|\Z)", re.DOTALL)
# 去掉 YAML 值后的行内 `# 注释`（模板里大量存在，会污染值）
INLINE_COMMENT_RE = re.compile(r"\s+#\s.*$")


@dataclass
class Doc:
    path: str
    doc_id: str | None = None
    doc_type: str | None = None
    title: str | None = None
    date: str | None = None
    status: str | None = None
    layers: list[str] = field(default_factory=list)
    stage: str | None = None
    category: str | None = None
    tags: list[str] = field(default_factory=list)
    related: list[str] = field(default_factory=list)
    body_refs: list[str] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    is_template: bool = False
    errors: list[str] = field(default_factory=list)
    drift: list[str] = field(default_factory=list)
    # 业务知识库扩展字段
    dimension: str | None = None        # 业务维度
    sub_area: str | None = None         # 子领域
    xref: list[dict] = field(default_factory=list)  # 交叉引用 [{path, relation}]
    last_reviewed: str | None = None    # 最后审查日期
    source: str | None = None           # 权威来源
    version: str | None = None          # 知识体系版本

    @property
    def refs(self) -> list[str]:
        """frontmatter related + 正文提及的 ID，去重保序。"""
        seen, out = set(), []
        for r in list(self.related) + list(self.body_refs):
            if r not in seen:
                seen.add(r)
                out.append(r)
        return out


def _strip_comments(raw: str) -> str:
    out = []
    for line in raw.splitlines():
        if line.lstrip().startswith("#"):
            continue
        out.append(INLINE_COMMENT_RE.sub("", line))
    return "\n".join(out)


def _as_list(val: Any) -> list[str]:
    if val is None:
        return []
    if isinstance(val, str):
        # "L1, L2" 或 "L2"
        return [p.strip() for p in val.replace("[", "").replace("]", "").split(",") if p.strip()]
    if isinstance(val, (list, tuple)):
        return [str(v).strip() for v in val if str(v).strip()]
    return [str(val).strip()]


def _first_key(meta: dict, keys: tuple[str, ...]) -> tuple[str | None, Any]:
    for k in keys:
        if k in meta:
            return k, meta[k]
    return None, None


def parse_doc(path: Path, base: Path | None = None) -> Doc:
    # ``base`` 仅供测试注入临时仓库；生产调用不传，取模块级 REPO。
    base = base or REPO
    rel = str(path.relative_to(base)) if base in path.parents else str(path)
    doc = Doc(path=rel, is_template="/templates/" in rel.replace("\\", "/"))
    text = path.read_text(encoding="utf-8")

    m = FRONTMATTER_RE.match(text)
    if not m:
        doc.errors.append("缺少 frontmatter")
        body = text
    else:
        body = text[m.end():]
        raw_fm = m.group(1)
        # 重复键检测：yaml.safe_load 按“后值覆盖”静默处理，不报错
        _seen_keys: dict[str, int] = {}
        for _line in _strip_comments(raw_fm).splitlines():
            if not _line or _line[0] in " \t-":
                continue  # 跳过嵌套/列表项，只查顶层键
            if ":" not in _line:
                continue
            _k = _line.split(":", 1)[0].strip()
            if _k:
                _seen_keys[_k] = _seen_keys.get(_k, 0) + 1
        for _k, _n in _seen_keys.items():
            if _n > 1:
                doc.drift.append(f"frontmatter 重复键 `{_k}`（出现 {_n} 次，后值静默覆盖前值）")
        try:
            meta = yaml.safe_load(_strip_comments(raw_fm)) or {}
        except yaml.YAMLError as exc:
            doc.errors.append(f"frontmatter YAML 解析失败: {exc}")
            meta = {}
        if not isinstance(meta, dict):
            doc.errors.append("frontmatter 不是映射结构")
            meta = {}

        raw_type = str(meta.get("type", "")).strip()
        doc.doc_type = TYPE_ALIASES.get(raw_type, raw_type or None)
        if raw_type and raw_type != doc.doc_type:
            doc.drift.append(f"type 别名 `{raw_type}` → 归一为 `{doc.doc_type}`")

        _ik, _iv = _first_key(meta, ID_KEYS)
        doc.doc_id = str(_iv).strip() if _iv else None
        if _ik == "adr_id":
            doc.drift.append("使用 `adr_id`，规范键为 `id`")
        doc.title = str(meta["title"]).strip() if meta.get("title") else None
        doc.date = str(meta.get("date") or meta.get("created") or meta.get("added") or "").strip() or None
        doc.status = str(meta["status"]).strip() if meta.get("status") else None

        lk, lv = _first_key(meta, LAYER_KEYS)
        doc.layers = _as_list(lv)
        if lk == "layer":
            doc.drift.append("使用 `layer`，规范键为 `layers`")

        doc.stage = str(meta["stage"]).strip() if meta.get("stage") else None

        ck, cv = _first_key(meta, CATEGORY_KEYS)
        doc.category = str(cv).strip() if cv else None
        if ck == "kind":
            doc.drift.append("使用 `kind`，规范键为 `category`")

        doc.tags = _as_list(meta.get("tags"))
        doc.related = _as_list(meta.get("related"))

        # 业务知识库扩展字段
        doc.dimension = str(meta["dimension"]).strip() if meta.get("dimension") else None
        doc.sub_area = str(meta["sub_area"]).strip() if meta.get("sub_area") else None
        doc.last_reviewed = str(meta["last_reviewed"]).strip() if meta.get("last_reviewed") else None
        doc.source = str(meta["source"]).strip() if meta.get("source") else None
        doc.version = str(meta["version"]).strip() if meta.get("version") else None
        raw_xref = meta.get("xref", [])
        if isinstance(raw_xref, list):
            for item in raw_xref:
                if isinstance(item, dict) and "path" in item:
                    doc.xref.append({
                        "path": str(item["path"]).strip(),
                        "relation": str(item.get("relation", "related")).strip(),
                    })

    placeholders = set(PLACEHOLDER_RE.findall(body))
    doc.body_refs = [
        i for i in ID_PATTERN.findall(body)
        if i != doc.doc_id and i not in placeholders
    ]
    doc.links = re.findall(r"\]\((\.{1,2}/[^)\s]+\.md)[^)]*\)", body)
    return doc


def load_docs(include_templates: bool = False) -> list[Doc]:
    docs = [parse_doc(p) for p in sorted(KB_ROOT.rglob("*.md"))]
    return docs if include_templates else [d for d in docs if not d.is_template]


# ---------- 校验 ----------

def validate(docs: list[Doc]) -> int:
    hard: list[str] = []
    soft: list[str] = []
    drift: list[str] = []

    # README/INDEX 是导航页，不承载知识，不强制三维 frontmatter
    NAV = {"INDEX.md", "README.md"}

    for d in docs:
        name = Path(d.path).name
        is_nav = name in NAV
        if is_nav:
            # 导航页只查链接有效性，不查 frontmatter
            for link in d.links:
                target = (REPO / Path(d.path).parent / link).resolve()
                if not target.exists():
                    soft.append(f"{d.path}: 相对链接失效 `{link}`")
            continue
        for e in d.errors:
            hard.append(f"{d.path}: {e}")
        for w in d.drift:
            drift.append(f"{d.path}: {w}")

        if not d.doc_id:
            soft.append(f"{d.path}: 缺 id")
        if not d.title:
            hard.append(f"{d.path}: 缺 title")
        # 业务知识库不需要 layers/stage（有自己的维度体系）
        if not d.dimension:
            if not d.layers:
                soft.append(f"{d.path}: 缺 layers")
            for lay in d.layers:
                if lay not in VALID_LAYERS:
                    hard.append(f"{d.path}: 非法 layer `{lay}`（合法: {sorted(VALID_LAYERS)}）")
            if d.stage and d.stage not in VALID_STAGES:
                hard.append(f"{d.path}: 非法 stage `{d.stage}`（合法: {sorted(VALID_STAGES)}）")
        # 业务知识库（有 dimension）不受三维 category 约束
        if d.dimension:
            pass  # 业务知识库有自己的 frontmatter 规范
        elif d.category and d.category not in VALID_CATEGORIES | {"correct", "wrong"}:
            hard.append(f"{d.path}: 非法 category `{d.category}`")
        if not d.tags:
            soft.append(f"{d.path}: 无 tags（检索会变差）")
        if not d.stage:
            soft.append(f"{d.path}: 缺 stage（三维查询会漏）")
        if d.doc_type in {"adr", "experience"} and not d.status:
            soft.append(f"{d.path}: 缺 status（生命周期不可追踪，资产清单会显示 —）")

    # ID 唯一性
    dupes = {k: v for k, v in Counter(d.doc_id for d in docs if d.doc_id).items() if v > 1}
    for k, v in dupes.items():
        hard.append(f"ID 重复 `{k}` 出现 {v} 次")

    # 断链（导航页已在上方单独处理）
    known = {d.doc_id for d in docs if d.doc_id}
    for d in docs:
        if Path(d.path).name in NAV:
            continue
        for r in d.refs:
            if r not in known:
                soft.append(f"{d.path}: 引用了不存在的 ID `{r}`")
        for link in d.links:
            target = (REPO / Path(d.path).parent / link).resolve()
            if not target.exists():
                soft.append(f"{d.path}: 相对链接失效 `{link}`")

    def dump(label: str, items: list[str], icon: str) -> None:
        print(f"\n{icon} {label}: {len(items)}")
        for i in items:
            print(f"   {i}")

    print(f"知识库校验 — {len(docs)} 篇（不含模板）")
    dump("阻断性错误", hard, "❌")
    dump("警告", soft, "⚠️ ")
    dump("schema 漂移", drift, "🔀")

    # 业务知识库校验
    biz_hard: list[str] = []
    biz_soft: list[str] = []
    for d in docs:
        if not d.dimension:
            continue
        if d.dimension not in VALID_DIMENSIONS:
            biz_hard.append(f"{d.path}: 非法 dimension `{d.dimension}`")
        if not d.title:
            biz_hard.append(f"{d.path}: 缺 title")
        if not d.source:
            biz_soft.append(f"{d.path}: 缺 source（业务知识必须标注权威来源）")
        if not d.tags:
            biz_soft.append(f"{d.path}: 无 tags")
        if len(d.tags or []) < 3:
            biz_soft.append(f"{d.path}: tags 仅 {len(d.tags or [])} 个（建议 ≥ 3）")
        if not d.last_reviewed:
            biz_soft.append(f"{d.path}: 缺 last_reviewed")
        # 交叉引用校验
        for xr in d.xref:
            target = (REPO / Path(d.path).parent / xr["path"]).resolve()
            if not target.exists():
                biz_soft.append(f"{d.path}: xref 指向不存在的文件 `{xr['path']}`")
            if xr.get("relation") not in VALID_XREF_RELATIONS:
                biz_soft.append(f"{d.path}: xref 非法 relation `{xr.get('relation')}`")

    if biz_hard or biz_soft:
        print()
        print("---")
        print("业务知识库校验")
        dump("阻断性错误", biz_hard, "❌")
        dump("警告", biz_soft, "⚠️ ")

    if not hard and not soft and not drift and not biz_hard and not biz_soft:
        print("\n✅ 全部通过")
    return 1 if (hard or biz_hard) else 0


# ---------- ADR 跨目录普查（Q-6 结构性缺口治理，2026-11-27）----------
#
# 背景：全仓 ADR 分布在三处（知识库 / 架构目录 / 组件本地），编号体系混编
# （``ADR-YYYYMM-NNN`` 与短号 ``ADR-NNN``），历史上已实测出 3 组冲突：
#   - 026：arch 短号（L3/L4 拆分方案）vs kb 完整号（FIN 框架）——同号不同题
#   - 035：arch 短号 vs kb 完整号——同题双稿（kb 为超集）
#   - 023：组件本地副本 vs kb 权威稿——仅差一个 schema 键别名
# 本普查把三处纳入同一判定，避免「只扫一处」导致的漏检。

ADR_SCAN_ROOTS: tuple[tuple[str, Path], ...] = (
    ("kb", KB_ROOT),
    ("arch", REPO / "docs" / "architecture" / "adr"),
    ("component", REPO / "docs" / "architecture" / "components"),
)


def _adr_serial(stem: str) -> tuple[str, int, str] | None:
    """解析 ADR 序列号。

    - ``ADR-202609-026-x`` → (``"full"``, 26, ``"202609"``)
    - ``ADR-026-x``      → (``"short"``, 26, ``""``)
    """
    m = re.match(r"ADR-(?:(\d{6})-)?(\d+)", stem)
    if not m:
        return None
    kind = "full" if m.group(1) else "short"
    return kind, int(m.group(2)), m.group(1) or ""


def _body_scalar(text: str, labels: tuple[str, ...]) -> str:
    """从正文引用行（``> 日期：2026-09-08`` / ``> 决策人：Rex``）取标量。

    架构目录 7 份 ADR 是无 frontmatter 的旧稿，元信息只存在于这类正文行；
    只读 frontmatter 会让这些稿在 R3 同题判定中永久缺席（2026-11-27 实测缺口）。
    读法与 ``gen_asset_inventory._adr_status`` 的兼容口径一致（不另造第二套）。
    """
    pat = (r"^\s*(?:>)?\s*(?:\*{0,2})(?:" + "|".join(
        re.escape(x) for x in labels
    ) + r")(?:\*{0,2})[：:]\s*(.+?)\s*$")
    for raw in text.splitlines()[:40]:
        m = re.match(pat, raw)
        if not m:
            continue
        v = m.group(1).strip()
        vm = re.search(r"\*\*(.+?)\*\*", v)
        if vm:
            return vm.group(1).strip()
        return re.split(r"[（(,，\s]", v, maxsplit=1)[0].strip().strip("*` ")
    return ""


def _adr_record(path: Path, base: Path | None = None) -> dict[str, Any]:
    """抽取单份 ADR 的判定字段（不引入额外口径，复用 gen_asset_inventory 的状态读法）。

    ``base`` 仅供测试注入临时仓库；生产调用不传，取模块级 ``REPO``。
    """
    base = base or REPO
    text = path.read_text(encoding="utf-8")
    meta: dict[str, Any] = {}
    m = FRONTMATTER_RE.match(text)
    if m:
        try:
            meta = yaml.safe_load(_strip_comments(m.group(1))) or {}
        except yaml.YAMLError:
            meta = {}
        if not isinstance(meta, dict):
            meta = {}

    def pick(*keys: str) -> str:
        for k in keys:
            v = meta.get(k)
            if v not in (None, ""):
                return str(v).strip()
        return ""

    # frontmatter 优先；缺失时回退正文旧式引用行（无 frontmatter 的旧稿）
    def pick_any(fm_keys: tuple[str, ...], body_labels: tuple[str, ...]) -> str:
        return pick(*fm_keys) or _body_scalar(text, body_labels)

    rec = {
        "path": path,
        "rel": str(path.relative_to(base)) if base in path.parents else path.name,
        "serial": _adr_serial(path.stem),
        "title": pick("title") or _first_header(text),
        "date": pick_any(("date", "created"), ("日期", "创建日期")),
        "deciders": pick_any(("deciders", "decider"), ("决策人", "作者")),
        "status": pick("status"),
        "copy_of": pick("copy_of"),
        "canonical": pick("canonical"),
        "supersedes": pick("supersedes"),
        "superseded_by": pick("superseded_by"),
        "sha": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }
    return rec


def _first_header(text: str) -> str:
    m = re.search(r"^#\s+(.+)$", text, re.M)
    return m.group(1).strip() if m else ""


def collect_adrs(
    roots: Sequence[tuple[str, Path]] = ADR_SCAN_ROOTS,
    base: Path | None = None,
) -> list[dict[str, Any]]:
    """扫描所有 ADR 目录，返回记录列表。目录缺失则跳过（不静默当成空仓库）。"""
    out: list[dict[str, Any]] = []
    for tag, root in roots:
        if not root.is_dir():
            continue
        # rel 的基准：优先显式 base，否则取各扫描根的公共祖先（保证 tmp 仓也取得到）
        _base = base or _common_base([r for _, r in roots])
        for p in sorted(root.rglob("ADR-*.md")):
            rec = _adr_record(p, base=_base)
            rec["root"] = tag
            out.append(rec)
    return out


def _common_base(paths: Sequence[Path]) -> Path:
    """求多个路径的公共父目录（用于测试注入的非工作树目录）。"""
    resolved = [p.resolve() for p in paths if p.exists()]
    if not resolved:
        return REPO
    common = resolved[0]
    for p in resolved[1:]:
        while common != common.parent and common not in p.parents:
            common = common.parent
    return common


def _norm_title(t: str) -> str:
    """归一标题用于同题判定：去编号前缀、去标点、小写。"""
    t = re.sub(r"^ADR[-_ ].*?[:：]\s*", "", t)
    t = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "", t)
    return t.lower()


def _norm_scalar(v: str) -> str:
    """归一标量字段（日期/决策人）用于分组：列表括号/逗号/空白一律剥掉。

    ``[Rex]`` 与 ``Rex`` 必须视为同一决策人，否则同题双稿会被漏判。
    """
    v = re.sub(r"[\[\](){}',，、\s]", "", v)
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", v)
    return f"{m.group(1)}{m.group(2)}{m.group(3)}" if m else v.lower()


def adr_audit(
    roots: Sequence[tuple[str, Path]] = ADR_SCAN_ROOTS,
) -> tuple[list[str], list[str]]:
    """ADR 跨目录一致性判定。返回 (hard, soft)。

    硬错误（阻塞提交）：
      R1 同一**完整**序列号在多处出现且存在未声明关系的稿（真·重号）。
      R2 **短号**与任何文件的尾号撞车，或两个短号撞车（短号无命名空间，必然歧义）。
      R3 同题同日期同决策人的双稿，且副本未声明 ``copy_of``（无法判断谁是权威）。
    软警告（放行但提示）：
      W1 同一尾号但月份不同（如 202608-018 与 202609-018）——合法但易误引，提示补全引用。
      W2 同完整序列号多处存在但已声明镜像关系——放行，建议收敛为单稿。
      W3 短号与完整序列号同名但已声明关系，或仍在使用已废弃的短号体系。

    判定口径（2026-11-27 Q-6）：
      - 「已声明关系」= frontmatter 含 ``copy_of`` / ``canonical`` /
        ``supersedes`` / ``superseded_by`` 之一。声明后歧义已消解，降为软警告；
        未声明的歧义一律 fail-closed —— 与 ADR-008「静默失败比明确失败更危险」同理。
    """
    recs = collect_adrs(roots)
    hard: list[str] = []
    soft: list[str] = []
    if not recs:
        return ([f"ADR 扫描无结果（根目录全部缺失: {[str(r) for _, r in roots]}）"], [])

    # R1：完整序列号（月份+尾号）唯一 —— 同 (月份, 尾号) 才是真·重号。
    by_full: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    by_short: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for r in recs:
        kind, num, month = r["serial"] or (None, 0, "")
        if kind == "full":
            by_full[(month, num)].append(r)
        elif kind == "short":
            by_short[num].append(r)
    for (month, num), lst in sorted(by_full.items()):
        if len(lst) > 1:
            undeclared = [
                x for x in lst
                if not (x["copy_of"] or x["canonical"] or x["supersedes"] or x["superseded_by"])
            ]
            if undeclared:
                hard.append(
                    f"R1 完整序列号 {month}-{num} 重复 {len(lst)} 处: "
                    + ", ".join(x["rel"] for x in lst)
                )
            else:
                soft.append(
                    f"W2 完整序列号 {month}-{num} 多处存在（已声明镜像关系，建议收敛为单稿）: "
                    + ", ".join(x["rel"] for x in lst)
                )

    def _declared(x: dict[str, Any]) -> bool:
        return bool(x["copy_of"] or x["canonical"] or x["supersedes"] or x["superseded_by"])

    # R2：短号撞任何尾号（短号无命名空间，必然歧义）
    for num, shorts in sorted(by_short.items()):
        collide = [x for x in recs if (x["serial"] or (None, 0, ""))[1] == num
                   and (x["serial"] or (None, 0, ""))[0] == "full"]
        if len(shorts) > 1 or collide:
            parts = [x["rel"] for x in shorts] + [x["rel"] for x in collide]
            if any(_declared(x) for x in shorts + collide):
                soft.append(
                    f"W3 短号 {num} 与完整序列号同名（已声明关系，建议迁移为完整序列号）: "
                    + ", ".join(parts)
                )
            else:
                hard.append(
                    f"R2 短号 {num} 与其他 ADR 尾号撞车（短号无命名空间，必然歧义）: "
                    + ", ".join(parts)
                )

    # W3：仍在使用的短号体系（无论是否已撞车，均提示迁移）
    for num, shorts in sorted(by_short.items()):
        for x in shorts:
            soft.append(
                f"W3 `{x['rel']}` 使用短号 ADR-{num}；规范为 ADR-<YYYYMM>-<NNN>，"
                "建议迁移并在迁移后更新引用"
            )

    # R3：同题同日期同决策人的双稿，需显式声明权威
    groups: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
    for r in recs:
        key = (_norm_title(r["title"]), _norm_scalar(r["date"]), _norm_scalar(r["deciders"]))
        if key[1] and key[2]:
            groups[key].append(r)
    for key, lst in groups.items():
        if len(lst) < 2:
            continue
        declared = [
            x for x in lst
            if x["copy_of"] or x["canonical"] or x["supersedes"] or x["superseded_by"]
        ]
        if declared:
            continue
        hard.append(
            "R3 同题双稿未声明权威（标题/日期/决策人相同）: "
            + ", ".join(x["rel"] for x in lst)
            + " —— 声明关系之一：副本写 `copy_of: <权威稿路径>`；被取代稿写 `superseded_by: <权威稿 id>`"
        )

    # W1：同尾号不同月（合法但易误引，提示补全引用）
    by_tail_month: dict[int, set[str]] = defaultdict(set)
    for r in recs:
        kind, num, month = r["serial"] or (None, 0, "")
        if kind == "full" and month:
            by_tail_month[num].add(month)
    for num, months in sorted(by_tail_month.items()):
        if len(months) > 1:
            soft.append(f"W1 尾号 {num} 跨月份复用: {sorted(months)}（引用请写全序列号）")
    return hard, soft


def render_adr_audit() -> int:
    recs = collect_adrs()
    print(f"ADR 跨目录普查 — {len(recs)} 份")
    counts: Counter = Counter(r["root"] for r in recs)
    print("  " + " · ".join(f"{k}: {v}" for k, v in sorted(counts.items())))
    hard, soft = adr_audit()
    for h in hard:
        print(f"\n❌ {h}")
    for s in soft:
        print(f"\n⚠️  {s}")
    if not hard and not soft:
        print("\n✅ 无跨目录冲突")
    return 1 if hard else 0


# ---------- 统计 ----------

def stats(docs: list[Doc]) -> None:
    print(f"知识库统计 — {len(docs)} 篇（不含模板）\n")

    # 业务知识库统计
    biz_docs = [d for d in docs if d.dimension]
    if biz_docs:
        print(f"## 业务知识库（{len(biz_docs)} 篇）")
        dim_c: Counter = Counter(d.dimension or "(未标注)" for d in biz_docs)
        for k, v in dim_c.most_common():
            bar = "█" * max(1, round(v / max(len(biz_docs), 1) * 24))
            print(f"  {k:<28} {v:>3}  {bar}")
        print()

    def table(title: str, counter: Counter, total: int) -> None:
        print(f"## {title}")
        if not counter:
            print("  (空)\n")
            return
        width = max(len(str(k)) for k in counter)
        for k, v in counter.most_common():
            bar = "█" * max(1, round(v / max(total, 1) * 24))
            print(f"  {str(k):<{width}}  {v:>3}  {bar}")
        print()

    layer_c: Counter = Counter()
    for d in docs:
        for lay in d.layers or ["(未标注)"]:
            layer_c[lay] += 1
    table("按层级 (layer)", layer_c, len(docs))
    table("按阶段 (stage)", Counter(d.stage or "(未标注)" for d in docs), len(docs))
    table("按类别 (category)", Counter(d.category or "(未标注)" for d in docs), len(docs))
    table("按类型 (type)", Counter(d.doc_type or "(未标注)" for d in docs), len(docs))
    table("按状态 (status)", Counter(d.status or "(未标注)" for d in docs), len(docs))

    # 三维交叉覆盖 —— 条件 3 的直接证据
    print("## 三维交叉覆盖 (layer × stage)")
    cells: dict[tuple[str, str], int] = defaultdict(int)
    for d in docs:
        for lay in d.layers:
            if d.stage:
                cells[(lay, d.stage)] += 1
    stages = sorted(VALID_STAGES)
    print(f"  {'':<6}" + "".join(f"{s:>10}" for s in stages))
    for lay in sorted(VALID_LAYERS):
        row = "".join(f"{cells.get((lay, s), 0):>10}" for s in stages)
        print(f"  {lay:<6}{row}")
    filled = sum(1 for v in cells.values() if v)
    print(f"\n  非空格子: {filled}/{len(VALID_LAYERS) * len(stages)}")


def show_tags(docs: list[Doc]) -> None:
    counter: Counter = Counter()
    owners: dict[str, list[str]] = defaultdict(list)
    for d in docs:
        for t in d.tags:
            counter[t] += 1
            owners[t].append(d.doc_id or Path(d.path).name)
    print(f"tag 聚合 — {len(counter)} 个 tag / {len(docs)} 篇\n")
    for t, n in counter.most_common():
        print(f"  {t:<24} {n:>2}  {', '.join(owners[t])}")
    singles = [t for t, n in counter.items() if n == 1]
    print(f"\n  仅出现 1 次: {len(singles)}/{len(counter)} — 占比 {len(singles)/max(len(counter),1):.0%}")


def xref(docs: list[Doc]) -> None:
    known = {d.doc_id: d for d in docs if d.doc_id}
    outgoing = {d.doc_id: d.refs for d in docs if d.doc_id}
    incoming: dict[str, list[str]] = defaultdict(list)
    for src, targets in outgoing.items():
        for t in targets:
            if t in known:
                incoming[t].append(src)

    print(f"交叉引用图 — {len(known)} 个带 ID 的文档\n")
    print("## 引用关系")
    for doc_id in sorted(known):
        out = [t for t in outgoing.get(doc_id, []) if t in known]
        inc = incoming.get(doc_id, [])
        if out or inc:
            print(f"  {doc_id}")
            if out:
                print(f"    → 引用: {', '.join(sorted(set(out)))}")
            if inc:
                print(f"    ← 被引: {', '.join(sorted(set(inc)))}")

    orphans = [i for i in sorted(known) if not incoming.get(i) and not [t for t in outgoing.get(i, []) if t in known]]
    print(f"\n## 孤岛（无任何双向关联）: {len(orphans)}/{len(known)}")
    for o in orphans:
        print(f"  {o}  {known[o].title or ''}")

    dangling = sorted({t for ts in outgoing.values() for t in ts if t not in known})
    print(f"\n## 断链（引用了不存在的 ID）: {len(dangling)}")
    for d_ in dangling:
        print(f"  {d_}")

    # 业务知识库交叉引用
    biz_xref = [d for d in docs if d.xref]
    if biz_xref:
        print(f"\n## 业务知识库交叉引用（{len(biz_xref)} 篇有 xref）")
        for d in biz_xref:
            print(f"  {d.doc_id or Path(d.path).name} [{d.dimension or '—'}]")
            for xr in d.xref:
                print(f"    → {xr['relation']}: {xr['path']}")


# ---------- 查询 ----------

def query(docs: list[Doc], exprs: list[str]) -> None:
    filters: list[tuple[str, str]] = []
    for e in exprs:
        if "=" not in e:
            sys.exit(f"查询表达式需为 key=value，收到 `{e}`")
        k, v = e.split("=", 1)
        filters.append((k.strip(), v.strip()))

    def match(d: Doc, k: str, v: str) -> bool:
        if k == "layer":
            return v in d.layers
        if k == "stage":
            return d.stage == v
        if k == "category":
            return d.category == v
        if k == "tag":
            return v in d.tags
        if k == "type":
            return d.doc_type == v
        if k == "status":
            return d.status == v
        # 业务知识库查询
        if k == "dimension":
            return d.dimension == v
        if k == "sub_area":
            return d.sub_area == v
        if k == "source":
            return d.source == v if d.source else False
        sys.exit(f"不支持的查询键 `{k}`（支持: layer/stage/category/tag/type/status/dimension/sub_area/source）")

    hits = [d for d in docs if all(match(d, k, v) for k, v in filters)]
    print(f"查询 {' '.join(exprs)} — 命中 {len(hits)}/{len(docs)}\n")
    for d in hits:
        print(f"  [{d.doc_id or '—'}] {d.title or Path(d.path).name}")
        if d.dimension:
            print(f"      dimension={d.dimension} sub_area={d.sub_area or '—'} source={d.source or '—'}")
        else:
            print(f"      layers={d.layers or '—'} stage={d.stage or '—'} tags={','.join(d.tags) or '—'}")
        print(f"      {d.path}")


# ---------- INDEX.md 派生 ----------

MARK_START = "<!-- kb_index:auto:start -->"
MARK_END = "<!-- kb_index:auto:end -->"


def emit_index(docs: list[Doc]) -> None:
    """生成 INDEX.md 的派生小节。只替换标记之间的内容，手写部分保留。"""
    index_path = KB_ROOT / "INDEX.md"
    lines: list[str] = [
        MARK_START,
        "",
        "> 以下内容由 `scripts/kb_index.py --emit-index` 自动生成，请勿手工编辑。",
        f"> 来源：{len(docs)} 篇 Markdown（ADR-003 §4.3 — Markdown 是唯一来源）。",
        "",
        "### 全部条目",
        "",
        "| ID | 标题 | layers | stage | status |",
        "|---|---|---|---|---|",
    ]
    for d in sorted(docs, key=lambda x: (x.doc_id or "zzz")):
        if not d.doc_id:
            continue
        rel = Path(d.path).relative_to("docs/knowledge-base")
        title = (d.title or "").replace("|", "\\|")
        lines.append(
            f"| [{d.doc_id}](./{rel}) | {title} | {','.join(d.layers) or '—'} "
            f"| {d.stage or '—'} | {d.status or '—'} |"
        )

    counter: Counter = Counter(t for d in docs for t in d.tags)
    lines += ["", "### 标签云", ""]
    lines.append(" · ".join(f"`{t}`({n})" for t, n in counter.most_common()) or "_(空)_")

    lines += ["", "### 三维分布 (layer × stage)", ""]
    cells: dict[tuple[str, str], int] = defaultdict(int)
    for d in docs:
        for lay in d.layers:
            if d.stage:
                cells[(lay, d.stage)] += 1
    stages = sorted(VALID_STAGES)
    lines.append("| layer | " + " | ".join(stages) + " |")
    lines.append("|---" * (len(stages) + 1) + "|")
    for lay in sorted(VALID_LAYERS):
        lines.append(f"| {lay} | " + " | ".join(str(cells.get((lay, s), 0)) for s in stages) + " |")

    lines += ["", MARK_END]
    block = "\n".join(lines)

    text = index_path.read_text(encoding="utf-8") if index_path.exists() else "# 知识库索引\n"
    if MARK_START in text and MARK_END in text:
        head, rest = text.split(MARK_START, 1)
        _, tail = rest.split(MARK_END, 1)
        new = head + block + tail
    else:
        new = text.rstrip() + "\n\n" + block + "\n"

    if new == text:
        print(f"INDEX.md 无变化 — {index_path}")
        return
    index_path.write_text(new, encoding="utf-8")
    print(f"✅ 已更新派生小节 — {index_path}")


# ---------- 子能力 6：导出（跨系统移植）----------


def export_bundle(docs: list[Doc], out_dir: Path) -> None:
    """导出自包含 bundle：结构化元数据 + 原始 Markdown 副本。

    ADR-003 §4.3：Markdown 是永久单一来源，本导出是**可重建副本**，
    用途是「把知识库迁出 OpenClaw 到另一系统」（触发条件 6）。

    产物：
        manifest.json   —— 全部元数据 + 三维索引 + xref 图（机器读）
        content/…       —— 原始 .md 逐字副本（保持相对路径）
        README.md       —— 人读导入说明
    """
    out_dir = out_dir.resolve()
    content_dir = out_dir / "content"
    content_dir.mkdir(parents=True, exist_ok=True)

    by_id = {d.doc_id: d for d in docs if d.doc_id}
    # xref 双向图
    fwd: dict[str, list[str]] = {}
    rev: dict[str, list[str]] = defaultdict(list)
    for d in docs:
        if not d.doc_id:
            continue
        outs = [r for r in d.refs if r != d.doc_id]
        fwd[d.doc_id] = outs
        for o in outs:
            rev[o].append(d.doc_id)

    copied = 0
    for d in docs:
        src = REPO / d.path
        if not src.exists():
            continue
        rel = Path(d.path).relative_to("docs/knowledge-base")
        dst = content_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        copied += 1

    manifest = {
        "schemaVersion": 1,
        "generator": "scripts/kb_index.py --export",
        "generatedAt": datetime.now(timezone(timedelta(hours=8))).isoformat(),
        "sourceOfTruth": "Markdown (ADR-003 §4.3) — 本 bundle 是可重建副本，非源",
        "dimensions": {
            "layers": sorted(VALID_LAYERS),
            "stages": sorted(VALID_STAGES),
            "categories": sorted(VALID_CATEGORIES),
        },
        "counts": {
            "documents": len(docs),
            "withId": len(by_id),
            "filesCopied": copied,
        },
        "documents": [asdict(d) for d in docs],
        "xref": {"forward": fwd, "reverse": {k: v for k, v in rev.items()}},
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    readme = f"""# 知识库导出 bundle

由 `scripts/kb_index.py --export` 生成，用于**跨系统移植**（ADR-003 触发条件 6）。

| 项 | 值 |
|---|---|
| 文档数 | {len(docs)} |
| 含 ID | {len(by_id)} |
| Markdown 副本 | {copied} 个（`content/`）|
| schema 版本 | 1 |

## 结构

```
manifest.json   全部元数据 + 三维索引 + xref 双向图（机器读）
content/        原始 Markdown 逐字副本，保持相对路径
```

## 导入到目标系统

1. 读 `manifest.json` 的 `documents[]` —— 每项含 `doc_id` / `layers` / `stage`
   / `category` / `tags` / `related`，可直接建表
2. 正文取 `content/<path>`（`documents[].path` 去掉 `docs/knowledge-base/` 前缀）
3. 关系图取 `xref.forward` 与 `xref.reverse`，无需重新解析正文

## 重要约束

**Markdown 是永久单一来源**（ADR-003 §4.3）。本 bundle 是**可重建的派生副本** ——
不要在此处编辑内容后回写，那会造成双写不一致。修改始终回到源 Markdown，重新导出。
"""
    (out_dir / "README.md").write_text(readme, encoding="utf-8")

    print(f"✅ 导出完成 — {out_dir}")
    print(f"   manifest.json  {len(docs)} 篇元数据 + xref 双向图")
    print(f"   content/       {copied} 个 Markdown 副本")
    print(f"   README.md      导入说明")


# ---------- 子能力 5：渲染（人机协作视图）----------


def render_doc(docs: list[Doc], target: str) -> int:
    """渲染单篇的「人机协作视图」：元数据卡 + 正文 + 双向关联。

    不做 Markdown→HTML 全量转换（那需要额外依赖）；输出结构化文本视图，
    重点是把**散落在 frontmatter 与 xref 图里的关系**一次性摊平给人看。
    """
    by_id = {d.doc_id: d for d in docs if d.doc_id}
    hit = by_id.get(target)
    if hit is None:
        cands = [d for d in docs if target in d.path or (d.title and target in d.title)]
        if len(cands) == 1:
            hit = cands[0]
        elif not cands:
            print(f"❌ 未找到: {target}")
            print(f"   可用 ID: {', '.join(sorted(by_id)[:8])} …")
            return 1
        else:
            print(f"⚠️ '{target}' 匹配 {len(cands)} 篇，请更精确：")
            for c in cands[:10]:
                print(f"   {c.doc_id or '—'}  {c.path}")
            return 1

    rev = [d.doc_id for d in docs if d.doc_id and hit.doc_id in d.refs]

    print("=" * 68)
    print(f"  {hit.doc_id or '(无 ID)'}  {hit.title or ''}")
    print("=" * 68)
    print(f"  路径     : {hit.path}")
    print(f"  类型     : {hit.doc_type or '—'}    状态: {hit.status or '—'}")
    print(f"  三维     : layers={','.join(hit.layers) or '—'}  "
          f"stage={hit.stage or '—'}  category={hit.category or '—'}")
    print(f"  日期     : {hit.date or '—'}")
    print(f"  标签     : {' '.join('#' + t for t in hit.tags) or '—'}")
    print("-" * 68)
    print(f"  → 引用   : {', '.join(hit.refs) or '（无）'}")
    print(f"  ← 被引   : {', '.join(rev) or '（无）'}")
    if hit.errors:
        print(f"  ⚠️ schema : {'; '.join(hit.errors)}")
    if hit.drift:
        print(f"  ℹ️ 漂移   : {'; '.join(hit.drift)}")
    print("-" * 68)

    body = (REPO / hit.path).read_text(encoding="utf-8")
    body = FRONTMATTER_RE.sub("", body).strip()
    # 跳过围栏代码块内的 '#'（否则 shell 注释/表格行会被当成标题）
    heads, in_fence = [], False
    for ln in body.splitlines():
        if ln.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if re.match(r"#{1,6}\s+\S", ln):
            heads.append(ln)
    print("  目录:")
    for h in heads[:20]:
        depth = len(h) - len(h.lstrip("#"))
        print("    " + "  " * (depth - 1) + h.lstrip("# ").strip())
    print("-" * 68)
    print(f"  正文 {len(body.splitlines())} 行 / {len(body)} 字符")
    print("=" * 68)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="知识库索引器（ADR-003 阶段 2 工具链）")
    ap.add_argument("--validate", action="store_true", help="frontmatter schema 校验")
    ap.add_argument("--adr-audit", action="store_true", help="ADR 跨目录普查（重号/撞短号/未声明权威副本）")
    ap.add_argument("--stats", action="store_true", help="三维分布统计")
    ap.add_argument("--tags", action="store_true", help="tag 聚合")
    ap.add_argument("--xref", action="store_true", help="交叉引用图")
    ap.add_argument("--query", nargs="+", metavar="K=V", help="交叉查询（支持: layer/stage/category/tag/type/status/dimension/sub_area/source）")
    ap.add_argument("--json", action="store_true", help="全量结构化输出")
    ap.add_argument("--emit-index", action="store_true", help="重新生成 INDEX.md 派生小节")
    ap.add_argument("--export", metavar="DIR", help="导出便携 bundle（跨系统移植）")
    ap.add_argument("--render", metavar="ID_OR_PATH", help="渲染单篇人机协作视图")
    ap.add_argument("--include-templates", action="store_true", help="把 templates/ 也算进来")
    args = ap.parse_args()

    if not KB_ROOT.exists():
        sys.exit(f"知识库目录不存在: {KB_ROOT}")

    docs = load_docs(include_templates=args.include_templates)
    if not docs:
        sys.exit("未找到任何知识库文档")

    if args.json:
        print(json.dumps([asdict(d) for d in docs], ensure_ascii=False, indent=2))
        return 0
    if args.query:
        query(docs, args.query)
        return 0
    if args.tags:
        show_tags(docs)
        return 0
    if args.xref:
        xref(docs)
        return 0
    if args.export:
        export_bundle(docs, Path(args.export))
        return 0
    if args.render:
        return render_doc(docs, args.render)
    if args.emit_index:
        emit_index(docs)
        return 0
    if args.stats:
        stats(docs)
        return 0
    if args.adr_audit:
        return render_adr_audit()
    if args.validate:
        return validate(docs)

    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
