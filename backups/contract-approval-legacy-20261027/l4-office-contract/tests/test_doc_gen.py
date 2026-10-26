"""
合同文档生成多格式测试 — docx / markdown / text
"""

import os
import sys
import tempfile
import shutil
import pytest

MODULE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, MODULE_DIR)

from office_contract import config


@pytest.fixture(scope="module")
def setup():
    test_db = os.path.join(tempfile.gettempdir(), "test_contract_doc_gen.db")
    test_out = os.path.join(tempfile.gettempdir(), "test_contract_doc_gen_out")
    orig_db = config.DB_PATH
    orig_out = config.OUTPUT_DIR
    config.DB_PATH = test_db
    config.OUTPUT_DIR = test_out
    if os.path.exists(test_db):
        os.remove(test_db)
    if os.path.exists(test_out):
        shutil.rmtree(test_out)
    os.makedirs(test_out, exist_ok=True)

    from office_contract.services import init_db, create_contract
    init_db()
    cid = create_contract(
        title="文档生成测试合同",
        party_b="测试客户有限公司",
        amount=150000,
        contract_type="tech_service",
        effective_date="2026-09-01",
        expiry_date="2027-08-31",
    )["id"]

    yield {"contract_id": cid, "output_dir": test_out}

    config.DB_PATH = orig_db
    config.OUTPUT_DIR = orig_out
    if os.path.exists(test_db):
        os.remove(test_db)
    if os.path.exists(test_out):
        shutil.rmtree(test_out)


class TestDocGenerationFormats:
    def test_generate_docx(self, setup):
        from office_contract.services import generate_contract_doc
        result = generate_contract_doc(setup["contract_id"], format="docx")
        assert result["format"] == "docx"
        assert os.path.exists(result["output_path"])
        assert result["output_path"].endswith(".docx")
        assert os.path.getsize(result["output_path"]) > 1000

    def test_generate_markdown(self, setup):
        from office_contract.services import generate_contract_doc
        result = generate_contract_doc(setup["contract_id"], format="md")
        assert result["format"] == "markdown"
        assert os.path.exists(result["output_path"])
        assert result["output_path"].endswith(".md")
        assert "word_count" in result
        assert result["word_count"] > 500

        # 验证内容结构
        with open(result["output_path"], "r", encoding="utf-8") as f:
            content = f.read()
        assert "# 文档生成测试合同" in content
        assert "**甲方（委托方）：**" in content
        assert "**乙方（受托方）：**" in content
        assert "## 第一条 技术服务内容" in content
        assert "## 第十一条 其他" in content
        assert "壹拾伍万元整" in content  # 15 万大写

    def test_generate_markdown_full_alias(self, setup):
        from office_contract.services import generate_contract_doc
        result = generate_contract_doc(setup["contract_id"], format="markdown")
        assert result["format"] == "markdown"
        assert result["output_path"].endswith(".md")

    def test_generate_text(self, setup):
        from office_contract.services import generate_contract_doc
        result = generate_contract_doc(setup["contract_id"], format="txt")
        assert result["format"] == "text"
        assert os.path.exists(result["output_path"])
        assert result["output_path"].endswith(".txt")

        # 验证纯文本无 markdown 标记
        with open(result["output_path"], "r", encoding="utf-8") as f:
            content = f.read()
        # 移除 markdown 标记后不应有 ** 和 # 标题
        assert "**" not in content


class TestAmountToChinese:
    def test_amount_small(self):
        from office_contract.services.contract_service import _amount_to_chinese
        assert "伍万元" in _amount_to_chinese(50000)

    def test_amount_large(self):
        from office_contract.services.contract_service import _amount_to_chinese
        cn = _amount_to_chinese(1000000)
        assert "壹佰万元" in cn or "壹佰万" in cn

    def test_amount_with_decimal(self):
        from office_contract.services.contract_service import _amount_to_chinese
        cn = _amount_to_chinese(12345.67)
        assert "陆角" in cn or "柒分" in cn or "陆角柒分" in cn

    def test_amount_zero(self):
        from office_contract.services.contract_service import _amount_to_chinese
        cn = _amount_to_chinese(0)
        assert "零元" in cn
