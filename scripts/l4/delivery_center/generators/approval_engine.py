"""审批流程引擎

处理 OA 审批流程和合同解析。
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
    print(f"合同台账解析: {len(df)} 行 x {len(df.columns)} 列")
    return df


def extract_revenue_items(contract_df: pd.DataFrame) -> pd.DataFrame:
    """从合同台账提取确收项

    Args:
        contract_df: 合同台账数据

    Returns:
        确收项 DataFrame
    """
    # TODO: 根据实际列名提取确收项
    revenue_cols = ["合同编号", "客户名称", "签约金额", "确收金额"]
    available_cols = [c for c in revenue_cols if c in contract_df.columns]

    if not available_cols:
        print("未找到确收相关列")
        return pd.DataFrame()

    return contract_df[available_cols]


def generate_approval_summary(approval_data: pd.DataFrame) -> str:
    """生成审批摘要报告

    Args:
        approval_data: 审批数据

    Returns:
        摘要文本
    """
    summary = f"审批摘要\n"
    summary += f"总数: {len(approval_data)}\n"

    if "审批状态" in approval_data.columns:
        status_counts = approval_data["审批状态"].value_counts()
        for status, count in status_counts.items():
            summary += f"  {status}: {count}\n"

    return summary
