"""合同 OCR 导入器 — ContractOCRImporter。

🔒 NO_TOKEN — 纯代码，零 AI 依赖。

职责：
  - 调用 ocr-digitalization skill 执行 OCR
  - 从 OCR 结果提取结构化字段
  - 检测签名/印章
"""

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Optional
from datetime import datetime

from bdms.core import db as _db
from bdms.core.paths import DATA_DIR
from ..base import BaseImporter


class ContractOCRImporter(BaseImporter):
    """合同 OCR 导入器。"""

    source_type = "ocr_contract"

    def __init__(self, db_path: Optional[Path] = None):
        super().__init__(db_path)

    # ─── BaseImporter 抽象方法 ───

    def _parse_source(self, source_path: Path) -> dict:
        """解析 OCR 结果。

        尝试调用 ocr-digitalization skill 或 tesseract CLI。
        """
        ocr_text = self._run_ocr(source_path)
        fields = self._extract_fields(ocr_text)
        signatures = self._detect_signatures(ocr_text)
        return {
            "ocr_text": ocr_text,
            "fields": fields,
            "signatures": signatures,
            "source_file": str(source_path),
        }

    def _validate_parsed(self, data: dict) -> bool:
        """校验 OCR 结果是否包含必要字段。"""
        fields = data.get("fields", {})
        # 至少要有合同编号或标题之一
        return bool(fields.get("contract_no") or fields.get("title"))

    def _persist_data(self, month: str, data: dict) -> dict[str, int]:
        """将 OCR 提取的字段持久化为合同记录。"""
        fields = data.get("fields", {})

        conn = _db.get_connection(self.db_path)
        try:
            now = datetime.now().isoformat()
            contract_no = fields.get("contract_no") or f"OCR-{now[:10].replace('-', '')}-{os.urandom(2).hex().upper()}"

            from ._crypto import encrypt
            cur = conn.execute(
                """INSERT INTO cr_contracts
                   (created_at, updated_at, created_by, updated_by,
                    contract_no, title, contract_type,
                    party_a, party_b, amount, currency,
                    effective_date, expiry_date, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    now, now, "ocr_import", "ocr_import",
                    contract_no,
                    fields.get("title", f"OCR导入-{contract_no}"),
                    fields.get("contract_type", ""),
                    encrypt(fields.get("party_a", "")),
                    encrypt(fields.get("party_b", "")),
                    float(fields.get("amount", 0)),
                    fields.get("currency", "CNY"),
                    fields.get("effective_date", ""),
                    fields.get("expiry_date", ""),
                    "draft",
                ],
            )
            contract_id = cur.lastrowid

            # 保存 OCR 原文到条款表（作为参考）
            if contract_id:
                conn.execute(
                    """INSERT INTO cr_contract_clauses
                       (contract_id, clause_type, clause_title, clause_content, created_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    (contract_id, "ocr_raw", "OCR 原文",
                     data.get("ocr_text", "")[:5000], now),
                )

            conn.commit()
            return {"cr_contracts": 1}
        finally:
            conn.close()

    # ─── OCR 执行 ───

    def _run_ocr(self, source_path: Path) -> str:
        """执行 OCR 识别。

        优先级：
        1. ocr-digitalization skill（如果可用）
        2. tesseract CLI（如果已安装）
        3. 返回空字符串
        """
        # 尝试 tesseract
        try:
            result = subprocess.run(
                ["tesseract", str(source_path), "stdout", "-l", "chi_sim+eng"],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        # 尝试 ocr-digitalization skill（通过 openclaw）
        skill_path = os.path.expanduser(
            "~/.openclaw/workspace/skills/ocr-digitalization"
        )
        if Path(skill_path).exists():
            # skill 目录存在，尝试调用
            try:
                result = subprocess.run(
                    ["openclaw", "run", "ocr-digitalization", str(source_path)],
                    capture_output=True, text=True, timeout=120,
                )
                if result.returncode == 0:
                    return result.stdout.strip()
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass

        return ""

    # ─── 字段提取 ───

    def _extract_fields(self, ocr_text: str) -> dict:
        """从 OCR 文本中提取结构化字段。"""
        fields = {}

        # 合同编号
        m = re.search(r'合同编号[：:\s]*([A-Za-z0-9\-_/\.]+)', ocr_text)
        if m:
            fields["contract_no"] = m.group(1).strip()

        # 标题
        m = re.search(r'(?:合同名称|项目名称)[：:\s]*([^\n]{2,50})', ocr_text)
        if m:
            fields["title"] = m.group(1).strip()

        # 甲方
        m = re.search(r'甲方[：:\s]*([^\n]{2,30})', ocr_text)
        if m:
            fields["party_a"] = m.group(1).strip()

        # 乙方
        m = re.search(r'乙方[：:\s]*([^\n]{2,30})', ocr_text)
        if m:
            fields["party_b"] = m.group(1).strip()

        # 金额
        m = re.search(r'(?:合同金额|总金额|金额)[：:\s]*[￥¥]?\s*([\d,]+(?:\.\d+)?)\s*(万元|元)?', ocr_text)
        if m:
            amount = float(m.group(1).replace(",", ""))
            unit = m.group(2) or "元"
            if unit == "万元":
                amount *= 10000
            fields["amount"] = amount

        # 日期
        m = re.search(r'(?:签订日期|签署日期|生效日期)[：:\s]*(\d{4}[-/年]\d{1,2}[-/月]\d{1,2})', ocr_text)
        if m:
            fields["effective_date"] = m.group(1).replace("年", "-").replace("月", "-").replace("/", "-")

        m = re.search(r'(?:到期日期|终止日期|有效期至)[：:\s]*(\d{4}[-/年]\d{1,2}[-/月]\d{1,2})', ocr_text)
        if m:
            fields["expiry_date"] = m.group(1).replace("年", "-").replace("月", "-").replace("/", "-")

        return fields

    # ─── 签名/印章检测 ───

    def _detect_signatures(self, ocr_text: str) -> dict:
        """检测签名/印章（基于文本特征）。"""
        has_signature = bool(re.search(r'(签字|签章|盖章|签署|签名|印章)', ocr_text))
        signature_count = len(re.findall(r'(签字|签章|盖章|签署)', ocr_text))

        # 检测是否有双方签署
        party_a_signed = bool(re.search(r'甲方[^\n]*(?:签字|盖章|签章)', ocr_text))
        party_b_signed = bool(re.search(r'乙方[^\n]*(?:签字|盖章|签章)', ocr_text))

        return {
            "has_signature": has_signature,
            "signature_count": signature_count,
            "party_a_signed": party_a_signed,
            "party_b_signed": party_b_signed,
            "fully_signed": party_a_signed and party_b_signed,
        }
