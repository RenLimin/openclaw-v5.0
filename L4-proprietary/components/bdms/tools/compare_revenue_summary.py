"""确收汇总对比脚本：BDMS 计算结果 vs 手工报表。

用法：
    python3 tools/compare_revenue_summary.py 202606
"""

import sys
from pathlib import Path

# 添加 src 到 path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from bdms.modules.revenue.summary_engine import SummaryEngine


def compare(month: str, manual_path: str = None):
    """对比 BDMS 计算结果与手工报表。"""
    engine = SummaryEngine()

    # 读手工报表
    if manual_path is None:
        from bdms.core.paths import find_revenue_source
        manual_path = find_revenue_source(month)

    if not manual_path or not Path(manual_path).exists():
        print(f"❌ 找不到手工报表: {manual_path}")
        return

    manual = engine.read_manual_summary(manual_path)
    if "error" in manual:
        print(f"❌ 读手工报表失败: {manual['error']}")
        return

    # 计算 BDMS 数据
    mine = engine.compute_summary(month)
    if "error" in mine:
        print(f"❌ 计算失败: {mine['error']}")
        return

    # 构建对比
    print(f"\n{'='*60}")
    print(f"确收汇总对比: {month}")
    print(f"{'='*60}")

    # 手工报表行
    manual_rows = {r.get("period"): r for r in manual.get("rows", []) if r.get("period")}

    # 对比各月
    total_checks = 0
    total_match = 0

    for row in mine["rows"]:
        period = row["period"]
        m = manual_rows.get(period)
        if not m:
            continue

        # 只对比到当前月份
        if period > month:
            continue

        print(f"\n--- {period} ---")

        # 新签合同额
        mine_ns = row.get("new_sign_amount", 0) / 10000  # 元 → 万元
        manual_ns = m.get("new_sign_amount", 0)
        match = abs(mine_ns - manual_ns) < 0.0001
        total_checks += 1
        total_match += match
        print(f"  新签合同额: mine={mine_ns:.6f} manual={manual_ns:.6f} {'✅' if match else '❌'}")

        # 各分类
        for cat, mkey in [("递延", "deferred"), ("新签", "new_sign"), ("合计", "total")]:
            mine_plan = row["categories"][cat]["plan"] / 10000
            mine_actual = row["categories"][cat]["actual"] / 10000
            manual_plan = m.get(mkey, {}).get("plan", 0) or 0
            manual_actual = m.get(mkey, {}).get("actual", 0) or 0

            match_plan = abs(mine_plan - manual_plan) < 0.0001
            match_actual = abs(mine_actual - manual_actual) < 0.0001
            total_checks += 2
            total_match += match_plan + match_actual

            print(f"  {cat} plan: mine={mine_plan:.6f} manual={manual_plan:.6f} {'✅' if match_plan else '❌'}")
            print(f"  {cat} actual: mine={mine_actual:.6f} manual={manual_actual:.6f} {'✅' if match_actual else '❌'}")

    # 小计
    print(f"\n--- 小计 ---")
    for label, key in [("1-6月小计", "h1"), ("全年合计", "full")]:
        subtotal = mine["subtotals"][key]
        # 找手工报表的小计行
        for r in manual.get("rows", []):
            if r.get("_kind") == "subtotal" and label in r.get("label", ""):
                print(f"\n  {label}:")
                mine_ns = subtotal["new_sign_amount"] / 10000
                manual_ns = r["values"][0] if r["values"] else 0
                match = abs(mine_ns - manual_ns) < 0.0001
                total_checks += 1
                total_match += match
                print(f"    新签合同额: mine={mine_ns:.6f} manual={manual_ns:.6f} {'✅' if match else '❌'}")

                for i, (cat, mkey) in enumerate([("新签", "new_sign"), ("递延", "deferred"), ("合计", "total")]):
                    # 手工报表列序：新签在前，递延在后
                    # values[0]=新签合同额, values[1-3]=新签(plan,actual,rate)
                    # values[4-6]=递延(plan,actual,rate), values[7-9]=合计(plan,actual,rate)
                    col_base = 1 + i * 3
                    manual_plan = r["values"][col_base] if len(r["values"]) > col_base else 0
                    manual_actual = r["values"][col_base + 1] if len(r["values"]) > col_base + 1 else 0

                    match_plan = abs(mine_plan - (manual_plan or 0)) < 0.0001
                    match_actual = abs(mine_actual - (manual_actual or 0)) < 0.0001
                    total_checks += 2
                    total_match += match_plan + match_actual

                    print(f"    {cat} plan: mine={mine_plan:.6f} manual={manual_plan:.6f} {'✅' if match_plan else '❌'}")
                    print(f"    {cat} actual: mine={mine_actual:.6f} manual={manual_actual:.6f} {'✅' if match_actual else '❌'}")
                break

    print(f"\n{'='*60}")
    print(f"总计: {total_match}/{total_checks} 项匹配")
    print(f"{'='*60}")

    return total_match == total_checks


if __name__ == "__main__":
    month = sys.argv[1] if len(sys.argv) > 1 else "202606"
    manual_path = sys.argv[2] if len(sys.argv) > 2 else None
    ok = compare(month, manual_path)
    sys.exit(0 if ok else 1)
