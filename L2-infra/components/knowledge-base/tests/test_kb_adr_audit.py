"""回归测试：ADR 跨目录普查门禁（Q-6 结构性缺口治理，2026-11-27）。

背景：全仓 ADR 分布在三处（``docs/knowledge-base/**``、``docs/architecture/adr/``、
组件本地），编号体系混编（``ADR-YYYYMM-NNN`` 与短号 ``ADR-NNN``）。实测出三类歧义：

- **短号撞车**：短号无命名空间，必然与其他尾号歧义（026 / 035 实例）。
- **同号不同题**：同尾号但主题不同（arch 026 拆分方案 vs KB 026 FIN 框架）。
- **同题双稿未声明权威**：023 组件本地副本与 KB 权威稿并存，无法判断谁为准。

本测试锁定判定口径不回退：未声明关系的歧义一律 fail-closed，
已声明 ``copy_of`` / ``canonical`` / ``supersedes`` / ``superseded_by`` 的降为软警告。
"""

from __future__ import annotations

import importlib.util
import sys
import textwrap
from pathlib import Path

KB_DIR = Path(__file__).resolve().parent.parent
KB_INDEX = KB_DIR / "kb_index.py"


def _load():
    spec = importlib.util.spec_from_file_location("kb_index_adr_audit", KB_INDEX)
    mod = importlib.util.module_from_spec(spec)
    # 必须先注册进 sys.modules：模块内的 dataclass 在解析类型注解时
    # 会回查 sys.modules[cls.__module__]，缺失则 AttributeError（2026-11-27 实测）。
    sys.modules["kb_index_adr_audit"] = mod
    spec.loader.exec_module(mod)
    return mod


def _write(root: Path, rel: str, body: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(body), encoding="utf-8")
    return p


KB_FM = """\
    ---
    id: {serial}
    title: {title}
    status: accepted
    date: {date}
    deciders: [Rex]
    layers: L2
    tags: [adr]
    {extra}
    ---

    # {serial}: {title}

    正文。
    """

ARCH_OLD = """\
    # {serial}: {title}

    > 状态：accepted
    > 日期：{date}
    > 决策人：Rex

    ## 背景
    """


def _tmp_repo(tmp_path: Path) -> tuple[Path, ...]:
    return (
        tmp_path / "docs" / "knowledge-base",
        tmp_path / "docs" / "architecture" / "adr",
        tmp_path / "docs" / "architecture" / "components",
    )


# --- R1：完整序列号（月份+尾号）唯一性 -------------------------------------

def test_r1_same_full_serial_is_hard(tmp_path):
    mod = _load()
    kb, arch, comp = _tmp_repo(tmp_path)
    _write(kb, "by-category/project-experience/adr/ADR-202609-023-x.md",
           KB_FM.format(serial="ADR-202609-023", title="OCR 数字化", date="2026-09-02",
                       extra="", ))
    _write(comp, "ocr/ADR-202609-023-x.md",
           KB_FM.format(serial="ADR-202609-023", title="OCR 数字化", date="2026-09-02",
                       extra="", ))
    hard, soft = mod.adr_audit(roots=[("kb", kb), ("component", comp)])
    assert any(h.startswith("R1") for h in hard), hard


def test_r1_declared_mirror_downgrades_to_soft(tmp_path):
    """已声明 copy_of 的镜像副本放行（W2），不阻塞。"""
    mod = _load()
    kb, _arch, comp = _tmp_repo(tmp_path)
    _write(kb, "by-category/project-experience/adr/ADR-202609-023-x.md",
           KB_FM.format(serial="ADR-202609-023", title="OCR 数字化", date="2026-09-02",
                       extra="canonical: true\n"))
    _write(comp, "ocr/ADR-202609-023-x.md",
           KB_FM.format(serial="ADR-202609-023", title="OCR 数字化", date="2026-09-02",
                       extra="copy_of: ../../../knowledge-base/by-category/project-experience/adr/ADR-202609-023-x.md\n"))
    hard, soft = mod.adr_audit(roots=[("kb", kb), ("component", comp)])
    assert not hard, hard
    assert any(s.startswith("W2") for s in soft), soft


# --- R2 / W3：短号体系 ----------------------------------------------------

def test_r2_short_number_collides_is_hard(tmp_path):
    """短号与任何完整序列号撞尾号即硬错误（短号无命名空间）。"""
    mod = _load()
    kb, arch, _comp = _tmp_repo(tmp_path)
    _write(arch, "ADR-026-fin-l4-split.md",
           ARCH_OLD.format(serial="ADR-026", title="个人理财引擎 L3/L4 分层拆分方案",
                           date="2026-09-08"))
    _write(kb, "by-category/project-experience/adr/ADR-202609-026-fin.md",
           KB_FM.format(serial="ADR-202609-026", title="家庭及个人理财通用框架",
                       date="2026-09-03", extra=""))
    hard, _soft = mod.adr_audit(roots=[("kb", kb), ("arch", arch)])
    assert any(h.startswith("R2") for h in hard), hard


def test_w3_short_number_declared_is_soft(tmp_path):
    """已声明关系的短号撞车降为 W3 提示。"""
    mod = _load()
    kb, arch, _comp = _tmp_repo(tmp_path)
    _write(arch, "ADR-035-prompt-rule-system.md",
           KB_FM.format(serial="ADR-202610-035", title="Agent Prompt 规则体系",
                       date="2026-10-30",
                       extra="copy_of: ../../knowledge-base/by-category/project-experience/adr/ADR-202610-035-x.md\n")
           .replace("# ADR-202610-035: Agent Prompt 规则体系", "# ADR-035: Agent Prompt 规则体系"))
    _write(kb, "by-category/project-experience/adr/ADR-202610-035-x.md",
           KB_FM.format(serial="ADR-202610-035", title="Agent Prompt 规则体系",
                       date="2026-10-30", extra=""))
    hard, soft = mod.adr_audit(roots=[("kb", kb), ("arch", arch)])
    assert not hard, hard
    assert any(s.startswith("W3") for s in soft), soft


def test_w3_legacy_short_number_flagged(tmp_path):
    """仍在使用的短号一律提示迁移。"""
    mod = _load()
    _kb, arch, _comp = _tmp_repo(tmp_path)
    _write(arch, "ADR-032-context-overflow.md",
           ARCH_OLD.format(serial="ADR-032", title="上下文溢出自动恢复",
                           date="2026-11-01"))
    hard, soft = mod.adr_audit(roots=[("arch", arch)])
    assert not hard
    assert any("使用短号" in s for s in soft), soft


# --- R3：同题双稿须声明权威 ----------------------------------------------

def test_r3_same_topic_twin_without_declaration_is_hard(tmp_path):
    mod = _load()
    kb, _arch, comp = _tmp_repo(tmp_path)
    body = KB_FM.format(serial="ADR-202609-023", title="L2 OCR 文档数字化组件建设",
                        date="2026-09-02", extra="")
    _write(kb, "by-category/project-experience/adr/ADR-202609-023-x.md", body)
    _write(comp, "ocr/ADR-202609-023-x.md", body)
    hard, _soft = mod.adr_audit(roots=[("kb", kb), ("component", comp)])
    assert any(h.startswith("R3") for h in hard), hard


def test_r3_superseded_by_declaration_passes(tmp_path):
    mod = _load()
    kb, _arch, comp = _tmp_repo(tmp_path)
    _write(kb, "by-category/project-experience/adr/ADR-202609-023-x.md",
           KB_FM.format(serial="ADR-202609-023", title="L2 OCR 文档数字化组件建设",
                       date="2026-09-02", extra="canonical: true\n"))
    _write(comp, "ocr/ADR-202609-023-x.md",
           KB_FM.format(serial="ADR-202609-023", title="L2 OCR 文档数字化组件建设",
                       date="2026-09-02",
                       extra="superseded_by: ADR-202609-023\n"))
    hard, _soft = mod.adr_audit(roots=[("kb", kb), ("component", comp)])
    assert not hard, hard


# --- 分组归一化 ----------------------------------------------------------

def test_decider_list_and_scalar_are_same_group(tmp_path):
    """``deciders: [Rex]`` 与旧式 ``决策人：Rex`` 必须视为同一决策人。"""
    mod = _load()
    kb, _arch, comp = _tmp_repo(tmp_path)
    _write(kb, "by-category/project-experience/adr/ADR-202609-023-x.md",
           KB_FM.format(serial="ADR-202609-023", title="L2 OCR 文档数字化组件建设",
                       date="2026-09-02", extra=""))
    _write(comp, "ocr/ADR-202609-023-x.md",
           ARCH_OLD.format(serial="ADR-023", title="L2 OCR 文档数字化组件建设",
                           date="2026-09-02"))
    hard, _soft = mod.adr_audit(roots=[("kb", kb), ("component", comp)])
    assert any(h.startswith("R3") for h in hard), hard


# --- 数据源可用性（红线：不可用即缺陷，不得静默当通过）------------------

def test_missing_scan_root_is_hard_not_silent(tmp_path):
    """根目录缺失时报错而非静默通过。"""
    mod = _load()
    hard, _soft = mod.adr_audit(roots=[("kb", tmp_path / "nope")])
    assert hard and "无结果" in hard[0]


# --- schema 键别名归一（ADR-017/018/023 曾用 adr_id）--------------------

def test_adr_id_alias_is_normalized(tmp_path):
    """``adr_id`` 应被识别为主键，且记一条 schema 漂移（不再报「缺 id」）。"""
    mod = _load()
    p = tmp_path / "adr_id_case.md"
    p.write_text(textwrap.dedent("""\
        ---
        adr_id: ADR-202608-017
        title: Bangcle PPT 模板
        status: accepted
        date: 2026-09-01
        layers: [L4]
        tags: [adr]
        ---

        # ADR-017
        """), encoding="utf-8")
    doc = mod.parse_doc(p, base=tmp_path)
    assert doc.doc_id == "ADR-202608-017", doc.doc_id
    assert any("adr_id" in d for d in doc.drift), doc.drift


def test_layer_singular_key_still_detected(tmp_path):
    """旧式 ``layer: L2`` 仍应被识别（并记漂移），不得静默丢失层级。"""
    mod = _load()
    p = tmp_path / "layer_case.md"
    p.write_text(textwrap.dedent("""\
        ---
        id: ADR-202609-023
        title: OCR
        status: accepted
        date: 2026-09-02
        layer: L2
        tags: [adr]
        ---

        # ADR-023
        """), encoding="utf-8")
    doc = mod.parse_doc(p, base=tmp_path)
    assert doc.layers == ["L2"], doc.layers
    assert any("layers" in d for d in doc.drift), doc.drift


# --- CLI 契约 ------------------------------------------------------------

def test_cli_adr_audit_flag_exists():
    import subprocess
    import sys

    r = subprocess.run(
        [sys.executable, str(KB_INDEX), "--help"],
        capture_output=True, text=True,
    )
    assert r.returncode == 0
    assert "--adr-audit" in r.stdout
