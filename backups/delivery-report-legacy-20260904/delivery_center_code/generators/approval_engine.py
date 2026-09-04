"""审批流程引擎

处理 OA 审批流程摘要和合同解析。

核心能力：
  1. 合同台账解析（从 OA 导出 Excel 提取关键字段）
  2. 审批摘要生成（统计审批状态）
  3. 确收项提取（从合同台账提取确收相关信息）

已验证 2026-09-01。
"""

import pandas as pd
from pathlib import Path
from typing import Optional

APPROVAL_DIR = Path.home() / ".openclaw" / "data" / "approvals"


def parse_contract_excel(excel_path: str) -> Optional[pd.DataFrame]:
    """解析 OA 销售合同信息查询台账

    Args:
        excel_path: OA 导出的 Excel 文件路径

    Returns:
        解析后的 DataFrame
    """
    if not Path(excel_path).exists():
        print(f"文件不存在: {excel_path}")
        return None

    df = pd.read_excel(excel_path)
    df.columns = [c.strip() for c in df.columns]
    print(f"  合同台账解析: {len(df)} 行 x {len(df.columns)} 列")
    return df


def extract_revenue_items(contract_df: pd.DataFrame) -> pd.DataFrame:
    """从合同台账提取确收项

    Args:
        contract_df: 合同台账数据

    Returns:
        确收项 DataFrame
    """
    # 核心字段映射
    revenue_cols = ["合同编号", "客户名称", "签约金额", "确收金额", "合同名称"]
    available_cols = [c for c in revenue_cols if c in contract_df.columns]

    if not available_cols:
        print("  ⚠️ 未找到确收相关列")
        return pd.DataFrame()

    result = contract_df[available_cols].copy()
    result = result.dropna(subset=["合同编号"])
    print(f"  确收项提取: {len(result)} 行")
    return result


def generate_approval_summary(approval_data: pd.DataFrame) -> str:
    """生成审批摘要报告

    Args:
        approval_data: 审批数据

    Returns:
        摘要文本
    """
    lines = []
    lines.append("=" * 50)
    lines.append("审批摘要报告")
    lines.append("=" * 50)
    lines.append(f"总数: {len(approval_data)}")

    if "审批状态" in approval_data.columns:
        status_counts = approval_data["审批状态"].value_counts()
        lines.append(f"\n审批状态分布:")
        for status, count in status_counts.items():
            lines.append(f"  {status}: {count}")

    if "是否接收" in approval_data.columns:
        receive_counts = approval_data["是否接收"].value_counts()
        lines.append(f"\n接收情况:")
        for status, count in receive_counts.items():
            lines.append(f"  {status}: {count}")

    if "财务是否接收" in approval_data.columns:
        fin_counts = approval_data["财务是否接收"].value_counts()
        lines.append(f"\n财务接收情况:")
        for status, count in fin_counts.items():
            lines.append(f"  {status}: {count}")

    if "部门" in approval_data.columns:
        dept_counts = approval_data["部门"].value_counts()
        lines.append(f"\n部门分布:")
        for dept, count in dept_counts.items():
            lines.append(f"  {dept}: {count}")

    lines.append("=" * 50)
    summary = "\n".join(lines)
    return summary


def generate_revenue_acceptance_summary(
    revenue_df: pd.DataFrame,
    acceptance_df: pd.DataFrame,
) -> str:
    """生成确收+验收汇总报告

    Args:
        revenue_df: 确收凭证数据
        acceptance_df: 验收凭证数据

    Returns:
        摘要文本
    """
    lines = []
    lines.append("=" * 50)
    lines.append("确收 & 验收汇总报告")
    lines.append("=" * 50)

    # 确收统计
    lines.append(f"\n【确收凭证】")
    lines.append(f"  总数: {len(revenue_df)}")

    if "是否接收" in revenue_df.columns:
        rev_receive = revenue_df["是否接收"].value_counts()
        for status, count in rev_receive.items():
            lines.append(f"  {status}: {count}")

    if "客户名称" in revenue_df.columns:
        rev_cust = revenue_df["客户名称"].nunique()
        lines.append(f"  涉及客户: {rev_cust} 个")

    # 验收统计
    lines.append(f"\n【验收凭证】")
    lines.append(f"  总数: {len(acceptance_df)}")

    if "财务是否接收" in acceptance_df.columns:
        acc_receive = acceptance_df["财务是否接收"].value_counts()
        for status, count in acc_receive.items():
            lines.append(f"  {status}: {count}")

    if "验收方式" in acceptance_df.columns:
        method_dist = acceptance_df["验收方式"].value_counts()
        lines.append(f"  验收方式:")
        for method, count in method_dist.head(5).items():
            lines.append(f"    {method}: {count}")

    # 关联统计
    if "合同编号" in revenue_df.columns and "合同编号" in acceptance_df.columns:
        rev_contracts = set(revenue_df["合同编号"].dropna().unique())
        acc_contracts = set(acceptance_df["合同编号"].dropna().unique())
        both = rev_contracts & acc_contracts
        lines.append(f"\n【关联统计】")
        lines.append(f"  有确收的合同: {len(rev_contracts)}")
        lines.append(f"  有验收的合同: {len(acc_contracts)}")
        lines.append(f"  两者都有: {len(both)}")

    lines.append("=" * 50)
    return "\n".join(lines)


if __name__ == "__main__":
    print("=== 审批流程引擎测试 ===\n")

    from scripts.l4.delivery_center.engines.join_engine import (
        load_revenue_vouchers,
        load_acceptance_vouchers,
    )

    rev_df = load_revenue_vouchers()
    acc_df = load_acceptance_vouchers()

    print("确收+验收汇总:")
    summary = generate_revenue_acceptance_summary(rev_df, acc_df)
    print(summary)
