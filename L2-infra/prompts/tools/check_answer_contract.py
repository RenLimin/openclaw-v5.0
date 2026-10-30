#!/usr/bin/env python3
"""P1/P2 应答契约确定性校验器（fail-closed）。

用法:
  python3 check_answer_contract.py <report.md> [--strict]

对一份分析报告做结构性校验。退出码:
  0 = 通过（无阻断项）
  1 = 存在阻断项（硬性契约缺失）→ 交付闸门必须拦截
默认 缺时间戳/缺溯源 等关键项即阻断；--strict 下警告也阻断。

只做确定性、可复现的结构检查；语义对错不在这里判定（那是 LLM/人工的事）。
"""
from __future__ import annotations
import argparse, re, sys, datetime

TS = re.compile(r"【已验证\s*(\d{4}-\d{2}-\d{2})\s*[|｜]\s*([^】]+)】")
DEGRADE = re.compile(r"⚠️[^\n]*(数据源|可能过期|降级)")
TRACE = re.compile(r"(溯源链|数据源\s*→|trace|查询条件)", re.I)
CLAIM_MISSING = re.compile(r"【缺失】")
INFER = re.compile(r"【推断】")

def check(path: str, strict: bool):
    text = open(path, encoding="utf-8").read()
    today = datetime.date.today()
    errors, warnings = [], []

    # 1) 至少一条带来源时间戳的【已验证】（纯方法论文档可豁免：含"无数据结论"标记）
    ts_hits = TS.findall(text)
    if not ts_hits and "ANSWER_CONTRACT_NO_DATA" not in text:
        errors.append("无任何 `【已验证 YYYY-MM-DD|来源】` 时间戳标注（P1 §2）")
    for ds, src in ts_hits:
        try:
            age = (today - datetime.date.fromisoformat(ds)).days
            if age > 30:
                warnings.append(f"数据已 {age} 天前（{ds}|{src.strip()}），注意时效（P1 §1.3）")
        except ValueError:
            errors.append(f"非法日期 {ds}")

    # 2) 出现【推断】必须可追溯（粗略：同段或后文出现"据/由/因为/推导/匹配"）
    if INFER.search(text) and not re.search(r"【推断】[^】\n]{0,40}(据|由|匹配|推导|因为)", text):
        warnings.append("【推断】未见就近推导依据（P1 §2 要求可追溯）")

    # 3) 降级信号：出现"旧报告/历史/非实时/导出"等词却无 ⚠️ 标注
    if re.search(r"(非实时|旧报告|历史报告|导出数据|降级)", text) and not DEGRADE.search(text):
        errors.append("使用了非实时/降级数据但缺少 `⚠️ 数据源…可能过期` 标注（P1 §3.4）")

    # 4) 溯源链
    if not TRACE.search(text) and "ANSWER_CONTRACT_NO_DATA" not in text:
        errors.append("缺少 minimal trace 溯源链（数据源→查询→结论）（P1 §4.5）")

    # 5) 副作用边界：报告若含动作建议，应区分"建议"而非"已执行"
    if re.search(r"(已发送|已通知客户|已对外)", text):
        warnings.append("出现对外动作完成态措辞，确认是否越权（P1 §4.3 / §8）")

    blocked = bool(errors) or (strict and bool(warnings))

    print(f"应答契约校验：{path}")
    print(f"  时间戳标注: {len(ts_hits)} 处")
    for e in errors:
        print(f"  ❌ {e}")
    for w in warnings:
        print(f"  ⚠️  {w}")
    if not errors and not warnings:
        print("  ✅ 全部硬性项通过")
    print("结果:", "BLOCK（阻断交付）" if blocked else "PASS")
    return 1 if blocked else 0

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("report")
    ap.add_argument("--strict", action="store_true")
    a = ap.parse_args()
    sys.exit(check(a.report, a.strict))
