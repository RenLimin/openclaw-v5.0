"""BDMS 调度器

提供自动化调度和 WeCom 投递接口。
实际 cron 任务通过 OpenClaw 的 automations 工具配置。

用法:
  python3 -m scripts.l4.delivery_center.scheduler --list     # 列出推荐配置
  python3 -m scripts.l4.delivery_center.scheduler --setup     # 输出 cron 配置 JSON

已验证 2026-09-01。
"""

import json
from pathlib import Path
from datetime import datetime


# 推荐的 cron 配置
RECOMMENDED_CRONS = [
    {
        "name": "bdms-monthly-report",
        "displayName": "BDMS 月度报告生成",
        "schedule": {"kind": "cron", "expr": "0 10 1 * *", "tz": "Asia/Shanghai"},
        "description": "每月 1 日 10:00 自动生成上月交付月报和确收月报",
        "payload": {
            "kind": "agentTurn",
            "message": "运行 BDMS 月度报告生成流程，月份为上月。步骤：1) python3 -m scripts.l4.delivery_center.pipeline YYYYMM --clean-only 2) python3 -m scripts.l4.delivery_center.main YYYYMM --report-only 3) 报告路径在 ~/.openclaw/data/reports/ 下，通过 WeCom 投递给 Rex",
        },
    },
    {
        "name": "bdms-daily-scan",
        "displayName": "BDMS 每日数据采集",
        "schedule": {"kind": "cron", "expr": "0 2 * * *", "tz": "Asia/Shanghai"},
        "description": "每日 02:00 采集 OA/ONES/工时/WeCom 数据",
        "payload": {
            "kind": "agentTurn",
            "message": "运行 BDMS 数据采集流程。步骤：1) 采集 OA 合同台账 2) 采集 ONES 项目数据 3) 采集工时门户数据 4) 清洗并存入 SQLite",
        },
    },
    {
        "name": "bdms-health-check",
        "displayName": "BDMS 健康检查",
        "schedule": {"kind": "cron", "expr": "0 8 * * 1", "tz": "Asia/Shanghai"},
        "description": "每周一 08:00 检查数据完整性和系统健康",
        "payload": {
            "kind": "agentTurn",
            "message": "BDMS 健康检查：1) 检查数据库表行数是否正常 2) 检查最近一次报告生成是否成功 3) 检查 Cookie 是否过期 4) 汇报结果",
        },
    },
]


def list_crons():
    """列出推荐的 cron 配置"""
    print("=" * 60)
    print("BDMS 推荐 Cron 配置")
    print("=" * 60)
    for cron in RECOMMENDED_CRONS:
        print(f"\n  [{cron['name']}]")
        print(f"  显示名: {cron['displayName']}")
        print(f"  调度: {cron['schedule']['expr']} ({cron['schedule']['tz']})")
        print(f"  说明: {cron['description']}")
    print("\n" + "=" * 60)


def get_cron_json():
    """输出 cron 配置 JSON（可用于 automations add）"""
    print(json.dumps(RECOMMENDED_CRONS, ensure_ascii=False, indent=2))


def deliver_report_to_wecom(report_path: str, month: str):
    """投递报告到 WeCom（接口预留）

    实际投递通过 OpenClaw 的 WeCom channel 实现。
    在 cron 任务的 agentTurn 中调用 conversations_send 发送文件。

    Args:
        report_path: 报告文件路径
        month: 报告月份
    """
    print(f"[Scheduler] 投递报告到 WeCom: {report_path}")
    print("  实际投递请在 cron agentTurn 中调用:")
    print(f"    conversations_send(channel='wecom', message='确收月报-{month}', attachments=[{report_path}])")


def setup_crons():
    """输出 setup 指南"""
    print("=" * 60)
    print("BDMS Cron 设置指南")
    print("=" * 60)
    print()
    print("方式 1: 通过 OpenClaw CLI")
    print("  openclaw cron add --name bdms-monthly-report ...")
    print()
    print("方式 2: 通过 Jerry 配置")
    print("  告诉 Jerry: '设置 BDMS 月度报告 cron'")
    print("  我会通过 automations 工具创建")
    print()
    print("推荐配置:")
    for cron in RECOMMENDED_CRONS:
        print(f"  - {cron['displayName']}: {cron['schedule']['expr']}")
    print()
    print("=" * 60)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--json":
        get_cron_json()
    elif len(sys.argv) > 1 and sys.argv[1] == "--setup":
        setup_crons()
    else:
        list_crons()
