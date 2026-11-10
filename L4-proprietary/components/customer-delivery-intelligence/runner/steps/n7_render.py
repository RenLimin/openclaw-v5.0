"""N7 渲染与交付：六类产物 → Markdown + PPTX + DOCX；按受众适配。

- Markdown：本组件 render_md
- PPTX：复用既有 L4 bangcle-ppt 引擎（Bangcle VI 模板）
- DOCX：复用既有 L2 office-generation 引擎（微软雅黑）
"""
from __future__ import annotations
from datetime import datetime
from pathlib import Path
from ..models import ArtifactSet
from .. import render_md, ppt_bridge, docx_bridge


def run(state: dict) -> dict:
    art = ArtifactSet.model_validate(state["artifacts"])
    customer = state["input_norm"]["customer"]
    audience = state["input_norm"]["audience"]
    date_label = datetime.now().strftime("%Y年%m月")
    out_dir = Path("storage/artifacts")/state["task_id"]
    out_dir.mkdir(parents=True, exist_ok=True)

    md_paths = render_md.render(art, str(out_dir), customer, audience)

    safe = customer.replace("/", "_")
    pptx_path = ppt_bridge.render_pptx(
        art, customer, str(out_dir/f"{safe}-项目交付汇报.pptx"), date_label)
    docx_path = docx_bridge.render_docx(
        art, customer, str(out_dir/f"{safe}-项目交付说明.docx"), date_label)

    state["renders"] = {"md": md_paths, "pptx": pptx_path, "docx": docx_path}
    state["audit"]["status"] = "PASS"
    state["_event"] = "pass"
    return state
