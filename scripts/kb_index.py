#!/usr/bin/env python3
"""知识库索引器 — Markdown + frontmatter → 结构化数据。

ADR-003 阶段 2 工具链。同时是阶段 3 自建系统的解析内核（§4.4 子能力 1~4）。

设计约束（ADR-003 §4.3）：
    Markdown 是永久单一来源；本工具只读，产出可重建的索引/视图。
    绝不反向写内容文件（唯一例外：--emit-index 生成 INDEX.md，且它是纯派生视图）。

用法：
    kb_index.py --validate            # frontmatter schema 校验（CI 友好，异常退出码）
    kb_index.py --stats               # 三维分布统计
    kb_index.py --query layer=L2 stage=manage
    kb_index.py --tags                # tag 聚合
    kb_index.py --xref                # 交叉引用图 + 孤儿/断链检测
    kb_index.py --json                # 全量结构化输出
    kb_index.py --emit-index          # 重新生成 INDEX.md 的派生小节
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    sys.exit("需要 PyYAML: pip3 install pyyaml")

REPO = Path(__file__).resolve().parent.parent
KB_ROOT = REPO / "docs" / "knowledge-base"

# --- 三维模型合法值（ADR-002）---
VALID_LAYERS = {"L1", "L2", "L3", "L4"}
VALID_STAGES = {"design", "develop", "manage"}
VALID_CATEGORIES = {"industry-practice", "theoretical-knowledge", "project-experience"}

# --- schema 别名归一 ---
# 实际文件里 schema 已漂移，归一化而非报错，避免工具比内容更严格反而没人用。
# 漂移事实本身由 --validate 的 drift 段报告。
LAYER_KEYS = ("layers", "layer")
CATEGORY_KEYS = ("category", "kind")

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


def parse_doc(path: Path) -> Doc:
    rel = str(path.relative_to(REPO))
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

        doc.doc_id = str(meta["id"]).strip() if meta.get("id") else None
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
        if not d.layers:
            soft.append(f"{d.path}: 缺 layers")
        for lay in d.layers:
            if lay not in VALID_LAYERS:
                hard.append(f"{d.path}: 非法 layer `{lay}`（合法: {sorted(VALID_LAYERS)}）")
        if d.stage and d.stage not in VALID_STAGES:
            hard.append(f"{d.path}: 非法 stage `{d.stage}`（合法: {sorted(VALID_STAGES)}）")
        if d.category and d.category not in VALID_CATEGORIES | {"correct", "wrong"}:
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

    if not hard and not soft and not drift:
        print("\n✅ 全部通过")
    return 1 if hard else 0


# ---------- 统计 ----------

def stats(docs: list[Doc]) -> None:
    print(f"知识库统计 — {len(docs)} 篇（不含模板）\n")

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
        sys.exit(f"不支持的查询键 `{k}`（支持: layer/stage/category/tag/type/status）")

    hits = [d for d in docs if all(match(d, k, v) for k, v in filters)]
    print(f"查询 {' '.join(exprs)} — 命中 {len(hits)}/{len(docs)}\n")
    for d in hits:
        print(f"  [{d.doc_id or '—'}] {d.title or Path(d.path).name}")
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


def main() -> int:
    ap = argparse.ArgumentParser(description="知识库索引器（ADR-003 阶段 2 工具链）")
    ap.add_argument("--validate", action="store_true", help="frontmatter schema 校验")
    ap.add_argument("--stats", action="store_true", help="三维分布统计")
    ap.add_argument("--tags", action="store_true", help="tag 聚合")
    ap.add_argument("--xref", action="store_true", help="交叉引用图")
    ap.add_argument("--query", nargs="+", metavar="K=V", help="三维交叉查询")
    ap.add_argument("--json", action="store_true", help="全量结构化输出")
    ap.add_argument("--emit-index", action="store_true", help="重新生成 INDEX.md 派生小节")
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
    if args.emit_index:
        emit_index(docs)
        return 0
    if args.stats:
        stats(docs)
        return 0
    if args.validate:
        return validate(docs)

    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
