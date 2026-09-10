"""
每日内容生成器 — 根据当日计划输出学习内容大纲

输入：当日计划（来自 planner）
输出：考点列表 + 对应 OSG 章节 + 建议学习顺序

数据源：
  - domains.json：域/主项/子项结构
  - chapter_map.json：考点 → OSG 章节映射
"""

import json
from pathlib import Path
from datetime import date

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def load_domains():
    with open(DATA_DIR / "domains.json", encoding="utf-8") as f:
        return json.load(f)["domains"]


def load_chapter_map():
    """加载考点 → OSG 章节映射"""
    # chapter_map.json 是列表，每项: {domain, chapter, section, desc}
    map_path = DATA_DIR / "chapter_map.json"
    if not map_path.exists():
        # 尝试从 /tmp 加载
        import os
        tmp_path = "/tmp/cissp_chapter_map.json"
        if os.path.exists(tmp_path):
            with open(tmp_path, encoding="utf-8") as f:
                return json.load(f)
        return []
    with open(map_path, encoding="utf-8") as f:
        return json.load(f)


def get_main_topic_details(domain_id, main_id):
    """获取某个主项的详细信息（子项 + 章节映射）"""
    domains = load_domains()
    chapter_map = load_chapter_map()

    domain = next((d for d in domains if d["id"] == domain_id), None)
    if not domain:
        return None

    main = next((m for m in domain["main_topics"] if m["id"] == main_id), None)
    if not main:
        return None

    # 查找相关章节映射（模糊匹配主项名称）
    related_sections = []
    main_name_key = main["name"][:8]  # 取前几个字做匹配
    for item in chapter_map:
        section_name = item.get("section", "")
        if main_name_key and main_name_key in section_name:
            related_sections.append({
                "chapter": item.get("chapter", ""),
                "section": section_name,
                "desc": item.get("desc", "")
            })
        if len(related_sections) >= 5:
            break

    return {
        "domain_id": domain["id"],
        "domain_name": domain["name"],
        "main_id": main["id"],
        "main_name": main["name"],
        "sub_topics": main["sub_topics"],
        "related_sections": related_sections
    }


def generate_daily_content(day_plan):
    """根据当日计划生成学习内容大纲"""
    if not day_plan or not day_plan.get("items"):
        return None

    sections = []
    for item in day_plan["items"]:
        detail = get_main_topic_details(item["domain_id"], item["main_id"])
        if detail:
            sections.append({
                "hours": item["hours"],
                "domain": detail["domain_name"],
                "main_topic": detail["main_name"],
                "key_points": detail["sub_topics"],
                "osg_references": detail["related_sections"]
            })
        else:
            sections.append({
                "hours": item["hours"],
                "domain": item["domain_name"],
                "main_topic": item["main_name"],
                "key_points": item.get("sub_topics_sample", []),
                "osg_references": []
            })

    return {
        "date": day_plan["date"],
        "day_of_week": day_plan["day_of_week"],
        "planned_hours": day_plan["planned_hours"],
        "is_weekend": day_plan["is_weekend"],
        "sections": sections,
        "suggested_order": [i for i in range(len(sections))]
    }


def format_daily_content(content):
    """格式化输出每日内容"""
    lines = []
    lines.append(f"📅 {content['date']} {content['day_of_week']}")
    lines.append(f"⏱  计划学习: {content['planned_hours']}h")
    lines.append("")

    for i, sec in enumerate(content["sections"], 1):
        lines.append(f"## {i}. {sec['domain']} / {sec['main_topic']} ({sec['hours']}h)")
        lines.append("")
        if sec["key_points"]:
            lines.append("**核心考点：**")
            for j, kp in enumerate(sec["key_points"][:10], 1):
                lines.append(f"  {j}. {kp}")
            if len(sec["key_points"]) > 10:
                lines.append(f"  ... 还有 {len(sec['key_points']) - 10} 个考点")
            lines.append("")
        if sec["osg_references"]:
            lines.append("**OSG 参考章节：**")
            for ref in sec["osg_references"]:
                ch = ref["chapter"] or "?"
                lines.append(f"  - Ch.{ch}: {ref['section']} — {ref['desc'][:60]}")
            lines.append("")

    return "\n".join(lines)


def get_today_content():
    """获取今日学习内容"""
    from .planner import get_day_plan
    day_plan = get_day_plan()
    if day_plan is None:
        return None
    return generate_daily_content(day_plan)


if __name__ == "__main__":
    content = get_today_content()
    if content:
        print(format_daily_content(content))
    else:
        print("暂无今日学习计划，请先生成计划。")
