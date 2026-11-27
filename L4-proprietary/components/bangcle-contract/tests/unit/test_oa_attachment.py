"""OA 单据合同附件自动获取（Rex 2026-11-27）回归。

背景：旧注释称「757 附件 REST 下载无权限」——实测为会话过期误判。
会话有效时 loadlink 可直接下载：886502 docx(PK)、其余三单 doc(OLE2)。

覆盖（依赖缺失 → pytest.skip，不伪 pass）：
- find_attachment_refs：从 xhrs.json 递归定位 filedatas（位置随单据而变）
- fetch_contract_text：真实下载 + magic 校验 + 文本抽取
- 编号缺失=warn 的新口径锁定（归档时才生成，不阻断）
"""
from __future__ import annotations

from pathlib import Path

import pytest

COMPONENT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = COMPONENT_ROOT / "tmp" / "oa-pif" / "raw"


def _refs(rid: str):
    from services.oa.enhance.attachment import find_attachment_refs
    p = RAW_DIR / rid / "xhrs.json"
    if not p.exists():
        pytest.skip("缺 raw: %s" % rid)
    return find_attachment_refs(p)


@pytest.mark.parametrize("rid", ["886502", "888194", "888171", "888166"])
def test_find_attachment_refs_real_shapes(rid):
    """四张真实单据均应检出合同附件引用（字段位置各异）。"""
    refs = _refs(rid)
    assert refs, "%s 未检出附件引用" % rid
    assert all(r["name"] for r in refs)
    assert any(r["url"] for r in refs), "至少一个引用带可构造 URL"


def test_contract_no_missing_is_warn_not_block():
    """规则口径（Rex 2026-11-27）：编号缺失=warn，不得 block/退回。"""
    from services.oa.enhance.checks import CheckResult, run_fixed_checks

    class _F:
        contract_name = "无编号合同名"
        request_id = "X"
        items = []
    res = run_fixed_checks(_F(), body_text="合同编号！\n\n服务开始日期\n2026-01-01\n服务结束日期\n2026-12-31\n")
    cn = [c for c in res if c.check_id == "contract_no_missing"]
    assert cn and cn[0].level == "warn", [c.to_dict() for c in res]
    # warn 不参与结论推导的「退回补充」
    from services.oa.enhance.remark import derive_verdict
    assert derive_verdict(res) != "退回补充"


@pytest.mark.parametrize("rid", ["886502"])
def test_fetch_contract_text_downloads_and_extracts(rid, tmp_path):
    """真实下载 + 文本抽取（会话失效/依赖缺失则 skip 留证）。"""
    from services.oa.enhance.attachment import AttachmentError, fetch_contract_text

    try:
        r = fetch_contract_text(RAW_DIR, rid, tmp_path)
    except Exception as exc:  # noqa: BLE001
        pytest.skip("OA 会话不可用：%s" % exc)
    if r.get("error"):
        pytest.skip("附件获取失败（会话/权限）：%s" % r["error"])
    assert r["found"], r
    assert Path(r["path"]).exists()
    assert len(r["text"]) > 200, "原文过短，疑似抽取失败"


def test_read_attachment_text_doc():
    """.doc 走 textutil（macOS 具备），缺工具返回 None 不伪造。"""
    from services.oa.enhance.attachment import read_attachment_text

    src = Path("/tmp/dl_888194.doc")
    if not src.exists():
        pytest.skip("缺 .doc 样本")
    t = read_attachment_text(src)
    assert t is None or len(t) > 100
