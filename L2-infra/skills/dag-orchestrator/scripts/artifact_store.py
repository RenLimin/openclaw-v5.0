"""工件传递（artifact_store）。

上游任务 outputs → 下游任务 inputs（SKILL 执行规则 2）。
结构化 JSON 工件（DESIGN §7 未决事项 5 的裁定：JSON 工件结构化）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ArtifactNotFoundError(KeyError):
    """下游引用了不存在/未产出的上游工件。"""


class ArtifactStore:
    """按 output 名保存工件，按 input 名读取。"""

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    def put(self, output_name: str, value: Any) -> None:
        self._data[output_name] = value

    def get(self, input_name: str) -> Any:
        if input_name not in self._data:
            raise ArtifactNotFoundError(
                f"工件 {input_name} 不存在（上游未产出或已被跳过）"
            )
        return self._data[input_name]

    def snapshot(self) -> dict[str, Any]:
        return dict(self._data)

    def save(self, path: str | Path) -> None:
        Path(path).write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
