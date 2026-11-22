"""运行状态落盘（state）。

每任务状态机: pending → running → success / failed / skipped
终态 JSON 可被独立解析（hermetic 测试友好，run 目录隔离）。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from loader import DagSpec

TERMINAL = {"success", "failed", "skipped"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class TaskRun:
    task_id: str
    status: str = "pending"  # pending / running / success / failed / skipped
    started_at: str | None = None
    finished_at: str | None = None
    error: str | None = None
    artifact_paths: dict[str, str] = field(default_factory=dict)


class RunState:
    """一次 run 的全部任务状态。"""

    def __init__(self, dag: DagSpec) -> None:
        self.tasks: dict[str, TaskRun] = {t.id: TaskRun(t.id) for t in dag.tasks}

    def update(self, task_id: str, **kw: object) -> None:
        r = self.tasks[task_id]
        for k, v in kw.items():
            setattr(r, k, v)

    def to_dict(self) -> dict:
        return {
            "status": "running",
            "tasks": {k: asdict(v) for k, v in self.tasks.items()},
        }

    def save(self, path: str | Path) -> None:
        Path(path).write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )

    @classmethod
    def load(cls, path: str | Path) -> dict:
        return json.loads(Path(path).read_text(encoding="utf-8"))


def mark_started(state: RunState, task_id: str) -> None:
    state.update(task_id, status="running", started_at=_now_iso())


def mark_finished(state: RunState, task_id: str, status: str, error: str | None = None) -> None:
    state.update(task_id, status=status, error=error, finished_at=_now_iso())
