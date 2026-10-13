"""
交付月报 V2 — 异常项目 Sheet 构建引擎

对齐人工黄金基准（202606 交付月报）异常项目 Sheet 的 38 列精确顺序：
第 1 行即表头，c37='项目经理团队'（值为项目经理人名）、c38='项目验收状态'。
"""

import pandas as pd


# 人工基准异常项目 Sheet 38 列精确顺序（黄金基准 202606）
EXPECTED_COLS = [
    "销售合同编号",
    "合同归档日期",
    "最终用户名称",
    "客户名称",
    "责任销售（履约项）",
    "责任销售所属团队",
    "负责人",
    "所属项目",
    "项目类型(概览)",
    "合同起始日期",
    "合同结束日期",
    "交付服务开始日期",
    "交付服务结束日期",
    "合同验收条款",
    "验收时点",
    "验收方式",
    "标题",
    "状态",
    "备注",
    "PMO备注",
    "ID",
    "事业部（区域）",
    "事业部负责人",
    "异常报备日期",
    "预估异常处置完成日期",
    "异常归档日期",
    "异常影响情况",
    "异常项目-类别",
    "异常项目-处置方案",
    "异常处置方案-影响",
    "交付说明（异常履约项统计类别）",
    "交付说明（履约项交付情况、合同交付条款）",
    "交付中心反馈",
    "营销中心反馈",
    "项目异常内容",
    "预估金额",
    "项目经理团队",
    "项目验收状态",
]


def _safe_lookup(series: pd.Series, key) -> str:
    """VLOOKUP 语义：按 key 取 series（重复 key 保留第一个），未命中返回 #N/A"""
    if pd.isna(key) or key is None:
        return "#N/A"
    if key not in series.index:
        return "#N/A"
    v = series[key]
    if pd.isna(v):
        return "#N/A"
    return v


def build_exception_df(df_exc_raw: pd.DataFrame, df_sign: pd.DataFrame) -> pd.DataFrame:
    """
    构建异常项目完整 DataFrame（38 列），与人工黄金基准完全一致。

    - 前 36 列：直接取自 ONES 异常处置 CSV 对应字段
    - c37 项目经理团队：从签约表按销售合同编号 VLOOKUP 项目经理（人工该列填人名）
    - c38 项目验收状态：从签约表按销售合同编号 VLOOKUP 项目验收状态

    重复合同编号取第一个（与 Excel VLOOKUP 语义一致）。
    """
    df = df_exc_raw.copy()

    # 从签约表建 VLOOKUP 索引（重复合同编号保留第一个）
    sign_dedup = df_sign.drop_duplicates("销售合同编号", keep="first")
    if "销售合同编号" in sign_dedup.columns and sign_dedup["销售合同编号"].notna().any():
        pm_lookup = sign_dedup.set_index("销售合同编号")["项目经理"]
        status_lookup = sign_dedup.set_index("销售合同编号")["项目验收状态（即，财报-验收状态）"]
    else:
        pm_lookup = pd.Series(dtype=object)
        status_lookup = pd.Series(dtype=object)

    # 构建 38 列
    out = pd.DataFrame(index=df.index)
    for col in EXPECTED_COLS:
        if col == "项目经理团队":
            out[col] = df["销售合同编号"].apply(lambda c: _safe_lookup(pm_lookup, c))
        elif col == "项目验收状态":
            out[col] = df["销售合同编号"].apply(lambda c: _safe_lookup(status_lookup, c))
        elif col == "预估金额":
            # 人工基准该列恒空，不输出 CSV 的预估金额
            out[col] = ""
        elif col in df.columns:
            out[col] = df[col].fillna("")
        else:
            out[col] = ""

    # 严格按人工 38 列顺序
    out = out[EXPECTED_COLS]

    return out
