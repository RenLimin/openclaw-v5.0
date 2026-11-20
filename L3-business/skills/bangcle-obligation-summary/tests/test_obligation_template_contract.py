#!/usr/bin/env python3
"""bangcle-obligation-summary 关键路径回归测试。

关键路径（D-09）：履约义务汇总模板**实例化填实后**必须过 `check_answer_contract.py`
闸门。模板在 2026-11-20 补了契约信封骨架（元信息 / 溯源链 / 质量信号），
本测试锁定该骨架不回归（原缺 F4/F5 → BLOCK，与 D-03 同性质）。

hermetic：仅用模板 + tmp_path，不依赖 analysis_output/。
"""
import datetime
import re
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
TEMPLATE = SKILL_DIR / "assets" / "obligation-summary-template.md"
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
        """模板必须内建 F2 元信息 / F4 溯源链 / F5 质量信号（原缺 F4/F5）。"""
        text = TEMPLATE.read_text(encoding="utf-8")
        assert "> 生成时间：" in text and "契约版本" in text and "归属" in text
        assert re.search(r"^##\s*0?\.?\s*溯源链", text, re.M), "模板缺 ## 0. 溯源链"
        assert re.search(r"^##.*质量信号", text, re.M), "模板缺 质量信号 章节"
        assert "【已验证 YYYY-MM-DD|" in text, "模板缺【已验证 日期|来源】标注位"

    def test_instantiated_passes_contract(self, tmp_path):
        inst = _instantiate(tmp_path / "obligation.md")
        r = subprocess.run(
            [sys.executable, str(CONTRACT), str(inst)],
            capture_output=True, text=True, timeout=60,
        )
        assert r.returncode == 0, f"期望 PASS，实际 exit={r.returncode}\n{r.stdout}"
        assert "结果: PASS" in r.stdout

    def test_required_columns_present(self):
        """总表必须含 9 列契约字段（到期日带来源标注 + 到期标记）。"""
        text = TEMPLATE.read_text(encoding="utf-8")
        for col in ("项目编号", "履约义务编号", "授权/维保到期日", "到期标记", "子工作项数"):
            assert col in text, f"总表缺列：{col}"
