#!/usr/bin/env python3
"""bangcle-project-summary 关键路径回归测试。

关键路径（D-09）：台账模板**实例化填实后**必须过 `check_answer_contract.py`
闸门（防 D-03「缺溯源链/质量信号章节」与 D-02「空日期假溯源」同类缺陷复发）。

测试 hermetic：不依赖 analysis_output/（已 gitignore），仅用模板 + tmp_path。
"""
import datetime
import re
import subprocess
import sys
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).resolve().parent.parent
TEMPLATE = SKILL_DIR / "assets" / "delivery-ledger-template.md"
CONTRACT = (
    SKILL_DIR.parent.parent.parent
    / "L2-infra" / "prompts" / "tools" / "check_answer_contract.py"
)


def _instantiate(dest: Path, customer: str = "测试客户") -> Path:
    """把模板占位符（YYYY-MM-DD / 客户全称）替换为真实值。"""
    text = TEMPLATE.read_text(encoding="utf-8")
    today = datetime.date.today().isoformat()
    text = text.replace("YYYY-MM-DD", today).replace("【客户全称】", customer)
    dest.write_text(text, encoding="utf-8")
    return dest


class TestTemplateContract:
    def test_template_contains_envelope_sections(self):
        """模板必须内建契约信封骨架（F2 元信息 / F4 溯源链 / F5 质量信号）。"""
        text = TEMPLATE.read_text(encoding="utf-8")
        assert "> 生成时间：" in text and "契约版本" in text and "归属" in text
        assert re.search(r"^##\s*0?\.?\s*溯源链", text, re.M), "模板缺 ## 0. 溯源链"
        assert re.search(r"^##.*质量信号", text, re.M), "模板缺 质量信号 章节"
        assert "【已验证 YYYY-MM-DD|" in text, "模板缺【已验证 日期|来源】标注位"

    def test_instantiated_passes_contract(self, tmp_path):
        """实例化（填真实日期/客户）后必须 PASS，exit=0。"""
        inst = _instantiate(tmp_path / "ledger.md")
        r = subprocess.run(
            [sys.executable, str(CONTRACT), str(inst)],
            capture_output=True, text=True, timeout=60,
        )
        assert r.returncode == 0, f"期望 PASS，实际 exit={r.returncode}\n{r.stdout}"
        assert "结果: PASS" in r.stdout

    def test_real_timestamp_required_not_placeholder(self, tmp_path):
        """模板含占位 YYYY-MM-DD，未经实例化不得冒充已验证时间戳（fail-closed 前提）。"""
        text = TEMPLATE.read_text(encoding="utf-8")
        # 占位符不是合法日期 → 校验器原样跑应 BLOCK（证明闸门确实生效）
        assert "YYYY-MM-DD" in text
        raw = tmp_path / "raw.md"
        raw.write_text(text, encoding="utf-8")
        r = subprocess.run(
            [sys.executable, str(CONTRACT), str(raw)],
            capture_output=True, text=True, timeout=60,
        )
        assert r.returncode == 1, "原样模板应 BLOCK，否则契约闸门形同虚设"
