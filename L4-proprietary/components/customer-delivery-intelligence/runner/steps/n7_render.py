"""N7 渲染与交付：六类产物 → Markdown（+ docx/PPT 后续）；按受众适配。"""
from __future__ import annotations
from pathlib import Path
from ..models import ArtifactSet
from .. import render_md


def run(state: dict) -> dict:
    art = ArtifactSet.model_validate(state["artifacts"])
    customer = state["input_norm"]["customer"]
    audience = state["input_norm"]["audience"]
    out_dir = Path("storage/artifacts")/state["task_id"]
    paths = render_md.render(art, str(out_dir), customer, audience)
    state["renders"] = {"md": paths}
    state["audit"]["status"] = "PASS"
    state["_event"] = "pass"
    return state
