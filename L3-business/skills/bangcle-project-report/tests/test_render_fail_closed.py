#!/usr/bin/env python3
"""bangcle-project-report 关键路径回归测试。

覆盖 2026-11-20 验收缺陷 D-02 的修复：
  1. render_report 缺真实取数时间（fetchedAt）必须 fail-closed exit=2，禁止产出假「【已验证|来源】」章
  2. normalize / aggregate 必须透传 fetchedAt（来源：fetch 的 completeness.fetchedAt）
  3. 带真实 fetchedAt 时渲染正常，时间戳正确落入报告
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
RENDER = SCRIPTS / "render_report.py"
NORMALIZE = SCRIPTS / "normalize_and_classify.py"
AGGREGATE = SCRIPTS / "aggregate.py"

STAGE4_MIN = {
    "detail": [],
    "byCategory": {},
    "byProduct": {},
    "byPeriod": {},
    "period": {"start": "2026-01-01", "end": "2026-12-31"},
    "goalMatrix": [],
    "inProgressItems": [],
    "contracts": [],
}


def run_script(script: Path, payload: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(script)],
        input=json.dumps(payload, ensure_ascii=False),
        capture_output=True, text=True, timeout=60,
    )


class TestRenderFailClosed:
    """D-02 修复：缺 fetchedAt 不得渲染（fail-closed）。"""

    def test_missing_fetched_at_exit2(self):
        """缺 fetchedAt → exit=2，stdout 零输出（不产假报告）。"""
        r = run_script(RENDER, STAGE4_MIN)
        assert r.returncode == 2, f"期望 exit=2，实际 {r.returncode}"
        assert r.stdout.strip() == "", "fail-closed 时不得输出报告正文"
        assert "missing fetchedAt" in r.stderr

    def test_with_fetched_at_ok(self):
        """带真实 fetchedAt → exit=0，正文含正确【已验证 日期|来源】。"""
        payload = dict(STAGE4_MIN, fetchedAt="2026-11-20T10:00:00+08:00", customer="测试客户")
        r = run_script(RENDER, payload)
        assert r.returncode == 0, f"期望 exit=0，实际 {r.returncode}，stderr={r.stderr}"
        assert "【已验证 2026-11-20|项目管理系统签约视图+逐项目工作项】" in r.stdout
        assert "数据基准：2026-11-20" in r.stdout


class TestFetchedAtPassthrough:
    """D-02 修复：normalize / aggregate 不得剥掉溯源字段。"""

    def test_normalize_passthrough_from_completeness(self):
        """normalize 从 fetch 的 completeness.fetchedAt 透传。"""
        stage1 = {
            "projects": [],
            "tasks": [],
            "completeness": {"fetchedAt": "2026-11-20T09:30:00+08:00", "perProject": {}, "globalTruncated": False},
        }
        r = run_script(NORMALIZE, stage1)
        assert r.returncode == 0, r.stderr
        out = json.loads(r.stdout)
        assert out["fetchedAt"] == "2026-11-20T09:30:00+08:00"
        assert out["customer"] == ""
        assert out["dataSource"] == "项目管理系统"

    def test_aggregate_passthrough(self):
        """aggregate 透传 normalize 输出的 fetchedAt。"""
        stage2 = {
            "workItems": [],
            "stats": {"total": 0, "excluded": 0, "inPeriod": 0, "outPeriod": 0, "byIssueType": {}, "missingProductDirection": 0},
            "period": {"start": "2026-01-01", "end": "2026-12-31"},
            "fetchedAt": "2026-11-20T09:30:00+08:00",
            "customer": "测试客户",
            "dataSource": "项目管理系统",
        }
        r = run_script(AGGREGATE, stage2)
        assert r.returncode == 0, r.stderr
        out = json.loads(r.stdout)
        assert out["fetchedAt"] == "2026-11-20T09:30:00+08:00"
        assert out["customer"] == "测试客户"
