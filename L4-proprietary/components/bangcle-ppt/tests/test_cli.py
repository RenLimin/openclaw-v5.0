"""
CLI 测试 — pptgen 命令行工具
至少 10 个测试用例
"""

from __future__ import annotations

import os
import sys
import tempfile
import yaml
import pytest

# 路径设置
_HERE = os.path.dirname(os.path.abspath(__file__))
_PKG_ROOT = os.path.dirname(_HERE)
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

from bangcle_ppt.cli.pptgen import main as cli_main


# ── Fixtures ────────────────────────────────────────────────────────

@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


@pytest.fixture
def sample_spec_path(tmp_dir):
    """创建一个有效的 DSL YAML 文件并返回路径。"""
    spec = {
        "title": "测试演示",
        "theme": "light",
        "slides": [
            {
                "meta": {
                    "name": "封面",
                    "page_type": "cover-light",
                    "theme": "light",
                },
                "data": {
                    "title": "测试标题",
                    "subtitle": "TEST SUBTITLE",
                    "presenter": "Jerry",
                },
            },
            {
                "meta": {
                    "name": "结束",
                    "page_type": "closing-light",
                    "theme": "light",
                },
                "data": {
                    "main_text": "谢谢观看",
                    "subtitle": "THANK YOU",
                },
            },
        ],
    }
    path = os.path.join(tmp_dir, "spec.yaml")
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(spec, f, allow_unicode=True)
    return path


@pytest.fixture
def invalid_spec_path(tmp_dir):
    """创建一个无效的 DSL YAML 文件。"""
    spec = {
        "title": "坏演示",
        "theme": "invalid-theme",  # 无效主题
        "slides": [
            {
                "meta": {
                    "name": "坏页",
                    "page_type": "nonexistent-type",  # 不存在的 page_type
                    "theme": "light",
                },
                "data": {},
            },
        ],
    }
    path = os.path.join(tmp_dir, "bad.yaml")
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(spec, f, allow_unicode=True)
    return path


# ── Helpers ─────────────────────────────────────────────────────────

def run_cli(*args):
    """运行 CLI 并返回 (return_code, stdout, stderr)。"""
    import io
    import contextlib

    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()

    with contextlib.redirect_stdout(stdout_buf):
        with contextlib.redirect_stderr(stderr_buf):
            try:
                rc = cli_main(list(args))
            except SystemExit as e:
                rc = e.code if e.code is not None else 0

    return rc, stdout_buf.getvalue(), stderr_buf.getvalue()


# ── 测试 1: --help ──────────────────────────────────────────────────

def test_cli_help():
    rc, out, _ = run_cli("--help")
    assert rc == 0
    assert "pptgen" in out
    assert "render" in out
    assert "list-templates" in out
    assert "info" in out
    assert "demo" in out
    assert "validate" in out


# ── 测试 2: list-templates light ────────────────────────────────────

def test_list_templates_light():
    rc, out, _ = run_cli("list-templates", "--theme", "light")
    assert rc == 0
    assert "cover-light" in out
    assert "19" in out or "个" in out  # 数量信息


# ── 测试 3: list-templates dark ─────────────────────────────────────

def test_list_templates_dark():
    rc, out, _ = run_cli("list-templates", "--theme", "dark")
    assert rc == 0
    assert "cover-dark" in out


# ── 测试 4: list-templates --json ───────────────────────────────────

def test_list_templates_json():
    import json
    rc, out, _ = run_cli("list-templates", "--theme", "light", "--json")
    assert rc == 0
    data = json.loads(out)
    assert data["theme"] == "light"
    assert isinstance(data["templates"], list)
    assert len(data["templates"]) >= 15
    assert "cover-light" in data["templates"]


# ── 测试 5: info 有效模板 ───────────────────────────────────────────

def test_info_valid_template():
    rc, out, _ = run_cli("info", "cover-light")
    assert rc == 0
    assert "cover-light" in out
    assert "Layout 字段" in out
    assert "title" in out
    assert "示例数据" in out


# ── 测试 6: info 无效模板 ───────────────────────────────────────────

def test_info_invalid_template():
    rc, out, _ = run_cli("info", "nonexistent-template-xyz")
    assert rc == 1
    assert "不存在" in out


# ── 测试 7: info --json ─────────────────────────────────────────────

def test_info_json():
    import json
    rc, out, _ = run_cli("info", "cover-light", "--json")
    assert rc == 0
    data = json.loads(out)
    assert data["page_type"] == "cover-light"
    assert "layout_fields" in data
    assert isinstance(data["layout_fields"], list)
    assert "sample_data" in data


# ── 测试 8: validate 有效 DSL ───────────────────────────────────────

def test_validate_valid(sample_spec_path):
    rc, out, _ = run_cli("validate", sample_spec_path)
    assert rc == 0
    assert "校验通过" in out
    assert "测试演示" in out


# ── 测试 9: validate 无效 DSL ───────────────────────────────────────

def test_validate_invalid(invalid_spec_path):
    rc, out, _ = run_cli("validate", invalid_spec_path)
    assert rc == 1
    assert "失败" in out or "未通过" in out


# ── 测试 10: validate 文件不存在 ────────────────────────────────────

def test_validate_missing_file():
    rc, out, _ = run_cli("validate", "/nonexistent/path/spec.yaml")
    assert rc == 1
    assert "不存在" in out


# ── 测试 11: validate --json ────────────────────────────────────────

def test_validate_json_valid(sample_spec_path):
    import json
    rc, out, _ = run_cli("validate", sample_spec_path, "--json")
    assert rc == 0
    data = json.loads(out)
    assert data["valid"] is True
    assert data["title"] == "测试演示"
    assert data["slide_count"] == 2


# ── 测试 12: render 生成 PPT ────────────────────────────────────────

def test_render_valid(sample_spec_path, tmp_dir):
    out_path = os.path.join(tmp_dir, "output.pptx")
    rc, out, _ = run_cli("render", sample_spec_path, "--output", out_path)
    assert rc == 0
    assert os.path.exists(out_path)
    assert os.path.getsize(out_path) > 1000  # PPT 至少 1KB
    assert "生成成功" in out


# ── 测试 13: render 主题覆盖 ────────────────────────────────────────

def test_render_with_theme(sample_spec_path, tmp_dir):
    out_path = os.path.join(tmp_dir, "dark.pptx")
    rc, out, _ = run_cli("render", sample_spec_path, "--output", out_path, "--theme", "light")
    assert rc == 0
    assert os.path.exists(out_path)
    assert os.path.getsize(out_path) > 1000


# ── 测试 14: render 文件不存在 ──────────────────────────────────────

def test_render_missing_file(tmp_dir):
    rc, out, _ = run_cli("render", "/tmp/nonexistent.yaml")
    assert rc == 1
    assert "不存在" in out


# ── 测试 15: demo 生成 ──────────────────────────────────────────────

def test_demo_light(tmp_dir):
    out_path = os.path.join(tmp_dir, "demo-light.pptx")
    rc, out, _ = run_cli("demo", "--theme", "light", "--output", out_path)
    assert rc == 0
    assert os.path.exists(out_path)
    assert os.path.getsize(out_path) > 5000  # 多页 PPT 应该更大
    assert "全模板示例" in out or "生成成功" in out


# ── 测试 16: 无子命令显示帮助 ───────────────────────────────────────

def test_no_command_shows_help():
    rc, out, _ = run_cli()
    assert rc == 0
    assert "usage" in out.lower() or "pptgen" in out


# ── 测试 17: python -m bangcle_ppt.cli 入口 ─────────────────────────

def test_module_entry_point():
    """验证 python -m bangcle_ppt.cli 入口可用。"""
    import subprocess
    result = subprocess.run(
        [sys.executable, "-m", "bangcle_ppt.cli", "--help"],
        capture_output=True, text=True, cwd=_PKG_ROOT,
    )
    assert result.returncode == 0
    assert "pptgen" in result.stdout


# ── 测试 18: cli/pptgen.py 直接运行 ─────────────────────────────────

def test_direct_cli_script():
    """验证 cli/pptgen.py 直接运行可用。"""
    import subprocess
    cli_script = os.path.join(_PKG_ROOT, "cli", "pptgen.py")
    result = subprocess.run(
        [sys.executable, cli_script, "list-templates", "--json"],
        capture_output=True, text=True, cwd=_PKG_ROOT,
    )
    assert result.returncode == 0
    import json
    data = json.loads(result.stdout)
    assert "templates" in data
