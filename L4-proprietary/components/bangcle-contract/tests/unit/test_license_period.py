"""license_period 授权期限提取单测（D1 修复回归）。

数据源：权威源 ``L4-proprietary/skills/ones-browser-export/scripts/oa_workflow_ones.py``
纯函数离线测试，不触网、不需要 Chrome。
真实语料取自 2026-11-19 实查：SSXM-2026-0810-2066 / SSXM-2026-0624-1641 的【云端】任务描述。
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

COMPONENT_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = COMPONENT_ROOT.parents[2]
SCRIPT = (
    REPO_ROOT / "L4-proprietary" / "skills" / "ones-browser-export"
    / "scripts" / "oa_workflow_ones.py"
)


def _load():
    if not SCRIPT.exists():
        pytest.skip("权威源脚本不存在: %s" % SCRIPT)
    spec = importlib.util.spec_from_file_location("oa_workflow_ones_lp", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["oa_workflow_ones_lp"] = mod
    spec.loader.exec_module(mod)
    return mod


m = _load()


def _task(name: str, desc: str, number: int = 1) -> dict:
    return {"number": number, "name": name, "descriptionText": desc}


# ============ 真实语料（2026-11-19 ONES 实查原文）============

# SSXM-2026-0810-2066 #381666
REAL_381666 = ("客户名称：招商银行股份有限公司 / 客户标识：1c3271f0-c02b-447c-a4c6-d53fdff29c1d"
               "项目编号：SSXM-2026-0810-2066 / 使用产品：安卓加固、源码iOS加固；"
               "授权时间：2026年8月11日 至 2027年8月11日 / APP数量：Android12个；IOS12个。")
# SSXM-2026-0810-2066 #385446（依据验收报告的授权调整）
REAL_385446 = ("客户名称：招商银行股份有限公司 / 授权时间：2026年8月14日 至 2027年8月14日 / "
               "APP数量：Android12个；IOS12个。")
# SSXM-2026-0810-2066 #390160（信用卡中心项目组，同产品不同客户标识）
REAL_390160 = ("客户名称：招商银行股份有限公司信用卡中心 / "
               "IOS加固引擎类型：源到源+IPA授权时间：2026年8月11日 至 2027年8月11日 / "
               "APP数量：1个APP，多个包名")
# SSXM-2026-0624-1641 #399765（「号」+ 无空格分隔）
REAL_399765 = ("客户标识：c8db4256-30bd-4f5d-ae5e-4b8a2edf1dda客户名称：浙江省农村信用社"
               "加固账号：zjnx    密码：zjnx#$ / 授权产品：Android应用加固，IOS源码加固。 / "
               "授权时间：2026年11月18号至2026年11月30号 / 项目编号：SSXM-2026-0624-1641 / "
               "部署类别：私有化软件 / 版本：v7.5.1")
# 真实维保任务：描述为空（不得伪造期限）
REAL_WEIBAO_EMPTY = ""


def test_real_381666():
    period, evid = m.license_period([_task("【黑盒6.0/黑盒7.8】招商银行股份有限公司-应用加固-授权续期", REAL_381666, 381666)])
    assert period == "2026-08-11 ~ 2027-08-11"
    assert evid == "381666"


def test_real_399765_hao_no_space():
    period, evid = m.license_period([_task("【黑盒7.5.1】浙江农村商业联合银行股份有限公司-应用加固-license延期", REAL_399765, 399765)])
    assert period == "2026-11-18 ~ 2026-11-30"
    assert evid == "399765"


def test_real_390160_no_separator_space():
    # 「源到源+IPA授权时间：」前缀紧贴，正则须仍命中
    period, _ = m.license_period([_task("【黑盒6.0/黑盒7.8】-信用卡中心项目组-授权license", REAL_390160, 390160)])
    assert period == "2026-08-11 ~ 2027-08-11"


# ============ 跨任务聚合：取结束日最晚（真实场景：续期/验收调整）============
def test_latest_end_wins_real():
    tasks = [
        _task("【黑盒6.0/黑盒7.8】-应用加固-授权续期", REAL_381666, 381666),
        _task("【黑盒6.0/黑盒7.8】-应用加固-授权调整（依据验收报告）", REAL_385446, 385446),
    ]
    period, evid = m.license_period(tasks)
    assert period == "2026-08-11 ~ 2027-08-14"
    assert evid == "385446"


def test_latest_end_wins_synthetic():
    tasks = [
        _task("云端-license授权", "授权时间：2026年8月11日 至 2027年8月11日", 1),
        _task("授权续期", "授权时间：2027年8月11日 至 2028年8月10日", 2),
    ]
    period, evid = m.license_period(tasks)
    assert period == "2026-08-11 ~ 2028-08-10"
    assert evid == "2"


# ============ ISO 回归（不得破坏）============
@pytest.mark.parametrize("desc,expect", [
    ("授权时间：2026-08-11 ~ 2027-08-11", "2026-08-11 ~ 2027-08-11"),
    ("授权期限：2026-08-11-2027-08-11", "2026-08-11 ~ 2027-08-11"),
    ("授权时间：2026.08.11至2027.08.11", "2026-08-11 ~ 2027-08-11"),
    ("维保期限：2026年6月1日 至 2027年5月31日", "2026-06-01 ~ 2027-05-31"),
])
def test_iso_and_weibao(desc, expect):
    assert m.license_period([_task("license", desc, 7)])[0] == expect


# ============ 负例 ============
def test_weibao_empty_desc_no_fabricate():
    """真实维保任务描述为空 → 必须返回空，不得用其他任务或合同期伪造。"""
    assert m.license_period([_task("【维保】私有化软件-Android应用加固软件V7.0-维保", REAL_WEIBAO_EMPTY, 381536)]) == ("", "")


def test_non_license_task_ignored():
    assert m.license_period([_task("【子验收】交付", "授权时间：2026年1月1日 至 2026年12月31日", 1)]) == ("", "")


def test_no_date_empty_input():
    assert m.license_period([_task("license", "授权功能：Android 加固", 1)]) == ("", "")
    assert m.license_period([]) == ("", "")


# ============ norm_date ============
@pytest.mark.parametrize("raw,expect", [
    ("2026年8月11日", "2026-08-11"),
    ("2026年11月18号", "2026-11-18"),
    ("2026-08-11", "2026-08-11"),
    ("2026.8.1", "2026-08-01"),
    ("无日期", "无日期"),
])
def test_norm_date(raw, expect):
    assert m.norm_date(raw) == expect


# ============ 服务期前缀（2026-11-19 实测新增：POC/云端项目常只写「服务期」）============
# SSXM-2026-1014-2727 #392586 真实原文
REAL_392586 = ("客户名称：亳州药都农村商业银行股份有限公司\n客户标识：7532fd58-7ee8-41ec-bed0-3861a5f9efc5\n"
               "账号：bzydyh   密码：bzydyh12#$\n授权功能：小程序加固\n"
               "服务期：2026年10月14日-2026年11月14日\nAPP数量或包名：1\n"
               "项目编号：SSXM-2026-1014-2727\n签约版本类型：公有云版\n部署类别：云端\n部署版本：7.9")


def test_real_392586_service_period():
    """POC 云端项目只写「服务期」→ 必须提取（原实现只认「授权」，漏）。"""
    period, evid = m.license_period(
        [_task("【云端】亳州药都农村商业银行股份有限公司-应用加固-授权并配置策略", REAL_392586, 392586)]
    )
    assert period == "2026-10-14 ~ 2026-11-14"
    assert evid == "392586"


# ============ 无授权记录项目：必须标缺失，不得伪造 ============
def test_no_license_record_returns_empty():
    """安全服务/结算类项目（真实 858/2598 无 license 任务）→ 空，不伪造。"""
    tasks = [
        _task("【子验收】方正证券-隐私合规服务", "验收文件交接中", 1),
        _task("【子交付】方正证券-隐私合规服务", "交付邮件已归档", 2),
        _task("3.5天1.5万【合规测试】方正证券-小方", "测试账号：自行注册", 3),
    ]
    assert m.license_period(tasks) == ("", "")


# ============ 前缀优先级：授权 > 服务期 ============
def test_prefix_priority_license_over_service():
    """同一描述同时含「授权时间」与「服务期」→ 取授权（授权为准，服务期仅兜底）。"""
    desc = "授权时间：2026年1月1日 至 2026年12月31日\n服务期：2026年2月1日-2026年11月1日"
    period, _ = m.license_period([_task("云端-license", desc, 1)])
    assert period == "2026-01-01 ~ 2026-12-31"
