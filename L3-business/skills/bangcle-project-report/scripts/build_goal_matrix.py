#!/usr/bin/env python3
"""build_goal_matrix.py — S5 目标闭环与在途归并

输入 (stdin JSON): aggregate.py 的输出 + 可选 contracts
  {
    byCategory, byProduct, byPeriod, detail, reconciliation, period,
    contracts: [{contractNo, officialName, serviceStart, serviceEnd, ...}]  // 可选
  }

输出 (stdout JSON):
  {
    goalMatrix: [GoalRealization],
    inProgressItems: [{direction, items: [...], summary}],
    contracts: [...]
  }

退出码: 0=成功, 2=数据/BLOCK
"""
import json
import sys
from collections import defaultdict


# ── 目标实现等级映射规则 ─────────────────────────────────────────────
REALIZATION_LEVELS = {
    "已实现": "维保方向 done/total 全覆盖且工单闭环",
    "基本实现": "完成、仅 1 项集成类在途",
    "部分实现/推进中": "研发完成、系统测试多在途",
    "能力已落地": "采购类 部署+授权 done，验收手续在途",
    "能力已建成": "采购类 部署+授权 done，验收完成",
    "往年已达成": "能力建于 prior 周期、本周期仅维护",
}

# 维保类方向（evidence 取服务事项 done/total）
MAINTENANCE_DIRECTIONS = {
    "安全监测", "合规检测", "安卓/SDK 加固",
    "应用安全测评", "小程序加固", "H5/API 安全",
}

# 采购新建类方向（evidence 取部署/授权履约完成记录）
PROCUREMENT_DIRECTIONS = {
    "鸿蒙 NEXT 加固",
}


def classify_realization(direction: str, done: int, total: int,
                         in_progress_items: list) -> str:
    """根据规则映射目标实现等级（不接受自由文本）。"""
    if total == 0:
        return "往年已达成" if direction in PROCUREMENT_DIRECTIONS else "部分实现/推进中"

    ratio = done / total if total > 0 else 0

    if direction in PROCUREMENT_DIRECTIONS:
        if done >= 2 and not in_progress_items:
            return "能力已建成"
        elif done >= 1:
            return "能力已落地"
        else:
            return "部分实现/推进中"

    # 维保类
    if ratio >= 1.0 and not in_progress_items:
        return "已实现"
    elif ratio >= 0.9 and len(in_progress_items) <= 1:
        return "基本实现"
    else:
        return "部分实现/推进中"


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"Invalid JSON: {e}"}))
        sys.exit(2)

    detail = data.get("detail", [])
    contracts = data.get("contracts", [])
    by_product = data.get("byProduct", {})

    # 按产品方向归集明细
    direction_items = defaultdict(list)
    for item in detail:
        direction_items[item.get("productDirection", "unknown")].append(item)

    # 构建目标矩阵
    goal_matrix = []
    in_progress_groups = defaultdict(list)

    for direction, items in sorted(direction_items.items()):
        done = sum(1 for i in items if i.get("statusCategory") == "done")
        in_progress = [i for i in items if i.get("statusCategory") == "in_progress"]
        total = len(items)

        level = classify_realization(direction, done, total, in_progress)

        # 合同列表
        contract_nos = list(set(
            i.get("contractNo") for i in items if i.get("contractNo")
        ))

        goal = {
            "direction": direction,
            "contracts": contract_nos,
            "goal": f"{direction}方向目标",
            "support": f"本周期完成 {done}/{total} 项",
            "realizationLevel": level,
            "evidence": {
                "workDone": done,
                "workTotal": total,
                "deliveryRecords": [
                    f"#{i.get('number')} {i.get('name', '')[:50]}"
                    for i in items if i.get("statusCategory") == "done"
                ],
            },
        }
        goal_matrix.append(goal)

        # 在途归并
        if in_progress:
            in_progress_groups[direction].extend(in_progress)

    # 在途归并输出
    in_progress_summary = []
    for direction, items in sorted(in_progress_groups.items()):
        in_progress_summary.append({
            "direction": direction,
            "count": len(items),
            "items": [
                {
                    "number": i.get("number"),
                    "name": i.get("name", ""),
                    "status": i.get("statusCategory"),
                    "createTime": i.get("createTime"),
                }
                for i in items
            ],
            "summary": f"{direction}方向 {len(items)} 项在途",
        })

    # 透传 aggregate 阶段的汇总数据，供 render_report 使用
    output = dict(data)  # 保留 byCategory/byProduct/byPeriod/detail/period 等
    output["goalMatrix"] = goal_matrix
    output["inProgressItems"] = in_progress_summary
    output["contracts"] = contracts
    print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    main()
