"""回归测试：kb_index --validate 两处口径修复（2026-11-27）。

背景一（误报）：``validate()`` 的注释与 quality-standard §2.2 都写明「业务知识库
（有 ``dimension``）用自己的维度体系，不要求 stage」，但 ``缺 stage`` 检查却写在
该豁免分支之外，对 177 份业务文档无条件误报。修复：把该检查移入「非业务库」分支。

背景二（断链）：全仓实测出 8 处失效相对链接（``ADR-202609-023`` 的 ./docs/... 绝对化
路径 ×2；DMS 系列指向 ``architecture/components/delivery-management-framework/DESIGN.md``
但该文件实际在 ``L3-business/components/...`` ×3；``../../adr/`` 多退一级 ×3），
以及 2 条悬空 ID 引用（``EXP-20260903-003/004`` 不存在，实为 006~009 号段）。

本测试锁定：
- 业务文档（有 dimension）无 stage **不得**再报「缺 stage」；
- 非业务文档（无 dimension）无 stage **仍须**报「缺 stage」（不能矫枉过正）；
- 有效相对链接不误报、失效相对链接必报。
"""

from __future__ import annotations

import importlib.util
import sys
import textwrap
from pathlib import Path

KB_DIR = Path(__file__).resolve().parent.parent
KB_INDEX = KB_DIR / "kb_index.py"


def _load():
    spec = importlib.util.spec_from_file_location("kb_index_validate_fixes", KB_INDEX)
    mod = importlib.util.module_from_spec(spec)
    # dataclass 注解解析需 sys.modules 注册（同 test_kb_adr_audit 的既有坑）。
    sys.modules["kb_index_validate_fixes"] = mod
    spec.loader.exec_module(mod)
    return mod


def _write(root: Path, rel: str, body: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(body), encoding="utf-8")
    return p


BIZ_DOC = """\
    ---
    title: 业务文档
    dimension: methodology
    sub_area: demo
    tags: [a, b]
    ---

    # 业务文档
"""

PLAIN_DOC = """\
    ---
    title: 普通文档
    layers: [L3]
    tags: [a, b]
    ---

    # 普通文档
"""


def _run(tmp_path, mod, capsys):
    """在临时仓库上跑 validate，返回其 stdout 文本。"""
    mod.REPO = tmp_path
    docs = [mod.parse_doc(p, base=tmp_path) for p in sorted(tmp_path.rglob("*.md"))]
    rc = mod.validate(docs)
    out = capsys.readouterr().out
    return rc, out


def test_business_doc_without_stage_is_not_flagged(tmp_path, capsys):
    """有 dimension 的文档缺 stage 必须静默（本次修复的核心断言）。"""
    mod = _load()
    _write(tmp_path, "by-category/biz/knowledge/doc.md", BIZ_DOC)
    rc, out = _run(tmp_path, mod, capsys)
    assert rc == 0, out
    assert "缺 stage" not in out, out


def test_plain_doc_without_stage_still_flagged(tmp_path, capsys):
    """无 dimension 的文档缺 stage 仍须告警——防止把豁免做成一刀切。"""
    mod = _load()
    _write(tmp_path, "by-layer/L3/knowledge/doc.md", PLAIN_DOC)
    rc, out = _run(tmp_path, mod, capsys)
    assert "缺 stage" in out, out


DESIGN_DOC = """\
    ---
    id: DEMO-DESIGN
    title: DESIGN
    layers: [L3]
    stage: design
    category: industry-practice
    tags: [demo]
    ---

    # DESIGN
"""


def test_valid_relative_link_not_flagged(tmp_path, capsys):
    """修好的 DMS 式链接（指向真实存在的 DESIGN.md）不得误报。

    fixture 目录层级与生产同构（``docs/knowledge-base/by-category/...``），
    否则 ``..`` 级数会与真实文件不同，测不出真问题。
    """
    mod = _load()
    _write(tmp_path, "L3-business/components/dms/DESIGN.md", DESIGN_DOC)
    _write(
        tmp_path,
        "docs/knowledge-base/by-category/project-experience/correct/EXP-x.md",
        """\
        ---
        id: EXP-DEMO-001
        title: EXP
        layers: [L3]
        stage: develop
        category: correct
        tags: [a]
        ---

        # EXP

        ## 参考
        - [DESIGN.md](../../../../../L3-business/components/dms/DESIGN.md)
        """,
    )
    rc, out = _run(tmp_path, mod, capsys)
    assert rc == 0, out
    assert "相对链接失效" not in out, out


def test_broken_relative_link_still_flagged(tmp_path, capsys):
    """指向不存在文件的相对链接必须被检出（门禁没被关掉）。"""
    mod = _load()
    _write(
        tmp_path,
        "by-category/project-experience/correct/EXP-y.md",
        """\
        ---
        title: EXP
        layers: [L3]
        stage: develop
        tags: [a]
        ---

        # EXP

        ## 参考
        - [缺失](../adr/ADR-999999-001-nope.md)
        """,
    )
    rc, out = _run(tmp_path, mod, capsys)
    assert "相对链接失效" in out, out
