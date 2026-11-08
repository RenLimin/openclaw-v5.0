#!/usr/bin/env python3
"""aggregate.py — S4 三维汇总与明细

输入 (stdin JSON): normalize_and_classify.py 的输出
  {workItems: WorkItem[], stats, period}

输出 (stdout JSON):
  {
    byCategory: {done, in_progress, to_do, total},
    byProduct: {done, in_progress, to_do, total},
    byPeriod: {done, in_progress, to_do, total},
    detail: [WorkItem sorted by createTime],
    reconciliation: {categoryTotal, productTotal, periodTotal, detailCount, ok}
  }

退出码: 0=成功, 2=对账失败
"""
import json
import sys
from collections import Counter, defaultdict


def aggregate_dimension(items: list, key: str) -> dict:
    """按维度汇总 done/in_progress/to_do/total。"""
    counter = Counter()
    for item in items:
        val = item.get(key, "unknown")
        status = item.get("statusCategory", "unknown")
        counter[(val, status)] += 1

    result = {}
    for (val, status), count in counter.items():
        if val not in result:
            result[val] = {"done": 0, "in_progress": 0, "to_do": 0, "total": 0}
        result[val][status] = count
        result[val]["total"] += count
    return result


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"Invalid JSON: {e}"}))
        sys.exit(2)

    work_items = data.get("workItems", [])
    period = data.get("period", {})

    # 只取 isWork=true 且 inPeriod=true
    active = [w for w in work_items if w.get("isWork") and w.get("inPeriod")]

    # 三维汇总
    by_category = aggregate_dimension(active, "category")
    by_product = aggregate_dimension(active, "productDirection")

    # 按季度
    def get_quarter(iso_time: str) -> str:
        if not iso_time or len(iso_time) < 7:
            return "unknown"
        month = int(iso_time[5:7])
        if month <= 3:
            return "Q1"
        elif month <= 6:
            return "Q2"
        elif month <= 9:
            return "Q3"
        else:
            return "Q4"

    for item in active:
        item["_quarter"] = get_quarter(item.get("createTime", ""))

    by_period = aggregate_dimension(active, "_quarter")

    # 明细排序（按 createTime 升序）
    detail = sorted(active, key=lambda x: x.get("createTime", ""))

    # 对账：各维度 total 必须相等且 = len(detail)
    cat_total = sum(v["total"] for v in by_category.values())
    prod_total = sum(v["total"] for v in by_product.values())
    period_total = sum(v["total"] for v in by_period.values())
    detail_count = len(detail)

    reconciliation = {
        "categoryTotal": cat_total,
        "productTotal": prod_total,
        "periodTotal": period_total,
        "detailCount": detail_count,
        "ok": cat_total == prod_total == period_total == detail_count,
    }

    if not reconciliation["ok"]:
        print(json.dumps({
            "error": "对账失败",
            "reconciliation": reconciliation,
        }, ensure_ascii=False))
        sys.exit(2)

    # done + wip = total 校验
    for dim_name, dim_data in [("category", by_category),
                                ("product", by_product),
                                ("period", by_period)]:
        for key, vals in dim_data.items():
            if vals["done"] + vals["in_progress"] + vals["to_do"] != vals["total"]:
                print(json.dumps({
                    "error": f"{dim_name}.{key} done+wip+todo != total",
                    "values": vals,
                }, ensure_ascii=False))
                sys.exit(2)

    output = {
        "byCategory": by_category,
        "byProduct": by_product,
        "byPeriod": by_period,
        "detail": detail,
        "reconciliation": reconciliation,
        "period": period,
    }
    print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    main()
