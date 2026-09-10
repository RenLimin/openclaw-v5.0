"""
学习规划引擎 — 生成 16 周 CISSP 学习计划

输入：
  - 8 域权重（来自 domains.json）
  - 每日可用时长（工作日 1h / 周末 3h，可配置）
  - 开始日期
  - 总周数（默认 16）

输出：
  - 按日粒度的学习计划：每天学习哪些域、哪些主项、预计时长
  - 计划以 JSON 存储，支持 CLI 查询

动态调整：
  - 某域正确率 < 60% 时，自动追加 20% 复习时间
  - 自动识别周末（周六日）并调增学习量
"""

import json
import os
from datetime import date, timedelta
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def load_domains():
    """加载 8 域结构"""
    with open(DATA_DIR / "domains.json", encoding="utf-8") as f:
        return json.load(f)["domains"]


def load_progress():
    """加载学习进度"""
    path = DATA_DIR / "progress.json"
    if not path.exists():
        return {"domain_progress": {}}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def total_study_hours(start_date, weeks=16, weekday_hours=1, weekend_hours=3):
    """计算总学习时长（小时）"""
    total = 0
    d = start_date
    for _ in range(weeks * 7):
        if d.weekday() >= 5:  # 周六=5, 周日=6
            total += weekend_hours
        else:
            total += weekday_hours
        d += timedelta(days=1)
    return total


def generate_plan(start_date=None, weeks=16, weekday_hours=1, weekend_hours=3):
    """
    生成 16 周学习计划。

    算法：
    1. 根据 8 域权重分配总时长
    2. 每个域按主项数分配到主项
    3. 按日期逐日填充：工作日 N 小时，周末 3N 小时
    4. 每日本地按"主项"为单位安排，保证每日覆盖 1-2 个主项
    5. 动态调整：根据 progress 中的正确率，给薄弱域追加 20% 时间
    """
    if start_date is None:
        start_date = date.today()

    domains = load_domains()
    progress = load_progress()
    domain_progress = progress.get("domain_progress", {})

    # 1. 计算总时长
    total_hours = total_study_hours(start_date, weeks, weekday_hours, weekend_hours)

    # 2. 按权重分配到各域，动态调整
    domain_hours = {}
    total_weight = sum(d["weight"] for d in domains)
    for d in domains:
        base = total_hours * d["weight"] / total_weight
        # 动态调整：正确率 < 60% 的域加 20%
        dp = domain_progress.get(str(d["id"]), {})
        correct_rate = dp.get("correct_rate", 0.7)  # 默认 70%（假设还不错）
        if correct_rate < 0.6:
            base *= 1.2
        domain_hours[d["id"]] = base

    # 3. 域内按主项数分配到主项
    # 构造主项列表，每个主项有预估小时数
    main_item_hours = {}  # main_topic_id -> hours
    for d in domains:
        d_hours = domain_hours[d["id"]]
        n_mains = len(d["main_topics"])
        if n_mains == 0:
            continue
        per_main = d_hours / n_mains
        for m in d["main_topics"]:
            main_item_hours[m["id"]] = per_main

    # 4. 逐日填充计划
    plan = {
        "meta": {
            "start_date": start_date.isoformat(),
            "total_weeks": weeks,
            "weekday_hours": weekday_hours,
            "weekend_hours": weekend_hours,
            "total_hours": round(total_hours, 1),
            "generated_at": date.today().isoformat()
        },
        "weeks": [],
        "days": {}
    }

    # 主项队列：按域顺序 + 主项顺序
    main_queue = []
    for d in domains:
        for m in d["main_topics"]:
            main_queue.append({
                "domain_id": d["id"],
                "domain_name": d["name"],
                "main_id": m["id"],
                "main_name": m["name"],
                "remaining_hours": main_item_hours[m["id"]],
                "sub_topics": m["sub_topics"]
            })

    current_date = start_date
    for week_idx in range(weeks):
        week_days = []
        for day_idx in range(7):
            is_weekend = current_date.weekday() >= 5
            day_hours = weekend_hours if is_weekend else weekday_hours
            day_str = current_date.isoformat()

            # 从队列里取主项，填满今日时长
            today_items = []
            remaining = day_hours

            while remaining > 0 and main_queue:
                item = main_queue[0]
                if item["remaining_hours"] <= 0:
                    main_queue.pop(0)
                    continue

                # 取多少时间给这个主项
                take = min(remaining, item["remaining_hours"])
                # 至少学 0.25h 才有意义
                if take < 0.25 and remaining >= 0.25 and len(main_queue) > 1:
                    # 跳过，试下一个
                    main_queue.pop(0)
                    main_queue.append(item)
                    if len([x for x in main_queue if x['remaining_hours'] >= 0.25]) == 0:
                        break
                    continue

                today_items.append({
                    "domain_id": item["domain_id"],
                    "domain_name": item["domain_name"],
                    "main_id": item["main_id"],
                    "main_name": item["main_name"],
                    "hours": round(take, 2),
                    "sub_topics_sample": item["sub_topics"][:3]  # 预览前 3 个子项
                })

                item["remaining_hours"] -= take
                remaining -= take

                if item["remaining_hours"] < 0.1:  # 完成
                    main_queue.pop(0)

            day_plan = {
                "date": day_str,
                "day_of_week": current_date.strftime("%A"),
                "is_weekend": is_weekend,
                "planned_hours": round(day_hours, 1),
                "actual_hours": 0,
                "items": today_items,
                "completed": False
            }
            plan["days"][day_str] = day_plan
            week_days.append(day_plan)
            current_date += timedelta(days=1)

        plan["weeks"].append({
            "week": week_idx + 1,
            "start": week_days[0]["date"],
            "end": week_days[-1]["date"],
            "days": [d["date"] for d in week_days]
        })

    return plan


def save_plan(plan, path=None):
    """保存计划到 progress.json"""
    if path is None:
        path = DATA_DIR / "progress.json"
    with open(path, encoding="utf-8") as f:
        progress = json.load(f)
    progress["plan"] = plan["meta"]
    progress["plan_days"] = plan["days"]
    progress["plan_weeks"] = plan["weeks"]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)


def get_plan():
    """获取已保存的计划；没有则生成新的"""
    path = DATA_DIR / "progress.json"
    with open(path, encoding="utf-8") as f:
        progress = json.load(f)
    if "plan_days" in progress and progress["plan_days"]:
        return {
            "meta": progress.get("plan", {}),
            "days": progress["plan_days"],
            "weeks": progress.get("plan_weeks", [])
        }
    return None


def get_day_plan(date_str=None):
    """获取某一天的学习计划"""
    if date_str is None:
        date_str = date.today().isoformat()
    plan = get_plan()
    if plan is None:
        return None
    return plan["days"].get(date_str)


if __name__ == "__main__":
    plan = generate_plan()
    print(f"生成 {plan['meta']['total_weeks']} 周计划")
    print(f"总时长: {plan['meta']['total_hours']}h")
    print(f"开始日期: {plan['meta']['start_date']}")
    # 打印第一周
    for w in plan["weeks"][:1]:
        print(f"\n第 {w['week']} 周 ({w['start']} ~ {w['end']})")
        for d_str in w["days"][:3]:
            d = plan["days"][d_str]
            items = ", ".join(f"{i['domain_name']}/{i['main_name']}({i['hours']}h)" for i in d["items"])
            print(f"  {d['date']} {d['day_of_week']} [{d['planned_hours']}h] {items}")
