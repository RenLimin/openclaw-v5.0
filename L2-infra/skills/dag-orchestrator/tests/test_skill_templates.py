"""TC01–TC05 自动化：SKILL.md 内嵌 YAML 工作流定义块结构与引用完整性。

固化 v1.0 VERIFICATION 的 TC01–TC03 人工走查逻辑，防止模板块回归。
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

SKILL_PATH = Path(__file__).resolve().parents[1] / "SKILL.md"

# SKILL.md「内置工作流」声明表 → (任务数, 并行度)
EXPECTED = {
    "交付月报生成": (6, 3),
    "确收月报生成": (5, 2),
    "系统健康检查": (4, 4),
    "数据质量审计": (3, 1),
}


def _blocks():
    txt = SKILL_PATH.read_text(encoding="utf-8")
    return [yaml.safe_load(b) for b in re.findall(r"```yaml\n(.*?)```", txt, re.S)]


def test_tc01_yaml_legal():
    """TC01: 所有 ```yaml 块可 yaml.safe_load。"""
    assert len(_blocks()) >= 1


def test_tc02_ids_unique_and_deps_valid():
    """TC02/TC03: id 唯一、depends_on 无悬空、inputs 均由本图产出。"""
    for d in _blocks():
        tasks = d.get("tasks", [])
        ids = [t["id"] for t in tasks]
        assert len(ids) == len(set(ids)), f"{d.get('name')} id 重复"
        produced = {o for t in tasks for o in t.get("outputs", [])}
        for t in tasks:
            for dep in t.get("depends_on", []):
                assert dep in ids, f"{d.get('name')} 悬空依赖 {dep}"
            for inp in t.get("inputs", []):
                assert inp in produced, f"{d.get('name')} 输入 {inp} 无产出"


def test_tc05_templates_complete():
    """TC05: 4 个内置模板均有 YAML 定义块，且任务数/并行度与声明表一致。"""
    by_name = {d["name"]: d for d in _blocks()}
    assert set(by_name) == set(EXPECTED), f"模板缺失或多出: {set(by_name)}"
    for name, (n_tasks, par) in EXPECTED.items():
        tasks = by_name[name]["tasks"]
        assert len(tasks) == n_tasks, f"{name} 任务数 {len(tasks)} != {n_tasks}"
        first_wave = len([t for t in tasks if not t.get("depends_on")])
        assert first_wave == par, f"{name} 并行度 {first_wave} != {par}"
