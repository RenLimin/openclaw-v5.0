#!/usr/bin/env python3
"""P1/P2 应答契约确定性校验器（fail-closed）。

用法:
  python3 check_answer_contract.py <report.md> [--strict]

对一份分析报告做结构性校验。退出码:
  0 = 通过（无阻断项）
  1 = 存在阻断项（硬性契约缺失）→ 交付闸门必须拦截

校验两层：
  内容契约（answer-spec-base）：时间戳/降级标注/溯源链/推断可溯。
  格式契约（format-spec-base）：报告型文件须满足统一信封 F1-F5；操作回执豁免。
只做确定性、可复现的结构检查；语义对错不在这里判定。
"""
from __future__ import annotations
import argparse, re, sys, datetime

TS = re.compile(r"【已验证\s*(\d{4}-\d{2}-\d{2})\s*[|｜]\s*([^】]+)】")
DEGRADE = re.compile(r"⚠️[^\n]*(数据源|可能过期|降级)")
TRACE = re.compile(r"(溯源链|数据源\s*→|trace|查询条件)", re.I)
INFER = re.compile(r"【推断】")


def is_report(text: str) -> bool:
    """报告型：存在 H1 且至少 2 个 ## 章节（P1 format-spec §2）。"""
    lines = text.splitlines()
    has_h1 = any(l.startswith("# ") for l in lines)
    h2_count = sum(1 for l in lines if l.startswith("## "))
    return has_h1 and h2_count >= 2


def check_envelope(text: str, errors: list, warnings: list):
    """统一信封 F1-F5（format-spec-base §3.1）。"""
    lines = [l for l in text.splitlines()]
    # F1 H1（is_report 已保证，仍定位）
    # F2 标题下元信息块：前 ~6 行内有 > 引用块，含 生成 + 契约版本 + 归属
    head = lines[:8]
    quote = next((l for l in head if l.lstrip().startswith(">")), None)
    if not quote:
        errors.append("信封F2：H1 下缺少 `>` 元信息块（format-spec §3）")
    else:
        for kw in ("生成", "契约版本", "归属"):
            if kw not in quote:
                errors.append(f"信封F2：元信息块缺关键字「{kw}」（须含 生成/契约版本/归属）")
    # F3 数据基准：元信息块含 数据基准，或正文有时间戳
    has_baseline = (quote and "数据基准" in quote) or TS.search(text)
    if not has_baseline:
        errors.append("信封F3：缺数据基准时间（元信息块「数据基准」或正文【已验证 日期|来源】）")
    # F4 溯源链章节
    if not re.search(r"^##\s*0?\.?\s*溯源链", text, re.M) and not TRACE.search(text):
        errors.append("信封F4：缺 `## 0. 溯源链` 章节")
    # F5 质量信号章节
    if not re.search(r"^##.*质量信号", text, re.M):
        errors.append("信封F5：缺「质量信号」章节")


def check(path: str, strict: bool):
    text = open(path, encoding="utf-8").read()
    today = datetime.date.today()
    errors, warnings = [], []

    report = is_report(text)

    # ── 内容契约 ──
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

    if INFER.search(text) and not re.search(r"【推断】[^】\n]{0,40}(据|由|匹配|推导|因为)", text):
        warnings.append("【推断】未见就近推导依据（P1 §2 要求可追溯）")

    if re.search(r"(非实时|旧报告|历史报告|导出数据|降级)", text) and not DEGRADE.search(text):
        errors.append("使用了非实时/降级数据但缺少 `⚠️ 数据源…可能过期` 标注（P1 §3.4）")

    if not TRACE.search(text) and "ANSWER_CONTRACT_NO_DATA" not in text:
        errors.append("缺少 minimal trace 溯源链（数据源→查询→结论）（P1 §4.5）")

    if re.search(r"(已发送|已通知客户|已对外)", text):
        warnings.append("出现对外动作完成态措辞，确认是否越权（P1 §4.3 / §8）")

    # ── 格式契约（仅报告型）──
    if report:
        check_envelope(text, errors, warnings)

    blocked = bool(errors) or (strict and bool(warnings))

    print(f"应答契约校验：{path}")
    print(f"  类型: {'报告(report)，信封校验启用' if report else '回执(receipt)，信封豁免'}")
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
