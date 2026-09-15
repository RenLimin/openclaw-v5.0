"""
金额工具 — L3 纯函数工具
==========================

纯函数，零副作用。
"""

# 金额大写映射
DIGITS = "零壹贰叁肆伍陆柒捌玖"
UNITS = ["", "拾", "佰", "仟", "万", "拾", "佰", "仟", "亿"]


def amount_to_chinese(amount: float) -> str:
    """金额转中文大写

    支持整数和两位小数。
    示例：amount_to_chinese(12345.67) → "壹万贰仟叁佰肆拾伍元陆角柒分"
    """
    if amount == 0:
        return "零元整"

    if amount < 0:
        return "负" + amount_to_chinese(-amount)

    int_part = int(amount)
    dec_part = round((amount - int_part) * 100)

    # 整数部分
    int_str = str(int_part)
    result = ""
    zero_flag = False

    for i, ch in enumerate(int_str):
        digit = int(ch)
        pos = len(int_str) - 1 - i
        if digit == 0:
            zero_flag = True
        else:
            if zero_flag:
                result += "零"
                zero_flag = False
            result += DIGITS[digit] + UNITS[pos]

    # 处理末尾的 "零"
    if result.endswith("零"):
        result = result[:-1]

    if not result:
        result = "零"

    result += "元"

    # 小数部分
    jiao = dec_part // 10
    fen = dec_part % 10

    if jiao == 0 and fen == 0:
        result += "整"
    else:
        if jiao > 0:
            result += DIGITS[jiao] + "角"
        elif int_part > 0:
            result += "零"
        if fen > 0:
            result += DIGITS[fen] + "分"

    return result
