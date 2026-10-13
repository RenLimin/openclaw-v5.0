"""
交付月报 V2 — 状态引擎（9 种履约项统计状态判定 + 项目级聚合计数）

对齐人工基准公式语义（202606 黄金基准签约 sheet）：
  c45-52 八状态桶     =IF(LEN(AP3)>0,COUNTIFS($AO:$AO,AP3,$AB:$AB,$AS$2),0)   项目级聚合，首行显示
  c53    履约项合计   =IF(LEN(AP3)>0,COUNTIFS($AO:$AO,AP3),0)                 项目行数，首行显示
  c54    校验         =合计 - SUM(八桶)
  c55    项目统计状态 = 基于桶的项目级文本分类
  c56    履约项统计状态 = IFS 逐行状态分类（1-9 带编号显示名）
  c57-65 九状态列     =IF(LEN(AP3)>0,COUNTIFS($AO:$AO,AP3,BD:BD,$BE$2),0)   项目级聚合，首行显示
  c66    统计校验     = SUM(c57:65) - c53
  c67    项目验收状态 = 基于九状态列的项目级 IFS 分类
"""

from datetime import datetime
import pandas as pd


def determine_status(row: pd.Series, report_date: str) -> str:
    """
    判断单个履约项的统计状态（9 种之一），严格对齐人工 c56 IFS 公式：

      AB=状态 | AF=预估交付完成日期 | AC=履约项异常/变更类型
      AK=预估验收完成日期 | I=项目状态 | K=实际结项日期 | $A$1=报告月末

      1. 状态∈{实施未开始,义务已拆分,实施进行中,实施已完成,交付邮件交接中}
         AND (AF>=$A$1 OR AF空) AND AC≠履约项交付异常 → 1：正常交付
      2. 同集合 AND AF<$A$1 AND AC≠履约项交付异常 → 2：应交未交
      3. 同集合 AND AC=履约项交付异常 → 3：交付异常
      4. 状态∈{交付邮件已归档,验收文件交接中}
         AND (AK>=$A$1 OR AK空) AND AC≠履约项验收异常 → 4：正常验收
      5. 同集合 AND AK<$A$1 AND AC≠履约项验收异常 → 5：应验未验
      6. 同集合 AND AC=履约项验收异常 → 6：验收异常
      7. I≠已归档 AND 状态=验收文件已归档 AND (K>=$A$1 OR K空) → 7：正常服务
      8. I≠已归档 AND 状态=验收文件已归档 AND K<$A$1 → 8：应结未结
      9. I=已归档 → 9：已结项
    """
    status = str(row.get("状态", ""))
    abnormal_type = str(row.get("履约项异常/变更类型", ""))
    # 人工 c56 IFS 公式列引用：AF=c32 预算-预估交付完成日期、AK=c37 预算-预估验收完成日期、K=c11 基线-预估结项日期
    estimated_delivery = row.get("预算-预估交付完成日期", "")
    estimated_acceptance = row.get("预算-预估验收完成日期", "")
    project_status = str(row.get("项目状态", ""))
    actual_finish = row.get("基线-预估结项日期", "")

    report_dt = datetime.strptime(report_date, "%Y-%m-%d")

    def _parse_date(s):
        if not s or pd.isna(s):
            return None
        try:
            return datetime.strptime(str(s)[:10], "%Y-%m-%d")
        except (ValueError, TypeError):
            return None

    est_delivery_dt = _parse_date(estimated_delivery)
    est_acceptance_dt = _parse_date(estimated_acceptance)
    finish_dt = _parse_date(actual_finish)

    status = str(status).strip()
    abnormal_type = str(abnormal_type).strip()
    project_status = str(project_status).strip()

    set_impl = {"实施未开始", "义务已拆分", "实施进行中", "实施已完成", "交付邮件交接中"}
    set_deliv = {"交付邮件已归档", "验收文件交接中"}
    is_deliv_abnormal = abnormal_type == "履约项交付异常"
    is_acc_abnormal = abnormal_type == "履约项验收异常"

    # 人工 c56 IFS 顺序执行：1-6 状态桶优先（不检查 I 项目状态）
    # 1/2/3：实施集合
    if status in set_impl:
        if is_deliv_abnormal:
            return "交付异常"
        if est_delivery_dt is not None and est_delivery_dt < report_dt:
            return "应交未交"
        return "正常交付"
    # 4/5/6：交付集合
    if status in set_deliv:
        if is_acc_abnormal:
            return "验收异常"
        if est_acceptance_dt is not None and est_acceptance_dt < report_dt:
            return "应验未验"
        return "正常验收"
    # 7/8/9：验收文件已归档（按 I 项目状态 + K 结项日期区分）
    if status == "验收文件已归档":
        if project_status == "已归档":
            return "已结项"
        if finish_dt is None or finish_dt >= report_dt:
            return "正常服务"
        return "应结未结"
    # 兜底：没有任何状态匹配 → 返回 None 输出 #N/A
    if project_status == "已归档":
        return "已结项"
    return None


def add_status_columns(df: pd.DataFrame, report_date: str) -> pd.DataFrame:
    """给 DataFrame 加所有状态相关的计算列（列 45-67），项目级聚合对齐人工基准。

    前置：调用前须已通过 add_simple_computed_columns 生成「项目编号」「统计项目编号」。
    """
    status_list = [
        "实施未开始", "义务已拆分", "实施进行中", "实施已完成",
        "交付邮件交接中", "交付邮件已归档", "验收文件交接中", "验收文件已归档"
    ]

    # ── 逐行状态（c56 履约项统计状态）──
    df["_status_text"] = df.apply(
        lambda r: determine_status(r, report_date), axis=1
    )
    STATUS_DISPLAY_MAP = {
        "正常交付": "1：正常交付",
        "应交未交": "2：应交未交",
        "交付异常": "3：交付异常",
        "正常验收": "4：正常验收",
        "应验未验": "5：应验未验",
        "验收异常": "6：验收异常",
        "正常服务": "7：正常服务",
        "应结未结": "8：应结未结",
        "已结项": "9：已结项",
    }
    df["履约项统计状态（即，财报-交付/确收状态）"] = df["_status_text"].map(
        lambda s: "#N/A" if (s is None or (isinstance(s, float) and pd.isna(s))) else STATUS_DISPLAY_MAP.get(s, s)
    )

    # ── 项目级聚合计数 ──
    # 项目键：项目编号（c41）。聚合结果只写在该项目首行（统计项目编号非空行）。
    if "项目编号" not in df.columns:
        df["项目编号"] = df["所属项目"].fillna("")
    proj = df["项目编号"].astype(str).values

    # 计算每行归属的项目首行索引（第一个出现该 项目编号 的位置）
    first_idx = {}
    first_pos = []
    for i, p in enumerate(proj):
        if p not in first_idx:
            first_idx[p] = i
        first_pos.append(first_idx[p])

    # 每个项目的聚合计数
    agg_status_counts = {}   # proj -> Counter(状态)
    agg_state_counts = {}    # proj -> Counter(逐行状态文本)
    from collections import Counter
    for i, p in enumerate(proj):
        agg_status_counts.setdefault(p, Counter())[str(df.iloc[i]["状态"])] += 1
        agg_state_counts.setdefault(p, Counter())[str(df.iloc[i]["_status_text"])] += 1

    # c45-52 八状态桶：仅首行显示项目内该状态行数
    n = len(df)
    for s in status_list:
        col = [0] * n
        for i in range(n):
            if first_pos[i] == i:  # 项目首行
                col[i] = agg_status_counts[proj[i]].get(s, 0)
        df[s] = col

    # c53 履约项合计：项目行数，首行显示
    total_col = [0] * n
    for i in range(n):
        if first_pos[i] == i:
            total_col[i] = sum(agg_status_counts[proj[i]].values())
    df["履约项合计"] = total_col

    # c54 校验 = 合计 - sum(八桶)
    df["校验"] = df["履约项合计"] - df[status_list].sum(axis=1)

    # c55 项目统计状态（仅首行）
    # 人工：IFS(I=已归档→已结项; 合计<=验收文件已归档→已完整验收;
    #           合计<=交付邮件已归档+验收文件交接中+验收文件已归档→可完整验收;
    #           交付邮件已归档+验收文件交接中+验收文件已归档>0→可部分验收; 否则→完全不可验收)
    proj_stat = [""] * n
    for i in range(n):
        if first_pos[i] != i:
            continue
        p = proj[i]
        cnt = agg_status_counts[p]
        total = sum(cnt.values())
        has_archived_proj = any(
            str(df.iloc[j]["项目状态"]) == "已归档"
            for j in range(n) if proj[j] == p
        )
        archived_acc = cnt.get("验收文件已归档", 0)
        mail_archived = cnt.get("交付邮件已归档", 0)
        acc_in_progress = cnt.get("验收文件交接中", 0)
        if has_archived_proj:
            proj_stat[i] = "已结项"
        elif total <= archived_acc:
            proj_stat[i] = "已完整验收"
        elif total <= mail_archived + acc_in_progress + archived_acc:
            proj_stat[i] = "可完整验收"
        elif mail_archived + acc_in_progress + archived_acc > 0:
            proj_stat[i] = "可部分验收"
        else:
            proj_stat[i] = "完全不可验收"
    df["项目统计状态"] = proj_stat

    # c57-65 九状态列：项目内按逐行状态计数，首行显示
    status_names = [
        ("1：正常交付", "正常交付"),
        ("2：应交未交", "应交未交"),
        ("3：交付异常", "交付异常"),
        ("4：正常验收", "正常验收"),
        ("5：应验未验", "应验未验"),
        ("6：验收异常", "验收异常"),
        ("7：正常服务", "正常服务"),
        ("8：应结未结", "应结未结"),
        ("9：已结项", "已结项"),
    ]
    for col_name, status_val in status_names:
        col = [0] * n
        for i in range(n):
            if first_pos[i] == i:
                col[i] = agg_state_counts[proj[i]].get(status_val, 0)
        df[col_name] = col

    # c66 统计校验 = sum(c57-65) - 履约项合计
    df["统计校验"] = df[[name for name, _ in status_names]].sum(axis=1) - df["履约项合计"]

    # c67 项目验收状态（仅首行）
    # 人工：IFS(9已结项==合计→已结项; 6验收异常>0→异常验收;
    #           sum(7正常服务,8应结未结,9已结项)==合计→全部验收;
    #           sum(7,8,9)>0 and <合计→部分验收; 5应验未验>0→应验未验;
    #           sum(1,2,3,4)>0→正常验收)
    acc_status = [""] * n
    for i in range(n):
        if first_pos[i] != i:
            continue
        p = proj[i]
        cnt = agg_state_counts[p]
        total = sum(cnt.values())
        c65 = cnt.get("已结项", 0)
        c62 = cnt.get("验收异常", 0)
        c63_64_65 = cnt.get("正常服务", 0) + cnt.get("应结未结", 0) + cnt.get("已结项", 0)
        c61 = cnt.get("应验未验", 0)
        c57_60 = (cnt.get("正常交付", 0) + cnt.get("应交未交", 0)
                  + cnt.get("交付异常", 0) + cnt.get("正常验收", 0))
        if c65 == total:
            acc_status[i] = "已结项"
        elif c62 > 0:
            acc_status[i] = "异常验收"
        elif c63_64_65 == total:
            acc_status[i] = "全部验收"
        elif 0 < c63_64_65 < total:
            acc_status[i] = "部分验收"
        elif c61 > 0:
            acc_status[i] = "应验未验"
        elif c57_60 > 0:
            acc_status[i] = "正常验收"
        else:
            # 所有 IFS 条件均不满足（如九状态全 0 且无异常）→ 人工公式返回 #N/A
            acc_status[i] = "#N/A"
    df["项目验收状态（即，财报-验收状态）"] = acc_status

    # 清理临时列
    df.drop(columns=["_status_text"], inplace=True)

    return df
