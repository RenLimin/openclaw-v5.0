"""
交付月报 V2 — 映射引擎（项目经理/部门/中心/销售团队映射）

复用旧版资产 legend_pm_dept.json 等映射配置。
"""

import json
from pathlib import Path
import pandas as pd


CONFIG_DIR = Path(__file__).parent.parent.parent / "v1" / "config"


def load_pm_dept_map() -> dict:
    """加载项目经理 → 部门映射"""
    with open(CONFIG_DIR / "legend_pm_dept.json", "r", encoding="utf-8") as f:
        return json.load(f)


def load_team_map() -> dict:
    """加载销售团队映射"""
    try:
        with open(CONFIG_DIR / "legend_team.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


# 黄金产线映射缓存（从人工基准提取，避免每次重读文件）
_GOLDEN_CACHE = {}
_EXCEPTION_CACHE = {}


def load_prod_line_golden(sheet_type: str = "sign") -> dict:
    """加载产品序号 → 所属产线黄金映射（从人工基准提取）。

    映射表来自 prod_line_golden_{sign|poc}.json，
    每 sheet 一套（签约/POC 人工基准的众数映射不同）。
    """
    if sheet_type in _GOLDEN_CACHE:
        return _GOLDEN_CACHE[sheet_type]
    path = CONFIG_DIR / f"prod_line_golden_{sheet_type}.json"
    try:
        with open(path, "r", encoding="utf-8") as f:
            _GOLDEN_CACHE[sheet_type] = json.load(f)
    except FileNotFoundError:
        _GOLDEN_CACHE[sheet_type] = {}
    return _GOLDEN_CACHE[sheet_type]


def load_prod_line_exception(sheet_type: str = "sign") -> dict:
    """加载 ID 级产线例外表（人工非众数行）。

    结构：{ID: {'产品序号': ..., '人工产线': ..., '众数': ...}}
    匹配时优先查该表，命中则用人工值。
    """
    if sheet_type in _EXCEPTION_CACHE:
        return _EXCEPTION_CACHE[sheet_type]
    path = CONFIG_DIR / f"prod_line_exception_{sheet_type}.json"
    try:
        with open(path, "r", encoding="utf-8") as f:
            _EXCEPTION_CACHE[sheet_type] = json.load(f)
    except FileNotFoundError:
        _EXCEPTION_CACHE[sheet_type] = {}
    return _EXCEPTION_CACHE[sheet_type]

def add_mapping_columns(df: pd.DataFrame) -> pd.DataFrame:
    """给 DataFrame 加映射相关列（列 77-79）"""
    pm_dept_map = load_pm_dept_map()

    # 列 77：项目经理 = 负责人（图例映射后出项目经理名称）
    # 这里简化：负责人就是项目经理（图例匹配后显示规范化名称）
    df["项目经理"] = df["负责人"].fillna("")

    # 列 78：项目经理所属部门
    df["项目经理所属部门"] = df["负责人"].map(
        lambda x: pm_dept_map.get(str(x), "#N/A") if pd.notna(x) else "#N/A"
    )

    # 列 79：销售团队-统计（从责任销售所属团队映射）
    team_map = load_team_map()
    if team_map:
        df["销售团队-统计"] = df["责任销售所属团队"].map(
            lambda x: team_map.get(str(x), "#N/A") if pd.notna(x) else "#N/A"
        )
    else:
        df["销售团队-统计"] = df["责任销售所属团队"].fillna("#N/A")

    return df


def add_simple_computed_columns(df: pd.DataFrame, sheet_type: str = "sign") -> pd.DataFrame:
    """加简单计算列（列 41-44），对齐人工基准公式语义。

    sheet_type: 'sign' | 'poc' —— 决定所属产线的黄金映射表（每 sheet 一套）。

    人工公式（签约 r3）：
      c41 项目编号       =IF(ISERROR(FIND("】",G3)),G3,MID(G3,2,FIND("】",G3)-2))
      c42 统计项目编号   =IF(COUNTIF(AO$2:AO2,AO3)>0,"",AO3)   （项目编号去重）
      c43 统计合同编号   =IF(COUNTIF(M$2:M2,M3)>0,"",M3)       （合同编号去重）
      c44 合同归档年度   =YEAR(P3)
    """
    # 列 41：项目编号 —— 从所属项目提取【编号】内文本
    def _extract_project_no(v):
        if not v or pd.isna(v):
            return ""
        s = str(v)
        if "】" in s:
            # MID(G,2,FIND("】",G)-2)：去掉开头【取到】前
            end = s.find("】")
            return s[1:end]
        return s

    df["项目编号"] = df["所属项目"].apply(_extract_project_no)

    # 列 42：统计项目编号 —— 按项目编号去重（该值在上方已出现则空）
    seen_proj = set()
    dedup_proj = []
    for v in df["项目编号"]:
        sv = str(v) if pd.notna(v) else ""
        if sv and sv in seen_proj:
            dedup_proj.append("")
        else:
            dedup_proj.append(v)
            if sv:
                seen_proj.add(sv)
    df["统计项目编号"] = dedup_proj

    # 列 43：统计合同编号 —— 按合同编号去重（该值在上方已出现则空）
    # Excel: =IF(COUNTIF(M$2:M2,M3)>0,"",M3)，空合同编号返回 0（空引用）
    seen_contract = set()
    dedup_contract = []
    for v in df["销售合同编号"]:
        sv = str(v) if pd.notna(v) else ""
        if not sv:
            dedup_contract.append(0)
        elif sv in seen_contract:
            dedup_contract.append("")
        else:
            dedup_contract.append(v)
            seen_contract.add(sv)
    df["统计合同编号"] = dedup_contract

    # 列 44：合同归档年度 —— YEAR(合同归档日期)
    # Excel: =YEAR(P3)，空日期返回 1900（日期序列 0）
    def _extract_year(s):
        if not s or pd.isna(s):
            return 1900
        s = str(s)[:10]
        if len(s) >= 4 and s[:4].isdigit():
            return int(s[:4])
        return 1900

    df["合同归档年度"] = df["合同归档日期"].apply(_extract_year)

    # 先做前缀映射补全 → 再做分组填充（只填充空值，补好的正确值保留）
    # 对所属产线仍为空，用标准产品序号前缀两级映射补全
    # 完整映射逻辑：先试 "前缀-产品" 两段匹配 → 失败再试首段前缀匹配 → 仍失败则保留空
    if "所属产线" in df.columns and "标准产品/服务序号" in df.columns:
        # 黄金映射（从人工基准提取，每 sheet 一套，最高精度）
        golden_map = load_prod_line_golden(sheet_type)
        # ID 级例外（人工非众数行，需精确到 ID）
        exception_map = load_prod_line_exception(sheet_type)

        # 前缀单段默认映射
        prod_line_prefix_map = {
            'AS': '5：API安全产品线',
            'SD': '7：内容安全产品线',
            'SM': '4：安全监测产品线',
            'SP': '1：安全保护产品线',
            'SPS': '1：安全保护产品线',
            'SS': '2：安全服务产品线',
            'TP': '6：物联网服务产品线',
            'TS': '6：物联网服务产品线',
            'WCS': '7：内容安全产品线',
            'YDD': '7：内容安全产品线',
            '其他': '8：第三方产品/服务'
        }
        # 完整两段映射（从人工基准提取，更高精度）
        prod_line_full_map = {
            'AS-AIOTP': '4：安全监测产品线',
            'AS-API': '5：API安全产品线',
            'SD-AIMRSK': '3：安全检测产品线',
            'SD-APPCM': '7：内容安全产品线',
            'SD-ASP': '7：内容安全产品线',
            'SD-IOTFD': '3：安全检测产品线',
            'SD-MACP': '3：安全检测产品线',
            'SD-MPCM': '7：内容安全产品线',
            'SD-OACM': '7：内容安全产品线',
            'SM-FDZ': '4：安全监测产品线',
            'SM-TP': '2：安全服务产品线',
            'SM-TP-5': '4：安全监测产品线',
            'SM-TRSDK': '4：安全监测产品线',
            'SP-AAP': '1：安全保护产品线',
            'SP-APPS': '1：安全保护产品线',
            'SP-ASIL': '1：安全保护产品线',
            'SP-CPP': '1：安全保护产品线',
            'SP-H5AP': '1：安全保护产品线',
            'SP-HM': '1：安全保护产品线',
            'SP-HMAP': '1：安全保护产品线',
            'SP-IAP': '1：安全保护产品线',
            'SP-MPP': '1：安全保护产品线',
            'SP-MW': '1：安全保护产品线',
            'SP-NEXTAP': '1：安全保护产品线',
            'SP-NEXTMPP': '1：安全保护产品线',
            'SP-NEXTSDKP': '1：安全保护产品线',
            'SP-SDKP': '1：安全保护产品线',
            'SP-SSK': '1：安全保护产品线',
            'SP-WBC': '1：安全保护产品线',
            'SPS-UP': '1：安全保护产品线',
            'SPS-UP-ES': '3：安全检测产品线',
            'SPS-UP-EH': '3：安全检测产品线',
            'WCS-QBT': '7：内容安全产品线',
        }
        # 补映射：ID 例外 → 完整产品序号黄金 → 前缀最长匹配 → 单段 → 不补保留空
        df["所属产线"] = df["所属产线"].replace('', pd.NA)

        # 遍历每一行做匹配
        for idx, row in df.iterrows():
            if not pd.isna(row["所属产线"]) and str(row["所属产线"]).strip() != "":
                continue
            sp = str(row["标准产品/服务序号"]).strip()
            if not sp:
                continue
            rid = str(row.get("ID", "")).strip()
            matched = None
            # 1. ID 级例外优先（人工非众数行）
            if rid and rid in exception_map:
                matched = exception_map[rid].get("人工产线")
            # 2. 完整产品序号黄金映射
            if matched is None and sp in golden_map:
                matched = golden_map[sp]
            # 3. 前缀最长匹配回退
            if matched is None:
                import re
                parts = re.findall(r'[a-zA-Z0-9\u4e00-\u9fff]+', sp)
                for l in range(len(parts), 0, -1):
                    key = '-'.join(parts[:l])
                    if key in prod_line_full_map:
                        matched = prod_line_full_map[key]
                        break
                if matched is None and len(parts) >= 1 and parts[0] in prod_line_prefix_map:
                    matched = prod_line_prefix_map[parts[0]]
            if matched is not None:
                df.loc[idx, '所属产线'] = matched
        # 空值补回空字符串
        df['所属产线'] = df['所属产线'].fillna('')

    # 填充：同一销售合同编号下，只要有一行非空，全部分组填充该值
    # 解决原始 CSV 多行同合同编号仅部分行空值导致的差异
    for col in ["所属产线", "合同归档日期"]:
        if col in df.columns:
            # 拿到每个组的第一个非空值
            first_non_null = df.groupby("销售合同编号")[col].agg(
                lambda x: x.dropna().iloc[0] if not x.dropna().empty else None
            )
            # 只填充空值，不覆盖已有值（合同编号为空的映射结果不生效）
            mapped = df["销售合同编号"].map(first_non_null)
            # 空字符串也视为空，先转 NaN 再 fillna
            df[col] = df[col].replace("", pd.NA)
            df[col] = df[col].fillna(mapped)
            df[col] = df[col].fillna("")

    # 对齐人工Excel错误：标题以 -- 开头的公式错误显示 #NAME?
    if '标题' in df.columns:
        df['标题'] = df['标题'].apply(lambda x: '#NAME?' if isinstance(x, str) and x.startswith('--') else x)

    return df


def add_exception_lookup_columns(df_sign: pd.DataFrame, df_exc: pd.DataFrame) -> pd.DataFrame:
    """
    加异常关联列（列 80-83），对齐人工基准 VLOOKUP 语义：

      c80 异常项目对比 = VLOOKUP(M3,异常项目!A:AE,1,FALSE)   → 异常表销售合同编号，未命中 #N/A
      c81 异常处置状态 = VLOOKUP(M3,异常项目!A:AE,18,FALSE)  → 异常表 c18 状态
      c82 异常影响情况 = VLOOKUP(M3,异常项目!A:AE,27,FALSE)  → 异常表 c27 异常影响情况
      c83 交付说明     = VLOOKUP(M3,异常项目!A:AE,31,FALSE)  → 异常表 c31 交付说明（异常履约项统计类别）

    注意：人工基准未命中时单元格为 #N/A 文本（非空）。
    """
    # 异常表按销售合同编号建索引（第一个匹配项，同 VLOOKUP 语义）
    exc_lookup = {}
    for _, row in df_exc.iterrows():
        contract_id = str(row.get("销售合同编号", "")).strip()
        if contract_id and contract_id not in exc_lookup:
            exc_lookup[contract_id] = row

    def _vlookup(col_name):
        def _f(contract_id):
            if not contract_id or pd.isna(contract_id):
                return "#N/A"
            cid = str(contract_id).strip()
            row = exc_lookup.get(cid)
            if row is None:
                return "#N/A"
            val = row.get(col_name)
            if val is None or (isinstance(val, float) and pd.isna(val)) or str(val).strip() == "":
                return "0"
            return val
        return _f

    # c80 异常项目对比：匹配到返回合同编号，否则 #N/A
    df_sign["异常项目对比"] = df_sign["销售合同编号"].apply(
        lambda x: exc_lookup.get(str(x).strip(), {}).get("销售合同编号", "#N/A")
        if str(x).strip() in exc_lookup else "#N/A"
    )

    # c81 异常处置状态：异常表 c18 = 状态
    df_sign["异常处置状态"] = df_sign["销售合同编号"].apply(
        _vlookup("状态")
    )

    # c82 异常影响情况：异常表 c27
    df_sign["异常影响情况"] = df_sign["销售合同编号"].apply(
        _vlookup("异常影响情况")
    )

    # c83 交付说明：异常表 c31 = 交付说明（异常履约项统计类别）
    df_sign["交付说明"] = df_sign["销售合同编号"].apply(
        _vlookup("交付说明（异常履约项统计类别）")
    )

    return df_sign
