"""合同解析器

解析合同 PDF 和 Excel，提取关键信息。
"""

import pandas as pd
from pathlib import Path
from typing import Optional


def parse_contract_pdf(pdf_path: str) -> Optional[dict]:
    """解析合同 PDF

    Args:
        pdf_path: PDF 文件路径

    Returns:
        合同信息字典
    """
    try:
        import pdfplumber
    except ImportError:
        print("pdfplumber 未安装: pip install pdfplumber")
        return None

    with pdfplumber.open(pdf_path) as pdf:
        text = ""
        for page in pdf.pages:
            text += page.extract_text() or ""

    # TODO: 提取关键信息（合同编号、金额、日期等）
    contract_info = {"raw_text": text, "pages": len(pdf.pages)}
    print(f"合同 PDF 解析: {len(pdf.pages)} 页")
    return contract_info


def extract_contract_fields(text: str) -> dict:
    """从合同文本中提取关键字段

    Args:
        text: 合同文本

    Returns:
        字段字典
    """
    import re

    fields = {}

    # 合同编号
    match = re.search(r"合同编号[：:]\s*(\S+)", text)
    if match:
        fields["合同编号"] = match.group(1)

    # 签约金额
    match = re.search(r"(?:签约金额|合同金额)[：:]\s*([\d,.]+)", text)
    if match:
        fields["签约金额"] = match.group(1)

    return fields


def batch_parse_contracts(pdf_dir: str) -> pd.DataFrame:
    """批量解析合同 PDF

    Args:
        pdf_dir: PDF 目录

    Returns:
        汇总 DataFrame
    """
    pdf_path = Path(pdf_dir)
    results = []

    for pdf_file in pdf_path.glob("*.pdf"):
        info = parse_contract_pdf(str(pdf_file))
        if info:
            info["文件名"] = pdf_file.name
            results.append(info)

    print(f"批量解析完成: {len(results)} 个合同")
    return pd.DataFrame(results)
