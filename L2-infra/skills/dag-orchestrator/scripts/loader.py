"""DAG 定义加载与结构校验（loader）。

契约（权威来源 SKILL.md §DAG 定义格式）：
- YAML 顶层: name / description / tasks[]
- task: id(唯一) / name / agent / action / inputs[] / outputs[] / depends_on[]
- 校验: id 唯一；depends_on 无悬空引用；inputs ⊆ 全图 outputs 并集（防输入名笔误）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


class DagValidationError(ValueError):
    """DAG 定义不合法。"""


@dataclass
class TaskSpec:
    """单个任务定义。timeout_s 为引擎扩展字段（SKILL 规则 4：默认 300s）。"""

    id: str
    name: str = ""
    agent: str = ""
    action: str = ""
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    timeout_s: int = 300


@dataclass
class DagSpec:
    """整个 DAG 定义。"""

    name: str
    description: str = ""
    tasks: list[TaskSpec] = field(default_factory=list)

    def task_map(self) -> dict[str, TaskSpec]:
        return {t.id: t for t in self.tasks}


def load_dag(path: str | Path) -> DagSpec:
    """从 YAML 文件加载并校验 DAG。"""
    p = Path(path)
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    return parse_dag(raw)


def parse_dag(raw: Any) -> DagSpec:
    """从已解析的 YAML 结构构建并校验 DagSpec。"""
    if not isinstance(raw, dict):
        raise DagValidationError("DAG 定义必须是 YAML 映射")
    name = raw.get("name")
    if not name:
        raise DagValidationError("DAG 缺少必填字段 name")
    tasks_raw = raw.get("tasks")
    if not isinstance(tasks_raw, list) or not tasks_raw:
        raise DagValidationError("DAG 必须包含非空 tasks 列表")

    tasks: list[TaskSpec] = []
    seen_ids: set[str] = set()
    for idx, t in enumerate(tasks_raw):
        if not isinstance(t, dict):
            raise DagValidationError(f"tasks[{idx}] 必须是映射")
        tid = t.get("id")
        if not tid:
            raise DagValidationError(f"tasks[{idx}] 缺少必填字段 id")
        if tid in seen_ids:
            raise DagValidationError(f"任务 id 重复: {tid}")
        seen_ids.add(tid)
        if not t.get("agent"):
            raise DagValidationError(f"任务 {tid} 缺少必填字段 agent")
        if not t.get("action"):
            raise DagValidationError(f"任务 {tid} 缺少必填字段 action")
        tasks.append(
            TaskSpec(
                id=str(tid),
                name=str(t.get("name", "")),
                agent=str(t["agent"]),
                action=str(t["action"]),
                inputs=[str(x) for x in t.get("inputs", [])],
                outputs=[str(x) for x in t.get("outputs", [])],
                depends_on=[str(x) for x in t.get("depends_on", [])],
                timeout_s=int(t.get("timeout_s", 300)),
            )
        )

    dag = DagSpec(name=str(name), description=str(raw.get("description", "")), tasks=tasks)
    _validate(dag)
    return dag


def _validate(dag: DagSpec) -> None:
    """结构校验：depends_on 无悬空；inputs ⊆ 全图 outputs 并集。"""
    ids = {t.id for t in dag.tasks}
    for t in dag.tasks:
        for dep in t.depends_on:
            if dep not in ids:
                raise DagValidationError(
                    f"任务 {t.id} 的 depends_on 引用不存在: {dep}"
                )
    produced = {o for t in dag.tasks for o in t.outputs}
    for t in dag.tasks:
        for inp in t.inputs:
            if inp not in produced:
                raise DagValidationError(
                    f"任务 {t.id} 的 inputs 引用了图中无人产出的变量: {inp}"
                )
