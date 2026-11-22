"""dag-orchestrator 测试夹具与共享 fixtures。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import loader  # noqa: E402  (确保 scripts 可导入)


@pytest.fixture
def sample_dag():
    """SKILL.md 内嵌「交付月报」示例（6 任务 / 并行度 3）。"""
    return loader.parse_dag(
        {
            "name": "交付月报生成",
            "description": "采集数据并生成交付月报",
            "tasks": [
                {"id": "collect_oa", "name": "采集 OA 合同台账",
                 "agent": "data-collector", "action": "collect_oa_contracts",
                 "outputs": ["oa_data"]},
                {"id": "collect_revenue", "name": "采集确收凭证",
                 "agent": "data-collector", "action": "collect_revenue_vouchers",
                 "outputs": ["revenue_data"]},
                {"id": "collect_acceptance", "name": "采集验收凭证",
                 "agent": "data-collector", "action": "collect_acceptance_vouchers",
                 "outputs": ["acceptance_data"]},
                {"id": "join_data", "name": "关联数据",
                 "agent": "data-analyst", "action": "join_sources",
                 "inputs": ["oa_data", "revenue_data", "acceptance_data"],
                 "outputs": ["joined_data"],
                 "depends_on": ["collect_oa", "collect_revenue", "collect_acceptance"]},
                {"id": "analyze", "name": "分析数据",
                 "agent": "data-analyst", "action": "analyze",
                 "inputs": ["joined_data"], "outputs": ["analysis_result"],
                 "depends_on": ["join_data"]},
                {"id": "generate_report", "name": "生成报告",
                 "agent": "report-generator", "action": "generate_delivery_report",
                 "inputs": ["analysis_result"], "outputs": ["report_file"],
                 "depends_on": ["analyze"]},
            ],
        }
    )
