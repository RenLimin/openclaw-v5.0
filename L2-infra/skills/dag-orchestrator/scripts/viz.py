"""DAG → Mermaid 文本生成（viz，第一阶段）。

输出 graph TD 文本，可直接嵌入 Markdown 报告 / SKILL.md / 文档。
零依赖、零服务、hermetic。
"""

from __future__ import annotations

from loader import DagSpec


def to_mermaid(dag: DagSpec) -> str:
    """生成 Mermaid graph TD 文本。"""
    lines = ["graph TD"]
    for t in dag.tasks:
        node = f'    {t.id}["{t.id}: {t.name or t.action}"]'
        if node not in lines:
            lines.append(node)
    for t in dag.tasks:
        for dep in t.depends_on:
            lines.append(f"    {dep} --> {t.id}")
    lines.append("")
    return "\n".join(lines)
