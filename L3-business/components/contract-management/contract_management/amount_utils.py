"""金额工具 — L3 纯函数工具（单一实现，修复版）。

纯函数，零副作用。

实现说明（2026-11-01 修订）：
- 基线：skills/contract-approval/scripts/contract_gen.py 的修复版实现，
  已修复旧版 core 的"漏万"bug（100000 → 壹拾万元整）与段间补零问题；
- 合并旧 core 版负数处理（负数 → 负 + 递归），保持 L4 既有契约；
- 依据 DESIGN-DETAIL-contract-management-v1.0 §1.4 单一实现原则，
  本实现为 L3/L4 唯一权威实现，消除 skills/ 与 components/ 重复。
"""

DIGITS = "零壹贰叁肆伍陆柒捌玖"
UNITS = ["", "拾", "佰", "仟", "万", "拾", "佰", "仟", "亿"]


def _four_digits_to_cn(s: str) -> str:
    """4 位数字转中文（仟佰拾个），处理中间零。"""
    result = ""
    zero_flag = False
    units4 = ["", "拾", "佰", "仟"]
    for i, ch in enumerate(s):
        digit = int(ch)
        pos = len(s) - 1 - i
        if digit == 0:
            zero_flag = True
        else:
            if zero_flag:
                result += "零"
                zero_flag = False
            result += DIGITS[digit] + units4[pos]
    return result


def amount_to_chinese(amount: float) -> str:
    """金额转中文大写。

    支持整数和两位小数，支持负数、亿级。
    示例：amount_to_chinese(12345.67) → "壹万贰仟叁佰肆拾伍元陆角柒分"
          amount_to_chinese(100000)  → "壹拾万元整"（修复版，不漏"万"）
    """
    if amount == 0:
        return "零元整"
    if amount < 0:
        return "负" + amount_to_chinese(-amount)

    int_part = int(amount)
    dec_part = round((amount - int_part) * 100)

    # 整数部分：按万分段处理（个级、万级、亿级）
    int_str = str(int_part)
    sections = []
    remaining = int_str
    while len(remaining) > 4:
        sections.append(remaining[-4:])
        remaining = remaining[:-4]
    sections.append(remaining)
    sections.reverse()  # 从高位到低位

    section_units = ["", "万", "亿"]
    result = ""
    zero_between = False  # 段之间是否需要补零

    for idx, sec in enumerate(sections):
        sec_num = int(sec)
        sec_unit = section_units[len(sections) - 1 - idx]

        if sec_num == 0:
            # 整段为零，标记后续段可能需要补零
            if result:
                zero_between = True
            continue

        sec_cn = _four_digits_to_cn(sec)
        if zero_between:
            if sec_cn.startswith("零"):
                result += sec_cn
            else:
                result += "零" + sec_cn
            zero_between = False
        else:
            result += sec_cn
        result += sec_unit

    # 小数部分
    jiao = dec_part // 10
    fen = dec_part % 10

    if int_part == 0:
        result = ""
    else:
        result += "元"

    if jiao == 0 and fen == 0:
        result += "整"
    else:
        if jiao > 0:
            result += DIGITS[jiao] + "角"
        elif int_part > 0 and fen > 0:
            result += "零"
        if fen > 0:
            result += DIGITS[fen] + "分"

    return result
