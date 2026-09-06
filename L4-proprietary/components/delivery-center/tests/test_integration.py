"""集成测试"""

import pytest
import pandas as pd
from pathlib import Path

TEST_DATA_DIR = Path.home() / "Bangcle Workspace/01. Management/2026/2026团队报告/202606"


def test_full_pipeline_dry_run():
    """端到端流水线 dry-run 测试"""
    from scripts.l4.delivery_center.main import run_pipeline

    result = run_pipeline(
        month="202606",
        data_dir=str(TEST_DATA_DIR),
        output_dir="/tmp/bdms_test",
    )

    assert result["status"] == "ok"
    assert result["month"] == "202606"


def test_data_files_exist():
    """验证所有测试数据文件存在"""
    required_files = [
        "202606周报-签约项目统计.csv",
        "202606周报-POC&提前实施统计.csv",
        "202606-签约项目异常处置.csv",
        "202606确收凭证交接-确收.csv",
        "202606确收凭证交接-验收.csv",
        "202606工时填报.xlsx",
        "2026交付月报-20260630.xlsx",
    ]

    for f in required_files:
        file_path = TEST_DATA_DIR / f
        assert file_path.exists(), f"测试数据缺失: {f}"


def test_report_structure_analysis_exists():
    """验证报告结构分析文档存在"""
    analysis_file = Path.home() / ".openclaw/workspace/docs/architecture/components/l4-delivery-center/references/report_structure_analysis.md"
    assert analysis_file.exists()
