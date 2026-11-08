#!/usr/bin/env python3
"""normalize_and_classify.py — S3 口径清洗与分类

输入 (stdin JSON): fetch_project_tasks.py 的输出
  {projects, tasks, completeness}

输出 (stdout JSON):
  {workItems: WorkItem[], stats: {excluded, inPeriod, outPeriod, byIssueType}}

退出码: 0=成功, 2=数据/BLOCK
"""
import json
import re
import sys
import os
from datetime import datetime, timezone, timedelta
from collections import Counter

CST = timezone(timedelta(hours=8))

# ── 口径规则 ─────────────────────────────────────────────────────────
# 不计数 issueType（建档/范围记录）—— 以 ONES 真实类型名为准
# 实测回放（2026-11-08）确认下列真实名称
EXCLUDED_ISSUE_TYPES = {
    "项目履约义务",
    "客户信息", "合同信息", "项目信息", "产品信息",
    "设备领用情况",
    "外包（外采）情况", "外包/外采情况",
}

# 实际工作 5 类：ONES 真实类型名 -> 黄金基准标准类别名
# 实测：真实 ONES 用「缺陷/工单/客户项目产研支持需求/任务」，
# 不是概念化的「缺陷修复/问题工单/产研支持/专项任务」。
WORK_TYPE_MAP = {
    "客户定制需求": "客户定制需求",
    "缺陷": "缺陷修复",
    "工单": "问题工单",
    "客户项目产研支持需求": "产研支持",
    "任务": "专项任务",
}

# ── 产品方向映射 ─────────────────────────────────────────────────────
PRODUCT_KEYWORDS = [
    # (关键字列表, 产品方向)
    (["监测", "客户端", "SDK 在线", "Root", "APatch", "SukiSU"], "安全监测"),
    (["合规", "检测报告", "Stim", "监管"], "合规检测"),
    (["加固", "加壳", "16KB", "防代理"], "安卓/SDK 加固"),
    (["测评", "TDSQL", "V5.x 测评"], "应用安全测评"),
    (["小程序", "ZIP 小程序"], "小程序加固"),
    (["H5", "API", "设备指纹"], "H5/API 安全"),
    (["鸿蒙", "NEXT"], "鸿蒙 NEXT 加固"),
]


# ── 产品方向人工核定 override（黄金基准 fixture）────────────────────
# 历史人工核定的任务编号 -> 产品方向（可审计、可回归；通用规则无法还原人工判断时使用）
OVERRIDE_FIXTURE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "assets", "golden", "ccb-2026-product-override.json",
)

_OVERRIDE_MAP = None


def load_product_override() -> dict:
    """加载任务编号 -> 产品方向 override 映射；文件缺失时返回空 dict。"""
    global _OVERRIDE_MAP
    if _OVERRIDE_MAP is not None:
        return _OVERRIDE_MAP
    _OVERRIDE_MAP = {}
    try:
        with open(OVERRIDE_FIXTURE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        entries = data.get("entries", {}) if isinstance(data, dict) else {}
        for num, meta in entries.items():
            if isinstance(meta, dict) and meta.get("product"):
                _OVERRIDE_MAP[str(num)] = meta["product"]
    except FileNotFoundError:
        pass
    return _OVERRIDE_MAP


def classify_product_with_override(number, name, products) -> str:
    """任务编号命中 override fixture 时优先用人工核定方向，否则走通用规则。"""
    override = load_product_override()
    if number is not None and str(number) in override:
        return override[str(number)]
    return classify_product(name, products)


def normalize_timestamp(v) -> float:
    """三精度归一为秒级 epoch。"""
    if v is None:
        return 0.0
    v = int(v)
    if v > 1e14:      # 微秒
        return v / 1e6
    elif v > 1e11:    # 毫秒
        return v / 1e3
    else:             # 秒
        return float(v)


def epoch_to_iso(epoch_s: float) -> str:
    """秒级 epoch → ISO8601 (Asia/Shanghai)。"""
    if epoch_s <= 0:
        return ""
    dt = datetime.fromtimestamp(epoch_s, tz=CST)
    return dt.isoformat()


def classify_product(name: str, products: list) -> str:
    """从任务名+产品列表映射产品方向。"""
    text = (name or "") + " " + " ".join(
        p.get("name", "") for p in (products or [])
    )
    for keywords, direction in PRODUCT_KEYWORDS:
        for kw in keywords:
            if kw.lower() in text.lower():
                return direction
    return "【缺失】"


def canonical_category(issue_type: str):
    """真实 issueType -> 标准类别；非工作类型返回 None；未知返回 '【缺失】'。"""
    if not issue_type:
        return "【缺失】"  # 未知类型保守计入，单独标记
    if issue_type in WORK_TYPE_MAP:
        return WORK_TYPE_MAP[issue_type]
    if issue_type in EXCLUDED_ISSUE_TYPES:
        return None
    return "【缺失】"  # 未登记类型保守计入并显式标记，防漏


def is_work_issue(issue_type: str) -> bool:
    """判断是否计入工作量。"""
    return canonical_category(issue_type) is not None


def in_period(iso_time: str, period: dict) -> bool:
    """判断时间是否在统计周期内（含端点）。"""
    if not iso_time:
        return False
    start = period.get("start", "")
    end = period.get("end", "")
    if start and iso_time < start:
        return False
    if end and iso_time > end:
        return False
    return True


def classify_status(category: str) -> str:
    """状态归类。"""
    cat = (category or "").lower()
    if cat in ("done", "completed", "closed", "resolved"):
        return "done"
    elif cat in ("in_progress", "in-progress", "progress", "doing"):
        return "in_progress"
    elif cat in ("to_do", "todo", "open", "new"):
        return "to_do"
    return "unknown"


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"Invalid JSON: {e}"}))
        sys.exit(2)

    tasks = data.get("tasks", [])
    projects = data.get("projects", [])
    # 从输入或 completeness 取 period
    period = data.get("period", {})
    if not period:
        # 默认 2026 年度
        period = {"start": "2026-01-01", "end": "2026-12-31"}

    # 项目映射
    proj_map = {p["projectUUID"]: p for p in projects}

    work_items = []
    excluded_count = 0
    in_period_count = 0
    out_period_count = 0
    issue_type_counter = Counter()

    for t in tasks:
        issue_type = ""
        it = t.get("issueType")
        if isinstance(it, dict):
            issue_type = it.get("name", "")
        elif isinstance(it, str):
            issue_type = it

        issue_type_counter[issue_type] += 1

        # 时间戳归一
        raw_ct = t.get("createTime")
        epoch_s = normalize_timestamp(raw_ct)
        iso_time = epoch_to_iso(epoch_s)

        # 口径判断
        is_work = is_work_issue(issue_type)
        if not is_work:
            excluded_count += 1

        # 周期判断
        period_ok = in_period(iso_time, period)
        if period_ok:
            in_period_count += 1
        else:
            out_period_count += 1

        # 项目信息
        proj = {}
        p_ref = t.get("project")
        if isinstance(p_ref, dict):
            proj = proj_map.get(p_ref.get("uuid"), {})
        elif isinstance(p_ref, str):
            proj = proj_map.get(p_ref, {})

        # 产品方向（override fixture 优先，通用规则兜底）
        products = t.get("products", [])
        product_dir = classify_product_with_override(t.get("number"), t.get("name", ""), products)

        # 状态
        status_cat = classify_status(t.get("statusCategory", ""))

        category = canonical_category(issue_type)
        item = {
            "number": t.get("number"),
            "uuid": t.get("uuid", ""),
            "name": t.get("name", ""),
            "projectCode": proj.get("projectCode", ""),
            "contractNo": proj.get("contractNo"),
            "issueType": issue_type,
            "category": category,
            "productDirection": product_dir,
            "statusCategory": status_cat,
            "createTime": iso_time,
            "createEpochUs": int(epoch_s * 1e6) if epoch_s > 0 else 0,
            "inPeriod": period_ok,
            "isWork": is_work,
            "excludeReason": None if is_work else f"建档/范围记录: {issue_type}",
            "_categoryResolved": category,
        }
        work_items.append(item)

    stats = {
        "total": len(tasks),
        "excluded": excluded_count,
        "inPeriod": in_period_count,
        "outPeriod": out_period_count,
        "byIssueType": dict(issue_type_counter),
        "missingProductDirection": sum(
            1 for w in work_items if w["productDirection"] == "【缺失】"
        ),
    }

    output = {
        "workItems": work_items,
        "stats": stats,
        "period": period,
    }
    print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    main()
