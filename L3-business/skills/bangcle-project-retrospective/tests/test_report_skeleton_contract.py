#!/usr/bin/env python3
"""bangcle-project-retrospective 关键路径回归测试。

本技能**无 scripts/、无 assets/ 模板**（纯方法论 + references 手册），
故关键路径 = 产出报告的**结构契约**：按 SKILL.md Step 4 规定的报告骨架
（复盘范围与层级 → 全景 → 交付与反馈 → 产品差异与交付方案改进 → PMBOK 复盘与
项目计划改进 → 三句话结论）+ 应答契约，实例化后必须过 `check_answer_contract.py`。

同时锁定 references/retro-evidence-playbook.md 的 6 个必算指标与三档证据铁律不回归。

hermetic：仅用 references + tmp_path，不依赖 analysis_output/。
"""
import datetime
import re
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
PLAYBOOK = SKILL_DIR / "references" / "retro-evidence-playbook.md"
SKILL_MD = SKILL_DIR / "SKILL.md"
CONTRACT = (
    SKILL_DIR.parent.parent.parent
    / "L2-infra" / "prompts" / "tools" / "check_answer_contract.py"
)

# SKILL.md Step 4 规定的报告骨架章节（顺序即契约）
REPORT_SECTIONS = [
    "复盘范围与层级",
    "全景",
    "交付与反馈",
    "产品差异与交付方案改进",
    "项目计划改进",
    "结论",
]


def _render_report(dest: Path) -> Path:
    """按 SKILL.md Step 4 骨架渲染一份契约合规的复盘报告样例。"""
    today = datetime.date.today().isoformat()
    parts = [
        "# 测试客户项目复盘报告-v1",
        "",
        f"> 生成时间：{today}T10:00+08:00 ｜ 契约版本：answer-spec-base v1 ｜ 归属：Bangcle 交付中心",
        f"> 数据基准：{today} ｜ 客户：测试客户",
        ">",
        "> 【已验证 " + today + "|项目管理系统+product-kb】",
        "",
        "## 溯源链",
        "",
        f"数据源 → 查询条件 → 计算口径 → 结论：数据源=项目管理系统；查询条件=客户=测试客户；"
        f"计算口径=剔除建档记录；结论=样本 N 项。"
        f"【已验证 {today}|项目管理系统+product-kb】",
        "",
        "## 质量信号",
        "",
        "| 信号 | 取值 |",
        "|---|---|",
        "| 取数完整性 | fetched/total = 1/1 |",
        "| 契约校验 | check_answer_contract PASS |",
        "",
    ]
    for sec in REPORT_SECTIONS:
        parts += [f"## {sec}", "", "（样例正文，含证据级【已验证】标注）", ""]
    dest.write_text("\n".join(parts), encoding="utf-8")
    return dest


class TestReportSkeletonContract:
    def test_skill_documents_report_skeleton(self):
        """SKILL.md 必须写明报告骨架（Step 4），否则产出无契约可校验。"""
        text = SKILL_MD.read_text(encoding="utf-8")
        assert "报告结构" in text
        assert "落盘" in text and "check_answer_contract" in text

    def test_rendered_report_passes_contract(self, tmp_path):
        """按骨架渲染的报告必须 PASS，exit=0。"""
        report = _render_report(tmp_path / "retro.md")
        r = subprocess.run(
            [sys.executable, str(CONTRACT), str(report)],
            capture_output=True, text=True, timeout=60,
        )
        assert r.returncode == 0, f"期望 PASS，实际 exit={r.returncode}\n{r.stdout}"
        assert "结果: PASS" in r.stdout


class TestEvidencePlaybook:
    """references/retro-evidence-playbook.md 的防幻觉铁律不回归。"""

    def test_three_grade_evidence_rule(self):
        text = PLAYBOOK.read_text(encoding="utf-8")
        assert "【已验证 YYYY-MM-DD｜来源】" in text
        assert "【推断】" in text and "【缺失】" in text
        assert "禁止用印象补齐" in text or "不得裸推断" in text

    def test_six_required_metrics(self):
        """6 个必算量化指标必须齐备（缺任一即复盘不完整）。"""
        text = PLAYBOOK.read_text(encoding="utf-8")
        for metric in (
            "POC 占比", "计划日期完整率", "在途无计划率",
            "占位 owner 率", "无合同归属率", "脏数据",
        ):
            assert metric in text, f"6 指标缺：{metric}"

    def test_done_rate_caveat_documented(self):
        """必须写明 statusCategory=done 完成率不可当作在途健康度（防误读）。"""
        text = PLAYBOOK.read_text(encoding="utf-8")
        assert "不可当作在途健康度" in text
