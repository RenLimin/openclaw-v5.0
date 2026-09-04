"""企业微信数据采集器

通过 wecom_mcp tool 读取企业微信智能表格中的确收/验收凭证数据。

数据来源（已验证 2026-09-01）：
  - 确收凭证/验收凭证在同一个智能表格里
  - URL: https://doc.weixin.qq.com/sheet/e3_AewA9wbYAJkCNWXLLXtMASV6kFQG5?scode=AD8AYAehAA801jsTMu
  - 品类：智能表格（smartsheet, doc_type=10）

采集方式：
  1. wecom_mcp tool → get_doc_content（异步轮询）
  2. 或 wecom_mcp tool → smartsheet_get_records（直接读取记录）

数据字段（参考本地 CSV）：
  - 确收凭证：标题、ID、BI履约ID、合同编号、客户名称、销售部门、项目经理、交接日期、财务、是否接收
  - 验收凭证：合同名称、标题、ID、BI履约ID、验收单编号、合同编号、客户名称、项目经理、交接日期、验收方式

注意：
  - wecom_mcp 是 MCP tool，需要通过 OpenClaw tool 系统调用
  - 首次调用需 wecom-preflight 检查白名单
  - 当前（2026-09-01）wecom_mcp 不在主会话可用 tool 列表，需要通过 WeCom channel 或配置解锁
  - 备选方案：Rex 手动从 WeCom 导出 CSV，脚本读取本地文件
"""

import json
import csv
import time
from pathlib import Path
from typing import Optional

EXPORT_DIR = Path.home() / ".openclaw" / "data" / "wecom_exports"

# WeCom 文档信息
WECOM_DOC_URL = "https://doc.weixin.qq.com/sheet/e3_AewA9wbYAJkCNWXLLXtMASV6kFQG5?scode=AD8AYAehAA801jsTMu"
WECOM_DOC_TYPE = "smartsheet"  # 智能表格

# 本地参考文件（用于开发和验证）
LOCAL_REVENUE_CSV = (
    Path.home() / "Bangcle Workspace" / "01. Management" / "2026" / "2026团队报告" / "202606" / "202606确收凭证交接-确收.csv"
)
LOCAL_ACCEPTANCE_CSV = (
    Path.home() / "Bangcle Workspace" / "01. Management" / "2026" / "2026团队报告" / "202606" / "202606确收凭证交接-验收.csv"
)


def _ensure_setup():
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)


def collect_from_local(
    month: str,
    export_dir: Optional[str] = None,
) -> Optional[dict]:
    """从本地 CSV 文件采集确收/验收数据（备选方案）

    Args:
        month: 报告月份（YYYYMM）
        export_dir: 导出目录

    Returns:
        {"revenue": {...}, "acceptance": {...}} 或 None
    """
    _ensure_setup()
    output_dir = Path(export_dir) if export_dir else EXPORT_DIR

    try:
        import pandas as pd
    except ImportError:
        print("ERROR: pandas 未安装")
        return None

    result = {}

    # 确收凭证
    if LOCAL_REVENUE_CSV.exists():
        print(f"[WeCom] 读取确收凭证: {LOCAL_REVENUE_CSV}")
        df_rev = pd.read_csv(LOCAL_REVENUE_CSV, encoding="utf-8-sig", low_memory=False)
        # 只保留核心字段
        core_cols = ["标题", "ID", "BI履约ID", "合同编号", "客户名称", "销售部门", "项目经理", "交接日期", "财务", "是否接收"]
        available_cols = [c for c in core_cols if c in df_rev.columns]
        df_rev = df_rev[available_cols]
        df_rev = df_rev.dropna(how="all", subset=["标题", "合同编号"])

        rev_file = output_dir / f"revenue_{month}.csv"
        df_rev.to_csv(rev_file, index=False, encoding="utf-8-sig")
        result["revenue"] = {"file": str(rev_file), "count": len(df_rev)}
        print(f"  ✅ 确收凭证: {len(df_rev)} 行 → {rev_file}")
    else:
        print(f"  ⚠️ 确收凭证文件不存在: {LOCAL_REVENUE_CSV}")

    # 验收凭证
    if LOCAL_ACCEPTANCE_CSV.exists():
        print(f"[WeCom] 读取验收凭证: {LOCAL_ACCEPTANCE_CSV}")
        df_acc = pd.read_csv(LOCAL_ACCEPTANCE_CSV, encoding="utf-8-sig", low_memory=False)
        core_cols = ["合同名称", "标题", "ID", "BI履约ID", "验收单编号-财务端", "合同编号", "客户名称", "项目经理", "交接日期", "验收方式"]
        available_cols = [c for c in core_cols if c in df_acc.columns]
        df_acc = df_acc[available_cols]
        df_acc = df_acc.dropna(how="all", subset=["标题", "合同编号"])

        acc_file = output_dir / f"acceptance_{month}.csv"
        df_acc.to_csv(acc_file, index=False, encoding="utf-8-sig")
        result["acceptance"] = {"file": str(acc_file), "count": len(df_acc)}
        print(f"  ✅ 验收凭证: {len(df_acc)} 行 → {acc_file}")
    else:
        print(f"  ⚠️ 验收凭证文件不存在: {LOCAL_ACCEPTANCE_CSV}")

    if not result:
        return None

    # 保存汇总 JSON
    summary = {
        "month": month,
        "source": "wecom_local_csv",
        "wecom_url": WECOM_DOC_URL,
        "data": result,
    }
    summary_file = output_dir / f"wecom_{month}_summary.json"
    summary_file.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  ✅ 汇总: {summary_file}")

    return summary


def collect_from_wecom(
    month: str,
    export_dir: Optional[str] = None,
) -> Optional[dict]:
    """从 WeCom 智能表格在线采集数据（需要 wecom_mcp tool）

    Args:
        month: 报告月份（YYYYMM）
        export_dir: 导出目录

    Returns:
        {"revenue": {...}, "acceptance": {...}} 或 None
    """
    _ensure_setup()
    output_dir = Path(export_dir) if export_dir else EXPORT_DIR

    """在线采集（预留接口，当前使用本地 CSV 方案）

    wecom_mcp 是 MCP tool，无法在 exec 环境中直接调用。
    当前方案：Rex 从企业微信导出 CSV → 脚本读取本地文件。
    未来方案：通过 cron agentTurn 调用 wecom_mcp tool 实现在线采集。
    """
    print(f"[WeCom] 在线采集预留接口（当前使用本地 CSV 方案）")
    print(f"  文档 URL: {WECOM_DOC_URL}")
    print(f"  提示：在线采集请通过 cron agentTurn 调用 wecom_mcp tool")

    # 回退到本地 CSV
    return collect_from_local(month, output_dir)


if __name__ == "__main__":
    import sys
    month = sys.argv[1] if len(sys.argv) > 1 else "202606"

    print("=== WeCom 数据采集 ===")
    print(f"月份: {month}")
    print()

    # 优先使用本地 CSV（开发和验证阶段）
    result = collect_from_local(month)

    if result:
        print(f"\n=== 采集完成 ===")
        for key, val in result.get("data", {}).items():
            print(f"  {key}: {val['count']} 行 → {val['file']}")
    else:
        print("\n=== 采集失败 ===")
