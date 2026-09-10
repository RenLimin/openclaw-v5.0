"""
pytest fixtures for session-isolation 组件测试
"""
import os
import sys
import shutil
import tempfile
import pytest
from pathlib import Path

# 组件根目录
COMP_DIR = Path(__file__).resolve().parent.parent

# 确保 scripts 目录在 path 里
sys.path.insert(0, str(COMP_DIR))
sys.path.insert(0, str(COMP_DIR / "scripts"))


@pytest.fixture
def tmp_workspace(tmp_path, monkeypatch):
    """
    创建临时 workspace，包含 tasks/ 和 state/ 目录
    所有被测函数都用相对路径，所以需要 chdir 到临时目录
    """
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    # 创建任务模板目录
    templates_dir = workspace / "tasks" / "_templates"
    templates_dir.mkdir(parents=True)

    # 复制 TASK.yml 模板
    src_template = Path(__file__).resolve().parent.parent.parent.parent.parent / "tasks" / "_templates" / "TASK.yml"
    if src_template.exists():
        shutil.copy(src_template, templates_dir / "TASK.yml")
    else:
        # fallback: 手写一个最小模板
        (templates_dir / "TASK.yml").write_text("""id: task-YYYYMMDD-NNN
name: <任务名称>
status: pending
priority: medium
created_at: YYYY-MM-DDTHH:MM:SS+08:00
updated_at: YYYY-MM-DDTHH:MM:SS+08:00
owner: <负责人>
scope:
  project: <项目名>
  component: <组件名>
  version: <版本号>
goals:
  - id: g1
    description: <目标1>
    status: pending
dependencies: []
blockers: []
context: []
artifacts: []
""")

    # 切换到临时 workspace
    monkeypatch.chdir(workspace)

    # 同时创建 in-progress 目录
    (workspace / "tasks" / "in-progress").mkdir(parents=True, exist_ok=True)
    (workspace / "state").mkdir(parents=True, exist_ok=True)

    return workspace
