#!/usr/bin/env python3
"""bangcle-customer-profile 关键路径回归测试。

关键路径（D-09）：客户画像模板**实例化填实后**必须过 `check_answer_contract.py`
闸门。模板在 2026-11-20 补了契约信封骨架（元信息 / 溯源链 / 质量信号，
原缺 F5），本测试锁定不回归。

hermetic：仅用模板 + tmp_path，不依赖 analysis_output/。
"""
import datetime
import re
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
TEMPLATE = SKILL_DIR / "assets" / "customer-profile-template.md"
CONTRACT = (
    SKILL_DIR.parent.parent.parent
    / "L2-infra" / "prompts" / "tools" / "check_answer_contract.py"
)


def _instantiate(dest: Path) -> Path:
    text = TEMPLATE.read_text(encoding="utf-8")
    text = text.replace("YYYY-MM-DD", datetime.date.today().isoformat())
    text = text.replace("【客户全称】", "测试客户")
    dest.write_text(text, encoding="utf-8")
    return dest


class TestTemplateEnvelope:
    def test_envelope_sections_present(self):
        """模板必须内建 F2 元信息 / F4 溯源链 / F5 质量信号（原缺 F5）。"""
        text = TEMPLATE.read_text(encoding="utf-8")
        assert "> 生成时间：" in text and "契约版本" in text and "归属" in text
        assert re.search(r"^##\s*溯源链", text, re.M), "模板缺 溯源链 章节"
        assert re.search(r"^##.*质量信号", text, re.M), "模板缺 质量信号 章节"
        assert "【已验证 YYYY-MM-DD|" in text, "模板缺【已验证 日期|来源】标注位"

    def test_instantiated_passes_contract(self, tmp_path):
        inst = _instantiate(tmp_path / "profile.md")
        r = subprocess.run(
            [sys.executable, str(CONTRACT), str(inst)],
            capture_output=True, text=True, timeout=60,
        )
        assert r.returncode == 0, f"期望 PASS，实际 exit={r.returncode}\n{r.stdout}"
        assert "结果: PASS" in r.stdout

    def test_evidence_grading_documented(self):
        """模板须写明三档证据级（【已验证】/【推断】/【缺失】），防幻觉。"""
        text = TEMPLATE.read_text(encoding="utf-8")
        assert "【已验证】" in text and "【推断】" in text and "【缺失】" in text
