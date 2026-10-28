"""E2E：真实合同全流程（CLI 实跑，真实 HTTP/文件，非 mock）。"""
import os
import subprocess
import sys

import pytest

COMPONENT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CLI = os.path.join(COMPONENT_ROOT, "cli", "contractctl.py")

# 真实合同样例（含扫描页）
FIXTURES = os.path.join(COMPONENT_ROOT, "tests", "fixtures")


@pytest.fixture(scope="module")
def sample_pdf(tmp_path_factory):
    """生成含文本层 + 扫描页的真实合同 PDF（fitz 写文本层，图片页作扫描）。"""
    import fitz
    from PIL import Image, ImageDraw, ImageFont
    import io

    out = tmp_path_factory.mktemp("e2e") / "contract.pdf"
    text = (
        "技术服务合同\n甲方：北京某科技有限公司\n乙方：上海某服务有限公司\n"
        "本合同经双方盖章签字后生效。\n"
        "1. 服务内容：安全测评服务\n2. 服务内容：合规评估服务\n"
        "服务期限自2026年1月1日至2026年12月31日止。\n"
        "合同金额（大写）：壹万元整，人民币10000元。\n"
        "增值税税率6%。\n支付方式：银行转账，10个工作日内支付。\n"
        "乙方开具增值税专用发票。\n验收标准：按需求文档验收。\n"
        "违约责任：违约方支付违约金，违约金按合同金额10%。\n"
        "争议解决：向甲方所在地人民法院起诉。\n"
        "知识产权与成果归甲方所有。\n保密条款：保密期限为合同终止后3年。\n"
        "不可抗力：双方互不担责。\n合同解除条件：协商一致可解除。\n"
        "本合同一式肆份，甲乙双方各执贰份。\n"
    )
    doc = fitz.open()
    page = doc.new_page()
    y = 72
    for line in text.strip().split("\n"):
        page.insert_text((72, y), line, fontname="helv", fontsize=11)
        y += 18
    # 第二页：扫描型（图片）
    img = Image.new("RGB", (600, 200), "white")
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 24)
    except Exception:
        font = None
    d.text((20, 60), "APPENDIX SCAN PAGE 2026", fill="black", font=font)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    page2 = doc.new_page()
    page2.insert_image(fitz.Rect(0, 0, 612, 200), stream=buf.getvalue())
    doc.save(out)
    doc.close()
    return str(out)


def test_cli_init_db(tmp_path):
    db = tmp_path / "e2e.db"
    r = subprocess.run([sys.executable, CLI, "--db", str(db), "init-db"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert os.path.isfile(db)


def test_cli_review_full_flow(sample_pdf, tmp_path):
    db = tmp_path / "flow.db"
    out = tmp_path / "out"
    r = subprocess.run(
        [sys.executable, CLI, "--db", str(db), "--out-dir", str(out),
         "review", "--file", sample_pdf, "--source", "upload"],
        capture_output=True, text=True, timeout=180,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "审查完成" in r.stdout
    # 报告落盘
    reports = list(out.glob("*.md"))
    assert reports, "未生成 md 报告"
    content = reports[0].read_text(encoding="utf-8")
    assert "免责声明" in content
    assert "综合风险" in content


def test_cli_review_idempotent(sample_pdf, tmp_path):
    """同一文件连跑 3 次：风险结论稳定（幂等铁律）。"""
    db = tmp_path / "idem.db"
    outs = []
    for i in range(3):
        r = subprocess.run(
            [sys.executable, CLI, "--db", str(db), "review", "--file", sample_pdf],
            capture_output=True, text=True, timeout=180,
        )
        assert r.returncode == 0, r.stderr
        outs.append([line for line in r.stdout.splitlines() if "综合风险" in line])
    assert outs[0] == outs[1] == outs[2], "三次结果不一致: %s" % outs
