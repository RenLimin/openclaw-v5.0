#!/usr/bin/env python3
"""render_report.py — S6+S8 渲染与受众适配

输入 (stdin JSON): build_goal_matrix.py 的输出 + aggregate 输出
  {
    goalMatrix, inProgressItems, contracts,
    byCategory, byProduct, byPeriod, detail, period,
    audience: "external"|"internal"
  }

输出: 汇报 MD 到 stdout（或 --output 指定路径）
可选: --docx 导出 docx

退出码: 0=成功, 2=数据/BLOCK
"""
import json
import sys
import argparse
import re
import os
from datetime import datetime, timezone, timedelta

CST = timezone(timedelta(hours=8))

# ── 脱敏词表 ─────────────────────────────────────────────────────────
REDACTION_TERMS = [
    "ONES", "OA", "BDMS", "GraphQL", "harbor", "SSXM",
    "内部任务号", "回款", "结算", "验收条款",
]


def redact_text(text: str) -> str:
    """对外版脱敏：替换内部系统名/编号。"""
    replacements = {
        "ONES": "项目管理系统",
        "OA": "办公系统",
        "BDMS": "合同管理系统",
        "GraphQL": "接口",
        "harbor": "镜像仓库",
        "SSXM": "项目",
        "内部任务号": "任务编号",
        "回款": "付款",
        "结算": "费用",
        "验收条款": "验收约定",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def format_number_table(data: dict, title: str) -> str:
    """格式化数字表格。"""
    lines = [f"### {title}\n"]
    lines.append("| 类别 | 数量 | 已完成 | 在途 | 未开始 |")
    lines.append("|---|--:|--:|--:|--:|")
    for key, vals in sorted(data.items(), key=lambda x: -x[1]["total"]):
        lines.append(
            f"| {key} | {vals['total']} | {vals['done']} | "
            f"{vals['in_progress']} | {vals['to_do']} |"
        )
    total_all = sum(v["total"] for v in data.values())
    done_all = sum(v["done"] for v in data.values())
    wip_all = sum(v["in_progress"] for v in data.values())
    lines.append(f"| **合计** | **{total_all}** | **{done_all}** | **{wip_all}** | — |")
    return "\n".join(lines)


def render_internal(data: dict) -> str:
    """渲染内部版报告（7 章）。"""
    period = data.get("period", {})
    by_cat = data.get("byCategory", {})
    by_prod = data.get("byProduct", {})
    by_period = data.get("byPeriod", {})
    detail = data.get("detail", [])
    goal_matrix = data.get("goalMatrix", [])
    in_progress = data.get("inProgressItems", [])
    contracts = data.get("contracts", [])

    total_work = len(detail)
    done_work = sum(1 for i in detail if i.get("statusCategory") == "done")
    wip_work = sum(1 for i in detail if i.get("statusCategory") == "in_progress")

    lines = []
    lines.append(f"# 项目工作汇报（内部版）\n")
    lines.append(f"**统计周期：** {period.get('start', '')} ~ {period.get('end', '')}\n")
    lines.append(f"**实际交付：** {total_work} 项，已完成 {done_work} 项，在途 {wip_work} 项\n")
    lines.append(f"**完成率：** {done_work/total_work*100:.0f}%\n" if total_work else "")

    # 一、服务概览
    lines.append("\n## 一、服务概览\n")
    lines.append(format_number_table(by_cat, "按工作类别"))
    lines.append("")
    lines.append(format_number_table(by_prod, "按产品方向"))
    lines.append("")
    lines.append(format_number_table(by_period, "按季度"))
    lines.append("")

    # 二、涉及合同清单
    lines.append("\n## 二、涉及合同清单\n")
    if contracts:
        lines.append("| 序号 | 合同编号 | 合同名称 | 服务期 |")
        lines.append("|--:|---|---|---|")
        for idx, c in enumerate(contracts, 1):
            name = c.get("officialName") or c.get("projectName") or "【缺失】"
            lines.append(
                f"| {idx} | {c.get('contractNo', '')} | {name} | "
                f"{c.get('serviceStart', '')} ~ {c.get('serviceEnd', '')} |"
            )
    else:
        lines.append("> 合同台账未提供，略。")
    lines.append("")

    # 三、交付明细
    lines.append(f"\n## 三、交付明细（共 {total_work} 项）\n")
    lines.append("| 日期 | 合同编号 | 产品方向 | 工作类别 | 事项 | 状态 |")
    lines.append("|---|---|---|---|---|---|")
    for item in detail:
        status_label = {"done": "已完成", "in_progress": "在途", "to_do": "未开始"}.get(
            item.get("statusCategory"), "未知"
        )
        lines.append(
            f"| {item.get('createTime', '')[:10]} | {item.get('contractNo', '') or '—'} | "
            f"{item.get('productDirection', '')} | {item.get('issueType', '')} | "
            f"{item.get('name', '')} | {status_label} |"
        )
    lines.append("")

    # 四、在推进事项与方案
    lines.append("\n## 四、在推进事项与方案\n")
    if in_progress:
        for g in in_progress:
            lines.append(f"### {g['direction']}（{g['count']} 项在途）\n")
            for item in g["items"]:
                lines.append(f"- #{item.get('number')} {item.get('name', '')} — 在途")
            lines.append("")
    else:
        lines.append("> 无在途事项。\n")

    # 五、交付价值与目标实现
    lines.append("\n## 五、交付价值与目标实现\n")
    lines.append("| 方向 | 目标实现状态 | 完成/总量 |")
    lines.append("|---|---|---|")
    for g in goal_matrix:
        lines.append(
            f"| {g['direction']} | {g['realizationLevel']} | "
            f"{g['evidence']['workDone']}/{g['evidence']['workTotal']} |"
        )
    lines.append("")

    # 六、关键节点
    lines.append("\n## 六、关键节点\n")
    lines.append("> 从明细中提取周期内里程碑事件。\n")

    # 七、后续安排
    lines.append("\n## 七、后续安排\n")
    if in_progress:
        for g in in_progress:
            lines.append(f"- {g['direction']}：继续推进 {g['count']} 项在途事项")
    else:
        lines.append("- 持续保障各方向服务稳定运行")
    lines.append("")

    return "\n".join(lines)


def render_external(data: dict) -> str:
    """渲染对外版报告（脱敏）。"""
    text = render_internal(data)
    # 脱敏
    text = redact_text(text)
    # 替换标题
    text = text.replace("（内部版）", "（对外版）")
    # 移除内部溯源信息
    text = re.sub(r'> 合同台账未提供.*\n?', '', text)
    return text


def main():
    parser = argparse.ArgumentParser(description="渲染汇报材料")
    parser.add_argument("--audience", choices=["internal", "external"],
                        default="internal", help="受众")
    parser.add_argument("--output", "-o", help="输出文件路径")
    parser.add_argument("--docx", action="store_true", help="导出 docx")
    args = parser.parse_args()

    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"Invalid JSON: {e}"}))
        sys.exit(2)

    data["audience"] = args.audience

    if args.audience == "external":
        report = render_external(data)
    else:
        report = render_internal(data)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"[INFO] 报告已写入: {args.output}", file=sys.stderr)
    else:
        print(report)

    if args.docx:
        try:
            from docx import Document
            doc = Document()
            for line in report.split("\n"):
                if line.startswith("# "):
                    doc.add_heading(line[2:], level=1)
                elif line.startswith("## "):
                    doc.add_heading(line[3:], level=2)
                elif line.startswith("### "):
                    doc.add_heading(line[4:], level=3)
                elif line.startswith("|"):
                    # 简化：表格行作为文本
                    doc.add_paragraph(line)
                else:
                    doc.add_paragraph(line)
            docx_path = (args.output or "report").rsplit(".", 1)[0] + ".docx"
            doc.save(docx_path)
            print(f"[INFO] docx 已导出: {docx_path}", file=sys.stderr)
        except ImportError:
            print("[WARN] python-docx 未安装，跳过 docx 导出", file=sys.stderr)


if __name__ == "__main__":
    main()
